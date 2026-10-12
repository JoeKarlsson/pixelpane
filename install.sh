#!/bin/bash
# Idempotent installer for PixelPane. Run as root on the Pi from a
# copy of this repo (tools/deploy.sh does that). Safe to re-run: it only
# rebuilds, rewrites or restarts what actually changed.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
PREFIX=/opt/pixelpane
VAR=/var/lib/pixelpane
LIB_URL=https://github.com/hzeller/rpi-rgb-led-matrix.git
LIB_COMMIT=14464b3ad8974665f75a3c82355cf872311fec21   # 2026-10-10, known good
BOOT=/boot/firmware

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

# Optional per-install settings (tools/deploy.sh copies deploy.env in):
#   PIXELPANE_TZ=America/Chicago   PIXELPANE_WIFI_COUNTRY=US
# shellcheck source=/dev/null
[ -f "$REPO/deploy.env" ] && . "$REPO/deploy.env"
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
case "$MODEL" in *"Raspberry Pi 5"*) PI5=1 ;; *) PI5=0 ;; esac
echo "== $MODEL"

changed=0
reboot_needed=0

# install_file <src> <dest> <mode>: copy only if different, flag a change
install_file() {
  if ! cmp -s "$1" "$2"; then
    install -D -m "$3" "$1" "$2"
    echo "updated $2"
    changed=1
  fi
}

# write_file <dest> <mode> <<EOF ... : same, for content generated here
write_file() {
  local tmp; tmp=$(mktemp); cat > "$tmp"
  install_file "$tmp" "$1" "$2"; rm -f "$tmp"
}

echo "== packages"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  git build-essential cmake python3-dev python3-venv python3-flask python3-pil python3-numpy \
  libgraphicsmagick++-dev libwebp-dev graphicsmagick unattended-upgrades >/dev/null

# One-time move from the project's old name (Graffiti Board, 2026): keep settings,
# uploads and the already-built LED driver; drop the old service, files and user.
if [ -d /opt/graffiti ] || [ -f /etc/systemd/system/graffiti.service ]; then
  echo "== migrating from graffiti"
  systemctl disable --now -q graffiti.service 2>/dev/null || true
  rm -f /etc/systemd/system/graffiti.service /etc/udev/rules.d/99-graffiti-*.rules \
        /etc/ssh/sshd_config.d/10-graffiti.conf /etc/systemd/journald.conf.d/10-graffiti.conf \
        /etc/apt/apt.conf.d/52graffiti-upgrades
  if [ -d /var/lib/graffiti ] && [ ! -d "$VAR" ]; then mv /var/lib/graffiti "$VAR"; fi
  mkdir -p "$PREFIX"
  if [ -d /opt/graffiti/rpi-rgb-led-matrix ] && [ ! -d "$PREFIX/rpi-rgb-led-matrix" ]; then
    mv /opt/graffiti/rpi-rgb-led-matrix "$PREFIX/"
  fi
  rm -rf /opt/graffiti   # its venv has the old path baked in; a new one is built below
  id graffiti >/dev/null 2>&1 && userdel graffiti 2>/dev/null || true
  changed=1
fi

