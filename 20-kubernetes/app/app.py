#!/usr/bin/env python3
"""Sandbox 20 fixture app: a deterministic, knob-driven HTTP server (and
optional queue worker) used as the workload for every task in this module.
Every behavior is controlled by an environment variable with a safe default
-- see the module README / .authoring/design.md for the full knob table.

Stdlib only for the HTTP server (ThreadingHTTPServer, no frameworks).
redis / pika are used only in WORK_MODE=consumer|producer.
"""

from __future__ import annotations

import http.server
import json
import os
import signal
import socket
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone

try:
    import redis
except ImportError:
    redis = None

try:
    import pika
except ImportError:
    pika = None


# --------------------------------------------------------------------------
# Env knobs
# --------------------------------------------------------------------------

def env_str(name, default=None):
    return os.environ.get(name, default)


def env_int(name, default):
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


def env_float(name, default):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


def env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def log(msg):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{ts} [sandbox20-app] {msg}", flush=True)


PORT = env_int("PORT", 8080)
APP_VERSION = env_str("APP_VERSION", "dev")

START_DELAY_S = env_float("START_DELAY_S", 0)
READY_DELAY_S = env_float("READY_DELAY_S", 0)
FAIL_READY = env_bool("FAIL_READY", False)
FAIL_HEALTH_AFTER_S = env_float("FAIL_HEALTH_AFTER_S", 0)  # 0 = disabled

CRASH_ON_START = env_bool("CRASH_ON_START", False)
CRASH_AFTER_S = env_float("CRASH_AFTER_S", 0)  # 0 = disabled
EXIT_CODE = env_int("EXIT_CODE", 1)

MEM_MB = env_int("MEM_MB", 0)
LEAK_MB_PER_S = env_float("LEAK_MB_PER_S", 0)
CPU_BURN_THREADS = env_int("CPU_BURN_THREADS", 0)

REQUIRED_ENV = env_str("REQUIRED_ENV", "")

TERM_IGNORE = env_bool("TERM_IGNORE", False)
TERM_GRACE_S = env_float("TERM_GRACE_S", 25)

WORK_MODE = env_str("WORK_MODE", "server")  # server | consumer | producer
QUEUE_BACKEND = env_str("QUEUE_BACKEND", "redis")  # redis | rabbitmq
PROCESS_MS = env_int("PROCESS_MS", 100)
RATE_PER_S = env_float("RATE_PER_S", 1)

START_TIME = time.monotonic()

# --------------------------------------------------------------------------
# Shared state
# --------------------------------------------------------------------------

request_count = 0
_request_count_lock = threading.Lock()

inflight = 0
_inflight_lock = threading.Lock()

processed_count = 0
_processed_lock = threading.Lock()

queue_depth = -1
_queue_depth_lock = threading.Lock()

shutting_down = threading.Event()
_stop_event = threading.Event()
_mem_hold = None
_leaked = []
httpd = None


# --------------------------------------------------------------------------
# Startup checks
# --------------------------------------------------------------------------

def check_required_env():
    names = [n.strip() for n in REQUIRED_ENV.split(",") if n.strip()]
    missing = [n for n in names if n not in os.environ]
    if missing:
        log(f"FATAL missing required env var(s): {', '.join(missing)} (REQUIRED_ENV check)")
        sys.exit(1)


def maybe_crash_on_start():
    if CRASH_ON_START:
        log(f"FATAL CRASH_ON_START fault injected: bootstrap-init-failure (exit={EXIT_CODE})")
        sys.exit(EXIT_CODE)


# --------------------------------------------------------------------------
# Background effects: memory hold/leak, cpu burn, delayed crash
# --------------------------------------------------------------------------

def _leak_loop():
    while not _stop_event.is_set():
        time.sleep(1)
        _leaked.append(bytearray(int(LEAK_MB_PER_S * 1024 * 1024)))
        log(f"leaked +{LEAK_MB_PER_S}MiB, total~{len(_leaked) * LEAK_MB_PER_S:.0f}MiB")


def _burn_loop(idx):
    log(f"cpu burn thread {idx} started")
    x = 0
    while not _stop_event.is_set():
        for _ in range(200_000):
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF


def _crash_after():
    time.sleep(CRASH_AFTER_S)
    log(f"CRASH_AFTER_S={CRASH_AFTER_S} elapsed, exiting with code {EXIT_CODE}")
    os._exit(EXIT_CODE)


