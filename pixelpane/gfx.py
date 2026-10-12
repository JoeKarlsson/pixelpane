"""Drawing helpers for a 32x32 panel: fonts, text, colors, sprites."""
import colorsys
import os
from functools import lru_cache
from pathlib import Path

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

W = H = 32
FONT_DIR = Path(__file__).with_name("fonts")
CACHE_DIR = Path(os.environ.get("PIXELPANE_CACHE", "/tmp/pixelpane-cache"))

# Cell height and the y offset that puts the glyph tops at the given y.
FONT_METRICS = {"tom-thumb": (6, 0), "4x6": (6, 0), "5x7": (7, 0), "5x8": (8, 0), "6x10": (10, 0)}


@lru_cache(maxsize=None)
def font(name="5x7"):
    """Load a BDF font from pixelpane/fonts as a PIL bitmap font (cached as .pil)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stem = CACHE_DIR / name
    if not stem.with_suffix(".pil").exists():
        with open(FONT_DIR / f"{name}.bdf", "rb") as fp:
            BdfFontFile.BdfFontFile(fp).save(str(stem))
    return ImageFont.load(str(stem.with_suffix(".pil")))


def text_width(text, name="5x7"):
    return int(font(name).getlength(text))


def text(img, xy, s, color, name="5x7"):
    ImageDraw.Draw(img).text(xy, s, font=font(name), fill=color)


def text_center(img, y, s, color, name="5x7"):
    text(img, ((W - text_width(s, name)) // 2, y), s, color, name)


def blank(color=(0, 0, 0)):
    return Image.new("RGB", (W, H), color)


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def scale(color, f):
    return tuple(max(0, min(255, int(c * f))) for c in color)


def hex_color(s, default=(255, 255, 255)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError, IndexError):
        return default


# --- ASCII sprites -----------------------------------------------------------
# Each sprite is rows of characters; PALETTE maps a character to a color and
# "." is transparent. Sprites are cached as RGBA images.

PALETTE = {
    "K": (0, 0, 0), "W": (255, 255, 255), "w": (150, 150, 160), "g": (70, 70, 80),
    "R": (230, 30, 30), "r": (130, 10, 10), "P": (255, 90, 160), "p": (150, 30, 90),
    "O": (255, 120, 0), "o": (170, 60, 0), "Y": (255, 210, 0), "y": (180, 130, 0),
    "G": (40, 200, 60), "d": (10, 100, 30), "L": (140, 230, 60),
    "B": (40, 110, 255), "b": (20, 40, 140), "C": (80, 220, 255), "c": (30, 120, 170),
    "N": (140, 80, 30), "n": (80, 45, 15), "V": (160, 70, 230), "v": (80, 30, 130),
    "S": (255, 230, 170),
}

SPRITES = {
    # weather (12 wide)
    "sun": [
        "....Y..Y....",
        ".Y........Y.",
        "....YYYY....",
        "...YYYYYY...",
        "Y..YYYYYY..Y",
        "...YYYYYY...",
        "...YYYYYY...",
        "....YYYY....",
        ".Y........Y.",
        "....Y..Y....",
    ],
    "moon": [
        "....YYY.....",
        "..YYY.......",
        ".YYY........",
        ".YY.........",
        "YYY.........",
        "YYY.........",
        ".YYY.....Y..",
        ".YYYY..YYY..",
        "..YYYYYYY...",
        "....YYYY....",
    ],
    "cloud": [
        "............",
        "............",
        "....www.....",
        "..wwWWWww...",
        ".wWWWWWWWw..",
        "wWWWWWWWWWww",
        "wWWWWWWWWWWw",
        ".wwwwwwwwww.",
        "............",
        "............",
    ],
    "partly": [
        ".Y..Y.......",
        "..YYYY......",
        "YYYYYYY.....",
        ".YYYwww.....",
        ".YwwWWWww...",
        "..wWWWWWWw..",
        ".wWWWWWWWWww",
        ".wWWWWWWWWWw",
        "..wwwwwwwww.",
        "............",
    ],
    "fog": [
        "............",
        "wwwwwwww....",
        "............",
        "..wwwwwwwwww",
        "............",
        "wwwwwwwwww..",
        "............",
        "...wwwwwwwww",
        "............",
        "wwwwwww.....",
    ],
    # notification icons (8x8)
    "bell": [
        "...YY...",
        "..YYYY..",
        ".YYYYYY.",
        ".YYYYYY.",
        ".YYYYYY.",
        "YYYYYYYY",
        "........",
        "...YY...",
    ],
    "mail": [
        "........",
        "WWWWWWWW",
        "WW....WW",
        "W.W..W.W",
        "W..WW..W",
        "W......W",
        "WWWWWWWW",
        "........",
    ],
    "alert": [
        "...RR...",
        "...RR...",
        "..RWWR..",
        "..RWWR..",
        ".RRWWRR.",
        ".RRRRRR.",
        "RRRWWRRR",
        "RRRRRRRR",
    ],
    "check": [
        "........",
        ".......G",
        "......GG",
        "G....GG.",
        "GG..GG..",
        ".GGGG...",
        "..GG....",
        "........",
    ],
    "heart": [
        ".RR..RR.",
        "RRRRRRRR",
        "RRRRRRRR",
        "RRRRRRRR",
        ".RRRRRR.",
        "..RRRR..",
        "...RR...",
        "........",
    ],
    "door": [
        ".NNNNNN.",
        ".NnnnnN.",
        ".NnnnnN.",
        ".NnnnYN.",
        ".NnnnnN.",
        ".NnnnnN.",
        ".NnnnnN.",
        "gggggggg",
    ],
    "music": [
        "...CCCCC",
        "...CCCCC",
        "...C...C",
        "...C...C",
        "...C...C",
        ".CCC.CCC",
        "CCCCCCCC",
        ".CC..CC.",
    ],
    "calendar": [
        ".W....W.",
        "RRRRRRRR",
        "RRRRRRRR",
        "WWWWWWWW",
        "WgWgWgWW",
        "WWWWWWWW",
        "WgWgWgWW",
        "WWWWWWWW",
    ],
    "package": [
        "..NNNN..",
        ".NNYYNN.",
        "NNNYYNNN",
        "nNNYYNNn",
        "nnNYYNnn",
        "nnnYYnnn",
        "nnnnnnnn",
        "........",
    ],
    "home": [
        "...OO...",
        "..OOOO..",
        ".OOOOOO.",
        "OOOOOOOO",
        ".WWWWWW.",
        ".WWNNWW.",
        ".WWNNWW.",
        ".WWNNWW.",
    ],
    "lock": [
        "..wwww..",
        ".w....w.",
        ".w....w.",
        "YYYYYYYY",
        "YYYyyYYY",
        "YYYyyYYY",
        "YYYYYYYY",
        "........",
    ],
    "washer": [
        "WWWWWWWW",
        "WgWWWWWW",
        "WWWccWWW",
        "WWcCCcWW",
        "WWcCCcWW",
        "WWWccWWW",
        "WWWWWWWW",
        "........",
    ],
    "thermometer": [
        "...ww...",
        "...wR...",
        "...wR...",
        "...wR...",
        "...wR...",
        "..RRRR..",
        "..RRRR..",
        "...RR...",
    ],
    "drop": [
        "...C....",
        "...C....",
        "..CCC...",
        ".CCCCC..",
        ".CCWCC..",
        ".CCCCC..",
        "..CCC...",
        "........",
    ],
    "info": [
        "..BBBB..",
        ".BBWWBB.",
        "BBBBBBBB",
        "BBBWWBBB",
        "BBBWWBBB",
        "BBBWWBBB",
        ".BBWWBB.",
        "..BBBB..",
    ],
    "camera": [
        "........",
        "..ww....",
        "wwwwwwww",
        "wwWWWwww",
        "wWKKKWww",
        "wwWWWwww",
        "wwwwwwww",
        "........",
    ],
    "car": [
        "........",
        "..RRRR..",
        ".RCRRCR.",
        "RRRRRRRR",
        "RRRRRRRR",
        ".KK..KK.",
        ".KK..KK.",
        "........",
    ],
    "cat": [
        "O.....O.",
        "OO...OO.",
        "OOOOOOO.",
        "OKOOOKO.",
        "OOOPOOO.",
        ".OOOOO..",
        "..OOO...",
        "........",
    ],
    # seasonal
    "pumpkin": [
        ".......dd.......",
        "......dd........",
        "...OOOOdOOOO....",
        "..OOOooOooOOO...",
        ".OOOooOOOooOOO..",
        "OOOYYOOOOOYYOOO.",
        "OOYYYYOOOYYYYOO.",
        "OOOOOOOYOOOOOOO.",
        "OOOOOOYYYOOOOOO.",
        "OOYOOOOOOOOOYOO.",
        "OOYYYOYYYOYYYOO.",
        ".OOYYYYYYYYYOO..",
        "..OOOOOOOOOOO...",
        "...ooOOOOOoo....",
    ],
    "bat1": [
        "V.....V",
        "VV.R.VV",
        "VVVVVVV",
        ".V...V.",
    ],
    "bat2": [
        "...R...",
        ".VVVVV.",
        "VV...VV",
        "V.....V",
    ],
    "cake": [
        "..................",
        "..................",
        "..................",
        "..................",
        "..PPPPPPPPPPPPPP..",
        ".PWPWPWPWPWPWPWPP.",
        ".SSSSSSSSSSSSSSSS.",
        ".PPPPPPPPPPPPPPPP.",
        ".SSSSSSSSSSSSSSSS.",
        ".NNNNNNNNNNNNNNNN.",
        ".NnNnNnNnNnNnNnNN.",
        ".NNNNNNNNNNNNNNNN.",
        "wwwwwwwwwwwwwwwwww",
    ],
    "shamrock": [
        "...GG..GG...",
        "..GGGGGGGG..",
        "..GGGGGGGG..",
        "...GGGGGG...",
        ".GGG.GG.GGG.",
        "GGGGGGGGGGGG",
        "GGGGGGGGGGGG",
        ".GGGGddGGGG.",
        "..GG.dd.GG..",
        ".....dd.....",
        "....dd......",
    ],
    "snowman": [
        "....KKKK....",
        "....KKKK....",
        "...KKKKKK...",
        "....WWWW....",
        "...WKWWKW...",
        "...WWOOWW...",
        "....WWWW....",
        "..RRRRRRRR..",
        "..WWWWWWWW..",
        ".WWWWKWWWWW.",
        ".WWWWWWWWWW.",
        ".WWWWKWWWWW.",
        "..WWWWWWWW..",
    ],
}


@lru_cache(maxsize=None)
def sprite(name):
    rows = SPRITES[name]
    w, h = max(len(r) for r in rows), len(rows)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in PALETTE:
                px[x, y] = PALETTE[ch] + (255,)
    return img


def paste(img, name_or_sprite, xy):
    s = sprite(name_or_sprite) if isinstance(name_or_sprite, str) else name_or_sprite
    img.paste(s, xy, s)


ICONS = [k for k, v in SPRITES.items() if len(v) == 8 and len(v[0]) == 8]
