import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests import support

support.load_plugins()
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.seasons import THEMES  # noqa: E402


def frames(name, ctx, secs=3, **params):
    return list(SCENES[name](ctx, secs, **params))


class ScenesTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def assert_frames(self, out, name):
        self.assertTrue(out, f"{name} showed nothing")
        for img, hold in out:
            self.assertEqual(img.size, (32, 32), name)
            self.assertEqual(img.mode, "RGB", name)
            self.assertGreater(hold, 0, name)

    def test_every_scene_renders_with_data(self):
        ctx = support.ctx_with(dict(support.SAMPLE_DATA, next_event={
            "title": "Standup", "start": (datetime.now() + timedelta(minutes=20)).isoformat()}))
        params = {"notify": {"text": "Doorbell", "flash": True, "sub": "front door"},
                  "message": {"text": "Hello there friend"}}
        for name in SCENES:
            with self.subTest(scene=name):
                self.assert_frames(frames(name, ctx, **params.get(name, {})), name)

    def test_every_seasonal_theme_has_a_scene(self):
        for theme in THEMES:
            self.assertIn(theme, SCENES)
            self.assertEqual(SCENES[theme].kind, "seasonal")

    def test_scenes_run_for_their_duration(self):
        ctx = support.ctx_with()
        for name in ("clock", "fire", "halloween", "on_air"):
            total = sum(h for _, h in frames(name, ctx, secs=4))
            self.assertAlmostEqual(total, 4, delta=0.3, msg=name)

    def test_data_scenes_skip_without_data(self):
        ctx = support.ctx_with()
        for name in ("weather", "now_playing", "calendar", "homelab", "tiles"):
            self.assertEqual(frames(name, ctx), [], name)

    def test_now_playing_skips_when_idle(self):
        ctx = support.ctx_with({"now_playing": {"title": "X", "state": "idle"}})
        self.assertEqual(frames("now_playing", ctx), [])

    def test_calendar_window(self):
        def ev(delta):
            return support.ctx_with({"next_event": {"title": "T", "start": (datetime.now() + delta).isoformat()}})
        self.assertTrue(frames("calendar", ev(timedelta(hours=2))))
        self.assertEqual(frames("calendar", ev(timedelta(hours=13))), [])
        self.assertEqual(frames("calendar", ev(timedelta(minutes=-30))), [])
        self.assertEqual(frames("calendar", support.ctx_with({"next_event": {"title": "T", "start": "garbage"}})), [])

    def test_calendar_accepts_timezone_offsets(self):
        start = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
        self.assertTrue(frames("calendar", support.ctx_with({"next_event": {"title": "T", "start": start}})))

    def test_homelab_states(self):
        ok = frames("homelab", support.ctx_with({"homelab": {"alerts": 0, "warnings": 0}}), secs=8)
        self.assertAlmostEqual(sum(h for _, h in ok), 8, delta=0.2)  # status page fills its time
        warn = frames("homelab", support.ctx_with({"homelab": {"alerts": 0, "warnings": 3}}))
        self.assertTrue(warn)
        red = frames("homelab", support.ctx_with({"homelab": {"alerts": 1, "names": ["plex"]}}))
        self.assertTrue(any(img.getpixel((5, 9))[0] > 150 for img, _ in red))  # red alert icon drawn

    def test_long_text_extends_scroll_time(self):
        ctx = support.ctx_with()
        short = sum(h for _, h in frames("notify", ctx, secs=3, text="Hi"))
        long = sum(h for _, h in frames("notify", ctx, secs=3, text="This message is far too long to fit"))
        self.assertLess(short, long)

    def test_weather_unknown_condition_still_draws(self):
        ctx = support.ctx_with({"weather": {"temp": 70, "condition": "volcanic"}})
        self.assertTrue(frames("weather", ctx))

    def test_gif_scene_plays_a_category_or_a_file(self):
        ctx = support.ctx_with()
        out = frames("gif", ctx, secs=1, category="space")
        self.assertTrue(out)
        self.assertIn("space-earth-spin.gif", ctx.label)
        self.assertEqual(frames("gif", ctx, category="nothing"), [])

    def test_clock_is_dim_red_at_night(self):
        ctx = support.ctx_with()
        with mock.patch.object(ctx, "now", return_value=datetime(2026, 10, 12, 23, 30)):
            img, _ = frames("clock", ctx, secs=0.25)[0]
        colors = [c for _, c in img.getcolors(1024) if c != (0, 0, 0)]
        self.assertTrue(all(r >= g and r >= b for r, g, b in colors))

    def test_every_clock_face_renders_and_fills_its_time(self):
        ctx = support.ctx_with({"weather": {"temp": 52}})
        for hour in (9, 13, 19, 23):
            for face in ("classic", "frame", "arcade", "sky"):
                with self.subTest(face=face, hour=hour), \
                        mock.patch.object(ctx, "now", return_value=datetime(2026, 10, 12, hour, 5)):
                    out = frames("clock", ctx, secs=4, face=face)
                    self.assert_frames(out, face)
                    self.assertAlmostEqual(sum(h for _, h in out), 4, delta=0.3)

    def test_clock_picks_from_the_ticked_faces(self):
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"clock": {"faces": ["sky"]}}})
        with mock.patch.object(ctx, "now", return_value=datetime(2026, 10, 12, 12, 0)):
            img, hold = frames("clock", ctx, secs=0.5)[0]
        self.assertLess(hold, 0.25)                # sky's frame rate, not classic's
        self.assertNotEqual(img.getpixel((0, 0)), (0, 0, 0))  # and its sky

    def test_busy_clock_faces_go_classic_at_night(self):
        ctx = support.ctx_with()
        with mock.patch.object(ctx, "now", return_value=datetime(2026, 10, 12, 23, 30)):
            for face in ("frame", "arcade"):
                self.assertEqual(frames("clock", ctx, secs=0.25, face=face)[0][1], 0.25, face)

    def test_birthday_uses_configured_name(self):
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"seasonal": {"birthday": {"month": 1, "day": 2, "name": "Pearl"}}}})
        self.assertTrue(frames("birthday", ctx, secs=2))


if __name__ == "__main__":
    unittest.main()
