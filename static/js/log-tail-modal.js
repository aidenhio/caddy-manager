// BEGIN LOG TAIL MODAL
// Fills the shared modal on open, fetching the tail fresh each time. JSON logs show as a
// readable, expandable list; anything else falls back to the raw lines.
(function () {
  const modal = document.getElementById('log-tail-modal');
  if (!modal) return;

  const fieldEls = {};
  modal.querySelectorAll('[data-field]').forEach((el) => {
    fieldEls[el.dataset.field] = el;
  });

  // Single source of truth for level -> Tabler color; the badge and raw-JSON
  // code block background classes both derive from this.
  const LEVEL_COLORS = {
    debug: 'blue',
    info: 'green',
    warn: 'yellow',
    warning: 'yellow',
    error: 'red',
    dpanic: 'red',
    panic: 'red',
    fatal: 'red',
  };

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function levelColor(level) {
    return LEVEL_COLORS[String(level || '').toLowerCase()] || 'secondary';
  }

  function levelBadgeClass(level) {
    return `bg-${levelColor(level)}-lt`;
  }

  function levelCodeClass(level) {
    return `code-${levelColor(level)}-lt`;
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

  // Every non-blank line must parse as a JSON object; one non-JSON line falls back to plain text.
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

  // Matches the app's accordion convention: Tabler needs an explicit chevron icon
  // carrying accordion-button-toggle; flex-shrink-0 keeps it from squishing with the row.
  const ACCORDION_TOGGLE_ICON = '<svg xmlns="http://www.w3.org/2000/svg" class="icon accordion-button-toggle flex-shrink-0" ' +
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M6 9l6 6l6 -6" /></svg>';

  // accordion-flush, edge-to-edge; each header doubles as the toggle so opening one entry
  // (data-bs-parent) auto-closes whichever other was open.
  function buildEntryItem(obj, idx) {
    const headingId = `log-json-heading-${idx}`;
    const collapseId = `log-json-collapse-${idx}`;
    // flex-shrink-0 on every fixed-content badge so only the summary span gives up width.
    const badges = [];
    if (obj.level !== undefined) {
      badges.push(`<span class="badge ${levelBadgeClass(obj.level)} text-uppercase flex-shrink-0" style="min-width: 3.75rem;">${escapeHtml(obj.level)}</span>`);
    }
    const time = formatTime(obj.ts);

    let statusHtml = '';
    if (typeof obj.status === 'number') {
      statusHtml = `<span class="badge ${statusBadgeClass(obj.status)} flex-shrink-0">${obj.status}</span>`;
    }
    let durationHtml = '';
    if (typeof obj.duration === 'number') {
      durationHtml = `<span class="text-secondary text-nowrap flex-shrink-0">${formatDuration(obj.duration)}</span>`;
    }
    let sizeHtml = '';
    if (typeof obj.size === 'number') {
      sizeHtml = `<span class="text-secondary text-nowrap flex-shrink-0 d-none d-md-inline">${formatSize(obj.size)}</span>`;
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
            <div class="d-flex align-items-center gap-2 flex-fill small overflow-hidden" style="min-width: 0;">
              ${badges.join('')}
              <span class="font-monospace text-secondary text-nowrap flex-shrink-0">${time}</span>
              <span class="flex-fill text-truncate" style="min-width: 0;">${buildSummary(obj)}</span>
              ${statusHtml}
              ${durationHtml}
              ${sizeHtml}
            </div>
            ${ACCORDION_TOGGLE_ICON}
          </button>
        </div>
        <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#${ACCORDION_ID}">
          <div class="accordion-body">
            <pre class="${levelCodeClass(obj.level)} font-monospace p-2 mb-0" style="white-space: pre-wrap; word-break: break-all;">${escapeHtml(raw)}</pre>
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

  modal.addEventListener('show.bs.modal', (event) => {
    const button = event.relatedTarget;
    if (!button) return;
    const filename = button.dataset.logFilename || '';

    if (fieldEls.filename) fieldEls.filename.textContent = filename;
    if (fieldEls.summary) fieldEls.summary.textContent = '';
    if (fieldEls.lines) fieldEls.lines.textContent = '';
    if (fieldEls.entries) fieldEls.entries.innerHTML = '';
    if (fieldEls.error) fieldEls.error.textContent = '';
    showState('loading');

    fetch(`/logs/${encodeURIComponent(filename)}/tail`, { headers: { Accept: 'application/json' } })
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          if (fieldEls.error) fieldEls.error.textContent = data.error;
          showState('error');
          return;
        }
        if (fieldEls.summary) {
          fieldEls.summary.textContent = `Showing the last ${data.lines.length} log line${data.lines.length === 1 ? '' : 's'}`;
        }

        const jsonEntries = parseJsonEntries(data.lines);
        if (jsonEntries && fieldEls.entries) {
          fieldEls.entries.innerHTML = buildEntriesHtml(jsonEntries);
          showState('entries');
        } else {
          if (fieldEls.lines) {
            // Blank line between entries so multi-line entries (stack traces) don't run together.
            fieldEls.lines.textContent = data.lines.length ? data.lines.join('\n\n') : '(empty file)';
          }
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