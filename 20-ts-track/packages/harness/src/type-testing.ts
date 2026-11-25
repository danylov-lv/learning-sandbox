// Type-level test utilities in the standard type-challenges style.
// Pure type-only module: every export is a type, so under verbatimModuleSyntax
// consumers must `import type` from it.

export type Expect<T extends true> = T;
export type ExpectTrue<T extends true> = T;
export type ExpectFalse<T extends false> = T;

// The HKT trick: two generic functions are assignable to each other only when
// their conditional bodies behave identically for every T. This distinguishes
// `any` from concrete types, unlike a plain bidirectional `extends` check.
export type Equal<X, Y> =
  (<T>() => T extends X ? 1 : 2) extends (<T>() => T extends Y ? 1 : 2)
    ? true
    : false;

export type NotEqual<X, Y> = true extends Equal<X, Y> ? false : true;

export type IsAny<T> = 0 extends 1 & T ? true : false;

export type IsNever<T> = [T] extends [never] ? true : false;

export type IsUnknown<T> =
  IsAny<T> extends true
    ? false
    : unknown extends T
      ? true
      : false;

// Structural "close enough" comparison: equal, or mutually assignable once
// `readonly`/optionality differences are ignored via the Equal fallback.
export type Alike<X, Y> =
  Equal<X, Y> extends true
    ? true
    : [X] extends [Y]
      ? [Y] extends [X]
        ? true
        : false
      : false;
