import configparser
import logging
import signal
import threading
from logging.handlers import RotatingFileHandler

from app_config import CONFIG_PATH, microsoft_settings, scan_interval_seconds
from license_manager import LicenseError, verify_license_key
from authentication.microsoft import AuthenticationError, MicrosoftAuth
from email_monitor.pipeline import FinanceScanner, default_database_path
from notifications.service import NotificationService
from notifications.telegram_client import TelegramError
from storage.database import FinanceDatabase


LOGGER = logging.getLogger("FinAlert.background")


def load_configuration():
    """Load settings from app_config.py."""
    client_id, authority = microsoft_settings()

    if not client_id or client_id == "REPLACE_WITH_APP_CLIENT_ID":
        raise ValueError("Set MICROSOFT_CLIENT_ID in your local settings.")

    return client_id, authority, scan_interval_seconds()


class SilentAuthentication:
    """Adapter that prevents Graph requests from starting interactive sign-in."""

    def __init__(self, authentication):
        self.authentication = authentication

    def acquire_for(self, account):
        return self.authentication.acquire_for_silent(account)


def configure_logging():
    log_path = default_database_path().parent / "background.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_path,
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )


def license_problem():
    """Return a reason monitoring must pause, or None for a valid license."""
    config = configparser.ConfigParser(interpolation=None)

    try:
        config.read(CONFIG_PATH, encoding="utf-8")
    except (OSError, configparser.Error):
        return "Local license settings could not be read."

    license_key = config.get("License", "KEY", fallback="").strip()
    if not license_key:
        return "No license is saved. Open the FinAlert dashboard to activate."

    try:
        verify_license_key(license_key)
    except LicenseError as exc:
        return str(exc)

    return None


def scan_accounts(authentication, scanner, notifications):
    accounts = authentication.accounts()
    if not accounts:
        LOGGER.warning("No Microsoft accounts are connected.")
        return

    for account in accounts:
        try:
            result = scanner.scan_since_last_sync(account)
            activities = result["activities"]

            if activities:
                delivery = notifications.send_activities(
                    result["account_id"],
                    activities,
                )
                LOGGER.info(
                    "Scan complete: %s messages, %s finance matches, "
                    "%s alerts sent, %s skipped, %s failed.",
                    result["total_messages_scanned"],
                    result["finance_messages_found"],
                    delivery["sent"],
                    delivery["skipped"],
                    delivery["failed"],
                )
            else:
                LOGGER.info(
                    "Scan complete: %s messages, no finance matches.",
                    result["total_messages_scanned"],
                )

        except AuthenticationError as exc:
            LOGGER.error("Microsoft sign-in needs attention: %s", exc)
        except TelegramError as exc:
            LOGGER.error("Telegram notification failed: %s", exc)
        except Exception:
            LOGGER.exception("Mailbox scan failed; it will retry next cycle.")


def main():
    configure_logging()

    try:
        client_id, authority, interval = load_configuration()
    except (OSError, ValueError) as exc:
        LOGGER.critical("Background monitoring could not start: %s", exc)
        return 1

    stop_event = threading.Event()

    def request_stop(_signum, _frame):
        LOGGER.info("Shutdown requested.")
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    last_license_problem = None
    while not stop_event.is_set():
        problem = license_problem()
        if problem is None:
            break

        if problem != last_license_problem:
            LOGGER.warning("Monitoring paused: %s", problem)
            last_license_problem = problem

        stop_event.wait(interval)

    if stop_event.is_set():
        LOGGER.info("Background monitoring stopped.")
        return 0

    try:
        authentication = MicrosoftAuth(client_id, authority)
    except AuthenticationError as exc:
        LOGGER.critical("Microsoft authentication could not start: %s", exc)
        return 1

    silent_authentication = SilentAuthentication(authentication)
    database = FinanceDatabase(default_database_path())
    scanner = FinanceScanner(silent_authentication, database)
    notifications = NotificationService(database, CONFIG_PATH)

    LOGGER.info("Background monitoring started; interval is %s seconds.", interval)

    while not stop_event.is_set():
        problem = license_problem()
        if problem:
            if problem != last_license_problem:
                LOGGER.warning("Monitoring paused: %s", problem)
                last_license_problem = problem
            stop_event.wait(interval)
            continue

        if last_license_problem is not None:
            LOGGER.info("A valid license is active; monitoring resumed.")
            last_license_problem = None

        scan_accounts(authentication, scanner, notifications)
        stop_event.wait(interval)

    LOGGER.info("Background monitoring stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
