"""Certificates page: recursively scans certificate_dir/certificates (Caddy's
own storage, keyed by issuer folder) and parses each cert. Read-only."""
import os
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
from cryptography.x509.oid import NameOID

from .configstore import get_certificate_dir, get_cert_expiring_soon_days

CERT_EXTENSIONS = (".crt", ".pem")


def certificates_root():
    certificate_dir = get_certificate_dir()
    return os.path.join(certificate_dir, "certificates") if certificate_dir else ""


def provider_for_issuer_dir(issuer_dir_name):
    """Human-readable provider name for an issuer folder name. Falls back
    to the raw folder name for an unrecognized ACME CA."""
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


def provider_key_for_issuer_dir(issuer_dir_name):
    """Stable key for the Provider filter checkboxes, independent of the
    varying display text. Unrecognized ACME CAs land in "other"."""
    name = (issuer_dir_name or "").lower()
    if name == "local":
        return "local"
    if "letsencrypt" in name:
        return "letsencrypt"
    if "zerossl" in name:
        return "zerossl"
    if "buypass" in name:
        return "buypass"
    return "other"


def _leaf_pem_block(content):
    """The first PEM block in `content` -- Caddy bundles the leaf cert with
    any intermediates, and only the leaf (first) is what we want."""
    marker = "-----END CERTIFICATE-----"
    end = content.find(marker)
    if end == -1:
        return None
    return content[: end + len(marker)]


def _all_dns_names(cert):
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        return san.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        return []


def _common_name(cert, dns_names):
    """The certificate's CN, falling back to its first SAN DNS name for
    certs issued without one (common for Let's Encrypt/ZeroSSL)."""
    attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if attrs:
        return attrs[0].value
    return dns_names[0] if dns_names else None


def _not_valid_after(cert):
    # Prefer the tz-aware accessor (newer cryptography); fall back to the naive one (always UTC).
    not_after = getattr(cert, "not_valid_after_utc", None)
    return not_after if not_after is not None else cert.not_valid_after.replace(tzinfo=timezone.utc)


def _not_valid_before(cert):
    not_before = getattr(cert, "not_valid_before_utc", None)
    return not_before if not_before is not None else cert.not_valid_before.replace(tzinfo=timezone.utc)


def _key_info(cert):
    """Human-readable key algorithm/size, for the detail modal."""
    pub = cert.public_key()
    if isinstance(pub, rsa.RSAPublicKey):
        return f"RSA {pub.key_size}-bit"
    if isinstance(pub, ec.EllipticCurvePublicKey):
        return f"ECDSA ({pub.curve.name})"
    if isinstance(pub, ed25519.Ed25519PublicKey):
        return "Ed25519"
    if isinstance(pub, ed448.Ed448PublicKey):
        return "Ed448"
    return type(pub).__name__


def _fingerprint_sha256(cert):
    digest = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def list_certificates():
    """Every certificate under certificate_dir/certificates, recursively.
    A file that fails to parse is silently skipped, not surfaced as an error."""
    certs_root = certificates_root()
    if not certs_root or not os.path.isdir(certs_root):
        return []

    expiring_soon_days = get_cert_expiring_soon_days()
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
            dns_names = _all_dns_names(cert)
            cn = _common_name(cert, dns_names) or fname

            # SAN entries other than the CN, for the +N badge, de-duplicated in order.
            extra_names = []
            for name in dns_names:
                if name != cn and name not in extra_names:
                    extra_names.append(name)

            not_before = _not_valid_before(cert)
            not_after = _not_valid_after(cert)
            expired = not_after <= now
            days_remaining = (not_after - now).days
            expiring_soon = (not expired) and days_remaining <= expiring_soon_days
            status = "expired" if expired else ("expiring_soon" if expiring_soon else "valid")

            certs.append({
                "cn": cn,
                "sans": extra_names,
                "provider": provider_for_issuer_dir(issuer_dir),
                "provider_key": provider_key_for_issuer_dir(issuer_dir),
                "path": fpath,
                "not_before": not_before.strftime("%d/%m/%Y %I:%M%p"),
                "expiry_ts": not_after.timestamp(),
                "expiry": not_after.strftime("%d/%m/%Y %I:%M%p"),
                "days_remaining": days_remaining,
                "expired": expired,
                "expiring_soon": expiring_soon,
                "status": status,
                "status_label": {"expired": "Expired", "expiring_soon": "Expiring soon", "valid": "Valid"}[status],
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial": format(cert.serial_number, "X"),
                "fingerprint": _fingerprint_sha256(cert),
                "key_info": _key_info(cert),
            })

    certs.sort(key=lambda c: c["cn"].lower())
    return certs


def certificate_stats(certs):
    """Total plus a per-status breakdown, for the dashboard's SSL
    Certificates widget and future certificate widgets."""
    return {
        "cert_total": len(certs),
        "cert_valid": sum(1 for c in certs if c["status"] == "valid"),
        "cert_expiring_soon": sum(1 for c in certs if c["status"] == "expiring_soon"),
        "cert_expired": sum(1 for c in certs if c["status"] == "expired"),
    }
