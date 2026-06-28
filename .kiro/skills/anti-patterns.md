---
name: Anti-Patterns to Avoid
tags: [always]
description: Critical coding mistakes to NEVER make. Injected into every generation call.
---

# Anti-Patterns — NEVER Do These

These are patterns that produce buggy code. Avoid them unconditionally.

## Concurrency

### NEVER sleep or await inside a lock
```python
# ❌ WRONG — blocks all other threads/tasks while sleeping
async with self._lock:
    if not enough_tokens:
        await asyncio.sleep(delay)  # DEADLOCK: nobody else can acquire the lock

# ❌ WRONG — same issue with threading.Lock
with self._lock:
    while not ready:
        time.sleep(0.01)  # DEADLOCK: lock held, other threads blocked
```

```python
# ✅ CORRECT — lock only around state mutation, sleep outside
async with self._lock:
    has_tokens = self._tokens >= requested
    if has_tokens:
        self._tokens -= requested

if not has_tokens:
    await asyncio.sleep(delay)  # Outside the lock
```

### NEVER hold locks during I/O operations
```python
# ❌ WRONG — HTTP request under lock
async with self._lock:
    response = await session.get(url)  # Blocks all other callers

# ✅ CORRECT — check state under lock, do I/O outside
async with self._lock:
    if self._state == State.OPEN:
        raise CircuitOpenError()

response = await session.get(url)  # Outside lock

async with self._lock:
    self._record_success()
```

### NEVER use busy-spin loops without sleep
```python
# ❌ WRONG — burns 100% CPU
while not self._queue:
    pass  # Busy spin

# ✅ CORRECT — use an event or blocking queue
item = await self._queue.get()  # Blocks efficiently
```

## Resource Management

### NEVER create background threads/timers without daemon=True
```python
# ❌ WRONG — prevents process from exiting
self._timer = threading.Timer(60, self._cleanup)
self._timer.start()  # Process hangs on exit

# ✅ CORRECT
self._timer = threading.Timer(60, self._cleanup)
self._timer.daemon = True
self._timer.start()
```

### NEVER forget to provide a shutdown/cleanup method
If your class creates background tasks, timers, or connections, it MUST have a way to stop them cleanly.

## Error Handling

### NEVER raise bare Exception
```python
# ❌ WRONG
raise Exception("something failed")

# ✅ CORRECT — use specific exception types
raise ConnectionError(f"Failed to connect to {host}:{port}")
raise ValueError(f"Rate must be positive, got {rate}")
```

### NEVER catch and ignore exceptions
```python
# ❌ WRONG
try:
    do_thing()
except Exception:
    pass  # Silently swallowed

# ✅ CORRECT
try:
    do_thing()
except SpecificError as e:
    logger.warning(f"Non-critical failure: {e}")
```

## Data Structures

### NEVER sort a collection on every insert
```python
# ❌ WRONG — O(n log n) per insert
self._queue.append(item)
self._queue = sorted(self._queue, key=lambda x: x.priority)

# ✅ CORRECT — use a heap or priority queue
import heapq
heapq.heappush(self._queue, item)  # O(log n) per insert
# Or for async: asyncio.PriorityQueue
```

### NEVER use defaultdict when you need cleanup
```python
# ❌ WRONG — entries accumulate forever
self._buckets = defaultdict(lambda: TokenBucket())
# No way to know which keys are stale

# ✅ CORRECT — track last access time, provide cleanup
self._buckets: dict[str, TokenBucket] = {}
self._last_access: dict[str, float] = {}
```

## Async

### NEVER mix sync sleep with async code
```python
# ❌ WRONG — blocks the entire event loop
async def retry():
    time.sleep(5)  # Blocks everything

# ✅ CORRECT
async def retry():
    await asyncio.sleep(5)  # Yields to event loop
```

### NEVER forget that asyncio.Lock is NOT reentrant
```python
# ❌ WRONG — will deadlock if method_a calls method_b
async def method_a(self):
    async with self._lock:
        await self.method_b()

async def method_b(self):
    async with self._lock:  # DEADLOCK — already held by method_a
        pass
```
