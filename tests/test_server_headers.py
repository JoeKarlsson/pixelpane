"""Responses through the real HTTP server carry exactly one Date header (proxies warn otherwise)."""
import http.client
import random
import threading
import unittest

from werkzeug.serving import make_server

from tests import support

support.load_plugins()
from pixelpane.app import health  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402


class HeaderTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        state = State()
        app = create_app(state, GifLibrary(state, random.Random(1)), health)
        self.server = make_server("127.0.0.1", 0, app)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()

    def test_one_date_header_everywhere(self):
        for path in ("/", "/api/health", "/favicon.ico", "/static/app.css", "/preview.png",
                     "/gif/repo/retro-mario-run.gif"):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            conn.request("GET", path)
            r = conn.getresponse()
            r.read()
            dates = [v for k, v in r.getheaders() if k.lower() == "date"]
            self.assertEqual((r.status, len(dates)), (200, 1), path)
            conn.close()


if __name__ == "__main__":
    unittest.main()
