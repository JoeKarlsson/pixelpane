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
                self.assertIn(f["type"], ("number", "range", "text", "list", "choices", "monthday", "secret"), p.name)
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


if __name__ == "__main__":
    unittest.main()
