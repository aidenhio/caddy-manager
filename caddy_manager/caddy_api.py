"""Caddy admin API client -- GET /reverse_proxy/upstreams for the Dashboard's
widgets, from the VIP URL or a running server. Failures return None, never raise."""
import json
import urllib.request
import urllib.error

from .configstore import MAX_CADDY_SERVERS, get_caddy_servers, get_caddy_vip_api_url
from .server_monitor import admin_api_base_url, caddy_status

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


def admin_api_candidates():
    """Base URLs to try for Dashboard stats, in order: just the VIP URL when both
    servers are configured and it's set; otherwise each server, running ones first."""
    servers = get_caddy_servers()
    vip_url = normalize_admin_api_url(get_caddy_vip_api_url())
    if vip_url and len(servers) == MAX_CADDY_SERVERS:
        return [vip_url]
    # A server not checked yet (None) is still worth trying; a known-stopped one isn't.
    statuses = [(caddy_status(s), s) for s in servers]
    ordered = [s for st, s in statuses if st == "running"] + [s for st, s in statuses if st is None]
    return [admin_api_base_url(s["host"], s["api_port"]) for s in ordered]


def _fetch_upstreams(base_url):
    try:
        req = urllib.request.Request(
            f"{base_url}/reverse_proxy/upstreams", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return data if isinstance(data, list) else None


def fetch_reverse_proxy_upstreams():
    """Parsed JSON list from the first candidate that answers, or None if
    nothing is configured or reachable."""
    for base_url in admin_api_candidates():
        data = _fetch_upstreams(base_url)
        if data is not None:
            return data
    return None


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
