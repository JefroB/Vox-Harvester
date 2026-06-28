---
name: Performance
tags: [code, optimization]
description: Profiling, caching, async patterns, algorithmic optimization, memory.
---

# Performance

## Core Principle

Measure first, optimize second. Fast code that's wrong is worthless. Correct code that's slow can be improved.

## When to Optimize

- When you have evidence of a problem (profiling data, user complaints, SLA violations)
- When the algorithm is obviously wrong (O(n²) on large data when O(n log n) exists)
- When you're making an architectural decision that's hard to change later (choose the faster path upfront)

### Do NOT optimize:
- Based on intuition without measurement
- Code that runs once at startup
- Code paths that handle <100 items
- To save microseconds in non-hot paths

## Profiling First

- Use the language's built-in profiler before changing anything
- Identify the actual bottleneck — it's rarely where you think
- Measure before AND after to prove the optimization helped
- Track wall time, CPU time, and memory separately

## Common Wins (low effort, high impact)

### Algorithmic
- Replace nested loops with hash maps/sets for lookups (O(n²) → O(n))
- Sort once, binary search many times
- Use appropriate data structures: set for membership, map for lookup, queue for FIFO
- Avoid re-computing the same value in a loop — cache it above

### I/O
- Batch database queries (N+1 problem: fetch all at once, not one per loop iteration)
- Use connection pooling
- Stream large files instead of loading fully into memory
- Parallelize independent I/O operations (async/await, Promise.all)

### Memory
- Avoid unnecessary copies of large data
- Release references to large objects when no longer needed
- Use streaming/iterators for large datasets instead of collecting into arrays
- Watch for memory leaks: event listeners, closures capturing large scopes, growing caches

### Caching
- Cache expensive computations with clear invalidation rules
- Use appropriate TTLs — stale data is a bug
- Cache at the right layer: in-process, distributed, CDN
- Know your cache-hit ratio — below 80% means your key strategy is wrong

## Async & Concurrency

- Use async I/O for network/disk operations — don't block threads waiting
- Parallelize independent work, serialize dependent work
- Use worker pools for CPU-bound tasks
- Be aware of concurrency bugs: race conditions, deadlocks, starvation

## Anti-Patterns

- ❌ Premature optimization based on "this might be slow"
- ❌ Micro-optimizing (bit shifts instead of division) in application code
- ❌ Caching without invalidation strategy
- ❌ Loading entire tables/files into memory "just in case"
- ❌ Synchronous I/O in request handlers
- ❌ Optimizing cold paths while the hot path is untouched
- ❌ Adding complexity for a 2% speedup that makes code unreadable

## Performance Checklist for New Features

1. What's the expected data size? (10 items vs 10 million)
2. What's the algorithmic complexity? Is it appropriate for the scale?
3. How many I/O calls does this make? Can they be batched?
4. Is there a caching opportunity? What's the invalidation story?
5. Will this block a thread or event loop?
