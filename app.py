import os
import re
import json
import glob
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Config helpers (a JSON file stands in for a database — there's very little
# to store: the admin credentials, the caddy.d directory, and a session key)
# ---------------------------------------------------------------------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def is_configured():
    cfg = load_config()
    return bool(cfg and cfg.get("username") and cfg.get("password_hash") and cfg.get("caddy_dir"))


@app.before_request
def load_secret_key():
    cfg = load_config()
    if cfg and cfg.get("secret_key"):
        app.secret_key = cfg["secret_key"]
    else:
        # Temporary key so the setup page can still use flash()/session.
        if "_TEMP_SECRET" not in app.config:
            app.config["_TEMP_SECRET"] = secrets.token_hex(32)
        app.secret_key = app.config["_TEMP_SECRET"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_configured():
            return redirect(url_for("setup"))
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if is_configured():
        return redirect(url_for("login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        caddy_dir = request.form.get("caddy_dir", "").strip()

        if not username or not password:
            error = "Username and password are required."
        elif password != password2:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif not caddy_dir:
            error = "Caddy conf directory is required."
        else:
            try:
                os.makedirs(caddy_dir, exist_ok=True)
            except OSError as e:
                error = f"Could not create/access that directory: {e}"

        if not error:
            cfg = {
                "secret_key": secrets.token_hex(32),
                "username": username,
                "password_hash": generate_password_hash(password),
                "caddy_dir": caddy_dir,
            }
            save_config(cfg)
            # Switch to the real secret key immediately so the flash message
            # set below actually survives the redirect to /login.
            app.secret_key = cfg["secret_key"]
            flash("Setup complete. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("setup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not is_configured():
        return redirect(url_for("setup"))
    error = None
    if request.method == "POST":
        cfg = load_config()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == cfg["username"] and check_password_hash(cfg["password_hash"], password):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def get_caddy_dir():
    cfg = load_config()
    return cfg["caddy_dir"]


def safe_path(filename):
    """Resolve filename inside caddy_dir, preventing path traversal."""
    caddy_dir = os.path.abspath(get_caddy_dir())
    target = os.path.abspath(os.path.join(caddy_dir, filename))
    if target != caddy_dir and not target.startswith(caddy_dir + os.sep):
        abort(400, "Invalid filename")
    return target


def split_target(value):
    """Split a Caddy upstream/target string like 'https://host:port' into
    (scheme, host, port). Any part that isn't present comes back as ''."""
    value = (value or "").strip()
    scheme, rest = value.split("://", 1) if "://" in value else ("", value)
    host, _, port = rest.partition(":")
    return scheme, host, port


def join_target(scheme, host, port):
    """Inverse of split_target: build a Caddy upstream/target string from
    parts, omitting any that are blank."""
    target = (host or "").strip()
    if port:
        target = f"{target}:{port.strip()}"
    if scheme:
        target = f"{scheme.strip()}://{target}"
    return target


def normalize_hosts(raw_hosts):
    """Clean, dedupe (first occurrence wins) and sort a list of hosts:
    hosts starting with a letter sort before hosts starting with a digit,
    alphabetically within each group -- e.g. api.example.com, app.example.com,
    2.example.com."""
    seen = set()
    hosts = []
    for h in raw_hosts:
        h = (h or "").strip()
        if h and h not in seen:
            seen.add(h)
            hosts.append(h)
    hosts.sort(key=lambda h: (h[:1].isdigit(), h.lower()))
    return hosts


def hosts_from_textarea(text):
    """Parse a one-host-per-line textarea into a normalized host list."""
    return normalize_hosts((text or "").splitlines())


def hosts_header(hosts):
    """Caddyfile site-address line for one or more hosts."""
    return ", ".join(hosts)


def extra_lines(extra_text):
    return [line.strip() for line in (extra_text or "").splitlines() if line.strip()]


def render_domain_block(site_header, body_lines):
    lines = [f"{site_header} {{"]
    lines.extend(f"    {line}" for line in body_lines)
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_reverse_proxy(site_header, target, extra_text="", insecure_skip_verify=False):
    body = [f"reverse_proxy {target}"]
    if insecure_skip_verify:
        body += ["transport http {", "    tls_insecure_skip_verify", "}"]
    body += extra_lines(extra_text)
    return render_domain_block(site_header, body)


def render_redirect(site_header, target, redirect_code=""):
    redirect_code = (redirect_code or "").strip()
    directive = f"redir {target} {redirect_code}" if redirect_code else f"redir {target}"
    return render_domain_block(site_header, [directive])


def render_load_balancer(site_header, upstreams, lb_policy="", extra_text=""):
    inner = [f"lb_policy {lb_policy}"] if lb_policy else []
    inner += extra_lines(extra_text)
    body = [f"reverse_proxy {' '.join(upstreams)} {{"]
    body += [f"    {line}" for line in inner]
    body += ["}"]
    return render_domain_block(site_header, body)


def render_custom(site_header, body_text):
    """Wrap a user-authored body (whatever's between the braces) with the
    site header, which is always derived from the Hosts field -- the user
    only ever writes/edits the inside of the block, never the host line."""
    body = (body_text or "").rstrip("\n")
    return f"{site_header} {{\n{body}\n}}\n" if body else f"{site_header} {{\n}}\n"


def extract_body(content):
    """Return the text between the first '{' and the matching last '}' of
    a block -- i.e. the inverse of render_custom -- for prefilling the
    custom-block edit form. Assumes one block per file, which matches how
    this app writes .conf files."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return content.strip()
    return content[start + 1:end].strip("\n")


# ---------------------------------------------------------------------------
# Conf parsing & metadata
#
# Every block gets a small sidecar metadata file (same base name as the
# .conf, extension .json) living in a hidden .metadata subdirectory of the
# caddy.d directory -- kept out of the way of Caddy's own `import *.conf`
# and out of the way of the sites list. It holds the block's structured
# fields plus the .conf's mtime/size at the time it was written. Listing a
# directory is then just one JSON read per file -- the .conf itself is
# only re-parsed with regex when a sidecar is missing or its stamped
# mtime/size no longer matches the .conf on disk (i.e. it was created or
# hand-edited outside the app). Blocks created/edited through this app's
# forms never take that path at all: their metadata is written directly
# from the submitted fields.
# ---------------------------------------------------------------------------

REVERSE_PROXY_RE = re.compile(r"^\s*reverse_proxy\s+([^\n{]+?)\s*\{?\s*$", re.MULTILINE)
LB_POLICY_RE = re.compile(r"^\s*lb_policy\s+(\S+)", re.MULTILINE)
REDIR_RE = re.compile(r"^\s*redir(?:ect)?\s+(\S+)(?:\s+(\d{3}))?", re.MULTILINE)


def extract_hosts(content):
    """Pull the site-address line out of a raw block ('host1, host2 {')
    and return it as a normalized, sorted host list."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and "{" in stripped and not stripped.startswith("#"):
            header = stripped.split("{")[0].strip()
            return normalize_hosts(re.split(r"[,\s]+", header))
    return []


def parse_conf_content(content):
    """Best-effort structured parse of a raw Caddy block. Only used as a
    fallback for files this app didn't write itself (or that were
    hand-edited since) -- app-created blocks skip this entirely because
    their metadata is written straight from the form."""
    hosts = extract_hosts(content)
    rp_match = REVERSE_PROXY_RE.search(content)
    lb_match = LB_POLICY_RE.search(content)

    if rp_match and lb_match:
        upstreams = rp_match.group(1).split()
        return {"type": "load_balancer", "hosts": hosts, "upstreams": upstreams,
                "lb_policy": lb_match.group(1), "extra": ""}

    if rp_match:
        tokens = rp_match.group(1).split()
        target = tokens[0] if tokens else ""
        scheme, host, port = split_target(target)
        return {"type": "reverse_proxy", "hosts": hosts, "target": target,
                "scheme": scheme, "host": host, "port": port, "extra": ""}

    redir_match = REDIR_RE.search(content)
    if redir_match:
        return {"type": "redirect", "hosts": hosts, "target": redir_match.group(1),
                "redirect_code": redir_match.group(2) or ""}

    return {"type": "custom", "hosts": hosts}


def meta_filename_for(conf_filename):
    base = conf_filename[: -len(".disabled")] if conf_filename.endswith(".disabled") else conf_filename
    if base.endswith(".conf"):
        base = base[: -len(".conf")]
    return base + ".json"


def metadata_dir():
    return os.path.join(get_caddy_dir(), ".metadata")


def safe_meta_path(filename):
    """Resolve filename inside the hidden .metadata directory, preventing
    path traversal."""
    base = os.path.abspath(metadata_dir())
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        abort(400, "Invalid filename")
    return target


def meta_path_for(conf_filename):
    return safe_meta_path(meta_filename_for(conf_filename))


def write_metadata(conf_filename, conf_path, meta):
    """Persist metadata for a block, stamped with the .conf's current
    mtime/size so future reads know whether the cache is still valid."""
    try:
        st = os.stat(conf_path)
    except OSError:
        return
    meta = {**meta, "source_mtime": st.st_mtime, "source_size": st.st_size}
    try:
        os.makedirs(metadata_dir(), exist_ok=True)
        with open(meta_path_for(conf_filename), "w") as f:
            json.dump(meta, f, indent=2)
    except OSError:
        pass


def read_metadata(conf_filename, conf_path):
    """Load metadata for a block: the cached sidecar if it's still fresh,
    otherwise a fallback parse of the .conf content (which also refreshes
    the cache so the next read is cheap again)."""
    try:
        st = os.stat(conf_path)
    except OSError:
        return {"type": "custom", "hosts": []}

    meta_file = meta_path_for(conf_filename)
    if os.path.isfile(meta_file):
        try:
            with open(meta_file) as f:
                cached = json.load(f)
            if cached.get("source_mtime") == st.st_mtime and cached.get("source_size") == st.st_size:
                return cached
        except (OSError, ValueError):
            pass

    try:
        with open(conf_path) as f:
            content = f.read()
    except OSError:
        content = ""
    parsed = parse_conf_content(content)
    write_metadata(conf_filename, conf_path, parsed)
    return parsed


def delete_metadata(conf_filename):
    meta_file = meta_path_for(conf_filename)
    if os.path.isfile(meta_file):
        try:
            os.remove(meta_file)
        except OSError:
            pass


def list_blocks():
    caddy_dir = get_caddy_dir()
    if not os.path.isdir(caddy_dir):
        return []
    paths = glob.glob(os.path.join(caddy_dir, "*.conf")) + \
        glob.glob(os.path.join(caddy_dir, "*.conf.disabled"))

    blocks = []
    for path in paths:
        fname = os.path.basename(path)
        disabled = fname.endswith(".disabled")
        fdate = datetime.fromtimestamp(os.path.getmtime(path))
        meta = read_metadata(fname, path)
        hosts = meta.get("hosts", [])
        block_type = meta.get("type", "custom")

        if block_type in ("reverse_proxy", "redirect"):
            upstream_sort = meta.get("target", "")
        elif block_type == "load_balancer":
            upstream_sort = f"{len(meta.get('upstreams', []))} upstreams"
        else:
            upstream_sort = "custom"

        blocks.append({
            "filename": fname,
            "disabled": disabled,
            "type": block_type,
            "hosts": hosts,
            "scheme": meta.get("scheme", ""),
            "host": meta.get("host", ""),
            "port": meta.get("port", ""),
            "target": meta.get("target", ""),
            "redirect_code": meta.get("redirect_code", ""),
            "upstreams": meta.get("upstreams", []),
            "lb_policy": meta.get("lb_policy", ""),
            "updated": fdate.strftime("%d/%m/%Y %I:%M%p"),
            "updated_ts": os.path.getmtime(path),
            "upstream_sort": upstream_sort,
        })
    blocks.sort(key=lambda b: b["filename"].lower())
    return blocks


def slugify(value):
    value = (value or "").strip().lower()
    out = []
    for ch in value:
        if ch.isalnum() or ch == ".":
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "block"


def unique_filename(base):
    caddy_dir = get_caddy_dir()
    candidate = f"{base}.conf"
    i = 2
    while os.path.exists(os.path.join(caddy_dir, candidate)) or \
            os.path.exists(os.path.join(caddy_dir, candidate + ".disabled")):
        candidate = f"{base}-{i}.conf"
        i += 1
    return candidate


def rename_block_if_first_host_changed(filename, path, old_hosts, new_hosts):
    """If the sorted, first (i.e. filename-defining) host changed, rename
    the .conf (and its metadata sidecar) to match -- preserving the
    .disabled suffix if the block is currently disabled. Returns the
    filename/path to use from here on (unchanged if no rename happened)."""
    old_first = old_hosts[0] if old_hosts else None
    new_first = new_hosts[0] if new_hosts else None
    if not new_first or (old_first and slugify(new_first) == slugify(old_first)):
        return filename, path

    disabled = filename.endswith(".disabled")
    new_conf_name = unique_filename(slugify(new_first))
    if disabled:
        new_conf_name += ".disabled"

    try:
        new_path = safe_path(new_conf_name)
        os.rename(path, new_path)
        old_meta_path = meta_path_for(filename)
        if os.path.isfile(old_meta_path):
            os.rename(old_meta_path, meta_path_for(new_conf_name))
        return new_conf_name, new_path
    except OSError:
        # Content/metadata are already saved under the old name -- if the
        # rename itself fails, just keep the old filename rather than
        # losing the edit.
        return filename, path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    stats = {
        "total": len(blocks),
        "enabled": sum(1 for b in blocks if not b["disabled"]),
        "disabled": sum(1 for b in blocks if b["disabled"]),
    }
    return render_template(
        "home.html", stats=stats, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@app.route("/sites")
@login_required
def sites():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    return render_template(
        "sites.html", blocks=blocks, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@app.route("/new/<block_type>", methods=["GET", "POST"])
@login_required
def new_block(block_type):
    if block_type not in ("reverse_proxy", "redirect", "load_balancer", "custom"):
        abort(404)
    error = None
    meta = {}

    if request.method == "POST":
        hosts = hosts_from_textarea(request.form.get("hosts", ""))
        content = None

        if block_type == "reverse_proxy":
            scheme = request.form.get("scheme", "http").strip() or "http"
            host = request.form.get("host", "").strip()
            port = request.form.get("port", "").strip()
            extra = request.form.get("extra", "").strip()
            insecure_skip_verify = scheme == "https" and request.form.get("insecure_skip_verify") == "1"
            meta = {"hosts": hosts, "scheme": scheme, "host": host, "port": port,
                    "extra": extra, "insecure_skip_verify": insecure_skip_verify}
            if not hosts:
                error = "At least one host is required."
            elif not host:
                error = "Upstream host is required."
            else:
                target = join_target(scheme, host, port)
                content = render_reverse_proxy(hosts_header(hosts), target, extra, insecure_skip_verify)
                meta = {"type": "reverse_proxy", "target": target, **meta}

        elif block_type == "load_balancer":
            upstreams = [u.strip() for u in request.form.get("upstreams", "").splitlines() if u.strip()]
            lb_policy = request.form.get("lb_policy", "").strip()
            extra = request.form.get("extra", "").strip()
            meta = {"hosts": hosts, "upstreams": upstreams, "lb_policy": lb_policy, "extra": extra}
            if not hosts:
                error = "At least one host is required."
            elif len(upstreams) < 2:
                error = "At least two upstreams are required."
            else:
                content = render_load_balancer(hosts_header(hosts), upstreams, lb_policy, extra)
                meta = {"type": "load_balancer", **meta}

        elif block_type == "redirect":
            target = request.form.get("target", "").strip()
            redirect_code = request.form.get("redirect_code", "301").strip()
            meta = {"hosts": hosts, "target": target, "redirect_code": redirect_code}
            if not hosts:
                error = "At least one host is required."
            elif not target:
                error = "Redirect target is required."
            else:
                content = render_redirect(hosts_header(hosts), target, redirect_code)
                meta = {"type": "redirect", **meta}

        else:  # custom
            raw = request.form.get("raw_content", "").strip()
            meta = {"hosts": hosts}
            if not hosts:
                error = "At least one host is required."
            elif not raw:
                error = "Block content is required."
            else:
                content = render_custom(hosts_header(hosts), raw)
                meta = {"type": "custom", **meta}

        if not error:
            filename = unique_filename(slugify(hosts[0]))
            os.makedirs(get_caddy_dir(), exist_ok=True)
            path = safe_path(filename)
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, meta)
            flash(f"Created {filename}", "success")
            return redirect(url_for("sites"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    hosts_text = "\n".join(meta.get("hosts") or [])
    raw_body_text = raw if block_type == "custom" and request.method == "POST" else ""
    return render_template(
        "block_form.html", mode="new", block_type=block_type,
        meta=meta, upstreams_text=upstreams_text, hosts_text=hosts_text,
        raw_body_text=raw_body_text, error=error
    )


@app.route("/edit/<path:filename>", methods=["GET", "POST"])
@login_required
def edit_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    meta = read_metadata(filename, path)
    block_type = meta.get("type", "custom")
    old_hosts = meta.get("hosts", [])
    error = None
    raw_body_text = ""
    if block_type == "custom" and request.method == "GET":
        with open(path) as f:
            raw_body_text = extract_body(f.read())

    if request.method == "POST":
        hosts = hosts_from_textarea(request.form.get("hosts", ""))
        content = None
        new_meta = None

        if block_type == "reverse_proxy":
            scheme = request.form.get("scheme", "http").strip() or "http"
            host = request.form.get("host", "").strip()
            port = request.form.get("port", "").strip()
            extra = request.form.get("extra", "").strip()
            insecure_skip_verify = scheme == "https" and request.form.get("insecure_skip_verify") == "1"
            meta = {**meta, "hosts": hosts, "scheme": scheme, "host": host, "port": port,
                    "extra": extra, "insecure_skip_verify": insecure_skip_verify}
            if not hosts:
                error = "At least one host is required."
            elif not host:
                error = "Upstream host is required."
            else:
                target = join_target(scheme, host, port)
                content = render_reverse_proxy(hosts_header(hosts), target, extra, insecure_skip_verify)
                new_meta = {"type": "reverse_proxy", "hosts": hosts, "scheme": scheme, "host": host,
                            "port": port, "target": target, "extra": extra,
                            "insecure_skip_verify": insecure_skip_verify}

        elif block_type == "load_balancer":
            upstreams = [u.strip() for u in request.form.get("upstreams", "").splitlines() if u.strip()]
            lb_policy = request.form.get("lb_policy", "").strip()
            extra = request.form.get("extra", "").strip()
            meta = {**meta, "hosts": hosts, "upstreams": upstreams, "lb_policy": lb_policy, "extra": extra}
            if not hosts:
                error = "At least one host is required."
            elif len(upstreams) < 2:
                error = "At least two upstreams are required."
            else:
                content = render_load_balancer(hosts_header(hosts), upstreams, lb_policy, extra)
                new_meta = {"type": "load_balancer", "hosts": hosts, "upstreams": upstreams,
                            "lb_policy": lb_policy, "extra": extra}

        elif block_type == "redirect":
            target = request.form.get("target", "").strip()
            redirect_code = request.form.get("redirect_code", "").strip()
            meta = {**meta, "hosts": hosts, "target": target, "redirect_code": redirect_code}
            if not hosts:
                error = "At least one host is required."
            elif not target:
                error = "Redirect target is required."
            else:
                content = render_redirect(hosts_header(hosts), target, redirect_code)
                new_meta = {"type": "redirect", "hosts": hosts, "target": target,
                            "redirect_code": redirect_code}

        else:  # custom
            raw = request.form.get("raw_content", "").strip()
            meta = {**meta, "hosts": hosts}
            raw_body_text = raw
            if not hosts:
                error = "At least one host is required."
            elif not raw:
                error = "Block content is required."
            else:
                content = render_custom(hosts_header(hosts), raw)
                new_meta = {"type": "custom", "hosts": hosts}

        if not error:
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, new_meta)
            # Rename the .conf/.metadata pair if the primary (first-after-
            # sorting) host changed, so the filename keeps tracking it.
            filename, path = rename_block_if_first_host_changed(filename, path, old_hosts, hosts)
            flash(f"Saved {filename}", "success")
            return redirect(url_for("sites"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    hosts_text = "\n".join(meta.get("hosts") or [])
    return render_template(
        "block_form.html", mode="edit", block_type=block_type, filename=filename,
        meta=meta, upstreams_text=upstreams_text, hosts_text=hosts_text,
        raw_body_text=raw_body_text, error=error
    )


@app.route("/toggle/<path:filename>", methods=["POST"])
@login_required
def toggle_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    if filename.endswith(".disabled"):
        new_name = filename[: -len(".disabled")]
    else:
        new_name = filename + ".disabled"

    os.rename(path, safe_path(new_name))
    state = "Disabled" if new_name.endswith(".disabled") else "Enabled"
    flash(f"{state} {new_name}", "success")
    return redirect(url_for("sites"))


@app.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete_block(filename):
    path = safe_path(filename)
    if os.path.isfile(path):
        os.remove(path)
        delete_metadata(filename)
        flash(f"Deleted {filename}", "success")
    return redirect(url_for("sites"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    cfg = load_config()
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_dir":
            new_dir = request.form.get("caddy_dir", "").strip()
            if not new_dir:
                error = "Directory is required."
            else:
                try:
                    os.makedirs(new_dir, exist_ok=True)
                except OSError as e:
                    error = f"Could not create/access that directory: {e}"
                if not error:
                    cfg["caddy_dir"] = new_dir
                    save_config(cfg)
                    flash("Caddy directory updated.", "success")
                    return redirect(url_for("settings"))

        elif action == "change_password":
            current = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password2 = request.form.get("new_password2", "")
            if not check_password_hash(cfg["password_hash"], current):
                error = "Current password is incorrect."
            elif len(new_password) < 6:
                error = "New password must be at least 6 characters."
            elif new_password != new_password2:
                error = "New passwords do not match."
            else:
                cfg["password_hash"] = generate_password_hash(new_password)
                save_config(cfg)
                flash("Password updated.", "success")
                return redirect(url_for("settings"))

    return render_template("settings.html", cfg=cfg, error=error)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
