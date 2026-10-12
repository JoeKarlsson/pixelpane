"""Which seasonal themes are active on a given date."""
from datetime import date, timedelta

THEMES = {
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


def season(d):
    m = d.month
    if m in (12, 1, 2):
        return "winter"
    return "spring" if m <= 5 else "summer" if m <= 8 else "autumn"


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
    if birthday and md == tuple(birthday):
        themes.append("birthday")
    return themes
