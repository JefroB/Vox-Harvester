---
name: TypeScript
tags: [lang-typescript]
description: TypeScript-specific idioms, type system patterns, and common pitfalls.
---

# TypeScript Language Skill

## Type System

- Prefer `unknown` over `any`. Use type guards to narrow.
- Use discriminated unions for state modeling (tagged unions with a literal `type` field).
- Prefer `interface` for public API shapes; use `type` for unions, intersections, and computed types.
- Use `readonly` on properties and arrays that should not be mutated.
- Prefer `Record<K, V>` over index signatures where key set is known.
- Use `satisfies` for validation without widening.
- Avoid `as` casts — use type guards or assertion functions instead.

## Patterns

- Use `Result<T, E>` or discriminated union return types instead of throwing for expected failures.
- Prefer `Map`/`Set` over plain objects for dynamic key collections.
- Use `const` assertions (`as const`) for literal tuples and enums.
- Prefer named exports over default exports for better refactoring support.
- Use barrel files (`index.ts`) sparingly — they break tree-shaking.

## Async

- Always handle promise rejections. Prefer `try/catch` in async functions over `.catch()` chains.
- Use `Promise.allSettled` when partial failure is acceptable.
- Avoid mixing callbacks and promises in the same API surface.
- Type async function returns explicitly: `async function foo(): Promise<Result>`.

## Error Handling

- Define typed error classes or discriminated error unions.
- Include context in errors (what operation failed, with what inputs).
- Use `cause` in Error constructor for error chaining: `new Error("msg", { cause: originalError })`.

## Project Structure

- Use `strict: true` in tsconfig (including `noUncheckedIndexedAccess`).
- Keep `compilerOptions.paths` minimal — prefer explicit relative imports for clarity.
- Separate types into `*.types.ts` files only when they're shared across multiple modules.

## Common Pitfalls

- `Array.includes()` doesn't narrow types — use a type guard wrapper.
- Optional chaining (`?.`) returns `undefined`, not `null`. Be explicit about which you expect.
- `Object.keys()` returns `string[]`, not `(keyof T)[]`. Use a typed helper if needed.
- `JSON.parse()` returns `any` — always validate with zod/valibot or a type guard.
- Avoid enums in libraries (they emit runtime code). Use `as const` objects instead.
