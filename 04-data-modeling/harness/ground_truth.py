"""Ground-truth reference answers for the PriceWatch question battery (q01-q15).

Computes every answer directly from data/events.jsonl + data/clients.jsonl in
one deterministic pass, independent of any learner schema. Results are cached
to data/ground_truth.json, keyed by the sha256 of the event stream + clients
file recorded in data/events.meta.json -- if either sha changes, the cache is
invalidated and recomputed.

Semantics (see harness/questions.md for the learner-facing phrasing):
- Business time = event_time. As-of state at time t for an entity = fold all
  admin events for that entity with event_time <= t, in event_time order.
- Shop initial state comes from shop_registered; shop_renamed / shop_tier_changed
  patch name / tier from their event_time onward.
- Product initial attrs (canonical_title, brand, category) come from the
  FIRST product_discovered event for that product_code (earliest event_time
  across all shops that list it); product_attrs_changed patches attrs for
  that product_code from its event_time onward. Attrs carried on later
  product_discovered events (other shops discovering the same product) are
  ignored -- they are listing snapshots, not attribute changes.
- A listing is the pair (shop_code, product_code); it is active from its
  product_discovered event, inactive from product_delisted, active again
  from product_relisted.
- Deduplication: price_observed rows are unique by (shop_code, product_code,
  event_time). The ~1% exact duplicates are collapsed to the first-arriving
  copy (smallest ingested_at) -- since the file is itself ordered by arrival
  (ingested_at), this is simply "first occurrence encountered".
- USD conversion uses the static common.FX_TO_USD table. All USD amounts are
  rounded to 4 decimals.

CLI:
    uv run python harness/ground_truth.py                # compute/print everything
    uv run python harness/ground_truth.py --q q05         # print just q05
    uv run python harness/ground_truth.py --refresh       # ignore cache, recompute
"""

import argparse
import bisect
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from common import CURRENCIES, FX_TO_USD, START_DATE, END_DATE

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data"))
EVENTS_PATH = os.path.join(DATA_DIR, "events.jsonl")
CLIENTS_PATH = os.path.join(DATA_DIR, "clients.jsonl")
META_PATH = os.path.join(DATA_DIR, "events.meta.json")
CACHE_PATH = os.path.join(DATA_DIR, "ground_truth.json")

T0_EPOCH = int(START_DATE.timestamp())
SPAN_DAYS = (END_DATE - START_DATE).days

# ---- fixed parameters (also documented in questions.md) --------------------

TOP10_PRODUCTS = [
    "P00001", "P01996", "P01001", "P00004", "P00998",
    "P01995", "P01000", "P01999", "P00002", "P00999",
]
Q04_PRODUCT = "P00001"
Q04_WINDOW_START = "2025-01-01"
Q04_WINDOW_DAYS = 60
Q05_YEAR, Q05_MONTH = 2024, 12
Q06_PRODUCTS = ["P00008", "P00595", "P00652"]
Q06_D1 = "2024-04-01T00:00:00Z"
Q06_D2 = "2024-07-01T00:00:00Z"
Q07_CUTOFF = "2024-09-01T00:00:00Z"
Q12_YEAR = 2025
Q13_YEAR, Q13_MONTH = 2025, 3
Q13_CUTOFF = "2025-04-01T00:00:00Z"

FX_VEC = np.array([FX_TO_USD[c] for c in CURRENCIES])
CUR_TO_IDX = {c: i for i, c in enumerate(CURRENCIES)}


