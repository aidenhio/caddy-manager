// Shared client-side form validation: native HTML5 required/minlength checks, shown with
// Bootstrap's per-field .is-invalid (not .was-validated, so valid fields stay unstyled).
// extraValidator plugs in fields that can't use `required`.

// Marks each field that fails its native checks with .is-invalid and clears the rest.
// Disabled fields (including inside a disabled fieldset) never validate, so they're cleared too.
function refreshInvalidFields(form) {
  form.querySelectorAll("input, select, textarea").forEach((field) => {
    field.classList.toggle("is-invalid", field.willValidate && !field.checkValidity());
  });
}

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
    // From the first Save on, invalid fields are flagged and kept up to date as they're edited.
    form.dataset.validated = "true";
    refreshInvalidFields(form);
  });
  const refreshIfValidated = () => {
    if (form.dataset.validated) refreshInvalidFields(form);
  };
  form.addEventListener("input", refreshIfValidated);
  form.addEventListener("change", refreshIfValidated);
  // A reset restores values but not invalid styling; clear it so the form looks untouched.
  form.addEventListener("reset", () => {
    delete form.dataset.validated;
    form.querySelectorAll(".is-invalid").forEach((field) => field.classList.remove("is-invalid"));
  });
}

// Keeps two password-style fields in sync: `field` is marked invalid (via the
// Constraint Validation API) whenever both are filled in but don't match.
function wireMatchingFields(field, otherField, message) {
  function check() {
    field.setCustomValidity(field.value && otherField.value && field.value !== otherField.value ? message : "");
  }
  field.addEventListener("input", check);
  otherField.addEventListener("input", check);
}

// Root-directory-or-custom-paths toggle shared by Setup and Settings Directories.
// pathSuffixes maps each field id to its name under the root (e.g. { conf_dir: 'caddy.d' }).
const DIRECTORY_TOGGLE_DEFAULT_ROOT = "/etc/caddy";

function wireDirectoryToggle(formId, rootId, toggleId, pathSuffixes) {
  const form = document.getElementById(formId);
  const rootInput = document.getElementById(rootId);
  const toggle = document.getElementById(toggleId);
  if (!form || !rootInput || !toggle) return;

  const inputs = Object.fromEntries(
    Object.keys(pathSuffixes).map((id) => [id, document.getElementById(id)])
  );

  // Only fires from the root field, which is disabled in custom mode -- no need to gate on toggle.checked.
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
      // Custom mode has no root directory; clear the field so it doesn't show a stale value.
      rootInput.value = "";
    } else if (!rootInput.value.trim()) {
      // Seed a sensible default so there's immediately something to derive paths from.
      rootInput.value = DIRECTORY_TOGGLE_DEFAULT_ROOT;
      deriveFromRoot();
    }
    Object.values(inputs).forEach((el) => { el.disabled = !custom; });
  }

  rootInput.addEventListener("input", deriveFromRoot);
  toggle.addEventListener("change", syncToggle);

  // Disabled fields don't submit -- briefly re-enable everything right before submit.
  form.addEventListener("submit", () => {
    rootInput.disabled = false;
    Object.values(inputs).forEach((el) => { el.disabled = false; });
  });

  // Reset applies its default action after this event dispatches, so defer the fixup a tick.
  form.addEventListener("reset", () => setTimeout(syncToggle, 0));
}
