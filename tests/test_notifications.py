"""Notification styles, and the triggers plugin's reminders and watches."""
import unittest
from datetime import datetime

from tests import support

support.load_plugins()
from pixelpane import schema  # noqa: E402
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.plugins import alerts, triggers  # noqa: E402
from pixelpane.testing import render  # noqa: E402
from pixelpane.web import create_app  # noqa: E402


def moving(frames):
    return len({img.tobytes() for img, _ in frames})


class StyleTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_every_style_draws_and_moves(self):
        for style in alerts.STYLES:
            frames = render("notify", 3, params={"text": "Doorbell", "icon": "bell", "color": "#f59e0b", "style": style})
            self.assertGreater(moving(frames), 10, style)
            self.assertEqual(frames[0][0].size, (32, 32))

    def test_banner_text_reads_on_a_light_bar(self):
        frames = render("notify", 3, params={"text": "HI", "icon": "mail", "color": "#ffffff", "style": "banner"})
        img = frames[20][0]
        bar = [img.getpixel((x, y)) for x in range(11, 32) for y in range(0, 12)]
        self.assertIn((0, 0, 0), bar)          # dark text on the white bar
        self.assertIn((255, 255, 255), bar)

    def test_settings_pick_the_default_style_and_color(self):
        settings = {"style": "ticker", "color": "#ff0000"}
        ticker = render("notify", 2, settings=settings, params={"text": "HELLO"})
        plain = render("notify", 2, params={"text": "HELLO", "style": "ticker", "color": "#ff0000"})
        self.assertEqual([i.tobytes() for i, _ in ticker[:15]], [i.tobytes() for i, _ in plain[:15]])

    def test_ticker_runs_long_enough_to_read(self):
        frames = render("notify", 3, params={"text": "SNOW EMERGENCY DECLARED", "style": "ticker"})
        self.assertGreater(sum(h for _, h in frames), 10)

    def test_pulse_draws_a_border(self):
        frames = render("notify", 2, settings={"pulse": True}, params={"text": "HI", "color": "#00ff00"})
        self.assertGreater(frames[5][0].getpixel((0, 16))[1], 50)


class NotifyApiTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        from pixelpane.state import GifLibrary, State
        import random
        self.state = State()
        self.client = create_app(self.state, GifLibrary(self.state, random.Random(1)), lambda s: {}).test_client()

    def test_style_passes_through_and_defaults_stay_unset(self):
        r = self.client.post("/api/notify", json={"text": "Hi", "style": "burst"})
        self.assertEqual(r.status_code, 200)
        n = self.state.notifications[-1]
        self.assertEqual(n["style"], "burst")
        self.assertNotIn("color", n)           # left to the alerts settings
        self.assertNotIn("seconds", n)
        self.assertEqual(self.client.post("/api/notify", json={"text": "Hi", "style": "explode"}).status_code, 400)
        self.client.post("/api/notify", json={"text": "Hi", "style": "default"})
        self.assertNotIn("style", self.state.notifications[-1])

    def test_scene_accepts_the_queued_notification(self):
        self.client.post("/api/notify", json={"text": "Hi", "style": "banner", "color": "#123456", "flash": True})
        n = dict(self.state.notifications[-1])
        frames = list(SCENES["notify"](support.ctx_with(), 2, **n))
        self.assertTrue(frames)


class ReminderTest(unittest.TestCase):
    R = {"text": "Bins out", "time": "19:00", "days": ["tue"], "icon": "bell", "color": "#ffffff", "style": "default"}

    def test_fires_once_at_the_time_on_its_days(self):
        fired = {}
        tue = datetime(2026, 10, 13, 18, 59)          # a Tuesday
        self.assertEqual(triggers.due_reminders([self.R], tue, fired), [])
        self.assertEqual(len(triggers.due_reminders([self.R], tue.replace(hour=19, minute=0, second=10), fired)), 1)
        self.assertEqual(triggers.due_reminders([self.R], tue.replace(hour=19, minute=3), fired), [])   # not twice
        self.assertEqual(triggers.due_reminders([self.R], tue.replace(hour=19, minute=30), {}), [])     # too late
        wed = datetime(2026, 10, 14, 19, 1)
        self.assertEqual(triggers.due_reminders([self.R], wed, {}), [])                                 # wrong day
        self.assertEqual(len(triggers.due_reminders([self.R], datetime(2026, 10, 20, 19, 1), fired)), 1)  # next week

    def test_the_task_raises_it_and_remembers_across_a_restart(self):
        import threading
        support.reset()
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"triggers": {"reminders": [dict(self.R, days=["tue"])]}}})
        ctx.now = lambda: datetime(2026, 10, 13, 19, 2)
        for _ in range(2):                      # the second run is a restart: it must not fire again
            stop = threading.Event()
            stop.set()                          # one round, then return
            triggers.run(ctx, stop)
        self.assertEqual([n["text"] for n in ctx.state.notifications], ["Bins out"])

    def test_note_uses_the_reminder_look(self):
        n = triggers.note(dict(self.R, style="burst"), "Bins out")
        self.assertEqual((n["style"], n["icon"]), ("burst", "bell"))
        self.assertNotIn("style", triggers.note(self.R, "x"))


class WatchTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def ctx(self, **data):
        return support.ctx_with(data)

    def test_fires_on_the_edge_only(self):
        w = {"when": "tile.aqi", "op": "above", "value": "150", "text": "Air {value} {label}",
             "icon": "alert", "color": "#ff0000", "cooldown": 0}
        watcher = triggers.Watcher()
        ctx = self.ctx(tiles={"items": [{"kind": "aqi", "value": 40, "label": "outside"}]})
        self.assertEqual(watcher.check(ctx, [w], 0), [])                       # learns: false
        ctx.state.put_data("tiles", {"items": [{"kind": "aqi", "value": 180, "label": "outside"}]})
        out = watcher.check(ctx, [w], 10)
        self.assertEqual([n["text"] for n in out], ["Air 180 outside"])
        self.assertEqual(watcher.check(ctx, [w], 20), [])                      # still true: quiet
        ctx.state.put_data("tiles", {"items": [{"kind": "aqi", "value": 30}]})
        watcher.check(ctx, [w], 30)
        ctx.state.put_data("tiles", {"items": [{"kind": "aqi", "value": 200}]})
        self.assertEqual(len(watcher.check(ctx, [w], 40)), 1)                  # true again

    def test_already_true_at_start_does_not_fire(self):
        w = {"when": "weather.condition", "op": "is", "value": "snowy", "cooldown": 0}
        ctx = self.ctx(weather={"temp": 20, "condition": "snowy"})
        self.assertEqual(triggers.Watcher().check(ctx, [w], 0), [])

    def test_cooldown(self):
        w = {"when": "weather.temp", "op": "below", "value": "32", "cooldown": 60, "text": "Freezing"}
        watcher = triggers.Watcher()
        ctx = self.ctx(weather={"temp": 40})
        watcher.check(ctx, [w], 0)
        for t, temp, want in ((100, 30, 1), (200, 40, 0), (300, 28, 0), (5000, 50, 0), (5100, 20, 1)):
            ctx.state.put_data("weather", {"temp": temp})
            self.assertEqual(len(watcher.check(ctx, [w], t)), want, (t, temp))

    def test_label_filter_and_changes(self):
        w = {"when": "tile.temp", "label": "attic", "op": "above", "value": "90", "cooldown": 0}
        ctx = self.ctx(tiles={"items": [{"kind": "temp", "value": 95, "label": "office"}]})
        watcher = triggers.Watcher()
        watcher.check(ctx, [w], 0)
        self.assertEqual(watcher.check(ctx, [w], 1), [])    # the office is hot, the attic isn't reporting
        song = {"when": "now_playing.title", "op": "changes", "cooldown": 0, "text": "Now: {value}", "icon": "music"}
        ctx.state.put_data("now_playing", {"title": "One", "state": "playing"})
        self.assertEqual(watcher.check(ctx, [song], 2), [])
        ctx.state.put_data("now_playing", {"title": "Two", "state": "playing"})
        self.assertEqual([n["text"] for n in watcher.check(ctx, [song], 3)], ["Now: Two"])

    def test_calendar_minutes(self):
        w = {"when": "calendar.minutes", "op": "below", "value": "5", "cooldown": 0, "text": "{label} in {value}m"}
        ctx = self.ctx(next_event={"title": "Standup", "start": "2026-10-13T10:00:00"})
        ctx.now = lambda: datetime(2026, 10, 13, 9, 50)
        watcher = triggers.Watcher()
        watcher.check(ctx, [w], 0)
        ctx.now = lambda: datetime(2026, 10, 13, 9, 56)
        self.assertEqual([n["text"] for n in watcher.check(ctx, [w], 1)], ["Standup in 4m"])


class SchemaTest(unittest.TestCase):
    def test_bad_triggers_are_refused(self):
        ok = {"plugins": {"triggers": {"reminders": [{"text": "Bins", "time": "19:00", "days": ["tue"]}]}}}
        clean = schema.validate(ok) if hasattr(schema, "validate") else None
        if clean is not None:
            r = clean["plugins"]["triggers"]["reminders"][0]
            self.assertEqual(r["icon"], "bell")              # filled from the sub-field default
        for bad in ({"time": "7pm"}, {"days": ["funday"]}, {"icon": "dragon"}, {"color": "red"}, {"nope": 1}):
            cfg = {"plugins": {"triggers": {"reminders": [dict({"text": "x"}, **bad)]}}}
            with self.assertRaises(schema.ConfigError, msg=bad):
                schema.validate(cfg)
        with self.assertRaises(schema.ConfigError):
            schema.validate({"plugins": {"triggers": {"watches": [{"when": "moon.phase"}]}}})
        with self.assertRaises(schema.ConfigError):
            schema.validate({"plugins": {"alerts": {"style": "explode"}}})


if __name__ == "__main__":
    unittest.main()