def _parse_iso_s(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_epoch(s):
    return int(_parse_iso_s(s).timestamp())


def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d")


def _fmt_month(y, m):
    return f"{y:04d}-{m:02d}"


def _fmt_quarter(y, q):
    return f"{y:04d}-Q{q}"


def _build_calendar():
    """year/month/day/quarter arrays indexed by day-offset from START_DATE."""
    years = np.empty(SPAN_DAYS, dtype=np.int32)
    months = np.empty(SPAN_DAYS, dtype=np.int32)
    days = np.empty(SPAN_DAYS, dtype=np.int32)
    quarters = np.empty(SPAN_DAYS, dtype=np.int32)
    d = START_DATE
    for i in range(SPAN_DAYS):
        years[i] = d.year
        months[i] = d.month
        days[i] = d.day
        quarters[i] = (d.month - 1) // 3 + 1
        d += timedelta(days=1)
    return years, months, days, quarters


CAL_YEAR, CAL_MONTH, CAL_DAY, CAL_QUARTER = _build_calendar()


def asof(times, vals, t):
    i = bisect.bisect_right(times, t) - 1
    return vals[i] if i >= 0 else None


def load_meta():
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


def _round4(x):
    return round(float(x), 4)


class Entities:
    """Parsed admin-event state: shops, products, listings, clients."""

    def __init__(self):
        self.shop_country = {}
        self.shop_tier_bp = {}   # code -> (times list, vals list)
        self.shop_name_bp = {}
        self._shop_tier_raw = {}
        self._shop_name_raw = {}
        self.prod_disc_events = {}   # code -> list of (t, title, brand, category)
        self.prod_category_bp = {}
        self.prod_brand_bp = {}
        self._prod_attr_raw = {}     # code -> list of (t, field, value)
        self.listing_discovered = {}   # (sc,pc) -> t
        self.listing_lifecycle = {}    # (sc,pc) -> list of (t, event_type)
        self.clients = []              # list of dict

    def finalize(self):
        for sc, raw in self._shop_tier_raw.items():
            raw.sort(key=lambda x: x[0])
            self.shop_tier_bp[sc] = ([r[0] for r in raw], [r[1] for r in raw])
        for sc, raw in self._shop_name_raw.items():
            raw.sort(key=lambda x: x[0])
            self.shop_name_bp[sc] = ([r[0] for r in raw], [r[1] for r in raw])
        for pc, disc in self.prod_disc_events.items():
            disc.sort(key=lambda x: x[0])
        for pc, raw in self._prod_attr_raw.items():
            raw.sort(key=lambda x: x[0])
        for pc, disc in self.prod_disc_events.items():
            first_t, first_title, first_brand, first_cat = disc[0]
            cat_bp = [(first_t, first_cat)]
            brand_bp = [(first_t, first_brand)]
            for t, field, val in self._prod_attr_raw.get(pc, []):
                if field == "category":
                    cat_bp.append((t, val))
                elif field == "brand":
                    brand_bp.append((t, val))
            self.prod_category_bp[pc] = ([b[0] for b in cat_bp], [b[1] for b in cat_bp])
            self.prod_brand_bp[pc] = ([b[0] for b in brand_bp], [b[1] for b in brand_bp])
        for key, evs in self.listing_lifecycle.items():
            evs.sort(key=lambda x: x[0])


def parse_events():
    ent = Entities()
    sc_list, pc_list, et_list, ing_list, price_list, cur_list = [], [], [], [], [], []

    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            etype = rec["event_type"]
            if etype == "price_observed":
                sc_list.append(rec["shop_code"])
                pc_list.append(rec["product_code"])
                et_list.append(rec["event_time"])
                ing_list.append(rec["ingested_at"])
                price_list.append(rec["price"])
                cur_list.append(rec["currency"])
                continue
            t = _parse_iso_s(rec["event_time"])
            if etype == "shop_registered":
                sc = rec["shop_code"]
                ent.shop_country[sc] = rec["country"]
                ent._shop_tier_raw.setdefault(sc, []).append((t, rec["tier"]))
                ent._shop_name_raw.setdefault(sc, []).append((t, rec["name"]))
            elif etype == "shop_renamed":
                ent._shop_name_raw.setdefault(rec["shop_code"], []).append((t, rec["new_name"]))
            elif etype == "shop_tier_changed":
                ent._shop_tier_raw.setdefault(rec["shop_code"], []).append((t, rec["new_tier"]))
            elif etype == "product_discovered":
                sc, pc = rec["shop_code"], rec["product_code"]
                key = (sc, pc)
                if key not in ent.listing_discovered or t < ent.listing_discovered[key]:
                    ent.listing_discovered[key] = t
                ent.prod_disc_events.setdefault(pc, []).append(
                    (t, rec["canonical_title"], rec["brand"], rec["category"])
                )
            elif etype == "product_attrs_changed":
                pc = rec["product_code"]
                for field, val in rec["changes"].items():
                    ent._prod_attr_raw.setdefault(pc, []).append((t, field, val))
            elif etype in ("product_delisted", "product_relisted"):
                key = (rec["shop_code"], rec["product_code"])
                ent.listing_lifecycle.setdefault(key, []).append((t, etype))
            else:
                raise ValueError(f"unknown event_type {etype!r}")

    ent.finalize()

    with open(CLIENTS_PATH, encoding="utf-8") as f:
        for line in f:
            ent.clients.append(json.loads(line))

    raw = {
        "sc": sc_list, "pc": pc_list, "et": et_list,
        "ing": ing_list, "price": price_list, "cur": cur_list,
    }
    return ent, raw


def build_observation_arrays(raw):
    """Encode + dedup observations. Returns a dict of numpy arrays, all
    sorted by (shop_idx, product_idx, event_time) ascending, deduplicated by
    (shop_code, product_code, event_time) keeping the first-arriving copy."""
    shop_codes = sorted(set(raw["sc"]))
    prod_codes = sorted(set(raw["pc"]))
    shop_to_idx = {c: i for i, c in enumerate(shop_codes)}
    prod_to_idx = {c: i for i, c in enumerate(prod_codes)}

    n = len(raw["sc"])
    sc_idx = np.fromiter((shop_to_idx[c] for c in raw["sc"]), dtype=np.int32, count=n)
    pc_idx = np.fromiter((prod_to_idx[c] for c in raw["pc"]), dtype=np.int32, count=n)
    cur_idx = np.fromiter((CUR_TO_IDX[c] for c in raw["cur"]), dtype=np.int8, count=n)
    price = np.array(raw["price"], dtype=np.float64)

    t_dt64 = np.array(raw["et"], dtype="datetime64[s]")
    ing_dt64 = np.array(raw["ing"], dtype="datetime64[s]")
    t_epoch = t_dt64.astype(np.int64)
    ing_epoch = ing_dt64.astype(np.int64)

    order = np.lexsort((t_epoch, pc_idx, sc_idx))
    sc_s = sc_idx[order]
    pc_s = pc_idx[order]
    t_s = t_epoch[order]
    ing_s = ing_epoch[order]
    price_s = price[order]
    cur_s = cur_idx[order]

    is_new = np.empty(n, dtype=bool)
    is_new[0] = True
    is_new[1:] = (sc_s[1:] != sc_s[:-1]) | (pc_s[1:] != pc_s[:-1]) | (t_s[1:] != t_s[:-1])
    dedup_idx = np.flatnonzero(is_new)

    sc_d = sc_s[dedup_idx]
    pc_d = pc_s[dedup_idx]
    t_d = t_s[dedup_idx]
    ing_d = ing_s[dedup_idx]
    price_d = price_s[dedup_idx]
    cur_d = cur_s[dedup_idx]
    usd_d = np.round(price_d * FX_VEC[cur_d], 4)

    day_offset = (t_d - T0_EPOCH) // 86400
    year_arr = CAL_YEAR[day_offset]
    month_arr = CAL_MONTH[day_offset]
    day_arr = CAL_DAY[day_offset]
    quarter_arr = CAL_QUARTER[day_offset]

    return {
        "shop_codes": shop_codes, "prod_codes": prod_codes,
        "raw_count": n, "dedup_count": dedup_idx.size,
        "sc": sc_d, "pc": pc_d, "t": t_d, "ing": ing_d,
        "price": price_d, "cur": cur_d, "usd": usd_d,
        "year": year_arr, "month": month_arr, "day": day_arr, "quarter": quarter_arr,
    }


def enrich_and_group_by_listing(ent, obs):
    """One pass over listing groups (contiguous slices of the (shop,prod,t)
    sorted arrays). Computes as-of tier/category/brand/country per row and
    detects per-listing price-drop events for q14."""
    n = obs["sc"].size
    tier_asof = np.empty(n, dtype=object)
    category_asof = np.empty(n, dtype=object)
    brand_asof = np.empty(n, dtype=object)
    country = np.empty(n, dtype=object)
    product_drops = {}   # product_code -> list of drop epoch times

    sc_codes = obs["shop_codes"]
    pc_codes = obs["prod_codes"]

    sc_d, pc_d, t_d, usd_d = obs["sc"], obs["pc"], obs["t"], obs["usd"]

    pair_start = np.empty(n, dtype=bool)
    pair_start[0] = True
    pair_start[1:] = (sc_d[1:] != sc_d[:-1]) | (pc_d[1:] != pc_d[:-1])
    starts = np.flatnonzero(pair_start)
    ends = np.append(starts[1:], n)

    for start, end in zip(starts, ends):
        sc = sc_codes[sc_d[start]]
        pc = pc_codes[pc_d[start]]
        times_slice = t_d[start:end]

        tt, tv = ent.shop_tier_bp[sc]
        tt_arr = np.array([int(x.timestamp()) for x in tt])
        idx = np.searchsorted(tt_arr, times_slice, side="right") - 1
        tier_asof[start:end] = [tv[i] for i in idx]
        country[start:end] = ent.shop_country[sc]

        ct, cv = ent.prod_category_bp[pc]
        ct_arr = np.array([int(x.timestamp()) for x in ct])
        cidx = np.searchsorted(ct_arr, times_slice, side="right") - 1
        category_asof[start:end] = [cv[i] for i in cidx]

        bt, bv = ent.prod_brand_bp[pc]
        bt_arr = np.array([int(x.timestamp()) for x in bt])
        bidx = np.searchsorted(bt_arr, times_slice, side="right") - 1
        brand_asof[start:end] = [bv[i] for i in bidx]

        usd_slice = usd_d[start:end]
        if usd_slice.size > 1:
            prev = usd_slice[:-1]
            cur = usd_slice[1:]
            drop_mask = cur <= prev * 0.8
            if drop_mask.any():
                drop_times = times_slice[1:][drop_mask]
                product_drops.setdefault(pc, []).extend(int(x) for x in drop_times)

    return tier_asof, category_asof, brand_asof, country, product_drops


def compute_all():
    ent, raw = parse_events()
    obs = build_observation_arrays(raw)
    tier_asof, category_asof, brand_asof, country, product_drops = enrich_and_group_by_listing(ent, obs)

    answers = {}

    # ---- q01: active listings per shop at end of stream --------------------
    active_count = {}
    for (sc, pc), t in ent.listing_discovered.items():
        evs = ent.listing_lifecycle.get((sc, pc), [])
        active = True
        for _, etype in evs:
            active = (etype == "product_relisted")
        if active:
            active_count[sc] = active_count.get(sc, 0) + 1
    rows = sorted(active_count.items())
    answers["q01"] = {"columns": ["shop_code", "active_listings"], "rows": [[sc, c] for sc, c in rows]}

    # ---- q02: latest observation per (shop,product) for top-10 products ---
    sc_codes, pc_codes = obs["shop_codes"], obs["prod_codes"]
    top10_idx = {pc_codes.index(pc) for pc in TOP10_PRODUCTS}
    top10_mask = np.isin(obs["pc"], list(top10_idx))
    latest = {}
    for pc_i, sc_i, t, usd in zip(
        obs["pc"][top10_mask], obs["sc"][top10_mask], obs["t"][top10_mask], obs["usd"][top10_mask]
    ):
        sc, pc = sc_codes[sc_i], pc_codes[pc_i]
        key = (sc, pc)
        t = int(t)
        if key not in latest or t > latest[key][0]:
            latest[key] = (t, float(usd))
    rows = []
    for (sc, pc), (t, usd) in latest.items():
        rows.append([pc, sc, datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), _round4(usd)])
    rows.sort(key=lambda r: (r[0], r[1]))
    answers["q02"] = {"columns": ["product_code", "shop_code", "event_time", "price_usd"], "rows": rows}

    # ---- q03: dedup totals -------------------------------------------------
    cur_counts = {}
    for c in obs["cur"]:
        name = CURRENCIES[c]
        cur_counts[name] = cur_counts.get(name, 0) + 1
    rows = [[c, cur_counts[c]] for c in sorted(cur_counts)]
    rows.append(["ALL", obs["dedup_count"]])
    answers["q03"] = {"columns": ["currency", "observation_count"], "rows": rows}
    assert obs["dedup_count"] != obs["raw_count"], "q03 dedup count must differ from raw line count"
    q03_delta = obs["raw_count"] - obs["dedup_count"]

    # ---- q04: daily min/max/avg for single product over fixed window ------
    win_start = _to_epoch(Q04_WINDOW_START + "T00:00:00Z")
    win_end = win_start + Q04_WINDOW_DAYS * 86400
    pidx = pc_codes.index(Q04_PRODUCT)
    mask = (obs["pc"] == pidx) & (obs["t"] >= win_start) & (obs["t"] < win_end)
    day_vals = {}
    for t, usd in zip(obs["t"][mask], obs["usd"][mask]):
        day = (int(t) - win_start) // 86400
        day_vals.setdefault(day, []).append(float(usd))
    rows = []
    for day in range(Q04_WINDOW_DAYS):
        vals = day_vals.get(day)
        assert vals, f"q04 window has no observations on day {day} -- window is not fully covered"
        d = (datetime.fromtimestamp(win_start, tz=timezone.utc) + timedelta(days=day))
        rows.append([_fmt_date(d), _round4(min(vals)), _round4(max(vals)), _round4(sum(vals) / len(vals))])
    answers["q04"] = {"columns": ["day", "min_price_usd", "max_price_usd", "avg_price_usd"], "rows": rows}

    # ---- q05: avg USD by shop tier as-of, fixed month, + non-degeneracy ---
    mask05 = (obs["year"] == Q05_YEAR) & (obs["month"] == Q05_MONTH)
    tier_sum, tier_cnt = {}, {}
    for tier, usd in zip(tier_asof[mask05], obs["usd"][mask05]):
        tier_sum[tier] = tier_sum.get(tier, 0.0) + float(usd)
        tier_cnt[tier] = tier_cnt.get(tier, 0) + 1
    rows = [[t, _round4(tier_sum[t] / tier_cnt[t])] for t in sorted(tier_sum)]
    answers["q05"] = {"columns": ["tier", "avg_price_usd"], "rows": rows}

    final_tier = {sc: ent.shop_tier_bp[sc][1][-1] for sc in ent.shop_tier_bp}
    final_sum, final_cnt = {}, {}
    for i in np.flatnonzero(mask05):
        sc = sc_codes[obs["sc"][i]]
        t = final_tier[sc]
        final_sum[t] = final_sum.get(t, 0.0) + float(obs["usd"][i])
        final_cnt[t] = final_cnt.get(t, 0) + 1
    final_rows = {t: _round4(final_sum[t] / final_cnt[t]) for t in final_sum}
    asof_rows = {r[0]: r[1] for r in rows}
    q05_delta = {t: (asof_rows.get(t), final_rows.get(t)) for t in set(asof_rows) | set(final_rows)}
    assert asof_rows != final_rows, "q05 as-of tier grouping must differ from final-tier grouping"

    # ---- q06: brand as-of two fixed dates for 3 earliest brand-change products
    d1, d2 = _to_epoch(Q06_D1), _to_epoch(Q06_D2)
    rows = []
    for pc in sorted(Q06_PRODUCTS):
        bt, bv = ent.prod_brand_bp[pc]
        bt_epoch = [int(x.timestamp()) for x in bt]
        b1 = asof(bt_epoch, bv, d1)
        b2 = asof(bt_epoch, bv, d2)
        rows.append([pc, b1, b2])
    answers["q06"] = {"columns": ["product_code", "brand_as_of_d1", "brand_as_of_d2"], "rows": rows}
    assert any(r[1] != r[2] for r in rows), "q06 must show at least one brand change between d1 and d2"

    # ---- q07: shops renamed before cutoff: name as-of cutoff + current name
    cutoff = _to_epoch(Q07_CUTOFF)
    rows = []
    for sc, (nt, nv) in ent.shop_name_bp.items():
        if len(nv) < 2:
            continue
        nt_epoch = [int(x.timestamp()) for x in nt]
        first_rename_epoch = nt_epoch[1]
        if first_rename_epoch < cutoff:
            name_asof = asof(nt_epoch, nv, cutoff)
            rows.append([sc, name_asof, nv[-1]])
    rows.sort(key=lambda r: r[0])
    answers["q07"] = {"columns": ["shop_code", "name_as_of_cutoff", "current_name"], "rows": rows}
    assert rows, "q07 must be non-empty"

    # ---- q08: listings discovered while shop tier as-of was gold -----------
    gold_count = {}
    total_gold = 0
    for (sc, pc), t in ent.listing_discovered.items():
        tt, tv = ent.shop_tier_bp[sc]
        tt_epoch = [int(x.timestamp()) for x in tt]
        tier = asof(tt_epoch, tv, int(t.timestamp()))
        if tier == "gold":
            gold_count[sc] = gold_count.get(sc, 0) + 1
            total_gold += 1
    rows = sorted(gold_count.items())
    rows.append(["TOTAL", total_gold])
    answers["q08"] = {"columns": ["shop_code", "gold_discovered_listings"], "rows": rows}
    assert total_gold > 0, "q08 must be non-empty"

    # ---- q09 / q15: monthly avg price + count by category as-of, 2025 -----
    mask09 = obs["year"] == 2025
    cat_stats = {}
    for m, cat, usd in zip(obs["month"][mask09], category_asof[mask09], obs["usd"][mask09]):
        key = (int(m), cat)
        s, c = cat_stats.get(key, (0.0, 0))
        cat_stats[key] = (s + float(usd), c + 1)
    rows09, rows15 = [], []
    for (m, cat), (s, c) in sorted(cat_stats.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        month_str = _fmt_month(2025, m)
        rows09.append([month_str, cat, _round4(s / c), c])
        rows15.append([month_str, cat, c])
    answers["q09"] = {"columns": ["month", "category", "avg_price_usd", "observation_count"], "rows": rows09}
    answers["q15"] = {"columns": ["month", "category", "observation_count"], "rows": rows15}

    # ---- q10: avg price by (country, tier as-of), 2025 H1 -------------------
    h1_start = _to_epoch("2025-01-01T00:00:00Z")
    h1_end = _to_epoch("2025-07-01T00:00:00Z")
    mask10 = (obs["t"] >= h1_start) & (obs["t"] < h1_end)
    ct_stats = {}
    for cnty, tier, usd in zip(country[mask10], tier_asof[mask10], obs["usd"][mask10]):
        key = (cnty, tier)
        s, c = ct_stats.get(key, (0.0, 0))
        ct_stats[key] = (s + float(usd), c + 1)
    rows = [[cnty, tier, _round4(s / c)] for (cnty, tier), (s, c) in sorted(ct_stats.items())]
    answers["q10"] = {"columns": ["country", "tier", "avg_price_usd"], "rows": rows}

    # ---- q11: top-5 brands by obs count per quarter of 2025, ranked --------
    q_stats = {}
    for q, brand in zip(obs["quarter"][mask09], brand_asof[mask09]):
        key = (int(q), brand)
        q_stats[key] = q_stats.get(key, 0) + 1
    by_quarter = {}
    for (q, brand), cnt in q_stats.items():
        by_quarter.setdefault(q, []).append((brand, cnt))
    rows = []
    for q in sorted(by_quarter):
        ranked = sorted(by_quarter[q], key=lambda bc: (-bc[1], bc[0]))[:5]
        for rank, (brand, cnt) in enumerate(ranked, start=1):
            rows.append([_fmt_quarter(2025, q), rank, brand, cnt])
    answers["q11"] = {"columns": ["quarter", "rank", "brand", "observation_count"], "rows": rows}

    # ---- q12: delisted during 2025, never relisted (as of stream end) -----
    rows = []
    for (sc, pc), evs in ent.listing_lifecycle.items():
        last_delist = None
        active = True
        for t, etype in evs:
            if etype == "product_delisted":
                active = False
                last_delist = t
            else:
                active = True
        if not active and last_delist is not None and last_delist.year == Q12_YEAR:
            rows.append([sc, pc, _fmt_date(last_delist)])
    rows.sort(key=lambda r: (r[0], r[1]))
    answers["q12"] = {"columns": ["shop_code", "product_code", "delisted_date"], "rows": rows}
    assert rows, "q12 must be non-empty"

    # ---- q13a: monthly share of observations with ingest lag > 24h, 2025 --
    lag = obs["ing"] - obs["t"]
    late_mask = lag > 86400
    month_total, month_late = {}, {}
    for m, is_late in zip(obs["month"][mask09], late_mask[mask09]):
        month_total[int(m)] = month_total.get(int(m), 0) + 1
        if is_late:
            month_late[int(m)] = month_late.get(int(m), 0) + 1
    rows = []
    for m in sorted(month_total):
        share = month_late.get(m, 0) / month_total[m]
        rows.append([_fmt_month(2025, m), _round4(share)])
    answers["q13a"] = {"columns": ["month", "late_share"], "rows": rows}

    # ---- q13b: 2025-03 avg price by category as-of, all vs ingest cutoff --
    cutoff13 = _to_epoch(Q13_CUTOFF)
    mask13 = (obs["year"] == Q13_YEAR) & (obs["month"] == Q13_MONTH)
    all_sum, all_cnt = {}, {}
    cut_sum, cut_cnt = {}, {}
    for cat, usd, ing in zip(category_asof[mask13], obs["usd"][mask13], obs["ing"][mask13]):
        all_sum[cat] = all_sum.get(cat, 0.0) + float(usd)
        all_cnt[cat] = all_cnt.get(cat, 0) + 1
        if ing <= cutoff13:
            cut_sum[cat] = cut_sum.get(cat, 0.0) + float(usd)
            cut_cnt[cat] = cut_cnt.get(cat, 0) + 1
    rows = []
    for cat in sorted(all_sum):
        avg_all = _round4(all_sum[cat] / all_cnt[cat])
        avg_cut = _round4(cut_sum[cat] / cut_cnt[cat]) if cut_cnt.get(cat) else None
        rows.append([cat, avg_all, avg_cut])
    answers["q13b"] = {"columns": ["category", "avg_price_usd_all", "avg_price_usd_by_cutoff"], "rows": rows}
    q13b_diff = sum(1 for r in rows if r[2] is not None and abs(r[1] - r[2]) > 1e-6)
    assert q13b_diff > 0, "q13b must show at least one category differing between cutoff and full data"

    # ---- q14: per-client tracked products + price-drop count --------------
    client_products = {}
    client_name = {}
    for c in ent.clients:
        client_products.setdefault(c["client_code"], []).append((c["product_code"], c["tracked_since"]))
        client_name[c["client_code"]] = c["client_name"]
    rows = []
    for client_code in sorted(client_products):
        tracked = client_products[client_code]
        n_tracked = len(tracked)
        drop_total = 0
        for pc, since in tracked:
            since_epoch = _to_epoch(since)
            drops = product_drops.get(pc, [])
            drop_total += sum(1 for t in drops if t >= since_epoch)
        rows.append([client_code, n_tracked, drop_total])
    answers["q14"] = {"columns": ["client_code", "tracked_products", "price_drop_count"], "rows": rows}

    meta = load_meta()
    result = {
        "meta_sha256": meta["sha256"],
        "meta_clients_sha256": meta["clients_sha256"],
        "answers": answers,
        "notes": {
            "raw_obs": obs["raw_count"],
            "dedup_obs": obs["dedup_count"],
            "q03_dedup_delta": q03_delta,
            "q05_asof_vs_final": {k: list(v) for k, v in q05_delta.items()},
            "q08_total_gold": total_gold,
            "q12_count": len(answers["q12"]["rows"]),
            "q13b_categories_differing": q13b_diff,
        },
    }
    return result


def load_or_compute(refresh=False):
    meta = load_meta()
    if not refresh and os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("meta_sha256") == meta["sha256"] and cached.get("meta_clients_sha256") == meta["clients_sha256"]:
            return cached
    result = compute_all()
    with open(CACHE_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    return result


def main():
    ap = argparse.ArgumentParser(description="Compute PriceWatch ground-truth answers")
    ap.add_argument("--q", default=None, help="print only this question key (e.g. q05, q13a)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache, recompute")
    args = ap.parse_args()

    result = load_or_compute(refresh=args.refresh)
    if args.q:
        if args.q not in result["answers"]:
            raise SystemExit(f"unknown question key {args.q!r}; known: {sorted(result['answers'])}")
        print(json.dumps(result["answers"][args.q], indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
