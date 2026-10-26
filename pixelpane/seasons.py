"""Which seasonal themes are active on a given date."""
from datetime import date, timedelta

BUILTIN = {
    "winter": "Winter (Dec to Feb)",
    "spring": "Spring (Mar to May)",
    "summer": "Summer (Jun to Aug)",
    "autumn": "Autumn (Sep to Nov)",
    "new_year": "New Year (Dec 31 to Jan 1)",
    "valentines": "Valentine's Day (Feb 7 to 14)",
    "st_patricks": "St. Patrick's Day (Mar 14 to 17)",
    "birthday": "Birthday (set in the seasonal plugin)",
    "july4": "Fourth of July (Jul 1 to 4)",
    "halloween": "Halloween (all of October)",
    "thanksgiving": "Thanksgiving (Mon to Thu of that week)",
    "christmas": "Christmas (Dec 1 to 26)",
}
SEASONS = ("winter", "spring", "summer", "autumn")
# Built-in holidays you can switch off (seasons always run; the birthday has its own setting)
HOLIDAYS = [k for k in BUILTIN if k not in SEASONS and k != "birthday"]

# Every theme the board knows: the built-ins plus your own from config["themes"]["custom"].
# Rebuilt in place by configure() whenever the config changes, so importers see updates.
THEMES = dict(BUILTIN)
_settings = {"hemisphere": "north", "off": [], "custom": []}


def configure(cfg):
    """Apply config["themes"]: {"hemisphere": "north"|"south", "off": [holiday keys],
    "custom": [{"key", "name", "dates": [["MM-DD" or "YYYY-MM-DD", same], ...]}]}."""
    cfg = cfg or {}
    _settings.update(hemisphere=cfg.get("hemisphere") or "north", off=list(cfg.get("off") or []),
                     custom=list(cfg.get("custom") or []))
    names = dict(BUILTIN)
    if _settings["hemisphere"] == "south":
        names.update(winter="Winter (Jun to Aug)", spring="Spring (Sep to Nov)",
                     summer="Summer (Dec to Feb)", autumn="Autumn (Mar to May)")
    for c in _settings["custom"]:
        names[c["key"]] = c["name"]
    THEMES.clear()
    THEMES.update(names)


def season(d):
    m = d.month
    if _settings["hemisphere"] == "south":
        m = (m + 5) % 12 + 1   # six months on: June is winter
    if m in (12, 1, 2):
        return "winter"
    return "spring" if m <= 5 else "summer" if m <= 8 else "autumn"


def in_range(d, start, end):
    """Is d inside start..end (inclusive)? A yearly range may wrap the new year (12-30 to 01-02)."""
    if len(str(start).split("-")) == 3:
        return date.fromisoformat(start) <= d <= date.fromisoformat(end)
    md = (d.month, d.day)
    a, b = (tuple(int(x) for x in str(v).split("-")) for v in (start, end))
    return a <= md <= b if a <= b else md >= a or md <= b


def thanksgiving(year):
    nov1 = date(year, 11, 1)
    return nov1 + timedelta(days=(3 - nov1.weekday()) % 7, weeks=3)


def active_themes(d, birthday=None):
    """Season first, then any holidays, most specific last."""
    md = (d.month, d.day)
    themes = [season(d)]
    if md in ((12, 31), (1, 1)):
        themes.append("new_year")
    if (2, 7) <= md <= (2, 14):
        themes.append("valentines")
    if (3, 14) <= md <= (3, 17):
        themes.append("st_patricks")
    if (7, 1) <= md <= (7, 4):
        themes.append("july4")
    if d.month == 10:
        themes.append("halloween")
    tg = thanksgiving(d.year)
    if tg - timedelta(days=3) <= d <= tg:
        themes.append("thanksgiving")
    if (12, 1) <= md <= (12, 26):
        themes.append("christmas")
    themes = [t for t in themes if t not in _settings["off"]]
    for c in _settings["custom"]:
        if any(in_range(d, a, b) for a, b in c["dates"]):
            themes.append(c["key"])
    if birthday and md == tuple(birthday):
        themes.append("birthday")
    return themes


def days_until(theme, d):
    """Days from d to the holiday's big day (0 on the day, negative after it, as on
    Dec 26 for Christmas), or None for a season, the birthday or a theme not on today.
    A custom holiday's big day is the last day of the range that's on."""
    if theme not in active_themes(d) or theme in SEASONS:
        return None
    y = d.year
    day = {"new_year": date(y + 1 if d.month == 12 else y, 1, 1), "valentines": date(y, 2, 14),
           "st_patricks": date(y, 3, 17), "july4": date(y, 7, 4), "halloween": date(y, 10, 31),
           "thanksgiving": thanksgiving(y), "christmas": date(y, 12, 25)}.get(theme)
    if day is None:
        for c in _settings["custom"]:
            if c["key"] != theme:
                continue
            for a, b in c["dates"]:
                if not in_range(d, a, b):
                    continue
                if len(str(b).split("-")) == 3:
                    day = date.fromisoformat(b)
                else:
                    m, dd = (int(x) for x in str(b).split("-"))
                    day = date(y, m, dd)
                    if day < d:
                        day = date(y + 1, m, dd)   # a range that wraps the new year
                break
    return None if day is None else (day - d).days
