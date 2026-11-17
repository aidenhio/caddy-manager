// BEGIN ANIMATED SECTIONS
// Shows or hides a .collapse element with Bootstrap's collapse animation (height slide; Bootstrap drops the
// transition for users who prefer reduced motion). On an inactive tab it switches instantly, since there's
// nothing to see. A hidden <fieldset> is also disabled (once it has finished closing), so its fields are
// neither submitted nor validated. Calls made mid-animation are applied as soon as that animation ends.
function setSectionShown(el, show) {
  el.dataset.shown = show ? 'true' : 'false';
  const isFieldset = el.tagName === 'FIELDSET';
  if (show && isFieldset) el.disabled = false;
  if (el.classList.contains('collapsing')) return;  // the shown/hidden listener below catches up

  const pane = el.closest('.tab-pane');
  const onScreen = !pane || pane.classList.contains('active');
  // Tabler's bundle exposes Bootstrap's components on window.tabler (not window.bootstrap).
  const Collapse = window.tabler && window.tabler.Collapse;
  if (!onScreen || !Collapse) {
    el.classList.toggle('show', show);
    if (!show && isFieldset) el.disabled = true;
    return;
  }
  if (!el.dataset.collapseWired) {
    el.dataset.collapseWired = 'true';
    const settle = (event) => {
      if (event.target !== el) return;  // collapse events bubble from nested sections
      const want = el.dataset.shown === 'true';
      if (el.classList.contains('show') !== want) {
        setSectionShown(el, want);
      } else if (!want && isFieldset) {
        el.disabled = true;
        // Let validation and the tab dots drop the now-disabled fields.
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    };
    el.addEventListener('shown.bs.collapse', settle);
    el.addEventListener('hidden.bs.collapse', settle);
  }
  if (el.classList.contains('show') === show) return;
  Collapse.getOrCreateInstance(el, { toggle: false })[show ? 'show' : 'hide']();
}

// Switches with data-reveals="#selector" (toggle_card's `reveals`) open and close that section.
(function () {
  document.querySelectorAll('input[data-reveals]').forEach((toggle) => {
    const target = document.querySelector(toggle.dataset.reveals);
    if (!target) return;
    toggle.addEventListener('change', () => setSectionShown(target, toggle.checked));
    // A no-op unless the browser restored a different switch state (e.g. on Back).
    setSectionShown(target, toggle.checked);
  });
})();
// END ANIMATED SECTIONS

// BEGIN BLOCK TYPE SWITCHER
// Shows the cards for the selected type; hidden sections are also disabled so their fields aren't submitted.
(function () {
  const form = document.getElementById('block-form');
  if (!form) return;
  const radios = form.querySelectorAll('input[name="block_type"]');
  const sections = form.querySelectorAll('[data-block-types]');

  function sync() {
    const checked = form.querySelector('input[name="block_type"]:checked');
    if (!checked) return;
    sections.forEach((section) => {
      setSectionShown(section, section.dataset.blockTypes.split(' ').includes(checked.value));
    });
  }

  radios.forEach((radio) => radio.addEventListener('change', sync));
  sync();  // a no-op unless the browser restored a different type (e.g. on Back)
})();
// END BLOCK TYPE SWITCHER

// BEGIN SITE ADDRESS TAG INPUT
(function () {
  const wrap = document.getElementById('site-address-input');
  const textInput = document.getElementById('site-address-text-input');
  const hidden = document.getElementById('site-addresses');
  if (!wrap || !textInput || !hidden) return;

  function currentSiteAddresses() {
    return Array.from(wrap.querySelectorAll('.site-address-chip')).map((el) => el.dataset.siteAddress);
  }

  function syncHidden() {
    hidden.value = currentSiteAddresses().join('\n');
  }

  function addChip(value) {
    value = value.trim();
    if (!value || currentSiteAddresses().includes(value)) return;

    wrap.classList.remove('is-invalid');

    const chip = document.createElement('span');
    chip.className = 'site-address-chip tag bg-primary-lt d-inline-flex align-items-center gap-1';
    chip.dataset.siteAddress = value;

    const label = document.createElement('span');
    label.textContent = value;
    chip.appendChild(label);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn-close';
    remove.setAttribute('aria-label', 'Remove site address');
    remove.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M18 6l-12 12"/><path d="M6 6l12 12"/></svg>';
    remove.addEventListener('click', (e) => {
      e.stopPropagation();
      chip.remove();
      syncHidden();
    });
    chip.appendChild(remove);

    wrap.insertBefore(chip, textInput);
    syncHidden();
  }

  (hidden.value || '').split('\n').map((h) => h.trim()).filter(Boolean).forEach(addChip);

  textInput.addEventListener('keydown', (e) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      addChip(textInput.value);
      textInput.value = '';
    } else if (e.key === 'Backspace' && textInput.value === '') {
      const chips = wrap.querySelectorAll('.site-address-chip');
      if (chips.length) {
        chips[chips.length - 1].remove();
        syncHidden();
      }
    }
  });

  textInput.addEventListener('blur', () => {
    if (textInput.value.trim()) {
      addChip(textInput.value);
      textInput.value = '';
    }
  });

  wrap.addEventListener('click', () => textInput.focus());
  // Text still in the input becomes a chip on submit, and before a preview reads the form.
  const addPendingChip = () => {
    if (textInput.value.trim()) addChip(textInput.value);
  };
  wrap.closest('form').addEventListener('submit', addPendingChip);
  wrap.closest('form').addEventListener('block-form:sync', addPendingChip);

  window.__validateSiteAddresses = function () {
    const valid = currentSiteAddresses().length > 0;
    wrap.classList.toggle('is-invalid', !valid);
    return valid;
  };
})();
// END SITE ADDRESS TAG INPUT

