// BEGIN SIDEBAR SERVER STATUS
// Keeps the sidebar's server status (dot + Server/Caddy badges) live on every
// page by polling the background ping/status monitor's state (server_monitor.py).
(function () {
  const items = document.querySelectorAll('[data-server-host]');
  if (!items.length) return;

  // Independent of the actual check intervals -- the endpoint reads cheap in-memory
  // state, so polling more often just surfaces a change sooner.
  const REFRESH_INTERVAL_MS = 20000;

  const DOT_CLASSES = ['status-success', 'status-warning', 'status-danger', 'status-secondary'];
  const BADGE_CLASSES = ['bg-green-lt', 'bg-yellow-lt', 'bg-red-lt', 'bg-secondary-lt'];

  function setBadge(item, name, label, badgeClass) {
    const badge = item.querySelector('[data-status-badge="' + name + '"]');
    if (!badge) return;
    badge.classList.remove(...BADGE_CLASSES);
    badge.classList.add(badgeClass);
    badge.textContent = label;
  }

  function applyStatus(item, server) {
    const dot = item.querySelector('.status-dot');
    if (dot) {
      dot.classList.remove(...DOT_CLASSES);
      dot.classList.add(server.dot_class);
    }
    setBadge(item, 'server', server.server_label, server.server_badge_class);
    setBadge(item, 'caddy', server.caddy_label, server.caddy_badge_class);
  }

  function refresh() {
    fetch('/nav/server-status', { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        const byHost = {};
        (data.servers || []).forEach((server) => { byHost[server.host] = server; });
        items.forEach((item) => {
          const server = byHost[item.dataset.serverHost];
          if (server) applyStatus(item, server);
        });
      })
      .catch(() => {
        // Leave the last known status showing rather than flash anything on a transient hiccup.
      });
  }

  setInterval(refresh, REFRESH_INTERVAL_MS);
})();
// END SIDEBAR SERVER STATUS
