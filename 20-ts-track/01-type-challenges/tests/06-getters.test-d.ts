import type { Expect, Equal } from "@sandbox19/harness";
import type { Getters } from "../src/06-getters";

interface Person {
  name: string;
  age: number;
}

type _Basic = Expect<
  Equal<Getters<Person>, { getName: () => string; getAge: () => number }>
>;

type _SingleKey = Expect<Equal<Getters<{ id: number }>, { getId: () => number }>>;

type _Empty = Expect<Equal<Getters<{}>, {}>>;

type _NestedValue = Expect<
  Equal<Getters<{ address: { city: string } }>, { getAddress: () => { city: string } }>
>;

declare const getters: Getters<Person>;
// @ts-expect-error — a getter takes no arguments
getters.getName("extra");

// @ts-expect-error — original key must not survive the remap
getters.name;
