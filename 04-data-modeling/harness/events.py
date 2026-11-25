"""Deterministic business-event stream generator for PriceWatch.

Writes data/events.jsonl (one JSON event per line, ordered by ingested_at,
i.e. arrival order) plus data/events.meta.json and data/clients.jsonl.

Gnarly realities included on purpose:
- the same product appears under different shop-local titles,
- prices are observed in the shop's home currency, occasionally in another,
- ~3% of observations arrive late (event_time far behind ingested_at),
- ~1% of observations are exact duplicates arriving twice.

Guarantees the loader may rely on (documented in the module README):
- shop_registered arrives before any event for that shop,
- product_discovered for a listing arrives before that listing's observations,
- admin events (renames, tier/attr changes, delist/relist) arrive in
  event_time order relative to each other for the same entity,
- no two distinct prices share the same (shop, product, event_time).
"""

import argparse
import hashlib
import json
import math
from datetime import timedelta

import numpy as np

from common import (
    BRANDS,
    CATEGORIES,
    COUNTRIES,
    CURRENCIES,
    END_DATE,
    FX_TO_USD,
    START_DATE,
    TIERS,
    TIER_WEIGHTS,
    iso,
)

DAY = 86400.0
HOUR = 3600.0
T0 = START_DATE.timestamp()
T1 = END_DATE.timestamp()
SPAN = T1 - T0

CATEGORY_PRICE_SCALE = {
    "electronics": 220.0,
    "home-appliances": 160.0,
    "kitchen": 55.0,
    "toys": 28.0,
    "sporting-goods": 60.0,
    "office-supplies": 18.0,
    "beauty": 22.0,
    "grocery": 8.0,
    "pet-supplies": 25.0,
    "tools": 70.0,
    "furniture": 240.0,
    "footwear": 75.0,
    "apparel": 45.0,
    "books": 16.0,
    "garden": 40.0,
}

SHOP_ADJ = [
    "Prime", "Metro", "Alpine", "Coastal", "Urban", "Golden", "Rapid", "Bright",
    "Nordic", "Central", "Velvet", "Summit", "Harbor", "Cobalt", "Maple", "Aurora",
    "Falcon", "Beacon", "Cinder", "Willow", "Granite", "Silver", "Copper", "Onyx",
    "Ember", "Frost", "Lantern", "Meadow", "Orchard", "Pioneer", "Quarry", "Ridge",
]
SHOP_NOUN = [
    "Market", "Depot", "Outlet", "Bazaar", "Store", "Trading", "Goods", "Supply",
    "Mart", "Exchange", "Emporium", "Warehouse", "Corner", "Hub", "Cart", "Shelf",
]
PRODUCT_NOUN = [
    "Blender", "Kettle", "Lamp", "Router", "Headphones", "Monitor", "Keyboard",
    "Drill", "Backpack", "Sneakers", "Jacket", "Mixer", "Vacuum", "Camera",
    "Speaker", "Charger", "Desk", "Chair", "Mat", "Bottle", "Tent", "Scale",
    "Fan", "Heater", "Grinder", "Toaster", "Tripod", "Notebook", "Marker", "Rack",
]
CLIENT_WORDS = [
    "Argon", "Basalt", "Corsair", "Delta", "Everest", "Fathom", "Glacier",
    "Helix", "Icarus", "Juno", "Krypton", "Lattice", "Mistral", "Nimbus",
    "Orbit", "Pylon", "Quasar", "Rhombus", "Sable", "Tundra", "Umbra", "Vector",
]

HOME_CURRENCY = {"US": "USD", "GB": "GBP"}


def home_currency(country: str) -> str:
    return HOME_CURRENCY.get(country, "EUR")


def local_title_variant(rng, canonical: str, brand: str, shop_code: str) -> str:
    kind = rng.integers(0, 5)
    if kind == 0:
        return canonical
    if kind == 1:
        return canonical.upper()
    if kind == 2:
        return canonical.replace(brand + " ", "") + f" by {brand}"
    if kind == 3:
        return f"{canonical} ({shop_code} exclusive)"
    return f"{brand[:3].upper()}. " + canonical.split(" ", 1)[1]


