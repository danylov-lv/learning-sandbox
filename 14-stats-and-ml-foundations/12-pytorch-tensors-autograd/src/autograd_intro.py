"""t12 -- PyTorch tensors and autograd, from first principles.

Every task so far in this module handed you a dataset and asked you to
compute something about it by hand: a mean, a confidence interval, a
correlation. An ML engineer downstream of you does something structurally
different -- they define a *loss function* and let an optimizer walk
parameters downhill until that loss is small, using gradients the
framework computes for them. This task builds the smallest possible
version of that: a linear regressor fit by gradient descent, with PyTorch
autograd computing the gradients you would otherwise have to derive with a
pen.

Two things this task is NOT: it is not a deep-learning task (no layers, no
nonlinearity, no GPU), and it is not asking you to beat scikit-learn's
`LinearRegression`. The point is to see the four moving parts underneath
every gradient-based model -- a computational graph, `requires_grad`,
`.backward()`, and a manual parameter-update loop -- on a problem small
enough that you can independently verify every number by hand (finite
differences, closed-form OLS) and know for certain whether your code is
right.

Functions in this file:

  - `toy_dataset(seed=0)` -- FULLY IMPLEMENTED. A fixed-seed synthetic
    linear-regression dataset. Read it; you do not need to modify it.
  - `autograd_gradient(f, x0)` -- YOU IMPLEMENT. Use torch autograd to
    compute the gradient of a scalar-valued function at a point.
  - `numerical_gradient(f, x0, eps=1e-4)` -- YOU IMPLEMENT. Central
    finite-difference gradient, used to independently check
    `autograd_gradient` against a method that never touches autograd at
    all.
  - `fit_linear_regression(X, y, lr, n_steps)` -- YOU IMPLEMENT. A manual
    gradient-descent training loop.
  - `make_figure(loss_history)` -- YOU IMPLEMENT. Plot the loss curve.
"""

import numpy as np
import torch


def toy_dataset(seed: int = 0):
    """Fixed-seed toy linear-regression dataset. FULLY IMPLEMENTED -- read
    this, you do not need to change it.

    Generates `n=200` observations with `d=3` features from a known linear
    model plus small Gaussian noise:

        y = X @ true_w + true_b + noise,   noise ~ N(0, 0.1^2)

    `X`'s features are drawn i.i.d. standard normal, so they are already on
    comparable scales (no separate standardization step is needed before
    fitting -- gradient descent with a single shared learning rate works
    fine directly on this `X`).

    The whole point of returning `true_w` and `true_b` alongside the data
    is that they are NOT what `fit_linear_regression` should be graded
    against -- the noise means the best any estimator can do is recover
    the data's own closed-form ordinary-least-squares (OLS) solution
    (`numpy.linalg.lstsq` on `[X | 1]` against `y`), which will be close
    to but not exactly `(true_w, true_b)`. `fit_linear_regression`'s job
    is to get close to the closed-form OLS solution via gradient descent,
    not to rediscover the (unknowable, in a real scraping pipeline) ground
    truth used to generate the data.

    Args:
        seed: int, RNG seed. `toy_dataset(0)` always returns bit-identical
            data.

    Returns:
        Tuple `(X, y, true_w, true_b)`:
          - X: torch.Tensor, shape (200, 3), dtype float32.
          - y: torch.Tensor, shape (200,), dtype float32.
          - true_w: np.ndarray, shape (3,), the generating weight vector.
          - true_b: float, the generating intercept.
    """
    rng = np.random.default_rng(seed)
    n, d = 200, 3
    true_w = np.array([2.0, -3.0, 0.5])
    true_b = 1.0

    X_np = rng.normal(loc=0.0, scale=1.0, size=(n, d))
    noise = rng.normal(loc=0.0, scale=0.1, size=n)
    y_np = X_np @ true_w + true_b + noise

    X = torch.tensor(X_np, dtype=torch.float32)
    y = torch.tensor(y_np, dtype=torch.float32)
    return X, y, true_w, true_b


def autograd_gradient(f, x0):
    """Compute the gradient of a scalar-valued function at a point, using
    PyTorch autograd.

    Args:
        f: a callable that maps a 1-D torch.Tensor to a 0-D (scalar)
            torch.Tensor -- e.g. `lambda x: torch.sum(x ** 2)`. `f` must be
            built entirely out of differentiable torch operations (no
            `.item()`, no numpy calls inside `f`) so that autograd can
            trace the computational graph from `x` to the output.
        x0: array-like (list, tuple, or np.ndarray) of floats -- the point
            at which to evaluate the gradient.

    Returns:
        np.ndarray, same shape as `x0`, holding df/dx evaluated at `x0`.

    What to do:
        1. Build a LEAF tensor from `x0` with `requires_grad=True`. It must
           be a leaf (created directly from data, not the result of some
           other differentiable operation) -- only leaf tensors accumulate
           gradients into `.grad` by default.
        2. Evaluate `out = f(x)`. This runs `x` through `f`'s operations
           and, because `x.requires_grad` is True, PyTorch records every
           operation into a computational graph as it executes (this is
           what makes autograd "define-by-run" rather than needing a
           separately-declared graph up front).
        3. Call `out.backward()`. This walks the recorded graph backward
           from `out` (which must be a scalar -- a 0-D tensor -- for
           `.backward()` to work without an explicit `gradient=` argument)
           and accumulates d(out)/dx into `x.grad`.
        4. Return `x.grad`, converted to a plain numpy array (detach it
           from the graph first).

    A leaf tensor's `.grad` starts as `None` before any `.backward()` call
    -- if you see an `AttributeError` on `.grad.numpy()` or similar, you
    likely never called `.backward()`, or `requires_grad=True` was never
    set on the tensor you're reading `.grad` from.
    """
    raise NotImplementedError


