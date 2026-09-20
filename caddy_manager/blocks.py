"""Block file & metadata management. Each block gets a hidden .metadata/*.json
sidecar so listing is a cheap JSON read; re-parsed only when stale or missing."""
import os
import glob
import json
from datetime import datetime

from flask import abort

from .configstore import get_conf_dir, get_log_dir, get_caddy_log_output_dir
from .caddyfile import (
    site_addresses_from_textarea, site_address_header, slugify,
    join_target, split_target, parse_conf_content, custom_block_preview, extract_body,
    render_reverse_proxy, render_redirect, render_load_balancer, render_custom, render_static_site,
    render_log_block, ENCODE_FORMATS, LOG_LEVELS, LOG_FORMATS,
)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def safe_path(filename):
    """Resolve filename inside conf_dir, preventing path traversal."""
    conf_dir = os.path.abspath(get_conf_dir())
    target = os.path.abspath(os.path.join(conf_dir, filename))
    if target != conf_dir and not target.startswith(conf_dir + os.sep):
        abort(400, "Invalid filename")
    return target


def metadata_dir():
    return os.path.join(get_conf_dir(), ".metadata")


def safe_meta_path(filename):
    """Resolve filename inside the hidden .metadata directory, preventing
    path traversal."""
    base = os.path.abspath(metadata_dir())
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        abort(400, "Invalid filename")
    return target


def block_base_name(conf_filename):
    """The .conf filename with its .disabled/.conf suffixes stripped --
    the stem shared by a block's .conf, sidecar, and log file."""
    base = conf_filename[: -len(".disabled")] if conf_filename.endswith(".disabled") else conf_filename
    if base.endswith(".conf"):
        base = base[: -len(".conf")]
    return base


def meta_filename_for(conf_filename):
    return block_base_name(conf_filename) + ".json"


def meta_path_for(conf_filename):
    return safe_meta_path(meta_filename_for(conf_filename))


def safe_log_path(filename):
    """Resolve filename inside the configured logs directory, preventing
    path traversal. Returns None if no logs directory is configured."""
    log_dir = get_log_dir()
    if not log_dir:
        return None
    base = os.path.abspath(log_dir)
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        abort(400, "Invalid filename")
    return target


def log_path_for(conf_filename):
    """Path of conf_filename's log file, or None if unconfigured -- this
    app's own view; not necessarily where Caddy writes, see caddy_log_path_for()."""
    if not conf_filename:
        return None
    return safe_log_path(block_base_name(conf_filename) + ".log")


def caddy_log_path_for(conf_filename):
    """Path Caddy itself writes conf_filename's access log to, baked into
    the `output file` directive -- overridable in Settings > Logging."""
    if not conf_filename:
        return None
    log_dir = get_caddy_log_output_dir()
    if not log_dir:
        return None
    return os.path.join(os.path.abspath(log_dir), block_base_name(conf_filename) + ".log")


def delete_log_file(conf_filename):
    path = log_path_for(conf_filename)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def rename_log_file(old_conf_filename, new_conf_filename):
    """Move an existing log file to match a renamed block, alongside the
    .conf/.metadata rename that happens when the primary site address changes."""
    old_path = log_path_for(old_conf_filename)
    new_path = log_path_for(new_conf_filename)
    if not old_path or not new_path or old_path == new_path or not os.path.isfile(old_path):
        return
    try:
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.rename(old_path, new_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Metadata read/write
# ---------------------------------------------------------------------------

def write_metadata(conf_filename, conf_path, meta):
    """Persist metadata stamped with the .conf's mtime/size for cache
    validity. created_ts is set once and carried forward untouched after that."""
    try:
        st = os.stat(conf_path)
    except OSError:
        return
    existing_created = None
    meta_file = meta_path_for(conf_filename)
    if os.path.isfile(meta_file):
        try:
            with open(meta_file) as f:
                existing_created = json.load(f).get("created_ts")
        except (OSError, ValueError):
            pass
    meta = {
        **meta,
        "source_mtime": st.st_mtime,
        "source_size": st.st_size,
        "created_ts": meta.get("created_ts") or existing_created or st.st_ctime,
    }
    try:
        os.makedirs(metadata_dir(), exist_ok=True)
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)
    except OSError:
        pass


