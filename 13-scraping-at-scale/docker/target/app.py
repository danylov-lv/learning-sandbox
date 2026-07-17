"""The hostile target site for module 13. Plain HTTP, fully deterministic,
no real browser/TLS involved anywhere -- see .authoring/design.md for the
emulation decisions this implements exactly (header/behavioral client
fingerprint gate, honeypots, token-bucket rate limiting with bans, K markup
versions, day-over-day price/stock changes with a volatile nonce, malformed
"bad records", and a documented XHR-style /api/product/{id} standing in for
headless rendering).

Reads data/catalog.json + data/target-spec.json (mounted read-only into the
container) at import time. Per-client state is a plain in-memory dict --
correct for a single uvicorn worker (see Dockerfile: --workers 1), never
meant to survive a restart.
"""

import json
import os
import re
import time
import uuid
from html import escape
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "/data/catalog.json"))
TARGET_SPEC_PATH = Path(os.environ.get("TARGET_SPEC_PATH", "/data/target-spec.json"))

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
SPEC = json.loads(TARGET_SPEC_PATH.read_text(encoding="utf-8"))

PRODUCTS_BY_ID = {p["id"]: p for p in CATALOG["products"]}
PRODUCT_IDS_SORTED = sorted(PRODUCTS_BY_ID.keys())

HONEYPOT_IDS = set(SPEC["honeypots"]["product_ids"])
HONEYPOT_IDS_SORTED = sorted(HONEYPOT_IDS)
TRAP_TOKENS = SPEC["honeypots"]["trap_tokens"]

BAD_MAP = {int(k): v for k, v in SPEC["bad_records"]["by_id"].items()}

N_DAYS = SPEC["change_days"]["n_days"]
CHANGE_DAYS_RAW = {
    int(d): {int(pid): delta for pid, delta in changes.items()}
    for d, changes in SPEC["change_days"]["days"].items()
}

RATE_CAPACITY = float(SPEC["rate_limit"]["capacity"])
RATE_REFILL_PER_SEC = float(SPEC["rate_limit"]["refill_per_sec"])
BAN_AFTER_VIOLATIONS = int(SPEC["rate_limit"]["ban_after_violations"])

UA_SUBSTRING = SPEC["required_headers"]["user_agent_substring"]
ACCEPT_LANGUAGE_REQUIRED = SPEC["required_headers"]["accept_language_required"]

MARKUP_VERSION_COUNT = SPEC["markup_versions"]["count"]
CHAOS_PERIOD_SEC = SPEC["chaos"]["period_sec"]
TARGET_CHAOS_ENV = os.environ.get("TARGET_CHAOS", "0") not in ("", "0", "false")

PAGE_SIZE = 50
HONEYPOTS_PER_PAGE = 2

# --------------------------------------------------------------------------
# Cumulative per-day price/stock overlay -- change_days.json records each
# day's DELTA relative to the previous day; fold once at startup so a
# request for day D only needs one dict lookup per product.
# --------------------------------------------------------------------------

_CUMULATIVE_OVERLAY = {0: {}}
_running = {}
for _d in range(1, N_DAYS):
    _running = {**_running, **CHANGE_DAYS_RAW.get(_d, {})}
    _CUMULATIVE_OVERLAY[_d] = dict(_running)


def _clamp_day(day):
    return max(0, min(int(day), N_DAYS - 1))


def _effective_product(pid, day):
    p = dict(PRODUCTS_BY_ID[pid])
    overlay = _CUMULATIVE_OVERLAY.get(_clamp_day(day), {}).get(pid)
    if overlay:
        p.update(overlay)
    return p


