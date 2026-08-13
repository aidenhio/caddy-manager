# Caddyfile Manager

A tiny, self-contained web app for creating and managing individual Caddy
`.conf` blocks inside a `caddy.d`-style directory — no database, no
frontend build step, just Flask + server-rendered HTML on top of the
[Tabler](https://tabler.io/admin-template) UI kit (vendored locally under
`static/vendor/`, dark theme, lime accent, neutral base, tight 2x corner
radius — see `static/custom.css`).

It assumes your main `Caddyfile` has a line like:

```
import caddy.d/*.conf
```

so any enabled `.conf` file in that directory is picked up automatically,
and a `.conf.disabled` file is ignored.

## Features

- Login-protected (single admin account, set up on first run)
- Configurable `caddy.d` directory (can be changed later in Settings)
- **Home** page: at-a-glance counts of configured / active / disabled sites
- **Sites** page: full table of blocks, plus create buttons for:
  - **Reverse proxy** (domain + upstream + optional extra directives)
  - **Redirect** (domain + target + status code)
  - **Custom** (write the raw block yourself — for anything else)
- Reads and lists *any* `.conf` / `.conf.disabled` file in the directory,
  whether it was created by the app or dropped in manually — type and
  domain are detected from the file content
- Enable/disable a block with one click (renames `file.conf` ⇄
  `file.conf.disabled`)
- Edit raw file content or delete a block
- Change the admin password from Settings

## Requirements

- Python 3.8+
- Flask (see `requirements.txt`)

## Setup

```bash
cd caddyfile-manager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

By default it listens on `http://0.0.0.0:5000`. Set a different port with
the `PORT` environment variable if needed, e.g. `PORT=8080 python app.py`.

On first visit you'll be sent to `/setup` to create the admin username,
password, and point the app at your `caddy.d` directory (e.g.
`/etc/caddy/caddy.d`). That configuration is stored in `config.json`,
created next to `app.py` — keep this file private, it contains the
password hash.

## Running for real use

For anything beyond local testing, put this behind Caddy itself (or
another reverse proxy) with HTTPS, and consider running it via a process
manager (systemd, supervisor, etc.) rather than `python app.py` directly.
A minimal systemd unit:

```ini
[Unit]
Description=Caddyfile Manager
After=network.target

[Service]
WorkingDirectory=/opt/caddyfile-manager
ExecStart=/opt/caddyfile-manager/venv/bin/python app.py
Environment=PORT=8080
Restart=on-failure
User=caddy-manager

[Install]
WantedBy=multi-user.target
```

Make sure whichever user runs the app has read/write permission on the
`caddy.d` directory, and that Caddy's admin/reload mechanism (e.g. a
`caddy reload` triggered manually, via a cron job, or a file-watcher) is
still your responsibility — this app only manages the `.conf` files
themselves, it does not reload Caddy for you.

## Notes on file naming

- New files are named from a slugified version of the domain (or the
  filename field, if you override it), e.g. `app.example.com` →
  `app-example-com.conf`.
- If a name is already taken, a numeric suffix is added
  (`app-example-com-2.conf`).
- Disabling a block appends `.disabled` to the filename; enabling removes
  it. Nothing else about the file changes.