def read_metadata(conf_filename, conf_path):
    """The cached sidecar if fresh, otherwise a fallback .conf parse
    (which also refreshes the cache)."""
    try:
        st = os.stat(conf_path)
    except OSError:
        return {"type": "custom", "site_addresses": []}

    meta_file = meta_path_for(conf_filename)
    if os.path.isfile(meta_file):
        try:
            with open(meta_file) as f:
                cached = json.load(f)
            if cached.get("source_mtime") == st.st_mtime and cached.get("source_size") == st.st_size:
                # Migrate pre-rename sidecars (hosts -> site_addresses) transparently.
                if "site_addresses" not in cached and "hosts" in cached:
                    cached["site_addresses"] = cached.pop("hosts")
                # Backfill the Site Blocks table snippet for custom sidecars saved before it existed.
                if cached.get("type") == "custom" and "snippet" not in cached:
                    try:
                        with open(conf_path) as f:
                            cached["snippet"] = custom_block_preview(extract_body(f.read()))
                        write_metadata(conf_filename, conf_path, cached)
                    except OSError:
                        cached["snippet"] = ""
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


def cleanup_orphaned_metadata():
    """Remove sidecars whose .conf was renamed/deleted directly on disk.
    Runs as part of list_blocks(), self-healing on every page load."""
    mdir = metadata_dir()
    if not os.path.isdir(mdir):
        return
    conf_dir = get_conf_dir()
    for meta_file in glob.glob(os.path.join(mdir, "*.json")):
        stem = os.path.basename(meta_file)[: -len(".json")]
        conf_exists = os.path.isfile(os.path.join(conf_dir, stem + ".conf")) or \
            os.path.isfile(os.path.join(conf_dir, stem + ".conf.disabled"))
        if not conf_exists:
            try:
                os.remove(meta_file)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def _conf_paths():
    """Every .conf/.conf.disabled file path in the caddy dir, or [] if
    that directory doesn't exist yet."""
    conf_dir = get_conf_dir()
    if not os.path.isdir(conf_dir):
        return []
    return glob.glob(os.path.join(conf_dir, "*.conf")) + \
        glob.glob(os.path.join(conf_dir, "*.conf.disabled"))


def refresh_all_metadata():
    """Clean up orphaned sidecars and refresh every block's metadata.
    Called once at login so changes made outside the app are already reflected."""
    cleanup_orphaned_metadata()
    for path in _conf_paths():
        read_metadata(os.path.basename(path), path)


def list_blocks():
    cleanup_orphaned_metadata()
    paths = _conf_paths()

    blocks = []
    for path in paths:
        fname = os.path.basename(path)
        disabled = fname.endswith(".disabled")
        fdate = datetime.fromtimestamp(os.path.getmtime(path))
        meta = read_metadata(fname, path)
        block_type = meta.get("type", "custom")
        # Falls back to ctime for a hand-added file never through write_metadata yet.
        created_ts = meta.get("created_ts") or os.path.getctime(path)
        cdate = datetime.fromtimestamp(created_ts)

        if block_type in ("reverse_proxy", "redirect"):
            upstream_sort = meta.get("target", "")
        elif block_type == "load_balancer":
            upstream_sort = f"{len(meta.get('upstreams', []))} upstreams"
        elif block_type == "static_site":
            upstream_sort = meta.get("path", "")
        else:
            upstream_sort = "custom"

        blocks.append({
            "filename": fname,
            "disabled": disabled,
            "type": block_type,
            "site_addresses": meta.get("site_addresses", []),
            "scheme": meta.get("scheme", ""),
            "host": meta.get("host", ""),
            "port": meta.get("port", ""),
            "target": meta.get("target", ""),
            "redirect_code": meta.get("redirect_code", ""),
            "upstreams": meta.get("upstreams", []),
            "lb_policy": meta.get("lb_policy", ""),
            "path": meta.get("path", ""),
            "encode": meta.get("encode", []),
            "custom_snippet": meta.get("snippet", ""),
            "browse": meta.get("browse", False),
            "index": meta.get("index", ""),
            "hide": meta.get("hide", ""),
            "log_enabled": meta.get("log_enabled", False),
            "updated": fdate.strftime("%d/%m/%Y %I:%M%p"),
            "updated_ts": os.path.getmtime(path),
            "created": cdate.strftime("%d/%m/%Y %I:%M%p"),
            "created_ts": created_ts,
            "upstream_sort": upstream_sort,
        })
    blocks.sort(key=lambda b: b["filename"].lower())
    return blocks