def build_shops(rng, n_shops):
    shops = []
    for i in range(n_shops):
        code = f"S{i + 1:03d}"
        name = f"{SHOP_ADJ[i % len(SHOP_ADJ)]} {SHOP_NOUN[(i * 7) % len(SHOP_NOUN)]}"
        country = COUNTRIES[int(rng.integers(0, len(COUNTRIES)))]
        tier = str(rng.choice(TIERS, p=TIER_WEIGHTS))
        r = rng.random()
        if r < 0.6:
            reg = T0 + rng.random() * 90 * DAY
        elif r < 0.9:
            reg = T0 + (90 + rng.random() * 150) * DAY
        else:
            reg = T0 + (240 + rng.random() * 190) * DAY
        shops.append({
            "code": code,
            "name": name,
            "country": country,
            "tier": tier,
            "currency": home_currency(country),
            "registered": reg,
            "factor": 0.8 + rng.random() * 0.5,
            "activity": 0.5 + rng.random(),
        })
    return shops


def build_products(rng, n_products):
    products = []
    for i in range(n_products):
        brand = BRANDS[int(rng.integers(0, len(BRANDS)))]
        noun = PRODUCT_NOUN[int(rng.integers(0, len(PRODUCT_NOUN)))]
        model = f"{chr(65 + int(rng.integers(0, 26)))}{chr(65 + int(rng.integers(0, 26)))}-{int(rng.integers(100, 999))}"
        category = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
        base = CATEGORY_PRICE_SCALE[category] * float(np.exp(rng.normal(0.0, 0.5)))
        birth = T0 + float(rng.beta(1.2, 2.5)) * 660 * DAY
        n_repr = 1 + int((T1 - birth) / (45 * DAY * max(0.2, float(rng.random()) + 0.3)))
        repr_times = np.sort(birth + rng.random(n_repr) * (T1 - birth))
        repr_times = np.concatenate([[birth], repr_times])
        season_amp = float(rng.random()) * 0.12
        phase = float(rng.random()) * 2 * math.pi
        drift = (float(rng.random()) * 0.25 - 0.1) / (365 * DAY)
        mults = []
        for t in repr_times:
            seasonal = 1.0 + season_amp * math.sin(2 * math.pi * (t - T0) / (365 * DAY) + phase)
            wobble = 1.0 + float(rng.normal(0.0, 0.05))
            mults.append(seasonal * (1.0 + drift * (t - birth)) * wobble)
        products.append({
            "code": f"P{i + 1:05d}",
            "brand": brand,
            "category": category,
            "title": f"{brand} {noun} {model}",
            "base": base,
            "birth": birth,
            "popularity": 1.0 / ((i % 997) + 1) ** 0.7,
            "repr_times": repr_times,
            "repr_mults": np.array(mults),
        })
    return products


def build_listings(rng, shops, products):
    listings = []
    n_shops = len(shops)
    for p_idx, prod in enumerate(products):
        k = min(n_shops, 2 + int(rng.zipf(1.6)) % 9)
        shop_ids = rng.choice(n_shops, size=k, replace=False)
        for s_idx in shop_ids:
            shop = shops[s_idx]
            disc = max(prod["birth"], shop["registered"] + 1 * DAY) + float(rng.exponential(15 * DAY))
            if disc > T1 - 30 * DAY:
                continue
            listings.append({
                "s": int(s_idx),
                "p": p_idx,
                "discovered": disc,
                "noise": 1.0 + float(rng.normal(0.0, 0.03)),
                "delist": None,
                "relist": None,
            })
    return listings


def assign_lifecycle(rng, listings):
    """Delist ~15% of listings once; ~55% of those relist 10-75 days later.
    Force a handful of 2025 churn cases so Q12 is never degenerate."""
    n = len(listings)
    idx = rng.permutation(n)
    n_delist = max(10, int(0.15 * n))
    chosen = idx[:n_delist]
    forced_recover, forced_churn = 0, 0
    for j, li_idx in enumerate(chosen):
        li = listings[li_idx]
        lo = li["discovered"] + 30 * DAY
        if lo > T1 - 20 * DAY:
            continue
        if forced_recover < 5:
            d_lo = max(lo, T0 + 400 * DAY)
            d_hi = T0 + 580 * DAY
            if d_lo < d_hi:
                d = d_lo + float(rng.random()) * (d_hi - d_lo)
                li["delist"] = d
                li["relist"] = d + (10 + float(rng.random()) * 40) * DAY
                forced_recover += 1
                continue
        if forced_churn < 4:
            d_lo = max(lo, T0 + 400 * DAY)
            d_hi = T0 + 700 * DAY
            if d_lo < d_hi:
                li["delist"] = d_lo + float(rng.random()) * (d_hi - d_lo)
                forced_churn += 1
                continue
        d = lo + float(rng.random()) * (T1 - 20 * DAY - lo)
        li["delist"] = d
        if rng.random() < 0.55:
            r = d + (10 + float(rng.random()) * 65) * DAY
            if r < T1 - 5 * DAY:
                li["relist"] = r


