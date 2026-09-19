/*
 * Dependency-free search/sort/filter/pagination controller for a plain
 * server-rendered <table>. Opt in via `data-datatable` plus the `data-dt-*` attributes read below.
 */
(function () {
  'use strict';

  function normalize(text) {
    return (text || '').toString().trim().toLowerCase();
  }

  function matchesSearch(row, query) {
    if (!query) return true;
    const terms = normalize(query).split(/\s+/).filter(Boolean);
    const haystack = normalize(row.textContent);
    return terms.every((term) => haystack.includes(term));
  }

  function initTable(table) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.children).filter((el) => el.tagName === 'TR');

    const searchInput = table.dataset.dtSearch ? document.querySelector(table.dataset.dtSearch) : null;
    const filtersEl = table.dataset.dtFilters ? document.querySelector(table.dataset.dtFilters) : null;
    const pageSizeEl = table.dataset.dtPageSize ? document.querySelector(table.dataset.dtPageSize) : null;
    const summaryEl = table.dataset.dtSummary ? document.querySelector(table.dataset.dtSummary) : null;
    const paginationEl = table.dataset.dtPagination ? document.querySelector(table.dataset.dtPagination) : null;
    const storageKey = table.dataset.dtStorageKey || null;

    const sortButtons = Array.from(table.querySelectorAll('thead .table-sort'));
    const filterChecks = filtersEl
      ? Array.from(filtersEl.querySelectorAll('input[type="checkbox"][data-filter-group]'))
      : [];
    const clearFiltersEl = filtersEl ? filtersEl.querySelector('[data-dt-clear-filters]') : null;
    const clearFiltersDivider = clearFiltersEl && clearFiltersEl.previousElementSibling &&
      clearFiltersEl.previousElementSibling.classList.contains('dropdown-divider')
      ? clearFiltersEl.previousElementSibling
      : null;

    const defaultPageSize = parseInt(
      (pageSizeEl && pageSizeEl.value) || table.dataset.dtPageSizeDefault || '10',
      10
    ) || 10;

    const state = {
      page: 1,
      pageSize: defaultPageSize,
      sortKey: null,
      sortType: 'text',
      sortDir: 'asc',
      search: '',
    };

    function loadPersistedState() {
      if (!storageKey) return null;
      try {
        const raw = sessionStorage.getItem('datatable:' + storageKey);
        return raw ? JSON.parse(raw) : null;
      } catch (e) {
        return null;
      }
    }

    function savePersistedState() {
      if (!storageKey) return;
      try {
        sessionStorage.setItem('datatable:' + storageKey, JSON.stringify({
          sortKey: state.sortKey,
          sortType: state.sortType,
          sortDir: state.sortDir,
          search: state.search,
          filters: activeFilterGroups(),
        }));
      } catch (e) {
        // sessionStorage unavailable -- degrade to non-persistent rather than erroring.
      }
    }

    // A persisted session wins; otherwise fall back to data-dt-default-sort.
    const persisted = loadPersistedState();
    if (persisted) {
      state.sortKey = persisted.sortKey || null;
      state.sortType = persisted.sortType || 'text';
      state.sortDir = persisted.sortDir || 'asc';
      state.search = persisted.search || '';
      if (searchInput) searchInput.value = state.search;
      const persistedFilters = persisted.filters || {};
      filterChecks.forEach((cb) => {
        const values = persistedFilters[cb.dataset.filterGroup];
        cb.checked = !!(values && values.includes(cb.value));
      });
    } else if (table.dataset.dtDefaultSort) {
      state.sortKey = table.dataset.dtDefaultSort;
      const defaultBtn = sortButtons.find((b) => b.dataset.sortKey === state.sortKey);
      state.sortType = (defaultBtn && defaultBtn.dataset.sortType) || 'text';
      state.sortDir = table.dataset.dtDefaultSortDir || 'asc';
    }

    function activeFilterGroups() {
      const groups = {};
      filterChecks.forEach((cb) => {
        if (!cb.checked) return;
        const group = cb.dataset.filterGroup;
        (groups[group] = groups[group] || []).push(cb.value);
      });
      return groups;
    }

    function matchesFilters(row, groups) {
      return Object.keys(groups).every((group) => {
        const values = groups[group];
        return !values.length || values.includes(row.dataset[group]);
      });
    }

    function compareRows(a, b) {
      if (!state.sortKey) return 0;
      let av = a.dataset[state.sortKey] || '';
      let bv = b.dataset[state.sortKey] || '';
      if (state.sortType === 'number') {
        av = parseFloat(av) || 0;
        bv = parseFloat(bv) || 0;
        if (av === bv) return 0;
        return state.sortDir === 'asc' ? av - bv : bv - av;
      }
      av = normalize(av);
      bv = normalize(bv);
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return state.sortDir === 'asc' ? cmp : -cmp;
    }

    function updateSortIndicators() {
      sortButtons.forEach((btn) => {
        btn.classList.remove('asc', 'desc');
        if (btn.dataset.sortKey === state.sortKey) btn.classList.add(state.sortDir);
      });
    }

    function updateClearFiltersVisibility() {
      if (!clearFiltersEl) return;
      const anyChecked = filterChecks.some((cb) => cb.checked);
      clearFiltersEl.classList.toggle('d-none', !anyChecked);
      if (clearFiltersDivider) clearFiltersDivider.classList.toggle('d-none', !anyChecked);
    }

    function pageItem(label, page, opts) {
      opts = opts || {};
      const item = document.createElement('li');
      item.className = 'page-item' + (opts.disabled ? ' disabled' : '') + (opts.active ? ' active' : '');
      const link = document.createElement(opts.disabled || opts.active ? 'span' : 'a');
      link.className = 'page-link';
      link.innerHTML = label;
      if (!opts.disabled && !opts.active) {
        link.href = '#';
        link.addEventListener('click', (e) => {
          e.preventDefault();
          state.page = page;
          render();
        });
      }
      item.appendChild(link);
      return item;
    }

    function renderPagination(totalPages) {
      if (!paginationEl) return;
      paginationEl.innerHTML = '';
      if (totalPages <= 1) return;

      paginationEl.appendChild(
        pageItem('<i class="ti ti-chevron-left"></i>', state.page - 1, { disabled: state.page <= 1 })
      );

      const shown = Array.from(new Set([1, totalPages, state.page - 1, state.page, state.page + 1]))
        .filter((p) => p >= 1 && p <= totalPages)
        .sort((a, b) => a - b);

      let last = 0;
      shown.forEach((p) => {
        if (last && p - last > 1) paginationEl.appendChild(pageItem('&hellip;', 0, { disabled: true }));
        paginationEl.appendChild(pageItem(String(p), p, { active: p === state.page }));
        last = p;
      });

      paginationEl.appendChild(
        pageItem('<i class="ti ti-chevron-right"></i>', state.page + 1, { disabled: state.page >= totalPages })
      );
    }

    function render() {
      const groups = activeFilterGroups();
      const filtered = rows
        .filter((r) => matchesFilters(r, groups) && matchesSearch(r, state.search))
        .sort(compareRows);

      const total = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
      if (state.page > totalPages) state.page = totalPages;
      if (state.page < 1) state.page = 1;

      const start = total === 0 ? 0 : (state.page - 1) * state.pageSize;
      const end = Math.min(start + state.pageSize, total);

      filtered.forEach((r) => tbody.appendChild(r));
      rows.forEach((r) => { r.style.display = 'none'; });
      filtered.slice(start, end).forEach((r) => { r.style.display = ''; });

      if (summaryEl) {
        summaryEl.textContent = total === 0
          ? 'No matching rows.'
          : `Showing ${start + 1} to ${end} of ${total} entr${total === 1 ? 'y' : 'ies'}`;
      }

      renderPagination(totalPages);
      updateSortIndicators();
      updateClearFiltersVisibility();
      savePersistedState();
    }

    sortButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.sortKey;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          state.sortKey = key;
          state.sortType = btn.dataset.sortType || 'text';
          state.sortDir = 'asc';
        }
        render();
      });
    });

    filterChecks.forEach((cb) => {
      cb.addEventListener('change', () => {
        state.page = 1;
        render();
      });
    });

    if (clearFiltersEl) {
      clearFiltersEl.addEventListener('click', (e) => {
        e.preventDefault();
        filterChecks.forEach((cb) => { cb.checked = false; });
        if (searchInput) searchInput.value = '';
        state.search = '';
        state.page = 1;
        render();
      });
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        state.search = searchInput.value;
        state.page = 1;
        render();
      });
    }

    if (pageSizeEl) {
      pageSizeEl.value = String(defaultPageSize);
      pageSizeEl.addEventListener('change', () => {
        state.pageSize = parseInt(pageSizeEl.value, 10) || defaultPageSize;
        state.page = 1;
        render();
      });
    }

    render();
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table[data-datatable]').forEach(initTable);
  });
})();
