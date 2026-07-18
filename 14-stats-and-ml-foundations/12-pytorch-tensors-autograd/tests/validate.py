"""Validator for 14-stats-and-ml-foundations task 12 --
pytorch-tensors-autograd.

Two independent checks, neither of which touches the shared scraped-price
dataset -- this task trains on a small fixed-seed synthetic dataset
(`src.autograd_intro.toy_dataset`) instead:

1. Autograd correctness: for three scalar functions with known closed-form
   gradients (sum of squares, sum of sines, sum of cubes), checks that the
   learner's `autograd_gradient` agrees with BOTH the learner's own
   `numerical_gradient` (a from-scratch finite-difference check that never
   touches autograd) AND the analytic gradient formula computed directly
   here. Requiring agreement with all three independently sourced values
   means a bug shared between `autograd_gradient` and `numerical_gradient`
   can't hide -- it would still be caught by the analytic comparison.
2. Fit correctness: builds `toy_dataset(seed=0)`, computes the closed-form
   OLS solution independently via `numpy.linalg.lstsq`, calls the
   learner's `fit_linear_regression` with a fixed (lr, n_steps) known to
   converge on this dataset, and checks the learned weights/bias land
   close to the OLS reference and that the loss dropped substantially
   (not just fluctuated near its starting value).

Run from the module root:

    uv run python 12-pytorch-tensors-autograd/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, require_figure  # noqa: E402
from src.autograd_intro import (  # noqa: E402
    autograd_gradient,
    fit_linear_regression,
    make_figure,
    numerical_gradient,
    toy_dataset,
)

# --- autograd-check tolerances --------------------------------------------
# autograd_gradient vs. the closed-form analytic gradient: both are exact
# up to float32 rounding, so this can be tight.
ANALYTIC_ABS_TOL = 1e-3
# autograd_gradient vs. numerical_gradient (central differences, eps=1e-4):
# finite differences at this eps carry float32 round-off on the order of
# ~1e-3 (verified empirically while authoring this task -- the worst-case
# observed gap, on the cubic test function, was ~4e-3), so this tolerance
# is deliberately looser than the analytic one.
NUMERICAL_ABS_TOL = 1e-2

# --- fit-correctness tolerances -------------------------------------------
# lr/n_steps chosen to sit comfortably inside the convergence basin for
# this dataset (verified while authoring: lr up to ~0.8 still converges,
# lr=1.0 diverges; at lr=0.1/n_steps=200 the learned params match the
# closed-form OLS solution to within ~1e-6 in float32 -- these tolerances
# leave three orders of magnitude of headroom).
FIT_LR = 0.1
FIT_N_STEPS = 200
WEIGHT_ABS_TOL = 0.05
BIAS_ABS_TOL = 0.05
# final loss must have dropped to well under this fraction of the initial
# loss (observed ratio while authoring: ~7e-4).
LOSS_DROP_RATIO = 0.1
# no single step's recorded loss may increase by more than this -- allows
# for float32 rounding noise near convergence (observed increases while
# authoring were all < 1e-7) without allowing a genuinely broken update
# rule (e.g. wrong sign, unzeroed gradients) to slip through.
LOSS_INCREASE_SLACK = 1e-3


def analytic_functions():
    """Three (f, x0, analytic_grad_fn) triples with known closed-form
    gradients, independent of anything in src/autograd_intro.py."""
    import numpy as np
    import torch

    def f_sumsq(x):
        return torch.sum(x**2)

    def grad_sumsq(x0):
        return 2 * x0

    def f_sumsin(x):
        return torch.sum(torch.sin(x))

    def grad_sumsin(x0):
        return np.cos(x0)

    def f_sumcube(x):
        return torch.sum(x**3)

    def grad_sumcube(x0):
        return 3 * x0**2

    return [
        ("sum(x**2)", f_sumsq, np.array([0.5, -1.2, 2.0, -0.3]), grad_sumsq),
        ("sum(sin(x))", f_sumsin, np.array([0.1, 1.0, -0.5, 2.5]), grad_sumsin),
        ("sum(x**3)", f_sumcube, np.array([1.0, -0.7, 0.3, 2.1]), grad_sumcube),
    ]


def check_gradient_array(label, got, want, abs_tol):
    import numpy as np

    got = np.asarray(got, dtype=float)
    want = np.asarray(want, dtype=float)
    if got.shape != want.shape:
        return False, f"{label}: shape mismatch, got {got.shape}, want {want.shape}"
    max_err = float(np.max(np.abs(got - want)))
    if max_err > abs_tol:
        return False, f"{label}: max abs error {max_err:.6g} exceeds tolerance {abs_tol:.6g} (got {got}, want {want})"
    return True, f"{label}: max abs error {max_err:.2e} <= {abs_tol:.2e}"


@guarded
def main():
    import numpy as np
    import torch

    torch.manual_seed(0)
    np.random.seed(0)

    # --- 1. autograd correctness -----------------------------------------
    for name, f, x0, analytic_grad_fn in analytic_functions():
        analytic = analytic_grad_fn(x0)

        ag = autograd_gradient(f, x0)
        ok, msg = check_gradient_array(f"autograd_gradient({name}) vs analytic", ag, analytic, ANALYTIC_ABS_TOL)
        if not ok:
            not_passed(msg)

        ng = numerical_gradient(f, x0)
        ok, msg = check_gradient_array(f"numerical_gradient({name}) vs analytic", ng, analytic, NUMERICAL_ABS_TOL)
        if not ok:
            not_passed(msg)

        ok, msg = check_gradient_array(f"autograd_gradient({name}) vs numerical_gradient({name})", ag, ng, NUMERICAL_ABS_TOL)
        if not ok:
            not_passed(msg)

    # --- 2. fit correctness -----------------------------------------------
    X, y, _true_w, _true_b = toy_dataset(seed=0)

    X_np = X.numpy()
    y_np = y.numpy()
    design = np.hstack([X_np, np.ones((X_np.shape[0], 1))])
    ols_sol, *_ = np.linalg.lstsq(design, y_np, rcond=None)
    ols_w, ols_b = ols_sol[:-1], float(ols_sol[-1])

    result = fit_linear_regression(X, y, lr=FIT_LR, n_steps=FIT_N_STEPS)

    if not isinstance(result, dict):
        not_passed(f"fit_linear_regression: expected a dict, got {type(result).__name__}")
    for key in ("weights", "bias", "loss_history"):
        if key not in result:
            not_passed(f"fit_linear_regression: missing key {key!r}")

    weights = np.asarray(result["weights"], dtype=float)
    bias = float(result["bias"])
    loss_history = list(result["loss_history"])

    if weights.shape != ols_w.shape:
        not_passed(f"fit_linear_regression: weights shape {weights.shape}, want {ols_w.shape}")
    if len(loss_history) != FIT_N_STEPS:
        not_passed(f"fit_linear_regression: loss_history has {len(loss_history)} entries, want {FIT_N_STEPS}")

    max_w_err = float(np.max(np.abs(weights - ols_w)))
    if max_w_err > WEIGHT_ABS_TOL:
        not_passed(
            f"fit_linear_regression: max weight error vs closed-form OLS {max_w_err:.6g} "
            f"exceeds tolerance {WEIGHT_ABS_TOL} (learned {weights}, OLS {ols_w})"
        )

    b_err = abs(bias - ols_b)
    if b_err > BIAS_ABS_TOL:
        not_passed(
            f"fit_linear_regression: bias error vs closed-form OLS {b_err:.6g} "
            f"exceeds tolerance {BIAS_ABS_TOL} (learned {bias}, OLS {ols_b})"
        )

    initial_loss = loss_history[0]
    final_loss = loss_history[-1]
    if not (final_loss < LOSS_DROP_RATIO * initial_loss):
        not_passed(
            f"fit_linear_regression: final loss {final_loss:.6g} is not well below "
            f"{LOSS_DROP_RATIO} * initial loss {initial_loss:.6g} -- training does not look converged"
        )

    for i in range(1, len(loss_history)):
        increase = loss_history[i] - loss_history[i - 1]
        if increase > LOSS_INCREASE_SLACK:
            not_passed(
                f"fit_linear_regression: loss_history increased by {increase:.6g} at step {i} "
                f"(from {loss_history[i - 1]:.6g} to {loss_history[i]:.6g}) -- "
                f"loss should decrease monotonically overall (check for unzeroed gradients or a sign error)"
            )

    # --- 3. figure ----------------------------------------------------------
    fig = make_figure(loss_history)
    ok, msg = require_figure(fig, min_axes=1)
    if not ok:
        not_passed(f"make_figure: {msg}")

    passed(
        f"autograd checks 3/3 ok; fit: final_loss={final_loss:.4f} "
        f"(initial={initial_loss:.4f}), max_weight_err={max_w_err:.4f}, bias_err={b_err:.4f}"
    )


if __name__ == "__main__":
    main()
