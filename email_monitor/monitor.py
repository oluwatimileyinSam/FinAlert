import configparser
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from authentication.microsoft import AuthenticationError, MicrosoftAuth
from email_monitor.pipeline import FinanceScanner, default_database_path
from notifications.service import NotificationService
from notifications.telegram_client import TelegramError
from storage.database import FinanceDatabase


LOGGER = logging.getLogger(__name__)


class MonitorWorker(QThread):
    scan_completed = Signal(dict)
    scan_failed = Signal(str)

    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.config_path = Path(config_path)
        self._stop_event = threading.Event()
        self.interval_seconds = self._read_interval()

    def _read_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_path, encoding="utf-8")
        return config

    def _read_interval(self):
        config = self._read_config()
        try:
            seconds = config.getint(
                "Monitoring",
                "CHECK_INTERVAL_SECONDS",
                fallback=60,
            )
        except ValueError:
            seconds = 60

        return max(15, min(seconds, 3600))

    def request_stop(self):
        """Ask the worker to stop after its current request finishes."""
        self._stop_event.set()

    def scan_once(self):
        """Perform one incremental check across connected accounts."""
        config = self._read_config()

        client_id = config.get(
            "Microsoft",
            "CLIENT_ID",
            fallback="",
        ).strip()
        authority = config.get(
            "Microsoft",
            "AUTHORITY",
            fallback="https://login.microsoftonline.com/common",
        ).strip()

        if not client_id:
            raise AuthenticationError(
                "The Microsoft application client ID is not configured."
            )

        authentication = MicrosoftAuth(client_id, authority)
        database = FinanceDatabase(default_database_path())
        scanner = FinanceScanner(authentication, database)

        result = {
            "accounts_checked": 0,
            "accounts_failed": 0,
            "messages_scanned": 0,
            "finance_messages_found": 0,
            "notifications_sent": 0,
            "notifications_skipped": 0,
            "notifications_failed": 0,
        }

        accounts = authentication.accounts()
        for account in accounts:
            if self._stop_event.is_set():
                break

            result["accounts_checked"] += 1

            try:
                scan = scanner.scan_since_last_sync(account)
            except Exception:
                LOGGER.exception("Mailbox scan failed for a connected account")
                result["accounts_failed"] += 1
                continue

            result["messages_scanned"] += scan["total_messages_scanned"]
            result["finance_messages_found"] += scan["finance_messages_found"]

            if not scan["activities"]:
                continue

            try:
                delivery = NotificationService(
                    database,
                    self.config_path,
                ).send_activities(
                    scan["account_id"],
                    scan["activities"],
                )
                result["notifications_sent"] += delivery["sent"]
                result["notifications_skipped"] += delivery["skipped"]
                result["notifications_failed"] += delivery["failed"]
            except TelegramError:
                LOGGER.warning(
                    "Telegram is unavailable or not configured; "
                    "finance notifications were not sent."
                )
                result["notifications_failed"] += len(scan["activities"])

        return result

    def run(self):
        while not self._stop_event.is_set():
            try:
                result = self.scan_once()
            except Exception:
                LOGGER.exception("The monitoring cycle failed")
                self.scan_failed.emit(
                    "FinAlert couldn't complete a monitoring check. "
                    "Check Microsoft sign-in and your internet connection."
                )
            else:
                self.scan_completed.emit(result)

            self._stop_event.wait(self.interval_seconds)
