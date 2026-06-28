---
name: Fast-Check Patterns
tags: [test, code]
description: Correct patterns and anti-patterns for fast-check property-based tests.
---

# Fast-Check Patterns

## Purpose
Guide local model generation of fast-check property-based tests. Prevents the most common generation errors: broken shrinking, impossible boundaries, and Math.random misuse.

## Core Principle: Shrinking Contract

fast-check controls the random generation AND the shrinking. If you bypass its generators (e.g., using Math.random()), shrinking breaks and test failure messages become useless.

**Rule:** NEVER use `Math.random()`, `Date.now()`, or any non-deterministic source inside `fc.property`. All randomness must come from fast-check arbitraries.

## Correct Patterns

### Constrained Pairs (a < b)

```typescript
// CORRECT: Use fc.tuple + map to ensure a < b
const ascendingPair = fc.tuple(fc.integer(), fc.integer()).map(([x, y]) => 
  x <= y ? [x, y] : [y, x]
);

// CORRECT: Use fc.integer with constraints
const rangeArb = fc.integer({ min: 0, max: 100 }).chain(min =>
  fc.integer({ min, max: 100 }).map(max => ({ min, max }))
);
```

### Ascending Arrays

```typescript
// CORRECT: Generate array then sort
const ascendingArray = fc.array(fc.integer()).map(arr => [...arr].sort((a, b) => a - b));

// CORRECT: Generate deltas and accumulate
const ascendingFromDeltas = fc.array(fc.nat()).map(deltas => {
  let acc = 0;
  return deltas.map(d => { acc += d; return acc; });
});
```

### Constrained Records

```typescript
// CORRECT: Build records with dependent fields
const validConfig = fc.record({
  min: fc.integer({ min: 0, max: 50 }),
  max: fc.integer({ min: 51, max: 100 }),
  name: fc.string({ minLength: 1, maxLength: 50 }),
});
```

### Float/Double with Constraints

```typescript
// CORRECT: Always use noNaN to avoid NaN propagation
const safeFloat = fc.float({ noNaN: true, noDefaultInfinity: true });
const safeDouble = fc.double({ noNaN: true, noDefaultInfinity: true });

// CORRECT: Bounded doubles
const percentage = fc.double({ min: 0, max: 1, noNaN: true });
```

### Filtering Individual Elements (Not Arrays)

```typescript
// CORRECT: Filter the element arbitrary, then make array
const positiveInts = fc.array(fc.integer().filter(n => n > 0));

// CORRECT: Use fc.nat() instead of filtering
const positiveArray = fc.array(fc.nat().map(n => n + 1));
```

## Anti-Patterns (NEVER DO THESE)

### Math.random Inside Property

```typescript
// ❌ WRONG: Breaks shrinking completely
fc.assert(fc.property(fc.integer(), (n) => {
  const threshold = Math.random() * 100; // BREAKS SHRINKING
  return n < threshold;
}));

// ✅ CORRECT: Use an arbitrary for the threshold
fc.assert(fc.property(fc.integer(), fc.integer(), (n, threshold) => {
  return someProperty(n, threshold);
}));
```

### Filtering Entire Arrays

```typescript
// ❌ WRONG: Filters the whole array, causes "too many skips" errors
const filtered = fc.array(fc.integer()).filter(arr => arr.every(x => x > 0));

// ✅ CORRECT: Filter elements before array construction
const correct = fc.array(fc.integer().filter(x => x > 0));

// ✅ BETTER: Use nat() to avoid filtering entirely
const better = fc.array(fc.nat().map(n => n + 1));
```

### fc.float vs fc.double Confusion

```typescript
// ❌ WRONG: fc.float generates 32-bit floats with different precision rules
const wrong = fc.float({ min: -1e308, max: 1e308 }); // Impossible for 32-bit

// ✅ CORRECT: Use fc.double for full-range floating point
const correct = fc.double({ min: -1e308, max: 1e308, noNaN: true });
```

### Impossible Boundaries After Filtering

```typescript
// ❌ WRONG: min > max after constraints are applied
const wrong = fc.double({ min: 0.5, max: 0.3 }); // min > max!

// ❌ WRONG: Filter makes generation nearly impossible
const wrong2 = fc.integer({ min: 0, max: 10 }).filter(n => n > 1000);

// ✅ CORRECT: Ensure min < max and filters are satisfiable
const correct = fc.double({ min: 0.3, max: 0.5, noNaN: true });
```

## Test Templates

### Behavioral Equivalence Test

Use when testing that a new implementation matches a reference:

```typescript
describe("MyFunction behavioral equivalence", () => {
  it("matches reference implementation for all valid inputs", () => {
    fc.assert(fc.property(
      validInputArb,
      (input) => {
        const actual = myFunction(input);
        const expected = referenceImplementation(input);
        expect(actual).toEqual(expected);
      }
    ));
  });
});
```

### Validator Classification Test

Use when testing that a validator accepts valid inputs and rejects invalid ones:

```typescript
describe("validateConfig", () => {
  it("accepts all valid configurations", () => {
    fc.assert(fc.property(
      validConfigArb,
      (config) => {
        expect(() => validateConfig(config)).not.toThrow();
      }
    ));
  });

  it("rejects configs with missing required fields", () => {
    fc.assert(fc.property(
      configMissingFieldArb,
      (config) => {
        expect(() => validateConfig(config)).toThrow();
      }
    ));
  });

  it("rejects configs with out-of-range values", () => {
    fc.assert(fc.property(
      configOutOfRangeArb,
      (config) => {
        expect(() => validateConfig(config)).toThrow();
      }
    ));
  });
});
```

### Round-Trip / Serialization Test

```typescript
describe("serialize/deserialize round-trip", () => {
  it("deserialize(serialize(x)) === x for all valid inputs", () => {
    fc.assert(fc.property(
      validDataArb,
      (data) => {
        const roundTripped = deserialize(serialize(data));
        expect(roundTripped).toEqual(data);
      }
    ));
  });
});
```

## Arbitrary Composition Rules

1. **Use `.chain()` for dependent values** — when one value constrains another
2. **Use `.map()` for transformations** — when deriving a value from another
3. **Use `fc.record()` for structured data** — cleaner than manual object construction
4. **Prefer `.map()` over `.filter()`** — mapping is always satisfiable, filtering can fail
5. **Use `fc.oneof()` for union types** — not conditional logic inside the property
6. **Cap array sizes** — `fc.array(arb, { maxLength: 20 })` prevents slow tests

## Settings for Reliable Tests

```typescript
// Good defaults for CI
fc.assert(fc.property(arb, prop), {
  numRuns: 100,        // Enough for confidence, fast enough for CI
  seed: undefined,     // Let fast-check pick (reproducible via reported seed)
  endOnFailure: true,  // Stop at first failure for clear diagnostics
});
```
