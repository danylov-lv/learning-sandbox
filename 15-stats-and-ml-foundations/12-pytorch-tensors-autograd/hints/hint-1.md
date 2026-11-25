Start with `autograd_gradient` and `numerical_gradient` before touching
`fit_linear_regression` -- they're independent of each other and of the
training loop, and getting them right first gives you a trustworthy tool
(`numerical_gradient`) for sanity-checking the harder function later if
something in the training loop looks off.

The core idea behind autograd: it only records operations on tensors that
have `requires_grad=True` (or that were produced by an operation on such a
tensor). If you build `x` from `x0` without setting `requires_grad=True`,
or if you convert `x` to a plain float/numpy value partway through `f` (a
`.item()` call, a numpy operation), the graph breaks there and `.backward()`
has nothing to walk back through -- `x.grad` stays `None`.

`.backward()` doesn't return the gradient -- it's a side-effecting call
that fills in `.grad` on every leaf tensor the output depended on. Read
that as: call it, then go look at `x.grad` separately, don't expect
`.backward()`'s return value to be useful here.

Once you have both functions working, run them against each other by hand
on something you can verify without a computer, like `f(x) = sum(x)`
(gradient is a vector of all ones) -- if `autograd_gradient` and
`numerical_gradient` don't roughly agree with that trivial case, you have a
bug before you even get to the validator's less-trivial test functions.
