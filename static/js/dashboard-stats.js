// BEGIN DASHBOARD STATS AUTO-REFRESH
// Keeps the Current Requests / Upstream Health cards fresh without a reload --
// these are sourced live from Caddy's admin API, unlike the rest of the dashboard.
(function () {
  // Each element can be independently missing (its widget/the admin API may be off);
  // setValue() and the check below just skip whichever aren't present.
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
        // Leave the last known values showing rather than flash N/A on a transient hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END DASHBOARD STATS AUTO-REFRESH