// BEGIN REVERSE PROXY SCHEME -> INSECURE SKIP VERIFY TOGGLE
(function () {
  const schemeSelect = document.getElementById('scheme');
  const row = document.getElementById('insecure-skip-verify-row');
  if (!schemeSelect || !row) return;

  schemeSelect.addEventListener('change', () => {
    const https = schemeSelect.value === 'https';
    setSectionShown(row, https);
    if (!https) row.querySelector('input[type="checkbox"]').checked = false;
  });
})();
// END REVERSE PROXY SCHEME -> INSECURE SKIP VERIFY TOGGLE

// BEGIN LOAD BALANCER SCHEME -> INSECURE SKIP VERIFY TOGGLE
// Mirrors the reverse proxy toggle above, but doesn't sync on load -- the
// UPSTREAM ROWS block below corrects #lb-scheme's value first.
(function () {
  const schemeSelect = document.getElementById('lb-scheme');
  const row = document.getElementById('lb-insecure-skip-verify-row');
  if (!schemeSelect || !row) return;

  schemeSelect.addEventListener('change', () => {
    const https = schemeSelect.value === 'https';
    setSectionShown(row, https);
    if (!https) row.querySelector('input[type="checkbox"]').checked = false;
  });
})();
// END LOAD BALANCER SCHEME -> INSECURE SKIP VERIFY TOGGLE

// BEGIN LOAD BALANCER UPSTREAM ROWS
(function () {
  const schemeSelect = document.getElementById('lb-scheme');
  const rowsWrap = document.getElementById('upstream-rows');
  const addBtn = document.getElementById('add-upstream-btn');
  const hidden = document.getElementById('upstreams');
  if (!schemeSelect || !rowsWrap || !addBtn || !hidden) return;

  function splitUpstream(value) {
    value = (value || '').trim();
    const [scheme, rest] = value.includes('://') ? value.split('://', 2) : ['', value];
    const [host, port] = rest.split(':');
    return { scheme, host: host || '', port: port || '' };
  }

  function addRow(host, port) {
    const row = document.createElement('div');
    row.className = 'row g-2 mb-2 align-items-center upstream-row';
    row.innerHTML =
      '<div class="col">' +
      '  <input type="text" class="form-control upstream-host" placeholder="10.0.0.1" required>' +
      '  <div class="invalid-feedback">Host is required.</div>' +
      '</div>' +
      '<div class="col-3">' +
      '  <input type="text" class="form-control upstream-port" placeholder="8080">' +
      '</div>' +
      '<div class="col-auto">' +
      '  <button type="button" class="btn-close upstream-remove" aria-label="Remove upstream">' +
      '    <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M18 6l-12 12"/><path d="M6 6l12 12"/></svg>' +
      '  </button>' +
      '</div>';
    row.querySelector('.upstream-host').value = host || '';
    row.querySelector('.upstream-port').value = port || '';
    row.querySelector('.upstream-remove').addEventListener('click', () => {
      row.remove();
      refreshRemoveState();
    });
    rowsWrap.appendChild(row);
    refreshRemoveState();
  }

  function refreshRemoveState() {
    const rows = rowsWrap.querySelectorAll('.upstream-row');
    rows.forEach((row) => {
      row.querySelector('.upstream-remove').disabled = rows.length <= 2;
    });
  }

  function syncHidden() {
    const values = Array.from(rowsWrap.querySelectorAll('.upstream-row')).map((row) => {
      const host = row.querySelector('.upstream-host').value.trim();
      const port = row.querySelector('.upstream-port').value.trim();
      if (!host) return '';
      return `${schemeSelect.value}://${host}${port ? ':' + port : ''}`;
    }).filter(Boolean);
    hidden.value = values.join('\n');
  }

  const existing = (hidden.value || '').split('\n').map((u) => u.trim()).filter(Boolean).map(splitUpstream);
  schemeSelect.value = (existing.find((u) => u.scheme) || {}).scheme || 'http';
  if (existing.length) {
    existing.forEach((u) => addRow(u.host, u.port));
  } else {
    addRow('', '');
    addRow('', '');
  }

  addBtn.addEventListener('click', () => addRow('', ''));
  rowsWrap.closest('form').addEventListener('submit', syncHidden);
  rowsWrap.closest('form').addEventListener('block-form:sync', syncHidden);
})();
// END LOAD BALANCER UPSTREAM ROWS

