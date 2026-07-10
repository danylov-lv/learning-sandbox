# TODO: containerize a consumer-group member.
#
# Requirements (the what, not the how):
#   - a python:3.12-slim base
#   - dependencies installed via uv (copy uv in from its official image, or
#     pip-install it — your call), driven by this module's lockfile, no dev
#     deps
#   - entrypoint runs one of this module's consumer scripts (task 03's
#     src/consumer.py is the natural pick for the rebalance demo this bonus
#     is about, but point it at whichever consumer you want to scale) — a
#     long-running poll loop, not a one-shot job
#   - bootstrap servers / group id / postgres DSN come in as env vars, set
#     by the Deployment template from values.yaml, not baked into the image
#   - handle SIGTERM: a rolling replica-count change sends pods a graceful
#     shutdown signal, and a consumer that doesn't call close() on the way
#     out leaves the group coordinator waiting out the full session timeout
#     before it notices the member is gone (task 03 already made you write
#     this handler — reuse it)
#   - think about layer order: dependency install should survive a
#     consumer.py edit without re-resolving
#
# FROM ...

# TODO
