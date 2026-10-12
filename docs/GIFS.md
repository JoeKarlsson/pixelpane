# GIFs: where to find them and how to make them

The panel is 32x32. GIFs drawn as pixel art at 16, 32 or 64 pixels look sharp;
anything shrunk down from video or photos turns to mush. This repo ships no GIFs
(most GIFs online have unclear licenses), so bring your own.

## Where to look

| Source | What you get | License |
|--------|--------------|---------|
| [OpenGameArt.org](https://opengameart.org) | animated sprites and sprite sheets; filter by CC0 | CC0 / CC-BY (credit the artist) |
| [Kenney.nl](https://kenney.nl/assets) | big packs of game sprites, 16-64 px | CC0 |
| [itch.io free pixel-art assets](https://itch.io/game-assets/free/tag-pixel-art) | characters, effects, seasonal tiles | per pack; check each page |
| Divoom Pixoo gallery (phone app) | thousands of 16/32/64 px animations made for LED panels | personal use |
| [Piskel](https://www.piskelapp.com) or [Aseprite](https://www.aseprite.org) | draw your own at 32x32 | yours |

Good search terms: "pixel art <thing> animated", "<thing> sprite sheet 32x32",
"8-bit <thing> gif". For seasons: pumpkins, bats and ghosts; falling leaves;
snowflakes and snowmen; fireworks; hearts; shamrocks; cake and balloons.

Keep a note of the source and license of anything CC-BY in your library (an
ATTRIBUTION file is enough).

## Making them panel-ready

`tools/ingest-gif.sh` turns any GIF, PNG or WebP into a looping 32x32 GIF:

```bash
tools/ingest-gif.sh --name retro-coin-spin ~/Downloads/coin.gif   # pixel art: crisp nearest-neighbor
tools/ingest-gif.sh --smooth ~/Downloads/loop.gif                  # photos and smooth art
```

Or just upload on the control page: it does the same conversion.

**Sprite sheets** (a PNG strip of frames) need slicing first. With ImageMagick:

```bash
magick sheet.png -crop 32x32 +repage -set delay 10 -loop 0 -dispose background out.gif
```

**Tips for good-looking GIFs on an LED panel:**

- Black backgrounds look best: black LEDs are off, so the art floats. White or
  bright backgrounds light every LED and wash out the picture.
- Bold outlines and saturated colors survive the two-way mirror; pale pastels
  disappear.
- 4-30 frames at 80-150 ms each loop nicely; very long GIFs are cut at 400
  frames.

## Naming and folders

```
gifs/retro-coin-spin.gif            all year; the part before the first "-" is its category
gifs/themes/halloween/bat-flap.gif  only while that theme is active
```

Categories (`retro`, `space`, `animal`, ...) get their own Play now buttons and
playlist entries like `gif:retro`. Themes: autumn, winter, spring, summer,
halloween, thanksgiving, christmas, new_year, valentines, st_patricks, july4,
birthday.

Keep your library outside this repo (see "Keeping your own stuff out of the
repo" in the README); `tools/deploy.sh` copies it to the board.
