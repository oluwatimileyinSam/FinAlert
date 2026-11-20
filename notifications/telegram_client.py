import re

import keyring
import requests


KEYRING_SERVICE = "FinAlert.Telegram"
KEYRING_USERNAME = "BotToken"
TELEGRAM_API = "https://api.telegram.org"
BOT_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
MAX_MESSAGE_LENGTH = 4096
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


class TelegramError(Exception):
    """A safe Telegram configuration or delivery error."""


class TelegramClient:
    def __init__(self, chat_id=None, bot_token=None, timeout=20):
        self.chat_id = self._validate_chat_id(chat_id, required=False)
        self.timeout = timeout
        self.session = requests.Session()

        if bot_token is None:
            try:
                bot_token = keyring.get_password(
                    KEYRING_SERVICE,
                    KEYRING_USERNAME,
                )
            except Exception:
                raise TelegramError(
                    "FinAlert could not access the Telegram token in "
                    "the operating system credential store."
                ) from None

        self.bot_token = self._validate_bot_token(bot_token)

    @classmethod
    def save_bot_token(cls, bot_token):
        """Save the token in the operating system credential store."""
        token = cls._validate_bot_token(bot_token)
        try:
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_USERNAME,
                token,
            )
        except Exception:
            raise TelegramError(
                "FinAlert could not save the Telegram token securely."
            ) from None

    @classmethod
    def remove_bot_token(cls):
        """Remove the stored bot token."""
        try:
            keyring.delete_password(
                KEYRING_SERVICE,
                KEYRING_USERNAME,
            )
        except keyring.errors.PasswordDeleteError:
            return
        except Exception:
            raise TelegramError(
                "FinAlert could not remove the Telegram token."
            ) from None

    def get_recent_chats(self):
        """Find chat IDs from recent messages sent to the bot."""
        updates = self._request(
            "getUpdates",
            {
                "limit": 100,
                "timeout": 0,
                "allowed_updates": [
                    "message",
                    "edited_message",
                    "channel_post",
                ],
            },
        )

        if not isinstance(updates, list):
            raise TelegramError(
                "Telegram returned an unexpected updates response."
            )

        chats = {}
        for update in updates:
            message = (
                update.get("message")
                or update.get("edited_message")
                or update.get("channel_post")
            )
            if not isinstance(message, dict):
                continue

            chat = message.get("chat")
            if not isinstance(chat, dict) or chat.get("id") is None:
                continue

            chat_id = str(chat["id"])
            display_name = (
                chat.get("title")
                or chat.get("username")
                or chat.get("first_name")
                or chat.get("type")
                or "Telegram chat"
            )
            chats[chat_id] = {
                "id": chat_id,
                "name": display_name,
                "type": chat.get("type", "unknown"),
            }

        return list(chats.values())

    def test_connection(self):
        """Check that the saved bot token is accepted by Telegram."""
        return self._request("getMe", {})

    def send_message(self, text):
        """Send one plain-text Telegram message to the configured chat."""
        if self.chat_id is None:
            raise TelegramError("Set a Telegram destination before sending.")

        if not isinstance(text, str) or not text.strip():
            raise TelegramError("The Telegram message cannot be empty.")

        if len(text) > MAX_MESSAGE_LENGTH:
            raise TelegramError(
                "The Telegram message is too long. Shorten its email excerpt."
            )

        return self._request(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )

    def send_document(self, filename, content):
        """Upload one PDF document to the configured Telegram chat."""
        if self.chat_id is None:
            raise TelegramError("Set a Telegram destination before sending.")

        if not isinstance(content, (bytes, bytearray)) or not content:
            raise TelegramError("The PDF attachment has no readable content.")

        content = bytes(content)
        if len(content) > MAX_DOCUMENT_BYTES:
            raise TelegramError(
                "The PDF is larger than Telegram's 50 MB document limit."
            )

        safe_name = str(filename or "attachment.pdf")
        safe_name = safe_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        safe_name = "".join(char for char in safe_name if char.isprintable())
        if not safe_name:
            safe_name = "attachment.pdf"
        if not safe_name.casefold().endswith(".pdf"):
            safe_name += ".pdf"

        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendDocument"

        try:
            response = self.session.post(
                url,
                data={"chat_id": self.chat_id},
                files={
                    "document": (
                        safe_name,
                        content,
                        "application/pdf",
                    ),
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise TelegramError(
                "Could not connect to Telegram to send the PDF."
            ) from None

        if response.status_code != 200:
            raise TelegramError(
                f"Telegram returned HTTP {response.status_code} for the PDF."
            )

        try:
            result = response.json()
        except ValueError:
            raise TelegramError(
                "Telegram returned an unreadable response for the PDF."
            ) from None

        if not isinstance(result, dict) or not result.get("ok"):
            raise TelegramError(
                "Telegram rejected the PDF upload. Check the bot and chat settings."
            )

        return result.get("result")

    def _request(self, method, payload):
        url = f"{TELEGRAM_API}/bot{self.bot_token}/{method}"

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise TelegramError(
                "Could not connect to Telegram. Check your internet connection."
            ) from None

        if response.status_code != 200:
            raise TelegramError(
                f"Telegram returned HTTP {response.status_code}."
            )

        try:
            result = response.json()
        except ValueError:
            raise TelegramError(
                "Telegram returned an unreadable response."
            ) from None

        if not isinstance(result, dict) or not result.get("ok"):
            raise TelegramError(
                "Telegram rejected the request. Check the bot and chat settings."
            )

        return result.get("result")

    @staticmethod
    def _validate_bot_token(bot_token):
        if not isinstance(bot_token, str):
            raise TelegramError("Enter a Telegram bot token.")

        token = bot_token.strip()
        if not BOT_TOKEN_RE.fullmatch(token):
            raise TelegramError("The Telegram bot token format is invalid.")

        return token

    @staticmethod
    def _validate_chat_id(chat_id, required=True):
        if chat_id is None:
            if required:
                raise TelegramError("Set CHAT_ID in fin_alert.ini.")
            return None

        value = str(chat_id).strip()
        if not value:
            if required:
                raise TelegramError("Set CHAT_ID in fin_alert.ini.")
            return None

        if len(value) > 128 or any(char.isspace() for char in value):
            raise TelegramError("The Telegram chat ID is invalid.")

        return value
