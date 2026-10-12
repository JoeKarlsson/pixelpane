"""Homelab: an animated status dashboard (checks, hosts, NAS, network, UPS, Plex)."""
import math

from PIL import ImageDraw

from .. import gfx
from ..kit import scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin(
    "homelab", "Animated homelab dashboard", data={"homelab": 60},
    about="Up to six animated pages: alerts (always first), health checks with a "
          "blinking server rack, Proxmox host CPU, NAS space and transfer, network "
          "latency and DNS, UPS batteries and Plex. Each page appears only when its data "
          "is pushed to POST /api/data/homelab (Plex only while someone is streaming); see docs/HOME_ASSISTANT.md for the fields.")


@plugin.scene("homelab")
def homelab(ctx, secs):
    """A short animated dashboard: status, hosts, NAS, network, UPS, Plex.

    Every page is optional; each shows only when Home Assistant sent its data.
    Active alerts always come first and get extra time.
    """
    lab = ctx.data("homelab")
    if not lab:
        return
    pages = lab_pages(lab)
    each = max(3.5, secs / len(pages))
    for page in pages:
        dur = max(each, 6) if page is _lab_alerts else each
        for i, t in ticks(dur, 10):
            img = gfx.blank()
            page(img, ImageDraw.Draw(img), lab, i, t)
            yield img, 0.1


def lab_pages(lab):
    pages = [_lab_alerts] if int(lab.get("alerts") or 0) else []
    pages.append(_lab_status)
    for key, page in (("hosts", _lab_hosts), ("nas", _lab_nas), ("net", _lab_net),
                      ("ups", _lab_ups), ("plex", _lab_plex)):
        if lab.get(key):
            pages.append(page)
    if _lab_plex in pages and not int(lab["plex"].get("watching") or 0):
        pages.remove(_lab_plex)   # only worth a page while someone is streaming
    return pages


def _ease(t, span=0.8):
    """0 -> 1 over the first `span` seconds, for bars that fill in."""
    return min(1.0, t / span) ** 0.5


def _level_color(pct, warn=75, crit=90):
    return (60, 220, 90) if pct < warn else (255, 180, 40) if pct < crit else (255, 60, 60)


def _title(img, s, color=(130, 140, 170)):
    gfx.text(img, (1, 0), s, color, "tom-thumb")


