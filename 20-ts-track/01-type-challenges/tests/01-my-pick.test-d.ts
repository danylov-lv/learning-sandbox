import type { Expect, Equal } from "@sandbox19/harness";
import type { MyPick } from "../src/01-my-pick";

interface Todo {
  id: number;
  title: string;
  completed: boolean;
  dueDate?: string;
}

type _SingleKey = Expect<Equal<MyPick<Todo, "title">, { title: string }>>;

type _MultiKey = Expect<
  Equal<MyPick<Todo, "id" | "completed">, { id: number; completed: boolean }>
>;

type _AllKeys = Expect<Equal<MyPick<Todo, keyof Todo>, Todo>>;

type _OptionalKeyPreserved = Expect<
  Equal<MyPick<Todo, "dueDate">, { dueDate?: string }>
>;

// @ts-expect-error — "nope" is not a key of Todo, so it must not be a valid K
type _InvalidKey = MyPick<Todo, "nope">;

// @ts-expect-error — picked shape must not carry "title" alongside "id"
const _wrongShape: MyPick<Todo, "id"> = { id: 1, title: "x" };
