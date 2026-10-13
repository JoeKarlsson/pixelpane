import base64
import random
import unittest

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane.app import health  # noqa: E402
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.sketch import Sketch  # noqa: E402
from pixelpane.state import VAR, GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402


def frame(color, size=(32, 32)):
    return base64.b64encode(Image.new("RGB", size, color).tobytes()).decode()


class SketchTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.gifs = GifLibrary(self.state, random.Random(0))
        self.client = create_app(self.state, self.gifs, health).test_client()

    def test_drawing_goes_on_the_board_and_holds_it(self):
        r = self.client.put("/api/sketch", json={"width": 32, "height": 32, "ms": 100, "frames": [frame((255, 0, 0))]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.state.active_pin()["scene"], "sketch")
        got = self.client.get("/api/sketch").get_json()
        self.assertEqual((got["size"], got["showing"], len(got["frames"])), ([32, 32], True, 1))
        # the scene shows it, and picks up a newer drawing without restarting
        gen = SCENES["sketch"](self._ctx(), 5)
        self.assertEqual(next(gen)[0].getpixel((0, 0)), (255, 0, 0))
        self.client.put("/api/sketch", json={"width": 32, "height": 32, "frames": [frame((0, 0, 255))], "show": False})
        self.assertEqual(next(gen)[0].getpixel((0, 0)), (0, 0, 255))

    def _ctx(self):
        from pixelpane.app import Ctx
        return Ctx(self.state, self.gifs, random.Random(0))

    def test_bad_drawings_are_refused(self):
        for bad in ({"width": 64, "height": 64, "frames": [frame((1, 2, 3), (64, 64))]},   # not this board's size
                    {"width": 32, "height": 32, "frames": []},
                    {"width": 32, "height": 32, "frames": ["nope"]},
                    {"width": 32, "height": 32, "frames": [frame((1, 2, 3))], "ms": 0},
                    {"width": 32, "height": 32, "frames": [frame((1, 2, 3))] * 65}):
            self.assertEqual(self.client.put("/api/sketch", json=bad).status_code, 400, bad.get("ms"))
        self.assertIsNone(self.state.active_pin())
        r = self.client.put("/api/sketch", json={"width": 32, "height": 32, "frames": [frame((1, 2, 3))]},
                            headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_save_to_library_as_a_gif(self):
        body = {"width": 32, "height": 32, "ms": 200, "frames": [frame((255, 0, 0)), frame((0, 255, 0))],
                "name": "My Cat!", "category": "Doodles"}
        r = self.client.post("/api/sketch/save", json=body).get_json()
        self.assertEqual(r["id"], "upload/all/doodles-my-cat.gif")
        self.assertEqual(self.client.post("/api/sketch/save", json=body).get_json()["name"], "doodles-my-cat-1.gif")
        with Image.open(VAR / "uploads" / "all" / "doodles-my-cat.gif") as im:
            self.assertEqual((im.n_frames, im.info["duration"]), (2, 200))
        self.assertIn("doodles", self.client.get("/api/state").get_json()["categories"])

    def test_kept_across_restarts(self):
        sk = Sketch(VAR / "s.png")
        sk.set([Image.new("RGB", (32, 32), (9, 9, 9)), Image.new("RGB", (32, 32), (7, 7, 7))], 80)
        sk.save()
        again = Sketch(VAR / "s.png")
        frames, ms, _ = again.get()
        self.assertEqual((len(frames), ms, frames[1].getpixel((3, 3))), (2, 80, (7, 7, 7)))

    def test_pages(self):
        for path in ("/draw", "/animate"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"/static/draw.js", r.data)


if __name__ == "__main__":
    unittest.main()
