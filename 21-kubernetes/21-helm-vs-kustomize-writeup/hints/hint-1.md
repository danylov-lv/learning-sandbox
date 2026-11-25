# Hint 1

Don't start writing `COMPARISON.md` from the "Decision" section backward
from a verdict you already hold. Start with `## Mental models` and force
yourself to state the actual pipeline each tool runs: for Helm, trace what
happens between "here's a `values.yaml` and a template file" and "here's
a `kubectl apply`-able object" -- what stage is text, and what stage
first becomes YAML. For Kustomize, trace the same thing: at what point,
if ever, does anything stop being valid YAML. If you can't answer "is
this thing YAML right now" at every stage of both pipelines, the rest of
the writeup will drift into vibes ("Helm feels more powerful") instead of
mechanism.

Then work outward from your own experience: the chart you hand-wrote in
arc 2 and the Argo CD `Application` you wrote by hand in arc 5. Which
specific things about that chart (subchart, hook, `_helpers.tpl` helper)
would have had a direct Kustomize equivalent, and which wouldn't? That's
the raw material for "Where Helm wins" and "Where Kustomize wins" --
don't reach for generic tool-comparison-blog-post points you haven't
actually traced through a concrete case.
