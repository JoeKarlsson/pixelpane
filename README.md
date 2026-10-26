<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.png">
    <img src="docs/images/logo-light.png" width="420" alt="PixelPane">
  </picture>
</p>

<p align="center"><b>A 32x32 LED art pane for your wall, driven by a Raspberry Pi.</b></p>

<p align="center">
  <a href="https://github.com/JoeKarlsson/pixelpane/actions/workflows/ci.yml"><img src="https://github.com/JoeKarlsson/pixelpane/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-a98bff" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/Raspberry%20Pi-3%20%7C%204%20%7C%205-58e0c8" alt="Raspberry Pi 3, 4, 5">
</p>

It mixes pixel-art
GIFs with live, animated scenes: a clock, weather, what's playing (with album
art), your next meeting, a homelab dashboard, seasonal and holiday animations,
and generative art. Home Assistant can push notifications to it (doorbell,
laundry, weather warnings) and control it like a light. Everything is a plugin,
in the spirit of MagicMirror.

<p align="center"><img src="docs/images/board-demo.gif" width="400" alt="The board on a desk: a shadow box with a two-way mirror front, showing the clock, a spinning planet and a Halloween scene"></p>

What it shows, panel's-eye view:

![Nine of the built-in scenes, animated](docs/images/scenes.gif)

| Control page | On a phone |
|---|---|
| ![The control page: live preview, now playing, Play now buttons](docs/images/control-page.png) | ![The control page on a phone](docs/images/control-page-phone.png) |

## What it does

- **Scenes, not just a slideshow.** A playlist mixes GIFs with live scenes. A
  scene with nothing to show (no music playing, no meeting soon) is skipped.
- **Everything animates.** Icons ring, hop and spin; gauges fill; the homelab
  dashboard cycles through six animated pages.
- **Readings you can feel from across the room.** Send a temperature, air quality,
  humidity or CO2 reading and the whole panel shows it: frost creeping in, heat
  shimmer, thick smog, condensation running down. The weather fills the panel too,
  with rain slanting in the wind. A reading that turns bad jumps the queue.
- **Seasons and holidays.** Autumn leaves, snow, flowers, beach days, Halloween,
  Thanksgiving, Christmas, New Year, Valentine's, St. Patrick's, the Fourth of
  July and your birthday, each with a scene and its own GIF folder. Add your
  own holidays (Diwali, Lunar New Year, an anniversary), switch built-in ones
  off, or flip the seasons for the southern hemisphere.
- **A web app in five pages**: a control page (live preview, a "now playing"
  view that follows the playlist, a drag-and-drop playlist editor and plugin
  switches), Draw (scribble on the board live), Animate (frame-by-frame loops
  that save as GIFs), a GIFs page (the generator and the library; uploads
  convert anything to 32x32) and Settings. Dark, light or match-the-device, in an accent
  color you pick.
