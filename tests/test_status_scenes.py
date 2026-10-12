"""Status scenes must always move (no static status screens), plus album art and homelab pages."""
import io
import time
import unittest
from datetime import datetime, timedelta

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane import gfx, kit  # noqa: E402
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.plugins.homelab import lab_pages  # noqa: E402
from pixelpane.plugins.now_playing import ArtCache, album_art  # noqa: E402
from pixelpane.plugins.weather import WEATHER_ICON  # noqa: E402

LAB = {"alerts": 0, "warnings": 0, "checks_total": 159, "checks_passing": 158,
       "hosts": [{"name": "P1", "cpu": 9, "temp": 115}, {"name": "P2", "cpu": 82, "temp": 111}],
       "nas": {"used_pct": 69, "used_tb": 36, "up_mbs": 20, "down_mbs": 3},
       "net": {"wan_ms": 5, "dns_queries": 398696, "blocked_pct": 1},
       "ups": [{"battery": 100, "load": 15, "status": "Online"}, {"battery": 64, "load": 12, "status": "On Battery"}],
       "plex": {"watching": 2}}


def distinct_frames(name, ctx, secs=2.0, **params):
    return len({img.tobytes() for img, _ in SCENES[name](ctx, secs, **params)})


class AlwaysAnimatedTest(unittest.TestCase):
    """Short text never scrolls, so any change between frames is real animation."""

    def setUp(self):
        support.reset()

    def test_every_icon_moves(self):
        for name in gfx.ICONS + ["air"]:
            frames = set()
            for k in range(20):
                img = gfx.blank()
                kit.animated_icon(img, name, (12, 8), k * 0.1, 0.5)
                frames.add(img.tobytes())
            self.assertGreater(len(frames), 1, f"icon {name} never moves")

    def test_tiles_animate_even_with_short_text(self):
        for icon in ("air", "thermometer", "washer", "info", "package", "nonexistent"):
            ctx = support.ctx_with({"tiles": {"items": [{"icon": icon, "text": "OK", "level": 0.5}]}})
            self.assertGreater(distinct_frames("tiles", ctx), 1, icon)

    def test_weather_animates_in_every_condition(self):
        for cond in WEATHER_ICON:
            ctx = support.ctx_with({"weather": {"temp": 50, "condition": cond}})
            self.assertGreater(distinct_frames("weather", ctx, 3), 1, cond)

    def test_other_status_scenes_animate(self):
        soon = (datetime.now() + timedelta(minutes=40)).isoformat()
        ctx = support.ctx_with({"homelab": LAB, "next_event": {"title": "Hi", "start": soon},
                                "now_playing": {"title": "Hi", "state": "playing"}})
        for name, params in (("clock", {}), ("calendar", {}), ("homelab", {}), ("now_playing", {}),
                             ("notify", {"text": "Hi", "icon": "mail"}), ("on_air", {})):
            self.assertGreater(distinct_frames(name, ctx, **params), 1, name)


class HomelabTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_pages_follow_the_data(self):
        self.assertEqual([p.__name__ for p in lab_pages(LAB)],
                         ["_lab_status", "_lab_hosts", "_lab_nas", "_lab_net", "_lab_ups", "_lab_plex"])
        self.assertEqual([p.__name__ for p in lab_pages({"alerts": 0})], ["_lab_status"])
        bare = list(SCENES["homelab"](support.ctx_with({"homelab": {"alerts": 0}}), 24))
        self.assertAlmostEqual(sum(h for _, h in bare), 24, delta=0.2)

    def test_every_page_renders(self):
        ctx = support.ctx_with({"homelab": dict(LAB, alerts=1, names=["plex"], warnings=2)})
        for img, _ in SCENES["homelab"](ctx, 30):
            self.assertEqual(img.size, (32, 32))

    def test_alerts_come_first(self):
        ctx = support.ctx_with({"homelab": dict(LAB, alerts=2, names=["plex", "nas"])})
        first, _ = next(SCENES["homelab"](ctx, 24))
        self.assertGreater(first.getpixel((5, 9))[0], 150)  # red alert icon on the first frame


class AlbumArtTest(unittest.TestCase):
    URL = "http://homeassistant.local:8123/api/media_player_proxy/media_player.office?token=x"

    def setUp(self):
        support.reset()
        buf = io.BytesIO()
        Image.new("RGB", (300, 200), (200, 30, 120)).save(buf, "PNG")
        self.png = buf.getvalue()

    def cache(self, ctx, data=None):
        ctx.state.update_config({"plugins": {"now_playing": {"art_hosts": ["http://homeassistant.local:8123/"]}}})
        album_art(ctx, None)  # creates the cache
        ctx.art_cache = ctx.store("now_playing")["art"]
        calls = []

        def fetch(url):
            calls.append(url)
            return self.png if data is None else data
        ctx.art_cache.fetch = fetch
        return calls

    def wait(self, ctx, url):
        end = time.time() + 3
        while time.time() < end and url in ctx.art_cache.pending | {None} - set(ctx.art_cache.images):
            time.sleep(0.02)
        for _ in range(100):
            if url in ctx.art_cache.images:
                return ctx.art_cache.images[url]
            time.sleep(0.02)

    def test_art_is_fetched_once_and_shrunk(self):
        ctx = support.ctx_with()
        calls = self.cache(ctx)
        self.assertIsNone(album_art(ctx, self.URL))   # starts the fetch
        img = self.wait(ctx, self.URL)
        self.assertEqual(img.size, (32, 32))
        self.assertIs(album_art(ctx, self.URL), img)
        self.assertEqual(calls, [self.URL])

    def test_only_home_assistant_urls_are_fetched(self):
        ctx = support.ctx_with()
        calls = self.cache(ctx)
        for url in ("http://evil.example/x.png", "file:///etc/passwd", None, 42):
            self.assertIsNone(album_art(ctx, url))
        time.sleep(0.1)
        self.assertEqual(calls, [])

    def test_bad_art_means_no_art(self):
        ctx = support.ctx_with()
        self.cache(ctx, data=b"not an image")
        album_art(ctx, self.URL)
        self.assertIsNone(self.wait(ctx, self.URL))

    def test_now_playing_shows_the_art_first(self):
        ctx = support.ctx_with({"now_playing": {"title": "Song", "state": "playing", "art": self.URL}})
        self.cache(ctx)
        album_art(ctx, self.URL)
        self.wait(ctx, self.URL)
        first, _ = next(SCENES["now_playing"](ctx, 10))
        self.assertEqual(first.getpixel((5, 5)), album_art(ctx, self.URL).getpixel((5, 5)))

    def test_cache_is_bounded(self):
        cache = ArtCache(lambda: ["http://homeassistant.local:8123/"], fetch=lambda url: self.png)
        for k in range(25):
            cache._load(f"http://homeassistant.local:8123/{k}")
        self.assertEqual(len(cache.images), 20)


if __name__ == "__main__":
    unittest.main()