def numerical_gradient(f, x0, eps=1e-4):
    """Central finite-difference approximation of the gradient of `f` at
    `x0` -- a way to check `autograd_gradient` that never uses autograd at
    all, so an autograd bug can't hide by also being present in your check.

    Args:
        f: same contract as in `autograd_gradient` -- a callable mapping a
            1-D torch.Tensor to a 0-D scalar torch.Tensor.
        x0: array-like of floats, the point to evaluate the gradient at.
        eps: float, the finite-difference step size.

    Returns:
        np.ndarray, same shape as `x0`, the numerically-approximated
        gradient.

    What to do:
        For each coordinate `i` of `x0` independently, perturb only that
        coordinate by `+eps` and by `-eps`, evaluate `f` at both perturbed
        points (as plain torch tensors -- `requires_grad` is irrelevant
        here, you're calling `f` for its *value*, not tracing a graph),
        and use the central-difference formula:

            grad[i] ~= (f(x0 + eps * e_i) - f(x0 - eps * e_i)) / (2 * eps)

        where `e_i` is the i-th standard basis vector. This is the
        standard technique for gradient-checking an autograd
        implementation: central differences are second-order accurate
        (error shrinks with `eps**2`, not `eps`), which is why it's the
        right choice here over a one-sided (forward) difference.

        `eps=1e-4` is a deliberate middle ground: too large and the
        quadratic Taylor-truncation error dominates; too small (below
        roughly `1e-6` at float32 precision) and floating-point round-off
        in `f(x0 + eps) - f(x0 - eps)` dominates instead. Do not tighten
        `eps` chasing more precision -- past a point it makes the estimate
        WORSE, not better.
    """
    raise NotImplementedError


def fit_linear_regression(X, y, lr, n_steps):
    """Fit a linear regression model `y ~= X @ w + b` via manual gradient
    descent, using autograd to compute the gradients of the MSE loss at
    every step -- this is the training loop underneath virtually every
    gradient-based ML model, stripped down to its smallest honest form.

    Args:
        X: torch.Tensor, shape (n, d), the design matrix (as returned by
            `toy_dataset`).
        y: torch.Tensor, shape (n,), the targets.
        lr: float, the learning rate (gradient-descent step size).
        n_steps: int, how many gradient-descent steps to run.

    Returns:
        dict with exactly these three keys:
          - "weights": np.ndarray, shape (d,) -- the learned weight vector.
          - "bias": float -- the learned intercept.
          - "loss_history": list[float], length `n_steps` -- the MSE loss
            recorded at each step, BEFORE that step's parameter update
            (so `loss_history[0]` is the loss under the untrained initial
            parameters, and `loss_history[-1]` is the loss just before the
            LAST update was applied -- it is not the loss of the final
            returned parameters, which will be slightly lower still).

    Initialization: start both `w` and `b` at exactly zero
    (`torch.zeros(..., requires_grad=True)`). This makes the whole
    function deterministic given only `(X, y, lr, n_steps)` -- no separate
    random seed needed for parameter initialization, and it means your run
    and the validator's independent run of your function will always match
    bit-for-bit.

    Loop structure, once per step (see hint-2.md if this needs unpacking):
        1. Forward pass: `pred = X @ w + b`.
        2. Loss: mean squared error, `loss = mean((pred - y) ** 2)`.
        3. Record `loss.item()` into `loss_history` -- BEFORE updating the
           parameters for this step.
        4. Backward pass: `loss.backward()` -- fills `w.grad` and `b.grad`.
        5. Parameter update, wrapped in `with torch.no_grad():` (updating a
           `requires_grad=True` tensor in place is itself a differentiable
           operation as far as autograd is concerned unless you suppress
           that with `no_grad` -- you want the update to be an ordinary
           in-place arithmetic op, not another node added to the graph):
               `w -= lr * w.grad`
               `b -= lr * b.grad`
        6. Zero out `w.grad` and `b.grad` before the next step (e.g.
           `w.grad.zero_()`, or set them to `None`). PyTorch ACCUMULATES
           gradients into `.grad` across multiple `.backward()` calls by
           design (useful for gradient accumulation over mini-batches in
           real training loops) -- if you skip this, step 2's gradient
           adds on top of step 1's, and every update after the first is
           wrong.

    A learning rate that is too large for this dataset will make the loss
    diverge (grow without bound, eventually to `inf` or `nan`) instead of
    decreasing -- if that happens, you have not found a bug, you've found
    the standard failure mode of gradient descent with too big a step
    size. See the README for a starting range of `lr` / `n_steps` values
    that converge cleanly on `toy_dataset`.
    """
    raise NotImplementedError


def make_figure(loss_history):
    """Plot the training loss curve.

    Args:
        loss_history: list[float] (or array-like), the per-step loss
            values returned in `fit_linear_regression`'s output dict.

    Returns:
        matplotlib.figure.Figure with at least one Axes containing actual
        drawn content (a line plot of loss vs. step index). Do not call
        `plt.show()`.

    A gradient-descent loss curve on a convex problem like this one should
    drop steeply for the first several steps and then flatten out as it
    approaches the optimum -- consider a log-scale y-axis
    (`ax.set_yscale("log")`) if the early steep drop makes the flattened
    tail hard to see on a linear scale.
    """
    raise NotImplementedError