// BEGIN FORM VALIDATION WIRING
(function () {
  const form = document.getElementById('block-form');
  if (!form || typeof initFormValidation !== 'function') return;

  initFormValidation(form, function () {
    return window.__validateSiteAddresses ? window.__validateSiteAddresses() : true;
  });

  // A red dot on each tab title that holds an invalid field, shown from the first failed Save
  // (when initFormValidation starts flagging fields) and kept live as fields are fixed.
  const invalidSelector = '.is-invalid';
  function updateTabDots() {
    const validated = Boolean(form.dataset.validated);
    if (validated) {
      // Also covers changes with no input event, like added/removed upstream rows and chips.
      refreshInvalidFields(form);
      if (window.__validateSiteAddresses) window.__validateSiteAddresses();
    }
    form.querySelectorAll('.tab-pane').forEach((pane) => {
      const dot = form.querySelector('[data-bs-target="#' + pane.id + '"] [data-invalid-dot]');
      if (dot) dot.hidden = !(validated && pane.querySelector(invalidSelector));
    });
  }
  let dotsQueued = false;
  function queueTabDots() {
    if (dotsQueued) return;
    dotsQueued = true;
    requestAnimationFrame(() => { dotsQueued = false; updateTabDots(); });
  }
  // click covers adding/removing chips and upstream rows; change covers the type picker.
  ['input', 'change', 'click', 'keyup'].forEach((type) => form.addEventListener(type, queueTabDots));
  form.addEventListener('reset', () => setTimeout(updateTabDots, 0));

  // Registered after initFormValidation, so defaultPrevented already reflects its verdict.
  form.addEventListener('submit', (event) => {
    updateTabDots();
    if (!event.defaultPrevented) return;
    const invalid = form.querySelector(invalidSelector);
    const pane = invalid && invalid.closest('.tab-pane');
    if (!pane || pane.classList.contains('active')) return;
    const tabButton = form.querySelector('[data-bs-toggle="tab"][data-bs-target="#' + pane.id + '"]');
    if (tabButton) tabButton.click();
  });
})();
// END FORM VALIDATION WIRING

// BEGIN PREVIEW MODAL
// Renders the form's current values server-side (same code as Save, nothing written) and shows the result.
(function () {
  const form = document.getElementById('block-form');
  const modal = document.getElementById('block-preview-modal');
  if (!form || !modal) return;
  const field = (name) => modal.querySelector('[data-field="' + name + '"]');

  function show(state, text, path) {
    field('loading').hidden = state !== 'loading';
    field('error').hidden = state !== 'error';
    field('content').hidden = state !== 'content';
    field('filename').hidden = !(state === 'content' && path);
    if (state === 'error') field('error-text').textContent = text;
    if (state === 'content') {
      field('content-text').textContent = text;
      field('filename-text').textContent = path || '';
    }
  }

  modal.addEventListener('show.bs.modal', () => {
    show('loading');
    form.dispatchEvent(new Event('block-form:sync'));
    fetch(form.dataset.previewUrl, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } })
      .then((res) => {
        if (!res.ok) throw new Error('The preview could not be generated (HTTP ' + res.status + ').');
        return res.json();
      })
      .then((data) => {
        if (data.error) show('error', data.error);
        else show('content', data.content, data.path);
      })
      .catch((err) => show('error', err.message || 'The preview could not be generated.'));
  });
})();
// END PREVIEW MODAL
