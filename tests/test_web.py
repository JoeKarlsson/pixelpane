import io
import random
import unittest

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane.app import health  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402


def gif_bytes(size=(64, 64), frames=2):
    buf = io.BytesIO()
    imgs = [Image.new("RGB", size, c) for c in ((255, 0, 0), (0, 255, 0))[:frames]]
    imgs[0].save(buf, "GIF", save_all=True, append_images=imgs[1:], duration=100, loop=0)
    buf.seek(0)
    return buf


class WebTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.gifs = GifLibrary(self.state, random.Random(0))
        self.client = create_app(self.state, self.gifs, health).test_client()

    def post(self, url, body):
        return self.client.post(url, json=body)

    def test_classify_api(self):
        r = self.client.patch("/api/gifs/repo/retro-mario-run.gif", json={"category": "Video Games", "theme": "halloween"})
        self.assertEqual(r.get_json(), {"ok": True, "changed": 1})
        g = {x["id"]: x for x in self.client.get("/api/gifs").get_json()}["repo/retro-mario-run.gif"]
        self.assertEqual((g["category"], g["theme"]), ("video_games", "halloween"))
        self.assertEqual(self.client.patch("/api/gifs/repo/nope.gif", json={"category": "x"}).status_code, 404)
        self.assertEqual(self.client.patch("/api/gifs/repo/retro-sonic-dash.gif", json={"theme": "easter"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/gifs/repo/retro-sonic-dash.gif", json={"category": "a/b"}).status_code, 400)
        r = self.post("/api/gifs/classify", {"ids": ["repo/retro-sonic-dash.gif", "repo/abstract-plasma.gif"],
                                              "category": "games"})
        self.assertEqual(r.get_json()["changed"], 2)
        self.assertEqual(self.post("/api/gifs/classify", {"ids": "x"}).status_code, 400)
        self.assertEqual(self.post("/api/categories/rename", {"from": "games", "to": "arcade"}).get_json()["changed"], 2)
        self.assertEqual(self.post("/api/categories/rename", {"from": "games", "to": "x"}).status_code, 404)
        self.assertIn("arcade", self.client.get("/api/state").get_json()["categories"])
        self.assertEqual(self.post("/api/gifs/classify", {"ids": ["repo/retro-mario-run.gif"], "reset": True}).status_code, 200)
        # writes from another site are refused, like every other write
        r = self.client.patch("/api/gifs/repo/retro-mario-run.gif", json={"category": "x"},
                              headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        # and config PUT validates gif_meta
        r = self.client.put("/api/config", json={"gif_meta": {"repo/x.gif": {"theme": "nope"}}})
        self.assertEqual(r.status_code, 400)

    def test_index_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<title>PixelPane</title>", r.data)

    def test_health_and_state(self):
        h = self.client.get("/api/health").get_json()
        for key in ("ok", "power", "brightness", "scene", "now", "themes", "temp_c", "throttled", "version"):
            self.assertIn(key, h)
        s = self.client.get("/api/state").get_json()
        self.assertEqual(s["categories"], ["abstract", "retro", "space"])
        self.assertIn("halloween", s["theme_names"])
        self.assertIn("bell", s["icons"])
        self.assertIn("fire", s["scenes"]["generative"])

    def test_power_and_brightness(self):
        r = self.post("/api/state", {"power": False, "brightness": 25}).get_json()
        self.assertEqual((r["power"], r["brightness"]), (False, 25))
        self.assertEqual(self.post("/api/state", {"brightness": 999}).get_json()["brightness"], 100)
        self.assertFalse(State().power)  # persisted

    def test_play(self):
        for scene in ("clock", "seasonal", "generative", "halloween", "gif:retro"):
            self.assertEqual(self.post("/api/play", {"scene": scene}).status_code, 200, scene)
            self.assertEqual(self.state.play_next["scene"], scene)
        self.assertEqual(self.post("/api/play", {"scene": "gif", "params": {"id": "repo/retro-mario-run.gif"}}).status_code, 200)
        for bad in ("bogus", "gif:../x", None):
            self.assertEqual(self.post("/api/play", {"scene": bad}).status_code, 400, bad)

    def test_skip(self):
        self.assertEqual(self.post("/api/skip", {}).status_code, 200)
        self.assertTrue(self.state.skip)

    def test_notify(self):
        self.assertEqual(self.post("/api/notify", {"text": ""}).status_code, 400)
        r = self.post("/api/notify", {"text": "x" * 500, "seconds": 999, "icon": "bell", "flash": 1})
        self.assertEqual(r.status_code, 200)
        n = self.state.notifications[-1]
        self.assertEqual((len(n["text"]), n["seconds"], n["flash"]), (200, 120, True))

    def test_pin(self):
        self.assertEqual(self.post("/api/pin", {"scene": "on_air", "minutes": 5}).status_code, 200)
        self.assertEqual(self.state.active_pin()["scene"], "on_air")
        self.assertEqual(self.post("/api/pin", {"scene": "gif"}).status_code, 400)
        self.assertEqual(self.client.delete("/api/pin").status_code, 200)
        self.assertIsNone(self.state.active_pin())

    def test_data(self):
        for key, value in support.SAMPLE_DATA.items():
            self.assertEqual(self.post(f"/api/data/{key}", value).status_code, 200)
            self.assertEqual(self.state.get_data(key), value)
        self.assertEqual(self.post("/api/data/secrets", {}).status_code, 400)
        self.assertEqual(set(self.client.get("/api/state").get_json()["data"]), set(support.SAMPLE_DATA))

    def test_config(self):
        self.assertEqual(self.client.get("/api/config").get_json()["rotation"], self.state.config["rotation"])
        self.assertEqual(self.client.put("/api/config", json={"junk": 1}).status_code, 400)
        r = self.client.put("/api/config", json={"rotation": ["clock", "gif:space"], "dwell": {"gif": 7}})
        self.assertEqual(r.status_code, 200)
        cfg = r.get_json()
        self.assertEqual((cfg["rotation"], cfg["dwell"]["gif"]), (["clock", "gif:space"], 7))
        r = self.client.put("/api/config", json={"rotation": ["clock", "nope"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("unknown scenes", r.get_json()["error"])
        self.assertEqual(self.client.put("/api/config", json={"brightness": "lots"}).status_code, 400)

    def test_gif_listing_and_file(self):
        rows = self.client.get("/api/gifs").get_json()
        self.assertEqual(len(rows), 6)
        r = self.client.get("/gif/repo/retro-mario-run.gif")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/gif"))
        self.assertEqual(self.client.get("/gif/repo/../state.py").status_code, 404)

    def test_upload_hide_delete(self):
        r = self.client.post("/api/gifs", data={"theme": "halloween", "file": (gif_bytes(), "Spooky Bat!.gif")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        gid = r.get_json()["saved"][0]["id"]
        self.assertEqual(gid, "upload/halloween/Spooky_Bat.gif")
        with Image.open(support.VAR / "uploads" / "halloween" / "Spooky_Bat.gif") as im:
            self.assertEqual((im.size, im.n_frames), ((32, 32), 2))
        again = self.client.post("/api/gifs", data={"theme": "halloween", "file": (gif_bytes(), "Spooky Bat!.gif")},
                                 content_type="multipart/form-data").get_json()
        self.assertEqual(again["saved"][0]["id"], "upload/halloween/Spooky_Bat-1.gif")  # never overwrites

        self.assertEqual(self.post("/api/gifs/hide", {"id": gid, "hidden": True}).status_code, 200)
        self.assertIn(gid, self.state.config["hidden_gifs"])
        self.post("/api/gifs/hide", {"id": gid, "hidden": False})
        self.assertNotIn(gid, self.state.config["hidden_gifs"])

        self.assertEqual(self.client.delete(f"/api/gifs/{gid}").status_code, 200)
        self.assertFalse((support.VAR / "uploads" / "halloween" / "Spooky_Bat.gif").exists())
        self.assertEqual(self.client.delete("/api/gifs/repo/retro-mario-run.gif").status_code, 400)

    def test_upload_rejects_bad_input(self):
        bad_theme = self.client.post("/api/gifs", data={"theme": "../etc", "file": (gif_bytes(), "a.gif")},
                                     content_type="multipart/form-data")
        self.assertEqual(bad_theme.status_code, 400)
        not_image = self.client.post("/api/gifs", data={"theme": "all", "file": (io.BytesIO(b"nope"), "a.gif")},
                                     content_type="multipart/form-data")
        self.assertEqual(not_image.status_code, 400)

    def test_cross_site_writes_are_refused(self):
        evil = {"Origin": "http://evil.example"}
        self.assertEqual(self.client.post("/api/state", json={"power": False}, headers=evil).status_code, 403)
        self.assertEqual(self.client.delete("/api/pin", headers=evil).status_code, 403)
        self.assertTrue(self.state.power)
        self.assertEqual(self.client.get("/api/health", headers=evil).status_code, 200)   # reads are fine
        same = {"Origin": "http://localhost"}  # the test client's host
        self.assertEqual(self.client.post("/api/state", json={"brightness": 30}, headers=same).status_code, 200)
        self.assertEqual(self.client.post("/api/state", json={"brightness": 31}).status_code, 200)  # no Origin (HA, curl)

    def test_optional_token(self):
        self.client.put("/api/config", json={"api_token": "correct-horse"})
        self.assertEqual(self.client.get("/api/config").get_json()["api_token"], "••••••••")   # never shown
        self.assertTrue(self.client.get("/api/state").get_json()["auth"])
        self.assertEqual(self.post("/api/state", {"power": False}).status_code, 401)
        self.assertEqual(self.client.post("/api/state", json={"power": False},
                                          headers={"X-PixelPane-Token": "wrong-horse"}).status_code, 401)
        self.assertEqual(self.client.post("/api/state", json={"power": False},
                                          headers={"Authorization": "Bearer correct-horse"}).status_code, 200)
        self.assertFalse(self.state.power)
        self.assertEqual(self.client.get("/api/health").status_code, 200)   # reads stay open
        r = self.client.put("/api/config", json={"api_token": None}, headers={"X-PixelPane-Token": "correct-horse"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.post("/api/state", {"power": True}).status_code, 200)

    def test_preview_follows_the_panel(self):
        self.state.update_config({"panel": {"cols": 64, "rows": 32}})
        with Image.open(io.BytesIO(self.client.get("/preview.png").data)) as im:
            self.assertEqual(im.size, (320, 160))
        self.assertEqual(self.client.get("/api/state").get_json()["panel"], [64, 32])

    def test_preview_png(self):
        r = self.client.get("/preview.png?scale=4")
        self.assertEqual(r.mimetype, "image/png")
        with Image.open(io.BytesIO(r.data)) as im:
            self.assertEqual(im.size, (128, 128))
        with Image.open(io.BytesIO(self.client.get("/preview.png?scale=999").data)) as im:
            self.assertEqual(im.size, (512, 512))  # clamped


if __name__ == "__main__":
    unittest.main()
