"""Launches a learner-authored FastAPI app for validators (module 12).

No fixed API port anywhere in this module: every launch binds
`127.0.0.1:0` (OS-assigned ephemeral port), so parallel task runs never
collide on a port the way they would with a hardcoded one. See
.authoring/design.md for the full rationale.

Two launch strategies, both async context managers yielding a `Service`:

- `run_app` -- runs uvicorn.Server IN-PROCESS as an asyncio Task. Cheap,
  fast to tear down, shares this process's event loop. Use this for most
  validators (pagination, caching, rate limiting, JWT auth, SQLi checks).
- `run_app_subprocess` -- launches a REAL separate `python -m uvicorn`
  process. Use this where in-process isn't representative: task 09's load
  test (measuring real HTTP + OS scheduling overhead, not coroutine
  hand-off) and task 04's background worker (which must survive/be
  observable independent of the validator's own event loop).

A third helper, `asgi_client`, skips sockets entirely (httpx's ASGI
transport talks to the app in-memory) for validators that only need to
assert response shape/content and don't care about real network behavior.

Every third-party import (uvicorn, httpx) is lazy inside the function that
needs it; importing this module has zero side effects.
"""

import os
import time
from contextlib import asynccontextmanager


class Service:
    """A running app under test. `base_url` is the real
    "http://127.0.0.1:<port>" the app is listening on."""

    def __init__(self, base_url, port):
        self.base_url = base_url
        self.port = port

    def client(self, **kwargs):
        """httpx.AsyncClient factory bound to this service's base_url. Use as
        `async with service.client() as c: await c.get("/health")`."""
        import httpx

        return httpx.AsyncClient(base_url=self.base_url, **kwargs)


@asynccontextmanager
async def run_app(app_or_import_string, *, host="127.0.0.1", startup_timeout=10.0, **uvicorn_kwargs):
    """Run a FastAPI/ASGI app in-process via uvicorn.Server, bound to an
    ephemeral port.

    Port-binding strategy (deliberate): we bind our OWN `socket` to
    `(host, 0)` first and hand it to `server.serve(sockets=[sock])`, rather
    than letting uvicorn bind port 0 itself and reading the port back off
    `server.servers[0].sockets` afterwards. Binding first means the port is
    known immediately via `sock.getsockname()`, before uvicorn's internal
    server objects exist at all -- no dependency on uvicorn's internal
    `Server.servers` attribute shape across versions. Same rationale as
    module 11's mock peer (see that module's design.md).

    `app_or_import_string` may be an ASGI app object or an "module:attr"
    import string -- uvicorn.Config accepts either.
    """
    import asyncio
    import socket

    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(app_or_import_string, host=host, port=port, log_level="warning", **uvicorn_kwargs)
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve(sockets=[sock]))

    deadline = time.monotonic() + startup_timeout
    try:
        while not server.started:
            if serve_task.done():
                serve_task.result()  # re-raise the startup failure
            if time.monotonic() > deadline:
                raise TimeoutError(f"uvicorn did not start within {startup_timeout}s")
            await asyncio.sleep(0.02)

        yield Service(f"http://{host}:{port}", port)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            serve_task.cancel()


@asynccontextmanager
async def run_app_subprocess(import_string, *, host="127.0.0.1", extra_args=None, env=None, startup_timeout=15.0):
    """Run a FastAPI/ASGI app in a REAL separate process:
    `python -m uvicorn <import_string> --host <host> --port <port>`.

    Port strategy: bind `(host, 0)` ourselves to learn a free port, then
    CLOSE that socket before the child process binds its own listener on the
    same port number. This is a small time-of-check/time-of-use race (another
    process could grab the port in between) -- acceptable for test infra
    where a collision is rare and, if it ever happens, surfaces as a clear
    startup-timeout failure rather than a silent misbehavior. A real
    inherited-socket handoff (as `run_app` does in-process) is not portable
    to a child process on Windows without extra plumbing, so this tradeoff
    is deliberate.

    `import_string` must be an "module:attr" string (a real subprocess needs
    something importable, not a live object). Polls the app's own port with
    plain TCP connect attempts (not an HTTP request, since the app's actual
    routes are unknown to the harness) until it accepts a connection or
    `startup_timeout` elapses, then hands back a `Service`.
    """
    import asyncio
    import socket
    import subprocess
    import sys as _sys

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, 0))
    port = sock.getsockname()[1]
    sock.close()

    cmd = [_sys.executable, "-m", "uvicorn", import_string, "--host", host, "--port", str(port), "--log-level", "warning"]
    if extra_args:
        cmd.extend(extra_args)

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    proc = subprocess.Popen(
        cmd, env=proc_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    base_url = f"http://{host}:{port}"
    try:
        deadline = time.monotonic() + startup_timeout
        connected = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"subprocess exited early (code {proc.returncode}): {_last_nonempty(out)}")
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.3)
            try:
                probe.connect((host, port))
                connected = True
            except OSError:
                pass
            finally:
                probe.close()
            if connected:
                break
            await asyncio.sleep(0.1)

        if not connected:
            raise TimeoutError(f"subprocess app did not accept connections within {startup_timeout}s at {base_url}")

        yield Service(base_url, port)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _last_nonempty(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


@asynccontextmanager
async def asgi_client(app, *, base_url="http://testserver", **kwargs):
    """httpx.AsyncClient wired directly to an ASGI app in-memory (httpx's
    ASGITransport) -- no socket, no subprocess, no real network stack. Use
    for validators that only need to assert response shape/content and
    don't care about real TCP/timing behavior (most correctness checks)."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url, **kwargs) as client:
        yield client
