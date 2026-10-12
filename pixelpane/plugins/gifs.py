"""GIFs: plays the GIF library (all-year, themed and uploads)."""


from ..plugin import Plugin

plugin = Plugin(
    "gifs", "The GIF library", defaults={"theme_share": 0.35},
    about="Plays GIFs from your library. All-year GIFs play any day; GIFs in a theme "
          "folder (Halloween, Christmas, your birthday...) only play while that theme is "
          "active. A playlist entry like gif:retro plays one from a single category "
          "(the part of the file name before the first dash).",
    fields=[{"key": "theme_share", "label": "Share of seasonal GIFs", "type": "range",
             "min": 0, "max": 1, "step": 0.05,
             "help": "When a season or holiday is active, how often a GIF slot picks from its folder."}])


# --- GIFs --------------------------------------------------------------------

@plugin.scene("gif", "gif", params={"id": "text"}, empty_text="NO GIFS")
def gif(ctx, secs, path=None, category=None):
    path = path or ctx.next_gif(category)
    if not path:
        return
    frames = ctx.gif_frames(path)
    if not frames:
        return
    ctx.label = f"gif: {path.name}"
    ctx.gif_played(path)
    elapsed = 0.0
    while elapsed < secs:
        for img, hold in frames:
            yield img, hold
            elapsed += hold
            if elapsed >= secs:
                break
