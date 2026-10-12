#!/bin/bash
# Convert any GIF (or PNG/WebP) into a 32x32 GIF for the panel and drop it in gifs/.
#   tools/ingest-gif.sh [--smooth] [--name NAME] input...
# Default scaling is nearest-neighbour, which keeps pixel art crisp when the
# source is an upscaled 32x32 or 64x64 sprite. Use --smooth for photos and
# anything that was not drawn on a pixel grid. Non-square inputs are
# center-cropped. Needs GraphicsMagick (gm) or ImageMagick (magick).
set -euo pipefail

SIZE=32
FILTER=Point
NAME=""
OUT="$(cd "$(dirname "$0")/.." && pwd)/gifs"

while [ $# -gt 0 ]; do
  case "$1" in
    --smooth) FILTER=Lanczos; shift ;;
    --name) NAME="$2"; shift 2 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) break ;;
  esac
done
[ $# -gt 0 ] || { sed -n '2,8p' "$0"; exit 1; }

if command -v gm >/dev/null; then IM=(gm convert)
elif command -v magick >/dev/null; then IM=(magick)
else echo "install GraphicsMagick or ImageMagick (brew install graphicsmagick)"; exit 1; fi

for src in "$@"; do
  base="${NAME:-$(basename "${src%.*}")}"
  base="$(printf '%s' "$base" | tr -cs 'A-Za-z0-9_-' '-' | sed 's/-*$//' | tr 'A-Z' 'a-z')"
  dest="$OUT/$base.gif"
  "${IM[@]}" "$src" -coalesce -filter "$FILTER" -resize "${SIZE}x${SIZE}^" \
    -gravity center -extent "${SIZE}x${SIZE}" +repage -loop 0 "$dest"
  echo "$dest"
done
