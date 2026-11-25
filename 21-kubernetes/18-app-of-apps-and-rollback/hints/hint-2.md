# Hint 2

For checkpoint 2: the validator's first-run `NOT PASSED` message already
contains the exact bad commit's short sha and the repo it's in --
re-read it rather than guessing. The full flow, once you have that sha:

```bash
kubectl --context kind-sandbox20 -n argocd port-forward svc/gitea-http 3000:3000 &
git clone http://gitea-admin:sandbox20-gitea-admin-pw@127.0.0.1:3000/sandbox20/t18-workload.git
cd t18-workload
git log --oneline
git revert <sha-from-the-validator-message>
git push
```

`git revert` opens your default editor with a pre-filled commit message
(`Revert "BREAK: ..."` plus a `This reverts commit <full-sha>.` line) --
just save and exit, don't delete that second line. The validator greps
the live commit history for exactly that "reverts commit `<sha>`" text at
the tip of `main`; a squashed/reworded commit that removes it, or a
`git reset`/force-push instead of a real revert, won't be found even if
the net effect on `values.yaml` looks the same.

If `git push` asks for credentials interactively instead of using the
ones embedded in the clone URL, double-check you typed the URL exactly as
shown (`gitea-admin:sandbox20-gitea-admin-pw@127.0.0.1:3000`, not
`gitea-http.argocd.svc...` -- that in-cluster DNS name is only for Argo
CD's own `repo-server` pod, not for you cloning from your machine).

After pushing, re-running `tests/validate_cp2.py` triggers Argo CD's sync
itself -- you don't need `argocd app sync` or the UI.
