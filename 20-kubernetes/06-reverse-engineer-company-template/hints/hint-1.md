# Hint 1

Don't start writing `ANALYSIS.md` from the top. Start by rendering the
chart twice -- `helm template . ` from inside `given/company-chart` with
no values, then again with `-f values-example.yaml` -- and diff the two
outputs. Whatever changes between those two renders is exactly what a
team controls by filling in their values file; whatever stays the same
no matter what a team writes is a template-level decision, not a
values-level one. That distinction matters for "Questionable decisions"
later: a bad default a team can override in their own values file is a
very different finding from a bad decision baked into the template with
no values knob to escape it at all.

Read `_helpers.tpl` end to end before any other template file. Every
other file in `templates/` calls into it constantly (`include
"svc-platform.xxx"`), so you'll otherwise be re-deriving what a helper
does from its call sites one at a time instead of once, up front.
