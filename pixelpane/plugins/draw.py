"""Draw: what you scribble on the Draw page shows on the board as you draw it, and
frames made on the Animate page play as a loop."""
from ..plugin import Plugin
from ..state import fit

plugin = Plugin(
    "draw", "Draw on the board live, or animate frames",
    about="The Draw page shows what you draw on the board while you draw it. The Animate "
          "page makes frame-by-frame animations that play on the board and save to the GIF "
          "library. Either one holds the board on your drawing until you press Stop showing "
          "(or Clear in Modes on the control page).")

FRAME = 0.04   # how often the scene looks for a newer drawing: changes show within this


@plugin.scene("sketch", kind="mode", empty_text="Nothing drawn yet")
def sketch(ctx, secs):
    sk = ctx.state.sketch
    size = ctx.gifs.gif_size()
    seen, shown, t = None, [], 0.0
    while t < secs:
        frames, ms, version = sk.get()
        if not frames:
            return
        if version != seen:   # drawn at another panel size: fit it to this one
            shown = [f if f.size == size else fit(f, size=size) for f in frames]
            seen = version
        yield shown[int(t * 1000 // ms) % len(shown)], FRAME
        t += FRAME
