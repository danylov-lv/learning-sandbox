"""Validator for 14-stats-and-ml-foundations task 03 -- matplotlib-fundamentals.

Checks the DASHBOARD STRUCTURE, not its visual quality:

  1. `build_dashboard(load_observations())` returns `(fig, facts)`; `fig` is
     a matplotlib Figure with drawn content (`require_figure`) and EXACTLY
     4 Axes (a 2x2 grid).
  2. Every one of the 4 Axes has a non-empty title, xlabel, and ylabel; the
     figure itself has a non-empty suptitle.
  3. `facts` has all 4 required keys, and each value matches an
     independently recomputed reference: `n_boxplot_categories` against the
     dataset's distinct category count (8), `price_axis_is_log` against
     whether any Axes on the figure actually has `get_xscale() == "log"`,
     `n_source_sites` against the dataset's distinct `source_site` count
     (3), `n_days_plotted` against the distinct `scraped_at` date count.

Visual correctness -- is the histogram actually readable, are the boxes
sensibly ordered, does the line chart look like a time series, is the bar
chart properly labeled -- is NOT machine-checkable and is not attempted
here. That part is a human (you) check; see this task's README.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, load_observations, not_passed, passed, require_figure  # noqa: E402
from src.plots import build_dashboard  # noqa: E402

REQUIRED_FACT_KEYS = [
    "n_boxplot_categories",
    "price_axis_is_log",
    "n_days_plotted",
    "n_source_sites",
]


@guarded
def main():
    df = load_observations()

    result = build_dashboard(df)
    if not isinstance(result, tuple) or len(result) != 2:
        not_passed(
            f"build_dashboard must return a (fig, facts) tuple, got "
            f"{type(result).__name__}"
        )
    fig, facts = result

    ok, msg = require_figure(fig, min_axes=4)
    if not ok:
        not_passed(msg)

    axes = fig.get_axes()
    if len(axes) != 4:
        not_passed(
            f"expected exactly 4 axes (a 2x2 grid), got {len(axes)} -- "
            f"the task calls for one figure with exactly 4 panels"
        )

    # --- labeling discipline: every axis needs title + xlabel + ylabel ---
    for i, ax in enumerate(axes):
        title = (ax.get_title() or "").strip()
        xlabel = (ax.get_xlabel() or "").strip()
        ylabel = (ax.get_ylabel() or "").strip()
        if not title:
            not_passed(f"axes[{i}] has no title -- every panel must document what it shows")
        if not xlabel:
            not_passed(f"axes[{i}] (title={title!r}) has no xlabel")
        if not ylabel:
            not_passed(f"axes[{i}] (title={title!r}) has no ylabel")

    suptitle = fig.get_suptitle().strip()
    if not suptitle:
        not_passed("figure has no suptitle -- add fig.suptitle('...') describing the dashboard")

    # --- facts dict shape ---------------------------------------------------
    if not isinstance(facts, dict):
        not_passed(f"build_dashboard must return facts as a dict, got {type(facts).__name__}")

    missing = [k for k in REQUIRED_FACT_KEYS if k not in facts]
    if missing:
        not_passed(f"facts dict missing key(s): {missing}")

    # --- facts vs. independently recomputed reference values ---------------
    expected_categories = int(df["category"].nunique())
    try:
        got_categories = int(facts["n_boxplot_categories"])
    except (TypeError, ValueError):
        not_passed(f"facts['n_boxplot_categories'] is not an int-like value: {facts['n_boxplot_categories']!r}")
    if got_categories != expected_categories:
        not_passed(
            f"facts['n_boxplot_categories'] = {got_categories}, expected "
            f"{expected_categories} (distinct df['category'] values -- panel 2 "
            f"should have one box per category)"
        )

    if not bool(facts["price_axis_is_log"]):
        not_passed(
            f"facts['price_axis_is_log'] must be truthy (True), got "
            f"{facts['price_axis_is_log']!r} -- the price histogram panel's x-axis "
            f"must be log-scaled"
        )
    log_axes = [ax for ax in axes if ax.get_xscale() == "log"]
    if not log_axes:
        not_passed(
            "facts['price_axis_is_log'] is True but no panel's Axes actually has a "
            "log x-scale (ax.get_xscale() != 'log' on all 4 axes) -- call "
            "ax.set_xscale('log') on the price histogram panel"
        )

    expected_sites = int(df["source_site"].nunique())
    try:
        got_sites = int(facts["n_source_sites"])
    except (TypeError, ValueError):
        not_passed(f"facts['n_source_sites'] is not an int-like value: {facts['n_source_sites']!r}")
    if got_sites != expected_sites:
        not_passed(
            f"facts['n_source_sites'] = {got_sites}, expected {expected_sites} "
            f"(distinct df['source_site'] values -- panel 4 should have one bar per site)"
        )

    expected_days = int(df["scraped_at"].dt.date.nunique())
    try:
        got_days = int(facts["n_days_plotted"])
    except (TypeError, ValueError):
        not_passed(f"facts['n_days_plotted'] is not an int-like value: {facts['n_days_plotted']!r}")
    if got_days != expected_days:
        not_passed(
            f"facts['n_days_plotted'] = {got_days}, expected {expected_days} "
            f"(distinct scraped_at dates in the dataset -- panel 3's time series "
            f"should cover the full window)"
        )

    passed(
        f"4-panel dashboard ok: {expected_categories} boxplot categories, "
        f"log-scaled price axis, {expected_sites} source sites, {expected_days} "
        f"days plotted. Visual quality (label wording, readability, chart choice "
        f"per panel) is your own human check -- see README."
    )


if __name__ == "__main__":
    main()
