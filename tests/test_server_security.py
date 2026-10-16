import http.client
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import MCPServer

BODY = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})


class TestServerSecurity(unittest.TestCase):
    def setUp(self):
        for k in ("MC_ICLONE8_MCP_TOKEN", "MC_ICLONE8_MCP_ALLOWED_ORIGINS"):
            os.environ.pop(k, None)
        self.calls = []
        self.srv = MCPServer(lambda body: (self.calls.append(body), '{"ok": true}')[1], port=0)
        self.srv.start()
        self.port = self.srv.httpd.server_address[1]

    def tearDown(self):
        self.srv.stop()
        for k in ("MC_ICLONE8_MCP_TOKEN", "MC_ICLONE8_MCP_ALLOWED_ORIGINS"):
            os.environ.pop(k, None)

    def req(self, method="POST", path="/mcp", headers=None, body=BODY):
        h = {"Host": "127.0.0.1:%d" % self.port, "Content-Type": "application/json"}
        h.update(headers or {})
        h = {k: v for k, v in h.items() if v is not None}
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            c.putheader(k, v)
        data = body.encode() if method == "POST" else None
        if data is not None:
            c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def test_native_client_allowed(self):
        status, headers, body = self.req()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(len(self.calls), 1)

    def test_localhost_host_allowed(self):
        self.assertEqual(self.req(headers={"Host": "localhost:%d" % self.port})[0], 200)

    def test_browser_origin_rejected_before_handler(self):
        status, _, _ = self.req(headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_rebinding_host_rejected(self):
        self.assertEqual(self.req(headers={"Host": "attacker.example:%d" % self.port})[0], 403)
        self.assertEqual(self.calls, [])

    def test_simple_request_content_type_rejected(self):
        # A cross-site form/fetch can send text/plain without a CORS preflight.
        self.assertEqual(self.req(headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.calls, [])

    def test_allowed_origin_gets_cors(self):
        os.environ["MC_ICLONE8_MCP_ALLOWED_ORIGINS"] = "http://localhost:6274"
        status, headers, _ = self.req(headers={"Origin": "http://localhost:6274"})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://localhost:6274")

    def test_token_required_when_set(self):
        os.environ["MC_ICLONE8_MCP_TOKEN"] = "s3cret"
        self.assertEqual(self.req()[0], 401)
        self.assertEqual(self.req(headers={"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.req(headers={"Authorization": "Bearer s3cret"})[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_health_still_works(self):
        status, _, body = self.req(method="GET", path="/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
