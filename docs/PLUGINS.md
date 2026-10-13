# Writing a plugin

Every scene on the board comes from a plugin. A plugin is one Python file: it
creates a `Plugin`, registers scenes on it, and can declare the data it accepts,
default settings and background tasks. The built-in plugins in
[`pixelpane/plugins/`](../pixelpane/plugins) are good examples; `tiles.py` and
`calendar.py` are the shortest.

## A complete example

Save this as `plugins/countdown.py` in your library folder
(`../pixelpane-library`, next to `gifs/`) and run `tools/deploy.sh`. The deploy puts
it in `/etc/pixelpane/plugins/` on the Pi and restarts the service. That folder
belongs to root and is read-only to the service, so the board can't be tricked into
writing code that it would then run. Keeping your plugins in the library folder also
keeps them in version control.

```python
"""Countdown: days until a date, with a little rocket that climbs as it gets closer."""
from datetime import date

from pixelpane import gfx
from pixelpane.kit import animated_icon, gauge, scroll_text, ticks
from pixelpane.plugin import Plugin

plugin = Plugin(
    "countdown",
    "Days until a date",
    data={"countdown": 24 * 60},            # POST /api/data/countdown, fresh for a day
    defaults={"label": "VACATION", "date": None, "color": "#ff5fa2"},
)


@plugin.scene("countdown")
def countdown(ctx, secs):
    settings = ctx.settings("countdown")
    pushed = ctx.data("countdown") or {}     # pushed data wins over settings
    when = pushed.get("date") or settings["date"]
    if not when:
        return                               # nothing to show: the player skips us
    days = (date.fromisoformat(when) - ctx.now().date()).days
    if days < 0:
        return
    color = gfx.hex_color(pushed.get("color") or settings["color"])
    label = str(pushed.get("label") or settings["label"]).upper()
    for i, t in ticks(secs, 10):             # 10 frames a second for `secs` seconds
        img = gfx.blank()
        animated_icon(img, "calendar", (12, 1), t)
        gfx.text_center(img, 11, f"{days}D", color, "6x10")
        scroll_text(img, 22, label, (200, 200, 220), "tom-thumb", t)
        gauge(img, 29, 1 - min(days, 100) / 100, t, color)
        yield img, 0.1
```

Then add it to the playlist (`"rotation": [..., "countdown"]`) or press its
button on the control page, and configure it:

```bash
curl -X PUT http://pixelpane.local/api/config -H 'Content-Type: application/json' \
  -d '{"plugins": {"countdown": {"date": "2027-04-13", "label": "BIRTHDAY"}}}'
```

## The contract

**A scene** is a generator `scene(ctx, secs, **params)` that yields
`(image, seconds_to_hold)` pairs: a 32x32 RGB Pillow image and how long to show
it. Yield until `secs` is used up (`ticks(secs, fps)` does the bookkeeping). If
there is nothing to show, return without yielding and the player moves on.
Scenes must not block or sleep; the player does the timing.

**`Plugin(name, description, data=None, defaults=None, about="", fields=None, version="", api=1)`**

