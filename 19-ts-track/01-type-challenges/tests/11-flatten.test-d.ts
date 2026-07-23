import type { Expect, Equal } from "@sandbox19/harness";
import type { Flatten } from "../src/11-flatten";

type _Empty = Expect<Equal<Flatten<[]>, []>>;

type _AlreadyFlat = Expect<Equal<Flatten<[1, 2, 3]>, [1, 2, 3]>>;

type _OneLevel = Expect<Equal<Flatten<[1, [2, 3], 4]>, [1, 2, 3, 4]>>;

type _DeeplyNested = Expect<
  Equal<Flatten<[1, [2, [3, [4, [5]]]]]>, [1, 2, 3, 4, 5]>
>;

type _MultipleNestedSiblings = Expect<
  Equal<Flatten<[[1, 2], [3, 4], [5, 6]]>, [1, 2, 3, 4, 5, 6]>
>;

// @ts-expect-error — flattening must not preserve the original nested shape
const _stillNested: [number, [number, number]] = [] as unknown as Flatten<[1, [2, 3]]>;
