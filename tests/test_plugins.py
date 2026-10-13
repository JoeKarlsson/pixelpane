from datetime import datetime
import random
import textwrap
import unittest

from tests import support

support.load_plugins()
from pixelpane import plugin  # noqa: E402
from pixelpane.app import Player, health  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.plugin import PLUGINS, SCENES  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402


class RegistryTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_builtins_and_their_scenes(self):
        self.assertEqual(set(plugin.BUILTIN) - set(PLUGINS), set())
        for name, fn in SCENES.items():
            self.assertIn(fn.plugin, PLUGINS, name)
            self.assertIn(name, PLUGINS[fn.plugin].scenes)
        self.assertEqual(SCENES["homelab"].plugin, "homelab")
        self.assertEqual(SCENES["halloween"].plugin, "seasonal")
        self.assertIn("weather", PLUGINS["weather"].data)

    def test_every_plugin_explains_itself_and_its_settings(self):
        for p in PLUGINS.values():
            if p.name not in plugin.BUILTIN:
                continue
            self.assertGreater(len(p.about), 40, p.name)
            for f in p.fields:
                self.assertIn(f["key"].split(".")[0], p.defaults, (p.name, f["key"]))
                self.assertIn(f["type"], ("number", "range", "text", "list", "choices", "monthday", "secret", "select", "toggle", "color", "items"), p.name)
        rows = {r["name"]: r for r in plugin.describe({})}
        self.assertEqual(rows["seasonal"]["fields"][1]["type"], "monthday")
        self.assertEqual(rows["weather"]["data"], {"weather": 180})

    def test_settings_merge_defaults_and_config(self):
        cfg = {"plugins": {"generative": {"scenes": ["fire"]}}}
        s = plugin.settings(cfg, "generative")
        self.assertEqual((s["scenes"], s["enabled"]), (["fire"], True))
        self.assertEqual(plugin.settings({}, "seasonal")["holiday_share"], 0.7)

    def test_data_ttl_follows_enabled_plugins(self):
        self.assertEqual(plugin.data_ttl({}, "homelab"), 60)
        self.assertEqual(plugin.data_ttl({"data_ttl_minutes": {"homelab": 5}}, "homelab"), 5)
        self.assertIsNone(plugin.data_ttl({"plugins": {"homelab": {"enabled": False}}}, "homelab"))
        self.assertIsNone(plugin.data_ttl({}, "nope"))


class DisableTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.state.update_config({"plugins": {"homelab": {"enabled": False}, "generative": {"enabled": False}}})
        self.player = Player(self.state, FakeDisplay(), GifLibrary(self.state, random.Random(1)), random.Random(1))
        self.client = create_app(self.state, GifLibrary(self.state, random.Random(1)), health).test_client()

    def test_disabled_scenes_never_play(self):
        self.state.put_data("homelab", {"alerts": 0})
        self.assertIsNone(self.player.resolve("homelab"))
        self.assertIsNone(self.player.resolve("generative"))
        self.assertIsNone(self.player.resolve("fire"))
        self.assertIsNotNone(self.player.resolve("clock"))

    def test_api_hides_and_rejects_disabled_plugins(self):
        s = self.client.get("/api/state").get_json()
        self.assertNotIn("homelab", s["scenes"].get("widget", []))
        self.assertNotIn("generative", s["scenes"])
        rows = {p["name"]: p for p in s["plugins"]}
        self.assertFalse(rows["homelab"]["enabled"])
        self.assertTrue(rows["clock"]["enabled"])
        self.assertEqual(self.client.post("/api/play", json={"scene": "homelab"}).status_code, 400)
        self.assertEqual(self.client.post("/api/data/homelab", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/pin", json={"scene": "fire"}).status_code, 400)

    def test_reenable_through_config_api(self):
        r = self.client.put("/api/config", json={"plugins": {"homelab": {"enabled": True}}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/api/data/homelab", json={"alerts": 0}).status_code, 200)


class UserPluginTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.dir = support.ROOT / "user-plugins"
        self.dir.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.dir.glob("*.py"):
            f.unlink()
        for name in ("hello",):
            PLUGINS.pop(name, None)
            SCENES.pop(name, None)

    def test_user_plugin_file_is_loaded_and_plays(self):
        (self.dir / "hello.py").write_text(textwrap.dedent('''
            from pixelpane import gfx
            from pixelpane.kit import scroll_text, ticks
            from pixelpane.plugin import Plugin

            plugin = Plugin("hello", "Says hello", data={"greeting": 30}, defaults={"color": "#ff5fa2"})

            @plugin.scene("hello")
            def hello(ctx, secs):
                text = (ctx.data("greeting") or {}).get("text", "HELLO")
                for i, t in ticks(secs, 10):
                    img = gfx.blank()
                    scroll_text(img, 12, text, gfx.hex_color(ctx.settings("hello")["color"]), "5x7", t)
                    yield img, 0.1
        '''))
        (self.dir / "broken.py").write_text("raise RuntimeError('boom')\n")
        with self.assertLogs("pixelpane.plugin", level="ERROR"):
            plugin.load(user_dir=self.dir)
        self.assertIn("hello", PLUGINS)
        state = State()
        state.put_data("greeting", {"text": "HI"})
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        name, gen, _ = player.resolve("hello", {"seconds": 1})
        frames = list(gen)
        self.assertEqual((name, len(frames)), ("hello", 10))


class PluginSystemTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.dir = support.ROOT / "system-plugins"
        self.dir.mkdir(exist_ok=True)
        plugin.ERRORS.clear()

    def tearDown(self):
        for f in self.dir.glob("*.py"):
            f.unlink()
        for name in ("fancy", "flaky"):
            PLUGINS.pop(name, None)
        for name in ("fancy", "sparkle"):
            SCENES.pop(name, None)
            plugin.PICKERS.pop(name, None)

    def test_collisions_and_newer_api_are_refused_cleanly(self):
        (self.dir / "a_clock.py").write_text("from pixelpane.plugin import Plugin\nPlugin('clock')\n")
        (self.dir / "b_steal.py").write_text(textwrap.dedent('''
            from pixelpane.plugin import Plugin
            p = Plugin("fancy")
            @p.scene("sparkle")
            def sparkle(ctx, secs):
                yield from ()
            @p.scene("weather")   # taken by the weather plugin
            def mine(ctx, secs):
                yield from ()
        '''))
        (self.dir / "c_future.py").write_text("from pixelpane.plugin import Plugin\nPlugin('flaky', api=99)\n")
        with self.assertLogs("pixelpane.plugin", level="ERROR"):
            plugin.load(user_dir=self.dir, entry_points=False)
        self.assertEqual(PLUGINS["clock"].source, "built-in")
        self.assertEqual(SCENES["weather"].plugin, "weather")
        self.assertNotIn("fancy", PLUGINS)        # half-registered plugin is rolled back
        self.assertNotIn("sparkle", SCENES)
        self.assertNotIn("flaky", PLUGINS)
        self.assertEqual([e["source"] for e in plugin.ERRORS], ["file a_clock.py", "file b_steal.py", "file c_future.py"])
        self.assertIn("plugin API 99", plugin.ERRORS[2]["error"])

    def test_declared_pinning_params_and_pickers(self):
        self.assertTrue(plugin.pinnable("clock"))
        self.assertTrue(plugin.pinnable("seasonal"))
        self.assertTrue(plugin.pinnable("moon"))
        self.assertFalse(plugin.pinnable("gif"))
        self.assertFalse(plugin.pinnable("notify"))
        self.assertEqual(plugin.check_params("message", {"text": "HI"}), {"text": "HI"})
        with self.assertRaises(ValueError):
            plugin.check_params("gif", {"path": "/etc/passwd"})
        state = State()
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        name, _, _ = player.resolve("generative")
        self.assertIn(name, PLUGINS["generative"].defaults["scenes"])
        self.assertIn(player.resolve("seasonal")[0], PLUGINS["seasonal"].scenes)

    def test_testing_helper_renders_a_scene(self):
        from pixelpane.testing import render
        frames = render("tiles", 1, data={"tiles": {"items": [{"icon": "bell", "text": "HI", "level": 0.5}]}})
        self.assertGreaterEqual(len(frames), 10)
        self.assertEqual(frames[0][0].size, (32, 32))
        self.assertEqual(render("tiles", 1), [])                 # no data: skips
        self.assertTrue(render("message", 1, params={"text": "YO"}))

    def test_fieldless_settings_keep_their_type(self):
        from pixelpane import schema
        with self.assertRaises(schema.ConfigError):
            schema.validate({"plugins": {"seasonal": {"holiday_share": "lots"}}})
        self.assertEqual(schema.validate({"plugins": {"gifs": {"theme_share": 0.5}}})["plugins"]["gifs"],
                         {"theme_share": 0.5})

    def test_tasks_restart_after_a_crash_and_stop_when_turned_off(self):
        import threading
        import time
        p = plugin.Plugin("flaky", "Crashes once")
        runs = []

        def poll(ctx, stop):
            runs.append(1)
            if len(runs) == 1:
                raise RuntimeError("first run fails")
            stop.wait()

        p.task(poll)
        state = State()
        ctx = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1)).ctx
        stop = threading.Event()
        sup = plugin.Supervisor(p, poll, ctx, stop)
        with self.assertLogs("pixelpane.plugin", level="ERROR"):
            sup.check()
            sup.thread.join(2)
        self.assertEqual(sup.status()["crashes"], 1)
        sup.restart_at = 0            # skip the back-off pause
        sup.check()
        time.sleep(0.1)
        self.assertTrue(sup.status()["running"])
        state.update_config({"plugins": {"flaky": {"enabled": False}}})
        sup.check()
        sup.thread.join(2)
        self.assertFalse(sup.status()["running"])
        self.assertEqual(len(runs), 2)


class DocsExampleTest(unittest.TestCase):
    """The example in docs/PLUGINS.md must keep working as written."""

    def setUp(self):
        support.reset()
        self.dir = support.ROOT / "doc-plugins"
        self.dir.mkdir(exist_ok=True)

    def tearDown(self):
        PLUGINS.pop("countdown", None)
        SCENES.pop("countdown", None)

    def test_countdown_example_runs(self):
        from pathlib import Path
        doc = (Path(__file__).parents[1] / "docs" / "PLUGINS.md").read_text()
        code = doc.split("```python\n", 1)[1].split("```", 1)[0]
        (self.dir / "countdown.py").write_text(code)
        plugin.load(user_dir=self.dir)
        state = State()
        state.update_config({"plugins": {"countdown": {"date": "2099-01-01", "label": "FAR AWAY"}}})
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        name, gen, _ = player.resolve("countdown", {"seconds": 2})
        frames = [img for img, _ in gen]
        self.assertEqual(len(frames), 20)
        self.assertGreater(len({f.tobytes() for f in frames}), 1)   # it animates
        state.update_config({"plugins": {"countdown": {"date": None}}})
        self.assertEqual(list(player.resolve("countdown")[1]), [])  # nothing set: skips


class ClockColorTest(unittest.TestCase):
    def colors(self, hour, **settings):
        from pixelpane.testing import render
        frames = render("clock", 0.5, settings={"faces": ["classic"], **settings}, now=datetime(2026, 10, 12, hour, 30))
        return support.pixels(frames[0][0])

    def test_fixed_color_by_day_and_dimmed_at_night(self):
        self.assertIn((0, 255, 0), self.colors(12, color_mode="fixed", color="#00ff00"))
        self.assertIn((0, 102, 0), self.colors(23, color_mode="fixed", color="#00ff00"))
        self.assertNotIn((0, 255, 0), self.colors(12))   # the default follows the time of day


if __name__ == "__main__":
    unittest.main()
