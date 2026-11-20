import os
import sys
from pathlib import Path

from email_monitor.classifier import classify_message
from email_monitor.graph_client import GraphMailClient
from storage.database import FinanceDatabase


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

    def scan_initial_history(self, account, days=60):
        """Scan both folders, classify messages, and save finance activity."""
        account_id = (
            account.get("home_account_id")
            or account.get("local_account_id")
        )
        if not account_id:
            raise ValueError("The Microsoft account has no stable account ID.")

        messages = self.graph.fetch_messages_from_last_days(
            account,
            days=days,
        )

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
            self.database.save_classification(
                account_id=account_id,
                message_id=message["id"],
                finance_category=classification["category"],
                details=classification,
            )

        return {
            "account_id": account_id,
            "days_scanned": days,
            "total_messages_scanned": len(messages),
            "finance_messages_found": len(activities),
            "new_finance_messages_recorded": newly_recorded,
            "activities": activities,
        }
