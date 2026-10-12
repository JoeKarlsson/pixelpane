# Security

## How PixelPane is meant to run

PixelPane is a LAN appliance. Out of the box its web page and API have **no login**:
anyone who can reach the board on your network can control it, upload GIFs or change
its settings. Set a token under **Settings, Access** to require it for every change
(and for logs and backups). Keep the board on your home network (an isolated IoT
network is ideal) and do not expose port 80 to the internet. To reach it remotely,
put it behind a reverse proxy with authentication (for example Authentik or a VPN
such as Tailscale), and add the proxy's host name under Settings, Allowed host names.

What the board does to protect itself:

- Cross-site writes are refused: a web page open in your browser cannot drive the
  board (requests with a foreign `Origin` header get a 403).
- It only answers to its IP addresses, its own host names (`pixelpane`,
  `pixelpane.local`...) and names you allow, which blocks DNS rebinding.
- The page is served with a strict Content Security Policy and can't be framed.
- Saved secrets (like the generator's API key) are never sent back out, and
  changing the generator's server clears its key, so the key can't be redirected.
- Scenes accept only the parameters they declare, the live preview is limited to a
  few viewers at once and only one GIF is generated at a time.
- The controller starts as root only to open the GPIO and port 80, then drops to
  an unprivileged user, inside a systemd sandbox (read-only system, no kernel
  tunables or modules). Your plugins live in root-owned `/etc/pixelpane/plugins`,
  which the service can't write. The installer turns off SSH passwords once a key is
  installed and enables automatic security updates.
- Album art is fetched only from hosts you list in `now_playing.art_hosts`.
- Album art is never fetched through redirects, and a host must match exactly
  (scheme, name and port), not just by prefix.
- Uploads are converted to GIF with Pillow and stored under `/var/lib/pixelpane`;
  GIF ids are resolved and checked so they can't reach a file outside the library
  folders (absolute paths, `..` and symlinks included).

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting
(**Security > Report a vulnerability** on the repository) rather than a public
issue. You'll get a reply within a week.
