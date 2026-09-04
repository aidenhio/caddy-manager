// BEGIN LOG TAIL MODAL
// Fills the shared #log-tail-modal from whichever row's "More" button
// triggered it (same one-modal-many-triggers pattern as
// certificate-detail-modal.js), fetching the tail fresh from the server
// on every open rather than baking log content into the page up front --
// log files can be large and change constantly, so a snapshot taken at
// page load would already be stale by the time someone clicks "More".
//
// When every returned line parses as a JSON object -- i.e. the block is
// using Caddy's `format json` log directive, one JSON object per line --
// the tail is also rendered as a readable list (time, level, request/msg
// summary, status, duration), each entry expandable to its raw JSON,
// with a Formatted/Raw toggle to fall back to the plain-text view. When
// the lines aren't uniformly JSON (console format, or anything else),
// only the plain-text view is offered, same as before.
(function () {
  const modal = document.getElementById('log-tail-modal');
  if (!modal) return;

  const fieldEls = {};
  modal.querySelectorAll('[data-field]').forEach((el) => {
    fieldEls[el.dataset.field] = el;
  });

  const LEVEL_BADGE_CLASS = {
    debug: 'bg-secondary-lt',
    info: 'bg-blue-lt',
    warn: 'bg-orange-lt',
    warning: 'bg-orange-lt',
    error: 'bg-red-lt',
    dpanic: 'bg-red-lt',
    panic: 'bg-red-lt',
    fatal: 'bg-red-lt',
  };

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function levelBadgeClass(level) {
    return LEVEL_BADGE_CLASS[String(level || '').toLowerCase()] || 'bg-secondary-lt';
  }

  function statusBadgeClass(status) {
    if (status < 300) return 'bg-green-lt';
    if (status < 400) return 'bg-azure-lt';
    if (status < 500) return 'bg-orange-lt';
    return 'bg-red-lt';
  }

  function formatTime(ts) {
    if (typeof ts !== 'number') return '';
    const d = new Date(ts * 1000);
    if (isNaN(d.getTime())) return '';
    const pad = (n, len) => String(n).padStart(len || 2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  }

  function formatDuration(seconds) {
    if (typeof seconds !== 'number') return '';
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
    return `${seconds.toFixed(2)}s`;
  }

  function formatSize(bytes) {
    if (typeof bytes !== 'number') return '';
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  // Every non-blank line must parse as a JSON object (not an array or
  // scalar) for the tail to be treated as JSON-formatted -- Caddy's log
  // format is uniform for a given file, so a single non-JSON line means
  // this isn't NDJSON and the whole tail falls back to plain text.
  function parseJsonEntries(lines) {
    const entries = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let obj;
      try {
        obj = JSON.parse(trimmed);
      } catch (e) {
        return null;
      }
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
      entries.push(obj);
    }
    return entries.length ? entries : null;
  }

  function buildSummary(obj) {
    const req = obj.request;
    if (req && typeof req === 'object' && (req.method || req.uri)) {
      const method = req.method ? escapeHtml(req.method) : '';
      const hostUri = escapeHtml(`${req.host || ''}${req.uri || ''}`);
      return `<span class="fw-medium">${method}</span> <span class="font-monospace">${hostUri}</span>`;
    }
    if (typeof obj.msg === 'string' && obj.msg) {
      return escapeHtml(obj.msg);
    }
    let preview = '';
    try {
      preview = JSON.stringify(obj);
    } catch (e) {
      preview = '';
    }
    if (preview.length > 140) preview = `${preview.slice(0, 140)}…`;
    return `<span class="font-monospace text-secondary">${escapeHtml(preview)}</span>`;
  }

  const ACCORDION_ID = 'log-json-accordion';

  // Matches the app's own accordion convention (see the "Advanced
  // options" / "Logging" accordions in setup.html and block_form.html):
  // Tabler expects an explicit chevron icon carrying the
  // accordion-button-toggle class inside .accordion-button -- its CSS
  // rotates that icon on expand -- rather than relying on Bootstrap's
  // bare ::after chevron.
  const ACCORDION_TOGGLE_ICON = '<svg xmlns="http://www.w3.org/2000/svg" class="icon accordion-button-toggle" ' +
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M6 9l6 6l6 -6" /></svg>';

  // A real Tabler/Bootstrap accordion (accordion-flush, so items sit
  // edge-to-edge in the modal like a list rather than as boxed cards) --
  // each entry's header doubles as the accordion-button, so opening one
  // entry's raw JSON auto-closes whichever other entry was open
  // (data-bs-parent).
  function buildEntryItem(obj, idx) {
    const headingId = `log-json-heading-${idx}`;
    const collapseId = `log-json-collapse-${idx}`;
    const badges = [];
    if (obj.level !== undefined) {
      badges.push(`<span class="badge ${levelBadgeClass(obj.level)} text-uppercase" style="min-width: 3.75rem;">${escapeHtml(obj.level)}</span>`);
    }
    const time = formatTime(obj.ts);

    let statusHtml = '';
    if (typeof obj.status === 'number') {
      statusHtml = `<span class="badge ${statusBadgeClass(obj.status)}">${obj.status}</span>`;
    }
    let durationHtml = '';
    if (typeof obj.duration === 'number') {
      durationHtml = `<span class="text-secondary text-nowrap">${formatDuration(obj.duration)}</span>`;
    }
    let sizeHtml = '';
    if (typeof obj.size === 'number') {
      sizeHtml = `<span class="text-secondary text-nowrap d-none d-md-inline">${formatSize(obj.size)}</span>`;
    }

    let raw = '';
    try {
      raw = JSON.stringify(obj, null, 2);
    } catch (e) {
      raw = String(obj);
    }

    return `
      <div class="accordion-item">
        <div class="accordion-header" id="${headingId}">
          <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
              data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
            <div class="d-flex align-items-center gap-2 flex-fill small overflow-hidden">
              ${badges.join('')}
              <span class="font-monospace text-secondary text-nowrap">${time}</span>
              <span class="flex-fill text-truncate">${buildSummary(obj)}</span>
              ${statusHtml}
              ${durationHtml}
              ${sizeHtml}
            </div>
            ${ACCORDION_TOGGLE_ICON}
          </button>
        </div>
        <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#${ACCORDION_ID}">
          <div class="accordion-body">
            <pre class="font-monospace small mb-0" style="white-space: pre-wrap; word-break: break-all;">${escapeHtml(raw)}</pre>
          </div>
        </div>
      </div>`;
  }

  function buildEntriesHtml(entries) {
    const items = entries.map((obj, idx) => buildEntryItem(obj, idx)).join('');
    return `<div class="accordion accordion-flush" id="${ACCORDION_ID}">${items}</div>`;
  }

  function showState(state) {
    ['loading', 'error', 'entries', 'lines'].forEach((key) => {
      if (fieldEls[key]) fieldEls[key].hidden = key !== state;
    });
  }

  const formattedRadio = modal.querySelector('#log-view-formatted');
  const rawRadio = modal.querySelector('#log-view-raw');
  if (formattedRadio) formattedRadio.addEventListener('change', () => { if (formattedRadio.checked) showState('entries'); });
  if (rawRadio) rawRadio.addEventListener('change', () => { if (rawRadio.checked) showState('lines'); });

  modal.addEventListener('show.bs.modal', (event) => {
    const button = event.relatedTarget;
    if (!button) return;
    const filename = button.dataset.logFilename || '';

    if (fieldEls.filename) fieldEls.filename.textContent = filename;
    if (fieldEls.summary) fieldEls.summary.textContent = '';
    if (fieldEls.lines) fieldEls.lines.textContent = '';
    if (fieldEls.entries) fieldEls.entries.innerHTML = '';
    if (fieldEls.error) fieldEls.error.textContent = '';
    if (fieldEls['view-toggle']) fieldEls['view-toggle'].hidden = true;
    if (formattedRadio) formattedRadio.checked = true;
    showState('loading');

    fetch(`/logs/${encodeURIComponent(filename)}/tail`, { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          if (fieldEls.error) fieldEls.error.textContent = data.error;
          showState('error');
          return;
        }
        if (fieldEls.lines) {
          // A blank line between each entry makes a dense log tail much
          // easier to scan, since multi-line entries (stack traces,
          // wrapped console output) no longer run into the next line.
          fieldEls.lines.textContent = data.lines.length ? data.lines.join('\n\n') : '(empty file)';
        }
        if (fieldEls.summary) {
          fieldEls.summary.textContent = `Showing the last ${data.lines.length} line${data.lines.length === 1 ? '' : 's'} (configured tail length: ${data.tail_lines})`;
        }

        const jsonEntries = parseJsonEntries(data.lines);
        if (jsonEntries && fieldEls.entries) {
          fieldEls.entries.innerHTML = buildEntriesHtml(jsonEntries);
          if (fieldEls['view-toggle']) fieldEls['view-toggle'].hidden = false;
          showState('entries');
        } else {
          showState('lines');
        }
      })
      .catch(() => {
        if (fieldEls.error) fieldEls.error.textContent = 'Could not load the log file.';
        showState('error');
      });
  });
})();
// END LOG TAIL MODAL
