"""Pure Caddyfile string building & parsing.

Nothing in this module touches the filesystem or Flask -- it's just string
in, string out, which makes it easy to reason about (and test) in
isolation from the metadata/routing layers built on top of it in blocks.py.
"""
import re

REVERSE_PROXY_RE = re.compile(r"^\s*reverse_proxy\s+([^\n{]+?)\s*\{?\s*$", re.MULTILINE)
LB_POLICY_RE = re.compile(r"^\s*lb_policy\s+(\S+)", re.MULTILINE)
REDIR_RE = re.compile(r"^\s*redir(?:ect)?\s+(\S+)(?:\s+(\d{3}))?", re.MULTILINE)


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
    site header, which is always derived from the Site Address field -- the
    user only ever writes/edits the inside of the block, never the site
    address line."""
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


def parse_conf_content(content):
    """Best-effort structured parse of a raw Caddy block."""
    site_addresses = extract_site_addresses(content)
    rp_match = REVERSE_PROXY_RE.search(content)
    lb_match = LB_POLICY_RE.search(content)

    if rp_match and lb_match:
        upstreams = rp_match.group(1).split()
        return {"type": "load_balancer", "site_addresses": site_addresses, "upstreams": upstreams,
                "lb_policy": lb_match.group(1), "extra": ""}

    if rp_match:
        tokens = rp_match.group(1).split()
        target = tokens[0] if tokens else ""
        scheme, host, port = split_target(target)
        return {"type": "reverse_proxy", "site_addresses": site_addresses, "target": target,
                "scheme": scheme, "host": host, "port": port, "extra": ""}

    redir_match = REDIR_RE.search(content)
    if redir_match:
        return {"type": "redirect", "site_addresses": site_addresses, "target": redir_match.group(1),
                "redirect_code": redir_match.group(2) or ""}

    return {"type": "custom", "site_addresses": site_addresses}
