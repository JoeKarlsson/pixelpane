import io
import random
import unittest
from unittest import mock

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane import state as st  # noqa: E402


class GifLibraryTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = st.State()
        self.lib = st.GifLibrary(self.state, random.Random(3))

    def names(self, paths):
        return sorted(p.name for p in paths)

    def test_pools_split_all_year_and_themes(self):
        self.assertEqual(self.names(self.lib.pool()),
                         ["abstract-plasma.gif", "retro-mario-run.gif", "retro-sonic-dash.gif", "space-earth-spin.gif"])
        self.assertEqual(self.names(self.lib.pool("halloween")), ["pumpkin-glow.gif"])
        self.assertEqual(self.lib.pool("summer"), [])

    def test_uploads_join_their_pool(self):
        support.make_gif(support.VAR / "uploads" / "all" / "retro-upload.gif")
        support.make_gif(support.VAR / "uploads" / "halloween" / "bat.gif")
        self.assertIn("retro-upload.gif", self.names(self.lib.pool()))
        self.assertIn("bat.gif", self.names(self.lib.pool("halloween")))

    def test_hidden_gifs_are_skipped(self):
        self.state.update_config({"hidden_gifs": ["repo/retro-mario-run.gif"]})
        self.assertNotIn("retro-mario-run.gif", self.names(self.lib.pool()))

    def test_categories_and_category_picks(self):
        self.assertEqual(self.lib.categories(), ["abstract", "retro", "space"])
        picks = {self.lib.next("retro").name for _ in range(10)}
        self.assertEqual(picks, {"retro-mario-run.gif", "retro-sonic-dash.gif"})
        self.assertIsNone(self.lib.next("nope"))

    def test_shuffle_bag_plays_everything_before_repeating(self):
        with mock.patch.object(self.state, "themes", return_value=["autumn"]):
            first = [self.lib.next().name for _ in range(4)]
        self.assertEqual(sorted(first), self.names(self.lib.pool()))

    def test_theme_share_prefers_active_theme(self):
        self.state.update_config({"plugins": {"gifs": {"theme_share": 1.0}}})
        with mock.patch.object(self.state, "themes", return_value=["autumn", "halloween"]):
            self.assertEqual(self.lib.next().name, "pumpkin-glow.gif")
        self.state.update_config({"plugins": {"gifs": {"theme_share": 0.0}}})
        with mock.patch.object(self.state, "themes", return_value=["autumn", "halloween"]):
            self.assertNotEqual(self.lib.next().name, "pumpkin-glow.gif")

    def test_resolve_and_ids(self):
        p = self.lib.resolve("repo/themes/halloween/pumpkin-glow.gif")
        self.assertEqual(self.lib.gif_id(p), "repo/themes/halloween/pumpkin-glow.gif")
        self.assertIsNone(self.lib.resolve("repo/../../etc/passwd"))
        self.assertIsNone(self.lib.resolve("nope/x.gif"))
        self.assertIsNone(self.lib.resolve("repo/missing.gif"))

    def test_listing_marks_theme_category_hidden_upload(self):
        self.state.update_config({"hidden_gifs": ["repo/space-earth-spin.gif"]})
        support.make_gif(support.VAR / "uploads" / "winter" / "snow.gif")
        rows = {r["name"]: r for r in self.lib.listing()}
        self.assertEqual(rows["retro-mario-run.gif"]["category"], "retro")
        self.assertTrue(rows["space-earth-spin.gif"]["hidden"])
        self.assertEqual(rows["pumpkin-glow.gif"]["theme"], "halloween")
        self.assertTrue(rows["snow.gif"]["upload"])
        self.assertNotIn("README.md", rows)

    def test_frames_are_panel_sized_with_durations(self):
        for name in ("space-earth-spin.gif", "abstract-plasma.gif", "retro-mario-run.gif"):
            frames = self.lib.frames(support.HOME / "gifs" / name)
            self.assertEqual(len(frames), 3)
            for img, hold in frames:
                self.assertEqual(img.size, (32, 32))
                self.assertEqual(img.mode, "RGB")
                self.assertAlmostEqual(hold, 0.08)

    def test_tall_sprites_fit_whole_and_get_trimmed(self):
        # a 6x14 sprite drawn in a 40x40 empty cell, like a sprite-sheet frame
        frames = []
        for shade in (200, 120):
            img = Image.new("RGB", (40, 40))
            for y in range(13, 27):
                for x in range(17, 23):
                    img.putpixel((x, y), (shade, 50, 50))
            frames.append(img)
        src = io.BytesIO()
        frames[0].save(src, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        src.seek(0)
        out = st.decode_gif(src)
        self.assertEqual(len(out), 2)
        img = out[0][0]
        self.assertEqual(img.size, (32, 32))
        lit = img.convert("L").point(lambda v: 255 if v > 16 else 0).getbbox()
        # trimmed to 6x14 then scaled 2x (whole-number) to 12x28, centered, nothing cut off
        self.assertEqual((lit[2] - lit[0], lit[3] - lit[1]), (12, 28))
        self.assertEqual((lit[0], lit[1]), (10, 2))

    def test_photos_still_fill_the_panel(self):
        src = io.BytesIO()
        Image.new("RGB", (120, 80), (90, 140, 200)).save(src, "PNG")
        src.seek(0)
        img = st.decode_gif(src, smooth=True)[0][0]
        self.assertEqual(img.getpixel((0, 0)), (90, 140, 200))   # no black bars

    def test_broken_gif_gives_no_frames(self):
        bad = support.HOME / "gifs" / "retro-broken.gif"
        bad.write_bytes(b"GIF89a garbage")
        self.assertEqual(self.lib.frames(bad), [])

    def test_convert_upload_makes_32x32_loop(self):
        src = io.BytesIO()
        imgs = [Image.new("RGB", (120, 80), c) for c in ((255, 0, 0), (0, 0, 255))]
        imgs[0].save(src, "GIF", save_all=True, append_images=imgs[1:], duration=100, loop=0)
        src.seek(0)
        dest = support.VAR / "uploads" / "all" / "x.gif"
        self.assertEqual(st.convert_upload(src, dest), 2)
        with Image.open(dest) as im:
            self.assertEqual(im.size, (32, 32))
            self.assertEqual(im.n_frames, 2)

    def test_convert_upload_rejects_non_images(self):
        with self.assertRaises(Exception):
            st.convert_upload(io.BytesIO(b"hello"), support.VAR / "uploads" / "all" / "y.gif")


if __name__ == "__main__":
    unittest.main()
