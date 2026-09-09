// Shared client-side form validation, used by every form in the app (login,
// settings, block_form) so they all behave and look the same: native HTML5
// `required`/`minlength` attributes drive Bootstrap's `.was-validated` /
// `:invalid` styling, with `.invalid-feedback` text shown underneath each
// field. Fields that can't use a native `required` attribute (e.g. the site
// address chip widget in block_form.html) plug in via the optional extraValidator
// callback so they still block submission and get the same is-invalid look.

function initFormValidation(form, extraValidator) {
  if (!form) return;
  form.setAttribute("novalidate", "novalidate");
  form.addEventListener("submit", (event) => {
    const nativeValid = form.checkValidity();
    const extraValid = typeof extraValidator === "function" ? extraValidator() : true;
    if (!nativeValid || !extraValid) {
      event.preventDefault();
      event.stopPropagation();
    }
    form.classList.add("was-validated");
  });
  // A <button type="reset"> (e.g. a "Cancel" button) restores field values
  // but leaves any invalid styling from a previous failed submit attempt in
  // place -- clear it so a cancelled/reset form looks untouched again.
  form.addEventListener("reset", () => form.classList.remove("was-validated"));
}

// Keeps two password-style fields in sync via the Constraint Validation API:
// `field` is marked invalid (with `message`) whenever it and `otherField`
// are both filled in but don't match.
function wireMatchingFields(field, otherField, message) {
  function check() {
    field.setCustomValidity(field.value && otherField.value && field.value !== otherField.value ? message : "");
  }
  field.addEventListener("input", check);
  otherField.addEventListener("input", check);
}

// Wires up the "derive paths from a root directory, or set them
// individually" pattern shared by the Setup page and the Settings
// Directories tab: a root directory field and a "Set custom directories"
// switch are mutually exclusive (exactly one is enabled at a time), and the
// path fields live-update from the root directory as it's typed.
// `pathSuffixes` maps each path field's id to what it's called under the
// root directory (e.g. { conf_dir: 'caddy.d' }).
const DIRECTORY_TOGGLE_DEFAULT_ROOT = "/etc/caddy";

function wireDirectoryToggle(formId, rootId, toggleId, pathSuffixes) {
  const form = document.getElementById(formId);
  const rootInput = document.getElementById(rootId);
  const toggle = document.getElementById(toggleId);
  if (!form || !rootInput || !toggle) return;

  const inputs = Object.fromEntries(
    Object.keys(pathSuffixes).map((id) => [id, document.getElementById(id)])
  );

  // Only fires from user input on the root field, which is only reachable
  // when the toggle is off (the root field is disabled while custom
  // directories are active) -- no need to gate on toggle.checked here.
  function deriveFromRoot() {
    const root = rootInput.value.trim().replace(/[/\\]+$/, "");
    Object.entries(inputs).forEach(([id, el]) => {
      el.value = root ? `${root}/${pathSuffixes[id]}` : "";
    });
  }

  function syncToggle() {
    const custom = toggle.checked;
    rootInput.disabled = custom;
    if (custom) {
      // Custom directories mean no root directory -- clear it so the field
      // (and, once saved, the config) reflects that rather than showing a
      // stale value that no longer has any effect.
      rootInput.value = "";
    } else if (!rootInput.value.trim()) {
      // Switching back from custom (where root was null) shouldn't leave
      // the now-active root field empty -- seed it with a sensible default
      // so there's immediately something valid to derive paths from.
      rootInput.value = DIRECTORY_TOGGLE_DEFAULT_ROOT;
      deriveFromRoot();
    }
    Object.values(inputs).forEach((el) => { el.disabled = !custom; });
  }

  rootInput.addEventListener("input", deriveFromRoot);
  toggle.addEventListener("change", syncToggle);

  // Disabled fields are excluded from form submission -- briefly re-enable
  // everything right before submit so the current values (root-derived or
  // custom, whichever is showing) are sent to the server.
  form.addEventListener("submit", () => {
    rootInput.disabled = false;
    Object.values(inputs).forEach((el) => { el.disabled = false; });
  });

  // A reset (e.g. a "Cancel" button) restores field values/checked state as
  // its default action *after* this event finishes dispatching, so the
  // toggle's checked state isn't reliably readable yet inside this handler
  // -- defer the enabled/disabled fixup to the next tick, once the browser
  // has actually applied the reset.
  form.addEventListener("reset", () => setTimeout(syncToggle, 0));
}
