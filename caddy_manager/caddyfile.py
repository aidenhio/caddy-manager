"""Pure Caddyfile string building & parsing.

Nothing in this module touches the filesystem or Flask -- it's just string
in, string out, which makes it easy to reason about (and test) in
isolation from the metadata/routing layers built on top of it in blocks.py.
"""
import re

REVERSE_PROXY_RE = re.compile(r"^\s*reverse_proxy\s+([^\n{]+?)\s*\{?\s*$", re.MULTILINE)
LB_POLICY_RE = re.compile(r"^\s*lb_policy\s+(\S+)", re.MULTILINE)
REDIR_RE = re.compile(r"^\s*redir(?:ect)?\s+(\S+)(?:\s+(\d{3}))?", re.MULTILINE)
ROOT_RE = re.compile(r"^\s*root\s+(?:\*\s+)?(\S+)", re.MULTILINE)
ENCODE_RE = re.compile(r"^\s*encode\s+(.+)$", re.MULTILINE)
FILE_SERVER_BLOCK_RE = re.compile(r"file_server\s*\{(.*?)\n\s*\}", re.DOTALL)
BROWSE_RE = re.compile(r"^\s*browse\b", re.MULTILINE)
INDEX_RE = re.compile(r"^\s*index\s+(.+)$", re.MULTILINE)
HIDE_RE = re.compile(r"^\s*hide\s+(.+)$", re.MULTILINE)
LOG_BLOCK_RE = re.compile(r"^\s*log(?:\s+\S+)?\s*\{(.*?)\n\s*\}", re.MULTILINE | re.DOTALL)
LOG_FORMAT_RE = re.compile(r"^\s*format\s+(\S+)", re.MULTILINE)
LOG_LEVEL_RE = re.compile(r"^\s*level\s+(\S+)", re.MULTILINE)

# The encode formats offered in the Static Site form, in the order they're
# presented -- also used to filter/validate whatever a submitted form or a
# hand-edited .conf's `encode` line actually contains.
ENCODE_FORMATS = ("gzip", "zstd", "br")

# The log levels/formats offered in the Logging accordion of every block
# type, in the order they're presented -- also used to filter/validate
# whatever a submitted form or a hand-edited .conf's `log` block actually
# contains. Caddy supports more of each (e.g. DEBUG/WARN/PANIC/FATAL
# levels), but the form intentionally only exposes the two most commonly
# useful choices for a reverse-proxy-style access log.
LOG_LEVELS = ("INFO", "ERROR")
LOG_FORMATS = ("console", "json")


# ---------------------------------------------------------------------------
# Upstream/target strings (e.g. "https://127.0.0.1:8080")
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Site addresses (the domain(s) a block matches on)
# ---------------------------------------------------------------------------

def normalize_site_addresses(raw_site_addresses):
    """Clean, dedupe (first occurrence wins) and sort a list of site
    addresses: addresses starting with a letter sort before addresses
    starting with a digit, alphabetically within each group -- e.g.
    api.example.com, app.example.com, 2.example.com."""
    seen = set()
    site_addresses = []
    for h in raw_site_addresses:
        h = (h or "").strip()
        if h and h not in seen:
            seen.add(h)
            site_addresses.append(h)
    site_addresses.sort(key=lambda h: (h[:1].isdigit(), h.lower()))
    return site_addresses


def site_addresses_from_textarea(text):
    """Parse a one-site-address-per-line textarea into a normalized list."""
    return normalize_site_addresses((text or "").splitlines())


def site_address_header(site_addresses):
    """Caddyfile site-address line for one or more site addresses."""
    return ", ".join(site_addresses)


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


# ---------------------------------------------------------------------------
# Block rendering (structured fields -> Caddyfile text)
# ---------------------------------------------------------------------------

def extra_lines(extra_text):
    return [line.strip() for line in (extra_text or "").splitlines() if line.strip()]


def render_domain_block(site_header, body_lines):
    lines = [f"{site_header} {{"]
    lines.extend(f"    {line}" for line in body_lines)
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_log_block(log_path, level="INFO", format="console"):
    """Lines for a `log { ... }` directive that writes this block's access
    log to `log_path` -- meant to be prepended to another render_*
    function's body list (each line here gets the same single level of
    indent render_domain_block already applies to every body line).
    Level and format are always stated explicitly, even when they're the
    Caddy default, since this is meant to be a readable, hand-editable
    admin tool rather than the most terse possible config."""
    path = f'"{log_path}"' if log_path and (" " in log_path or "\t" in log_path) else log_path
    return [
        "log {",
        f"    output file {path}",
        f"    format {format or 'console'}",
        f"    level {level or 'INFO'}",
        "}",
    ]


def render_reverse_proxy(site_header, target, extra_text="", insecure_skip_verify=False, log_lines=None):
    body = list(log_lines or [])
    body.append(f"reverse_proxy {target}")
    if insecure_skip_verify:
        body += ["transport http {", "    tls_insecure_skip_verify", "}"]
    body += extra_lines(extra_text)
    return render_domain_block(site_header, body)


def render_redirect(site_header, target, redirect_code="", log_lines=None):
    redirect_code = (redirect_code or "").strip()
    directive = f"redir {target} {redirect_code}" if redirect_code else f"redir {target}"
    body = list(log_lines or [])
    body.append(directive)
    return render_domain_block(site_header, body)


