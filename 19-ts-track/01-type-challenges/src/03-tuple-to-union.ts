// Challenge 03 — TupleToUnion
//
// Given a tuple type `T`, produce the union of its element types. An empty
// tuple yields `never`.

export type TupleToUnion<T extends readonly unknown[]> = unknown; // TODO: implement
