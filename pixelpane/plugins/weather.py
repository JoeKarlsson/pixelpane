"""Weather: icon, temperature, high/low and conditions, with an Open-Meteo fallback."""
import json
import logging
import math
import time
import urllib.request

from PIL import Image, ImageChops, ImageDraw

from .. import gfx
from ..gfx import W
from ..kit import Mood, outlined_center, outlined_text, scroll_text, temp_color, ticks
from ..plugin import Plugin

log = logging.getLogger("pixelpane.weather")

plugin = Plugin(
    "weather", "Current conditions and today's high/low",
    data={"weather": 180},
    defaults={"latitude": None, "longitude": None, "mood": "full", "temp_colors": True,
              "show_high_low": True, "show_line": True},
    about="The weather fills the panel: rain slanting in the wind, drifting snow, fog, "
          "stars at night, a warm glow on sunny days, heat shimmer when it's hot and frost "
          "when it's bitter. The temperature is colored from cold blue to hot red, with "
          "today's high and low and the chance of rain. Home Assistant can push it to "
          "POST /api/data/weather; if nothing does, the board fetches Open-Meteo itself "
          "for the location below.",
    fields=[{"key": "latitude", "label": "Latitude", "type": "number", "step": 0.01,
             "help": "Only used when nothing pushes weather."},
            {"key": "longitude", "label": "Longitude", "type": "number", "step": 0.01},
            {"key": "mood", "label": "Background", "type": "select",
             "options": [{"label": "Full: the weather fills the panel", "value": "full"},
                         {"label": "Subtle: the same, at half brightness", "value": "subtle"},
                         {"label": "Off: plain black", "value": "off"}]},
            {"key": "temp_colors", "label": "Temperature color", "type": "toggle",
             "text": "Color the temperature from cold blue to hot red (else white)"},
            {"key": "show_high_low", "label": "High and low", "type": "toggle", "text": "Show today's high and low"},
            {"key": "show_line", "label": "Conditions line", "type": "toggle",
             "text": "Scroll the conditions, chance of rain and wind"}])


WEATHER_ICON = {
    "sunny": "sun", "clear-night": "moon", "partlycloudy": "partly", "cloudy": "cloud",
    "fog": "fog", "rainy": "cloud", "pouring": "cloud", "snowy": "cloud",
    "snowy-rainy": "cloud", "hail": "cloud", "lightning": "cloud",
    "lightning-rainy": "cloud", "windy": "cloud", "windy-variant": "cloud",
    "exceptional": "cloud",
}
WEATHER_WORDS = {
    "clear-night": "CLEAR", "partlycloudy": "PARTLY CLOUDY", "snowy-rainy": "SLEET",
    "lightning-rainy": "STORMS", "lightning": "LIGHTNING", "windy-variant": "WINDY",
}


# The whole panel behind the numbers: (mood, amount) for each condition.
WEATHER_MOOD = {
    "sunny": ("glow", 0.5), "clear-night": ("stars", 0.5), "partlycloudy": ("glow", 0.3),
    "cloudy": ("fog", 0.1), "fog": ("fog", 1.0), "rainy": ("rain", 0.35), "pouring": ("rain", 1.0),
    "lightning-rainy": ("rain", 0.7), "snowy": ("snow", 0.5), "snowy-rainy": ("snow", 0.3),
    "hail": ("snow", 1.0), "lightning": ("fog", 0.2), "windy": ("wind", 0.6), "windy-variant": ("wind", 0.6),
}


def _fahrenheit(wx, v):
    v = float(v)
    return v * 9 / 5 + 32 if str(wx.get("unit", "F")).upper().startswith("C") else v


