---
name: pixel-gif
description: Make an animated 32x32 GIF for the PixelPane board in code (a sprite, an effect, an icon, a loop), preview it, show it on the real LEDs, and save it to the GIF library. Use when Joe asks for a new GIF, asset, animation or pixel art for the board, or wants an existing GIF redrawn.
---

# Pixel GIFs for PixelPane

Adapted from [codixel](https://github.com/mankidev/codixel) (MIT, © 2026 mankidev),
cut down to what matters on a 32x32 LED panel and rewritten for Python and PIL.

You don't paint. You write code that draws. Things you can describe as shapes,
motion and color ramps come out well. Complex organic subjects drawn from
memory (a dragon, a face, a specific animal) come out badly at any size.

## 1. Before drawing

- **Simple subject** (icon, coin, heart, CD, planet, flame, rain, a geometric
  loop): draw it in code. Go to 2.
- **Complex subject** (a character, an animal, a vehicle, anything with a face):
  ask Joe for a reference image, or offer a CC0 sprite from the sources in
  `docs/GIFS.md`. If he still wants it from scratch, keep it a few pixels big
  and simple, and show it right away.
- Someone else's art (a game sprite, an album cover): fine on Joe's own wall.
  Don't commit it to this repo; it goes in the library (see 5).
- Check `../pixelpane-library/gifs/` for an earlier version of the same subject
  and match it unless he says otherwise.

## 2. Draw it for the panel

The panel is 32x32 (`GET /api/sketch` returns `size` if the board is set to
something else). Black is "LED off", so the art floats on black.

- **Render big, then shrink.** Draw round or rotating things at 8x
  (256x256) and shrink with `Image.LANCZOS`. Rotating a 32px image directly
  gives jagged edges and broken lines. `cd_frame` in
  `pixelpane/plugins/now_playing.py` is a worked example.
  Exception: hard-edged pixel sprites stay on their own grid; draw them at 1x
  and scale previews with `Image.NEAREST`.
- **Color for LEDs.** Saturated colors and bold shapes survive the panel's
  two-way mirror; pastels and dark mid-tones vanish. Keep the subject well above
  about 25% brightness. No white or bright backgrounds: they light every LED and
  wash the picture out.
- **Ramps shift hue.** A shading ramp that only changes lightness looks dead.
  Darker steps move toward blue or purple, lighter steps toward yellow or
  orange; saturation drops a little at both ends. Build it with `colorsys`.
- **Flat bands, dither only where two bands meet.** At 32px there's no room for
  smooth gradients or dither across a whole area (it reads as noise). Shade with
  2 to 4 flat bands and a 1px checker strip at each border.
- **Shapes.** Build round shapes from round parts (a heart is two circles and a
  wedge). Thin parts keep one width. One-pixel diagonals go corner to corner,
  with no extra pixel in the L of each step.
- **One light**, top left unless asked otherwise. Something that should shine
  (a disc, a gem, a coin) gets a glint that stays still while the object moves:
  that's what makes motion read.
- **Effects** (fire, smoke, sparkle, rain) are built from a value per pixel
  (heat, density) from noise that moves over time, mapped to a dark-to-bright
  ramp. Keep the brightest part small, at the source. Add only a few particles.
  Don't use a per-pixel fire grid when Joe asks for realistic; it looks grainy.

## 3. Motion and loops

- 4 to 30 frames at 80 to 150 ms each (the board cuts GIFs at 400 frames).
- **Seamless loop.** The frame after the last is the first. Anything that
  repeats does a whole number of cycles per loop: a spin turns a whole number of
  times (or a whole number of symmetry steps), noise uses a time value that
  wraps.
- **Slower than you think.** Too fast is the most common mistake. Work out the
  pixels per frame before rendering: surface detail (ripples, smoke texture)
  moves well under 1 px per frame, and a calm area that changes more than about
  20% of its pixels per frame is boiling. Measure that with `frame_change` from
  the helper.
- Ease in and out (smoothstep) for things that start and stop. Constant speed is
  right only for spins and scrolls.

## 4. Check before you show

- Save a numbered frame sheet and look at it with the Read tool (Read shows only
  the first frame of a GIF). Put the last frame next to the first to check the
  seam, and 4 frames in a row to check step size.
- Look at the 1x image too: the shape must read at real size.
- Be your own critic: list the worst problem you see, fix it, look again. Show
  only when you can't find one more. Joe is not the QA step.
- When Joe says something is too much or too little, change it by about half,
  not all the way to the other end.
- Do only what was asked: no extra text, effects or colors.

## 5. Show it, then save it

Use the helper next to this file (run with the repo's `.venv/bin/python`):

```python
import sys; sys.path.insert(0, ".claude/skills/pixel-gif")
from pixelkit import save_gif, frame_sheet, frame_change, show_on_board

save_gif(frames, "out.gif", ms=100)              # 32x32 GIF, loops forever
save_gif(frames, "out-big.gif", ms=100, scale=10)  # zoomed copy for the mockup page
frame_sheet(frames, "sheet.png")                 # numbered sheet + first/last pair
```

1. **Mockup.** Put the zoomed GIF on a local HTML page per
   `~/.claude/knowledge/mockups.md` (`~/mockups/pixelpane-<topic>/index.html`,
   `image-rendering: pixelated` on a black panel, options labeled A/B/C, the
   current version first if there is one) and `open` it. Ask for a verdict by
   label.
2. **Real LEDs.** Colors look different on the panel. Offer to show it there:
   `show_on_board(frames, ms)` holds the board on it through the Draw page's
   sketch. It refuses when the board is already pinned to something else (ON AIR
   during meetings); don't unpin that. Afterwards `DELETE /api/pin` hands the
   board back, only if `/api/health`
   still shows `"pinned"` on `sketch`.
3. **Save only after Joe approves.** Write the 32x32 GIF to
   `../pixelpane-library/gifs/<category>-<color>-<subject>.gif` (the part before
   the first `-` is the Play now category; seasonal ones go in
   `gifs/themes/<theme>/`), then run `tools/deploy.sh`. Any reference that isn't
   Joe's own or CC0 gets a row in `../pixelpane-library/ATTRIBUTION.md`.
   Don't put GIFs in this repo: it ships none on purpose.
