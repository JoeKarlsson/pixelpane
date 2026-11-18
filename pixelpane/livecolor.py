"""The web pages' one color, taken from what the board is showing (the "lit pixels" look)."""

LIVE_DEFAULT = "#ff9a2e"   # warm amber for the page when the board shows nothing colorful
_live = {"frame": None, "color": None}


def _luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_on_black_text(rgb):
    """rgb lightened toward white until black text on it passes 4.5:1 (luminance >= 0.175)."""
    rgb = tuple(rgb)
    while _luminance(rgb) < 0.175:
        rgb = tuple(min(255, round(c + (255 - c) * 0.1)) for c in rgb)
    return rgb


def live_color(frame, on=True, default=LIVE_DEFAULT):
    """The web pages' one color: the most vivid color the board is showing, as hex, or
    `default` (the Appearance setting) when it's off or shows nothing colorful.
    Cached per frame object, since the board makes a new one for every frame it shows."""
    if not on or frame is None:
        return default
    if _live["frame"] is frame:
        return _live["color"] or default
    from .plugins.now_playing import art_palette
    picks = art_palette(frame.convert("RGB"))
    color = "#%02x%02x%02x" % readable_on_black_text(picks[0]) if picks else None
    _live.update(frame=frame, color=color)
    return color or default
