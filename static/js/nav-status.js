// BEGIN NAVBAR CADDY SERVER STATUS
// Keeps the Caddy Server status tags in the navbar's right-hand side
// (see templates/partials/header_nav_bar.html) live across every page,
// not just while some particular page happens to stay open -- the
// background ping monitor this polls (server_monitor.py) runs for as
// long as the app itself is running, independent of any browser tab.
(function () {
  const tags = document.querySelectorAll('[data-server-host]');
  if (!tags.length) return;

  // Independent of the actual ping interval (configurable in Settings,
  // 60s by default) -- this just refreshes what the navbar shows of
  // already-known state, so polling more often than pings actually
  // happen is harmless (the endpoint reads cheap in-memory state, no
  // live ping triggered per request) and keeps a status change visible
  // sooner than waiting a full ping interval to notice it.
  const REFRESH_INTERVAL_MS = 20000;

  const BG_CLASSES = ['bg-success-lt', 'bg-warning-lt', 'bg-danger-lt', 'bg-secondary-lt'];
  const DOT_CLASSES = ['status-success', 'status-warning', 'status-danger', 'status-secondary'];

  function applyStatus(tag, server) {
    tag.classList.remove(...BG_CLASSES);
    tag.classList.add(server.bg_class);
    const dot = tag.querySelector('.status-dot');
    if (dot) {
      dot.classList.remove(...DOT_CLASSES);
      dot.classList.add(server.dot_class);
    }
    // Bootstrap's tooltip re-reads this attribute fresh every time it's
    // shown (see Tooltip._getTitle() in Tabler's bundled Bootstrap
    // build) rather than caching the title at init time, so updating it
    // here is enough -- no need to destroy/recreate the Tooltip
    // instance Tabler's own bundle already created for this element.
    tag.setAttribute('data-bs-original-title', server.label + ' (' + server.host + ')');
  }

  function refresh() {
    fetch('/nav/server-status', { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        const byHost = {};
        (data.servers || []).forEach((server) => { byHost[server.host] = server; });
        tags.forEach((tag) => {
          const server = byHost[tag.dataset.serverHost];
          if (server) applyStatus(tag, server);
        });
      })
      .catch(() => {
        // Leave the last known status showing rather than flashing
        // anything for what's likely just a transient network hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END NAVBAR CADDY SERVER STATUS
