"""Caddy admin API client -- currently just the one read used by the
Dashboard's "Current Requests" widget: GET /reverse_proxy/upstreams,
which Caddy's admin API exposes to introspect the live state of its
configured reverse-proxy upstreams
(https://caddyserver.com/docs/api#get-reverseproxyupstreams). Each item
in the returned array carries the upstream's dial `address`, its
currently in-flight `num_requests` (an active/live count, not a
cumulative historical total), and its `fails` count from passive health
checks.

This talks directly to Caddy's admin endpoint -- a separate, optional
integration from everything else this app manages -- so any failure
(Caddy not running, no admin API URL configured, host unreachable, an
unexpected response shape) is swallowed and surfaced as None rather
than raised: a dashboard widget shouldn't break the page just because
Caddy is briefly unreachable.

The stats computed here (upstream count, summed requests/fails) mirror
the approach community dashboard widgets for Caddy already take, e.g.
homepage's (https://github.com/gethomepage/homepage/tree/main/src/widgets/caddy),
which sums num_requests/fails across every upstream the same way.
"""
import json
import urllib.request
import urllib.error

from .configstore import get_caddy_admin_api_url

REQUEST_TIMEOUT_SECONDS = 3


def normalize_admin_api_url(raw_url):
    """A user-entered admin API address (e.g. "caddy.example.com:2019" or
    "https://caddy.example.com:2019") normalized to a base URL with a
    scheme and no trailing slash, or "" if nothing was given. Caddy's
    admin API listens on plain HTTP by default, so a bare host:port
    defaults to http://."""
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = f"http://{url}"
    return url


def fetch_reverse_proxy_upstreams():
    """GET {admin_api_url}/reverse_proxy/upstreams, returning the parsed
    JSON list of upstreams, or None if no admin API URL is configured, the
    request fails, or the response isn't the JSON array this endpoint is
    documented to return."""
    base_url = normalize_admin_api_url(get_caddy_admin_api_url())
    if not base_url:
        return None
    try:
        req = urllib.request.Request(
            f"{base_url}/reverse_proxy/upstreams", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return data if isinstance(data, list) else None


def upstream_stats():
    """Summary counts derived from the live /reverse_proxy/upstreams
    response, ready for the Dashboard's Current Requests widget (and any
    other upstream-derived widgets added later -- upstreams_total and
    failed_requests aren't shown yet but are computed here for that).
    Returns None -- rather than zeroed-out values -- when the API
    couldn't be reached at all, so the caller can tell "0 requests" apart
    from "not configured/unreachable"."""
    upstreams = fetch_reverse_proxy_upstreams()
    if upstreams is None:
        return None
    valid = [u for u in upstreams if isinstance(u, dict)]
    return {
        "upstreams_total": len(valid),
        "current_requests": sum((u.get("num_requests") or 0) for u in valid),
        "failed_requests": sum((u.get("fails") or 0) for u in valid),
    }
