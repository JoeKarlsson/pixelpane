import random
import unittest
from datetime import datetime

from PIL import Image

from tests import support

support.load_plugins()
from pixelpane import plugin  # noqa: E402
from pixelpane.app import Player  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.plugins import effects  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.testing import FakeCtx  # noqa: E402

RED, BLUE = (255, 0, 0), (0, 0, 255)


def solid(color, n=3, hold=0.1):
    return [(Image.new("RGB", (32, 32), color), hold) for _ in range(n)]


def ctx(settings=None, data=None):
    return FakeCtx("effects", data=data, settings=settings, now=datetime(2026, 10, 13, 9, 41))


def run(settings=None, frames=None, kind="gif", prev=None, data=None):
    info = {"scene": "x", "kind": kind, "prev": prev}
    return list(effects.effects(ctx(settings, data), iter(solid(BLUE) if frames is None else frames), info))


class RegistryTest(unittest.TestCase):
    def test_effects_registers_a_wrapper(self):
        self.assertIn(effects.effects, plugin.WRAPPERS)
        self.assertEqual(effects.effects.plugin, "effects")

    def test_disabled_plugin_leaves_frames_alone(self):
        frames = solid(BLUE)
        cfg = {"plugins": {"effects": {"enabled": False}}}
        out = plugin.wrap(cfg, ctx(), iter(frames), {"scene": "gif", "kind": "gif", "prev": Image.new("RGB", (32, 32))})
        self.assertEqual(list(out), frames)

    def test_a_plugin_that_fails_to_load_leaves_no_wrapper(self):
        before = len(plugin.WRAPPERS)

        def broken():
            p = plugin.Plugin("half_loaded", "x")
            p.frames(lambda c, f, i: f)
            raise RuntimeError("oops")
        plugin._guarded("file half.py", broken)
        self.assertEqual(len(plugin.WRAPPERS), before)
        self.assertNotIn("half_loaded", plugin.PLUGINS)
        plugin.ERRORS.clear()


class TransitionTest(unittest.TestCase):
    def test_fade_blends_from_the_scene_before(self):
        prev = Image.new("RGB", (32, 32), RED)
        out = run({"transition": "fade", "transition_seconds": 0.5}, prev=prev)
        self.assertEqual(len(out), 10 + 2)        # 9 in-betweens, then the 3 frames
        mid = out[4][0].getpixel((5, 5))
        self.assertTrue(0 < mid[0] < 255 and 0 < mid[2] < 255, mid)
        self.assertEqual(out[9][0].getpixel((5, 5)), BLUE)
        self.assertAlmostEqual(sum(h for _, h in out), 0.45 + 0.05 + 0.2)

    def test_every_style_moves_from_old_to_new(self):
        prev = Image.new("RGB", (32, 32), RED)
        for style in ("wipe", "slide", "dissolve"):
            out = run({"transition": style}, prev=prev)
            colors = [set(img.getdata()) for img, _ in out[:9]]
            self.assertIn(RED, colors[1], style)
            self.assertIn(BLUE, colors[5], style)
            self.assertEqual(colors[0] | colors[-1], {RED, BLUE}, style)

    def test_no_transition_without_a_frame_before_or_when_off(self):
        self.assertEqual(len(run({"transition": "fade"}, prev=None)), 3)
        self.assertEqual(len(run({"transition": "none"}, prev=Image.new("RGB", (32, 32)))), 3)

    def test_empty_scene_stays_empty(self):
        self.assertEqual(run({"transition": "fade"}, frames=[], prev=Image.new("RGB", (32, 32))), [])


