"""Certificates page: recursively scanning certificate_dir/certificates
for the leaf certificate Caddy (via its certmagic storage layer) keeps
per site, and parsing each one (with the `cryptography` library) to
surface its common name, issuing provider, and expiry. Read-only --
nothing in this module writes to that directory.

Caddy's on-disk layout there is:

    <certificate_dir>/certificates/
    |- local/                                        -- Caddy's own internal CA
    |  |- app.example.com/
    |     |- app.example.com.crt
    |     |- app.example.com.key
    |- acme-v02.api.letsencrypt.org-directory/        -- Let's Encrypt (production)
       |- app2.example.com/
          |- app2.example.com.crt
          |- app2.example.com.key

The top-level folder under certificates/ is keyed by issuer (Caddy's
"local" internal CA, or an ACME CA's directory URL) -- that's what
determines the Provider column below.
"""
import os
from datetime import datetime, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID

from .configstore import get_certificate_dir

CERT_EXTENSIONS = (".crt", ".pem")
EXPIRY_WARNING_DAYS = 14


def certificates_root():
    certificate_dir = get_certificate_dir()
    return os.path.join(certificate_dir, "certificates") if certificate_dir else ""


def provider_for_issuer_dir(issuer_dir_name):
    """Human-readable provider name for an issuer folder name, per the
    layout above. Falls back to showing the raw folder name for an ACME
    CA this app doesn't specifically recognize, rather than hiding it
    behind a generic label."""
    name = (issuer_dir_name or "").lower()
    if name == "local":
        return "Local"
    if "letsencrypt" in name:
        return "Let's Encrypt (staging)" if "staging" in name else "Let's Encrypt"
    if "zerossl" in name:
        return "ZeroSSL"
    if "buypass" in name:
        return "Buypass"
    return issuer_dir_name or "Unknown"


def _leaf_pem_block(content):
    """The first PEM certificate block in `content` -- a Caddy-written
    .crt file bundles the leaf certificate together with any
    intermediates, and only the first (the site's own certificate, i.e.
    the leaf) is what CN/expiry should be read from."""
    marker = "-----END CERTIFICATE-----"
    end = content.find(marker)
    if end == -1:
        return None
    return content[: end + len(marker)]


def _common_name(cert):
    """The certificate's CN, falling back to its first SAN DNS name for
    a certificate issued without one (increasingly common practice for
    publicly-trusted certs, which Let's Encrypt/ZeroSSL both do)."""
    attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if attrs:
        return attrs[0].value
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        if dns_names:
            return dns_names[0]
    except x509.ExtensionNotFound:
        pass
    return None


def _not_valid_after(cert):
    # not_valid_after_utc (timezone-aware) is the non-deprecated accessor
    # on newer `cryptography` releases; fall back to the naive one (always
    # UTC per the X.509 spec) for older versions that don't have it.
    not_after = getattr(cert, "not_valid_after_utc", None)
    if not_after is not None:
        return not_after
    return cert.not_valid_after.replace(tzinfo=timezone.utc)


def list_certificates():
    """Every certificate found under certificate_dir/certificates,
    recursively -- one row per .crt/.pem file that parses successfully.
    A file that fails to parse (not a certificate, corrupt, mid-write)
    is silently skipped rather than surfaced as an error, since this is
    Caddy's own directory and may hold other bookkeeping this app has no
    business about (*.json metadata, lock files). Returns [] if no
    certificate directory is configured or certificates/ doesn't exist
    yet under it."""
    certs_root = certificates_root()
    if not certs_root or not os.path.isdir(certs_root):
        return []

    now = datetime.now(timezone.utc)
    certs = []
    for dirpath, _dirnames, filenames in os.walk(certs_root):
        for fname in filenames:
            if not fname.lower().endswith(CERT_EXTENSIONS):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "rb") as f:
                    raw = f.read()
            except OSError:
                continue

            pem_block = _leaf_pem_block(raw.decode("utf-8", errors="ignore"))
            if not pem_block:
                continue
            try:
                cert = x509.load_pem_x509_certificate(pem_block.encode("utf-8"))
            except ValueError:
                continue

            issuer_dir = os.path.relpath(fpath, certs_root).split(os.sep)[0]
            not_after = _not_valid_after(cert)
            expired = not_after <= now
            days_remaining = (not_after - now).total_seconds() / 86400

            certs.append({
                "cn": _common_name(cert) or fname,
                "provider": provider_for_issuer_dir(issuer_dir),
                "path": fpath,
                "expiry_ts": not_after.timestamp(),
                "expiry": not_after.strftime("%d/%m/%Y %I:%M%p"),
                "expired": expired,
                "expiring_soon": (not expired) and days_remaining <= EXPIRY_WARNING_DAYS,
            })

    certs.sort(key=lambda c: c["cn"].lower())
    return certs
