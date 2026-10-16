import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# CLAUDE-NOTE: security baseline. This server exposes python_exec (arbitrary code in iClone), so it must not be
# reachable from web pages. Previously it sent "Access-Control-Allow-Origin: *" with no checks, letting any site
# in the user's browser POST tool calls (CSRF; text/plain "simple" requests skip preflight) or reach it via
# DNS rebinding. Now: Host must be 127.0.0.1/localhost:<port> (anti-rebinding), any browser Origin is rejected
# unless listed in MC_ICLONE8_MCP_ALLOWED_ORIGINS (comma-separated), POST must be application/json, and if
# MC_ICLONE8_MCP_TOKEN is set every request needs "Authorization: Bearer <token>". Native MCP clients
# (Claude Code, Codex, scripts/*.py) send no Origin and are unaffected when no token is set.


def _allowed_origins():
    return {o.strip() for o in os.environ.get("MC_ICLONE8_MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()}


class _RequestHandler(BaseHTTPRequestHandler):
    server_version = "mc-iclone8-mcp/0.1"

    def log_message(self, *_args):
        return

    def _reject(self, code, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        """Return True if the request may proceed; otherwise send a 4xx and return False."""
        port = self.server.server_address[1]
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
            self._reject(403, "forbidden host")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in _allowed_origins():
            self._reject(403, "forbidden origin")
            return False
        token = os.environ.get("MC_ICLONE8_MCP_TOKEN")
        if token:
            auth = self.headers.get("Authorization") or ""
            if not hmac.compare_digest(auth.encode("utf-8"), ("Bearer " + token).encode("utf-8")):
                self._reject(401, "missing or invalid bearer token")
                return False
        return True

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin is not None and origin in _allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, Mcp-Session-Id")

    def do_OPTIONS(self):
        if not self._guard():
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._guard():
            return
        if self.path == "/health":
            payload = {"status": "ok", "server": "mc-iclone8-mcp", "api": "iClone 8 RLPy"}
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return
        if not self._guard():
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._reject(415, "Content-Type must be application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            result = self.server.mcp_handler(body)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(result.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError):
            return


class MCPServer:
    def __init__(self, handler, host="127.0.0.1", port=8766):
        self.handler = handler
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None
        self.running = False

    def start(self):
        if self.running and self.httpd:
            return "http://%s:%d/mcp" % (self.host, self.port)
        ThreadingHTTPServer.allow_reuse_address = True
        ThreadingHTTPServer.daemon_threads = True
        if hasattr(ThreadingHTTPServer, "block_on_close"):
            ThreadingHTTPServer.block_on_close = False
        self.httpd = ThreadingHTTPServer((self.host, self.port), _RequestHandler)
        self.httpd.mcp_handler = self.handler
        self.running = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="mc-iclone8-mcp", daemon=True)
        self.thread.start()
        return "http://%s:%d/mcp" % (self.host, self.port)

    def stop(self):
        httpd, thread = self.httpd, self.thread
        self.running = False
        self.httpd = None
        self.thread = None
        if httpd:
            try:
                httpd.shutdown()
            finally:
                httpd.server_close()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