# ---------------------------------------------------------------------------
# Filename management
# ---------------------------------------------------------------------------

def unique_filename(base):
    conf_dir = get_conf_dir()
    candidate = f"{base}.conf"
    i = 2
    while os.path.exists(os.path.join(conf_dir, candidate)) or \
            os.path.exists(os.path.join(conf_dir, candidate + ".disabled")):
        candidate = f"{base}-{i}.conf"
        i += 1
    return candidate


def rename_block_if_first_site_address_changed(filename, path, old_site_addresses, new_site_addresses):
    """Rename the .conf and sidecar to match if the first (filename-defining)
    site address changed. Returns the filename/path to use from here on."""
    old_first = old_site_addresses[0] if old_site_addresses else None
    new_first = new_site_addresses[0] if new_site_addresses else None
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
        # Content/metadata are already saved under the old name; keep it rather than lose the edit.
        return filename, path


def set_block_disabled(filename, path, disabled):
    """Add/remove the .disabled suffix on a block's .conf and sidecar to
    match, a no-op if already matching. Returns the filename/path to use from here on."""
    if filename.endswith(".disabled") == disabled:
        return filename, path

    new_filename = filename + ".disabled" if disabled else filename[: -len(".disabled")]
    try:
        new_path = safe_path(new_filename)
        os.rename(path, new_path)
        old_meta_path = meta_path_for(filename)
        if os.path.isfile(old_meta_path):
            os.rename(old_meta_path, meta_path_for(new_filename))
        return new_filename, new_path
    except OSError:
        return filename, path


# ---------------------------------------------------------------------------
# Form parsing -- shared by the new-block and edit-block routes
# ---------------------------------------------------------------------------

def parse_logging_fields(form):
    """Parse the Logging accordion's fields, shared by every block type.
    Falls back to INFO/json for invalid choices; rotation fields are left as-is, validated by the caller."""
    log_enabled = form.get("log_enabled") == "1"
    log_level = form.get("log_level", "INFO").strip().upper()
    if log_level not in LOG_LEVELS:
        log_level = "INFO"
    log_format = form.get("log_format", "json").strip().lower()
    if log_format not in LOG_FORMATS:
        log_format = "json"
    roll_size = form.get("log_roll_size", "").strip()
    roll_keep = form.get("log_roll_keep", "").strip()
    roll_keep_for = form.get("log_roll_keep_for", "").strip()
    return log_enabled, log_level, log_format, roll_size, roll_keep, roll_keep_for


