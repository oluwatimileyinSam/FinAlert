import logging
import shutil
import subprocess
import sys
import webbrowser

import keyring
import msal


LOGGER = logging.getLogger(__name__)

KEYRING_SERVICE = "FinAlert"
KEYRING_USERNAME = "MicrosoftTokenCache"
SCOPES = ["User.Read", "Mail.Read"]


class AuthenticationError(Exception):
    """An authentication error that is safe to show in the app."""


def open_chrome_or_default(auth_url):
    """Open Microsoft sign-in in Chrome when available."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["open", "-a", "Google Chrome", auth_url],
                check=False,
                capture_output=True,
            )
            if result.returncode == 0:
                return

        elif sys.platform == "win32":
            chrome = shutil.which("chrome") or shutil.which("chrome.exe")
            if chrome:
                subprocess.Popen([chrome, auth_url], close_fds=True)
                return

        else:
            chrome = (
                shutil.which("google-chrome")
                or shutil.which("chrome")
                or shutil.which("chromium")
            )
            if chrome:
                subprocess.Popen([chrome, auth_url], close_fds=True)
                return

    except OSError:
        LOGGER.info("Chrome could not be opened; using the default browser.")

    webbrowser.open(auth_url, new=1)


class MicrosoftAuth:
    def __init__(self, client_id, authority="https://login.microsoftonline.com/common"):
        if not client_id or client_id == "REPLACE_WITH_APP_CLIENT_ID":
            raise AuthenticationError("The Microsoft application client ID is not configured.")

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
            on_before_launching_ui=open_chrome_or_default,
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
                on_before_launching_ui=open_chrome_or_default,
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
