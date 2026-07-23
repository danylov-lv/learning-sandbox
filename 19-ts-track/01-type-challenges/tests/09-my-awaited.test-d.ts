import type { Expect, Equal } from "@sandbox19/harness";
import type { MyAwaited } from "../src/09-my-awaited";

type _SingleLevel = Expect<Equal<MyAwaited<Promise<string>>, string>>;

type _DoubleNested = Expect<Equal<MyAwaited<Promise<Promise<number>>>, number>>;

type _TripleNested = Expect<Equal<MyAwaited<Promise<Promise<Promise<boolean>>>>, boolean>>;

type _NonPromisePassthrough = Expect<Equal<MyAwaited<string>, string>>;

type _NonPromiseObject = Expect<Equal<MyAwaited<{ id: number }>, { id: number }>>;

declare const _unwrapped: MyAwaited<Promise<string>>;
// @ts-expect-error — unwrapping a Promise<string> must not leave a Promise behind
const _stillWrapped: Promise<string> = _unwrapped;