def start_background_effects():
    global _mem_hold
    if MEM_MB > 0:
        log(f"allocating {MEM_MB}MiB and holding")
        _mem_hold = bytearray(MEM_MB * 1024 * 1024)
    if LEAK_MB_PER_S > 0:
        log(f"leaking {LEAK_MB_PER_S}MiB/s forever (OOMKill fixture)")
        threading.Thread(target=_leak_loop, daemon=True).start()
    if CPU_BURN_THREADS > 0:
        for i in range(CPU_BURN_THREADS):
            threading.Thread(target=_burn_loop, args=(i,), daemon=True).start()
    if CRASH_AFTER_S > 0:
        threading.Thread(target=_crash_after, daemon=True).start()


# --------------------------------------------------------------------------
# Queue backends (WORK_MODE=consumer|producer)
# --------------------------------------------------------------------------

class RedisQueue:
    def __init__(self):
        if redis is None:
            raise RuntimeError("redis package not installed")
        self.host = env_str("REDIS_HOST", "localhost")
        self.port = env_int("REDIS_PORT", 6379)
        self.key = env_str("QUEUE_KEY", "sandbox20:queue")
        self.client = None
        self._connect()

    def _connect(self):
        backoff = 1
        while True:
            try:
                self.client = redis.Redis(host=self.host, port=self.port, socket_connect_timeout=3)
                self.client.ping()
                log(f"redis connected {self.host}:{self.port} key={self.key}")
                return
            except Exception as e:
                log(f"redis connect failed: {e}; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 15)

    def push(self, item):
        try:
            self.client.rpush(self.key, item)
        except Exception as e:
            log(f"redis push failed: {e}; reconnecting")
            self._connect()

    def pop(self):
        try:
            res = self.client.blpop(self.key, timeout=1)
            return res[1] if res else None
        except Exception as e:
            log(f"redis pop failed: {e}; reconnecting")
            self._connect()
            return None

    def depth(self):
        try:
            return self.client.llen(self.key)
        except Exception as e:
            log(f"redis depth check failed: {e}")
            return -1


class RabbitQueue:
    def __init__(self):
        if pika is None:
            raise RuntimeError("pika package not installed")
        self.host = env_str("RABBIT_HOST", "localhost")
        self.port = env_int("RABBIT_PORT", 5672)
        self.user = env_str("RABBIT_USER", "guest")
        self.password = env_str("RABBIT_PASS", "guest")
        self.queue = env_str("QUEUE", "sandbox20-queue")
        self.conn = None
        self.channel = None
        self._connect()

    def _connect(self):
        backoff = 1
        creds = pika.PlainCredentials(self.user, self.password)
        params = pika.ConnectionParameters(
            host=self.host, port=self.port, credentials=creds,
            heartbeat=30, blocked_connection_timeout=10,
        )
        while True:
            try:
                self.conn = pika.BlockingConnection(params)
                self.channel = self.conn.channel()
                self.channel.queue_declare(queue=self.queue, durable=False)
                log(f"rabbitmq connected {self.host}:{self.port} queue={self.queue}")
                return
            except Exception as e:
                log(f"rabbitmq connect failed: {e}; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 15)

    def push(self, item):
        try:
            self.channel.basic_publish(exchange="", routing_key=self.queue, body=item)
        except Exception as e:
            log(f"rabbitmq push failed: {e}; reconnecting")
            self._connect()

    def pop(self):
        try:
            _method, _props, body = self.channel.basic_get(queue=self.queue, auto_ack=True)
            return body
        except Exception as e:
            log(f"rabbitmq pop failed: {e}; reconnecting")
            self._connect()
            return None

    def depth(self):
        try:
            res = self.channel.queue_declare(queue=self.queue, durable=False, passive=True)
            return res.method.message_count
        except Exception as e:
            log(f"rabbitmq depth check failed: {e}")
            return -1


def make_queue():
    return RabbitQueue() if QUEUE_BACKEND == "rabbitmq" else RedisQueue()


def consumer_loop():
    global processed_count, queue_depth
    q = make_queue()
    last_depth_poll = 0.0
    log(f"consumer started backend={QUEUE_BACKEND} process_ms={PROCESS_MS}")
    while not _stop_event.is_set():
        item = q.pop()
        if item is not None:
            with _processed_lock:
                processed_count += 1
            time.sleep(PROCESS_MS / 1000.0)
        now = time.monotonic()
        if now - last_depth_poll > 2:
            with _queue_depth_lock:
                queue_depth = q.depth()
            last_depth_poll = now


def producer_loop():
    q = make_queue()
    interval = 1.0 / RATE_PER_S if RATE_PER_S > 0 else 1.0
    log(f"producer started backend={QUEUE_BACKEND} rate_per_s={RATE_PER_S}")
    i = 0
    while not _stop_event.is_set():
        i += 1
        q.push(json.dumps({"i": i, "ts": time.time()}))
        time.sleep(interval)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def render_metrics():
    lines = [
        "# HELP app_requests_total Total HTTP requests served.",
        "# TYPE app_requests_total counter",
        f"app_requests_total {request_count}",
        "# HELP app_inflight In-flight HTTP requests.",
        "# TYPE app_inflight gauge",
        f"app_inflight {inflight}",
    ]
    if WORK_MODE in ("consumer", "producer"):
        lines += [
            "# HELP app_queue_depth Last observed queue depth.",
            "# TYPE app_queue_depth gauge",
            f"app_queue_depth {queue_depth}",
        ]
    if WORK_MODE == "consumer":
        lines += [
            "# HELP app_processed_total Total queue items processed.",
            "# TYPE app_processed_total counter",
            f"app_processed_total {processed_count}",
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "sandbox20/1.0"

    def log_message(self, fmt, *args):
        pass  # the app logs its own state-transition lines; suppress access log noise

    def do_GET(self):
        global inflight, request_count
        with _inflight_lock:
            inflight += 1
        with _request_count_lock:
            request_count += 1
        try:
            self._route()
        finally:
            with _inflight_lock:
                inflight -= 1

    def _route(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._json(200, {
                "app_version": APP_VERSION,
                "hostname": socket.gethostname(),
                "request_count": request_count,
            })
        elif path == "/healthz":
            if FAIL_HEALTH_AFTER_S > 0 and (time.monotonic() - START_TIME) > FAIL_HEALTH_AFTER_S:
                self._text(500, "unhealthy: FAIL_HEALTH_AFTER_S exceeded\n")
            else:
                self._text(200, "ok\n")
        elif path == "/readyz":
            if shutting_down.is_set():
                self._text(503, "not ready: shutting down\n")
            elif FAIL_READY:
                self._text(503, "not ready: FAIL_READY=1\n")
            elif (time.monotonic() - START_TIME) < READY_DELAY_S:
                self._text(503, "not ready: warming up\n")
            else:
                self._text(200, "ready\n")
        elif path == "/work":
            try:
                ms = max(int(qs.get("ms", ["0"])[0]), 0)
            except ValueError:
                ms = 0
            time.sleep(ms / 1000.0)
            self._text(200, f"worked {ms}ms\n")
        elif path == "/env":
            name = qs.get("name", [""])[0]
            if name.startswith("APP_") or name.startswith("CONFIG_"):
                self._text(200, f"{name}={os.environ.get(name, '')}\n")
            else:
                self._text(403, "forbidden: only APP_* or CONFIG_* env vars are exposed\n")
        elif path == "/metrics":
            self._text(200, render_metrics())
        else:
            self._text(404, "not found\n")

    def _text(self, code, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# --------------------------------------------------------------------------
# Shutdown
# --------------------------------------------------------------------------

def _graceful_shutdown():
    threading.Thread(target=httpd.shutdown, daemon=True).start()
    deadline = time.monotonic() + TERM_GRACE_S
    while inflight > 0 and time.monotonic() < deadline:
        time.sleep(0.05)
    log(f"graceful shutdown done (inflight={inflight}), exiting 0")
    _stop_event.set()
    os._exit(0)


def handle_sigterm(signum, frame):
    if TERM_IGNORE:
        log("SIGTERM received but TERM_IGNORE=1, ignoring")
        return
    log("SIGTERM received, draining inflight requests before exit")
    shutting_down.set()
    threading.Thread(target=_graceful_shutdown, daemon=True).start()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    global httpd

    check_required_env()
    maybe_crash_on_start()

    if START_DELAY_S > 0:
        log(f"START_DELAY_S={START_DELAY_S}, sleeping before bind")
        time.sleep(START_DELAY_S)

    start_background_effects()

    if WORK_MODE == "consumer":
        threading.Thread(target=consumer_loop, daemon=True).start()
    elif WORK_MODE == "producer":
        threading.Thread(target=producer_loop, daemon=True).start()

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.daemon_threads = True

    signal.signal(signal.SIGTERM, handle_sigterm)

    log(f"listening on 0.0.0.0:{PORT} version={APP_VERSION} mode={WORK_MODE}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
