import type { Expect, Equal } from "@sandbox19/harness";
import type { EventByTag } from "../src/05-event-by-tag";
import { assertNever } from "../src/05-event-by-tag";

type AppEvent =
  | { tag: "click"; x: number; y: number }
  | { tag: "keypress"; key: string }
  | { tag: "scroll"; delta: number };

type _Click = Expect<Equal<EventByTag<AppEvent, "click">, { tag: "click"; x: number; y: number }>>;

type _Keypress = Expect<Equal<EventByTag<AppEvent, "keypress">, { tag: "keypress"; key: string }>>;

type _Scroll = Expect<Equal<EventByTag<AppEvent, "scroll">, { tag: "scroll"; delta: number }>>;

// @ts-expect-error — "hover" is not a member of AppEvent["tag"]
type _UnknownTag = EventByTag<AppEvent, "hover">;

function describe(event: AppEvent): string {
  switch (event.tag) {
    case "click":
      return `click at ${event.x},${event.y}`;
    case "keypress":
      return `key ${event.key}`;
    case "scroll":
      return `scroll ${event.delta}`;
    default:
      // Compiles only because assertNever demands `never`, and the switch
      // above is exhaustive so `event` has already narrowed to `never` here.
      return assertNever(event);
  }
}

// A switch that leaves a variant unhandled must fail to compile at the
// assertNever call, because the unhandled member survives into `default`.
type PartialEvent = { tag: "a" } | { tag: "b" } | { tag: "c" };
function partialDescribe(event: PartialEvent): string {
  switch (event.tag) {
    case "a":
      return "a";
    case "b":
      return "b";
    default:
      // @ts-expect-error — "c" was never handled, so `event` is not `never` here
      return assertNever(event);
  }
}
