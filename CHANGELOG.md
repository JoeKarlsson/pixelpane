# Changelog

All notable changes to PixelPane. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
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
- In select mode, click GIFs to pick or unpick them, shift-click for a range,
  and clear the selection; "Select page" becomes "Unselect page".
- The homelab dashboard skips its Plex page while nobody is streaming.

### Fixed
- File responses (GIFs, the preview, static files) sent two `Date` headers,
  which reverse proxies log as an error on every request.
- The control page polls half as often and stops polling in a background tab.
- GIFs that are not square keep their whole subject instead of being cropped.

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
