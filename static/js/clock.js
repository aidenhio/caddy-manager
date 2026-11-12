// BEGIN BREADCRUMB CLOCK
// Fills the breadcrumb date/time from this device's clock, in the 12h/24h format
// chosen in Settings -> Dashboard, and keeps it current on the minute.
(function () {
  const dateEl = document.querySelector('[data-clock="date"]');
  const timeEl = document.querySelector('[data-clock="time"]');
  if (!dateEl || !timeEl) return;
  const use24h = timeEl.dataset.timeFormat === '24h';

  function formatTime(now) {
    const minutes = String(now.getMinutes()).padStart(2, '0');
    if (use24h) return String(now.getHours()).padStart(2, '0') + ':' + minutes;
    const hours = now.getHours() % 12 || 12;
    return hours + ':' + minutes + (now.getHours() < 12 ? 'AM' : 'PM');
  }

  function tick() {
    const now = new Date();
    dateEl.textContent = now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
    timeEl.textContent = formatTime(now);
    // Re-run just after the next minute starts, so the clock never lags by up to a minute.
    setTimeout(tick, 60000 - (now.getSeconds() * 1000 + now.getMilliseconds()) + 50);
  }

  tick();
})();
// END BREADCRUMB CLOCK
