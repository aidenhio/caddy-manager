// BEGIN DASHBOARD STATS AUTO-REFRESH
// Keeps the Current Requests stat card and the Upstream Health card
// current without needing a full page reload. These are the Dashboard
// stats sourced live from Caddy's own admin API (see caddy_api.py)
// rather than this app's own files/config, so they're the ones that
// visibly go stale if the page is left open -- Active/Disabled Site
// Blocks and SSL Certificates only change in response to actions taken
// through this app itself, so they don't need the same treatment.
(function () {
  // Each of these elements can be independently missing from the DOM: the
  // Current Requests span is only rendered when the Quick Glance Row
  // widget is turned on (Settings > Dashboard), and the Upstream Health
  // card's spans only exist when both that widget is turned on and the
  // Caddy admin API is configured. setValue()/the wrapper check below
  // just skip updating whichever of these aren't present.
  const currentRequestsEl = document.getElementById('current-requests-value');
  const upstreamCountEl = document.getElementById('upstream-count-value');
  const requestedSitesEl = document.getElementById('requested-sites-value');
  const failedRequestsEl = document.getElementById('failed-requests-value');
  const failedRequestsWrapper = document.getElementById('failed-requests-wrapper');

  // Nothing on the page needs a live refresh -- both widgets are hidden.
  if (!currentRequestsEl && !upstreamCountEl && !requestedSitesEl && !failedRequestsEl) return;

  const REFRESH_INTERVAL_MS = 60000;

  function setValue(el, value) {
    if (!el) return;
    el.textContent = typeof value === 'number' ? value : 'N/A';
  }

  function refresh() {
    fetch('/dashboard/caddy-stats', { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        setValue(currentRequestsEl, data.current_requests);
        setValue(upstreamCountEl, data.upstreams_total);
        setValue(requestedSitesEl, data.unique_requested_sites);
        setValue(failedRequestsEl, data.failed_requests);
        if (failedRequestsWrapper) {
          failedRequestsWrapper.classList.toggle('text-danger', !!data.failed_requests);
        }
      })
      .catch(() => {
        // Leave the last known values showing rather than flashing N/A for
        // what's likely just a transient network hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END DASHBOARD STATS AUTO-REFRESH
