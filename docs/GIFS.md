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

### Specific packs worth a look

Checked in October 2026. Most itch.io packs are "name your own price", so $0 works.
Sprite sheets need slicing (see below). The 16 px ones look best at 2x, or as a
2x2 grid.

**Game sprites**

| Pack | What's in it | License |
|------|--------------|---------|
| [Pixel Adventure 1](https://pixelfrog-assets.itch.io/pixel-adventure-1) (Pixel Frog) | platformer heroes (Ninja Frog and friends), fruit and items | CC0 |
| [Kings and Pigs](https://pixelfrog-assets.itch.io/kings-and-pigs) (Pixel Frog) | a king and his pigs, lots of funny animations; some frames are wider than 32, so crop | CC0 |
| [DungeonTileset II](https://0x72.itch.io/dungeontileset-ii) (0x72) | 16 px knights, wizards, monsters, torches and chests | CC0 |
| [Ninja Adventure](https://pixel-boy.itch.io/ninja-adventure-asset-pack) (Pixel-boy) | 50+ characters, 30+ monsters and 9 bosses, all 16 px, Zelda-like | CC0 |
| [A platformer in the forest](https://opengameart.org/content/a-platformer-in-the-forest) (Buch) | 16 px heroes that walk, run, jump, slash and climb; NES feel | CC0 |
| [Free Pixel Monsters 16x16](https://danaida.itch.io/free-pixel-monsters-pack-16x16) (DanAida) | 25 cute animated blob monsters | free to use, don't redistribute |
| [The Spriters Resource](https://www.spriters-resource.com) | real Nintendo, Sega and other game sprites, ripped from the games | the games' copyright: fine on your own wall, never share or ship them |

**Pixel art as art**

| Where | What | License |
|-------|------|---------|
| [Pixel Joint](https://www.pixeljoint.com/pixels/new_icons.asp) | a curated gallery; filter by Anim = Yes and by size | the artists keep their rights: personal use |
| [Pixilart](https://www.pixilart.com) | huge community gallery, lots drawn at exactly 32x32, GIF download | personal use |
| [Canvas Cycle](http://www.effectgames.com/demos/canvascycle/) (Mark Ferrari) | the famous color-cycling landscapes; too big to use, great to copy the idea | personal use |

**Motivation and feel-good**

| Pack | What | License |
|------|------|---------|
| [Pixel Heart Animation](https://nicolemariet.itch.io/pixel-heart-animation-32x32-16x16-freebie) (Nicole Marie T) | a beating heart at exactly 32x32, as a ready GIF | free, credit asked |
| [16x16 animated hearts](https://dmitriy-shmilo.itch.io/16x16-animated-hearts) (dmitriy-shmilo) | heart loops | any use, no credit needed |
| [Hearts and Stars](https://ivnolida.itch.io/heartsandstars) (ivnolida) | an animated heart and star, ready GIFs | CC-BY 3.0 |
| [Pixel VFX Level Up](https://sentient-dream-studio.itch.io/pixel-vfx-level-up-effect) (Sentient Dream) | a level-up burst | free to use, no resale |
| [Animated emote bubbles](https://opengameart.org/content/animated-emote-bubbles) | 16 px RPG speech balloons: love, surprise, "!" and "?" | CC0 |

Nobody seems to give away "you got this" or "quest complete" banners. Ask the
**Make one** box for them instead (below), or put text over one of the hearts or
the level-up burst in Piskel.

**Made for LED panels**

| Where | What | License |
|-------|------|---------|
| [Tronbyt apps](https://github.com/tronbyt/apps) (the Tidbyt community apps) | hundreds of apps for 64x32 panels with sprites already tuned for black LEDs; the images live inside the `.star` files | Apache-2.0 |
| [Game Frame art forum](https://ledseq.com/forums/forum/game-frame/game-frame-art/) | fan animations made for a 16x16 LED frame, so 2x fits exactly | unclear, mostly fan art: personal use |

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

### Moving GIFs without renaming files

On the control page, ✎ on a GIF moves it to another category (pick one or type a
new name) or theme (or to "All year"). **Select** picks several GIFs, or a whole
page, and moves them together; with a category showing, **Rename category**
renames it on every GIF in it (an existing name merges the two). The files stay
where they are: the moves are saved on the board (`gif_meta` in its config), so
the next deploy doesn't undo them. "Back to where the file is" undoes a move.

The same from scripts:

```bash
curl -X PATCH  http://pixelpane.local/api/gifs/repo/retro-coin-spin.gif -H 'Content-Type: application/json' \
     -d '{"category": "arcade", "theme": "christmas"}'
curl -X POST   http://pixelpane.local/api/gifs/classify -H 'Content-Type: application/json' \
     -d '{"ids": ["repo/a.gif", "repo/b.gif"], "theme": "all"}'        # or {"ids": [...], "reset": true}
curl -X POST   http://pixelpane.local/api/categories/rename -H 'Content-Type: application/json' \
     -d '{"from": "retro", "to": "arcade"}'
```

Keep your library outside this repo (see "Keeping your own stuff out of the
repo" in the README); `tools/deploy.sh` copies it to the board.

## Make one from a prompt

**Make a GIF** on the control page asks a chat model to design one: type an idea
and press Generate, or press **Surprise me**. The model doesn't paint pixels; it
writes a short description (pixel sprites with walk or flap poses, shapes,
paths to follow, parts that swing at a joint, snow, stars, fire) and the board
renders that into a seamless loop. With **Check its own work** on, the board
then shows the model a picture of its render and lets it fix what it sees
(a hidden laser dot, a tail that sweeps through the body). That takes about
twice as long and needs a model that can read images.

Nothing goes in the library on its own. Each result is a **draft** with a big
preview, and you choose:

- **Show on the panel**: play it on the real LEDs once.
- **Refine**: say what to change ("make the cat bigger") for a new draft built on this one.
- **Try again**: a fresh design from the same prompt.
- **Save to library**: with the name, category and theme you pick.
- **Discard**: throw it away.

The last 60 drafts stay on the board under **Recent drafts** (saved ones are
marked), with their prompts, so you can come back to one later.

Set it up in the **generator** plugin's panel:

| Kind of server | Server URL | Model, for example |
|----------------|------------|--------------------|
| OpenAI-compatible: LiteLLM | `http://<litellm-host>:4000/v1` | an alias you defined |
| OpenAI-compatible: OpenRouter | `https://openrouter.ai/api/v1` | any model on its list |
| OpenAI-compatible: OpenAI | `https://api.openai.com/v1` | `gpt-4.1` |
| OpenAI-compatible: Ollama | `http://<ollama-host>:11434/v1` | `qwen3:14b` (no key) |
| Anthropic | leave empty (`https://api.anthropic.com`) | a Claude model |

Bigger models draw much better than small local ones. One draft is one or two
requests of a few thousand tokens. The board makes the requests itself, so it
needs a network path to that server.
