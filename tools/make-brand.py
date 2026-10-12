"""Regenerate the PixelPane mark, favicons and app icons.

    python tools/make-brand.py

The mark is a 15x15 pixel window: a soft frame, four panes in a gradient of
joekarlsson.com's colors (peach, pink, lavender, teal), a glass reflection band and a sparkle.
"""
from pathlib import Path

from PIL import Image, ImageDraw

N = 15
STOPS = [(253, 174, 132), (249, 168, 212), (196, 181, 253), (139, 203, 200)]  # joekarlsson.com: peach, pink, lavender, teal
FRAME = (226, 232, 240)
SPARK = (255, 255, 255)
ROOT = Path(__file__).resolve().parents[1]


def mix(t):
    t = max(0.0, min(1.0, t)) * (len(STOPS) - 1)
    i = min(int(t), len(STOPS) - 2)
    f = t - i
    return tuple(round(a + (b - a) * f) for a, b in zip(STOPS[i], STOPS[i + 1]))


def tint(c, k):
    return tuple(round(v + (255 - v) * k) for v in c)


def cells():
    out = {}
    for y in range(N):
        for x in range(N):
            if (x, y) in ((0, 0), (N - 1, 0), (0, N - 1), (N - 1, N - 1)):
                continue                                  # pixel-rounded corners
            if x in (0, N - 1) or y in (0, N - 1) or x == 7 or y == 7:
                out[(x, y)] = (FRAME, 0.9)
            else:
                base = mix((x + y) / (2 * (N - 2)))
                band = (x + y) in (5, 6) and x < 7 and y < 7   # glass reflection, top-left pane
                out[(x, y)] = (tint(base, 0.55) if band else base, 1.0)
    for x, y in ((11, 9), (10, 10), (11, 10), (12, 10), (11, 11)):   # sparkle
        out[(x, y)] = (SPARK, 1.0)
    return out


def svg(c, bg=None):
    pad = 1 if bg else 0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad} {-pad} {N + 2 * pad} {N + 2 * pad}">']
    if bg:
        parts.append(f'<rect x="-1" y="-1" width="{N + 2}" height="{N + 2}" rx="3.4" fill="{bg}"/>')
    for (x, y), (col, a) in sorted(c.items()):
        hexc = "#%02x%02x%02x" % col
        op = f' fill-opacity="{a}"' if a < 1 else ""
        parts.append(f'<rect x="{x + .07:.2f}" y="{y + .07:.2f}" width=".86" height=".86" rx=".24" fill="{hexc}"{op}/>')
    return "".join(parts) + "</svg>"


def raster(c, px, bg=(17, 19, 24, 255), pad=1):
    s = px / (N + 2 * pad)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg:
        d.rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * 0.2), fill=bg)
    g = s * 0.07
    for (x, y), (col, a) in c.items():
        x0, y0 = (x + pad) * s, (y + pad) * s
        d.rounded_rectangle((x0 + g, y0 + g, x0 + s - g, y0 + s - g), radius=s * 0.24, fill=col + (int(255 * a),))
    return img


if __name__ == "__main__":
    c = cells()
    st = ROOT / "pixelpane" / "static"
    (st / "logo-mark.svg").write_text(svg(c))
    (st / "favicon.svg").write_text(svg(c, bg="#111318"))
    raster(c, 32).save(st / "favicon-32.png")
    raster(c, 512).resize((180, 180), Image.LANCZOS).convert("RGB").save(st / "apple-touch-icon.png")
    raster(c, 256).save(st / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    raster(c, 512).save(st / "icon-512.png")
    print("brand assets written to", st)
