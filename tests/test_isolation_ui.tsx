/// <reference types="@testing-library/jest-dom" />
import React from "react";
import { render, screen, waitFor, act, cleanup } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import Library from "../src/components/Library";

// Mock the lucide-react icons to avoid rendering SVGs in jsdom
vi.mock("lucide-react", () => ({
  Music: () => <div data-testid="music-icon" />,
  Search: () => <div data-testid="search-icon" />,
  Filter: () => <div data-testid="filter-icon" />,
  Play: () => <div data-testid="play-icon" />,
  Pause: () => <div data-testid="pause-icon" />,
  Download: () => <div data-testid="download-icon" />,
  Trash2: () => <div data-testid="trash-icon" />,
  Tag: () => <div data-testid="tag-icon" />,
  Plus: () => <div data-testid="plus-icon" />,
  X: () => <div data-testid="x-icon" />,
  Sparkles: () => <div data-testid="sparkles-icon" />,
  CheckCircle2: () => <div data-testid="check-circle-icon" />,
  ChevronRight: () => <div data-testid="chevron-right-icon" />,
  Volume2: () => <div data-testid="volume-icon" />,
  Flame: () => <div data-testid="flame-icon" />,
  RefreshCcw: () => <div data-testid="refresh-icon" />,
  Loader2: () => <div data-testid="loader-icon" />,
}));

