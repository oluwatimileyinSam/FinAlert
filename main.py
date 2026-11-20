import configparser
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from authentication.microsoft import AuthenticationError, MicrosoftAuth
from email_monitor.pipeline import FinanceScanner, default_database_path
from storage.database import FinanceDatabase


logging.basicConfig(level=logging.INFO)
CONFIG_PATH = Path(__file__).resolve().parent / "fin_alert.ini"


class FinAlertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinAlert")
        self.resize(1000, 650)
        self.auth = None
        self.database = FinanceDatabase(default_database_path())

        self.navigation = QListWidget()
        self.navigation.addItems([
            "Dashboard",
            "Microsoft accounts",
            "Telegram",
            "Finance activity",
            "Notification history",
            "Monitoring settings",
        ])
        self.navigation.setFixedWidth(210)

        self.pages = QStackedWidget()
        self.pages.addWidget(
            self.make_page(
                "Finance overview",
                "Connect an account or scan a connected mailbox's last 60 days.",
            )
        )
        self.pages.addWidget(self.make_accounts_page())
        self.pages.addWidget(
            self.make_page(
                "Telegram",
                "Telegram settings will be added in a later step.",
            )
        )
        self.pages.addWidget(self.make_finance_page())
        self.pages.addWidget(
            self.make_page(
                "Notification history",
                "Sent notifications will appear here.",
            )
        )
        self.pages.addWidget(
            self.make_page(
                "Monitoring settings",
                "Monitoring controls will be added later.",
            )
        )

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(content)

        self.refresh_accounts()
        self.refresh_finance_activity()

    @staticmethod
    def make_page(title, message):
        page = QWidget()
        layout = QVBoxLayout(page)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 26px; font-weight: 600;")
        layout.addWidget(heading)
        layout.addWidget(QLabel(message))
        layout.addStretch()

        return page

    def make_accounts_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        heading = QLabel("Microsoft accounts")
        heading.setStyleSheet("font-size: 26px; font-weight: 600;")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel(
                "Connect mailboxes independently. "
                "FinAlert requests read-only access."
            )
        )

        self.account_list = QListWidget()
        layout.addWidget(self.account_list, 1)

        connect_button = QPushButton("Connect Microsoft account")
        connect_button.clicked.connect(self.connect_account)

        scan_button = QPushButton("Scan selected account — last 60 days")
        scan_button.clicked.connect(self.scan_selected_account)

        disconnect_button = QPushButton("Disconnect selected")
        disconnect_button.clicked.connect(self.disconnect_account)

        buttons = QHBoxLayout()
        buttons.addWidget(connect_button)
        buttons.addWidget(scan_button)
        buttons.addWidget(disconnect_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        return page

    def make_finance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        heading = QLabel("Finance activity")
        heading.setStyleSheet("font-size: 26px; font-weight: 600;")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel(
                "Classified finance messages from Inbox and Sent Items "
                "appear below."
            )
        )

        self.finance_list = QListWidget()
        layout.addWidget(self.finance_list, 1)

        return page

    def get_auth(self):
        if self.auth is None:
            config = configparser.ConfigParser()
            config.read(CONFIG_PATH, encoding="utf-8")

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
                    "Set CLIENT_ID in fin_alert.ini before connecting an account."
                )

            self.auth = MicrosoftAuth(client_id, authority)

        return self.auth

    def connect_account(self):
        try:
            auth = self.get_auth()
            result = auth.connect()
            self.refresh_accounts()

            username = (
                result.get("id_token_claims", {})
                .get("preferred_username", "")
                .casefold()
            )
            accounts = auth.accounts()
            account = next(
                (
                    item for item in accounts
                    if item.get("username", "").casefold() == username
                ),
                accounts[-1] if accounts else None,
            )

            if account is None:
                QMessageBox.warning(
                    self,
                    "Account connected",
                    "The account connected, but FinAlert couldn't find it "
                    "in the saved account list.",
                )
                return

            self.scan_account(account)

        except AuthenticationError as exc:
            QMessageBox.warning(self, "Microsoft sign-in", str(exc))
        except Exception:
            logging.exception("Unexpected Microsoft sign-in or scan error")
            QMessageBox.critical(
                self,
                "FinAlert",
                "The account connected, but FinAlert couldn't finish "
                "the initial scan. Check your connection and try again.",
            )

    def scan_selected_account(self):
        item = self.account_list.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                "Scan mailbox",
                "Select a connected Microsoft account first.",
            )
            return

        account_id = item.data(Qt.ItemDataRole.UserRole)

        try:
            account = next(
                (
                    item for item in self.get_auth().accounts()
                    if item.get("home_account_id") == account_id
                ),
                None,
            )
            if account is None:
                QMessageBox.warning(
                    self,
                    "Scan mailbox",
                    "That Microsoft account is no longer connected.",
                )
                return

            self.scan_account(account)

        except AuthenticationError as exc:
            QMessageBox.warning(self, "Microsoft sign-in", str(exc))

    def scan_account(self, account):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = FinanceScanner(
                self.get_auth(),
                self.database,
            ).scan_initial_history(account, days=60)

            self.refresh_finance_activity()
            QMessageBox.information(
                self,
                "60-day scan complete",
                f"Messages scanned: {result['total_messages_scanned']}\n"
                f"Finance messages found: {result['finance_messages_found']}\n"
                f"New finance records saved: "
                f"{result['new_finance_messages_recorded']}\n\n"
                "Telegram notifications are not enabled yet.",
            )
        except AuthenticationError as exc:
            QMessageBox.warning(self, "Microsoft sign-in", str(exc))
        except Exception:
            logging.exception("The 60-day mailbox scan failed")
            QMessageBox.critical(
                self,
                "Mailbox scan",
                "FinAlert couldn't complete the scan. "
                "Check your connection and try again.",
            )
        finally:
            QApplication.restoreOverrideCursor()

    def refresh_accounts(self):
        self.account_list.clear()

        try:
            accounts = self.get_auth().accounts()
        except AuthenticationError:
            return

        for account in accounts:
            username = account.get("username", "Microsoft account")
            item = QListWidgetItem(f"{username} — Connected")
            item.setData(
                Qt.ItemDataRole.UserRole,
                account.get("home_account_id"),
            )
            self.account_list.addItem(item)

        if self.account_list.count():
            self.account_list.setCurrentRow(0)

    def refresh_finance_activity(self):
        self.finance_list.clear()
        records = self.database.list_messages(limit=1000)

        if not records:
            self.finance_list.addItem("No finance activity found yet.")
            return

        for record in records:
            direction = (
                "Sent"
                if record.get("folder") == "Sent Items"
                else "Received"
            )
            category = record.get("finance_category") or "Finance related"
            subject = record.get("subject") or "(No subject)"
            sender = (
                record.get("sender_name")
                or record.get("sender_address")
                or "Unknown sender"
            )
            date = (
                record.get("sent_at")
                or record.get("received_at")
                or record.get("first_seen_at")
                or ""
            )

            self.finance_list.addItem(
                f"{category} · {direction} · {date}\n"
                f"{subject}\n"
                f"{sender}"
            )

    def disconnect_account(self):
        item = self.account_list.currentItem()
        if item is None:
            return

        answer = QMessageBox.question(
            self,
            "Disconnect account",
            f"Disconnect {item.text()} from FinAlert?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            account_id = item.data(Qt.ItemDataRole.UserRole)
            self.get_auth().disconnect(account_id)
            self.refresh_accounts()
        except AuthenticationError as exc:
            QMessageBox.warning(self, "Disconnect account", str(exc))


def main():
    application = QApplication(sys.argv)
    window = FinAlertWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
