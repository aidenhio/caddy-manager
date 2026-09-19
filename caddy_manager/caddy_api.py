"""Caddy admin API client -- GET /reverse_proxy/upstreams for the Dashboard's
widgets. Any failure returns None rather than raising, so a widget degrades quietly."""
import json
import urllib.request
import urllib.error

from .configstore import get_caddy_admin_api_url

REQUEST_TIMEOUT_SECONDS = 3


def normalize_admin_api_url(raw_url):
    """Normalize a user-entered admin API address to a base URL with a scheme
    and no trailing slash ("" if blank). Bare host:port defaults to http://."""
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = f"http://{url}"
    return url


def fetch_reverse_proxy_upstreams():
    """GET {admin_api_url}/reverse_proxy/upstreams; returns the parsed JSON
    list, or None if unconfigured, unreachable, or not a JSON array."""
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
    """Summary counts for the Dashboard widgets. Returns None (not zeros)
    when unreachable, so "0 requests" is distinguishable from "unconfigured"."""
    upstreams = fetch_reverse_proxy_upstreams()
    if upstreams is None:
        return None
    valid = [u for u in upstreams if isinstance(u, dict)]
    requested_addresses = {
        u.get("address") for u in valid if (u.get("num_requests") or 0) > 0
    }
    return {
        "upstreams_total": len(valid),
        "current_requests": sum((u.get("num_requests") or 0) for u in valid),
        "failed_requests": sum((u.get("fails") or 0) for u in valid),
        "unique_requested_sites": len(requested_addresses),
    }
