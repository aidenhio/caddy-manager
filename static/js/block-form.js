// BEGIN SITE ADDRESS TAG INPUT + LIVE CONF-PATH PREVIEW
(function () {
  const wrap = document.getElementById('site-address-input');
  const textInput = document.getElementById('site-address-text-input');
  const hidden = document.getElementById('site-addresses');
  const form = document.getElementById('block-form');
  if (!wrap || !textInput || !hidden || !form) return;

  const typeColor = form.dataset.typeColor || 'primary';
  const confDir = form.dataset.confDir || '';
  const confPathBadge = document.getElementById('conf-path-badge');
  const originallyDisabled = form.dataset.originallyDisabled === 'true';

  function currentSiteAddresses() {
    return Array.from(wrap.querySelectorAll('.site-address-chip')).map((el) => el.dataset.siteAddress);
  }

  function sortedFirstSiteAddress() {
    // Mirrors the backend's normalize_site_addresses(): addresses starting
    // with a letter sort before addresses starting with a digit,
    // alphabetically (case-insensitively) within each group.
    const siteAddresses = currentSiteAddresses().slice();
    siteAddresses.sort((a, b) => {
      const aDigit = /^[0-9]/.test(a) ? 1 : 0;
      const bDigit = /^[0-9]/.test(b) ? 1 : 0;
      if (aDigit !== bDigit) return aDigit - bDigit;
      const aLower = a.toLowerCase();
      const bLower = b.toLowerCase();
      if (aLower < bLower) return -1;
      if (aLower > bLower) return 1;
      return 0;
    });
    return siteAddresses[0];
  }

  function slugify(value) {
    value = (value || '').trim().toLowerCase();
    let out = '';
    for (const ch of value) {
      out += (/[a-z0-9.]/.test(ch)) ? ch : '-';
    }
    let slug = out.replace(/^-+|-+$/g, '');
    while (slug.includes('--')) slug = slug.replace(/--/g, '-');
    return slug || 'block';
  }

  function updateConfPathBadge() {
    if (!confPathBadge) return;
    const dirPrefix = confDir.replace(/\/$/, '') + '/';
    const first = sortedFirstSiteAddress();
    if (!first) {
      confPathBadge.textContent = dirPrefix + '...';
      return;
    }
    const createDisabledInput = document.getElementById('create-disabled-input');
    const isDisabled = createDisabledInput ? createDisabledInput.checked : originallyDisabled;
    confPathBadge.textContent = dirPrefix + slugify(first) + '.conf' + (isDisabled ? '.disabled' : '');
  }

  function syncHidden() {
    hidden.value = currentSiteAddresses().join('\n');
    updateConfPathBadge();
  }

  function addChip(value) {
    value = value.trim();
    if (!value || currentSiteAddresses().includes(value)) return;

    wrap.classList.remove('is-invalid');

    const chip = document.createElement('span');
    chip.className = 'site-address-chip badge bg-' + typeColor + '-lt d-inline-flex align-items-center gap-1';
    chip.dataset.siteAddress = value;

    const label = document.createElement('span');
    label.textContent = value;
    chip.appendChild(label);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn btn-icon btn-action btn-sm btn-animate-icon btn-animate-icon-rotate p-0 mx-2 lh-1';
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
  updateConfPathBadge();

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
  wrap.closest('form').addEventListener('submit', () => {
    if (textInput.value.trim()) addChip(textInput.value);
  });

  window.__validateSiteAddresses = function () {
    const valid = currentSiteAddresses().length > 0;
    wrap.classList.toggle('is-invalid', !valid);
    return valid;
  };
  window.__updateConfPathBadge = updateConfPathBadge;
})();
// END SITE ADDRESS TAG INPUT + LIVE CONF-PATH PREVIEW

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
      '  <button type="button" class="btn btn-icon btn-ghost-secondary upstream-remove" aria-label="Remove upstream">' +
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
})();
// END LOAD BALANCER UPSTREAM ROWS

// BEGIN FORM VALIDATION WIRING
(function () {
  const form = document.getElementById('block-form');
  if (!form || typeof initFormValidation !== 'function') return;

  initFormValidation(form, function () {
    return window.__validateSiteAddresses ? window.__validateSiteAddresses() : true;
  });
})();
// END FORM VALIDATION WIRING
