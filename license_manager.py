import json
import os
import secrets
import sys
import time
import uuid

import requests

from app_config import application_data_directory


LICENSE_API_BASE_URL = "https://finalert-licensing-api.finalert.workers.dev"
ONLINE_CHECK_INTERVAL = 24 * 60 * 60
OFFLINE_GRACE_PERIOD = 7 * 24 * 60 * 60
REQUEST_TIMEOUT = (5, 15)


class LicenseError(Exception):
    def __init__(self, message, retryable=False, code=None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class LicenseManager:
    def __init__(self):
        self.data_directory = application_data_directory()
        self.device_id_path = self.data_directory / "license_device_id"
        self.license_path = self.data_directory / "license.json"
        self.pending_path = self.data_directory / "license_pending.json"

    def _write_private_file(self, path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f".{path.name}.tmp")
        temporary_path.write_text(contents, encoding="utf-8")

        if os.name != "nt":
            temporary_path.chmod(0o600)

        os.replace(temporary_path, path)

    def _write_json(self, path, data):
        self._write_private_file(
            path,
            json.dumps(data, indent=2) + "\n",
        )

    def _read_json(self, path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise LicenseError(
                f"FinAlert could not read its saved license data: {path.name}."
            ) from exc

        if not isinstance(value, dict):
            raise LicenseError(
                f"FinAlert's saved license data is invalid: {path.name}."
            )

        return value

    def _get_device_id(self):
        try:
            device_id = self.device_id_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            device_id = ""

        if device_id:
            try:
                uuid.UUID(hex=device_id)
            except ValueError as exc:
                raise LicenseError(
                    "FinAlert's saved device identity is unreadable. "
                    "The license is locked to this device; contact support."
                ) from exc
            return device_id

        device_id = uuid.uuid4().hex
        self._write_private_file(self.device_id_path, device_id)
        return device_id

    @staticmethod
    def _platform():
        if sys.platform == "darwin":
            return "macos"
        if sys.platform == "win32":
            return "windows"
        return "unknown"

    def _request(self, endpoint, payload):
        try:
            response = requests.post(
                f"{LICENSE_API_BASE_URL}{endpoint}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LicenseError(
                "FinAlert could not reach the license service.",
                retryable=True,
            ) from exc

        try:
            result = response.json()
        except ValueError:
            result = {}

        if response.status_code == 200 and result.get("status") == "active":
            return result

        code = result.get("error", "")
        messages = {
            "license_not_valid": "That license key is invalid or revoked.",
            "license_expired": "That license has expired.",
            "license_locked_to_another_device": (
                "That license key is locked to another device."
            ),
            "license_already_redeemed": (
                "That license key has already been redeemed."
            ),
            "activation_not_valid": (
                "FinAlert's saved activation is no longer valid."
            ),
            "activation_locked_to_another_device": (
                "FinAlert's activation is locked to another device."
            ),
            "service_not_configured": (
                "The license service is being configured. Try again later."
            ),
        }

        retryable = (
            response.status_code >= 500
            or response.status_code == 429
            or code == "service_not_configured"
        )

        message = messages.get(
            code,
            "FinAlert could not validate the license. Try again later.",
        )
        raise LicenseError(message, retryable=retryable, code=code)

    def _redeem_pending_activation(self, pending):
        return self._request(
            "/api/activate",
            {
                "license_key": pending["license_key"],
                "activation_token": pending["activation_token"],
                "device_id": self._get_device_id(),
                "platform": self._platform(),
            },
        )

    def _validate_activation(self, activation_token):
        return self._request(
            "/api/validate",
            {
                "activation_token": activation_token,
                "device_id": self._get_device_id(),
            },
        )

    def _remove_pending_activation(self):
        try:
            self.pending_path.unlink()
        except FileNotFoundError:
            pass

    def _finish_pending_activation(self, pending):
        try:
            try:
                result = self._validate_activation(
                    pending["activation_token"],
                )
            except LicenseError as exc:
                if exc.code != "activation_not_valid":
                    raise
                result = self._redeem_pending_activation(pending)

            license_id = result.get("license_id")
            if not license_id:
                raise LicenseError(
                    "The license service returned an incomplete activation."
                )

            self._write_json(
                self.license_path,
                {
                    "activation_token": pending["activation_token"],
                    "license_id": license_id,
                    "last_validated_at": time.time(),
                },
            )
            self._remove_pending_activation()
            return True
        except LicenseError as exc:
            if not exc.retryable:
                self._remove_pending_activation()
            raise

    def activate(self, license_key):
        """Redeem a key once and save the device-bound activation token."""
        key = str(license_key).strip().upper()
        if not key:
            raise LicenseError("Enter a license key.")

        existing_pending = self._read_json(self.pending_path)
        if existing_pending is not None:
            raise LicenseError(
                "A previous activation is still pending. Connect to the "
                "internet and restart FinAlert to finish it."
            )

        if self.license_path.exists():
            try:
                self.check_saved_license()
            except LicenseError as exc:
                if exc.retryable:
                    raise
            else:
                raise LicenseError(
                    "FinAlert is already activated on this device."
                )

        pending = {
            "license_key": key,
            "activation_token": secrets.token_urlsafe(32),
        }

        self._write_json(self.pending_path, pending)
        self._finish_pending_activation(pending)

    def check_saved_license(self):
        """Check the saved activation, allowing a limited offline grace."""
        pending = self._read_json(self.pending_path)
        if pending is not None:
            if (
                not isinstance(pending.get("license_key"), str)
                or not isinstance(pending.get("activation_token"), str)
            ):
                raise LicenseError("FinAlert's pending activation is invalid.")
            return self._finish_pending_activation(pending)

        state = self._read_json(self.license_path)
        if state is None:
            raise LicenseError("Enter a license key to activate FinAlert.")

        activation_token = state.get("activation_token")
        last_validated_at = state.get("last_validated_at")

        if (
            not isinstance(activation_token, str)
            or not isinstance(last_validated_at, (int, float))
        ):
            raise LicenseError("FinAlert's saved activation is invalid.")

        now = time.time()
        age = now - float(last_validated_at)

        if 0 <= age < ONLINE_CHECK_INTERVAL:
            return True

        try:
            result = self._validate_activation(activation_token)
        except LicenseError as exc:
            if exc.retryable and 0 <= age <= OFFLINE_GRACE_PERIOD:
                return True
            if exc.retryable:
                raise LicenseError(
                    "FinAlert needs an internet connection to renew its "
                    "activation.",
                    retryable=True,
                    code=exc.code,
                ) from exc
            raise

        state["license_id"] = result.get(
            "license_id",
            state.get("license_id"),
        )
        state["last_validated_at"] = now
        self._write_json(self.license_path, state)
        return True