def build_admin_events(rng, shops, products, listings):
    events = []

    def emit(t, etype, payload, max_delay=300.0):
        ing = t + 1 + float(rng.random()) * max_delay
        events.append((ing, t, etype, payload))

    for shop in shops:
        emit(shop["registered"], "shop_registered", {
            "shop_code": shop["code"], "name": shop["name"],
            "country": shop["country"], "tier": shop["tier"],
            "home_currency": shop["currency"],
        })

    renamed = [s for s in shops if rng.random() < 0.4]
    for i, shop in enumerate(renamed):
        lo = shop["registered"] + 60 * DAY
        if i < 2:
            t = max(lo, T0 + 70 * DAY) + float(rng.random()) * 120 * DAY
            t = min(t, T0 + 250 * DAY)
        else:
            t = lo + float(rng.random()) * max(DAY, (T1 - 30 * DAY - lo))
        if t >= T1 - 5 * DAY or t <= shop["registered"]:
            continue
        new_name = shop["name"] + " " + ["Group", "Online", "Direct", "Plus"][i % 4]
        emit(t, "shop_renamed", {"shop_code": shop["code"], "new_name": new_name})

    tiered = [s for s in shops if rng.random() < 0.5]
    for i, shop in enumerate(tiered):
        lo = shop["registered"] + 45 * DAY
        if i < 3:
            t = max(lo, T0 + 60 * DAY) + float(rng.random()) * 130 * DAY
            t = min(t, T0 + 250 * DAY)
        else:
            t = lo + float(rng.random()) * max(DAY, (T1 - 30 * DAY - lo))
        if t >= T1 - 5 * DAY or t <= shop["registered"]:
            continue
        others = [x for x in TIERS if x != shop["tier"]]
        new_tier = others[int(rng.integers(0, len(others)))]
        emit(t, "shop_tier_changed", {"shop_code": shop["code"], "new_tier": new_tier})
        if rng.random() < 0.3:
            t2 = t + (60 + float(rng.random()) * 200) * DAY
            if t2 < T1 - 5 * DAY:
                final = [x for x in TIERS if x != new_tier][int(rng.integers(0, 2))]
                emit(t2, "shop_tier_changed", {"shop_code": shop["code"], "new_tier": final})

    first_disc = {}
    for li in listings:
        p = li["p"]
        if p not in first_disc or li["discovered"] < first_disc[p]:
            first_disc[p] = li["discovered"]

    n_attr = max(8, int(0.10 * len(products)))
    early = [i for i in first_disc if first_disc[i] < T0 + 120 * DAY]
    order = list(rng.permutation(len(products)))
    attr_targets = ([i for i in early[:4]] + [i for i in order if i in first_disc])[:n_attr]
    seen = set()
    attr_targets = [i for i in attr_targets if not (i in seen or seen.add(i))][:n_attr]
    win_lo, win_hi = T0 + 213 * DAY, T0 + 480 * DAY  # 2024-08-01 .. 2025-04-26
    for j, p_idx in enumerate(attr_targets):
        prod = products[p_idx]
        lo = first_disc[p_idx] + 30 * DAY
        if j < 3:
            t = max(lo, win_lo) + float(rng.random()) * max(DAY, win_hi - max(lo, win_lo))
            kind = "brand"
        else:
            t = lo + float(rng.random()) * max(DAY, T1 - 20 * DAY - lo)
            r = rng.random()
            kind = "canonical_title" if r < 0.4 else ("brand" if r < 0.7 else "category")
        if t >= T1 - 5 * DAY:
            continue
        changes = {}
        if kind == "brand":
            changes["brand"] = BRANDS[(BRANDS.index(prod["brand"]) + 1 + int(rng.integers(0, 5))) % len(BRANDS)]
        elif kind == "category":
            changes["category"] = CATEGORIES[(CATEGORIES.index(prod["category"]) + 1 + int(rng.integers(0, 4))) % len(CATEGORIES)]
        else:
            changes["canonical_title"] = prod["title"] + " (rev. " + chr(66 + int(rng.integers(0, 3))) + ")"
        emit(t, "product_attrs_changed", {"product_code": prod["code"], "changes": changes})
        if rng.random() < 0.25:
            t2 = t + (40 + float(rng.random()) * 300) * DAY
            if t2 < T1 - 10 * DAY:
                emit(t2, "product_attrs_changed", {
                    "product_code": prod["code"],
                    "changes": {"canonical_title": prod["title"] + " (rev. Z)"},
                })

    for li in listings:
        prod = products[li["p"]]
        shop = shops[li["s"]]
        emit(li["discovered"], "product_discovered", {
            "shop_code": shop["code"], "product_code": prod["code"],
            "local_title": local_title_variant(rng, prod["title"], prod["brand"], shop["code"]),
            "canonical_title": prod["title"], "brand": prod["brand"],
            "category": prod["category"],
        }, max_delay=120.0)
        if li["delist"] is not None:
            emit(li["delist"], "product_delisted", {
                "shop_code": shop["code"], "product_code": prod["code"],
            })
            if li["relist"] is not None:
                emit(li["relist"], "product_relisted", {
                    "shop_code": shop["code"], "product_code": prod["code"],
                    "local_title": local_title_variant(rng, prod["title"], prod["brand"], shop["code"]),
                })
    return events