def _short(n):
    n = float(n)
    for unit, div in (("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{n / div:.0f}{unit}" if n / div >= 10 else f"{n / div:.1f}{unit}"
    return f"{n:.0f}"


def _lab_alerts(img, d, lab, i, t):
    n = int(lab.get("alerts") or 0)
    if i % 10 < 7:
        gfx.paste(img, "alert", (2, 2))
    gfx.text(img, (13, 2), str(n), (255, 60, 60), "6x10")
    gfx.text_center(img, 13, "ALERTS" if n > 1 else "ALERT", (255, 120, 120), "tom-thumb")
    names = ", ".join(str(x) for x in (lab.get("names") or [])).upper() or "SEE PHONE"
    scroll_text(img, 21, names, (255, 200, 200), "5x7", t, 16)


def _lab_status(img, d, lab, i, t):
    # a little server rack with blinking drive lights
    for u in range(3):
        y = 4 + u * 5
        d.rectangle((1, y, 10, y + 3), outline=(90, 95, 120))
        for k in range(3):
            if (i + u * 3 + k * 7) % 9 < 6:
                img.putpixel((3 + k * 2, y + 2), (60, 255, 90) if k < 2 else (255, 170, 30))
    total, passing = lab.get("checks_total"), lab.get("checks_passing")
    warn = int(lab.get("warnings") or 0)
    bad = int(lab.get("alerts") or 0)
    col = (255, 60, 60) if bad else (255, 180, 40) if warn else (60, 220, 90)
    if total:
        gfx.text(img, (13, 3), str(passing), col, "6x10")
        gfx.text(img, (13, 13), f"/{total}", (120, 130, 150), "tom-thumb")
    else:
        gfx.paste(img, "check" if not (bad or warn) else "alert", (16, 5))
    word = f"{bad} ALERT" if bad else f"{warn} WARN" if warn else "ALL OK"
    gfx.text_center(img, 21, word, col, "5x7")
    if not (bad or warn):
        x = int(t * 12) % 40 - 4  # a heartbeat blip running along the bottom
        for k, dy in enumerate((0, -2, 2, 0)):
            if 0 <= x + k < 32:
                img.putpixel((x + k, 30 + dy // 2), col)


def _lab_hosts(img, d, lab, i, t):
    _title(img, "PROXMOX")
    for row, h in enumerate(lab["hosts"][:2]):
        y = 8 + row * 12
        cpu = float(h.get("cpu") or 0)
        gfx.text(img, (1, y), str(h.get("name", "?"))[:2].upper(), (200, 200, 220), "tom-thumb")
        w = int(18 * min(cpu, 100) / 100 * _ease(t))
        d.rectangle((10, y, 28, y + 3), outline=(50, 55, 70))
        if w:
            d.rectangle((10, y, 10 + w, y + 3), fill=_level_color(cpu))
        if i % 6 < 3:
            img.putpixel((30, y + 1), (60, 255, 90))  # activity light
        gfx.text(img, (1, y + 5), f"{cpu:.0f}%", (150, 160, 190), "tom-thumb")
        if h.get("temp") is not None:
            temp = f"{float(h['temp']):.0f}F"
            gfx.text(img, (32 - gfx.text_width(temp, "tom-thumb"), y + 5), temp, (120, 130, 160), "tom-thumb")


def _lab_nas(img, d, lab, i, t):
    nas = lab["nas"]
    _title(img, "NAS")
    used = float(nas.get("used_pct") or 0)
    w = int(29 * used / 100 * _ease(t, 1.2))
    d.rectangle((1, 8, 30, 14), outline=(60, 65, 85))
    for x in range(w):
        d.line((2 + x, 9, 2 + x, 13), fill=gfx.scale(_level_color(used, 80, 90), 0.6 + 0.4 * x / 29))
    gfx.text(img, (1, 17), f"{used:.0f}%", (230, 230, 240), "tom-thumb")
    if nas.get("used_tb") is not None:
        s = f"{float(nas['used_tb']):.0f}TB"
        gfx.text(img, (31 - gfx.text_width(s, "tom-thumb"), 17), s, (150, 160, 190), "tom-thumb")
    up, down = float(nas.get("up_mbs") or 0), float(nas.get("down_mbs") or 0)
    for x0, mbs, col, sign in ((1, up, (80, 200, 255), -1), (17, down, (255, 140, 200), 1)):
        y = 27 + sign * (int(t * 6) % 3 - 1)  # arrows bob in their direction
        img.putpixel((x0 + 1, y + sign), col)  # arrow tip
        d.line((x0, y, x0 + 2, y), fill=col)
        gfx.text(img, (x0 + 4, 25), f"{mbs:.0f}M" if mbs >= 1 else f"{mbs:.1f}M", col, "tom-thumb")


def _lab_net(img, d, lab, i, t):
    net = lab["net"]
    _title(img, "NETWORK")
    ms = net.get("wan_ms")
    d.line((3, 11, 28, 11), fill=(50, 55, 75))
    img.putpixel((2, 11), (120, 200, 255))
    img.putpixel((29, 11), (120, 200, 255))
    phase = (t * 1.5) % 2
    x = 3 + int(25 * (phase if phase < 1 else 2 - phase))  # ping out and back
    d.rectangle((x, 10, x + 1, 12), fill=(255, 255, 255))
    if ms is not None:
        gfx.text_center(img, 14, f"WAN {float(ms):.0f}MS", (120, 200, 255), "tom-thumb")
    if net.get("dns_queries") is not None:
        gfx.text(img, (1, 21), f"DNS {_short(net['dns_queries'])}", (200, 200, 220), "tom-thumb")
    if net.get("blocked_pct") is not None:
        gfx.text(img, (1, 27), f"BLOCK {float(net['blocked_pct']):.0f}%", (255, 120, 120), "tom-thumb")


def _lab_ups(img, d, lab, i, t):
    _title(img, "POWER")
    units = lab["ups"][:2]
    for k, u in enumerate(units):
        x = 2 + k * 16
        charge = float(u.get("battery") or 0)
        d.rectangle((x, 8, x + 10, 22), outline=(170, 170, 190))
        d.rectangle((x + 3, 6, x + 7, 7), fill=(170, 170, 190))
        h = int(13 * charge / 100 * _ease(t))
        if h:
            d.rectangle((x + 1, 22 - h, x + 9, 21), fill=_level_color(100 - charge, 50, 80))
        online = str(u.get("status", "")).lower().startswith("online")
        if online and i % 10 < 6:
            for px, py in ((6, 11), (5, 13), (6, 13), (7, 13), (6, 15)):  # lightning bolt
                img.putpixel((x + px - 1, py + 1), (255, 230, 60))
        label = f"{charge:.0f}" if charge >= 100 else f"{charge:.0f}%"  # "100%" twice won't fit
        gfx.text(img, (x + 5 - gfx.text_width(label, "tom-thumb") // 2, 25), label, (150, 160, 190), "tom-thumb")


def _lab_plex(img, d, lab, i, t):
    plex = lab["plex"]
    _title(img, "PLEX")
    n = int(plex.get("watching") or 0)
    pulse = 0.55 + 0.45 * abs(math.sin(t * 3))
    col = gfx.scale((255, 170, 30), pulse if n else 0.5)
    d.polygon([(3, 8), (3, 20), (13, 14)], fill=col)
    gfx.text(img, (18, 9), str(n), (255, 200, 120) if n else (140, 140, 160), "6x10")
    gfx.text_center(img, 24, "WATCHING" if n else "IDLE", (255, 200, 120) if n else (140, 140, 160), "tom-thumb")
