"""Vocal isolation service for the audio validation subsystem.

Defines the dataclasses and processing logic for isolating vocals
from harvested audio samples using Demucs source separation.

Heavy dependencies (torch, torchaudio) are imported lazily inside
methods that need them, so the module can be loaded for CLI argument
parsing and dependency checks without requiring PyTorch installed.
"""

import sys
import os
import json
import time
import threading
import pathlib
from dataclasses import dataclass, asdict


@dataclass
class IsolationResult:
    """Result of vocal isolation via Demucs source separation."""

    input_path: str
    output_path: str
    duration_seconds: float  # duration of isolated track in seconds
    model_name: str  # e.g., "htdemucs_ft"
    device: str  # "cuda" or "cpu"
    processing_time_seconds: float
    gpu_unavailable: bool  # True if fell back to CPU


@dataclass
class IsolationError:
    """Structured error from the isolation service."""

    error: str  # Human-readable description
    dependency: str | None  # Package name if dependency issue, else None
    input_path: str


# Module-level demucs availability check
try:
    import demucs
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False


class VocalIsolator:
    """Service for isolating vocals from audio using Demucs source separation."""

    def _load_model(self, device: str) -> tuple:
        """Load the htdemucs_ft model and move it to the specified device.

        Args:
            device: Target device ('cuda' or 'cpu')

        Returns:
            Tuple of (model, actual_device, gpu_unavailable)
        """
        from demucs.pretrained import get_model
        
        try:
            model = get_model('htdemucs_ft')
            model = model.to(device)
            model.eval()
            return (model, device, False)
        except RuntimeError as e:
            if device == 'cuda':
                # Fall back to CPU
                model = get_model('htdemucs_ft')
                model = model.to('cpu')
                model.eval()
                return (model, 'cpu', True)
            raise

    def _separate(self, model, audio: "torch.Tensor", device: str) -> "torch.Tensor":
        """Separate sources using the model and return vocals.

        Args:
            model: Loaded Demucs model
            audio: Audio tensor
            device: Device used for processing

        Returns:
            Vocals tensor
        """
        import torch
        from demucs.apply import apply_model
        
        audio = audio.to(device)
        with torch.no_grad():
            sources = apply_model(model, audio[None])
        # For htdemucs_ft, source order is: drums, bass, other, vocals (index 3)
        vocals = sources[0, 3]
        return vocals.cpu()

    def _segment_and_process(
        self, model, waveform: "torch.Tensor", device: str, sample_rate: int, input_path: str = ""
    ) -> "torch.Tensor | IsolationError":
        """Process audio by segmenting long files and stitching results.

        For audio > 600 seconds: split into chunks of at most 300 seconds with
        10 seconds overlap between adjacent chunks. Process each chunk independently
        through Demucs, then stitch using linear crossfading.

        Args:
            model: Loaded Demucs model
            waveform: Audio tensor of shape (channels, samples)
            device: Device used for processing
            sample_rate: Sample rate of the audio
            input_path: Path to original input file (for error reporting)

        Returns:
            Processed vocals tensor on success, IsolationError on failure
        """
        max_chunk_duration = 300  # seconds
        overlap_duration = 10  # seconds
        max_chunk_samples = int(max_chunk_duration * sample_rate)
        overlap_samples = int(overlap_duration * sample_rate)

        total_samples = waveform.shape[1]
        step_samples = max_chunk_samples - overlap_samples  # advance by chunk minus overlap

        chunks: list[torch.Tensor] = []
        chunk_num = 0
        start = 0

        while start < total_samples:
            end = min(start + max_chunk_samples, total_samples)
            chunk = waveform[:, start:end]

            try:
                vocals = self._separate(model, chunk, device)
                chunks.append(vocals)
            except Exception as e:
                # Stop immediately, discard all partial results
                return IsolationError(
                    error=f"Failed to process chunk {chunk_num}: {str(e)}",
                    dependency=None,
                    input_path=input_path,
                )

            chunk_num += 1
            start += step_samples

        if len(chunks) == 0:
            return IsolationError(
                error="No chunks were produced from segmentation",
                dependency=None,
                input_path=input_path,
            )

        return self._crossfade_stitch(chunks, overlap_samples)

    def _crossfade_stitch(self, chunks: "list[torch.Tensor]", overlap_samples: int) -> "torch.Tensor":
        """Apply linear crossfade between adjacent audio chunks.

        For the overlap region: chunk N fades out linearly from 1.0 to 0.0 over
        the last overlap_samples, chunk N+1 fades in linearly from 0.0 to 1.0 over
        the first overlap_samples, then sum the two faded regions sample-by-sample.

        The linear crossfade guarantees amplitude continuity because at every
        sample in the overlap region: fade_out[i] + fade_in[i] = 1.0. This means
        when both chunks have equal values in the overlap, the output equals that
        value exactly — no discontinuity.

        Args:
            chunks: List of audio tensors (channels, samples) to stitch together
            overlap_samples: Number of samples in the overlap region between chunks

        Returns:
            Stitched audio tensor with crossfades applied
        """
        import torch
        if len(chunks) == 1:
            return chunks[0]

        # Linear fade curves, shape (1, overlap_samples) for broadcasting
        fade_out = torch.linspace(1.0, 0.0, overlap_samples).unsqueeze(0)
        fade_in = torch.linspace(0.0, 1.0, overlap_samples).unsqueeze(0)

        result = chunks[0]

        for i in range(1, len(chunks)):
            curr_chunk = chunks[i]

            if overlap_samples > 0 and result.shape[1] >= overlap_samples:
                # Overlap region from accumulated result (its tail)
                prev_overlap = result[:, -overlap_samples:]
                # Overlap region from current chunk (its head)
                curr_overlap = curr_chunk[:, :overlap_samples]

                # Apply linear crossfade
                crossfaded = prev_overlap * fade_out + curr_overlap * fade_in

                # Build new result: non-overlapping head + crossfaded region + non-overlapping tail
                result = torch.cat(
                    [result[:, :-overlap_samples], crossfaded, curr_chunk[:, overlap_samples:]],
                    dim=1,
                )
            else:
                # No overlap or chunk too short — simple concatenation
                result = torch.cat([result, curr_chunk], dim=1)

        return result

    @staticmethod
    def _cleanup_partial(output_path: str) -> None:
        """Clean up partial output file if it exists.

        Args:
            output_path: Path to the output file to clean up
        """
        try:
            path = pathlib.Path(output_path)
            if path.exists():
                path.unlink()
        except OSError:
            # Silent on cleanup errors
            pass

    def isolate(self, input_path: str, output_path: str) -> "IsolationResult | IsolationError":
        """Isolate vocals from input audio file and save to output path.

        Args:
            input_path: Path to input audio file
            output_path: Path where isolated vocals will be saved

        Returns:
            IsolationResult on success, IsolationError on failure
        """
        import torch
        import soundfile as sf
        import numpy as np

        start_time = time.time()
        model = None
        
        try:
            # Load audio using soundfile directly (torchaudio 2.11 forces torchcodec)
            audio_data, sample_rate = sf.read(input_path, dtype='float32')
            # soundfile returns (samples, channels) for multi-channel, (samples,) for mono
            if audio_data.ndim == 1:
                waveform = torch.from_numpy(audio_data).unsqueeze(0)  # (1, samples)
            else:
                waveform = torch.from_numpy(audio_data.T)  # (channels, samples)
            
            # Track original channel count for output
            original_channels = waveform.shape[0]
            
            # Demucs htdemucs_ft expects stereo (2-channel) input
            # Duplicate mono to stereo for processing
            if waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)  # (1, samples) -> (2, samples)
            
            # Determine device
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            # Load model
            model, actual_device, gpu_unavailable = self._load_model(device)
            
            # Check duration and process accordingly
            duration_seconds = waveform.shape[1] / sample_rate
            
            if duration_seconds > 600:
                # Use segmentation for long audio files
                vocals = self._segment_and_process(model, waveform, actual_device, sample_rate, input_path)
                
                # Handle error from segmentation
                if isinstance(vocals, IsolationError):
                    return vocals
            else:
                # Use existing path for short audio files
                vocals = self._separate(model, waveform, actual_device)
            
            # Convert output back to original channel count
            output_channels = vocals.shape[0]
            
            if original_channels != output_channels:
                if original_channels == 1 and output_channels == 2:
                    # Convert stereo output back to mono by taking mean
                    vocals = vocals.mean(dim=0, keepdim=True)
                elif original_channels == 2 and output_channels == 1:
                    # Convert mono to stereo by duplicating
                    vocals = vocals.repeat(2, 1)
            
            # Save output as PCM 16-bit WAV using soundfile
            vocals_np = vocals.cpu().numpy()
            # soundfile expects (samples, channels) shape
            if vocals_np.ndim == 2:
                vocals_np = vocals_np.T  # (channels, samples) -> (samples, channels)
            sf.write(output_path, vocals_np, sample_rate, subtype='PCM_16')
            
            # Calculate duration and processing time
            duration_seconds = vocals.shape[-1] / sample_rate
            processing_time = time.time() - start_time
            
            return IsolationResult(
                input_path=input_path,
                output_path=output_path,
                duration_seconds=duration_seconds,
                model_name='htdemucs_ft',
                device=actual_device,
                processing_time_seconds=processing_time,
                gpu_unavailable=gpu_unavailable
            )
            
        except torch.cuda.OutOfMemoryError as e:
            torch.cuda.empty_cache()
            self._cleanup_partial(output_path)
            return IsolationError(
                error=f'CUDA out of memory: {str(e)}',
                dependency=None,
                input_path=input_path
            )
        except Exception as e:
            self._cleanup_partial(output_path)
            return IsolationError(
                error=str(e),
                dependency=None,
                input_path=input_path
            )
        finally:
            # Ensure model is released and GPU memory is freed
            if model is not None:
                del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m src.audio_validation.isolator <input_path> <output_path>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not DEMUCS_AVAILABLE:
        error_result = IsolationError(
            error="Demucs dependency is required but not installed",
            dependency="demucs",
            input_path=input_path
        )
        print(json.dumps(asdict(error_result)), file=sys.stderr)
        sys.exit(1)
    
    # Check if input file exists
    if not os.path.exists(input_path):
        error_result = IsolationError(
            error=f"Input file does not exist: {input_path}",
            dependency=None,
            input_path=input_path
        )
        print(json.dumps(asdict(error_result)), file=sys.stderr)
        sys.exit(1)
    
    # Set up timeout using threading.Timer
    timer = None
    
    def timeout_handler():
        VocalIsolator._cleanup_partial(output_path)
        error_result = IsolationError(
            error="Timeout: processing exceeded 600 seconds",
            dependency=None,
            input_path=input_path
        )
        print(json.dumps(asdict(error_result)), file=sys.stderr)
        os._exit(1)
    
    # Start timeout timer
    timer = threading.Timer(600.0, timeout_handler)
    timer.daemon = True
    timer.start()
    
    try:
        isolator = VocalIsolator()
        result = isolator.isolate(input_path, output_path)
        
        if isinstance(result, IsolationResult):
            print(json.dumps(asdict(result)))
        else:
            print(json.dumps(asdict(result)), file=sys.stderr)
            sys.exit(1)
    finally:
        # Cancel the timer on completion
        if timer and timer.is_alive():
            timer.cancel()