"""Minimal alert sink: POST /alert appends one NDJSON line, GET /health checks liveness."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALERTS_PATH = "/alerts/alerts.ndjson"


class AlertHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, b"ok")
        else:
            self._respond(404, b"not found")

    def do_POST(self):
        if self.path != "/alert":
            self._respond(404, b"not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._respond(400, b"invalid json")
            return
        with open(ALERTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        self._respond(200, b"ok")

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), AlertHandler)
    server.serve_forever()
