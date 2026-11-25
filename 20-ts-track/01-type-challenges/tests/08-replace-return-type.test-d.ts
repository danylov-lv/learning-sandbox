import type { Expect, Equal } from "@sandbox19/harness";
import type { ReplaceReturnType } from "../src/08-replace-return-type";

type _TwoArgs = Expect<
  Equal<ReplaceReturnType<(a: string, b: number) => boolean, string>, (a: string, b: number) => string>
>;

type _NoArgs = Expect<Equal<ReplaceReturnType<() => void, number>, () => number>>;

type _RestArgs = Expect<
  Equal<ReplaceReturnType<(...items: number[]) => number, string[]>, (...items: number[]) => string[]>
>;

type _ReturnPromise = Expect<
  Equal<ReplaceReturnType<(id: number) => boolean, Promise<boolean>>, (id: number) => Promise<boolean>>
>;

declare const replaced: ReplaceReturnType<(a: string, b: number) => boolean, string>;
// @ts-expect-error — parameter list must be preserved exactly, wrong arg type rejected
replaced(1, 2);

// @ts-expect-error — the replaced return type is `string`, not the original `boolean`
const _wrongReturn: boolean = replaced("a", 1);
