# Configuration reference

Everything the board remembers lives in one file on the Pi,
`/var/lib/pixelpane/config.json`. You rarely edit it by hand: the control page,
the GIFs page and **Settings** write it for you, and `PUT /api/config` takes any of
the keys below (merged, so you send only what changes). Every change is checked
first; a bad value comes back as a `400` with the reason and nothing is saved.

Defaults are in [`pixelpane/default_config.json`](../pixelpane/default_config.json).

```bash
curl -X PUT http://pixelpane.local/api/config -H 'Content-Type: application/json' \
  -d '{"brightness": 40, "ui": {"theme": "light"}}'
```

## Playback

| Key | Default | What it does |
|-----|---------|--------------|
| `brightness` | `60` | 1 to 100. The board's brightness at start-up; the slider changes it live |
| `rotation` | clock, gif, seasonal, ... | The playlist: scene names, `gif`, `gif:<category>`, `seasonal`, `generative` or `ambient`. Unknown names are refused |
| `dwell` | per scene | Seconds each scene stays on, `{"clock": 10, "gif": 20}`. A scene not listed gets 15 |
| `data_ttl_minutes` | `{}` | How long pushed data stays fresh, per key, `{"weather": 90}`. Empty uses the plugin's own (see [Plugins](#plugins)) |
| `schedule` | `[]` | Quiet hours, dimming and time-of-day playlists. See [Schedule](#schedule) |

## Schedule

A list of up to 30 rules:

```json
{"label": "Quiet hours", "days": [0, 1, 2, 3, 4, 5, 6], "from": "23:00", "to": "07:00", "action": "off"}
```

| Key | Meaning |
|-----|---------|
| `label` | A name, up to 40 characters (optional) |
| `days` | 0 (Monday) to 6 (Sunday), counted on the day the window starts. Default: every day |
| `from`, `to` | `HH:MM`. A window past midnight belongs to the day it starts |
| `action` | `off`, `dim` (needs `brightness`, 1 to 100) or `playlist` (needs `rotation`, a list of scenes) |
| `enabled` | `false` keeps the rule without running it |

Pressing Power during quiet hours turns the board on until they end.

## Holidays and seasons

```json
"themes": {
  "hemisphere": "north",
  "off": ["july4", "thanksgiving"],
  "custom": [
    {"key": "diwali", "name": "Diwali", "dates": [["2026-11-08", "2026-11-12"], ["2027-10-28", "2027-11-01"]]},
    {"key": "anniversary", "name": "Our anniversary", "dates": [["06-14", "06-14"]]}
  ]
}
```

| Key | Default | What it does |
|-----|---------|--------------|
| `hemisphere` | `north` | `south` moves the seasons six months, so winter is June to August |
| `off` | `[]` | Built-in holidays to skip: `new_year`, `valentines`, `st_patricks`, `july4`, `halloween`, `thanksgiving`, `christmas`. Seasons always run; the birthday is set in the seasonal plugin |
| `custom` | `[]` | Your own holidays, up to 50 |

Each custom holiday has a `name` (up to 40 characters), a `key` (letters, digits
and `_`; made from the name if you leave it out) and `dates`: a list of
`[from, to]` ranges, inclusive. `MM-DD` dates repeat every year (and may wrap the
new year, `["12-30", "01-02"]`); `YYYY-MM-DD` dates are for that year only, which
is how you add holidays that move, like Diwali or Lunar New Year.

A custom holiday has no animated scene of its own. While it's on, its GIFs play:
upload them to it on the GIFs page, move GIFs into it with ✎, or put files in
`gifs/themes/<key>/` in your library folder.

## Appearance

```json
"ui": {"theme": "dark", "accent": "#fdae84"}
```

| Key | Default | What it does |
|-----|---------|--------------|
| `theme` | `dark` | `dark`, `light`, or `auto` to follow each device's setting |
| `accent` | `#fdae84` | The color of buttons, links and highlights, as `#rrggbb`. Text on it turns dark or light to stay readable |

## Plugins

`plugins.<name>` holds each plugin's settings, merged over its defaults.
`"enabled": false` turns a plugin off (its scenes leave the playlist and Play now,
and its data keys are refused). Secret settings come back from the API as
`••••••••`; sending that back keeps the saved value.

| Plugin | Settings | Takes data (fresh for) |
|--------|----------|------------------------|
| clock | `faces` (any of classic, frame, arcade, sky), `color_mode` (`day` follows the time of day, `fixed` uses `color`), `color` (`#rrggbb`, dimmed at night), `hours` (`"12"` or `"24"`, also used by the calendar), `leading_zero`, `blink` (the colon), `show_date`, `show_temp` | |
| weather | `latitude`, `longitude` (for the Open-Meteo fallback when nothing is pushed), `mood` (the background: `full`, `subtle` or `off`), `temp_colors` (cold-to-hot digits, else white), `show_high_low`, `show_line` (conditions, rain chance, wind) | `weather` (180 min) |
| now_playing | `art_hosts`: base URLs album art may be fetched from; `art_seconds` (full-screen cover first, 0 for none), `equalizer`, `show_room`, `title_color`, `artist_color` | `now_playing` (360 min) |
| calendar | `lookahead_hours` (show events starting within, default 12), `bell_minutes` (bell and red countdown, default 10), `title_color` | `next_event` (720 min) |
| homelab | `pages` (any of hosts, nas, net, ups, plex; alerts and status always show), `cpu_warn`, `cpu_crit`, `disk_warn`, `disk_crit` (%, amber and red) | `homelab` (60 min) |
| tiles | `temp_unit` (`F` or `C`), `comfy_low` and `comfy_high` (the comfortable range, `null` for 68 to 76F / 20 to 24C), `humidity_low`, `humidity_high` (%), `co2_high` (ppm), `cold_color`, `comfy_color`, `hot_color` (`#rrggbb`), `alert` (a reading that turns bad jumps the queue), `moods` (`full`, `subtle` or `off`), `sparkline`, `trend`, `count_up` | `tiles` (240 min) |
| gifs | `theme_share`: 0 to 1, how often a GIF slot picks from an active theme | |
| seasonal | `holiday_share`: 0 to 1, how often a holiday wins over the season; `birthday`: `{"month", "day", "name"}` or `null` | |
| generative | `scenes`: which of fire, plasma, life, matrix_rain, starfield, lava, ripples, reaction, sand, aurora, fireflies, aquarium, snake, hourglass and smog the `generative` and `ambient` slots pick from; `speed` (`slow`, `normal`, `fast`) | |
| generator | `provider` (`openai` or `anthropic`), `base_url`, `model`, `api_key` (secret), `review` | |
| effects | `transition` (`none`, `fade`, `wipe`, `slide`, `dissolve`), `transition_seconds` (0.2 to 1.5), `status_dots` (`true`/`false`), `overlays`: up to four of `{show, reading, label, text, corner, mode, size, style, color, color_by_value, on}`. `show` is `time`, `date`, `time_date`, `temp` (outside), `reading` (a tile reading: `reading` is its kind, `label` picks one tile), `meeting` or `text` (your own, up to 8 characters); `corner` is `auto` or `top_left`, `top_right`, `bottom_left`, `bottom_right`; `mode` `always` or `peek` (3 seconds every 20); `size` `small` or `large`; `style` `outline`, `box` or `plain`; `on` any of gif, generative, seasonal. Until `overlays` is saved, the older single `overlay`, `overlay_corner`, `overlay_mode`, `overlay_on` and `overlay_color` still work | `status` (120 min) |
| sky | `stars` (`none`, `few`, `some`, `lots`) | |
| alerts | | |

What each data key expects is in [HOME_ASSISTANT.md](HOME_ASSISTANT.md). Your own
plugins add their own settings; see [PLUGINS.md](PLUGINS.md).

## GIF library

The page and the API keep these; you don't usually write them yourself.

| Key | What it holds |
|-----|---------------|
| `hidden_gifs` | GIF ids that never play (the library's hide button) |
| `gif_meta` | Per-GIF overrides, `{"repo/retro-mario.gif": {"category": "arcade", "theme": "halloween"}}`, from ✎ and bulk moves. They survive deploys that rewrite `gifs/` |

## Access

| Key | Default | What it does |
|-----|---------|--------------|
| `api_token` | `null` | With a token (8 characters or more), every change, the logs and backups need `X-PixelPane-Token: <token>` or `Authorization: Bearer <token>`. `null` turns it off |
| `allowed_hosts` | `[]` | Extra host names the board answers to, like a reverse proxy's. It always answers to its IPs and its own names. This blocks DNS rebinding |

## Display hardware

These take effect after a restart (Settings, Display, Save and restart).

| Key | Default | What it does |
|-----|---------|--------------|
| `display` | `auto` | The driver: `auto` picks for the Pi, or `hzeller` (Pi 2 to 4), `piomatter` (Pi 5), `fake` (no panel) |
| `adafruit_board` | `hat` | `hat` or `bonnet` |
| `hardware_mapping` | `adafruit-hat` | rpi-rgb-led-matrix `--led-gpio-mapping`; `adafruit-hat-pwm` after the PWM mod |
| `panel` | `{"cols": 32, "rows": 32}` | Panel size in LEDs: 16, 32, 64 or 128 each way |
| `panel_bgr` | `false` | For panels wired blue-green-red (Pi 5 driver) |
| `gpio_slowdown` | `null` | 0 to 5. Raise it if a Pi 4 flickers; `null` lets the driver pick |
| `refresh_hz` | `null` | 30 to 2000, a cap on the panel refresh rate; `null` runs as fast as it goes |

## Backup and restore

`GET /api/backup` downloads everything above except secrets (the token and secret
plugin settings), and `POST /api/restore` puts it back, keeping the secrets already
on the board. Both are on Settings, Backup.
