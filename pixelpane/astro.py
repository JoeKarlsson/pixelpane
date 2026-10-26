"""Moon phases, full moon names, zodiac signs and sunrise. Pure functions, no network.

New and full moon times follow Jean Meeus, Astronomical Algorithms (2nd ed.),
chapter 49, with the main periodic terms: good to a few minutes. The moon's
distance and longitude use the leading terms of chapter 47: good enough to call
a supermoon and the moon's sign.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

SYNODIC = 29.530588861
J2000 = 2451545.0


def julian(dt: datetime) -> float:
    """Julian day of an aware or UTC-naive datetime."""
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return (dt - datetime(2000, 1, 1, 12)).total_seconds() / 86400 + J2000


def from_julian(jd: float) -> datetime:
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - J2000)


def sun_times(d: date, lat: float, lon: float) -> tuple[datetime, datetime] | None:
    """Sunrise and sunset on d at lat/lon (east positive), as local naive datetimes,
    or None when the sun doesn't rise or set that day. The sunrise equation: good to
    a minute or two away from the poles."""
    n = round(julian(datetime(d.year, d.month, d.day, 12)) - J2000 - lon / 360) - lon / 360
    m = (357.5291 + 0.98560028 * n) % 360
    c = 1.9148 * math.sin(_rad(m)) + 0.02 * math.sin(_rad(2 * m)) + 0.0003 * math.sin(_rad(3 * m))
    ecl = (m + c + 282.9372) % 360
    noon = J2000 + n + 0.0053 * math.sin(_rad(m)) - 0.0069 * math.sin(_rad(2 * ecl))
    dec = math.asin(math.sin(_rad(ecl)) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(dec)) / (math.cos(phi) * math.cos(dec))
    if not -1 <= cos_w <= 1:
        return None
    w = math.degrees(math.acos(cos_w)) / 360

    def local(jd):
        return from_julian(jd).astimezone().replace(tzinfo=None)
    return local(noon - w), local(noon + w)


def _rad(deg: float) -> float:
    return math.radians(deg % 360)


def phase_time(k: int, full: bool) -> datetime:
    """UTC time of the new (full=False) or full moon number k (k=0: 6 Jan 2000)."""
    k = k + (0.5 if full else 0.0)
    t = k / 1236.85
    jde = (2451550.09766 + SYNODIC * k + 0.00015437 * t ** 2 - 0.000000150 * t ** 3
           + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t ** 2
    m = _rad(2.5534 + 29.10535670 * k - 0.0000014 * t ** 2 - 0.00000011 * t ** 3)
    mp = _rad(201.5643 + 385.81693528 * k + 0.0107582 * t ** 2 + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    f = _rad(160.7108 + 390.67050284 * k - 0.0016118 * t ** 2 - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)
    om = _rad(124.7746 - 1.56375588 * k + 0.0020672 * t ** 2 + 0.00000215 * t ** 3)
    s = math.sin
    if full:
        c = (-0.40614 * s(mp) + 0.17302 * e * s(m) + 0.01614 * s(2 * mp) + 0.01043 * s(2 * f)
             + 0.00734 * e * s(mp - m) - 0.00515 * e * s(mp + m) + 0.00209 * e * e * s(2 * m))
    else:
        c = (-0.40720 * s(mp) + 0.17241 * e * s(m) + 0.01608 * s(2 * mp) + 0.01039 * s(2 * f)
             + 0.00739 * e * s(mp - m) - 0.00514 * e * s(mp + m) + 0.00208 * e * e * s(2 * m))
    c += (-0.00111 * s(mp - 2 * f) - 0.00057 * s(mp + 2 * f) + 0.00056 * e * s(2 * mp + m)
          - 0.00042 * s(3 * mp) + 0.00042 * e * s(m + 2 * f) + 0.00038 * e * s(m - 2 * f)
          - 0.00024 * e * s(2 * mp - m) - 0.00017 * s(om))
    return from_julian(jde + c)


def _k_near(dt: datetime) -> int:
    return math.floor((julian(dt) - 2451550.09766) / SYNODIC)


def last_new_moon(dt: datetime) -> datetime:
    k = _k_near(dt) + 1
    while phase_time(k, False) > dt:
        k -= 1
    return phase_time(k, False)


def next_phase(dt: datetime, full: bool) -> datetime:
    k = _k_near(dt) - 1
    while phase_time(k, full) <= dt:
        k += 1
    return phase_time(k, full)


def full_moons(start: datetime, end: datetime) -> list[datetime]:
    out, t = [], next_phase(start - timedelta(seconds=1), True)
    while t < end:
        out.append(t)
        t = next_phase(t, True)
    return out


def _mean_elements(dt: datetime) -> tuple[float, float, float, float, float]:
    t = (julian(dt) - J2000) / 36525
    lp = 218.3164477 + 481267.88123421 * t
    d = 297.8501921 + 445267.1114034 * t
    m = 357.5291092 + 35999.0502909 * t
    mp = 134.9633964 + 477198.8675055 * t
    f = 93.2720950 + 483202.0175233 * t
    return lp, d, m, mp, f


def moon_distance_km(dt: datetime) -> float:
    _, d, m, mp, f = (_rad(x) for x in _mean_elements(dt))
    c = math.cos
    return (385000.56 - 20905.355 * c(mp) - 3699.111 * c(2 * d - mp) - 2955.968 * c(2 * d)
            - 569.925 * c(2 * mp) + 48.888 * c(m) - 3.149 * c(2 * f) + 246.158 * c(2 * d - 2 * mp)
            - 152.138 * c(2 * d - m - mp) - 170.733 * c(2 * d + mp) - 204.586 * c(2 * d - m))


def moon_longitude(dt: datetime) -> float:
    lp, d, m, mp, f = _mean_elements(dt)
    d, m, mp, f = (_rad(x) for x in (d, m, mp, f))
    s = math.sin
    return (lp + 6.289 * s(mp) + 1.274 * s(2 * d - mp) + 0.658 * s(2 * d) + 0.214 * s(2 * mp)
            - 0.186 * s(m) - 0.114 * s(2 * f)) % 360


SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio",
         "sagittarius", "capricorn", "aquarius", "pisces"]
ELEMENTS = {"aries": "fire", "leo": "fire", "sagittarius": "fire", "taurus": "earth", "virgo": "earth",
            "capricorn": "earth", "gemini": "air", "libra": "air", "aquarius": "air", "cancer": "water",
            "scorpio": "water", "pisces": "water"}
# (month, day) each sun sign starts, tropical zodiac
SIGN_STARTS = [((1, 20), "aquarius"), ((2, 19), "pisces"), ((3, 21), "aries"), ((4, 20), "taurus"),
               ((5, 21), "gemini"), ((6, 21), "cancer"), ((7, 23), "leo"), ((8, 23), "virgo"),
               ((9, 23), "libra"), ((10, 23), "scorpio"), ((11, 22), "sagittarius"), ((12, 22), "capricorn")]


def sun_sign(d: date) -> str:
    sign = "capricorn"
    for (m, day), name in SIGN_STARTS:
        if (d.month, d.day) >= (m, day):
            sign = name
    return sign


def moon_sign(dt: datetime) -> str:
    return SIGNS[int(moon_longitude(dt) // 30)]


# Supermoon: a full moon within about 90% of perigee. The series above is good to a
# few hundred km, so this matches the commonly published lists.
SUPERMOON_KM = 362600
MONTH_NAMES = {1: "wolf", 2: "snow", 3: "worm", 4: "pink", 5: "flower", 6: "strawberry", 7: "buck",
               8: "sturgeon", 9: "corn", 10: "hunter's", 11: "beaver", 12: "cold"}


def full_moon_name(full: datetime, tz=None) -> dict:
    """Traditional (North American) name of the full moon at `full` (UTC).

    The Harvest moon is the full moon nearest the September equinox and the
    Hunter's moon is the one after it; the rest take their month's name. A second
    full moon in a calendar month is a blue moon; one near perigee is a supermoon.
    """
    local = full.astimezone(tz) if tz else full.astimezone()
    equinox = datetime(local.year, 9, 22, 18, tzinfo=timezone.utc)
    harvest = min(full_moons(equinox - timedelta(days=30), equinox + timedelta(days=30)),
                  key=lambda t: abs(t - equinox))
    if abs(full - harvest) < timedelta(hours=1):
        name = "harvest"
    elif abs(full - next_phase(harvest, True)) < timedelta(hours=1):
        name = "hunter's"
    elif local.month == 10:
        name = "falling leaves"   # rare: an October full moon that is neither
    else:
        name = MONTH_NAMES[local.month]
    prev = next_phase(full - timedelta(days=31), True).astimezone(local.tzinfo)   # the full moon before
    blue = (prev.year, prev.month) == (local.year, local.month)
    return {"name": name, "blue": blue, "super": moon_distance_km(full) < SUPERMOON_KM}


PHASES = ["new moon", "waxing crescent", "first quarter", "waxing gibbous", "full moon",
          "waning gibbous", "last quarter", "waning crescent"]


def moon_phase(dt: datetime, tz=None) -> dict:
    """Everything a moon scene needs at `dt` (aware, or local naive)."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    new = last_new_moon(dt)
    nxt_new = next_phase(dt, False)
    frac = (dt - new) / (nxt_new - new)
    full = next_phase(new, True)          # this cycle's full moon
    first_q = new + (full - new) / 2
    last_q = full + (nxt_new - full) / 2
    day = timedelta(hours=18)
    if dt - new < day or nxt_new - dt < day:
        name = "new moon"
    elif abs(dt - full) < day:
        name = "full moon"
    elif abs(dt - first_q) < day:
        name = "first quarter"
    elif abs(dt - last_q) < day:
        name = "last quarter"
    elif dt < first_q:
        name = "waxing crescent"
    elif dt < full:
        name = "waxing gibbous"
    elif dt < last_q:
        name = "waning gibbous"
    else:
        name = "waning crescent"
    upcoming_full = full if full > dt - day else next_phase(dt, True)
    info = {"phase": name, "fraction": frac, "illumination": (1 - math.cos(2 * math.pi * frac)) / 2,
            "age_days": (dt - new).total_seconds() / 86400, "next_full": upcoming_full, "next_new": nxt_new,
            "sun_sign": sun_sign(dt.astimezone(tz).date() if tz else dt.date()), "moon_sign": moon_sign(dt)}
    if name == "full moon":
        info["full"] = full_moon_name(full, tz)
    return info
