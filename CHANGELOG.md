# Changelog

All notable changes to PixelPane. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Security
- GIF ids could name any file on the Pi (`upload//etc/passwd`): the GIF file route
  served it and DELETE removed it. Ids are now resolved and must stay inside the
  library.
- Changing the generator's server URL clears its saved API key, so the key can't be
  sent to a server someone else picked.
- The board only answers to its IPs, its own host names and names you allow
  (`allowed_hosts`), which blocks DNS rebinding.
- Scenes accept only the params they declare (`/api/play` could pass a file path to
  the GIF scene).
- Album art hosts must match by scheme, host and port, and redirects aren't followed.
- A Content Security Policy, no framing and no MIME sniffing on every page.
- Only one GIF is generated at a time, and at most six live previews stream at once.
- Your plugins now live in root-owned `/etc/pixelpane/plugins` (moved there from
  `/var/lib/pixelpane/plugins` by the installer), so the service can't write code
  it would run. The systemd unit is sandboxed further, and the Pi 5 driver is pinned.
- With a token set, logs and backups need it too.

### Added
- An aquatic plugin: a fish tank that lives. Fish hatch from eggs, grow from fry to
  adults, lay eggs and grow old over about a week, even while the tank isn't on screen.
  When a CO2, temperature or air quality tile goes bad they turn pale, slow down and
  stop laying, and the water clouds over.
- The fish tank comes alive: babies sometimes hatch striped, two-tone, gold or albino and
  pass it on (the board announces them); the tank earns a starfish, a castle, a treasure
  chest and a snail; it dims and the fish rest at night (sunrise and sunset from the
  weather plugin's location); it feeds itself at feeding times you set; and Home
  Assistant can bring the fish to the glass to greet you (`greet`) or tap it to scatter
  them (`tap`). The generative aquarium now shows your tank instead of strangers.
- Plugins can keep state across restarts with `ctx.saved(name)` and `ctx.save(name)`.
- Ten more transitions: iris, zoom, pixelate, blinds, blocks, diagonal, push up, melt
  (columns drip away), dip to black and TV switch-off. Random picks from all of them
  unless you untick some.
- Random transitions: each scene change picks one of the styles you tick, never the
  same one twice in a row.
- Settings, Notifications: write a message (with a second line, icon, style, color and
  length) and send it now, or keep it on screen until you clear it. Previewing the
  notification look uses the message you're writing.
- Draw and Animate pages. Draw puts what you scribble on the board as you draw it:
  pen, eraser, fill, color picker, brush sizes, mirror, opacity, undo. Animate makes
  frame-by-frame loops: step through frames with the arrows or ← →, add, copy,
  delete and move them, an onion-skin ghost of the frame before, speed and Play.
  It starts from an example (bouncing ball, heartbeat, blinking face, spinner,
  rainbow wave). The board plays your loop as you edit it, or when you press Show on
  board, and both pages save to the GIF library (`/api/sketch`).
- Play now buttons show a little animated preview of their scene, rendered on the
  board from its real data (`GET /api/scenes/<name>/thumb.gif`).
- Every plugin's settings are on the Settings page too: On screen (transitions,
  overlays, status dots), Notifications and Plugins, with a small live preview in the
  corner so you can watch a change land.
- Up to four overlays at once, each with what it shows (time, date, outside
  temperature, a tile reading such as the office temperature or CO2, minutes to the
  next meeting, or your own text), a corner, size, style (outlined, on a dark box or
  plain), color (or colored by the reading), peek or always, and which scenes it's on.
  Auto corners never overlap.
- An `items` field type for plugin settings: a list of small records with Add and
  Remove, each sub-field validated.
- Options for each plugin, on the Settings page under Plugins. Clock: 12 or 24 hours,
  a leading zero, a steady colon, and the date and temperature lines on or off.
  Weather: the background full, subtle or off, white or temperature-colored digits,
  and the high/low and conditions lines on or off. Tiles: the background full, subtle
  or off, and the sparkline, trend arrow and count-up on or off. Calendar: how far
  ahead to look, when the bell starts ringing, the title color. Now playing: how long
  the album art fills the panel, the equalizer, the room, text colors. Homelab: which
  pages show, and the CPU and NAS levels that turn amber and red. Generative: slow,
  normal or fast. Sky: how many stars. The defaults look exactly as before.
- Notification styles: classic, banner (a bar slides down from the top), burst (the
  icon pops in with ripples) and ticker (big text crawls across). The alerts plugin
  sets the default style, seconds, color, flash and a pulsing border; a notification
  can pick its own `style`. Send a test from the Settings page, or pick a style on
  the control page.
