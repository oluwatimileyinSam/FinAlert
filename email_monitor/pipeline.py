import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from email_monitor.classifier import classify_message
from email_monitor.graph_client import GraphMailClient
from storage.database import FinanceDatabase


SYNC_FOLDERS = ("Inbox", "Sent Items")


def default_database_path():
    """Return an application data path outside the project repository."""
    if sys.platform == "darwin":
        data_root = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        data_root = Path(
            os.environ.get(
                "LOCALAPPDATA",
                str(Path.home() / "AppData" / "Local"),
            )
        )
    else:
        data_root = Path(
            os.environ.get(
                "XDG_DATA_HOME",
                str(Path.home() / ".local" / "share"),
            )
        )

    return data_root / "FinAlert" / "fin_alert.sqlite3"


class FinanceScanner:
    def __init__(self, authentication, database=None):
        self.authentication = authentication
        self.graph = GraphMailClient(authentication)
        self.database = database or FinanceDatabase(default_database_path())

    @staticmethod
    def _get_account_id(account):
        account_id = (
            account.get("home_account_id")
            or account.get("local_account_id")
        )
        if not account_id:
            raise ValueError("The Microsoft account has no stable account ID.")
        return account_id

    def scan_initial_history(self, account, days=60):
        """Scan both folders, classify messages, and save finance activity."""
        account_id = self._get_account_id(account)
        scan_started_at = datetime.now(timezone.utc)

        messages = self.graph.fetch_messages_from_last_days(
            account,
            days=days,
        )

        return self._process_messages(
            account_id=account_id,
            messages=messages,
            days_scanned=days,
            scan_started_at=scan_started_at,
        )

    def scan_since_last_sync(self, account, overlap_seconds=300):
        """Scan only messages newer than the saved per-folder sync times."""
        account_id = self._get_account_id(account)

        sync_states = {
            folder: self.database.get_sync_state(account_id, folder)
            for folder in SYNC_FOLDERS
        }

        if any(
            not state or not state.get("last_sync_at")
            for state in sync_states.values()
        ):
            return self.scan_initial_history(account, days=60)

        since_by_folder = {
            folder: state["last_sync_at"]
            for folder, state in sync_states.items()
        }
        scan_started_at = datetime.now(timezone.utc)

        messages = self.graph.fetch_messages_since(
            account,
            since_by_folder=since_by_folder,
            overlap_seconds=overlap_seconds,
        )

        return self._process_messages(
            account_id=account_id,
            messages=messages,
            days_scanned=0,
            scan_started_at=scan_started_at,
        )

    def _process_messages(
        self,
        account_id,
        messages,
        days_scanned,
        scan_started_at,
    ):
        activities = []
        for message in messages:
            classification = classify_message(message)
            if classification["is_finance_related"]:
                activities.append({
                    "message": message,
                    "classification": classification,
                })

        finance_messages = [item["message"] for item in activities]
        newly_recorded = self.database.save_messages(
            account_id,
            finance_messages,
        )

        for item in activities:
            message = item["message"]
            classification = item["classification"]
            message_id = message.get("id")
            if not message_id:
                continue

            self.database.save_classification(
                account_id=account_id,
                message_id=message_id,
                finance_category=classification["category"],
                details=classification,
            )

        for folder in SYNC_FOLDERS:
            self.database.save_sync_state(
                account_id,
                folder,
                last_sync_at=scan_started_at,
            )

        return {
            "account_id": account_id,
            "days_scanned": days_scanned,
            "total_messages_scanned": len(messages),
            "finance_messages_found": len(activities),
            "new_finance_messages_recorded": newly_recorded,
            "activities": activities,
        }
