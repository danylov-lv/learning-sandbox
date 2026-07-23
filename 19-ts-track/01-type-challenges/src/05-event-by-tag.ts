// Challenge 05 — EventByTag and assertNever
//
// `EventByTag<Events, Tag>` extracts the member of the discriminated union
// `Events` whose `tag` property equals `Tag`.
//
// `assertNever` is the exhaustiveness helper: type it so that, in the
// `default` branch of a fully-handled `switch`, the value is `never` and the
// call compiles — but if any variant is left unhandled, passing the still
// non-`never` value becomes a compile error.

export type EventByTag<
  Events extends { tag: PropertyKey },
  Tag extends Events["tag"],
> = unknown; // TODO: implement

export function assertNever(value: unknown): never {
  throw new Error("not implemented");
}
