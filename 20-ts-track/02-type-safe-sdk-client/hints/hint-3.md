# Hint 3

Concrete approach, close to pseudocode. You still have to turn every step
below into working TypeScript yourself -- none of this is copy-pasteable.

## `src/schemas.ts`

```text
ProductSchema = object with:
  id: number, sku: string, name: string, categoryId: number,
  sellerId: number, price: number, inStock: boolean, scrapedAt: string

UserSchema = object with:
  id: number, email: string, displayName: string,
  role: literal "user" OR literal "admin"

ApiErrorSchema = object with:
  error: object with { code: string, message: string }

ProductsPageSchema = object with:
  items: array of ProductSchema
  nextCursor: string, nullable

CategorySummarySchema = object with:
  categoryId, productCount, avgPrice, inStockCount -- all number

SearchResultSchema = object with:
  items: array of ProductSchema

AuthTokensSchema = object with:
  accessToken: string, refreshToken: string
```

Every `export type X = z.infer<typeof XSchema>` line underneath each schema
stays exactly as it already is in the stub -- you're only replacing the
`z.custom(...)` right-hand side, not the type alias below it.

## `MarketplaceClient` internal state

```text
class holds:
  baseUrl: string
  tokens: AuthTokens | undefined

constructor(options): store options.baseUrl and options.tokens
getTokens(): return the stored tokens
setTokens(t): store t (overwrite, including with undefined)
```

## `request(path, schema, init?)`

```text
res = await fetch(baseUrl + path, init)
json = await res.json()   // read the body exactly once, before branching

if not res.ok:
  if res.status == 404: throw ApiNotFoundError(path)
  if res.status == 401: throw ApiAuthError(path)
  parsedError = ApiErrorSchema.safeParse(json)
  body = parsedError.success ? parsedError.data : <a fallback ApiErrorBody>
  throw ApiRequestError(res.status, path, body)

parsed = schema.safeParse(json)
if not parsed.success:
  throw SdkValidationError(path, parsed.error)
return parsed.data
```

## The straightforward wrappers

```text
getProduct(id) = request(`/products/${id}`, ProductSchema)

getCategorySummary(id) = request(`/categories/${id}/summary`, CategorySummarySchema)

search(q) =
  result = request(`/search?q=${encodeURIComponent(q)}`, SearchResultSchema)
  return result.items

listProducts(opts) =
  build a URLSearchParams from opts.limit (if present) and opts.cursor
  (if present and not null)
  request(`/products` + (params non-empty ? `?${params}` : ``), ProductsPageSchema)
```

## `iterateProducts(opts)`

```text
async generator:
  cursor = null
  loop forever:
    page = await listProducts({ limit: opts?.limit, cursor })
      -- careful here: under exactOptionalPropertyTypes you cannot pass
      -- `limit: possiblyUndefined` into a `{ limit?: number }` parameter;
      -- build the options object by conditionally SETTING the key, not by
      -- assigning it the value `undefined`
    yield each item in page.items, one at a time
    if page.nextCursor is null: return (stop iterating)
    cursor = page.nextCursor
```

## `login` / `refresh`

```text
login(email, password):
  tokens = request("/auth/login", AuthTokensSchema, {
    method: POST, headers: content-type json,
    body: JSON.stringify({ email, password }),
  })
  this.tokens = tokens
  return tokens

refresh():
  if this.tokens is undefined: throw ApiAuthError("/auth/refresh")
  tokens = request("/auth/refresh", AuthTokensSchema, {
    method: POST, headers: content-type json,
    body: JSON.stringify({ refreshToken: this.tokens.refreshToken }),
  })
  this.tokens = tokens
  return tokens
```

## `me()`

```text
attempt = async () =>
  accessToken = this.tokens?.accessToken
  request("/me", UserSchema, {
    headers: accessToken !== undefined ? { authorization: `Bearer ${accessToken}` } : {}
  })

me():
  try:
    return await attempt()
  catch err:
    if err is ApiAuthError AND this.tokens is defined:
      await this.refresh()
      return await attempt()   // exactly one retry, no loop
    else:
      rethrow err
```

Every method above returns exactly what `request`/`listProducts` gives it
-- none of them need their own try/catch beyond what `me()` does, because
`request` already turns every failure mode into the right typed error
before it gets anywhere near a caller.
