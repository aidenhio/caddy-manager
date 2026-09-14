// BEGIN GLOBAL CONFIGURATION CADDYFILE EDITOR
// Wires up the Settings -> Caddy Settings -> Global Configuration tab: a
// CodeMirror-backed editor for the raw Caddyfile (falling back to a plain
// textarea if CodeMirror didn't load), plus a live check for whether the
// file actually imports this app's conf directory -- without that import
// line, blocks created in Caddy Manager are never picked up by Caddy.
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

  let cm = null;
  if (typeof CodeMirror !== "undefined") {
    const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    cm = CodeMirror.fromTextArea(textarea, {
      mode: "nginx",
      theme: isDark ? "material-darker" : "default",
      lineNumbers: true,
      lineWrapping: true,
      indentUnit: 2,
      tabSize: 2,
    });
    cm.on("change", () => updateImportCheck(cm.getValue()));

    // The Global Configuration tab starts hidden -- Settings opens on the
    // User tab -- and CodeMirror measures a 0-width/height container when
    // initialized while hidden, leaving the editor visually broken until
    // something forces a re-layout. Refresh it once its tab is actually
    // shown to fix that.
    const tabLink = document.querySelector('a[href="#global"][data-bs-toggle="tab"]');
    if (tabLink) {
      tabLink.addEventListener("shown.bs.tab", () => cm.refresh());
    }
  } else {
    // CodeMirror failed to load (e.g. offline/CDN blocked) -- the plain
    // textarea still works, just without syntax highlighting, so keep the
    // import check live off its own input event instead.
    textarea.addEventListener("input", () => updateImportCheck(textarea.value));
  }

  updateImportCheck(textarea.value);

  const form = document.getElementById("global-config-form");
  if (form) {
    form.addEventListener("submit", () => {
      // CodeMirror only writes back to the original textarea on save() --
      // without this the form would submit whatever was in the textarea
      // before CodeMirror took it over, i.e. none of what was typed since.
      if (cm) cm.save();
    });
  }
})();
// END GLOBAL CONFIGURATION CADDYFILE EDITOR
