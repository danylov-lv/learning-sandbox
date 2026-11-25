If the validator says your autograd/numerical gradients don't match the
analytic reference, check these in order:

1. **Is the tensor you call `.backward()` from actually a scalar?** For
   `autograd_gradient`, `f(x)` must reduce to a single number
   (`torch.sum(...)`, not an elementwise result). If `f` itself already
   does the reduction (as all three of the validator's test functions do),
   you don't need to sum anything yourself -- just don't accidentally
   return an intermediate, non-reduced tensor from inside your own testing.
2. **Is `x` a leaf tensor with `requires_grad=True` set at construction,
   not after?** `torch.tensor(x0, requires_grad=True)` is correct;
   converting `x0` to a tensor first and calling `.requires_grad_(True)`
   on it afterward also works, but building `x` from another tensor that
   already required grad (e.g. slicing or reshaping a tensor that had
   `requires_grad=True`) makes `x` a non-leaf, and non-leaf tensors don't
   populate `.grad` unless you explicitly call `.retain_grad()` on them.
3. **In `numerical_gradient`, are you perturbing one coordinate at a
   time and holding the rest fixed?** The central-difference formula is
   per-coordinate: for each `i`, only `x0[i]` moves by `+-eps`; every other
   coordinate stays exactly as given. A common bug is perturbing the whole
   vector by `eps` at once, which computes a directional derivative along
   `[1, 1, ..., 1]`, not the gradient.
4. **Did you forget `.detach()` before `.numpy()`?** A tensor with
   `requires_grad=True` (or one that's part of a live graph) raises on
   `.numpy()` directly -- `x.grad` itself does not require grad (it's a
   plain leaf-adjacent tensor) so `x.grad.numpy()` is usually fine as-is,
   but if you're converting `x` (not `x.grad`) anywhere, you'll need
   `.detach().numpy()`.

If `fit_linear_regression`'s weights land far from the closed-form OLS
solution even after `n_steps` in the hundreds, check whether the loss is
actually decreasing (print `loss_history[0]` and `loss_history[-1]`
directly). If the loss is flat or barely moving, the learning rate is
likely too small, or gradients aren't being zeroed (so later updates are
corrupted by earlier steps' leftover gradient) -- print `w.grad` right
after `.backward()` on the first two steps and check it isn't roughly
double what you'd expect on the second step compared to the first. If the
loss is exploding toward very large numbers or `nan`, the learning rate is
too large for this dataset -- see the README's suggested range.