def _apply_defect(p, pid):
    defect = BAD_MAP.get(pid)
    if not defect:
        return p
    p = dict(p)
    if defect == "missing_price":
        p.pop("price", None)
    elif defect == "price_na":
        p["price"] = "N/A"
    elif defect == "empty_title":
        p["title"] = ""
    elif defect == "negative_price":
        p["price"] = -abs(float(p.get("price") or 1.0))
    elif defect == "bad_currency":
        p["currency"] = "XYZ"
    elif defect == "truncated":
        desc = p.get("description", "")
        cut = desc[: max(5, len(desc) // 3)]
        p["description"] = cut + "...[TRNC]��"
    return p


def _resolved_record(pid, day):
    return _apply_defect(_effective_product(pid, day), pid)


def _resolve_version(pid, v_param, chaos_param):
    if v_param is not None:
        v = int(v_param)
        if 1 <= v <= MARKUP_VERSION_COUNT:
            return v
    if TARGET_CHAOS_ENV or bool(chaos_param):
        period_idx = int(time.time() // CHAOS_PERIOD_SEC)
        return 1 + (period_idx % MARKUP_VERSION_COUNT)
    return 1 + (pid % MARKUP_VERSION_COUNT)


# --------------------------------------------------------------------------
# Per-client state (in-memory, single worker)
# --------------------------------------------------------------------------

CLIENTS = {}


def _new_client_state():
    return {
        "tokens": RATE_CAPACITY, "last_refill": time.monotonic(),
        "requests": 0, "honeypot_hits": 0,
        "rate_limit_violations": 0, "header_rejections": 0, "banned": False,
    }


def _client_key(request: Request):
    cid = request.headers.get("x-client-id")
    if cid:
        return cid
    conn = request.client
    if conn:
        return f"anon-{conn.host}:{conn.port}"
    return "anon-unknown"


def _get_client(cid):
    return CLIENTS.setdefault(cid, _new_client_state())


def _decoy_response(as_json=False):
    nonce = str(uuid.uuid4())
    if as_json:
        return JSONResponse(
            {"id": None, "title": "Item Unavailable", "price": None, "_nonce": nonce},
            status_code=200,
        )
    html = (
        "<html><body><h1>Item Unavailable</h1>"
        "<p>This listing is no longer available.</p>"
        f'<meta name="x-nonce" content="{nonce}"></body></html>'
    )
    return HTMLResponse(html, status_code=200)


app = FastAPI(title="Kupitron Bazaar (hostile target)")


@app.middleware("http")
async def defense_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/__debug/"):
        return await call_next(request)

    cid = _client_key(request)
    client = _get_client(cid)

    if client["banned"]:
        client["requests"] += 1
        return JSONResponse({"error": "forbidden", "reason": "banned"}, status_code=403)

    ua = request.headers.get("user-agent", "")
    accept_language = request.headers.get("accept-language", "")
    headers_ok = (UA_SUBSTRING in ua) and (not ACCEPT_LANGUAGE_REQUIRED or bool(accept_language.strip()))
    if not headers_ok:
        client["header_rejections"] += 1
        client["requests"] += 1
        return JSONResponse({"error": "forbidden", "reason": "missing_or_invalid_headers"}, status_code=403)

    if path.startswith("/trap/"):
        client["honeypot_hits"] += 1
        client["banned"] = True
        client["requests"] += 1
        return _decoy_response()

    m = re.match(r"^/(?:api/)?product/(\d+)$", path)
    if m and int(m.group(1)) in HONEYPOT_IDS:
        client["honeypot_hits"] += 1
        client["banned"] = True
        client["requests"] += 1
        return _decoy_response(as_json=path.startswith("/api/"))

    now = time.monotonic()
    elapsed = now - client["last_refill"]
    client["tokens"] = min(RATE_CAPACITY, client["tokens"] + elapsed * RATE_REFILL_PER_SEC)
    client["last_refill"] = now
    if client["tokens"] < 1.0:
        client["rate_limit_violations"] += 1
        if client["rate_limit_violations"] >= BAN_AFTER_VIOLATIONS:
            client["banned"] = True
        client["requests"] += 1
        return JSONResponse({"error": "too_many_requests"}, status_code=429, headers={"Retry-After": "1"})
    client["tokens"] -= 1.0
    client["requests"] += 1

    return await call_next(request)


# --------------------------------------------------------------------------
# Public routes
# --------------------------------------------------------------------------

@app.get("/")
def landing():
    return HTMLResponse(
        "<html><body><h1>Kupitron Bazaar</h1>"
        f"<p>{len(PRODUCT_IDS_SORTED)} products. <a href=\"/catalog\">Browse the catalog</a>.</p>"
        "</body></html>"
    )


@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /trap/\nDisallow: /__debug/\n")


def _honeypots_for_page(page):
    if not HONEYPOT_IDS_SORTED:
        return []
    n = len(HONEYPOT_IDS_SORTED)
    start = ((page - 1) * HONEYPOTS_PER_PAGE) % n
    return [HONEYPOT_IDS_SORTED[(start + i) % n] for i in range(min(HONEYPOTS_PER_PAGE, n))]


@app.get("/catalog")
def catalog(page: int = Query(1, ge=1), day: int = Query(0, ge=0), v: int | None = Query(None), chaos: int = Query(0)):
    day = _clamp_day(day)
    total = len(PRODUCT_IDS_SORTED)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_ids = PRODUCT_IDS_SORTED[start:start + PAGE_SIZE]

    items = []
    for pid in page_ids:
        p = _resolved_record(pid, day)
        title = escape(str(p.get("title", "")))
        qs = f"?day={day}" + (f"&v={v}" if v is not None else "")
        items.append(f'<li><a href="/product/{pid}{qs}">{title}</a></li>')

    hidden_links = "".join(
        f'<a href="/product/{hid}" style="display:none" rel="nofollow" class="hp">item {hid}</a>'
        for hid in _honeypots_for_page(page)
    )
    trap_block = ""
    if page == 1 and TRAP_TOKENS:
        trap_block = (
            f'<div class="hp" style="display:none">'
            f'<a href="/trap/{TRAP_TOKENS[0]}" rel="nofollow">clearance items</a></div>'
        )
    next_link = f'<a rel="next" href="/catalog?page={page + 1}&day={day}">next</a>' if page < total_pages else ""
    nonce = str(uuid.uuid4())

    html = (
        f"<html><body><h1>Catalog page {page}/{total_pages}</h1>"
        f"<ul>{''.join(items)}</ul>{hidden_links}{trap_block}<p>{next_link}</p>"
        f'<meta name="x-nonce" content="{nonce}"></body></html>'
    )
    return HTMLResponse(html)


def _price_text(p):
    if "price" not in p:
        return ""
    val = p["price"]
    if val == "N/A":
        return "N/A"
    return f"{p.get('currency', '')} {val}"


def _availability(p):
    return "In Stock" if p.get("in_stock") else "Out of Stock"


def _render_v1(p, nonce):
    return (
        "<html><body>"
        f'<div class="product" id="product-{p["id"]}">'
        f'<h1 class="product-title">{escape(str(p.get("title", "")))}</h1>'
        f'<div class="product-meta"><span class="category">{escape(p.get("category", ""))}</span>'
        f'<span class="brand">{escape(p.get("brand", ""))}</span>'
        f'<span class="seller">{escape(p.get("seller_name", ""))}</span></div>'
        f'<div class="price-block"><span class="price">{escape(_price_text(p))}</span></div>'
        f'<div class="stock">{_availability(p)}</div>'
        f'<div class="reviews">{p.get("review_count", 0)} reviews</div>'
        f'<p class="description">{escape(p.get("description", ""))}</p>'
        "</div>"
        f'<meta name="x-nonce" content="{nonce}">'
        "</body></html>"
    )


def _render_v2(p, nonce):
    availability_token = "InStock" if p.get("in_stock") else "OutOfStock"
    price_val = p.get("price", "")
    display_price = f"{price_val} {p.get('currency', '')}" if "price" in p else ""
    return (
        "<html><body>"
        f'<article itemscope itemtype="https://schema.org/Product" data-pid="{p["id"]}">'
        f'<h1 itemprop="name">{escape(str(p.get("title", "")))}</h1>'
        f'<p><span itemprop="brand">{escape(p.get("brand", ""))}</span> &middot; '
        f'<span class="sold-by">Sold by {escape(p.get("seller_name", ""))}</span></p>'
        f'<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        f'<meta itemprop="priceCurrency" content="{escape(str(p.get("currency", "")))}">'
        f'<meta itemprop="price" content="{escape(str(price_val))}">'
        f'<span class="display-price">{escape(display_price)}</span>'
        f'<link itemprop="availability" href="https://schema.org/{availability_token}"></div>'
        f'<span class="cat-tag">{escape(p.get("category", ""))}</span>'
        f'<span class="rc">({p.get("review_count", 0)})</span>'
        f'<div class="desc">{escape(p.get("description", ""))}</div>'
        f'<!-- nonce:{nonce} -->'
        "</article></body></html>"
    )


def _render_v3(p, nonce):
    ld = {
        "@context": "https://schema.org", "@type": "Product",
        "name": p.get("title", ""), "sku": p["id"], "brand": p.get("brand", ""),
        "offers": {
            "@type": "Offer",
            "price": p.get("price"), "priceCurrency": p.get("currency"),
            "availability": "https://schema.org/InStock" if p.get("in_stock") else "https://schema.org/OutOfStock",
        },
    }
    return (
        "<html><body>"
        '<div class="pdp">'
        f'<h2>{escape(str(p.get("title", "")))}</h2>'
        f'<div class="tags"><span>{escape(p.get("category", ""))}</span>'
        f'<span>{escape(p.get("brand", ""))}</span></div>'
        f'<div class="by">{escape(p.get("seller_name", ""))}</div>'
        f'<div class="avail">{"available" if p.get("in_stock") else "unavailable"}</div>'
        f'<div class="rv">{p.get("review_count", 0)}</div>'
        f'<div class="body">{escape(p.get("description", ""))}</div>'
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        f'<span class="hidden-nonce" style="display:none">{nonce}</span>'
        "</div></body></html>"
    )


def _render_v4(p, nonce):
    data = {
        "id": p["id"], "price": p.get("price"), "currency": p.get("currency"),
        "in_stock": p.get("in_stock"), "seller": p.get("seller_name"), "nonce": nonce,
    }
    return (
        "<html><body>"
        '<div id="app-root">'
        f'<h1>{escape(str(p.get("title", "")))}</h1>'
        f'<p class="subtitle">{escape(p.get("brand", ""))} &mdash; {escape(p.get("category", ""))}</p>'
        f'<p class="rv">{p.get("review_count", 0)} reviews</p>'
        f'<p class="body">{escape(p.get("description", ""))}</p>'
        "</div>"
        f'<script id="__DATA__" type="application/json">{json.dumps(data)}</script>'
        "</body></html>"
    )


_RENDERERS = {1: _render_v1, 2: _render_v2, 3: _render_v3, 4: _render_v4}


@app.get("/product/{product_id}")
def product_detail(product_id: int, day: int = Query(0, ge=0), v: int | None = Query(None), chaos: int = Query(0)):
    if product_id not in PRODUCTS_BY_ID:
        raise HTTPException(status_code=404, detail="not found")
    p = _resolved_record(product_id, day)
    version = _resolve_version(product_id, v, chaos)
    nonce = str(uuid.uuid4())
    html = _RENDERERS[version](p, nonce)
    return HTMLResponse(html)


@app.get("/api/product/{product_id}")
def product_api(product_id: int, day: int = Query(0, ge=0)):
    if product_id not in PRODUCTS_BY_ID:
        raise HTTPException(status_code=404, detail="not found")
    p = _resolved_record(product_id, day)
    out = {k: v for k, v in p.items() if k not in ("shipping_free", "shipping_eta_days", "shipping_carrier")}
    out["shipping_info"] = {
        "free": p.get("shipping_free"),
        "eta_days": p.get("shipping_eta_days"),
        "carrier": p.get("shipping_carrier"),
    }
    out["_nonce"] = str(uuid.uuid4())
    return JSONResponse(out)


# --------------------------------------------------------------------------
# Debug endpoints -- bypass the header gate and rate limiter entirely (see
# defense_middleware's early return), so validators can always read/reset
# client state regardless of what defenses that client has tripped.
# --------------------------------------------------------------------------

@app.get("/__debug/client")
def debug_client(x_client_id: str | None = Header(None, alias="X-Client-Id")):
    if not x_client_id:
        raise HTTPException(status_code=400, detail="X-Client-Id header required")
    c = CLIENTS.get(x_client_id, _new_client_state())
    return {
        "client_id": x_client_id, "requests": c["requests"],
        "honeypot_hits": c["honeypot_hits"], "rate_limit_violations": c["rate_limit_violations"],
        "header_rejections": c["header_rejections"], "banned": c["banned"],
    }


@app.post("/__debug/reset")
def debug_reset(x_client_id: str | None = Header(None, alias="X-Client-Id")):
    if not x_client_id:
        raise HTTPException(status_code=400, detail="X-Client-Id header required")
    CLIENTS[x_client_id] = _new_client_state()
    return {"client_id": x_client_id, "reset": True}