def build_observations(rng, shops, products, listings, total_obs):
    """Vectorized per listing. Returns parallel numpy arrays sorted by ingestion."""
    weights = np.array([products[li["p"]]["popularity"] * shops[li["s"]]["activity"] for li in listings])
    weights /= weights.sum()
    counts = np.maximum(3, np.round(weights * total_obs).astype(int))

    cur_idx = {c: i for i, c in enumerate(CURRENCIES)}
    fx = np.array([FX_TO_USD[c] for c in CURRENCIES])

    chunks = []
    for li_i, li in enumerate(listings):
        n = int(counts[li_i])
        prod = products[li["p"]]
        shop = shops[li["s"]]
        lo = li["discovered"] + 6 * HOUR
        if lo >= T1 - HOUR:
            continue
        times = lo + rng.random(n) * (T1 - HOUR - lo)
        if li["delist"] is not None:
            hi = li["relist"] if li["relist"] is not None else T1
            mask = ~((times >= li["delist"]) & (times < hi + 6 * HOUR))
            times = times[mask]
        times = np.unique(np.round(times))
        if times.size == 0:
            continue
        pos = np.searchsorted(prod["repr_times"], times, side="right") - 1
        ref = prod["base"] * prod["repr_mults"][np.clip(pos, 0, None)]
        usd = ref * shop["factor"] * li["noise"]
        promo = rng.random(times.size) < 0.04
        usd = np.where(promo, usd * (0.65 + rng.random(times.size) * 0.15), usd)
        cur = np.full(times.size, cur_idx[shop["currency"]], dtype=np.int8)
        switch = rng.random(times.size) < 0.03
        if switch.any():
            alt = rng.integers(0, len(CURRENCIES), size=int(switch.sum()))
            cur[switch] = alt
        amount = np.maximum(0.5, np.round(usd / fx[cur], 2))

        r = rng.random(times.size)
        delay = np.where(
            r < 0.965, 2 + rng.random(times.size) * 1800,
            np.where(
                r < 0.985, (25 + rng.random(times.size) * 71) * HOUR,
                np.where(
                    r < 0.995, (3 + rng.random(times.size) * 7) * DAY,
                    (1 + rng.random(times.size) * 23) * HOUR,
                ),
            ),
        )
        ing = times + delay
        chunks.append((
            np.full(times.size, li["s"], dtype=np.int32),
            np.full(times.size, li["p"], dtype=np.int32),
            times, ing, amount, cur,
        ))

    s_arr = np.concatenate([c[0] for c in chunks])
    p_arr = np.concatenate([c[1] for c in chunks])
    t_arr = np.concatenate([c[2] for c in chunks])
    i_arr = np.concatenate([c[3] for c in chunks])
    a_arr = np.concatenate([c[4] for c in chunks])
    c_arr = np.concatenate([c[5] for c in chunks])

    dup_mask = rng.random(s_arr.size) < 0.01
    dup_idx = np.flatnonzero(dup_mask)
    if dup_idx.size:
        s_arr = np.concatenate([s_arr, s_arr[dup_idx]])
        p_arr = np.concatenate([p_arr, p_arr[dup_idx]])
        t_arr = np.concatenate([t_arr, t_arr[dup_idx]])
        i_arr = np.concatenate([i_arr, i_arr[dup_idx] + 60 + rng.random(dup_idx.size) * 3540])
        a_arr = np.concatenate([a_arr, a_arr[dup_idx]])
        c_arr = np.concatenate([c_arr, c_arr[dup_idx]])

    order = np.argsort(i_arr, kind="stable")
    return s_arr[order], p_arr[order], t_arr[order], i_arr[order], a_arr[order], c_arr[order]


