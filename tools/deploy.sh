#!/bin/bash
# Push this repo (plus your private GIF library and settings) to the Pi and run
# install.sh there. Run from your computer.
#
#   tools/deploy.sh
#
# Settings come from the environment or from $PIXELPANE_LIBRARY/deploy.env:
#   PIXELPANE_HOST=pi@pixelpane.local     (required)
#   PIXELPANE_KEY=~/.ssh/id_ed25519             (optional ssh key)
#   PIXELPANE_TZ=America/Chicago                (optional, passed to install.sh)
#   PIXELPANE_WIFI_COUNTRY=US                   (optional, passed to install.sh)
#   PIXELPANE_HOSTNAME=pixelpane                (optional, passed to install.sh)
# PIXELPANE_LIBRARY (default ../pixelpane-library) may hold gifs/ and
# deploy.env; its gifs/ replaces this repo's (empty) gifs/ folder on the Pi.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIBRARY="${PIXELPANE_LIBRARY:-$REPO/../pixelpane-library}"
# shellcheck source=/dev/null
[ -f "$LIBRARY/deploy.env" ] && . "$LIBRARY/deploy.env"
HOST="${PIXELPANE_HOST:?set PIXELPANE_HOST (user@pi) or put it in $LIBRARY/deploy.env}"
SSH=(ssh); [ -n "${PIXELPANE_KEY:-}" ] && SSH+=(-i "${PIXELPANE_KEY/#\~/$HOME}")
STAGE=/tmp/pixelpane
VERSION="$(git -C "$REPO" describe --always --dirty)"

COPYFILE_DISABLE=1 tar --no-xattrs -C "$REPO" --exclude .git --exclude '*.nmconnection' \
    --exclude __pycache__ --exclude node_modules --exclude test-results -czf - . \
  | "${SSH[@]}" "$HOST" "rm -rf $STAGE && mkdir -p $STAGE && tar -xzf - -C $STAGE && echo $VERSION > $STAGE/VERSION"
if [ -d "$LIBRARY/gifs" ]; then
  echo "GIF library: $LIBRARY/gifs"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$LIBRARY" -czf - gifs | "${SSH[@]}" "$HOST" "tar -xzf - -C $STAGE"
fi
printf 'PIXELPANE_TZ=%q\nPIXELPANE_WIFI_COUNTRY=%q\nPIXELPANE_HOSTNAME=%q\n' \
    "${PIXELPANE_TZ:-}" "${PIXELPANE_WIFI_COUNTRY:-}" "${PIXELPANE_HOSTNAME:-}" \
  | "${SSH[@]}" "$HOST" "cat > $STAGE/deploy.env"
"${SSH[@]}" -t "$HOST" "sudo bash $STAGE/install.sh"
