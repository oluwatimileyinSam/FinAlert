import logging
import os
import shutil
import sys
import webbrowser
from pathlib import Path

import keyring
import msal


LOGGER = logging.getLogger(__name__)

KEYRING_SERVICE = "FinAlert"
KEYRING_USERNAME = "MicrosoftTokenCache"
SCOPES = ["User.Read", "Mail.Read"]


class AuthenticationError(Exception):
    """An authentication error that is safe to show in the app."""


def find_chrome():
    """Find a Chrome executable on macOS, Windows, or Linux."""
    chrome_from_path = (
        shutil.which("chrome")
        or shutil.which("chrome.exe")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
    )
    if chrome_from_path:
        return chrome_from_path

    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    elif sys.platform == "win32":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google/Chrome/Application/chrome.exe",
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
        ]

    return next((str(path) for path in candidates if path.is_file()), None)


def prepare_browser(**kwargs):
    """Prefer Chrome for MSAL's browser launch, with a system-browser fallback."""
    if kwargs.get("ui") != "browser":
        return

    chrome = find_chrome()
    if not chrome:
        LOGGER.info("Chrome was not found; MSAL will use the default browser.")
        return

    webbrowser.register(
        "fin_alert_chrome",
        None,
        webbrowser.BackgroundBrowser(chrome),
        preferred=True,
    )


class MicrosoftAuth:
    def __init__(
        self,
        client_id,
        authority="https://login.microsoftonline.com/common",
    ):
        if not client_id or client_id == "REPLACE_WITH_APP_CLIENT_ID":
            raise AuthenticationError(
                "The Microsoft application client ID is not configured."
            )

        self.cache = msal.SerializableTokenCache()

        try:
            saved_cache = keyring.get_password(
                KEYRING_SERVICE,
                KEYRING_USERNAME,
            )
            if saved_cache:
                self.cache.deserialize(saved_cache)
        except Exception as exc:
            LOGGER.exception("Could not read the protected Microsoft token cache")
            raise AuthenticationError(
                "FinAlert could not access the saved sign-in cache."
            ) from exc

        self.client = msal.PublicClientApplication(
            client_id=client_id,
            authority=authority,
            token_cache=self.cache,
        )

    def accounts(self):
        """Return the independently signed-in Microsoft accounts."""
        return self.client.get_accounts()

    def connect(self):
        """Sign in a Microsoft account using MSAL's interactive PKCE flow."""
        result = self.client.acquire_token_interactive(
            scopes=SCOPES,
            prompt="select_account",
            on_before_launching_ui=prepare_browser,
        )

        if "access_token" not in result:
            error_code = result.get("error", "sign_in_failed")
            LOGGER.warning("Microsoft sign-in failed (%s)", error_code)
            description = result.get("error_description", error_code)
            raise AuthenticationError(f"Microsoft sign-in failed: {description}")

        self._save_cache()
        return result

    def acquire_for(self, account):
        """Get a token silently when possible, otherwise request sign-in."""
        result = self.client.acquire_token_silent(SCOPES, account=account)

        if result is None:
            result = self.client.acquire_token_interactive(
                scopes=SCOPES,
                account=account,
                prompt="select_account",
                on_before_launching_ui=prepare_browser,
            )

        if "access_token" not in result:
            error_code = result.get("error", "sign_in_failed")
            LOGGER.warning("Microsoft token renewal failed (%s)", error_code)
            description = result.get("error_description", error_code)
            raise AuthenticationError(f"Microsoft sign-in is required: {description}")

        self._save_cache()
        return result

    def disconnect(self, home_account_id):
        """Remove only the selected account from the local MSAL cache."""
        account = next(
            (
                item
                for item in self.accounts()
                if item.get("home_account_id") == home_account_id
            ),
            None,
        )

        if account is not None:
            self.client.remove_account(account)
            self._save_cache()

    def _save_cache(self):
        if not self.cache.has_state_changed:
            return

        try:
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_USERNAME,
                self.cache.serialize(),
            )
        except Exception as exc:
            LOGGER.exception("Could not save the protected Microsoft token cache")
            raise AuthenticationError(
                "FinAlert could not save the sign-in cache securely."
            ) from exc
