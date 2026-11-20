import configparser
from pathlib import Path

from notifications.formatter import format_finance_notification
from notifications.telegram_client import TelegramClient, TelegramError


class NotificationService:
    def __init__(self, database, config_path):
        self.database = database
        self.config_path = Path(config_path)

        config = configparser.ConfigParser()
        config.read(self.config_path, encoding="utf-8")

        self.chat_id = config.get(
            "Telegram",
            "CHAT_ID",
            fallback="",
        ).strip()
        self.include_body = config.getboolean(
            "Telegram",
            "INCLUDE_EMAIL_BODY",
            fallback=True,
        )

        try:
            self.body_length = config.getint(
                "Telegram",
                "BODY_LENGTH",
                fallback=3000,
            )
        except ValueError:
            self.body_length = 3000

        self.body_length = max(0, min(self.body_length, 3000))
        self.telegram = TelegramClient(self.chat_id)

    def send_activities(self, account_id, activities, account_label=None):
        """Send unsent classified messages and return delivery counts."""
        result = {
            "sent": 0,
            "skipped": 0,
            "failed": 0,
        }

        for activity in activities:
            message = activity["message"]
            classification = activity["classification"]
            message_id = message.get("id")

            if not message_id:
                result["failed"] += 1
                continue

            if self.database.notification_was_sent(
                account_id,
                message_id,
                "telegram",
            ):
                result["skipped"] += 1
                continue

            self.database.record_notification(
                account_id,
                message_id,
                "telegram",
                "pending",
            )

            try:
                text = format_finance_notification(
                    message,
                    classification,
                    include_body=self.include_body,
                    body_length=self.body_length,
                    account_label=account_label,
                )
                self.telegram.send_message(text)
            except TelegramError:
                self.database.record_notification(
                    account_id,
                    message_id,
                    "telegram",
                    "failed",
                    error_code="telegram_delivery_failed",
                )
                result["failed"] += 1
                continue
            except Exception:
                self.database.record_notification(
                    account_id,
                    message_id,
                    "telegram",
                    "failed",
                    error_code="notification_processing_failed",
                )
                result["failed"] += 1
                continue

            self.database.record_notification(
                account_id,
                message_id,
                "telegram",
                "sent",
            )
            result["sent"] += 1

        return result
