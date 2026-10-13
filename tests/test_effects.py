import random
import unittest
from datetime import datetime

import numpy as np
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
        with self.assertLogs("pixelpane.plugin", level="ERROR"):
            plugin._guarded("file half.py", broken)
        self.assertEqual(len(plugin.WRAPPERS), before)
        self.assertNotIn("half_loaded", plugin.PLUGINS)
        plugin.ERRORS.clear()


class TransitionTest(unittest.TestCase):
    def test_fade_blends_from_the_scene_before(self):
        prev = Image.new("RGB", (32, 32), RED)
        out = run({"transition": "fade", "transition_seconds": 0.5}, prev=prev,
                  frames=solid(BLUE, n=10, hold=0.1))
        self.assertEqual(len(out), 9 + 1 + 5)     # 9 in-betweens, the frame then due, the rest
        mid = out[4][0].getpixel((5, 5))
        self.assertTrue(0 < mid[0] < 255 and 0 < mid[2] < 255, mid)
        self.assertEqual(out[9][0].getpixel((5, 5)), BLUE)
        self.assertAlmostEqual(sum(h for _, h in out), 1.0)   # the scene keeps its own length

    def test_the_new_scene_keeps_animating_during_the_transition(self):
        # a "GIF" whose frames alternate green and blue every 0.1 s
        frames = [(Image.new("RGB", (32, 32), (0, 255, 0) if k % 2 else BLUE), 0.1) for k in range(20)]
        out = run({"transition": "wipe", "transition_seconds": 1.0}, prev=Image.new("RGB", (32, 32), RED),
                  frames=frames)
        right = [img.getpixel((2, 5)) for img, _ in out[:19]]   # the left edge is the new scene early on
        self.assertIn((0, 255, 0), right)
        self.assertIn(BLUE, right)                               # it changed while the wipe ran
        self.assertAlmostEqual(sum(h for _, h in out), 2.0)

    def test_a_scene_shorter_than_the_transition_finishes_on_its_last_frame(self):
        out = run({"transition": "fade", "transition_seconds": 1.0}, prev=Image.new("RGB", (32, 32), RED),
                  frames=solid(BLUE, n=2, hold=0.1))
        self.assertEqual(out[-1][0].getpixel((5, 5)), BLUE)
        self.assertEqual(len(out), 19 + 1)

    def test_every_style_moves_from_old_to_new(self):
        prev = Image.new("RGB", (32, 32), RED)
        for style in ("wipe", "slide", "dissolve"):
            out = run({"transition": style}, prev=prev)
            colors = [support.pixels(img) for img, _ in out[:9]]
            self.assertIn(RED, colors[1], style)
            self.assertIn(BLUE, colors[5], style)
            self.assertEqual(colors[0] | colors[-1], {RED, BLUE}, style)

    def test_every_style_goes_from_the_old_scene_to_the_new(self):
        a, b = Image.new("RGB", (32, 32), RED), Image.new("RGB", (32, 32), BLUE)
        order = np.random.default_rng(1).permutation(32 * 32)
        dist = lambda img, ref: np.abs(np.asarray(img, int) - np.asarray(ref, int)).mean()  # noqa: E731
        for style in effects.STYLES:
            early, late = effects.blend(a, b, 0.1, style, order), effects.blend(a, b, 0.9, style, order)
            self.assertEqual(early.size, (32, 32), style)
            self.assertLess(dist(early, a), dist(late, a), style)
            self.assertLess(dist(late, b), dist(early, b), style)
        self.assertEqual(len(effects.STYLES), len(set(effects.STYLES)))
        self.assertIn("random", effects.TRANSITIONS)

    def test_random_picks_from_the_mix_and_never_repeats(self):
        c = ctx({"transition_mix": ["wipe", "dissolve", "fade"]})
        picks = [effects.pick_style(c, ["wipe", "dissolve", "fade"]) for _ in range(40)]
        self.assertEqual(set(picks), {"wipe", "dissolve", "fade"})
        self.assertTrue(all(a != b for a, b in zip(picks, picks[1:])))
        self.assertEqual({effects.pick_style(c, ["slide"]) for _ in range(5)}, {"slide"})   # one ticked: always it
        self.assertIn(effects.pick_style(c, []), effects.STYLES)                           # none ticked: any
        out = run({"transition": "random", "transition_mix": ["dissolve"]}, prev=Image.new("RGB", (32, 32), RED))
        self.assertEqual(colors(out[5][0]), {RED, BLUE})   # it really transitioned (dissolve: only old and new pixels)

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
        self.assertEqual(support.pixels(frames[0][0]), {BLUE})   # the cached GIF frame is untouched
        img = out[0][0]
        corner = img.crop((14, 25, 32, 32))
        self.assertIn((255, 255, 255), support.pixels(corner))
        self.assertIn((0, 0, 0), support.pixels(corner))          # the outline
        self.assertEqual(support.pixels(img.crop((0, 0, 14, 20))), {BLUE})

    def test_overlay_only_on_chosen_kinds(self):
        out = run({"overlay": "time", "transition": "none", "status_dots": False}, kind="widget")
        self.assertEqual(support.pixels(out[0][0]), {BLUE})

    def test_long_holds_are_split(self):
        out = run({"overlay": "time", "transition": "none"}, frames=solid(BLUE, n=1, hold=2.0))
        self.assertEqual([h for _, h in out], [0.5] * 4)

    def test_peek_shows_only_in_its_window(self):
        out = run({"overlay": "time", "overlay_mode": "peek", "transition": "none", "status_dots": False},
                  frames=solid(BLUE, n=1, hold=8.0))
        shown = [len(support.pixels(img)) > 1 for img, _ in out]
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

    def test_time_follows_the_clocks_24_hour_setting(self):
        c = FakeCtx("clock", settings={"hours": "24"}, now=datetime(2026, 10, 13, 21, 5))
        self.assertEqual(effects.overlay_text(c, "time", 0), "21:05")

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
            picks.append(c.pick(img, (18, 7)))
        self.assertEqual(picks[0], "bottom_right")
        self.assertEqual(set(picks[:20]), {"bottom_right"})     # no hopping within 10 s
        self.assertEqual(picks[-1], "top_left")                 # but it moves once it's clearly better


