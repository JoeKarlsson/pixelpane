"""Helpers for testing a plugin's scenes without a board, a state folder or a server.

    from pixelpane.testing import render

    frames = render("countdown", seconds=2, settings={"date": "2099-01-01"})
    assert frames                      # it drew something
    assert len({img.tobytes() for img, _ in frames}) > 1   # and it moves

Import your plugin module first (or call pixelpane.plugin.load()) so its scenes exist.
"""
import random
from datetime import datetime

from . import plugin


class FakeCtx:
    """What a scene sees (see pixelpane.app.Ctx), with data and settings you hand it."""

    def __init__(self, owner, data=None, settings=None, now=None, seed=1):
        self._data, self._now = dict(data or {}), now
        self.rng = random.Random(seed)
        self.label = ""
        self._stores = {}
        self._saved = {}
        self.config = {"plugins": {owner: dict(settings or {})}}

    def settings(self, name):
        return plugin.settings(self.config, name)

    def store(self, name):
        return self._stores.setdefault(name, {})

    def saved(self, name):
        return self._saved.setdefault(name, {})

    def save(self, name):
        pass   # kept in memory for the life of the test

    def now(self):
        return self._now or datetime.now()

    def data(self, key):
        return self._data.get(key)


def render(scene, seconds=2.0, data=None, settings=None, now=None, params=None, seed=1):
    """Run scene for `seconds` and return its frames as [(image, seconds_held), ...].

    data: {key: payload} as if pushed to /api/data/<key>. settings: the scene's own
    plugin settings, over its defaults. now: a datetime to freeze time at."""
    if not plugin.PLUGINS:
        plugin.load(user_dir=None)
    fn = plugin.SCENES[scene]
    ctx = FakeCtx(fn.plugin, data, settings, now, seed)
    return list(fn(ctx, seconds, **(params or {})))