- Triggers: reminders (text at a time on the days you pick) and watches (a
  notification when the air quality goes above 150, it starts to snow, a homelab
  alert fires, the next meeting is close, the song changes...), with a cooldown and
  `{value}` / `{label}` in the text. They live on the Settings page under
  Notifications. A reminder goes off once a day, even across a restart.
- Tiles that are readings: send `{kind, value}` for `temp`, `aqi`, `humidity`, `co2`
  or `battery` and the whole panel takes on a mood that shows how it feels (frost,
  heat shimmer, clear or smoggy air, condensation, murky bubbles). The number counts
  up in a color that follows it, with a trend arrow and a sparkline of the last five
  hours. A reading that turns bad jumps the queue (once an hour, can be switched
  off). The comfortable range, units and colors are in the tiles plugin's settings.
- The weather fills the panel: rain slanting in the wind, snow, fog, stars, a glow
  on sunny days, lightning that lights the sky, heat shimmer on hot days and frost
  on bitter ones. The temperature is colored from cold to hot. It takes a `wind`
  field (mph), which the Open-Meteo fallback now fills in.
- `kit.Mood` and friends (`temp_color`, `outlined_text`, `sparkline`, `arrow`) for
  plugins that want the same full-panel moods.
- An effects plugin: scenes blend into each other (fade, wipe, slide or dissolve);
  GIFs, and optionally generative and seasonal scenes, can show the time, date,
  outside temperature or minutes to the next meeting in a corner, all the time or
  for 3 seconds every 20, with auto picking the calmest corner; and status dots,
  up to four lights along the top edge pushed to `POST /api/data/status`.
- `@plugin.frames`: plugins can wrap every scene's frames (docs/PLUGINS.md).
- Ten new generative scenes: a lava lamp, rain ripples on a pond, reaction-diffusion
  (coral, spots and worms), falling sand, an aurora, fireflies, an aquarium, a snake
  that plays itself, an hourglass that drains toward your next meeting, and smog.
- An `ambient` playlist slot that picks generative art to suit outside: ripples when
  it rains, fire when it's hot, an aurora or fireflies on a clear night, and smog
  when an air quality tile (`kind: "aqi"`) is over 150. Otherwise it keeps to the
  scenes you ticked.
- A `color` field type for plugin settings forms, and a table of every field type
  in docs/PLUGINS.md.
- Your own holidays (Settings, Holidays): a name and date ranges, every year
  (`11-08 to 11-12`) or one year only (`2027-02-06 to 2027-02-10`), with their own
  GIF folder. Built-in holidays can be switched off, and the seasons flipped for the
  southern hemisphere (`themes` in the config).
- Appearance (Settings, Appearance): dark, light or match the device, and an accent
  color; text on the accent turns dark or light to stay readable (`ui` in the config).
- The clock's digits can be one color you pick instead of following the time of
  day (dimmed at night).
- Drag and drop to reorder the playlist.
- docs/CONFIG.md, a reference for every config key.
- A Settings page: a schedule (quiet hours, dimming and time-of-day playlists, by
  day of the week), seconds per scene and data freshness, display hardware, access
  (token and allowed host names), backup and restore, and system status with
  power and heat warnings, plugin problems, a restart button and recent logs.
- Plugins declare what they need instead of the core knowing them: whether a scene
  can be pinned, its params and its "nothing to show" text, and pickers for slots
  like seasonal and generative. Plugins have a version and an API version, can ship
  as pip packages (a `pixelpane.plugins` entry point), are refused if their name is
  taken, and show load errors on the page. Background tasks stop when their plugin
  is off and restart after a crash.
- `pixelpane.testing.render()` to test a plugin's scene without a board.
- `tools/deploy.sh` deploys `plugins/` from your library folder.
- The clock has animated faces, picked at random from the ones you tick:
  classic, frame (a rainbow border with a comet that laps it once a minute),
  arcade (a little hero runs under the time, hopping slimes and grabbing coins)
  and sky (the real sky for the hour, with the sun or moon crossing it). Frame
  and arcade switch to classic at night.
- More places to find GIFs in docs/GIFS.md: specific CC0 game-sprite packs,
  pixel-art galleries, hearts and level-up effects, and LED-panel art.