def render_static_site(site_header, path, encodings=None, browse=False, index="", hide="", log_lines=None):
    """file_server is always present for this block type (a static site
    with no file_server wouldn't actually serve anything) -- rendered as a
    bare `file_server` line when none of browse/index/hide are set, or as
    a `file_server { ... }` block when any of them are."""
    encodings = [e for e in (encodings or []) if e in ENCODE_FORMATS]
    index = (index or "").strip()
    hide = (hide or "").strip()

    body = list(log_lines or [])
    body.append(f"root * {path}")
    if encodings:
        body.append("encode " + " ".join(encodings))

    file_server_lines = []
    if hide:
        file_server_lines.append(f"hide {hide}")
    if index:
        file_server_lines.append(f"index {index}")
    if browse:
        file_server_lines.append("browse")

    if file_server_lines:
        body.append("file_server {")
        body += [f"    {line}" for line in file_server_lines]
        body.append("}")
    else:
        body.append("file_server")

    return render_domain_block(site_header, body)


def render_load_balancer(site_header, upstreams, lb_policy="", extra_text="", log_lines=None):
    inner = [f"lb_policy {lb_policy}"] if lb_policy else []
    inner += extra_lines(extra_text)
    body = list(log_lines or [])
    body.append(f"reverse_proxy {' '.join(upstreams)} {{")
    body += [f"    {line}" for line in inner]
    body += ["}"]
    return render_domain_block(site_header, body)


def render_custom(site_header, body_text, log_lines=None):
    """Wrap a user-authored body (whatever's between the braces) with the
    site header, which is always derived from the Site Address field -- the
    user only ever writes/edits the inside of the block, never the site
    address line. Unlike the other render_* functions, the body here isn't
    a list of directive lines this module controls -- it's opaque
    user-authored text -- so a `log` block, if enabled, is stitched onto
    the front of it directly rather than passed to render_domain_block."""
    body = (body_text or "").rstrip("\n")
    prefix_lines = [f"    {line}" for line in (log_lines or [])]
    prefix = ("\n".join(prefix_lines) + "\n") if prefix_lines else ""
    inner = f"{prefix}{body}" if body else prefix.rstrip("\n")
    return f"{site_header} {{\n{inner}\n}}\n" if inner else f"{site_header} {{\n}}\n"


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
# Block parsing (Caddyfile text -> structured fields)
#
# Only used as a fallback for files this app didn't write itself (or that
# were hand-edited since) -- app-created blocks skip this entirely because
# their metadata is written straight from the form. See blocks.read_metadata.
# ---------------------------------------------------------------------------

def extract_site_addresses(content):
    """Pull the site-address line out of a raw block ('addr1, addr2 {')
    and return it as a normalized, sorted site-address list."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and "{" in stripped and not stripped.startswith("#"):
            header = stripped.split("{")[0].strip()
            return normalize_site_addresses(re.split(r"[,\s]+", header))
    return []


def extract_logging(content):
    """Best-effort parse of a `log { ... }` block out of a raw Caddy block,
    for the structured (non-custom) block types' fallback parser -- a
    `log` block added by hand between app saves should still show up,
    pre-filled, in the Logging accordion next time the block is opened.
    Only recognizes the level/format combinations the Logging accordion
    itself can produce (see LOG_LEVELS/LOG_FORMATS); anything else falls
    back to the form's defaults rather than being left blank."""
    match = LOG_BLOCK_RE.search(content)
    if not match:
        return {"log_enabled": False, "log_level": "INFO", "log_format": "console"}

    body = match.group(1)
    format_match = LOG_FORMAT_RE.search(body)
    level_match = LOG_LEVEL_RE.search(body)
    log_format = format_match.group(1) if format_match and format_match.group(1) in LOG_FORMATS else "console"
    log_level = level_match.group(1).upper() if level_match and level_match.group(1).upper() in LOG_LEVELS else "INFO"
    return {"log_enabled": True, "log_level": log_level, "log_format": log_format}


def parse_conf_content(content):
    """Best-effort structured parse of a raw Caddy block."""
    site_addresses = extract_site_addresses(content)
    rp_match = REVERSE_PROXY_RE.search(content)
    lb_match = LB_POLICY_RE.search(content)
    logging_fields = extract_logging(content)

    if rp_match and lb_match:
        upstreams = rp_match.group(1).split()
        return {"type": "load_balancer", "site_addresses": site_addresses, "upstreams": upstreams,
                "lb_policy": lb_match.group(1), "extra": "", **logging_fields}

    if rp_match:
        tokens = rp_match.group(1).split()
        target = tokens[0] if tokens else ""
        scheme, host, port = split_target(target)
        return {"type": "reverse_proxy", "site_addresses": site_addresses, "target": target,
                "scheme": scheme, "host": host, "port": port, "extra": "", **logging_fields}

    redir_match = REDIR_RE.search(content)
    if redir_match:
        return {"type": "redirect", "site_addresses": site_addresses, "target": redir_match.group(1),
                "redirect_code": redir_match.group(2) or "", **logging_fields}

    root_match = ROOT_RE.search(content)
    if root_match:
        encode_match = ENCODE_RE.search(content)
        encodings = [e for e in (encode_match.group(1).split() if encode_match else []) if e in ENCODE_FORMATS]

        fs_block_match = FILE_SERVER_BLOCK_RE.search(content)
        fs_body = fs_block_match.group(1) if fs_block_match else ""
        index_match = INDEX_RE.search(fs_body)
        hide_match = HIDE_RE.search(fs_body)

        return {"type": "static_site", "site_addresses": site_addresses, "path": root_match.group(1),
                "encode": encodings, "browse": bool(BROWSE_RE.search(fs_body)),
                "index": index_match.group(1).strip() if index_match else "",
                "hide": hide_match.group(1).strip() if hide_match else "", **logging_fields}

    return {"type": "custom", "site_addresses": site_addresses}
