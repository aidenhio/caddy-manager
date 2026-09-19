// BEGIN CERTIFICATE DETAIL MODAL
// Fills the shared modal from the triggering row's data-cert-* attributes
// (event.relatedTarget), so one modal serves every row instead of one per certificate.
(function () {
  const modal = document.getElementById('certificate-detail-modal');
  if (!modal) return;

  const fieldEls = {};
  modal.querySelectorAll('[data-field]').forEach((el) => {
    fieldEls[el.dataset.field] = el;
  });

  function setField(name, value) {
    const el = fieldEls[name];
    if (el) el.textContent = value || '';
  }

  modal.addEventListener('show.bs.modal', (event) => {
    const button = event.relatedTarget;
    if (!button) return;
    const d = button.dataset;

    setField('cn', d.certCn);
    setField('status', d.certStatusLabel);
    setField('provider', d.certProvider);
    setField('not-before', d.certNotBefore);
    setField('expiry', d.certExpiry);
    setField('days-remaining', d.certDaysRemaining);
    setField('key-info', d.certKeyInfo);
    setField('serial', d.certSerial);
    setField('fingerprint', d.certFingerprint);
    setField('subject', d.certSubject);
    setField('issuer', d.certIssuer);
    setField('sans', d.certSans);
    setField('path', d.certPath);
  });
})();
// END CERTIFICATE DETAIL MODAL
