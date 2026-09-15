// BEGIN GLOBAL CONFIGURATION CADDYFILE EDITOR
// Wires up the Settings -> Caddy Settings -> Global Configuration tab: a
// live check for whether the raw Caddyfile actually imports this app's conf
// directory -- without that import line, blocks created in Caddy Manager
// are never picked up by Caddy. Plain textarea, no code editor library.
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

  // Matches a line such as `import /etc/caddy/caddy.d/*.conf` -- optionally
  // quoted, with or without a trailing slash before the glob, and with or
  // without the .conf extension on it -- covering the reasonable ways
  // someone would write the import line Caddy needs to actually load the
  // blocks this app manages. Also accepts a relative import using just the
  // conf directory's own name (e.g. `import caddy.d/*.conf`, optionally
  // `./`-prefixed) -- Caddy resolves relative import paths against the
  // Caddyfile's own directory, which for the default layout is exactly one
  // level above the conf directory, so the directory's basename alone is a
  // valid import too.
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