| Argument | Meaning |
|----------|---------|
| `data` | `{key: minutes}`: keys accepted at `POST /api/data/<key>`, and how long each stays fresh. Keys of disabled plugins are refused |
| `defaults` | your settings; users override them under `config["plugins"][name]`. `enabled` is added for you. A setting without a form field must keep its default's type (number, text, list...) |
| `about`, `fields` | a paragraph and a settings form for the control page (see [Settings forms](#settings-forms)) |
| `version` | your plugin's own version, shown on the control page |
| `api` | the plugin API you wrote it for (`pixelpane.plugin.API_VERSION`, now 1). A board with an older API refuses the plugin with a clear message instead of failing later |

Names are unique: a plugin or scene whose name is taken (`clock`, say) is refused,
not silently swapped in. Load errors show on the control page and in Settings, System.

| Method | Use |
|--------|-----|
| `@plugin.scene(name, kind="widget", pinnable=None, params=None, empty_text=None)` | register a scene. Kinds: `widget`, `gif`, `generative`, `seasonal`, `interrupt`, `mode`. `pinnable`: may `POST /api/pin` hold it (default yes for widget, generative, seasonal and mode). `params`: what `/api/play` and `/api/pin` may pass it, e.g. `{"text": "text", "color": "color"}` (types `text`, `color`, `number`, `bool`); anything else is refused. `empty_text`: shown when someone asks for the scene and it has nothing to show |
| `@plugin.picker(name)` | a playlist entry that picks one of your scenes each time it comes up: `fn(ctx)` returns a scene name (or `None` to skip). `seasonal` and `generative` work this way |
| `@plugin.frames` | a frame wrapper `fn(ctx, frames, info)` run around every scene while your plugin is on: it gets the scene's `(image, seconds)` pairs and yields its own. `info` is `{"scene", "kind", "prev"}`, where `prev` is the last frame of the scene before (or `None`). Images can be shared (GIF frames are cached), so draw on a copy. The effects plugin uses this for transitions, overlays and status dots |
| `@plugin.task` | a background function `fn(ctx, stop)` (fetch an API, poll a sensor). Loop with `while not stop.wait(seconds):`. It runs while the plugin is on: `stop` is set when it's turned off, and it starts again when it's turned back on. If it raises, the error is logged and shown on the page, and it is restarted after a growing pause |

**`ctx`**, what a scene or task can use:

| | |
|-|-|
| `ctx.data(key)` | the latest pushed data for `key`, or `None` if missing or stale |
| `ctx.settings(name)` | a plugin's settings (defaults plus config) |
| `ctx.now()` | the current local time (use it instead of `datetime.now()` so tests can freeze time) |
| `ctx.rng` | a `random.Random` |
| `ctx.store(name)` | a dict for caches that should live as long as the process |
| `ctx.state.put_data(key, value)` | for tasks that fetch their own data |

**The toolkit** (`pixelpane.kit` and `pixelpane.gfx`):

| | |
|-|-|
| `gfx.blank(color)`, `gfx.text`, `gfx.text_center`, `gfx.text_width` | drawing; fonts `tom-thumb`, `4x6`, `5x7`, `5x8`, `6x10` |
| `gfx.hsv`, `gfx.scale`, `gfx.hex_color` | colors |
| `gfx.sprite(name)`, `gfx.paste(img, name, xy)` | the built-in pixel sprites (add your own to `gfx.SPRITES` as rows of characters) |
| `ticks(secs, fps)` | frame index and elapsed time |
| `scroll_text(img, y, text, color, font, t)` | text that scrolls only if it does not fit |
| `animated_icon(img, name, xy, t, level)` | the animated 8x8 icons (bell rings, washer spins, ...) |
| `gauge(img, y, level, t, color)` | a bar that fills to `level` (0-1) |
| `Particles`, `Fireworks`, `palette` | effects used by the seasonal and generative plugins |
| `Mood(rng, name, amount, color, wind).frame(t)` | a dim, moving full-panel background to draw on: `calm`, `glow`, `frost`, `heat`, `haze`, `bubbles`, `droplets`, `rain`, `snow`, `stars`, `wind`, `fog`; `amount` (0-1) is how strong |
| `outlined_text`, `outlined_center` | text with a dark edge, readable over a mood |
| `temp_color(f)`, `SEVERITY`, `mix(a, b, f)` | a temperature as a color, colors for fine to hazardous, blending |
| `sparkline(img, values, y0, y1)`, `arrow(img, x, y, up, color)` | a little history chart, a trend arrow |

## Settings forms

`fields` turns your `defaults` into a form in the plugin's dialog on the control page.
Each field is a dict with `key` (dotted for nested settings, like `"birthday.month"`),
`label`, `type` and optional `help`. The board validates every save against the field,
so a bad value is refused with a message instead of reaching your scene.

| `type` | Shows | Extra keys | Saved as |
|--------|-------|------------|----------|
| `text` (the default) | a text box | `placeholder` | a string |
| `number` | a number box; empty means "use the default" | `min`, `max`, `step` | a number or `null` |
| `range` | a slider | `min`, `max`, `step` | a number |
| `toggle` | a checkbox | `text` | `true` or `false` |
| `select` | a drop-down | `options`: `[{"label": ..., "value": ...}]` | one of the values |
| `choices` | a checkbox per option | `options`: a list of strings | a list of the ticked ones |
| `list` | a text area, one item per line | `placeholder` | a list of strings |
| `color` | a color picker | | `"#rrggbb"` |
| `monthday` | month, day and name | | `{"month", "day", "name"}` or `null` |
| `secret` | a password box; the API never sends the value back | `placeholder` | a string |

For the countdown example above:

```python
fields=[
    {"key": "label", "label": "Label", "type": "text", "help": "Scrolls under the number"},
    {"key": "date", "label": "Date", "type": "text", "placeholder": "2027-04-13"},
    {"key": "color", "label": "Color", "type": "color"},
]
```

## Shipping a plugin as a package

A plugin can also be a normal Python package with its own version and dependencies.
Declare an entry point and PixelPane loads it after the built-ins:

```toml
# pyproject.toml of your package
[project.entry-points."pixelpane.plugins"]
countdown = "pixelpane_countdown"     # the module that creates the Plugin
```

Install it into the board's venv (`sudo /opt/pixelpane/venv/bin/pip install pixelpane-countdown==1.2.0`)
and restart. The control page shows which package and version each plugin came from.

## Good plugin manners

- **Animate.** Every status scene on this board moves; even a static number
  can have a pulsing icon or a filling gauge.
- **Skip when empty.** Return without yielding when there's nothing to show.
- **Fit 32x32.** `tom-thumb` gives 8 characters per line; use `scroll_text` for
  anything longer.
- **Push, don't poll, when you can.** Let Home Assistant (or a cron job) POST to
  `/api/data/<key>`; use a task only for data the board must fetch itself.
- **Look at it** without a panel: `python -m pixelpane.preview gif /tmp/out.gif countdown 6`
  renders your scene to an animated GIF (point `PIXELPANE_PLUGINS` at your plugins folder).
- **Test it**: `pixelpane.testing.render("countdown", 2, settings={...}, data={...})`
  runs a scene against made-up data and settings and returns its frames, no board needed.
- A plugin that fails to import is logged and skipped; a scene that raises is
  logged and the playlist moves on. Neither takes the board down.