def build_block_from_form(block_type, form, log_filename_hint=None):
    """Parse+validate submitted block-form fields, rendering Caddyfile content.
    Returns (content, meta, error); meta is populated even on error so a rejected form can re-render it."""
    site_addresses = site_addresses_from_textarea(form.get("site_addresses", ""))
    meta = {"site_addresses": site_addresses}
    content = None
    error = None

    log_enabled, log_level, log_format, roll_size, roll_keep, roll_keep_for = parse_logging_fields(form)
    meta.update(log_enabled=log_enabled, log_level=log_level, log_format=log_format,
                log_roll_size=roll_size, log_roll_keep=roll_keep, log_roll_keep_for=roll_keep_for)

    log_lines = None
    log_error = None
    if log_enabled:
        if roll_keep and not (roll_keep.isdigit() and int(roll_keep) > 0):
            log_error = "Rotated files to keep must be a positive whole number."
        else:
            log_path = caddy_log_path_for(log_filename_hint)
            if not log_path:
                log_error = "Set a logs directory in Settings before enabling logging."
            else:
                log_lines = render_log_block(log_path, log_level, log_format, roll_size, roll_keep, roll_keep_for)

    if block_type == "reverse_proxy":
        scheme = form.get("scheme", "http").strip() or "http"
        host = form.get("host", "").strip()
        port = form.get("port", "").strip()
        extra = form.get("extra", "").strip()
        insecure_skip_verify = scheme == "https" and form.get("insecure_skip_verify") == "1"
        meta.update(scheme=scheme, host=host, port=port, extra=extra,
                    insecure_skip_verify=insecure_skip_verify)
        if not site_addresses:
            error = "At least one site address is required."
        elif not host:
            error = "Upstream host is required."
        else:
            target = join_target(scheme, host, port)
            content = render_reverse_proxy(site_address_header(site_addresses), target, extra,
                                            insecure_skip_verify, log_lines)
            meta.update(type="reverse_proxy", target=target)

    elif block_type == "load_balancer":
        upstreams = [u.strip() for u in form.get("upstreams", "").splitlines() if u.strip()]
        lb_policy = form.get("lb_policy", "").strip()
        extra = form.get("extra", "").strip()
        lb_retries = form.get("lb_retries", "").strip()
        lb_try_duration = form.get("lb_try_duration", "").strip()
        lb_try_interval = form.get("lb_try_interval", "").strip()
        health_uri = form.get("health_uri", "").strip()
        # Blank means "use Caddy's own GET default" rather than a redundant explicit line.
        health_method = form.get("health_method", "").strip().upper()
        health_interval = form.get("health_interval", "").strip()
        health_timeout = form.get("health_timeout", "").strip()
        health_status = form.get("health_status", "").strip()
        health_passes = form.get("health_passes", "").strip()
        health_fails = form.get("health_fails", "").strip()
        # Skip-verify is only honored server-side when upstreams are actually https.
        lb_scheme = split_target(upstreams[0])[0] if upstreams else ""
        insecure_skip_verify = lb_scheme == "https" and form.get("insecure_skip_verify") == "1"
        meta.update(upstreams=upstreams, lb_policy=lb_policy, extra=extra,
                    lb_retries=lb_retries, lb_try_duration=lb_try_duration, lb_try_interval=lb_try_interval,
                    health_uri=health_uri, health_method=health_method, health_interval=health_interval,
                    health_timeout=health_timeout, health_status=health_status, health_passes=health_passes,
                    health_fails=health_fails, insecure_skip_verify=insecure_skip_verify)
        if not site_addresses:
            error = "At least one site address is required."
        elif len(upstreams) < 2:
            error = "At least two upstreams are required."
        else:
            content = render_load_balancer(site_address_header(site_addresses), upstreams, lb_policy, extra, log_lines,
                                            lb_retries, lb_try_duration, lb_try_interval,
                                            health_uri, health_method, health_interval, health_timeout, health_status,
                                            health_passes, health_fails, insecure_skip_verify)
            meta.update(type="load_balancer")

    elif block_type == "redirect":
        target = form.get("target", "").strip()
        redirect_code = form.get("redirect_code", "").strip() or "301"
        meta.update(target=target, redirect_code=redirect_code)
        if not site_addresses:
            error = "At least one site address is required."
        elif not target:
            error = "Redirect target is required."
        else:
            content = render_redirect(site_address_header(site_addresses), target, redirect_code, log_lines)
            meta.update(type="redirect")

    elif block_type == "static_site":
        path = form.get("path", "").strip()
        encodings = [e for e in form.getlist("encode") if e in ENCODE_FORMATS]
        browse = form.get("browse") == "1"
        index = form.get("index", "").strip()
        hide = form.get("hide", "").strip()
        meta.update(path=path, encode=encodings, browse=browse, index=index, hide=hide)
        if not site_addresses:
            error = "At least one site address is required."
        elif not path:
            error = "File path is required."
        else:
            content = render_static_site(site_address_header(site_addresses), path, encodings, browse, index,
                                          hide, log_lines)
            meta.update(type="static_site")

    else:  # custom
        raw = form.get("raw_content", "").strip()
        if not site_addresses:
            error = "At least one site address is required."
        elif not raw:
            error = "Block content is required."
        else:
            content = render_custom(site_address_header(site_addresses), raw, log_lines)
            meta.update(type="custom", snippet=custom_block_preview(raw))

    if not error:
        error = log_error

    return content, meta, error