- Sky plugin, calculated on the board with no network: a `moon` scene that
  draws tonight's moon with its real shape, the phase and the days to the next
  full moon, and names each full moon (Harvest, Hunter's, Wolf and the rest),
  calling out supermoons and blue moons; a `zodiac` scene with the sun sign's
  symbol, dates and element, and the sign the moon is in.
- Move GIFs to another category or theme from the control page (one at a time,
  or select several or a whole page), rename or merge categories, and undo a
  move; also through the API. Moves are saved on the board, so deploys keep them.
- The live preview plays at the panel's real speed: the board streams each frame
  to the page (`/api/frames`) instead of the page fetching a snapshot a second.
- Make a GIF: describe an idea (or press Surprise me) and a chat model designs a
  looping animation the board renders. Each result is a draft to preview (also on
  the panel), refine ("make the cat bigger"), try again, save with your own name,
  category and theme, or discard; recent drafts stay on the board. Works with
  OpenAI-compatible servers (LiteLLM, OpenRouter, OpenAI, Ollama) and Anthropic's
  API. The model can check a picture of its own render and fix what it sees.
- Library: sort by recently added (the default), oldest, name, category, season
  and theme, most, least or recently played; search by name; a Mine filter for
  your uploads and saved GIFs, a Hidden filter, and three thumbnail sizes.

### Changed
- Draw and Animate have one board button beside the preview: Show on board puts
  your drawing on the board and turns into Stop showing, which takes it off. The
  separate Show on board button under the frames is gone.
- During a transition the new scene keeps playing (a GIF animates through it)
  instead of freezing on its first frame, and it keeps its full length.
- A plugin's card on the control page now opens its section on the Settings page,
  which has its options, Play now buttons, the data it has received and its on/off
  switch. The control page's plugin dialog is gone; old `/#plugin=<name>` links
  still land in the right place.
- Make a GIF and the GIF library moved to their own page, `/library` (GIFs in the
  header). The control page keeps the live controls, playlist and plugins.
- Play now is grouped: scenes, art, then holidays and GIF categories folded away.
- The footer is just the GitHub link and the maker's credit.
- Deleting a GIF takes a second click to confirm.
- The playlist editor marks unsaved changes, and the browser warns before you
  leave the page with some.
- A failed action on the control page shows the board's error in a toast instead
  of doing nothing.
- Symbol-only buttons (↑, ↓, ✕, ▶, ✎, 🗑) have names for screen readers, plugin
  cards open with the keyboard, and keyboard focus is visible on every control.
- The hardware guide recommends a separate supply for the Pi, as Adafruit does: on
  the HAT's supply alone the Pi sees under-voltage when the panel draws hard.
- Seconds per scene moved from the control page to Settings.
- Settings without a form field must keep their default's type.
- In select mode, click GIFs to pick or unpick them, shift-click for a range,
  and clear the selection; "Select page" becomes "Unselect page".
- The homelab dashboard skips its Plex page while nobody is streaming.

### Fixed
- File responses (GIFs, the preview, static files) sent two `Date` headers,
  which reverse proxies log as an error on every request.
- The control page polls half as often and stops polling in a background tab.
- GIFs that are not square keep their whole subject instead of being cropped.
- Switching a plugin off or on in Settings no longer folds its section shut.

## [0.1.0] - 2026-10-12

First public release.

### Added
- Scene player for a 32x32 HUB75 panel: GIFs mixed with live, animated scenes
  (clock, weather, now playing with album art, calendar countdown, a six-page
  homelab dashboard, info tiles), 12 seasonal and holiday scenes and 5
  generative ones.
- Plugin system: every scene comes from a plugin; plugins can be switched off,
  configured, and added as single Python files.
- Control page: live preview, now-playing view with playlist position and
  Skip, Play now, modes (ON AIR, messages), notifications, playlist editor,
  plugin panels (what each plugin does, its scenes, data and editable
  settings) and a paged GIF library with upload, categories and themes.
- Cross-site writes to the API are refused (same-origin check).
- HTTP API for notifications, modes, data and configuration; Home Assistant
  examples (light, feed automation, notification steps).
- Raspberry Pi 2-4 support through hzeller/rpi-rgb-led-matrix and Pi 5 support
  through Adafruit PioMatter (untested on hardware).
- Idempotent installer with hardening (unprivileged service, key-only SSH,
  unattended upgrades, logs in RAM), deploy script and a GIF ingest tool.
- Build guide with parts list, diagrams and a parametric 3D-printed light grid.
- Backend unittest suite and Playwright tests of the control page.

[0.1.0]: https://github.com/JoeKarlsson/pixelpane/releases/tag/v0.1.0
