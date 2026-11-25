import type { Expect, Equal } from "@sandbox19/harness";
import type { TupleToUnion } from "../src/03-tuple-to-union";

type _Numbers = Expect<Equal<TupleToUnion<[1, 2, 3]>, 1 | 2 | 3>>;

type _Mixed = Expect<Equal<TupleToUnion<[string, number, boolean]>, string | number | boolean>>;

type _Single = Expect<Equal<TupleToUnion<["only"]>, "only">>;

type _Empty = Expect<Equal<TupleToUnion<[]>, never>>;

type _Readonly = Expect<Equal<TupleToUnion<readonly ["a", "b"]>, "a" | "b">>;

// @ts-expect-error — a plain object is not a tuple and must not satisfy the constraint
type _NotATuple = TupleToUnion<{ length: 2 }>;