def ts(t: float) -> str:
    from datetime import datetime, timezone
    return iso(datetime.fromtimestamp(round(t), tz=timezone.utc))


def write_events(path, admin_events, obs, shops, products):
    admin_events.sort(key=lambda e: e[0])
    s_arr, p_arr, t_arr, i_arr, a_arr, c_arr = obs
    shop_codes = [s["code"] for s in shops]
    prod_codes = [p["code"] for p in products]
    n_obs = s_arr.size
    ai, oi = 0, 0
    count = 0
    sha = hashlib.sha256()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        while ai < len(admin_events) or oi < n_obs:
            take_admin = oi >= n_obs or (ai < len(admin_events) and admin_events[ai][0] <= i_arr[oi])
            if take_admin:
                ing, t, etype, payload = admin_events[ai]
                ai += 1
                rec = {"event_type": etype, "event_time": ts(t), "ingested_at": ts(ing)}
                rec.update(payload)
            else:
                rec = {
                    "event_type": "price_observed",
                    "event_time": ts(float(t_arr[oi])),
                    "ingested_at": ts(float(i_arr[oi])),
                    "shop_code": shop_codes[s_arr[oi]],
                    "product_code": prod_codes[p_arr[oi]],
                    "price": float(a_arr[oi]),
                    "currency": CURRENCIES[c_arr[oi]],
                }
                oi += 1
            line = json.dumps(rec, separators=(",", ":")) + "\n"
            f.write(line)
            sha.update(line.encode("utf-8"))
            count += 1
    return count, sha.hexdigest()


def write_clients(path, rng, products, scale):
    n_clients = max(6, int(round(18 * math.sqrt(scale))))
    pop = np.array([p["popularity"] for p in products])
    pop = pop / pop.sum()
    sha = hashlib.sha256()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i in range(n_clients):
            code = f"C{i + 1:03d}"
            name = f"{CLIENT_WORDS[i % len(CLIENT_WORDS)]} {CLIENT_WORDS[(i * 5 + 3) % len(CLIENT_WORDS)]} Ltd"
            created = T0 + 366 * DAY + float(rng.random()) * 200 * DAY
            k = min(len(products), 5 + int(rng.zipf(1.5)) % 36)
            tracked = rng.choice(len(products), size=k, replace=False, p=pop)
            for p_idx in sorted(int(x) for x in tracked):
                since = created + float(rng.random()) * 60 * DAY
                rec = {
                    "client_code": code,
                    "client_name": name,
                    "created_at": ts(created),
                    "product_code": products[p_idx]["code"],
                    "tracked_since": ts(since),
                }
                line = json.dumps(rec, separators=(",", ":")) + "\n"
                f.write(line)
                sha.update(line.encode("utf-8"))
    return n_clients, sha.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Generate the PriceWatch event stream")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/events.jsonl")
    args = ap.parse_args()

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    rng = np.random.default_rng(args.seed)
    scale = args.scale

    n_shops = max(10, int(round(50 * math.sqrt(scale))))
    n_products = max(60, int(round(2400 * scale)))
    total_obs = int(2_400_000 * scale)

    shops = build_shops(rng, n_shops)
    products = build_products(rng, n_products)
    listings = build_listings(rng, shops, products)
    assign_lifecycle(rng, listings)
    admin = build_admin_events(rng, shops, products, listings)
    obs = build_observations(rng, shops, products, listings, total_obs)

    count, sha = write_events(args.out, admin, obs, shops, products)

    clients_path = os.path.join(os.path.dirname(args.out) or ".", "clients.jsonl")
    n_clients, clients_sha = write_clients(clients_path, rng, products, scale)

    meta = {
        "scale": scale,
        "seed": args.seed,
        "events": count,
        "sha256": sha,
        "shops": n_shops,
        "products": n_products,
        "listings": len(listings),
        "clients": n_clients,
        "clients_sha256": clients_sha,
    }
    meta_path = os.path.join(os.path.dirname(args.out) or ".", "events.meta.json")
    with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    print(f"wrote {count} events to {args.out} (scale={scale}, shops={n_shops}, "
          f"products={n_products}, listings={len(listings)}, clients={n_clients})")


if __name__ == "__main__":
    main()
