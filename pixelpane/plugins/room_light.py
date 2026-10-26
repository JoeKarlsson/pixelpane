"""Room light: the panel follows the room, dimmer in a dark room and full in a bright one."""
import math

from ..plugin import Plugin

plugin = Plugin(
    "room_light", "Brightness that follows the room",
    data={"room_light": 30},
    defaults={"dark_lux": 3, "bright_lux": 300, "lowest": 25},
    about="Push the room's light level from a sensor (Home Assistant: POST "
          "/api/data/room_light with {\"lux\": 120}) and the panel dims in a dark room and "
          "comes up to your brightness in a bright one, easing between them so it never "
          "jumps. In between it follows the light on a log scale, the way eyes do. Your "
          "brightness and the schedule's dimming still set the top; without a fresh "
          "reading (half an hour) the panel is left alone.",
    fields=[{"key": "dark_lux", "label": "Dark room (lux)", "type": "number", "min": 0, "max": 1000, "step": 1,
             "help": "At or below this, the panel is at its lowest"},
            {"key": "bright_lux", "label": "Bright room (lux)", "type": "number", "min": 1, "max": 100000,
             "step": 1, "help": "At or above this, the panel is at your brightness"},
            {"key": "lowest", "label": "Lowest (% of your brightness)", "type": "range",
             "min": 1, "max": 100, "step": 1}])

EASE = 0.02   # of the way to the target each frame: about five seconds to settle


def target(lux, dark, bright, lowest):
    """The share of your brightness (from lowest up to 1) for this much light."""
    dark, bright = max(0.1, dark), max(dark + 1, bright)
    f = math.log(max(lux, dark) / dark) / math.log(bright / dark)
    return lowest + (1 - lowest) * max(0.0, min(1.0, f))


@plugin.level
def follow_the_room(ctx, brightness):
    reading = ctx.data("room_light") or {}
    try:
        lux = float(reading["lux"])
    except (KeyError, TypeError, ValueError):
        return brightness
    s = ctx.settings("room_light")
    want = target(lux, float(s.get("dark_lux") or 3), float(s.get("bright_lux") or 300),
                  float(s.get("lowest") or 25) / 100)
    store = ctx.store("room_light")
    now = store.get("share", want)
    store["share"] = now + (want - now) * EASE
    return brightness * store["share"]
