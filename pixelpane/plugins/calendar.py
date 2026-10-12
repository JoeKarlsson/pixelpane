"""Calendar: the next timed event, with a countdown."""
from datetime import datetime


from .. import gfx
from ..kit import animated_icon, gauge, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin(
    "calendar", "Next event and countdown", data={"next_event": 720},
    about="Shows your next timed event with a bar that empties as it gets closer, and a "
          "ringing bell in the last ten minutes. It only appears when an event starts "
          "within 12 hours; otherwise it quietly skips. Feed it from Home Assistant: "
          "POST /api/data/next_event with {title, start}.")


@plugin.scene("calendar")
def calendar(ctx, secs):
    ev = ctx.data("next_event")
    if not ev or not ev.get("title") or not ev.get("start"):
        return
    try:
        start = datetime.fromisoformat(str(ev["start"]))
        if start.tzinfo:
            start = start.astimezone().replace(tzinfo=None)
    except ValueError:
        return
    now = ctx.now()
    mins = (start - now).total_seconds() / 60
    if mins < -15 or mins > 12 * 60:
        return
    title = str(ev["title"]).upper()
    when = f"{start.hour % 12 or 12}:{start.minute:02d}"
    soon = "NOW" if mins <= 0 else f"IN {int(mins)}M" if mins < 120 else ""
    secs = max(secs, scroll_seconds(title, "5x7", 16) + 1)
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        animated_icon(img, "bell" if 0 <= mins < 10 else "calendar", (1, 1), t)
        gfx.text(img, (11, 2), when, (255, 255, 255), "4x6")
        if soon:
            urgent = 0 <= mins < 10 and i % 10 < 5
            gfx.text_center(img, 11, soon, (255, 60, 60) if urgent else (255, 170, 60), "tom-thumb")
        scroll_text(img, 18, title, (180, 220, 255), "5x7", t, 16)
        # countdown: the bar empties as the event gets closer (full = 2 hours away)
        gauge(img, 28, max(0.0, mins) / 120, t, (255, 170, 60) if mins > 10 else (255, 60, 60))
        yield img, 0.1
