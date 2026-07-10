# TODO: containerize the loader.
#
# Requirements (the what, not the how):
#   - a python:3.12-slim base
#   - dependencies installed via uv (copy uv in from its official image, or
#     pip-install it — your call), driven by a lockfile, no dev deps
#   - src/loader/loader.py as the entrypoint; one container run = one
#     day's load, then exit 0/1
#   - the day to load comes in as an argument or env var (the CronJob
#     template decides which — keep the two consistent)
#   - think about layer order: dependency install should survive a
#     loader.py edit without re-resolving
#
# FROM ...

# TODO
