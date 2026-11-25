# Hint 3

Concrete approach, close to pseudocode. You still have to turn every line
below into real TypeScript syntax yourself — nothing here is
copy-pasteable.

## 06 Getters

```text
for each key K in keyof T:
  new key = "get" + Capitalize(K as a string)
  new value = a zero-arg function returning T[K]
result = the object type built from those remapped pairs
```

## 07 PartialBy

```text
result =
  ( the properties of T whose key is NOT in K, unchanged )
  intersected with
  ( the properties of T whose key IS in K, each wrapped optional )
```

Both halves can be written as mapped types over a filtered key set, or by
reaching for the two-argument forms of `Omit`/`Pick` you already know from
challenge 01.

## 08 ReplaceReturnType

```text
if F matches "a function taking some parameter list P and returning anything":
  result = a function type taking that same P, returning R
else:
  (unreachable given the constraint on F)
```

The parameter list `P` is not something you write out by hand — it's
whatever the compiler infers when you match `F` against a function-type
pattern with `infer` in the parameter position, and you splice it back in
with a rest element (`...P`) when building the result.

## 09 MyAwaited

```text
if T matches "Promise of some payload U":
  result = MyAwaited<U>          // keep peeling
else:
  result = T                     // base case: not a promise, stop
```

## 10 ExtractParams

```text
if Path matches ".../:Param/Rest..."   (there's more path after this param):
  result = { Param: string } merged with ExtractParams<"/Rest...">
else if Path matches "...:Param"        (this is the last segment):
  result = { Param: string }
else:
  result = {}                          // no param in this path at all
```

Watch the second recursive call: you need to feed the *remaining* path back
in with a leading `/` restored (or structure the pattern so `Rest` already
includes it), otherwise the recursion won't find a `:` that's actually
there.

## 11 Flatten

```text
if T is the empty tuple:
  result = []
else:
  Head = first element of T, Tail = rest of T
  if Head is itself a tuple:
    result = [...Flatten<Head>, ...Flatten<Tail>]
  else:
    result = [Head, ...Flatten<Tail>]
```

## 12 Brand

```text
Brand<T, B> = T intersected with { readonly __brand: B }   // property name is arbitrary,
                                                              // as long as nothing else uses it

UserId = Brand<number, "UserId">
ProductId = Brand<number, "ProductId">

toUserId(id) = id, forced to type UserId via a type assertion
  (there is no runtime transformation — the number is unchanged)
```

The `__brand` field must never appear as a real, populated field on any
object you construct normally — it only exists so the type checker sees
`UserId` and `ProductId` as structurally different, even though both erase
to `number` at runtime.
