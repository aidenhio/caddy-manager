// BEGIN NAVBAR CADDY SERVER STATUS
// Keeps the navbar's Caddy Server status tags live on every page by
// polling the background ping monitor's state (server_monitor.py).
(function () {
  const tags = document.querySelectorAll('[data-server-host]');
  if (!tags.length) return;

  // Independent of the actual ping interval -- the endpoint reads cheap in-memory
  // state, so polling more often just surfaces a change sooner.
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
    // Bootstrap re-reads this attribute fresh on every show(), so no need to recreate the Tooltip instance.
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
        // Leave the last known status showing rather than flash anything on a transient hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END NAVBAR CADDY SERVER STATUS
