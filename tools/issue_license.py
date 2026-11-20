import argparse
import base64
import getpass
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PRIVATE_KEY_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "FinAlert"
    / "license_issuer"
    / "private_key.pem"
)


def encode_segment(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def main():
    parser = argparse.ArgumentParser(
        description="Issue a signed FinAlert license key."
    )
    parser.add_argument(
        "--customer",
        required=True,
        help="Name associated with this license.",
    )
    args = parser.parse_args()

    if not PRIVATE_KEY_PATH.is_file():
        print(f"Private signing key not found: {PRIVATE_KEY_PATH}", file=sys.stderr)
        return 1

    passphrase = getpass.getpass("License signing key passphrase: ")

    try:
        private_key = serialization.load_pem_private_key(
            PRIVATE_KEY_PATH.read_bytes(),
            password=passphrase.encode("utf-8"),
        )
    except (TypeError, ValueError) as exc:
        print("Could not unlock the signing key.", file=sys.stderr)
        return 1

    if not isinstance(private_key, Ed25519PrivateKey):
        print("The signing key is not an Ed25519 key.", file=sys.stderr)
        return 1

    payload = {
        "product": "FinAlert",
        "license_id": str(uuid.uuid4()),
        "customer": args.customer.strip(),
        "issued_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "expires_at": None,
    }

    if not payload["customer"]:
        print("Customer name cannot be blank.", file=sys.stderr)
        return 1

    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = private_key.sign(payload_bytes)
    license_key = (
        f"FINALERT1.{encode_segment(payload_bytes)}.{encode_segment(signature)}"
    )

    print(f"License issued for: {payload['customer']}")
    print(license_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
