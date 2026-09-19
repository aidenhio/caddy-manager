"""Pure Caddyfile string building & parsing -- string in, string out, no
filesystem or Flask, so it's easy to reason about and test in isolation."""
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
LOG_START_RE = re.compile(r"^\s*log(?:\s+\S+)?\s*\{", re.MULTILINE)
LOG_FORMAT_RE = re.compile(r"^\s*format\s+(\S+)", re.MULTILINE)
LOG_LEVEL_RE = re.compile(r"^\s*level\s+(\S+)", re.MULTILINE)
ROLL_SIZE_RE = re.compile(r"^\s*roll_size\s+(\S+)", re.MULTILINE)
ROLL_KEEP_RE = re.compile(r"^\s*roll_keep\s+(\d+)\b", re.MULTILINE)
ROLL_KEEP_FOR_RE = re.compile(r"^\s*roll_keep_for\s+(\S+)", re.MULTILINE)

# Encode formats offered in the Static Site form; also used to validate
# a submitted form or a hand-edited .conf's `encode` line.
ENCODE_FORMATS = ("gzip", "zstd", "br")

# Log levels/formats offered in the Logging accordion; also used to
# validate a submitted form or hand-edited `log` block.
LOG_LEVELS = ("INFO", "ERROR")
LOG_FORMATS = ("json", "console")


def find_braced_block(content, start_match):
    """Text up to the matching '}' for a match ending after an opening '{',
    brace-depth aware (None if unbalanced) -- needed since `log` blocks can nest."""
    depth = 1
    i = start_match.end()
    start = i
    while i < len(content) and depth > 0:
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
        i += 1
    return content[start:i - 1] if depth == 0 else None


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
    """Clean, dedupe (first occurrence wins) and sort site addresses --
    letter-leading addresses sort before digit-leading ones."""
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


def render_log_block(log_path, level="INFO", format="json", roll_size="", roll_keep="", roll_keep_for=""):
    """Lines for a `log { ... }` directive, prepended to another render_*
    function's body. Setting any roll_* option nests `output file` into a block."""
    path = f'"{log_path}"' if log_path and (" " in log_path or "\t" in log_path) else log_path
    roll_size = (roll_size or "").strip()
    roll_keep = str(roll_keep or "").strip()
    roll_keep_for = (roll_keep_for or "").strip()

    roll_lines = []
    if roll_size:
        roll_lines.append(f"roll_size {roll_size}")
    if roll_keep:
        roll_lines.append(f"roll_keep {roll_keep}")
    if roll_keep_for:
        roll_lines.append(f"roll_keep_for {roll_keep_for}")

    lines = ["log {"]
    if roll_lines:
        lines.append(f"    output file {path} {{")
        lines += [f"        {line}" for line in roll_lines]
        lines.append("    }")
    else:
        lines.append(f"    output file {path}")
    lines.append(f"    format {format or 'json'}")
    lines.append(f"    level {level or 'INFO'}")
    lines.append("}")
    return lines


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
    """file_server is always present -- a bare line if none of
    browse/index/hide are set, otherwise a `file_server { ... }` block."""
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


def render_load_balancer(site_header, upstreams, lb_policy="", extra_text="", log_lines=None,
                          lb_retries="", lb_try_duration="", lb_try_interval="",
                          health_uri="", health_method="", health_interval="", health_timeout="",
                          health_status="", health_passes="", health_fails="", insecure_skip_verify=False):
    """Retry/health-check params are optional `reverse_proxy` sub-directives,
    rendered only when set. Blank `health_method` means Caddy's own GET default."""
    inner = [f"lb_policy {lb_policy}"] if lb_policy else []

    lb_retries = str(lb_retries or "").strip()
    lb_try_duration = (lb_try_duration or "").strip()
    lb_try_interval = (lb_try_interval or "").strip()
    if lb_retries:
        inner.append(f"lb_retries {lb_retries}")
    if lb_try_duration:
        inner.append(f"lb_try_duration {lb_try_duration}")
    if lb_try_interval:
        inner.append(f"lb_try_interval {lb_try_interval}")

    health_uri = (health_uri or "").strip()
    health_method = (health_method or "").strip().upper()
    health_interval = (health_interval or "").strip()
    health_timeout = (health_timeout or "").strip()
    health_status = (health_status or "").strip()
    health_passes = str(health_passes or "").strip()
    health_fails = str(health_fails or "").strip()
    if health_uri:
        inner.append(f"health_uri {health_uri}")
    if health_method:
        inner.append(f"health_method {health_method}")
    if health_interval:
        inner.append(f"health_interval {health_interval}")
    if health_timeout:
        inner.append(f"health_timeout {health_timeout}")
    if health_status:
        inner.append(f"health_status {health_status}")
    if health_passes:
        inner.append(f"health_passes {health_passes}")
    if health_fails:
        inner.append(f"health_fails {health_fails}")

    if insecure_skip_verify:
        inner += ["transport http {", "    tls_insecure_skip_verify", "}"]

    inner += extra_lines(extra_text)
    body = list(log_lines or [])
    body.append(f"reverse_proxy {' '.join(upstreams)} {{")
    body += [f"    {line}" for line in inner]
    body += ["}"]
    return render_domain_block(site_header, body)


def render_custom(site_header, body_text, log_lines=None):
    """Wrap opaque user-authored body text with the site header. Unlike the
    other render_* functions, a `log` block is stitched on directly, not via render_domain_block."""
    body = (body_text or "").rstrip("\n")
    prefix_lines = [f"    {line}" for line in (log_lines or [])]
    prefix = ("\n".join(prefix_lines) + "\n") if prefix_lines else ""
    inner = f"{prefix}{body}" if body else prefix.rstrip("\n")
    return f"{site_header} {{\n{inner}\n}}\n" if inner else f"{site_header} {{\n}}\n"


def extract_body(content):
    """Text between the first '{' and matching last '}' (inverse of
    render_custom), for prefilling the custom-block edit form."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return content.strip()
    return content[start + 1:end].strip("\n")


# ---------------------------------------------------------------------------
# Block parsing (Caddyfile text -> structured fields). Fallback only, for
# files this app didn't write -- see blocks.read_metadata.
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
    """Best-effort parse of a `log { ... }` block for the fallback parser.
    Unrecognized level/format falls back to defaults; roll_* settings pass through as-is."""
    start_match = LOG_START_RE.search(content)
    body = find_braced_block(content, start_match) if start_match else None
    if body is None:
        return {"log_enabled": False, "log_level": "INFO", "log_format": "json",
                "log_roll_size": "", "log_roll_keep": "", "log_roll_keep_for": ""}

    format_match = LOG_FORMAT_RE.search(body)
    level_match = LOG_LEVEL_RE.search(body)
    roll_size_match = ROLL_SIZE_RE.search(body)
    roll_keep_match = ROLL_KEEP_RE.search(body)
    roll_keep_for_match = ROLL_KEEP_FOR_RE.search(body)
    log_format = format_match.group(1) if format_match and format_match.group(1) in LOG_FORMATS else "json"
    log_level = level_match.group(1).upper() if level_match and level_match.group(1).upper() in LOG_LEVELS else "INFO"
    return {
        "log_enabled": True, "log_level": log_level, "log_format": log_format,
        "log_roll_size": roll_size_match.group(1) if roll_size_match else "",
        "log_roll_keep": roll_keep_match.group(1) if roll_keep_match else "",
        "log_roll_keep_for": roll_keep_for_match.group(1) if roll_keep_for_match else "",
    }


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
