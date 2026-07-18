# 12 -- PyTorch Tensors and Autograd

## Backstory

For eleven tasks you have been the one computing things by hand: a mean, a
skewness, a bootstrap confidence interval, a confounder. Every one of those
answers came from a formula you understood well enough to derive yourself.
The next stop for this dataset -- and for most "scraped data becomes a
product feature" pipelines -- is handing it to an ML engineer who will
define a *loss function* and let an optimizer walk downhill until that loss
is small, using gradients a framework computed for them, not gradients they
derived by hand.

To reason about what that engineer's code is actually doing -- to know
whether a training run that "isn't converging" is a real bug or just a bad
learning rate, or to spot when a loss curve looks wrong -- you need to have
built the smallest possible version of that loop yourself. This task builds
one: a linear regressor, trained by gradient descent, with PyTorch autograd
computing the gradients you would otherwise have to derive with a pen. No
neural network, no GPU, nothing beyond what's needed to see the four moving
parts underneath every gradient-based model: a computational graph,
`requires_grad`, `.backward()`, and a manual parameter-update loop.

## What's given

- `src/autograd_intro.py`:
  - `toy_dataset(seed=0)` -- **fully implemented, read it, don't modify
    it.** A fixed-seed synthetic dataset: 200 observations, 3 features,
    `y = X @ true_w + true_b + small_noise`. It returns `true_w` / `true_b`
    for context, but they are not what your fit is graded against -- noise
    means even a perfect fit can only recover the data's own closed-form
    ordinary-least-squares (OLS) solution, not the exact generating
    parameters. See the function's docstring for why.
  - Four function stubs (`autograd_gradient`, `numerical_gradient`,
    `fit_linear_regression`, `make_figure`), each with a docstring that
    specifies its exact contract.
- The idea of a finite-difference gradient check (a from-scratch technique
  for verifying an autograd implementation without trusting autograd
  itself) -- the mechanics are yours to write, but `numerical_gradient`'s
  docstring spells out the central-difference formula and why `eps` can't
  be pushed arbitrarily small.

## What's required

Implement all four functions in `src/autograd_intro.py`:

1. `autograd_gradient(f, x0)` -- given a scalar-valued function `f` of a
   1-D torch tensor and a point `x0`, build a leaf tensor with
   `requires_grad=True`, evaluate `f`, call `.backward()`, and return the
   gradient as a numpy array.
2. `numerical_gradient(f, x0, eps=1e-4)` -- the central finite-difference
   gradient at `x0`, computed without touching autograd at all. This is
   your own tool for checking `autograd_gradient`, not a shortcut around
   it.
3. `fit_linear_regression(X, y, lr, n_steps)` -- a manual gradient-descent
   training loop: weights and bias as `requires_grad=True` tensors
   initialized to zero, MSE loss, `.backward()`, a parameter update under
   `torch.no_grad()`, and zeroing the gradients before the next step.
   Returns learned weights, bias, and the per-step loss history.
4. `make_figure(loss_history)` -- the loss curve over training steps.

A note on hyperparameters: `fit_linear_regression` takes `lr` and
`n_steps` as arguments rather than hardcoding them, so you'll need to pick
values while testing. On this dataset (features are i.i.d. standard
normal, so the loss surface is well-conditioned), a learning rate
somewhere in **0.02 to 0.5**, run for **at least 100 steps**, converges
cleanly to the closed-form OLS solution. Push the learning rate too high
(roughly 1.0 or above on this data) and gradient descent diverges instead
of converging -- that's expected behavior, not a bug in your loop, and
worth deliberately triggering once so you recognize what divergence looks
like in a loss curve.

## Completion criteria

From the module root:

```bash
uv run python 12-pytorch-tensors-autograd/tests/validate.py
```

The validator:

- Checks `autograd_gradient` against both your own `numerical_gradient`
  and an independently-computed analytic gradient, for three functions
  with known closed forms (`sum(x**2)`, `sum(sin(x))`, `sum(x**3)`).
  Agreement with all three sources at once means a bug shared between your
  two functions can't hide behind itself.
- Builds `toy_dataset(seed=0)`, computes the closed-form OLS solution
  independently via `numpy.linalg.lstsq`, calls your
  `fit_linear_regression` with a fixed learning rate and step count, and
  checks your learned weights and bias land close to that OLS reference,
  and that the loss dropped substantially (not just wobbled near its
  starting value).
- Confirms `make_figure` returns a real figure with drawn content via
  `require_figure`.

`PASSED` prints the final loss, the initial loss, and the max weight/bias
error against the closed-form solution.

## Estimated evenings

1-2

## Topics to read up on

- Torch tensors vs. numpy arrays -- what a tensor adds (`requires_grad`,
  the autograd graph, GPU dispatch you won't use here) and where they stay
  interchangeable (`.numpy()` / `torch.tensor(...)`)
- The computational graph and autograd -- "define-by-run": how PyTorch
  records operations as they execute rather than requiring a graph
  declared up front
- `requires_grad`, `.backward()`, and `.grad` -- what makes a tensor a
  leaf, why `.grad` accumulates across calls instead of resetting, and why
  that's a feature (mini-batch gradient accumulation) as much as it's a
  gotcha here
- Gradient descent and learning rate -- why a step size that's too large
  causes divergence rather than just "slower convergence"
- Mean squared error as a loss function for regression
- Why `zero_grad` (or the equivalent manual `.grad.zero_()`) has to happen
  every step
- Finite-difference gradient checking -- central vs. forward differences,
  and why the step size `eps` has a sweet spot (too large: truncation
  error; too small: floating-point round-off error)
- Closed-form ordinary least squares (the normal equations /
  `numpy.linalg.lstsq`) as the ground truth gradient descent on a linear
  model should converge toward

## Off-limits

`.authoring/design.md` at the module root documents the harness API and
this module's shared dataset -- this task doesn't use that dataset, but the
file also carries spoilers for other tasks. Don't read it before finishing
your current task.