mkdir -p "$PREFIX"
VENV="$PREFIX/venv"
[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
if [ "$PI5" -eq 1 ]; then
  echo "== Pi 5: Adafruit PioMatter driver"
  "$VENV/bin/python" -c "import adafruit_blinka_raspberry_pi5_piomatter" 2>/dev/null \
    || { "$VENV/bin/pip" install -q Adafruit-Blinka-Raspberry-Pi5-Piomatter; changed=1; }
  write_file /etc/udev/rules.d/99-pixelpane-pio.rules 644 <<'EOF'
SUBSYSTEM=="*-pio", GROUP="gpio", MODE="0660"
EOF
else
echo "== rpi-rgb-led-matrix @ ${LIB_COMMIT:0:7}"
LIB="$PREFIX/rpi-rgb-led-matrix"
[ -d "$LIB/.git" ] || git clone -q "$LIB_URL" "$LIB"
git config --global --add safe.directory "$LIB" 2>/dev/null || true
if [ "$(git -C "$LIB" rev-parse HEAD)" != "$LIB_COMMIT" ] || [ ! -x "$LIB/utils/led-image-viewer" ]; then
  git -C "$LIB" fetch -q origin
  git -C "$LIB" checkout -q "$LIB_COMMIT"
  make -C "$LIB/lib" -j3 >/dev/null
  # led-image-viewer is not used by the service; it stays as a raw hardware test.
  make -C "$LIB/utils" led-image-viewer -j3 >/dev/null
  echo "built led-image-viewer"
fi
# Python bindings in the venv (it can also see Debian's Flask/Pillow/numpy).
if [ "$(cat "$VENV/.rgbmatrix-commit" 2>/dev/null)" != "$LIB_COMMIT" ]; then
  echo "building python bindings (about 4 minutes on a Pi 3)"
  (cd /tmp && "$VENV/bin/pip" install -q "$LIB")
  echo "$LIB_COMMIT" > "$VENV/.rgbmatrix-commit"
  changed=1
fi
fi

echo "== user + state dir"
id pixelpane >/dev/null 2>&1 || useradd --system --home-dir "$VAR" --shell /usr/sbin/nologin pixelpane
usermod -a -G video pixelpane
getent group gpio >/dev/null && usermod -a -G gpio pixelpane
install -d -o pixelpane -g pixelpane -m 755 "$VAR" "$VAR/uploads" "$VAR/cache"
chown -R pixelpane:pixelpane "$VAR"   # also fixes files carried over from an older install
# vcgencmd (undervoltage/throttle flags) needs /dev/vcio; let the video group read it.
write_file /etc/udev/rules.d/99-pixelpane-vcio.rules 644 <<'EOF'
KERNEL=="vcio", GROUP="video", MODE="0660"
EOF
[ "$(stat -c %G /dev/vcio)" = video ] || udevadm trigger --name-match=vcio 2>/dev/null || true

echo "== app + gifs"
# The deployed copy is the source of truth; --delete keeps the Pi in sync with it.
# Web uploads live in /var/lib/pixelpane/uploads and are never touched here.
# A deploy without a GIF library must not wipe the one already on the Pi.
if ! find "$REPO/gifs" -iname '*.gif' -print -quit | grep -q . \
   && find "$PREFIX/gifs" -iname '*.gif' -print -quit 2>/dev/null | grep -q . \
   && [ "${PIXELPANE_SYNC_EMPTY_GIFS:-0}" != 1 ]; then
  echo "no GIFs in this deploy: keeping the $(find "$PREFIX/gifs" -iname '*.gif' | wc -l) on the Pi"
  SKIP_GIFS=1
fi
sync_dir() {
  if [ -n "$(rsync -a --omit-dir-times --delete --exclude __pycache__ --itemize-changes "$1" "$2")" ]; then
    echo "synced $2"; changed=1
  fi
}
sync_dir "$REPO/pixelpane/" "$PREFIX/pixelpane/"
[ "${SKIP_GIFS:-0}" = 1 ] || sync_dir "$REPO/gifs/" "$PREFIX/gifs/"
[ -f "$REPO/VERSION" ] && install_file "$REPO/VERSION" "$PREFIX/VERSION" 644
rm -f "$PREFIX/start-pixelpane.sh"   # the old led-image-viewer launcher

echo "== service + system config"
install_file "$REPO/system/pixelpane.service" /etc/systemd/system/pixelpane.service 644
install_file "$REPO/system/blacklist-rgb-matrix.conf" /etc/modprobe.d/blacklist-rgb-matrix.conf 644

# Onboard audio shares the PWM hardware the hzeller driver uses; it must be off.
if [ "$PI5" -eq 0 ] && ! grep -q '^dtparam=audio=off' "$BOOT/config.txt"; then
  sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "$BOOT/config.txt"
  grep -q '^dtparam=audio=off' "$BOOT/config.txt" || echo 'dtparam=audio=off' >> "$BOOT/config.txt"
  echo "config.txt: audio off"; reboot_needed=1
fi
# Reserve core 3 for the matrix refresh thread (less flicker).
if [ "$PI5" -eq 0 ] && ! grep -qw 'isolcpus=3' "$BOOT/cmdline.txt"; then
  sed -i '1 s/$/ isolcpus=3/' "$BOOT/cmdline.txt"
  echo "cmdline.txt: isolcpus=3"; reboot_needed=1
fi

# Optional hostname (PIXELPANE_HOSTNAME=pixelpane in deploy.env).
if [ -n "${PIXELPANE_HOSTNAME:-}" ] && [ "$(hostname)" != "$PIXELPANE_HOSTNAME" ]; then
  hostnamectl set-hostname "$PIXELPANE_HOSTNAME"
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$PIXELPANE_HOSTNAME/" /etc/hosts
  echo "hostname: $PIXELPANE_HOSTNAME"
fi

# The clock needs local time (images ship as Europe/London).
if [ -n "${PIXELPANE_TZ:-}" ] && [ "$(timedatectl show -p Timezone --value)" != "$PIXELPANE_TZ" ]; then
  timedatectl set-timezone "$PIXELPANE_TZ"
  echo "timezone: $PIXELPANE_TZ"
fi

# Wi-Fi stays rfkill-blocked until a regulatory country is set.
if [ -n "${PIXELPANE_WIFI_COUNTRY:-}" ] && [ "$(raspi-config nonint get_wifi_country 2>/dev/null)" != "$PIXELPANE_WIFI_COUNTRY" ]; then
  raspi-config nonint do_wifi_country "$PIXELPANE_WIFI_COUNTRY"
  echo "wifi country: $PIXELPANE_WIFI_COUNTRY"
fi

echo "== hardening"
# Security updates nightly; reboot at 04:00 only when an update needs it.
write_file /etc/apt/apt.conf.d/20auto-upgrades 644 <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
write_file /etc/apt/apt.conf.d/52pixelpane-upgrades 644 <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
# Keys only, once the deploying user has a key installed (the console still works).
if [ -s "/home/${SUDO_USER:-nobody}/.ssh/authorized_keys" ]; then
  write_file /etc/ssh/sshd_config.d/10-pixelpane.conf 644 <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
  sshd -t && systemctl reload ssh
fi
# Nothing here uses Bluetooth, cloud-init (first boot only) or udisks.
if ! grep -q '^dtoverlay=disable-bt' "$BOOT/config.txt"; then
  echo 'dtoverlay=disable-bt' >> "$BOOT/config.txt"
  echo "config.txt: bluetooth off"; reboot_needed=1
fi
for unit in bluetooth.service hciuart.service udisks2.service; do
  if systemctl list-unit-files "$unit" >/dev/null 2>&1 && [ "$(systemctl is-enabled "$unit" 2>/dev/null)" != masked ]; then
    systemctl disable --now -q "$unit" 2>/dev/null || true
    systemctl mask -q "$unit"
    echo "masked $unit"
  fi
done
[ -e /etc/cloud/cloud-init.disabled ] || { touch /etc/cloud/cloud-init.disabled; echo "cloud-init disabled"; }
# Logs in RAM: fewer SD writes. They do not survive a reboot.
write_file /etc/systemd/journald.conf.d/10-pixelpane.conf 644 <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=30M
EOF

systemctl daemon-reload
systemctl restart systemd-journald
systemctl enable -q pixelpane.service
if [ "$changed" -eq 1 ] || ! systemctl is-active -q pixelpane.service; then
  systemctl restart pixelpane.service
  echo "pixelpane.service restarted"
fi

sleep 3
systemctl is-active pixelpane.service
[ "$reboot_needed" -eq 1 ] && echo "REBOOT NEEDED for boot config changes"
echo "done"