describe("Library Component - Vocal Isolation UI", () => {
  const sampleWithoutIsolation = {
    id: "sample1",
    phrase_text: "Hello world",
    video_id: "video1",
    video_title: "Test Video 1",
    start_time: 0,
    duration: 5,
    file_path: "/path/to/sample1.wav",
    energy_score: 0.75,
    is_processed: false,
    createdAt: "2023-01-01T00:00:00Z",
    tags: [],
  };

  const sampleWithIsolation = {
    id: "sample2",
    phrase_text: "Goodbye world",
    video_id: "video2",
    video_title: "Test Video 2",
    start_time: 10,
    duration: 3,
    file_path: "/path/to/sample2.wav",
    isolated_path: "/api/samples/audio/sample2_isolated",
    energy_score: 0.65,
    is_processed: true,
    createdAt: "2023-01-01T00:00:00Z",
    tags: [],
  };

  beforeEach(() => {
    vi.useFakeTimers();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function setupFetchForSamples(samples: any[], extraHandlers?: Record<string, () => Promise<any>>) {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, options?: any) => {
      if (typeof url === "string" && url.startsWith("/api/samples?")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ samples, tagFacets: {} }),
        });
      }
      if (extraHandlers) {
        for (const [pattern, handler] of Object.entries(extraHandlers)) {
          if (url === pattern) return handler();
        }
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  }

  async function renderLibraryAndLoad() {
    let result: ReturnType<typeof render>;
    await act(async () => {
      result = render(<Library refreshTrigger={0} />);
      // Flush the initial fetch promise by running all pending timers and microtasks
      await vi.runAllTimersAsync();
    });
    return result!;
  }

  // Requirement 5.1: Button renders for samples without isolated_path
  it("renders Isolate button for samples without isolated_path", async () => {
    setupFetchForSamples([sampleWithoutIsolation]);
    await renderLibraryAndLoad();

    expect(document.getElementById("sample-card-sample1")).toBeInTheDocument();
    expect(screen.getByText("Isolate")).toBeInTheDocument();
  });

  // Requirement 5.1: Button hidden for samples with isolated_path
  it("does not render Isolate button for samples with isolated_path", async () => {
    setupFetchForSamples([sampleWithIsolation]);
    await renderLibraryAndLoad();

    expect(document.getElementById("sample-card-sample2")).toBeInTheDocument();
    expect(screen.queryByText("Isolate")).not.toBeInTheDocument();
  });

  // Requirement 5.2: Button becomes disabled on click, shows loading
  it("disables button and shows loading indicator on click", async () => {
    setupFetchForSamples([sampleWithoutIsolation], {
      "/api/samples/sample1/isolate": () => Promise.resolve({
        ok: true,
        status: 202,
        json: () => Promise.resolve({ jobId: "job-abc-123" }),
      }),
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      // Only flush microtasks without advancing time — don't let polling fire
      await Promise.resolve();
    });

    expect(screen.getByText("Isolating...")).toBeInTheDocument();
    const loadingButton = screen.getByText("Isolating...").closest("button")!;
    expect(loadingButton).toBeDisabled();
  });

  // Requirement 5.2: POST request sent to correct URL on click
  it("sends POST to /api/samples/:id/isolate on click", async () => {
    setupFetchForSamples([sampleWithoutIsolation], {
      "/api/samples/sample1/isolate": () => Promise.resolve({
        ok: true,
        status: 202,
        json: () => Promise.resolve({ jobId: "job-abc-123" }),
      }),
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledWith("/api/samples/sample1/isolate", {
      method: "POST",
    });
  });

  // Requirement 5.3: On 202 response, polling starts at /api/jobs/:jobId
  it("starts polling /api/jobs/:jobId after 202 response", async () => {
    setupFetchForSamples([sampleWithoutIsolation], {
      "/api/samples/sample1/isolate": () => Promise.resolve({
        ok: true,
        status: 202,
        json: () => Promise.resolve({ jobId: "job-abc-123" }),
      }),
      "/api/jobs/job-abc-123": () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: "pending" }),
      }),
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Advance 3 seconds to trigger first poll
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledWith("/api/jobs/job-abc-123");
  });

  // Requirement 5.3: Status text updates shown (pending, processing)
  it("displays job status text during polling", async () => {
    let pollCount = 0;
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, options?: any) => {
      if (typeof url === "string" && url.startsWith("/api/samples?")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ samples: [sampleWithoutIsolation], tagFacets: {} }),
        });
      }
      if (url === "/api/samples/sample1/isolate") {
        return Promise.resolve({
          ok: true,
          status: 202,
          json: () => Promise.resolve({ jobId: "job-abc-123" }),
        });
      }
      if (url === "/api/jobs/job-abc-123") {
        pollCount++;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "processing" }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    // Click triggers POST and startPolling sets initial "pending" status
    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    // "pending" is set immediately in startPolling before any interval fires
    expect(screen.getByText("pending")).toBeInTheDocument();

    // First poll at 3s — returns "processing"
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("processing")).toBeInTheDocument();
  });

  // Requirement 5.4: On completed status, button disappears and library refreshes
  it("removes loading state and refreshes library on completed status", async () => {
    let fetchCallCount = 0;
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, options?: any) => {
      if (typeof url === "string" && url.startsWith("/api/samples?")) {
        fetchCallCount++;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ samples: [sampleWithoutIsolation], tagFacets: {} }),
        });
      }
      if (url === "/api/samples/sample1/isolate") {
        return Promise.resolve({
          ok: true,
          status: 202,
          json: () => Promise.resolve({ jobId: "job-abc-123" }),
        });
      }
      if (url === "/api/jobs/job-abc-123") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "completed" }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderLibraryAndLoad();

    const initialFetchCount = fetchCallCount;
    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Advance to trigger poll — returns "completed"
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // After completed, fetchLibrary should be called again (refresh)
    expect(fetchCallCount).toBeGreaterThan(initialFetchCount);
    // The isolating state should be cleared
    expect(screen.queryByText("Isolating...")).not.toBeInTheDocument();
  });

  // Requirement 5.5: On failed status, error displayed and button re-enabled
  it("shows error and re-enables button on failed status", async () => {
    setupFetchForSamples([sampleWithoutIsolation], {
      "/api/samples/sample1/isolate": () => Promise.resolve({
        ok: true,
        status: 202,
        json: () => Promise.resolve({ jobId: "job-abc-123" }),
      }),
      "/api/jobs/job-abc-123": () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: "failed", error: "Demucs model failed to load" }),
      }),
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Error message should appear
    expect(screen.getByText("Demucs model failed to load")).toBeInTheDocument();
    // Button should be re-enabled
    const btn = screen.getByText("Isolate").closest("button")!;
    expect(btn).not.toBeDisabled();
  });

  // Requirement 5.7: On network error, error displayed and button re-enabled
  it("shows error and re-enables button on network error during POST", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, options?: any) => {
      if (typeof url === "string" && url.startsWith("/api/samples?")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ samples: [sampleWithoutIsolation], tagFacets: {} }),
        });
      }
      if (url === "/api/samples/sample1/isolate") {
        return Promise.reject(new Error("Network error"));
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Error message should appear
    expect(screen.getByText("Network error")).toBeInTheDocument();
    // Button should be re-enabled
    const btn = screen.getByText("Isolate").closest("button")!;
    expect(btn).not.toBeDisabled();
  });

  // Requirement 5.8: On 180s polling timeout, timeout error displayed
  it("shows timeout error and re-enables button after 180s polling", async () => {
    setupFetchForSamples([sampleWithoutIsolation], {
      "/api/samples/sample1/isolate": () => Promise.resolve({
        ok: true,
        status: 202,
        json: () => Promise.resolve({ jobId: "job-abc-123" }),
      }),
      "/api/jobs/job-abc-123": () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: "pending" }),
      }),
    });

    await renderLibraryAndLoad();

    const button = screen.getByText("Isolate").closest("button")!;

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Advance past 180 seconds in steps to trigger intervals
    for (let i = 0; i < 61; i++) {
      await act(async () => {
        vi.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
      });
    }

    // Timeout error should appear
    expect(screen.getByText("Operation timed out after 180 seconds")).toBeInTheDocument();
    // Button should be re-enabled
    const btn = screen.getByText("Isolate").closest("button")!;
    expect(btn).not.toBeDisabled();
  }, 30000);
});
