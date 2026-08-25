# Caddyfile Manager

A tiny, self-contained web app for creating and managing individual Caddy
`.conf` blocks inside a `caddy.d`-style directory — no database, no
frontend build step, just Flask + server-rendered HTML on top of the
[Tabler](https://tabler.io/admin-template) UI kit (loaded from a CDN,
light theme, azure accent, neutral gray base, tight 2x corner radius — see
`static/css/override.css`).

It assumes your main `Caddyfile` has a line like:

```
import caddy.d/*.conf
```

so any enabled `.conf` file in that directory is picked up automatically,
and a `.conf.disabled` file is ignored.

## Terminology

Following the [Caddyfile structure](https://caddyserver.com/docs/caddyfile/concepts#structure),
the app calls the domain(s) a block matches on its **Site Address(es)**,
and calls each managed `.conf` file a **Site Block**. Reverse proxy,
redirect, load balancer, and custom blocks are all just different bodies
wrapped in a site-address header.

## Features

- Login-protected (single admin account, set up on first run)
- Configurable `caddy.d` directory (can be changed later in Settings)
- **Home** page: at-a-glance counts of active / disabled site blocks
- **Site Blocks** page: searchable, sortable, filterable, paginated table
  of every block (state persists across visits in `sessionStorage`), with
  a type-colored badge per row and a warning icon for any block with no
  site address configured
- A single **New Site Block** popup (shared between Home and Site Blocks)
  with a type-colored card per block type:
  - **Reverse Proxy** *(azure)* — site address(es) + upstream host/port +
    scheme, with an optional "skip TLS verification" toggle
  - **Redirect** *(purple)* — site address(es) + target + status code
  - **Load Balancer** *(pink)* — site address(es) + a shared scheme
    selector with structured host/port rows for each upstream (add/remove
    as needed) + load-balancing policy
  - **Custom** *(yellow)* — write the raw block body yourself, for
    anything else
  - Every type has an **Advanced options** accordion for extra raw
    directives (reverse proxy / load balancer) and a **Create disabled**
    checkbox that writes the block straight to disk as `.disabled` so it
    never goes live until you enable it
  - The form header shows a live preview of the exact `.conf` path the
    block will be saved to (or is currently saved at, in edit mode),
    updating as you add/remove site addresses
- Reads and lists *any* `.conf` / `.conf.disabled` file in the directory,
  whether it was created by the app or dropped in manually — type and
  site address(es) are detected from the file content if there's no
  metadata sidecar yet (see below)
- Enable/disable a block with one click (renames `file.conf` ⇄
  `file.conf.disabled`)
- A read-only **Preview** page for each block: rendered Caddyfile
  content, raw metadata JSON, and a details sidebar (status, type, site
  address(es), upstream/target, file path, created/updated timestamps)
- Edit a block's fields (or its raw content, for custom blocks), or
  delete it
- Change the admin password from Settings

### Metadata sidecars

Every block gets a small `.json` sidecar in a hidden `.metadata`
subdirectory alongside your `.conf` files, caching its structured fields
plus the `.conf`'s mtime/size. This makes listing the directory a single
JSON read per file; the `.conf` itself is only re-parsed with regex when
a sidecar is missing or stale (e.g. the file was created or hand-edited
outside the app). Sidecars for `.conf` files that no longer exist are
cleaned up automatically.

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

## Project structure

```
app.py                        # entry point: create_app() + dev server
caddy_manager/
  __init__.py                 # application factory (secret key, blueprints, Jinja globals)
  configstore.py              # config.json load/save/is_configured/get_caddy_dir
  colors.py                   # the one place block-type -> Tabler color is defined
  caddyfile.py                # pure Caddyfile string building & parsing (no file I/O)
  blocks.py                   # filesystem/metadata layer + shared block-form parsing
  auth.py                     # login_required + the auth blueprint (setup/login/logout)
  views.py                    # the main blueprint (dashboard, site blocks, settings, etc.)
templates/                    # Jinja templates (unchanged location)
static/                       # CSS/JS/images (unchanged location)
```

`app.py` stays a thin entry point (`from caddy_manager import create_app`)
so `python app.py` and the systemd unit below keep working exactly as
before.

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

- New files are named from a slugified version of the first site address
  after sorting (letter-leading addresses sort before digit-leading ones,
  alphabetically within each group), e.g. `app.example.com` →
  `app.example.com.conf`. Slugifying only replaces characters that aren't
  alphanumeric or a dot, so ordinary domains pass through unchanged.
- If a name is already taken, a numeric suffix is added
  (`app.example.com-2.conf`).
- Editing a block and changing what its first (sorted) site address is
  renames the `.conf` (and its metadata sidecar) to match, preserving the
  `.disabled` suffix if the block is currently disabled.
- Disabling a block appends `.disabled` to the filename; enabling removes
  it. Nothing else about the file changes. Checking **Create disabled**
  when creating a new block does the same thing, up front.
