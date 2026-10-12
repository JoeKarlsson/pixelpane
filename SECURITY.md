# Security

## How PixelPane is meant to run

PixelPane is a LAN appliance. Its web page and API have **no login**: anyone who
can reach the board on your network can control it, upload GIFs or change its
settings. Keep it on your home network (an isolated IoT network is ideal) and do
not expose port 80 to the internet. To reach it remotely, put it behind a reverse
proxy with authentication (for example Authentik or a VPN such as Tailscale).

What the board does to protect itself:

- Cross-site writes are refused: a web page open in your browser cannot drive the
  board (requests with a foreign `Origin` header get a 403).
- The controller starts as root only to open the GPIO and port 80, then drops to
  an unprivileged user. The installer turns off SSH passwords once a key is
  installed and enables automatic security updates.
- Album art is fetched only from hosts you list in `now_playing.art_hosts`.
- Uploads are converted to GIF with Pillow and stored under `/var/lib/pixelpane`;
  paths are checked so a GIF id cannot escape the library folders.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting
(**Security > Report a vulnerability** on the repository) rather than a public
issue. You'll get a reply within a week.
