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
      const show = section.dataset.blockTypes.split(' ').includes(checked.value);
      section.hidden = !show;
      section.disabled = !show;
    });
  }

  radios.forEach((radio) => radio.addEventListener('change', sync));
  sync();
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
    row.hidden = schemeSelect.value !== 'https';
    if (row.hidden) row.querySelector('input[type="checkbox"]').checked = false;
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
    row.hidden = schemeSelect.value !== 'https';
    if (row.hidden) row.querySelector('input[type="checkbox"]').checked = false;
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

// BEGIN LOGGING ENABLE TOGGLE
(function () {
  const toggle = document.getElementById('log-enabled-input');
  const row = document.getElementById('log-options-row');
  if (!toggle || !row) return;

  function sync() {
    row.hidden = !toggle.checked;
  }
  toggle.addEventListener('change', sync);
  sync();
})();
// END LOGGING ENABLE TOGGLE

// BEGIN FORM VALIDATION WIRING
(function () {
  const form = document.getElementById('block-form');
  if (!form || typeof initFormValidation !== 'function') return;

  initFormValidation(form, function () {
    return window.__validateSiteAddresses ? window.__validateSiteAddresses() : true;
  });

  // Registered after initFormValidation, so defaultPrevented already reflects its verdict.
  form.addEventListener('submit', (event) => {
    if (!event.defaultPrevented) return;
    const invalid = form.querySelector('.is-invalid, :invalid:not(fieldset)');
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
