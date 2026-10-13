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
#   PIXELPANE_DEPLOY_NOPASSWD=0                 (optional: always ask for the sudo password)
# install.sh lets the deploying user rerun it without a password, so only the first
# deploy (or one after PIXELPANE_DEPLOY_NOPASSWD changes) asks for it.
# PIXELPANE_LIBRARY (default ../pixelpane-library) may hold gifs/, plugins/ and
# deploy.env; its gifs/ replaces this repo's (empty) gifs/ folder on the Pi and its
# plugins/*.py become the board's plugins (in /etc/pixelpane/plugins).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIBRARY="${PIXELPANE_LIBRARY:-$REPO/../pixelpane-library}"
# shellcheck source=/dev/null
[ -f "$LIBRARY/deploy.env" ] && . "$LIBRARY/deploy.env"
HOST="${PIXELPANE_HOST:?set PIXELPANE_HOST (user@pi) or put it in $LIBRARY/deploy.env}"
SSH=(ssh); [ -n "${PIXELPANE_KEY:-}" ] && SSH+=(-i "${PIXELPANE_KEY/#\~/$HOME}")
STAGE=pixelpane-deploy   # in the deploying user's home on the Pi (only it can write there)
VERSION="$(git -C "$REPO" describe --always --dirty)"

COPYFILE_DISABLE=1 tar --no-xattrs -C "$REPO" --exclude .git --exclude '*.nmconnection' \
    --exclude __pycache__ --exclude node_modules --exclude test-results -czf - . \
  | "${SSH[@]}" "$HOST" "rm -rf /tmp/pixelpane $STAGE 2>/dev/null; mkdir -p $STAGE && tar -xzf - -C $STAGE && echo $VERSION > $STAGE/VERSION"
if [ -d "$LIBRARY/gifs" ]; then
  echo "GIF library: $LIBRARY/gifs"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$LIBRARY" -czf - gifs | "${SSH[@]}" "$HOST" "tar -xzf - -C $STAGE"
fi
if [ -d "$LIBRARY/plugins" ]; then
  echo "plugins: $LIBRARY/plugins"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$LIBRARY" --exclude __pycache__ -czf - plugins | "${SSH[@]}" "$HOST" "tar -xzf - -C $STAGE"
fi
printf 'PIXELPANE_TZ=%q\nPIXELPANE_WIFI_COUNTRY=%q\nPIXELPANE_HOSTNAME=%q\nPIXELPANE_DEPLOY_NOPASSWD=%q\n' \
    "${PIXELPANE_TZ:-}" "${PIXELPANE_WIFI_COUNTRY:-}" "${PIXELPANE_HOSTNAME:-}" "${PIXELPANE_DEPLOY_NOPASSWD:-1}" \
  | "${SSH[@]}" "$HOST" "cat > $STAGE/deploy.env"
# The exact command the sudoers rule from install.sh allows ($HOME expands on the Pi).
RUN="/usr/bin/bash \"\$HOME/$STAGE/install.sh\""
# Look for the rule itself: "sudo -l <command>" also says yes to commands that need a password.
if "${SSH[@]}" "$HOST" "sudo -n -l 2>/dev/null | grep -qF \"NOPASSWD: /usr/bin/bash \$HOME/$STAGE/install.sh\""; then
  "${SSH[@]}" "$HOST" "sudo -n $RUN"
elif [ -t 0 ]; then
  "${SSH[@]}" -t "$HOST" "sudo $RUN"   # first deploy: asks for the password once
else
  echo "sudo needs a password on the Pi this once; run tools/deploy.sh from a terminal" >&2
  exit 1
fi
