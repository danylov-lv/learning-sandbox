"""Seed the Kupitron marketplace database.

Deterministic (fixed seeds), vectorized generation -> CSV files in data/ ->
COPY into Postgres. Includes a mid-seed ANALYZE, a bulk load of the most
recent 6 months without re-analyzing, and an update-churn phase. All of this
is deliberate: see ../.authoring/notes.md (spoilers) before changing anything.

Usage:
    uv run python seed/generate.py --scale 1.0
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import psycopg
from faker import Faker

MODULE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = MODULE_ROOT / "data"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

SEED = 20260708
DAYS = 548  # 18 months of orders / events
RECENT_DAYS = 183  # phase-2 window loaded after the mid-seed ANALYZE

FAMILIES = [
    "electronics", "apparel", "home", "garden", "toys", "sports",
    "beauty", "auto", "books", "grocery", "office", "pets",
]

BRANDS = [
    "Nexara", "Voltique", "Kordell", "Aurelio", "Trubond", "Zephyra",
    "Mistralon", "Quantevo", "Bravura", "Solmark", "Vantico", "Peakline",
    "Ferroway", "Lumidra", "Castevo", "Nordwyn", "Ozentra", "Palmyro",
    "Rivetta", "Skandia", "Tessoro", "Umbrelo", "Verdano", "Wexford",
    "Xylenta", "Ybarra", "Zenkora", "Altivo", "Brontex", "Cindral",
    "Dorvana", "Elmarra", "Fjordis", "Grantero", "Helvique", "Ivoretta",
    "Jolvane", "Krontal", "Lorvina", "Morvath",
]

ADJECTIVES = [
    "Classic", "Premium", "Compact", "Wireless", "Portable", "Heavy-Duty",
    "Slim", "Ultra", "Eco", "Smart", "Foldable", "Ergonomic", "Vintage",
    "Modular", "Waterproof", "Cordless", "Deluxe", "Essential", "Pro",
    "Reinforced", "Lightweight", "Insulated", "Adjustable", "Universal",
    "Magnetic", "Rechargeable", "Titanium", "Ceramic", "Bamboo", "Carbon",
]
# "Titanium" is the planted ILIKE search term; keep it rare.
ADJ_WEIGHTS = np.array([1.0] * len(ADJECTIVES))
ADJ_WEIGHTS[ADJECTIVES.index("Titanium")] = 0.18

NOUNS = [
    "Headphones", "Speaker", "Kettle", "Backpack", "Jacket", "Sneakers",
    "Desk Lamp", "Monitor Stand", "Blender", "Drill", "Tent", "Yoga Mat",
    "Notebook", "Office Chair", "Dog Bed", "Cat Tower", "Car Charger",
    "Power Bank", "Keyboard", "Mouse", "Water Bottle", "Thermos",
    "Frying Pan", "Knife Set", "Bookshelf", "Curtains", "Rug", "Planter",
    "Trimmer", "Helmet", "Gloves", "Scarf", "Sunglasses", "Watch Strap",
    "Router", "Webcam", "Microphone", "Tripod", "Toolbox", "Ladder",
]

COLORS = [
    "black", "white", "silver", "gray", "red", "blue", "green", "yellow",
    "orange", "purple", "pink", "brown", "beige", "navy", "teal", "olive",
]

COUNTRIES = ["US", "DE", "GB", "FR", "PL", "UA", "ES", "IT", "NL", "CZ"]
COUNTRY_W = np.array([0.28, 0.14, 0.12, 0.10, 0.09, 0.08, 0.06, 0.06, 0.04, 0.03])

SELLER_TIERS = ["basic", "silver", "gold", "platinum"]
TIER_W = np.array([0.80, 0.15, 0.04, 0.01])

# order status mix differs between "old" and "recent" orders on purpose:
# the mid-seed ANALYZE only ever sees the old mix (defect g).
ORDER_STATUSES = ["pending", "paid", "processing", "shipped", "delivered", "cancelled", "refunded"]
STATUS_W_OLD = np.array([0.01, 0.02, 0.02, 0.04, 0.78, 0.08, 0.05])
STATUS_W_RECENT = np.array([0.10, 0.15, 0.12, 0.20, 0.35, 0.06, 0.02])

PAYMENT_STATUSES = ["captured", "pending", "failed", "refunded"]
PAY_W = np.array([0.80, 0.12, 0.05, 0.03])

EVENT_TYPES = ["sale", "restock", "return", "adjustment", "correction"]
EVENT_W = np.array([0.55, 0.20, 0.08, 0.10, 0.07])

FAMILY_EXTRA_KEY = {
    "electronics": "warranty_months",
    "apparel": "size",
    "home": "material",
    "garden": "material",
    "toys": "age_min",
    "sports": "size",
    "beauty": "volume_ml",
    "auto": "warranty_months",
    "books": "pages",
    "grocery": "volume_ml",
    "office": "material",
    "pets": "age_min",
}
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
MATERIALS = ["steel", "wood", "plastic", "cotton", "glass", "bamboo"]

_T0 = time.time()


def log(msg):
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


def conninfo():
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '54302')} "
        f"dbname={os.environ.get('PGDATABASE', 'sandbox')} "
        f"user={os.environ.get('PGUSER', 'sandbox')} "
        f"password={os.environ.get('PGPASSWORD', 'sandbox')}"
    )


def zipf_ids(rng, a, n, size):
    s = rng.zipf(a, size=size).astype(np.int64)
    return ((s - 1) % n) + 1


def day_weights_orders(end_date):
    month_f = {1: 0.75, 2: 0.80, 3: 0.90, 4: 0.95, 5: 1.00, 6: 1.00,
               7: 0.95, 8: 0.90, 9: 1.05, 10: 1.15, 11: 1.80, 12: 2.10}
    dow_f = [1.00, 0.95, 0.95, 1.00, 1.10, 1.25, 1.15]
    trend = np.linspace(0.7, 1.6, DAYS)
    w = np.empty(DAYS)
    for i in range(DAYS):
        d = end_date - timedelta(days=DAYS - 1 - i)
        w[i] = trend[i] * month_f[d.month] * dow_f[d.weekday()]
    return w / w.sum()


HOUR_W = np.array([
    0.6, 0.4, 0.3, 0.2, 0.2, 0.3, 0.6, 1.0, 1.6, 2.2, 2.8, 3.0,
    3.0, 2.9, 2.8, 2.7, 2.8, 3.0, 3.4, 3.8, 4.0, 3.6, 2.6, 1.4,
])
HOUR_P = HOUR_W / HOUR_W.sum()


def sample_timestamps(rng, n, start_epoch, day_p):
    days = rng.choice(len(day_p), size=n, p=day_p).astype(np.int64)
    hours = rng.choice(24, size=n, p=HOUR_P).astype(np.int64)
    secs = rng.integers(0, 3600, size=n, dtype=np.int64)
    return start_epoch + days * 86400 + hours * 3600 + secs


def ts_str(epoch):
    return np.datetime_as_string(epoch.astype("datetime64[s]"), unit="s")


def write_csv(path, columns):
    t0 = time.time()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(zip(*columns))
    log(f"wrote {path.name} ({time.time() - t0:.1f}s)")


def copy_csv(cur, table, cols, path):
    t0 = time.time()
    with open(path, "rb") as f:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)") as cp:
            while chunk := f.read(1 << 20):
                cp.write(chunk)
    log(f"COPY {table} <- {path.name} ({time.time() - t0:.1f}s)")


def main():
    ap = argparse.ArgumentParser(description="Seed the Kupitron database.")
    ap.add_argument("--scale", type=float, default=float(os.environ.get("SCALE", "1.0")))
    args = ap.parse_args()
    scale = args.scale

    n_users = max(5000, int(1_000_000 * scale))
    n_sellers = max(300, int(40_000 * scale))
    n_categories = max(150, min(2000, int(2000 * scale)))
    n_products = max(10_000, int(2_000_000 * scale))
    n_orders = max(20_000, int(6_000_000 * scale))
    n_reviews = max(10_000, int(3_000_000 * scale))
    n_inventory = max(30_000, int(9_000_000 * scale))

    log(f"scale={scale}: users={n_users} sellers={n_sellers} categories={n_categories} "
        f"products={n_products} orders={n_orders} reviews={n_reviews} inventory={n_inventory}")

    DATA_DIR.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    fk = Faker()
    Faker.seed(SEED)

    end_dt = datetime.now().replace(minute=0, second=0, microsecond=0)
    end_epoch = int(end_dt.timestamp())
    start_epoch = end_epoch - DAYS * 86400
    cutoff_epoch = end_epoch - RECENT_DAYS * 86400

    # ---------------------------------------------------------------- pools
    first_names = list({fk.first_name() for _ in range(1200)})[:400]
    last_names = list({fk.last_name() for _ in range(1200)})[:400]
    cities = list({fk.city() for _ in range(800)})[:300]
    domains = ["example.com", "mailbox.test", "kupitron-mail.test", "post.test"]
    sentences = [fk.sentence(nb_words=12) for _ in range(300)]
    company_words = list({fk.last_name() for _ in range(600)})[:250]
    suffixes = ["Trade", "Retail", "Goods", "Supply", "Store", "Market", "Outlet", "Depot"]

    # ---------------------------------------------------------------- users
    t = time.time()
    fn_i = rng.integers(0, len(first_names), n_users)
    ln_i = rng.integers(0, len(last_names), n_users)
    dom_i = rng.integers(0, len(domains), n_users)
    user_created = end_epoch - rng.integers(0, 3 * 365 * 86400, n_users, dtype=np.int64)
    emails = [f"{first_names[a]}.{last_names[b]}.{i + 1}@{domains[d]}".lower()
              for i, (a, b, d) in enumerate(zip(fn_i, ln_i, dom_i))]
    names = [f"{first_names[a]} {last_names[b]}" for a, b in zip(fn_i, ln_i)]
    city_i = rng.integers(0, len(cities), n_users)
    country_i = rng.choice(len(COUNTRIES), size=n_users, p=COUNTRY_W)
    write_csv(DATA_DIR / "users.csv", [
        np.arange(1, n_users + 1), emails, names,
        [cities[i] for i in city_i], [COUNTRIES[i] for i in country_i],
        ts_str(user_created),
    ])
    del emails, names
    log(f"users generated ({time.time() - t:.1f}s)")

    # -------------------------------------------------------------- sellers
    w_i = rng.integers(0, len(company_words), n_sellers)
    s_i = rng.integers(0, len(suffixes), n_sellers)
    seller_names = [f"{company_words[a]} {suffixes[b]}" for a, b in zip(w_i, s_i)]
    tiers = rng.choice(len(SELLER_TIERS), size=n_sellers, p=TIER_W)
    ratings = np.clip(rng.normal(4.1, 0.6, n_sellers), 1.0, 5.0).round(2)
    seller_created = end_epoch - rng.integers(0, 3 * 365 * 86400, n_sellers, dtype=np.int64)
    write_csv(DATA_DIR / "sellers.csv", [
        np.arange(1, n_sellers + 1), seller_names,
        [SELLER_TIERS[i] for i in tiers], ratings, ts_str(seller_created),
    ])

    # ----------------------------------------------------------- categories
    n_roots = len(FAMILIES)
    n_l1 = max(30, int(n_categories * 0.15))
    n_l2 = n_categories - n_roots - n_l1
    cat_parent, cat_name, cat_family, cat_depth = [], [], [], []
    for i, fam in enumerate(FAMILIES):
        cat_parent.append("")
        cat_name.append(fam.capitalize())
        cat_family.append(fam)
        cat_depth.append(0)
    for i in range(n_l1):
        p = int(rng.integers(1, n_roots + 1))
        cat_parent.append(p)
        cat_name.append(f"{cat_family[p - 1].capitalize()} {NOUNS[int(rng.integers(0, len(NOUNS)))]} {i}")
        cat_family.append(cat_family[p - 1])
        cat_depth.append(1)
    for i in range(n_l2):
        p = int(rng.integers(n_roots + 1, n_roots + n_l1 + 1))
        cat_parent.append(p)
        cat_name.append(f"{cat_name[p - 1]} / {ADJECTIVES[int(rng.integers(0, len(ADJECTIVES)))]} {i}")
        cat_family.append(cat_family[p - 1])
        cat_depth.append(2)
    write_csv(DATA_DIR / "categories.csv", [
        np.arange(1, n_categories + 1), cat_parent, cat_name, cat_family, cat_depth,
    ])
    cat_family_arr = np.array(cat_family)

    # ------------------------------------------------------------- products
    t = time.time()
    prod_seller = zipf_ids(rng, 1.4, n_sellers, n_products)
    prod_cat = zipf_ids(rng, 1.2, n_categories, n_products)
    brand_i = zipf_ids(rng, 1.3, len(BRANDS), n_products) - 1
    adj_i = rng.choice(len(ADJECTIVES), size=n_products, p=ADJ_WEIGHTS / ADJ_WEIGHTS.sum())
    noun_i = rng.integers(0, len(NOUNS), n_products)
    model_num = rng.integers(100, 999, n_products)
    model_ch = rng.integers(65, 91, n_products)
    price_cents = np.maximum(99, (rng.lognormal(3.4, 1.1, n_products) * 100).astype(np.int64))
    prod_created = end_epoch - rng.integers(0, 2 * 365 * 86400, n_products, dtype=np.int64)

    titles = [f"{BRANDS[b]} {ADJECTIVES[a]} {NOUNS[n]} {chr(c)}-{m}"
              for b, a, n, c, m in zip(brand_i, adj_i, noun_i, model_ch, model_num)]

    color_i = rng.integers(0, len(COLORS), n_products)
    weight_g = np.maximum(10, (rng.lognormal(5.5, 1.2, n_products)).astype(np.int64))
    fam_per_prod = cat_family_arr[prod_cat - 1]
    extra_int = rng.integers(1, 49, n_products)
    size_i = rng.integers(0, len(SIZES), n_products)
    mat_i = rng.integers(0, len(MATERIALS), n_products)

    def attrs_json(i):
        fam = fam_per_prod[i]
        key = FAMILY_EXTRA_KEY[fam]
        if key == "size":
            val = f'"{SIZES[size_i[i]]}"'
        elif key == "material":
            val = f'"{MATERIALS[mat_i[i]]}"'
        elif key == "pages":
            val = str(int(extra_int[i]) * 12)
        elif key == "volume_ml":
            val = str(int(extra_int[i]) * 25)
        else:
            val = str(int(extra_int[i]))
        return (f'{{"brand": "{BRANDS[brand_i[i]]}", "color": "{COLORS[color_i[i]]}", '
                f'"weight_g": {weight_g[i]}, "{key}": {val}}}')

    attrs = [attrs_json(i) for i in range(n_products)]
    write_csv(DATA_DIR / "products.csv", [
        np.arange(1, n_products + 1), prod_seller, prod_cat, titles,
        (price_cents / 100).round(2), attrs, ts_str(prod_created),
    ])
    del titles, attrs
    log(f"products generated ({time.time() - t:.1f}s)")

    # --------------------------------------------------------------- orders
    t = time.time()
    day_p = day_weights_orders(end_dt)
    order_epoch = np.sort(sample_timestamps(rng, n_orders, start_epoch, day_p))
    order_user = zipf_ids(rng, 1.6, n_users, n_orders)
    recent_mask = order_epoch >= cutoff_epoch
    status_i = np.where(
        recent_mask,
        rng.choice(len(ORDER_STATUSES), size=n_orders, p=STATUS_W_RECENT),
        rng.choice(len(ORDER_STATUSES), size=n_orders, p=STATUS_W_OLD),
    )
    order_status = np.array(ORDER_STATUSES)[status_i]

    # ---------------------------------------------------------- order_items
    item_counts = np.clip(rng.geometric(0.43, n_orders), 1, 8).astype(np.int64)
    n_items = int(item_counts.sum())
    item_order = np.repeat(np.arange(1, n_orders + 1), item_counts)
    item_product = zipf_ids(rng, 1.35, n_products, n_items)
    item_qty = np.clip(rng.geometric(0.6, n_items), 1, 5).astype(np.int64)
    discount = rng.uniform(0.85, 1.0, n_items)
    item_price = ((price_cents[item_product - 1] * discount) / 100).round(2)

    offsets = np.concatenate(([0], np.cumsum(item_counts)[:-1]))
    order_total = np.add.reduceat(item_qty * item_price, offsets).round(2)

    order_split = int(np.searchsorted(order_epoch, cutoff_epoch))
    item_split = int(np.searchsorted(item_order, order_split + 1))
    log(f"orders: {n_orders} total, {n_orders - order_split} in last {RECENT_DAYS} days; "
        f"order_items: {n_items}")

    order_ts = ts_str(order_epoch)
    write_csv(DATA_DIR / "orders_old.csv", [
        np.arange(1, order_split + 1), order_user[:order_split],
        order_status[:order_split], order_total[:order_split], order_ts[:order_split],
    ])
    write_csv(DATA_DIR / "orders_recent.csv", [
        np.arange(order_split + 1, n_orders + 1), order_user[order_split:],
        order_status[order_split:], order_total[order_split:], order_ts[order_split:],
    ])
    write_csv(DATA_DIR / "order_items_old.csv", [
        np.arange(1, item_split + 1), item_order[:item_split],
        item_product[:item_split], item_qty[:item_split], item_price[:item_split],
    ])
    write_csv(DATA_DIR / "order_items_recent.csv", [
        np.arange(item_split + 1, n_items + 1), item_order[item_split:],
        item_product[item_split:], item_qty[item_split:], item_price[item_split:],
    ])
    del item_order, item_product, item_qty, item_price, discount
    log(f"orders + items generated ({time.time() - t:.1f}s)")

    # ------------------------------------------------------------- payments
    t = time.time()
    paid_mask = order_status != "pending"
    pay_order = np.arange(1, n_orders + 1)[paid_mask]
    n_pay = len(pay_order)
    pay_status_i = rng.choice(len(PAYMENT_STATUSES), size=n_pay, p=PAY_W)
    pay_amount = order_total[paid_mask]
    pay_epoch = order_epoch[paid_mask] + rng.integers(60, 86400, n_pay, dtype=np.int64)
    raw = rng.integers(0, 256, size=(n_pay, 16), dtype=np.uint8)
    hx = raw.tobytes().hex()
    refs = [f"{hx[i:i+8]}-{hx[i+8:i+12]}-{hx[i+12:i+16]}-{hx[i+16:i+20]}-{hx[i+20:i+32]}"
            for i in range(0, n_pay * 32, 32)]
    pay_split = int(np.searchsorted(pay_order, order_split + 1))
    pay_ts = ts_str(pay_epoch)
    pay_status = np.array(PAYMENT_STATUSES)[pay_status_i]
    write_csv(DATA_DIR / "payments_old.csv", [
        np.arange(1, pay_split + 1), pay_order[:pay_split], refs[:pay_split],
        pay_amount[:pay_split], pay_status[:pay_split], pay_ts[:pay_split],
    ])
    write_csv(DATA_DIR / "payments_recent.csv", [
        np.arange(pay_split + 1, n_pay + 1), pay_order[pay_split:], refs[pay_split:],
        pay_amount[pay_split:], pay_status[pay_split:], pay_ts[pay_split:],
    ])
    del refs, pay_order, pay_amount, pay_status, pay_ts
    log(f"payments generated: {n_pay} ({time.time() - t:.1f}s)")

    # -------------------------------------------------------------- reviews
    t = time.time()
    rev_product = zipf_ids(rng, 1.4, n_products, n_reviews)
    rev_user = rng.integers(1, n_users + 1, n_reviews)
    rev_rating = rng.choice([1, 2, 3, 4, 5], size=n_reviews, p=[0.12, 0.06, 0.10, 0.24, 0.48])
    rev_day_w = np.linspace(0.5, 1.5, DAYS)
    rev_epoch = sample_timestamps(rng, n_reviews, start_epoch, rev_day_w / rev_day_w.sum())
    sent_i = rng.integers(0, len(sentences), size=(n_reviews, 3))
    sent_n = rng.choice([1, 2, 3], size=n_reviews, p=[0.35, 0.4, 0.25])
    texts = [" ".join(sentences[sent_i[i, j]] for j in range(sent_n[i])) for i in range(n_reviews)]
    write_csv(DATA_DIR / "reviews.csv", [
        np.arange(1, n_reviews + 1), rev_product, rev_user, rev_rating,
        texts, ts_str(rev_epoch),
    ])
    del texts, rev_product, rev_user
    log(f"reviews generated ({time.time() - t:.1f}s)")

    # ----------------------------------------------------- inventory_events
    t = time.time()
    inv_day_w = ((np.arange(1, DAYS + 1) / DAYS) ** 2.2)
    inv_epoch = np.sort(sample_timestamps(rng, n_inventory, start_epoch, inv_day_w / inv_day_w.sum()))
    inv_product = zipf_ids(rng, 1.35, n_products, n_inventory)
    inv_type_i = rng.choice(len(EVENT_TYPES), size=n_inventory, p=EVENT_W)
    qty = np.select(
        [inv_type_i == 0, inv_type_i == 1, inv_type_i == 2, inv_type_i == 3, inv_type_i == 4],
        [-rng.integers(1, 6, n_inventory), rng.integers(20, 200, n_inventory),
         rng.integers(1, 4, n_inventory), rng.integers(-10, 11, n_inventory),
         rng.integers(-5, 6, n_inventory)],
    ).astype(np.int64)
    inv_split = int(np.searchsorted(inv_epoch, cutoff_epoch))
    inv_type = np.array(EVENT_TYPES)[inv_type_i]
    inv_ts = ts_str(inv_epoch)
    write_csv(DATA_DIR / "inventory_events_old.csv", [
        np.arange(1, inv_split + 1), inv_product[:inv_split], inv_type[:inv_split],
        qty[:inv_split], inv_ts[:inv_split],
    ])
    write_csv(DATA_DIR / "inventory_events_recent.csv", [
        np.arange(inv_split + 1, n_inventory + 1), inv_product[inv_split:], inv_type[inv_split:],
        qty[inv_split:], inv_ts[inv_split:],
    ])
    del inv_product, inv_type, inv_ts, qty
    log(f"inventory_events generated ({time.time() - t:.1f}s)")

    # ----------------------------------------------------------------- load
    log("connecting to Postgres...")
    with psycopg.connect(conninfo(), autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("SET synchronous_commit = off")

        log("applying schema.sql")
        cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

        copy_csv(cur, "users", "id, email, full_name, city, country, created_at", DATA_DIR / "users.csv")
        copy_csv(cur, "sellers", "id, name, tier, rating, created_at", DATA_DIR / "sellers.csv")
        copy_csv(cur, "categories", "id, parent_id, name, family, depth", DATA_DIR / "categories.csv")
        copy_csv(cur, "products", "id, seller_id, category_id, title, price, attrs, created_at", DATA_DIR / "products.csv")
        copy_csv(cur, "reviews", "id, product_id, user_id, rating, review_text, created_at", DATA_DIR / "reviews.csv")

        # phase 1: everything older than the recent window
        copy_csv(cur, "orders", "id, user_id, status, total_amount, created_at", DATA_DIR / "orders_old.csv")
        copy_csv(cur, "order_items", "id, order_id, product_id, quantity, unit_price", DATA_DIR / "order_items_old.csv")
        copy_csv(cur, "payments", "id, order_id, external_ref, amount, status, created_at", DATA_DIR / "payments_old.csv")
        copy_csv(cur, "inventory_events", "id, product_id, event_type, qty_delta, occurred_at", DATA_DIR / "inventory_events_old.csv")

        t = time.time()
        cur.execute("ANALYZE")
        log(f"mid-seed ANALYZE done ({time.time() - t:.1f}s) — recent data is loaded AFTER this on purpose")

        # phase 2: last 6 months, bulk-loaded with no re-ANALYZE (defect g)
        copy_csv(cur, "orders", "id, user_id, status, total_amount, created_at", DATA_DIR / "orders_recent.csv")
        copy_csv(cur, "order_items", "id, order_id, product_id, quantity, unit_price", DATA_DIR / "order_items_recent.csv")
        copy_csv(cur, "payments", "id, order_id, external_ref, amount, status, created_at", DATA_DIR / "payments_recent.csv")
        copy_csv(cur, "inventory_events", "id, product_id, event_type, qty_delta, occurred_at", DATA_DIR / "inventory_events_recent.csv")

        # churn phase: months of status transitions compressed into one pass.
        # autovacuum is disabled on these tables (schema), so dead tuples stay.
        log("churn phase (mass UPDATEs, defect f)...")
        churn = [
            ("orders", "UPDATE orders SET status = 'delivered' WHERE status = 'shipped' AND id % 2 = 0"),
            ("orders", "UPDATE orders SET status = 'shipped' WHERE status = 'processing' AND id % 3 <> 0"),
            ("orders", "UPDATE orders SET status = 'paid' WHERE status = 'pending' AND id % 5 < 2"),
            ("payments", "UPDATE payments SET status = 'captured' WHERE status = 'pending' AND id % 3 <> 0"),
            ("payments", "UPDATE payments SET status = 'refunded' WHERE id % 41 = 7"),
            ("inventory_events",
             "UPDATE inventory_events SET occurred_at = occurred_at - interval '90 minutes' "
             "WHERE event_type = 'adjustment' AND id % 2 = 0"),
        ]
        for table, sql in churn:
            t = time.time()
            cur.execute(sql)
            log(f"churn {table}: {cur.rowcount} rows ({time.time() - t:.1f}s)")

        for table in ["users", "sellers", "categories", "products", "orders",
                      "order_items", "reviews", "payments", "inventory_events"]:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
            )

        cur.execute("""
            SELECT relname, n_live_tup, n_dead_tup,
                   pg_size_pretty(pg_total_relation_size(relid))
            FROM pg_stat_user_tables ORDER BY relname
        """)
        log("table stats (live / dead / total size incl. indexes):")
        for r in cur.fetchall():
            log(f"  {r[0]:<18} live={r[1]:>10} dead={r[2]:>9} size={r[3]}")
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        log(f"database size: {cur.fetchone()[0]}")

    log("seed complete")


if __name__ == "__main__":
    main()
