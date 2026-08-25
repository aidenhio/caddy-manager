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
