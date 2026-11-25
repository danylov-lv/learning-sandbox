import type { Expect, Equal } from "@sandbox19/harness";
import type { First, Last } from "../src/04-first-last";

type _FirstOfThree = Expect<Equal<First<[1, 2, 3]>, 1>>;
type _LastOfThree = Expect<Equal<Last<[1, 2, 3]>, 3>>;

type _FirstOfOne = Expect<Equal<First<["only"]>, "only">>;
type _LastOfOne = Expect<Equal<Last<["only"]>, "only">>;

type _FirstEmpty = Expect<Equal<First<[]>, never>>;
type _LastEmpty = Expect<Equal<Last<[]>, never>>;

type _FirstMixed = Expect<Equal<First<[string, number, boolean]>, string>>;
type _LastMixed = Expect<Equal<Last<[string, number, boolean]>, boolean>>;

// @ts-expect-error — a non-tuple array-like object must not satisfy the constraint
type _FirstNotATuple = First<{ 0: "a"; length: 1 }>;
