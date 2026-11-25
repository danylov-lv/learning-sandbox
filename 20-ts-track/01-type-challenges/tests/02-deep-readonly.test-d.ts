import type { Expect, Equal } from "@sandbox19/harness";
import type { DeepReadonly } from "../src/02-deep-readonly";

interface Nested {
  name: string;
  address: { city: string; zip: string };
  tags: string[];
  greet: (name: string) => string;
}

type _FlatPrimitive = Expect<Equal<DeepReadonly<{ a: number }>, { readonly a: number }>>;

type _Nested = Expect<
  Equal<
    DeepReadonly<Nested>,
    {
      readonly name: string;
      readonly address: { readonly city: string; readonly zip: string };
      readonly tags: readonly string[];
      readonly greet: (name: string) => string;
    }
  >
>;

type _EmptyObject = Expect<Equal<DeepReadonly<Record<string, never>>, Readonly<Record<string, never>>>>;

type _DoublyNested = Expect<
  Equal<
    DeepReadonly<{ a: { b: { c: number } } }>,
    { readonly a: { readonly b: { readonly c: number } } }
  >
>;

const locked: DeepReadonly<{ a: { b: number } }> = { a: { b: 1 } };
// @ts-expect-error — a deeply readonly property must reject reassignment
locked.a.b = 2;
