import base64
import binascii
import json
import re
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PRODUCT_NAME = "FinAlert"
PUBLIC_KEY_B64 = "BZJAOaC6q4bv74Jwhp8dIEoQPQUJh9YZCsAlVG6q6Is"


class LicenseError(ValueError):
    """A license key is invalid or expired."""


def _decode_segment(value, label):
    if not value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise LicenseError(f"The license key has an invalid {label}.")

    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded)
    except (ValueError, binascii.Error) as exc:
        raise LicenseError(f"The license key has an invalid {label}.") from exc


def verify_license_key(license_key):
    """Verify a signed license and return its payload."""
    parts = license_key.strip().split(".")
    if len(parts) != 3 or parts[0] != "FINALERT1":
        raise LicenseError("Enter a valid FinAlert license key.")

    payload_bytes = _decode_segment(parts[1], "payload")
    signature = _decode_segment(parts[2], "signature")
    public_key_bytes = _decode_segment(PUBLIC_KEY_B64, "public key")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, payload_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise LicenseError("This license key is not valid.") from exc

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseError("The license key contains unreadable data.") from exc

    if not isinstance(payload, dict):
        raise LicenseError("The license key contains invalid data.")

    if payload.get("product") != PRODUCT_NAME:
        raise LicenseError("This license key is for a different product.")

    for field in ("license_id", "customer", "issued_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise LicenseError("The license key is missing required information.")

    expires_at = payload.get("expires_at")
    if expires_at is not None:
        if not isinstance(expires_at, str):
            raise LicenseError("The license has an invalid expiration date.")

        try:
            expiration = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise LicenseError("The license has an invalid expiration date.") from exc

        if expiration.tzinfo is None:
            raise LicenseError("The license expiration must include a timezone.")

        if expiration.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise LicenseError("This license key has expired.")

    return payload
