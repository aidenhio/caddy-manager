// BEGIN DASHBOARD STATS AUTO-REFRESH
// Keeps the Current Requests stat card current without needing a full
// page reload. It's the one Dashboard stat sourced live from Caddy's own
// admin API (see caddy_api.py) rather than this app's own files/config,
// so it's the one that visibly goes stale if the page is left open --
// Active/Disabled Site Blocks and SSL Certificates only change in
// response to actions taken through this app itself, so they don't need
// the same treatment.
(function () {
  const valueEl = document.getElementById('current-requests-value');
  if (!valueEl) return;

  const REFRESH_INTERVAL_MS = 60000;

  function refresh() {
    fetch('/dashboard/caddy-stats', { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        valueEl.textContent = typeof data.current_requests === 'number' ? data.current_requests : 'N/A';
      })
      .catch(() => {
        // Leave the last known value showing rather than flashing N/A for
        // what's likely just a transient network hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END DASHBOARD STATS AUTO-REFRESH
