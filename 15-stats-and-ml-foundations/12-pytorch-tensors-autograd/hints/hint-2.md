A training loop, stripped to its essence, is always the same five-beat
cycle, repeated `n_steps` times: **forward -> loss -> backward -> step
(under no_grad) -> zero grads**. `fit_linear_regression` is that cycle with
nothing extra around it.

Forward: `pred = X @ w + b`. This is matrix-vector multiply plus a
broadcast add -- `X` is `(n, d)`, `w` is `(d,)`, so `X @ w` is `(n,)`, and
`b` (a scalar-shaped tensor) broadcasts against it. `pred` ends up shape
`(n,)`, matching `y`.

Loss: `torch.mean((pred - y) ** 2)`. This is a single scalar tensor --
important, because `.backward()` on a non-scalar tensor needs an explicit
`gradient=` argument you don't want to deal with here. If you get a
"grad can be implicitly created only for scalar outputs" error, something
upstream produced a tensor with more than one element where you expected a
scalar.

Backward: `loss.backward()`. After this call, `w.grad` and `b.grad` hold
d(loss)/dw and d(loss)/db -- the same kind of gradient `autograd_gradient`
computes, just now for a loss defined over the whole design matrix instead
of a toy scalar function.

Step, under `torch.no_grad()`:

```python
with torch.no_grad():
    w -= lr * w.grad
    b -= lr * b.grad
```

Why the `no_grad()` block: `w` and `b` have `requires_grad=True`, so an
in-place update like `w -= ...` would otherwise itself be traced as part of
the graph -- you want this line to be a plain arithmetic mutation, not a
new differentiable operation layered on top of the one you just walked
backward through.

Zero the grads before the next iteration -- `w.grad.zero_()` and
`b.grad.zero_()` -- or the next `.backward()` call will ADD to what's
already there instead of replacing it (this is intentional PyTorch
behavior, useful for accumulating gradients across mini-batches in real
training; here, with one full-batch step per iteration, it's purely a
footgun if you forget it). Record `loss.item()` into your history list
*before* the update, not after -- the value you want is "the loss under
the parameters this step started with."

To compare against the closed-form answer: `numpy.linalg.lstsq` on the
design matrix `[X | column_of_ones]` against `y` gives you `[w_ols | b_ols]`
in one call -- that's the target your gradient-descent weights and bias
should land close to after enough steps at a reasonable learning rate.