@plugin.scene("weather", empty_text="NO WEATHER YET")
def weather(ctx, secs):
    wx = ctx.data("weather")
    if not wx or wx.get("temp") is None:
        return
    cond = str(wx.get("condition", "cloudy"))
    icon = WEATHER_ICON.get(cond, "cloud")
    temp = f"{round(float(wx['temp']))}"
    temp_f = _fahrenheit(wx, wx["temp"])
    hl = []
    if wx.get("high") is not None:
        hl.append(f"H{round(float(wx['high']))}")
    if wx.get("low") is not None:
        hl.append(f"L{round(float(wx['low']))}")
    words = WEATHER_WORDS.get(cond, cond.upper().replace("-", " "))
    line = words + (f"  {int(wx['precip'])}% PRECIP" if wx.get("precip") else "")
    wind = float(wx.get("wind") or 0)   # mph
    if wind >= 15:
        line += f"  WIND {wind:.0f}"
    cfg = ctx.settings("weather")
    mood = cfg.get("mood", "full")
    if not cfg.get("show_high_low", True):
        hl = []
    rng = ctx.rng
    name, amount = WEATHER_MOOD.get(cond, ("fog", 0.1))
    if name == "wind":
        amount = max(amount, min(1.0, wind / 35))
    layers = [Mood(rng, name, amount, (255, 190, 60) if name == "glow" else (60, 220, 170), wind=wind / 20)]
    if cond == "snowy-rainy":
        layers.append(Mood(rng, "rain", 0.3, wind=wind / 20))
    if wind >= 15 and name != "wind":
        layers.append(Mood(rng, "wind", min(1.0, wind / 35)))
    if temp_f >= 85:     # a hot day shimmers; a bitter one frosts over
        layers.append(Mood(rng, "heat", min(1.0, (temp_f - 80) / 20)))
    elif temp_f <= 25:
        layers.append(Mood(rng, "frost", min(1.0, (32 - temp_f) / 30)))
    color = temp_color(temp_f) if cfg.get("temp_colors", True) else (255, 255, 255)
    for i, t in ticks(secs, 10):
        if mood == "off":
            img = gfx.blank()
        else:
            img = layers[0].frame(t)
            for layer in layers[1:]:
                img = ImageChops.lighter(img, layer.frame(t))
            if mood == "subtle":
                img = Image.blend(gfx.blank(), img, 0.5)
            if cond.startswith("lightning") and i % 37 in (0, 2):   # the sky lights up
                img = Image.blend(img, gfx.blank((200, 200, 255)), 0.5 if mood == "full" else 0.25)
        drift = round(math.sin(t * 1.2)) if icon in ("cloud", "partly", "fog") else 0
        gfx.paste(img, icon, (1 + drift, 1))
        d = ImageDraw.Draw(img)
        if cond.startswith("lightning") and i % 20 in (0, 1):
            d.line((6, 9, 4, 12, 7, 12, 5, 15), fill=(255, 230, 0))
        if cond == "sunny" and i % 10 < 5:
            for x, y in ((0, 4), (11, 4), (4, 0), (7, 9)):  # rays twinkle (sprite drawn at 1,1)
                img.putpixel((x + 1, y + 1), (0, 0, 0))
        tx = W - gfx.text_width(temp, "6x10") - 4
        outlined_text(img, (tx, 2), temp, color, "6x10")
        d.rectangle((W - 3, 2, W - 2, 3), outline=color)  # degree mark
        if hl:
            outlined_center(img, 18, " ".join(hl), (170, 190, 255), "tom-thumb")
        if cfg.get("show_line", True):
            scroll_text(img, 25, line, (255, 200, 80), "tom-thumb", t, 16)
        yield img, 0.1


WMO = {0: "sunny", 1: "sunny", 2: "partlycloudy", 3: "cloudy", 45: "fog", 48: "fog",
       51: "rainy", 53: "rainy", 55: "rainy", 61: "rainy", 63: "rainy", 65: "pouring",
       66: "snowy-rainy", 67: "snowy-rainy", 71: "snowy", 73: "snowy", 75: "snowy", 77: "snowy",
       80: "rainy", 81: "rainy", 82: "pouring", 85: "snowy", 86: "snowy", 95: "lightning-rainy",
       96: "lightning-rainy", 99: "lightning-rainy"}


@plugin.task
def open_meteo(ctx, stop):
    """Fetch Open-Meteo every 20 min, but only while nothing else is pushing weather
    and the plugin has latitude/longitude set."""
    state = ctx.state
    while not stop.wait(5):
        fb = ctx.settings("weather")
        item = state.data.get("weather")
        fresh = item and item[1].get("source") != "open-meteo" and time.time() - item[0] < 3600
        if not fb.get("enabled", True) or fb.get("latitude") is None or fresh or (item and time.time() - item[0] < 1200):
            stop.wait(55)
            continue
        url = ("https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
               "&current=temperature_2m,weather_code,is_day,wind_speed_10m&daily=temperature_2m_max,"
               "temperature_2m_min,precipitation_probability_max&temperature_unit=fahrenheit&wind_speed_unit=mph"
               "&timezone=auto&forecast_days=1").format(latitude=fb["latitude"], longitude=fb["longitude"])
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                j = json.load(r)
            cond = WMO.get(j["current"]["weather_code"], "cloudy")
            if cond == "sunny" and not j["current"].get("is_day", 1):
                cond = "clear-night"
            state.put_data("weather", {
                "temp": j["current"]["temperature_2m"], "condition": cond, "unit": "F",
                "high": j["daily"]["temperature_2m_max"][0], "low": j["daily"]["temperature_2m_min"][0],
                "precip": j["daily"]["precipitation_probability_max"][0],
                "wind": j["current"].get("wind_speed_10m"), "source": "open-meteo"})
        except Exception as e:  # network blips are normal; retry next round
            log.warning("open-meteo: %s", e)
