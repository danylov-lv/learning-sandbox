"""Deterministic generator of "scraped" price NDJSON dumps for module 06.

Writes one file per day under data/raw/dt=YYYY-MM-DD/prices.ndjson for
2025-06-01 through 2025-06-14, plus data/ground-truth.json with everything
the generator planted (dedup, poison lines, invalid records, schema drift,
late-arriving repeats). See .authoring/design.md for the full contract —
this file must stay in sync with it.

Respects SCALE (default 1.0) for volume. Deterministic: same SCALE always
produces byte-identical output (single seeded np.random.default_rng(60606)
stream, Faker seeded the same).

Usage:
    uv run python generate.py
    SCALE=0.05 uv run python generate.py
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from faker import Faker

SEED = 60606
MODULE_ROOT = Path(__file__).resolve().parent
RAW_DIR = MODULE_ROOT / "data" / "raw"
GROUND_TRUTH_PATH = MODULE_ROOT / "data" / "ground-truth.json"

N_PRODUCTS = 8000
N_DAYS = 14
START_DATE = datetime(2025, 6, 1, tzinfo=timezone.utc)

MALFORMED_RATE = 0.004
DUPLICATE_RATE = 0.02
INVALID_RATE = 0.01
LATE_ARRIVING_RATE = 0.03
MEAN_LINES_PER_DAY = 45_000
DAILY_LOGNORMAL_SIGMA = 0.2

SELLER_RATING_FROM = datetime(2025, 6, 10, tzinfo=timezone.utc)
PRICE_STRING_FROM = datetime(2025, 6, 12, tzinfo=timezone.utc)

SOURCES = [
    "shopnest.example",
    "dealbarn.example",
    "cartify.example",
    "brightbuy.example",
    "thriftloop.example",
    "primemart.example",
]

CATEGORIES = [
    "electronics", "home-goods", "kitchen", "toys", "sporting-goods",
    "office-supplies", "beauty", "grocery", "pet-supplies", "tools",
    "furniture", "apparel",
]

CATEGORY_PRICE_PROFILE = {
    "electronics": (120.0, 0.9),
    "home-goods": (45.0, 0.7),
    "kitchen": (35.0, 0.6),
    "toys": (25.0, 0.6),
    "sporting-goods": (55.0, 0.7),
    "office-supplies": (15.0, 0.5),
    "beauty": (20.0, 0.5),
    "grocery": (8.0, 0.4),
    "pet-supplies": (18.0, 0.5),
    "tools": (40.0, 0.7),
    "furniture": (250.0, 0.8),
    "apparel": (30.0, 0.6),
}

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.60, 0.25, 0.15]
CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}
BAD_CURRENCY_CODES = ["XXX", "ZZZ", "N/A", "???"]

INVALID_REASON_SHARES = {
    "missing_url": 0.30,
    "bad_price": 0.30,
    "unknown_currency": 0.20,
    "bad_timestamp": 0.20,
}

Z99 = 2.3263


def category_weights():
    ranks = np.arange(len(CATEGORIES))
    w = 1.0 / (ranks + 1) ** 1.1
    return w / w.sum()


def day_date(day_idx):
    return START_DATE + timedelta(days=day_idx)


def day_key(day_idx):
    return day_date(day_idx).strftime("%Y-%m-%d")


class Universe:
    def __init__(self, rng, fake):
        cat_w = category_weights()
        self.cat_weights = cat_w
        product_category_idx = rng.choice(len(CATEGORIES), size=N_PRODUCTS, p=cat_w)
        self.product_category_idx = product_category_idx

        popularity_rank = rng.permutation(N_PRODUCTS) + 1
        raw_pop_weight = 1.0 / popularity_rank ** 1.2
        pop_weight = np.zeros(N_PRODUCTS)
        self.category_product_ids = {}
        self.category_product_weights = {}
        for ci, cat in enumerate(CATEGORIES):
            members = np.nonzero(product_category_idx == ci)[0]
            if members.size == 0:
                continue
            w = raw_pop_weight[members]
            w = w / w.sum()
            self.category_product_ids[cat] = members + 1  # product ids 1-based
            self.category_product_weights[cat] = w
            pop_weight[members] = w

        self.titles = [fake.catch_phrase() for _ in range(N_PRODUCTS)]

        self.product_url = [None] * N_PRODUCTS
        for pid in range(1, N_PRODUCTS + 1):
            cat = CATEGORIES[product_category_idx[pid - 1]]
            self.product_url[pid - 1] = f"/products/p-{pid:05d}-{cat}"

        self.category_p99 = {}
        for cat, (median, sigma) in CATEGORY_PRICE_PROFILE.items():
            self.category_p99[cat] = median * math.exp(sigma * Z99)

    def category_of(self, pid):
        return CATEGORIES[self.product_category_idx[pid - 1]]

    def sample_products(self, rng, cat, n):
        ids = self.category_product_ids[cat]
        w = self.category_product_weights[cat]
        return rng.choice(ids, size=n, p=w)


def iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def random_time_in_day(rng, day_idx, n):
    base = day_date(day_idx)
    secs = rng.integers(0, 86400, size=n)
    return [base + timedelta(seconds=int(s)) for s in secs]


def resolve_valid_key_collisions(valid_recs, day_idx):
    """Nudge scraped_at seconds so that within each (source_site, product_url)
    group every valid record has a distinct whole-second scraped_at inside the
    day window. Fully deterministic, zero RNG draws: only some valid records'
    scraped_at seconds move (never price/currency/product/validity), searching
    outward +1s, -1s, +2s, -2s, ... to the nearest free second in
    [dt 00:00:00Z, dt+1 00:00:00Z). Returns the count of records nudged."""
    base = day_date(day_idx)
    used = {}
    nudged = 0
    for rec in valid_recs:
        key = (rec["source_site"], rec["product_url"])
        ts = datetime.strptime(rec["scraped_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        sec = int((ts - base).total_seconds())
        taken = used.setdefault(key, set())
        if sec not in taken:
            taken.add(sec)
            continue
        new_sec = None
        delta = 1
        while new_sec is None:
            for cand in (sec + delta, sec - delta):
                if 0 <= cand < 86400 and cand not in taken:
                    new_sec = cand
                    break
            delta += 1
        taken.add(new_sec)
        rec["scraped_at"] = iso(base + timedelta(seconds=new_sec))
        nudged += 1
    return nudged


def format_price_string(price, currency, style_bit):
    if style_bit == 0:
        symbol = CURRENCY_SYMBOL[currency]
        return f"{symbol}{price:,.2f}"
    whole = f"{price:,.2f}"
    whole = whole.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{whole} {currency}"


def build_valid_record(rng, u, day_idx, source, pid, currency, price, in_stock,
                        scraped_at, seller_rating, price_is_string):
    cat = u.category_of(pid)
    # round() and the "%.2f"-style formatting in format_price_string both use
    # round-half-even on the same double, so the drift-day string encodes
    # exactly this 2-decimal numeric.
    numeric_price = round(float(price), 2)
    rec = {
        "source_site": source,
        "product_url": u.product_url[pid - 1],
        "title": u.titles[pid - 1],
        "category": cat,
        "price": format_price_string(price, currency, int(rng.integers(0, 2))) if price_is_string else numeric_price,
        "currency": currency,
        "in_stock": bool(in_stock),
        "scraped_at": iso(scraped_at),
    }
    if seller_rating is not None:
        rec["seller_rating"] = seller_rating
    return rec, pid, cat, numeric_price


def generate_fresh_valid(rng, u, day_idx, n, has_seller_rating, price_is_string):
    if n == 0:
        return [], [], [], []
    cat_idx = rng.choice(len(CATEGORIES), size=n, p=u.cat_weights)
    pids = np.zeros(n, dtype=np.int64)
    for ci, cat in enumerate(CATEGORIES):
        mask = cat_idx == ci
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        pids[mask] = u.sample_products(rng, cat, cnt)

    sources = rng.choice(SOURCES, size=n)
    currencies = rng.choice(CURRENCIES, size=n, p=CURRENCY_WEIGHTS)
    in_stock = rng.random(n) < 0.85
    scraped_ats = random_time_in_day(rng, day_idx, n)
    ratings = np.round(rng.uniform(1.0, 5.0, size=n), 1) if has_seller_rating else [None] * n

    prices = np.zeros(n)
    for ci, cat in enumerate(CATEGORIES):
        mask = cat_idx == ci
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        median, sigma = CATEGORY_PRICE_PROFILE[cat]
        mu = math.log(median)
        prices[mask] = rng.lognormal(mu, sigma, size=cnt)

    recs = []
    pairs = []
    cur_prices = []
    for i in range(n):
        pid = int(pids[i])
        rating = None if not has_seller_rating else float(ratings[i])
        rec, out_pid, cat, numeric_price = build_valid_record(
            rng, u, day_idx, str(sources[i]), pid, str(currencies[i]),
            float(prices[i]), bool(in_stock[i]), scraped_ats[i], rating, price_is_string,
        )
        recs.append(rec)
        pairs.append((str(sources[i]), out_pid, cat))
        cur_prices.append((str(currencies[i]), numeric_price))
    return recs, pairs, list(pids), cur_prices


def generate_late_arriving(rng, u, day_idx, n, prev_pairs, has_seller_rating, price_is_string):
    if n == 0 or not prev_pairs:
        return [], [], [], []
    choice_idx = rng.integers(0, len(prev_pairs), size=n)
    currencies = rng.choice(CURRENCIES, size=n, p=CURRENCY_WEIGHTS)
    in_stock = rng.random(n) < 0.85
    scraped_ats = random_time_in_day(rng, day_idx, n)
    ratings = np.round(rng.uniform(1.0, 5.0, size=n), 1) if has_seller_rating else [None] * n

    recs = []
    pairs = []
    pids_out = []
    cur_prices = []
    for i in range(n):
        source, pid, cat = prev_pairs[int(choice_idx[i])]
        median, sigma = CATEGORY_PRICE_PROFILE[cat]
        mu = math.log(median)
        price = float(rng.lognormal(mu, sigma))
        rating = None if not has_seller_rating else float(ratings[i])
        rec, out_pid, out_cat, numeric_price = build_valid_record(
            rng, u, day_idx, source, pid, str(currencies[i]), price,
            bool(in_stock[i]), scraped_ats[i], rating, price_is_string,
        )
        recs.append(rec)
        pairs.append((source, out_pid, out_cat))
        pids_out.append(pid)
        cur_prices.append((str(currencies[i]), numeric_price))
    return recs, pairs, pids_out, cur_prices


def generate_invalid(rng, u, day_idx, n):
    """Returns (lines, reason_counts dict)."""
    if n == 0:
        return [], {k: 0 for k in INVALID_REASON_SHARES}

    shares = list(INVALID_REASON_SHARES.items())
    counts = {}
    assigned = 0
    for i, (reason, share) in enumerate(shares):
        if i < len(shares) - 1:
            c = round(n * share)
            counts[reason] = c
            assigned += c
        else:
            counts[reason] = n - assigned

    lines = []
    for reason, cnt in counts.items():
        if cnt == 0:
            continue
        cat_idx = rng.choice(len(CATEGORIES), size=cnt, p=u.cat_weights)
        pids = np.zeros(cnt, dtype=np.int64)
        for ci, cat in enumerate(CATEGORIES):
            mask = cat_idx == ci
            m = int(mask.sum())
            if m == 0:
                continue
            pids[mask] = u.sample_products(rng, cat, m)
        sources = rng.choice(SOURCES, size=cnt)
        currencies = rng.choice(CURRENCIES, size=cnt, p=CURRENCY_WEIGHTS)
        in_stock = rng.random(cnt) < 0.85
        scraped_ats = random_time_in_day(rng, day_idx, cnt)

        prices = np.zeros(cnt)
        for ci, cat in enumerate(CATEGORIES):
            mask = cat_idx == ci
            m = int(mask.sum())
            if m == 0:
                continue
            median, sigma = CATEGORY_PRICE_PROFILE[cat]
            mu = math.log(median)
            prices[mask] = rng.lognormal(mu, sigma, size=m)

        for i in range(cnt):
            pid = int(pids[i])
            cat = u.category_of(pid)
            rec = {
                "source_site": str(sources[i]),
                "product_url": u.product_url[pid - 1],
                "title": u.titles[pid - 1],
                "category": cat,
                "price": round(float(prices[i]), 2),
                "currency": str(currencies[i]),
                "in_stock": bool(in_stock[i]),
                "scraped_at": iso(scraped_ats[i]),
            }
            if reason == "missing_url":
                if i % 2 == 0:
                    rec["product_url"] = None
                else:
                    del rec["product_url"]
            elif reason == "bad_price":
                p99 = u.category_p99[cat]
                if i % 2 == 0:
                    rec["price"] = round(float(rng.uniform(-500, -1)), 2)
                else:
                    rec["price"] = round(p99 * float(rng.uniform(10, 20)), 2)
            elif reason == "unknown_currency":
                rec["currency"] = BAD_CURRENCY_CODES[i % len(BAD_CURRENCY_CODES)]
            elif reason == "bad_timestamp":
                offset_days = int(rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]))
                bad_ts = scraped_ats[i] + timedelta(days=offset_days)
                rec["scraped_at"] = iso(bad_ts)

            lines.append(json.dumps(rec, ensure_ascii=False))

    return lines, counts


def generate_malformed(rng, fake, existing_lines, n):
    if n == 0:
        return []
    out = []
    for i in range(n):
        kind = i % 3
        if kind == 0 and existing_lines:
            src = existing_lines[int(rng.integers(0, len(existing_lines)))]
            cut = int(rng.integers(10, 60))
            out.append(src[:cut])
        elif kind == 1:
            pid = int(rng.integers(1, N_PRODUCTS + 1))
            out.append('{"source_site": "shopnest.example", "product_url": "/products/p-%05d", truncated' % pid)
        else:
            out.append("NOT_JSON " + fake.sentence())
    return out


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)

    print(f"SCALE={scale}")
    print("building product universe...")
    u = Universe(rng, fake)

    if RAW_DIR.exists():
        for child in RAW_DIR.glob("dt=*"):
            for f in child.glob("*"):
                f.unlink()
            child.rmdir()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    per_day = {}
    per_day_currency = {}
    global_pair_set = set()
    per_category_valid_counts = {c: 0 for c in CATEGORIES}
    mart_reference = {}

    prev_valid_pairs = []

    mean_log = math.log(MEAN_LINES_PER_DAY * scale)

    for day_idx in range(N_DAYS):
        d = day_date(day_idx)
        dk = day_key(day_idx)
        has_seller_rating = d >= SELLER_RATING_FROM
        price_is_string = d >= PRICE_STRING_FROM

        T = int(round(rng.lognormal(mean_log, DAILY_LOGNORMAL_SIGMA)))
        T = max(T, 100)  # floor so tiny SCALE never produces a degenerate day

        malformed_n = round(T * MALFORMED_RATE)
        dup_n = round(T * DUPLICATE_RATE)
        base_n = T - malformed_n - dup_n
        invalid_n = round(base_n * INVALID_RATE)
        valid_n = base_n - invalid_n
        late_n = round(valid_n * LATE_ARRIVING_RATE) if day_idx > 0 else 0
        fresh_n = valid_n - late_n

        fresh_recs, fresh_pairs, fresh_pids, fresh_cur_prices = generate_fresh_valid(
            rng, u, day_idx, fresh_n, has_seller_rating, price_is_string
        )
        late_recs, late_pairs, late_pids, late_cur_prices = generate_late_arriving(
            rng, u, day_idx, late_n, prev_valid_pairs, has_seller_rating, price_is_string
        )
        invalid_lines, invalid_counts = generate_invalid(rng, u, day_idx, invalid_n)

        valid_recs = fresh_recs + late_recs
        nudged = resolve_valid_key_collisions(valid_recs, day_idx)
        valid_lines = [json.dumps(rec, ensure_ascii=False) for rec in valid_recs]
        valid_pairs = fresh_pairs + late_pairs
        valid_pids = fresh_pids + late_pids
        valid_cur_prices = fresh_cur_prices + late_cur_prices

        for source, pid, cat in valid_pairs:
            global_pair_set.add((source, u.product_url[pid - 1]))
            per_category_valid_counts[cat] += 1

        day_currency_stats = {c: {"count": 0, "price_sum": 0.0} for c in CURRENCIES}
        for line in valid_lines:
            rec = json.loads(line)
            cur = rec["currency"]
            day_currency_stats[cur]["count"] += 1
            if not price_is_string:
                day_currency_stats[cur]["price_sum"] += rec["price"]

        if price_is_string:
            mart_reference[dk] = {c: {"count": day_currency_stats[c]["count"]} for c in CURRENCIES}
        else:
            mart_reference[dk] = {
                c: {"count": day_currency_stats[c]["count"], "price_sum": round(day_currency_stats[c]["price_sum"], 2)}
                for c in CURRENCIES
            }

        # per_day_currency: planted numerics, all days, drift or not
        pdc = {c: {"count": 0, "price_sum": 0.0} for c in CURRENCIES}
        for cur, numeric_price in valid_cur_prices:
            pdc[cur]["count"] += 1
            pdc[cur]["price_sum"] += numeric_price
        per_day_currency[dk] = {
            c: {"count": pdc[c]["count"], "price_sum": round(pdc[c]["price_sum"], 2)}
            for c in CURRENCIES
        }

        base_lines = valid_lines + invalid_lines
        order = rng.permutation(len(base_lines))
        base_lines = [base_lines[i] for i in order]

        dup_lines = []
        if dup_n > 0 and base_lines:
            dup_src_idx = rng.integers(0, len(base_lines), size=dup_n)
            dup_lines = [base_lines[i] for i in dup_src_idx]

        malformed_lines = generate_malformed(rng, fake, base_lines, malformed_n)

        all_lines = list(base_lines)
        for line in dup_lines:
            pos = int(rng.integers(0, len(all_lines) + 1))
            all_lines.insert(pos, line)
        for line in malformed_lines:
            pos = int(rng.integers(0, len(all_lines) + 1))
            all_lines.insert(pos, line)

        day_dir = RAW_DIR / f"dt={dk}"
        day_dir.mkdir(parents=True, exist_ok=True)
        out_path = day_dir / "prices.ndjson"
        out_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8", newline="\n")

        distinct_products_valid = len(set(valid_pids))

        per_day[dk] = {
            "total_lines": len(all_lines),
            "malformed_lines": malformed_n,
            "parseable_records": len(all_lines) - malformed_n,
            "duplicate_lines": dup_n,
            "invalid_records": {"total": invalid_n, **invalid_counts},
            "valid_records": valid_n,
            "late_arriving_records": late_n,
            "distinct_products_valid": distinct_products_valid,
            "has_seller_rating": has_seller_rating,
            "price_is_string": price_is_string,
        }

        print(f"  {dk}: total={len(all_lines)} valid={valid_n} invalid={invalid_n} "
              f"dup={dup_n} malformed={malformed_n} late_arriving={late_n} "
              f"distinct_products={distinct_products_valid} nudged={nudged}")

        prev_valid_pairs = valid_pairs

    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    ground_truth = {
        "seed": SEED,
        "scale": scale,
        "days": [day_key(i) for i in range(N_DAYS)],
        "schema_drift": {
            "seller_rating_from": SELLER_RATING_FROM.strftime("%Y-%m-%d"),
            "price_string_from": PRICE_STRING_FROM.strftime("%Y-%m-%d"),
        },
        "constants": {
            "sources": SOURCES,
            "categories": CATEGORIES,
            "currency_weights": dict(zip(CURRENCIES, CURRENCY_WEIGHTS)),
            "n_products": N_PRODUCTS,
        },
        "per_day": per_day,
        "per_day_currency": per_day_currency,
        "global": {
            "distinct_source_product_pairs": len(global_pair_set),
            "per_category_valid_counts": per_category_valid_counts,
            "mart_reference": mart_reference,
        },
    }
    GROUND_TRUTH_PATH.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    sys.exit(generate())
