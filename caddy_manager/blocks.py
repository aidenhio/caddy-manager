"""Block file & metadata management.

Every block gets a small sidecar metadata file (same base name as the
.conf, extension .json) living in a hidden .metadata subdirectory of the
caddy.d directory -- kept out of the way of Caddy's own `import *.conf`
and out of the way of the site blocks list. It holds the block's structured
fields plus the .conf's mtime/size at the time it was written. Listing a
directory is then just one JSON read per file -- the .conf itself is only
re-parsed with regex when a sidecar is missing or its stamped mtime/size no
longer matches the .conf on disk (i.e. it was created or hand-edited
outside the app). Blocks created/edited through this app's forms never
take that path at all: their metadata is written directly from the
submitted fields (see build_block_from_form below).
"""
import os
import glob
import json
from datetime import datetime

from flask import abort

from .configstore import get_conf_dir, get_log_dir
from .caddyfile import (
    site_addresses_from_textarea, site_address_header, slugify,
    join_target, parse_conf_content,
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
    """The .conf filename with its .disabled and .conf suffixes stripped
    -- the stem shared by a block's .conf, its .metadata/*.json sidecar,
    and (when logging is enabled) its logs_dir/*.log file."""
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
    """Absolute path of the log file that would correspond to a given
    .conf filename (same base name as its .conf/.metadata sidecar, with a
    .log extension), or None if no logs directory is configured."""
    if not conf_filename:
        return None
    return safe_log_path(block_base_name(conf_filename) + ".log")


def delete_log_file(conf_filename):
    path = log_path_for(conf_filename)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def rename_log_file(old_conf_filename, new_conf_filename):
    """If a log file exists for the old filename, move it to match the
    new one -- called alongside the .conf/.metadata rename that happens
    when a block's primary site address changes."""
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
    """Persist metadata for a block, stamped with the .conf's current
    mtime/size so future reads know whether the cache is still valid.
    Also stamps/preserves a created_ts: the first time a sidecar is ever
    written for a filename it's set from the .conf's own ctime (a close
    enough proxy for creation time, and exactly right for a block just
    created through the app, since this always runs immediately after
    the .conf itself is written) -- every write after that just carries
    the existing sidecar's created_ts forward untouched, so editing a
    block never resets when it was "created"."""
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
    """Load metadata for a block: the cached sidecar if it's still fresh,
    otherwise a fallback parse of the .conf content (which also refreshes
    the cache so the next read is cheap again)."""
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
                # Migrate sidecars written before the hosts -> site_addresses
                # rename, so pre-existing installs upgrade transparently.
                if "site_addresses" not in cached and "hosts" in cached:
                    cached["site_addresses"] = cached.pop("hosts")
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
    """Remove metadata sidecars that no longer have a matching .conf file.
    Renames/deletes made through the app already keep the sidecar in sync
    (see rename_block_if_first_site_address_changed / delete_block), but a
    .conf renamed or deleted directly on disk -- which this app is explicitly
    designed to allow -- leaves its .json behind with nothing to key off
    of. Runs as part of list_blocks() so it self-heals on every page load,
    the same way read_metadata already self-heals stale caches."""
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
    """Bring every block's metadata sidecar up to date: clean up any
    orphaned sidecars, then read (and, via read_metadata's own self-heal,
    re-parse/re-write if stale) every .conf/.conf.disabled file's
    metadata. Called once at login so anything changed outside the app
    since the last visit -- a hand-edited block, or a .conf dropped in,
    renamed, or removed directly -- is already reflected before the user
    reaches the site blocks list or a preview page, rather than only
    self-healing lazily, file by file, as each happens to be viewed."""
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
            "browse": meta.get("browse", False),
            "index": meta.get("index", ""),
            "hide": meta.get("hide", ""),
            "log_enabled": meta.get("log_enabled", False),
            "updated": fdate.strftime("%d/%m/%Y %I:%M%p"),
            "updated_ts": os.path.getmtime(path),
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
    """If the sorted, first (i.e. filename-defining) site address changed,
    rename the .conf (and its metadata sidecar) to match -- preserving the
    .disabled suffix if the block is currently disabled. Returns the
    filename/path to use from here on (unchanged if no rename happened)."""
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
        # Content/metadata are already saved under the old name -- if the
        # rename itself fails, just keep the old filename rather than
        # losing the edit.
        return filename, path


# ---------------------------------------------------------------------------
# Form parsing -- shared by the new-block and edit-block routes
# ---------------------------------------------------------------------------

def parse_logging_fields(form):
    """Parse+validate the Logging accordion's fields, shared by every
    block type. Falls back to INFO/console for anything missing or not
    one of the choices the accordion itself offers."""
    log_enabled = form.get("log_enabled") == "1"
    log_level = form.get("log_level", "INFO").strip().upper()
    if log_level not in LOG_LEVELS:
        log_level = "INFO"
    log_format = form.get("log_format", "console").strip().lower()
    if log_format not in LOG_FORMATS:
        log_format = "console"
    return log_enabled, log_level, log_format


def build_block_from_form(block_type, form, log_filename_hint=None):
    """Parse and validate submitted block-form fields for `block_type`,
    rendering the Caddyfile block content. Returns (content, meta, error):
    `content` is the rendered block text (None if invalid), `meta` is the
    metadata dict ready for write_metadata() -- populated with whatever the
    user submitted even when `error` is set, so the form can re-render the
    attempted values.

    `log_filename_hint` is the .conf filename the log block's `output
    file` path should be derived from (the same base name, in the
    configured logs directory) -- the eventual filename for a new block,
    or the block's current filename when editing. It's a hint rather than
    something this function resolves itself because a new block's
    filename isn't decided until after this call returns (it depends on
    the normalized site_addresses this function produces); the caller is
    expected to pass the filename it intends to use.

    This is the one place the five block-type shapes are described; both
    new_block() and edit_block() call it identically, since every field a
    saved block needs is always resubmitted in full on every save (nothing
    from a previous version needs to be separately preserved/merged in)."""
    site_addresses = site_addresses_from_textarea(form.get("site_addresses", ""))
    meta = {"site_addresses": site_addresses}
    content = None
    error = None

    log_enabled, log_level, log_format = parse_logging_fields(form)
    meta.update(log_enabled=log_enabled, log_level=log_level, log_format=log_format)

    log_lines = None
    log_error = None
    if log_enabled:
        log_path = log_path_for(log_filename_hint)
        if not log_path:
            log_error = "Set a logs directory in Settings before enabling logging."
        else:
            log_lines = render_log_block(log_path, log_level, log_format)

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
        meta.update(upstreams=upstreams, lb_policy=lb_policy, extra=extra)
        if not site_addresses:
            error = "At least one site address is required."
        elif len(upstreams) < 2:
            error = "At least two upstreams are required."
        else:
            content = render_load_balancer(site_address_header(site_addresses), upstreams, lb_policy, extra, log_lines)
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
            meta.update(type="custom")

    if not error:
        error = log_error

    return content, meta, error
