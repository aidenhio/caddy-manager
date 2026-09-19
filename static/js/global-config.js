// BEGIN GLOBAL CONFIGURATION CADDYFILE EDITOR
// Live check for whether the Caddyfile imports this app's conf directory --
// without that import line, blocks created here are never loaded by Caddy.
(function () {
  const textarea = document.getElementById("caddyfile-content");
  if (!textarea) return;

  const confDir = textarea.dataset.confDir || "";
  const importCheck = document.getElementById("conf-import-check");
  const foundBadge = importCheck ? importCheck.querySelector('[data-state="found"]') : null;
  const missingBadge = importCheck ? importCheck.querySelector('[data-state="missing"]') : null;

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // Matches `import /path/to/caddy.d/*.conf` in its reasonable variants
  // (quoted, with/without .conf), plus a relative import by directory basename alone.
  function buildImportPattern(dir) {
    const normalized = dir.replace(/[/\\]+$/, "");
    const segments = normalized.split(/[/\\]+/).filter(Boolean);
    const basename = segments[segments.length - 1] || normalized;
    const alternatives = [escapeRegExp(normalized)];
    if (basename !== normalized) alternatives.push(escapeRegExp(basename));
    return new RegExp(
      '^\\s*import\\s+"?(?:\\./)?(?:' + alternatives.join("|") + ")[/\\\\]?\\*(\\.conf)?\"?\\s*$",
      "m"
    );
  }

  function updateImportCheck(content) {
    if (!confDir || !foundBadge || !missingBadge) return;
    const found = buildImportPattern(confDir).test(content);
    foundBadge.hidden = !found;
    missingBadge.hidden = found;
  }

  textarea.addEventListener("input", () => updateImportCheck(textarea.value));
  updateImportCheck(textarea.value);
})();
// END GLOBAL CONFIGURATION CADDYFILE EDITOR
