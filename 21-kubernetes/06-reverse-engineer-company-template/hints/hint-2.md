# Hint 2

For "Every decision explained," go file by file and, for each one, ask
two questions: what would a `kubectl get`/`describe` of the rendered
object look like, and what would visibly break (not just "be worse") if
this file were deleted from `templates/` entirely? A ConfigMap you can't
explain the deletion consequence of is a ConfigMap you haven't actually
understood yet.

For "Questionable decisions," the chart's comments are not neutral --
some of them describe what a piece of code is *supposed* to do, not
what it verifiably *does*. Where a comment in `values.yaml` or
`_helpers.tpl` makes a factual claim about behavior, check that claim
against the actual template logic rather than trusting the prose. Also
worth tracing concretely: what a Secret's `envFrom` reference means for
which components are affected when that Secret's contents change, and
what (if anything) forces a pod restart when a ConfigMap or Secret a
Deployment references gets edited without the Deployment's own spec
changing.