- **GIFs from a prompt.** Type "a cat chasing a laser dot" (or press Surprise
  me) and a chat model (any OpenAI-compatible server such as LiteLLM,
  OpenRouter or Ollama, or Anthropic's API) designs a looping animation. Preview
  it, refine it, then save it to your library or throw it out. See
  [which models draw best](docs/GIFS.md#choosing-a-model).
- **Draw on the board, live.** The Draw page is a pixel canvas the size of the
  board: what you scribble shows on the panel as you draw it, until you press Stop
  showing. Pen, eraser, fill and a color picker, brush sizes, a mirror for
  symmetric drawings, an opacity slider for softer shades, undo, and a palette that
  reads well on LEDs.
- **Animate it.** The Animate page makes frame-by-frame loops: step through frames
  with the arrows (or ← →), add, copy, delete and reorder them, and see the frame
  before as a teal onion-skin ghost. Start from an example (a bouncing ball, a
  heartbeat, a blinking face, a spinner, a rainbow wave) and pull it apart. With Live
  on, the board plays your loop while you edit it; with it off, Show on board sends
  it when you're ready. The same button then reads Stop showing. Either page saves to the GIF library.
- **Transitions and overlays.** Scenes fade (or wipe, slide, dissolve, iris, melt, switch off like an old TV, and more) into each
  other, GIFs can carry a small clock, date, temperature or meeting countdown in
  their calmest corner, and Home Assistant can light status dots along the top edge
  (laundry done, garage open).
- **Notifications in four styles** (classic, a banner that slides down, a burst
  of ripples, a big ticker), plus ones the board raises by itself: reminders at a
  time on the days you pick, and watches that go off when the air turns bad, it
  starts to snow or a meeting is five minutes away. Set them up on the Settings page.
- **An HTTP API** for notifications, modes (ON AIR, messages) and data.
- **Home Assistant ready**: a light entity, a feed automation and notification
  examples in [docs/HOME_ASSISTANT.md](docs/HOME_ASSISTANT.md).
- **Appliance-grade setup**: one idempotent installer, unattended security
  updates, logs in RAM, runs unprivileged, survives power cuts.

## Build one

You need a Raspberry Pi, an Adafruit RGB Matrix HAT (or Bonnet), a 32x32 HUB75
panel, a 5 V 4 A supply for the panel plus the Pi's own supply and, for the finished look, a shadow box with a
3D-printed light grid behind a two-way mirror. The full parts list, diagrams and
assembly steps are in **[docs/HARDWARE.md](docs/HARDWARE.md)**.

| Pi | Driver | Status |
|----|--------|--------|
| Pi 3 B / 3 B+ | hzeller/rpi-rgb-led-matrix | the reference build |
| Pi 4, Zero 2 W | hzeller/rpi-rgb-led-matrix | supported (set `gpio_slowdown` if it flickers) |
| Pi 5 | Adafruit PioMatter | supported in code, picked automatically; not yet tested on hardware |

## Install

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In its
   settings set a hostname, a user, your SSH public key, Wi-Fi and its country.
2. On your computer, clone this repo and run the deploy script:

   ```bash
   git clone https://github.com/JoeKarlsson/pixelpane && cd pixelpane
   PIXELPANE_HOST=pi@pixelpane.local PIXELPANE_TZ=America/Chicago tools/deploy.sh
   ```

   It copies the code to the Pi and runs `install.sh`, which builds the LED
   driver (about 10 minutes on a Pi 3), installs the service and hardens the
   box. Run it again any time; it only changes what changed.
3. Reboot once if it says `REBOOT NEEDED`, then open `http://pixelpane.local/`.
4. Add GIFs: see **[docs/GIFS.md](docs/GIFS.md)** for where to find them and
   how to make your own. Upload them on the page, or keep a library folder and
   deploy it (below).

### Keeping your own stuff out of the repo

Put your GIFs and settings in a sibling folder, by default
`../pixelpane-library`:

```
pixelpane-library/
  gifs/                 all-year GIFs, named <category>-<what-it-shows>.gif
  gifs/themes/<theme>/  seasonal GIFs (halloween, winter, birthday, ...)
  plugins/              your own plugins, one .py file each (docs/PLUGINS.md)
  deploy.env            PIXELPANE_HOST=..., PIXELPANE_KEY=..., PIXELPANE_TZ=..., PIXELPANE_WIFI_COUNTRY=...
```

`tools/deploy.sh` picks it up automatically (`PIXELPANE_LIBRARY` points elsewhere).

## Plugins

| Plugin | Scenes | Takes data |
|--------|--------|------------|
| clock | clock, on a classic, frame, arcade or sky face | |
| weather | weather (+ Open-Meteo fallback) | `weather` |
| now_playing | now_playing, with album art, in the album's colors; comes round more often while music plays, and shows dimmed while paused | `now_playing` |
| calendar | calendar, with a countdown; comes round more often when a meeting is close | `next_event` |
| homelab | a six-page animated dashboard | `homelab` |
| tiles | readings that look how they feel (temperature, air quality, humidity, CO2, battery), or cards with animated icons and gauges | `tiles` |
| alerts | notify (classic, banner, burst or ticker), on_air, message | |
| gifs | gif, gif:&lt;category&gt; | |
| seasonal | a scene per season and holiday, plus your birthday | |
| generative | fire, plasma, life, matrix_rain, starfield, lava, ripples, reaction, sand, aurora, fireflies, aquarium, snake, hourglass, smog; an `ambient` slot that picks one to suit the weather and air | |
| aquatic | aquatic: a living fish tank. Fish hatch, grow, lay eggs and grow old over days; rare colors run in families; the tank earns a starfish, castle, chest and snail; it follows the sun, feeds itself, goes murky when the air is stale (CO2, temperature and air quality tiles), and the fish greet you or scatter at a tap (`/api/play` params `greet`, `tap`). The generative `aquarium` shows this tank too | |
| window | window: a landscape whose sky is the real one: the sun and the moon (in its phase) where they are, clouds, rain, snow, hail, lightning and fog as they are, wind in the tree and the chimney smoke, the season, haze when the air is bad, a lit house at dusk | (uses `weather`) |
| sky | moon (phase, named full moons, supermoons, blue moons), zodiac | |
| effects | no scenes: transitions, up to four overlays (time, date, temperature, a tile reading, your next meeting, your own text), status dots | `status` |
| triggers | no scenes: reminders and watches that raise notifications | |
| room_light | no scenes: the panel dims in a dark room and comes up in a bright one | `room_light` (`{"lux": 120}`) |
| draw | sketch: whatever the Draw and Animate pages send, held on screen until you stop it | |
| generator | no scenes: settings for making GIFs from a prompt ([docs/GIFS.md](docs/GIFS.md#make-one-from-a-prompt)) | |

Switch plugins on or off on the control page (a card opens that plugin on the Settings
page, with its options, its scenes and the data it has received), or in the config. Writing your
own takes one Python file: see **[docs/PLUGINS.md](docs/PLUGINS.md)**.

![Plugin switches on the control page](docs/images/plugins.png)

## Configuration

Settings live on the Pi in `/var/lib/pixelpane/config.json` and are edited from
the pages (the **Settings** page has the schedule, timings, holidays, appearance,
display hardware, access, backup and system status) or `PUT /api/config`. Every
key is described in **[docs/CONFIG.md](docs/CONFIG.md)**; defaults are in
[`pixelpane/default_config.json`](pixelpane/default_config.json). An example:

```json
{
  "brightness": 60,
  "rotation": ["clock", "gif", "seasonal", "weather", "gif:retro", "homelab"],
  "dwell": {"gif": 20, "clock": 10},
  "plugins": {
    "seasonal": {"birthday": {"month": 4, "day": 13, "name": "Joe"}},
    "weather": {"latitude": 51.5, "longitude": -0.12},
    "now_playing": {"art_hosts": ["http://homeassistant.local:8123/"]},
    "generative": {"enabled": false}
  },
  "themes": {"off": ["july4"], "custom": [{"name": "Diwali", "dates": [["2026-11-08", "2026-11-12"]]}]},
  "ui": {"theme": "auto", "accent": "#8bcbc8"},
  "display": "auto",
  "adafruit_board": "hat",
  "schedule": [
    {"label": "Quiet hours", "from": "23:00", "to": "07:00", "action": "off"},
    {"label": "Evening", "from": "20:00", "to": "23:00", "action": "dim", "brightness": 20},
    {"label": "Mornings", "days": [0, 1, 2, 3, 4], "from": "06:30", "to": "09:00",
     "action": "playlist", "rotation": ["clock", "weather", "calendar"]}
  ]
}
```

Schedule rules turn the board off, cap its brightness or swap in a playlist at set
times. `days` are 0 (Monday) to 6 (Sunday), counted on the day a window starts, so
23:00-07:00 on Friday runs into Saturday morning. Pressing Power during quiet hours
turns the board on until they end.

## API

LAN only. No authentication unless you set a token (Settings, Access); then every
change needs `X-PixelPane-Token: <token>` or `Authorization: Bearer <token>`. The
board only answers to its IPs and its own host names; add others under Settings,
Allowed host names. See [SECURITY.md](SECURITY.md).

| Call | Body | Does |
|------|------|------|
| `GET /api/health` | | power, scene, themes, temperature, throttle flags, version |
| `GET /api/state` | | the above plus plugins, scenes, icons, data ages |
| `POST /api/state` | `{"power": true, "brightness": 40}` | on/off, brightness 1-100 |
| `POST /api/notify` | `{"text": "Doorbell", "icon": "bell", "color": "#ffcc00", "flash": true, "seconds": 10, "style": "banner"}` | a message that jumps the queue; anything left out comes from the alerts settings |
| `POST /api/pin`, `DELETE /api/pin` | `{"scene": "on_air", "minutes": 30}` | hold a scene, or clear it |
| `POST /api/skip` | | end the current scene (never a notification) |
| `POST /api/play` | `{"scene": "halloween"}` or `{"scene": "gif:retro"}` | play next |
| `POST /api/data/<key>` | see each plugin | feed a scene |
| `GET/PUT /api/config` | any config key, merged | playlist, timings, plugin settings |
| `GET /api/gifs`, `POST /api/gifs`, `DELETE /api/gifs/<id>` | multipart `file`, `theme` | the GIF library |
| `PATCH /api/gifs/<id>`, `POST /api/gifs/classify` | `{"category": "arcade", "theme": "all"}`, `{"ids": [...], ...}` or `{"reset": true}` | move GIFs between categories and themes ([docs/GIFS.md](docs/GIFS.md)) |
| `POST /api/gifs/generate`, `GET /api/gifs/generate/<job>` | `{"prompt": "a cat chasing a laser dot"}` or `{"from": "<draft>", "change": "make it bigger"}` | make a draft from a prompt, or rework one; poll the job |
| `GET /api/drafts`, `GET /draft/<id>.gif`, `POST /api/drafts/<id>/save`, `DELETE /api/drafts/<id>` | `{"name": "...", "category": "...", "theme": "all"}` | list, view, save to the library, or discard drafts |
| `GET/PUT /api/sketch`, `POST /api/sketch/save` | `{"width": 32, "height": 32, "ms": 125, "frames": ["<base64 RGB>"], "show": true}`, plus `name`, `category`, `theme` to save | the Draw and Animate pages' drawing: PUT shows it on the board (and holds it there), save puts it in the GIF library |
| `POST /api/categories/rename` | `{"from": "retro", "to": "arcade"}` | rename or merge a category |
| `GET /api/backup`, `POST /api/restore` | a backup file | your settings as a file (secrets stay on the board), and back |
| `GET /api/logs?since=<unix time>` | | recent log lines |
| `POST /api/system/restart` | | restart the service |
| `GET /preview.png?scale=10` | | the current frame |
| `GET /api/frames` | | a stream of every frame as the panel shows it (the page's live preview) |

Icons for `notify` and tiles: bell, mail, alert, check, heart, door, music,
calendar, package, home, lock, washer, thermometer, drop, info, camera, car,
cat, air.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install flask pillow numpy
PIXELPANE_FAKE=1 PIXELPANE_HOME=. PIXELPANE_STATE=/tmp/pixelpane .venv/bin/python -m pixelpane.app --port 8080
.venv/bin/python -m pixelpane.preview sheet /tmp/scenes.png halloween clock homelab   # look at scenes
PYTHON=.venv/bin/python tools/test.sh   # backend unittest + Playwright tests of the page
```

`PIXELPANE_FAKE=1` runs everything without a panel. Tests are plain `unittest`
for the backend (they also run on the Pi) and Playwright for the page, which
clicks every button against the real server. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Layout

```
pixelpane/            the controller: app (player), web (API + page), state, display, kit (scene toolkit)
pixelpane/plugins/    the built-in plugins
pixelpane/fonts/      BDF fonts (public domain, tom-thumb MIT)
install.sh           idempotent installer and hardening, runs on the Pi
tools/               deploy.sh, ingest-gif.sh, test.sh
hardware/            led-grid.scad, the parametric 3D-printed light grid
docs/                hardware, configuration, plugins, Home Assistant, GIFs
tests/               backend tests and tests/frontend (Playwright)
```

## Credits

- [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) (GPL-2.0), the LED driver for Pi 2-4, built by the installer.
- [Adafruit PioMatter](https://github.com/adafruit/Adafruit_Blinka_Raspberry_Pi5_Piomatter), the Pi 5 driver.
- [Silkscreen](https://github.com/googlefonts/silkscreen) by Jason Kottke for the web page (SIL OFL 1.1).
- [Inter](https://github.com/rsms/inter) and [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) for the web page (SIL OFL 1.1). The page's look follows [joekarlsson.com](https://www.joekarlsson.com).
- Fonts from the X11 misc-fixed set (public domain) and [tom-thumb](https://robey.lag.net/2010/01/23/tiny-monospace-font.html) by Robey Pointer (MIT).

## Name

PixelPane started life in 2020 as *Graffiti Board*, a live collaborative drawing
wall. It grew into a wall display, and the name grew with it.

## License

MIT. See [LICENSE](LICENSE).