def colors(img, box=None):
    return set(map(tuple, np.asarray(img.crop(box) if box else img).reshape(-1, 3).tolist()))


TILES = {"tiles": {"items": [{"kind": "aqi", "value": 12},
                             {"kind": "temp", "value": 95, "label": "attic"},
                             {"kind": "temp", "value": 71, "label": "office"}]}}


class OverlaysTest(unittest.TestCase):
    """Several overlays, from config["plugins"]["effects"]["overlays"]."""

    def over(self, *items, data=None, kind="gif"):
        out = run({"transition": "none", "status_dots": False, "overlays": list(items)}, data=data, kind=kind)
        return out[0][0]

    def test_two_overlays_take_two_corners(self):
        img = self.over({"show": "time", "corner": "auto", "on": ["gif"]},
                        {"show": "date", "corner": "auto", "on": ["gif"]})
        white = (255, 255, 255)
        self.assertIn(white, colors(img, (0, 0, 32, 8)))     # one label on top
        self.assertIn(white, colors(img, (0, 24, 32, 32)))   # the other (too wide to share the row) below

    def test_fixed_corner_wins_and_auto_moves_out_of_its_way(self):
        img = self.over({"show": "time", "corner": "auto", "on": ["gif"]},
                        {"show": "text", "text": "hi", "corner": "top_left", "color": "#ff0000", "on": ["gif"]})
        self.assertIn(RED, colors(img, (0, 0, 10, 8)))
        self.assertNotIn((255, 255, 255), colors(img, (0, 0, 12, 8)))   # the time went elsewhere
        self.assertIn((255, 255, 255), colors(img))

    def test_reading_by_label_colored_by_value(self):
        c = ctx(data=TILES)
        o = {"show": "reading", "reading": "temp", "label": "attic", "color_by_value": True}
        text, color = effects.overlay_value(c, o, 0)
        self.assertEqual(text, "95F")
        self.assertGreater(color[0], color[2])             # hot: red, not blue
        self.assertEqual(effects.overlay_value(c, dict(o, label="office"), 0)[0], "71F")
        self.assertEqual(effects.overlay_value(c, dict(o, reading="aqi", label=""), 0)[0], "AQI12")
        self.assertIsNone(effects.overlay_value(c, dict(o, reading="co2"), 0))   # no such tile: nothing
        plain = effects.overlay_value(c, dict(o, color_by_value=False, color="#00ff00"), 0)[1]
        self.assertEqual(plain, (0, 255, 0))

    def test_own_text_and_box_style(self):
        img = self.over({"show": "text", "text": "hey", "corner": "bottom_left", "style": "box",
                         "color": "#ffffff", "on": ["gif"]})
        box = colors(img, (0, 25, 12, 32))
        self.assertIn((255, 255, 255), box)
        self.assertTrue(any(0 < b < 255 and r == 0 for r, g, b in box))   # dimmed blue behind the text

    def test_labels_never_overlap(self):
        data = {"tiles": {"items": [{"kind": "co2", "value": 1450}]}, "weather": {"temp": 55, "unit": "F"}}
        out = run({"transition": "none", "status_dots": False, "overlays": [
            {"show": "time", "size": "large", "corner": "auto", "on": ["gif"]},
            {"show": "reading", "reading": "co2", "corner": "auto", "on": ["gif"]},
            {"show": "temp", "corner": "auto", "on": ["gif"]},
            {"show": "date", "size": "large", "corner": "auto", "on": ["gif"]}]}, data=data)
        img = out[0][0]
        rows = [colors(img, (0, y, 32, y + 1)) for y in range(32)]
        self.assertTrue(any(len(r) > 1 for r in rows[:8]) and any(len(r) > 1 for r in rows[24:]))
        c = effects.Corner("auto")
        c.see(img, 0)
        wide = (30, 9)   # as wide as the panel: once the top row has a label, only the bottom is left
        self.assertEqual(c.pick(img, wide, [(0, 0, 18, 7)]).split("_")[0], "bottom")
        self.assertIsNone(c.pick(img, wide, [(0, 0, 18, 7), (0, 25, 18, 32)]))

    def test_large_size_is_bigger(self):
        small = effects.label_size("9:41", "tom-thumb")
        large = effects.label_size("9:41", "5x7")
        self.assertGreater(large[0], small[0])
        self.assertGreater(large[1], small[1])

    def test_only_on_its_kinds(self):
        img = self.over({"show": "time", "on": ["generative"]})
        self.assertEqual(colors(img), {BLUE})

    def test_old_single_overlay_still_works_until_overlays_is_saved(self):
        self.assertEqual(effects.overlays({"overlay": "time"})[0]["show"], "time")
        self.assertEqual(effects.overlays({"overlay": "time", "overlays": []}), [])
        self.assertEqual(effects.overlays({}), [])

    def test_schema_fills_defaults_and_refuses_junk(self):
        from pixelpane import schema
        clean = schema._plugins({"effects": {"overlays": [{"show": "reading", "reading": "co2"}]}})
        o = clean["effects"]["overlays"][0]
        self.assertEqual((o["corner"], o["mode"], o["on"], o["style"]), ("auto", "always", ["gif"], "outline"))
        for bad in ([{"show": "weather_radar"}], [{"show": "time", "spin": True}], [{"show": "text", "text": "x" * 20}],
                    [{"show": "time"}] * 5, "time"):
            with self.assertRaises(schema.ConfigError, msg=bad):
                schema._plugins({"effects": {"overlays": bad}})


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
            self.assertEqual(support.pixels(out[0][0]), {BLUE})


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
