"""Play now thumbnails: GET /api/scenes/<name>/thumb.gif."""
import io
import random
import unittest

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane.app import health  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402

HOST = {"Host": "localhost"}


class ThumbTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.gifs = GifLibrary(self.state, random.Random(1))
        self.client = create_app(self.state, self.gifs, health).test_client()

    def get(self, name):
        return self.client.get(f"/api/scenes/{name}/thumb.gif", headers=HOST)

    def test_a_scene_is_a_small_looping_animation(self):
        r = self.get("plasma")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/gif"))
        im = Image.open(io.BytesIO(r.data))
        self.assertEqual(im.size, (32, 32))
        self.assertGreater(im.n_frames, 10)

    def test_data_scenes_need_their_data(self):
        self.assertEqual(self.get("weather").status_code, 204)
        self.state.put_data("weather", {"temp": 52, "condition": "rainy"})
        self.client = create_app(self.state, self.gifs, health).test_client()   # fresh cache
        self.assertEqual(self.get("weather").status_code, 200)

    def test_pickers_show_a_scene_they_would_pick(self):
        self.assertEqual(self.get("generative").status_code, 200)

    def test_gifs_unknown_and_disabled_scenes_get_none(self):
        played_before = dict(getattr(self.gifs, "recent", {}) or {})
        self.assertEqual(self.get("gif").status_code, 204)    # would take a turn from the playlist
        self.assertEqual(dict(getattr(self.gifs, "recent", {}) or {}), played_before)
        self.assertEqual(self.get("volcano").status_code, 404)
        self.assertEqual(self.get("gif:retro").status_code, 404)
        self.state.update_config({"plugins": {"generative": {"enabled": False}}})
        self.assertEqual(self.get("fire").status_code, 404)

    def test_cached(self):
        a = self.get("fire").data
        self.assertEqual(self.get("fire").data, a)


if __name__ == "__main__":
    unittest.main()
