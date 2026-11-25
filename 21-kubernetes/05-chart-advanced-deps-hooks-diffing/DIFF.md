# DIFF.md -- helm template diff workflow

Document a real `helm template` diffing session between your `values-dev.yaml`
and `values-prod.yaml` (both files you create under `chart/`, see README.md
"What's required" step 3). Run the commands for real, then report what you
actually saw -- don't reconstruct this from memory.

## Command

[fill in: the exact `helm template` commands you ran for each values file
(redirected to files), and the diff command you ran against the two outputs]

## Differences found

[fill in: the concrete fields that differ between the dev and prod renders --
replicas, resources (requests/limits), and the QUEUE_KEY override, plus
anything else you notice]

## Why each difference exists

[fill in: for each differing field, why that difference makes sense for a
dev environment vs. a prod environment]
