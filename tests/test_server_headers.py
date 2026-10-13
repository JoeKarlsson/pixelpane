"""Responses through the real HTTP server carry exactly one Date header (proxies warn otherwise)."""
import http.client
import logging
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
        self.state = state
        self.werkzeug = logging.getLogger("werkzeug")
        self.level, self.werkzeug.level = self.werkzeug.level, logging.WARNING   # no request lines in test output
        self.server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.werkzeug.level = self.level

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

    def test_frame_stream_pushes_new_frames(self):
        from PIL import Image
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request("GET", "/api/frames")
        r = conn.getresponse()
        self.assertEqual((r.status, r.getheader("X-Accel-Buffering")), (200, "no"))

        def frame():
            head = r.read(4)
            cols, rows = int.from_bytes(head[:2], "big"), int.from_bytes(head[2:], "big")
            return cols, rows, r.read(cols * rows * 3)
        cols, rows, px = frame()
        self.assertEqual((cols, rows, px[:3]), (32, 32, b"\0\0\0"))
        self.state.last_frame = Image.new("RGB", (32, 32), (255, 0, 0))   # what the player does
        self.assertEqual(frame()[2][:3], b"\xff\0\0")
        r.close()
        conn.close()


if __name__ == "__main__":
    unittest.main()