class OverlayTest(unittest.TestCase):
    def test_time_overlay_drawn_on_a_copy(self):
        frames = solid(BLUE)
        out = run({"overlay": "time", "overlay_corner": "bottom_right", "transition": "none",
                   "status_dots": False}, frames=frames)
        self.assertEqual(set(frames[0][0].getdata()), {BLUE})   # the cached GIF frame is untouched
        img = out[0][0]
        corner = img.crop((14, 25, 32, 32))
        self.assertIn((255, 255, 255), set(corner.getdata()))
        self.assertIn((0, 0, 0), set(corner.getdata()))          # the outline
        self.assertEqual(set(img.crop((0, 0, 14, 20)).getdata()), {BLUE})

    def test_overlay_only_on_chosen_kinds(self):
        out = run({"overlay": "time", "transition": "none", "status_dots": False}, kind="widget")
        self.assertEqual(set(out[0][0].getdata()), {BLUE})

    def test_long_holds_are_split(self):
        out = run({"overlay": "time", "transition": "none"}, frames=solid(BLUE, n=1, hold=2.0))
        self.assertEqual([h for _, h in out], [0.5] * 4)

    def test_peek_shows_only_in_its_window(self):
        out = run({"overlay": "time", "overlay_mode": "peek", "transition": "none", "status_dots": False},
                  frames=solid(BLUE, n=1, hold=8.0))
        shown = [len(set(img.getdata())) > 1 for img, _ in out]
        self.assertEqual(shown, [False] * 4 + [True] * 6 + [False] * 6)

    def test_texts(self):
        c = ctx(data={"weather": {"temp": 51.6, "unit": "F"},
                      "next_event": {"title": "Standup", "start": "2026-10-13T10:00:00"}})
        self.assertEqual(effects.overlay_text(c, "time", 0), "9:41")
        self.assertEqual(effects.overlay_text(c, "date", 0), "OCT 13")
        self.assertEqual(effects.overlay_text(c, "time_date", 6), "OCT 13")
        self.assertEqual(effects.overlay_text(c, "temp", 0), "52F")
        self.assertEqual(effects.overlay_text(c, "meeting", 0), "IN 19M")
        self.assertEqual(effects.overlay_text(ctx(), "meeting", 0), "9:41")   # nothing soon: the time

    def test_auto_corner_is_dark_and_stays_put(self):
        def frame(dark):
            img = Image.new("RGB", (32, 32), (200, 200, 200))
            box = {"top_left": (0, 0, 18, 8), "bottom_right": (14, 24, 32, 32)}[dark]
            img.paste((0, 0, 0), box)
            return img, 0.5
        c = effects.Corner("auto")
        picks = []
        for i in range(30):   # dark bottom right for a while, then dark top left
            img, _ = frame("bottom_right" if i < 4 else "top_left")
            c.see(img, i * 0.5)
            picks.append(c.pick(img, "9:41"))
        self.assertEqual(picks[0], "bottom_right")
        self.assertEqual(set(picks[:20]), {"bottom_right"})     # no hopping within 10 s
        self.assertEqual(picks[-1], "top_left")                 # but it moves once it's clearly better


class StatusDotsTest(unittest.TestCase):
    def test_dots_light_the_top_edge_and_blink(self):
        data = {"status": {"dots": [{"color": "#00ffff"}, {"color": "#ff0000", "blink": True}]}}
        out = run({"transition": "none"}, frames=solid(BLUE, n=1, hold=1.0), kind="widget", data=data)
        on, off = out[0][0], out[1][0]
        self.assertEqual(on.getpixel((31, 0)), (0, 255, 255))
        self.assertEqual(on.getpixel((29, 0)), (255, 0, 0))
        self.assertEqual(off.getpixel((31, 0)), (0, 255, 255))
        self.assertEqual(off.getpixel((29, 0)), BLUE)

    def test_no_dots_on_notifications_or_when_off(self):
        data = {"status": {"dots": [{"color": "#00ffff"}]}}
        for settings, kind in (({}, "interrupt"), ({"status_dots": False}, "widget")):
            out = run(dict(settings, transition="none"), kind=kind, data=data)
            self.assertEqual(out[0][0].getpixel((31, 0)), BLUE)

    def test_junk_status_is_ignored(self):
        for junk in ({"dots": "x"}, {"dots": [1, None]}, ["x"]):
            out = run({"transition": "none"}, kind="widget", data={"status": junk})
            self.assertEqual(set(out[0][0].getdata()), {BLUE})


class PlayerTest(unittest.TestCase):
    def test_player_fades_between_scenes_and_preview_sees_it(self):
        support.reset()
        state = State()
        state.update_config({"plugins": {"effects": {"transition": "fade", "transition_seconds": 0.2}}})
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        shown = []
        player.display.show = lambda img: shown.append(img.getpixel((5, 5)))

        def scene(color):
            def gen():
                for img, _ in solid(color, n=2, hold=0.01):
                    yield img, 0.01
            return gen()
        player.play("a", scene(RED), scene="clock")
        player.play("b", scene(BLUE), scene="clock")
        self.assertEqual(shown[:2], [RED, RED])
        self.assertEqual(shown[-1], BLUE)
        self.assertTrue(any(c not in (RED, BLUE) for c in shown[2:]), shown)
        self.assertEqual(state.last_frame.getpixel((5, 5)), BLUE)


if __name__ == "__main__":
    unittest.main()
