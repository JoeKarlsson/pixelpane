"""GIFs: plays the GIF library (all-year, themed and uploads)."""


from ..plugin import Plugin

plugin = Plugin("gifs", "The GIF library", defaults={"theme_share": 0.35})


# --- GIFs --------------------------------------------------------------------

@plugin.scene("gif", "gif")
def gif(ctx, secs, path=None, category=None):
    path = path or ctx.next_gif(category)
    if not path:
        return
    frames = ctx.gif_frames(path)
    if not frames:
        return
    ctx.label = f"gif: {path.name}"
    elapsed = 0.0
    while elapsed < secs:
        for img, hold in frames:
            yield img, hold
            elapsed += hold
            if elapsed >= secs:
                break
