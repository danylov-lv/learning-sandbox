A concrete shape for the test file. Still pseudocode -- fill in every real
line yourself, including the exact `jsonschema` and `httpx`/`TestClient`
calls, which this deliberately leaves out.

```
load CONTRACT dict once at module level from src/contract.json

fixture client():
    build the app via make_app(), wrap it in a TestClient / ASGITransport
    client, yield it

test_products_page_matches_schema(client):
    response = client.get("/products")
    assert response.status_code == 200
    jsonschema.validate(response.json(), CONTRACT["product_list"])

test_single_product_matches_schema(client):
    fetch page one, take any real id from it
    response = client.get(f"/products/{that_id}")
    assert response.status_code == 200
    jsonschema.validate(response.json(), CONTRACT["product"])

test_missing_product_returns_404_with_error_envelope(client):
    pick an id outside the real range (e.g. one bigger than any id you've
    seen, or negative)
    response = client.get(f"/products/{missing_id}")
    assert response.status_code == 404
    jsonschema.validate(response.json(), CONTRACT["error"])
    assert response.json()["error"]["code"] == "not_found"

test_pagination_walks_every_item_exactly_once(client):
    seen_ids = []
    cursor = None
    loop (with a hard iteration cap so a bug can't hang the suite):
        response = client.get("/products", params={"cursor": cursor} if cursor else {})
        body = response.json()
        seen_ids += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None: break
    assert len(seen_ids) == len(set(seen_ids))   # no duplicates
    assert seen_ids == sorted(seen_ids)          # id order preserved
    # compare len(seen_ids) against an independently-obtained total count

test_last_page_next_cursor_is_null(client):
    walk to the actual last page (reuse the loop above, or request with a
    limit large enough to get everything in one page) and assert
    next_cursor is exactly None there

test_mid_stream_next_cursor_is_a_nonnull_string(client):
    request page one with a limit smaller than the full catalog size and
    assert next_cursor is a non-null str

test_collection_endpoint_sets_cache_control_header(client):
    response = client.get("/products")
    assert "cache-control" in response.headers  # header names are
                                                  # case-insensitive on
                                                  # both dict-like objects

test_id_is_int_price_is_str(client):
    for each item in a /products page:
        assert isinstance(item["id"], int) and not isinstance(item["id"], bool)
        assert isinstance(item["price"], str)
```

That's roughly nine tests -- comfortably over `min_tests`. Every mutant in
the bank breaks exactly one of these; if you find one you can't map to any
test above, that's a sign you're missing an invariant, not that the mutant
bank is unfair. A test that never calls `jsonschema.validate` and never
inspects a specific key by name will not catch a renamed field, a status
code swap, or a truncated pagination walk -- the point of this task is
that "it returned 200" is the least interesting thing you can assert about
an API response.
