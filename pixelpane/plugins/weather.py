"""Weather: icon, temperature, high/low and conditions, with an Open-Meteo fallback."""
import json
import logging
import math
import time
import urllib.request

from PIL import ImageDraw

from .. import gfx
from ..gfx import W
from ..kit import scroll_text, ticks
from ..plugin import Plugin

log = logging.getLogger("pixelpane.weather")

plugin = Plugin(
    "weather", "Current conditions and today's high/low",
    data={"weather": 180}, defaults={"latitude": None, "longitude": None},
    about="An animated icon (rain falls, snow drifts, clouds roll), the temperature, "
          "today's high and low and the chance of rain. Home Assistant can push it to "
          "POST /api/data/weather; if nothing does, the board fetches Open-Meteo itself "
          "for the location below.",
    fields=[{"key": "latitude", "label": "Latitude", "type": "number", "step": 0.01,
             "help": "Only used when nothing pushes weather."},
            {"key": "longitude", "label": "Longitude", "type": "number", "step": 0.01}])


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


@plugin.scene("weather", empty_text="NO WEATHER YET")
def weather(ctx, secs):
    wx = ctx.data("weather")
    if not wx or wx.get("temp") is None:
        return
    cond = str(wx.get("condition", "cloudy"))
    icon = WEATHER_ICON.get(cond, "cloud")
    temp = f"{round(float(wx['temp']))}"
    hl = []
    if wx.get("high") is not None:
        hl.append(f"H{round(float(wx['high']))}")
    if wx.get("low") is not None:
        hl.append(f"L{round(float(wx['low']))}")
    words = WEATHER_WORDS.get(cond, cond.upper().replace("-", " "))
    line = words + (f"  {int(wx['precip'])}% PRECIP" if wx.get("precip") else "")
    rng = ctx.rng
    drops = [[rng.randrange(1, 12), rng.randrange(11, 16)] for _ in range(4)]
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        drift = round(math.sin(t * 1.2)) if icon in ("cloud", "partly", "fog") else 0
        gfx.paste(img, icon, (1 + drift, 1))
        d = ImageDraw.Draw(img)
        if cond.startswith("windy") or cond == "fog":
            for k in range(3):
                x0 = int(t * (10 + k * 4) + k * 9) % 18 - 4
                d.line((x0, 12 + k * 1, x0 + 3, 12 + k * 1), fill=(150, 150, 170))
        if cond in ("rainy", "pouring", "lightning-rainy", "snowy", "snowy-rainy", "hail"):
            snow = cond in ("snowy", "snowy-rainy", "hail")
            for p in drops:
                p[1] += 1 if snow else 2
                if p[1] > 15:
                    p[:] = [rng.randrange(1, 12), 10]
                img.putpixel((p[0], p[1]), (230, 230, 255) if snow else (60, 130, 255))
        if cond.startswith("lightning") and i % 20 in (0, 1):
            d.line((6, 9, 4, 12, 7, 12, 5, 15), fill=(255, 230, 0))
        if cond == "sunny" and i % 10 < 5:
            for x, y in ((0, 4), (11, 4), (4, 0), (7, 9)):  # rays twinkle (sprite drawn at 1,1)
                img.putpixel((x + 1, y + 1), (0, 0, 0))
        if cond == "clear-night":
            for k, (x, y) in enumerate(((14, 2), (9, 13), (2, 15))):
                if (i // 4 + k) % 3:
                    img.putpixel((x, y), (200, 200, 255))
        gfx.text(img, (W - gfx.text_width(temp, "6x10") - 4, 2), temp, (255, 255, 255), "6x10")
        d.rectangle((W - 3, 2, W - 2, 3), outline=(255, 255, 255))  # degree mark
        if hl:
            gfx.text_center(img, 18, " ".join(hl), (170, 190, 255), "tom-thumb")
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
               "&current=temperature_2m,weather_code,is_day&daily=temperature_2m_max,"
               "temperature_2m_min,precipitation_probability_max&temperature_unit=fahrenheit"
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
                "precip": j["daily"]["precipitation_probability_max"][0], "source": "open-meteo"})
        except Exception as e:  # network blips are normal; retry next round
            log.warning("open-meteo: %s", e)
