import random
import threading
import time
import unittest
from unittest import mock

from tests import support

support.load_plugins()
from pixelpane.app import Player  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402


class ResolveTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.player = Player(self.state, FakeDisplay(), GifLibrary(self.state, random.Random(1)), random.Random(1))

    def test_dwell_and_explicit_seconds(self):
        self.assertEqual(self.player.resolve("clock")[2], self.state.config["dwell"]["clock"])
        self.assertEqual(self.player.resolve("clock", {"seconds": 3})[2], 3)

    def test_seasonal_picks_from_active_themes(self):
        with mock.patch.object(self.state, "themes", return_value=["autumn", "halloween"]):
            picked = {self.player.resolve("seasonal")[0] for _ in range(40)}
        self.assertEqual(picked, {"autumn", "halloween"})
        with mock.patch.object(self.state, "themes", return_value=["spring", "birthday"]):
            self.assertEqual({self.player.resolve("seasonal")[0] for _ in range(10)}, {"birthday"})

    def test_generative_and_categories(self):
        self.state.update_config({"plugins": {"generative": {"scenes": ["plasma"]}}})
        self.assertEqual(self.player.resolve("generative")[0], "plasma")
        name, gen, _ = self.player.resolve("gif:retro")
        self.assertEqual(name, "gif")
        next(gen)
        self.assertTrue(self.player.ctx.label.startswith("gif: retro-"))

    def test_unknown_scene(self):
        self.assertIsNone(self.player.resolve("bogus"))

    def test_birthday_boost_every_fourth_slot(self):
        self.state.update_config({"rotation": ["clock"]})
        with mock.patch.object(self.state, "themes", return_value=["spring", "birthday"]):
            slots = [self.player.next_item() for _ in range(8)]
        self.assertEqual(slots.count("seasonal"), 2)


class RunLoopTest(unittest.TestCase):
    """Drives the real loop on a FakeDisplay and watches what it shows."""

    def setUp(self):
        support.reset()
        self.state = State()
        self.state.update_config({"rotation": ["clock"], "dwell": {"clock": 30}})
        self.display = FakeDisplay()
        self.player = Player(self.state, self.display, GifLibrary(self.state, random.Random(2)), random.Random(2))
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.player.run, args=(self.stop,), daemon=True)
        self.thread.start()
        self.wait_for(lambda: self.state.label == "clock")

    def tearDown(self):
        self.stop.set()
        self.state.wake.set()
        self.thread.join(timeout=5)

    def wait_for(self, cond, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return
            time.sleep(0.02)
        self.fail(f"timed out; label is {self.state.label!r}")

    def test_request_interrupts_and_plays(self):
        self.state.request("fire")
        self.wait_for(lambda: self.state.label == "fire")
        self.assertIsNotNone(self.display.frame)

    def test_nothing_playing_or_no_event_just_skips(self):
        seen = []
        self.state.label = "watching"
        for scene in ("now_playing", "calendar"):
            self.state.request(scene)
            end = time.time() + 1.5
            while time.time() < end:
                seen.append(self.state.label)
                time.sleep(0.02)
        self.assertFalse([s for s in seen if "now_playing" in s or "calendar" in s], seen)
        self.state.put_data("now_playing", {"title": "Song", "state": "playing"})
        self.state.request("now_playing")
        self.wait_for(lambda: self.state.label == "now_playing")

    def test_missing_setup_data_says_so(self):
        self.state.request("homelab")
        self.wait_for(lambda: self.state.label == "empty: homelab")

    def test_notification_jumps_the_queue(self):
        self.state.notify({"text": "Hi", "seconds": 1})  # short enough not to scroll
        self.wait_for(lambda: self.state.label == "notify")
        self.wait_for(lambda: self.state.label == "clock", timeout=8)  # then the playlist resumes

    def test_pin_and_unpin(self):
        self.state.pin("on_air")
        self.wait_for(lambda: self.state.label == "on_air")
        self.state.pin(None)
        self.wait_for(lambda: self.state.label == "clock")

    def test_pinned_scene_without_data_waits_quietly(self):
        self.state.pin("calendar")
        self.wait_for(lambda: self.state.label == "waiting: calendar")
        self.state.pin("weather")
        self.wait_for(lambda: self.state.label == "empty: weather")

    def test_power_off_and_on(self):
        self.state.set(power=False)
        self.wait_for(lambda: self.state.label == "off")
        self.assertIsNone(self.display.frame)
        self.state.set(power=True)
        self.wait_for(lambda: self.state.label == "clock")

    def test_skip_moves_on_but_never_cuts_a_notification(self):
        self.state.update_config({"rotation": ["clock", "fire"], "dwell": {"clock": 30, "fire": 30}})
        self.state.request("plasma")
        self.wait_for(lambda: self.state.label == "plasma")
        self.state.skip_scene()
        self.wait_for(lambda: self.state.now.get("source") == "playlist")
        self.state.notify({"text": "Hi", "seconds": 1.5})
        self.wait_for(lambda: self.state.label == "notify")
        self.state.skip_scene()
        time.sleep(0.5)
        self.assertEqual(self.state.label, "notify")

    def test_brightness_reaches_display(self):
        self.state.set(brightness=33)
        self.wait_for(lambda: self.display.brightness == 33)

    def test_now_tracks_source_slot_and_next(self):
        self.state.update_config({"rotation": ["clock", "fire"], "dwell": {"clock": 30, "fire": 30}})
        self.state.request("plasma")
        self.wait_for(lambda: self.state.now.get("source") == "requested")
        self.assertEqual(self.state.now["entry"], "plasma")
        self.state.notify({"text": "Hi", "seconds": 1})
        self.wait_for(lambda: self.state.now.get("source") == "notification")
        self.assertEqual(self.state.now["text"], "Hi")
        self.wait_for(lambda: self.state.now.get("source") == "playlist", timeout=8)
        now = self.state.now
        self.assertEqual((now["entry"], now["length"]), (["clock", "fire"][now["index"]], 2))
        self.assertEqual(now["next"], ["clock", "fire"][(now["index"] + 1) % 2])
        self.assertEqual(now["seconds"], 30)
        self.state.pin("on_air")
        self.wait_for(lambda: self.state.now.get("source") == "pinned")
        self.state.set(power=False)
        self.wait_for(lambda: self.state.now.get("source") == "off")

    def test_broken_scene_does_not_kill_the_loop(self):
        from pixelpane.plugin import SCENES

        def boom(ctx, secs):
            raise RuntimeError("bad scene")
            yield  # pragma: no cover

        boom.kind, boom.plugin = "widget", "clock"
        with mock.patch.dict(SCENES, {"boom": boom}):
            self.state.request("boom")
            time.sleep(0.3)
            self.state.request("fire")
            self.wait_for(lambda: self.state.label == "fire", timeout=8)
        self.assertTrue(self.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
