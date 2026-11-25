import argparse
import csv
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
HEADER = ("source", "sku", "version", "cents")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate two reproducible, overlapping PriceWatch batches.")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    args = parser.parse_args()

    scale = float(os.environ.get("SCALE", "1.0"))
    if not np.isfinite(scale) or scale <= 0:
        parser.error("SCALE must be finite and positive")
    count = max(20, round(1000 * scale))
    rng = np.random.default_rng(42)
    sources = rng.choice(("market", "outlet", "direct"), count, p=(0.60, 0.30, 0.10))
    products = rng.choice(("a", "b", "c", "d"), count, p=(0.55, 0.25, 0.15, 0.05))
    prices = np.maximum(1, rng.lognormal(7, 0.7, count).round().astype(int))
    events = list(zip(sources, products, range(1, count + 1), prices, strict=True))

    args.output.mkdir(parents=True, exist_ok=True)
    for name, start, stop in (("batch-a", 0, 3 * count // 5), ("batch-b", 2 * count // 5, count)):
        batch = events[start:stop] + events[start:stop:11]
        with (args.output / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            writer.writerows(batch[index] for index in rng.permutation(len(batch)))


if __name__ == "__main__":
    main()
