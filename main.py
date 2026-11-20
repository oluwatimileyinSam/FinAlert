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


logging.basicConfig(level=logging.INFO)
CONFIG_PATH = Path(__file__).resolve().parent / "fin_alert.ini"


class FinAlertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinAlert")
        self.resize(1000, 650)
        self.auth = None

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
            self.make_page("Finance overview", "Connect a Microsoft account to get started.")
        )
        self.pages.addWidget(self.make_accounts_page())
        self.pages.addWidget(
            self.make_page("Telegram", "Telegram settings will be added in a later step.")
        )
        self.pages.addWidget(
            self.make_page("Finance activity", "Detected activity will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Notification history", "Sent notifications will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Monitoring settings", "Monitoring controls will be added later.")
        )

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(content)

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
        layout.addWidget(QLabel(
            "Connect mailboxes independently. FinAlert requests read-only access."
        ))

        self.account_list = QListWidget()
        layout.addWidget(self.account_list, 1)

        connect_button = QPushButton("Connect Microsoft account")
        connect_button.clicked.connect(self.connect_account)

        disconnect_button = QPushButton("Disconnect selected")
        disconnect_button.clicked.connect(self.disconnect_account)

        buttons = QHBoxLayout()
        buttons.addWidget(connect_button)
        buttons.addWidget(disconnect_button)
        buttons.addStretch()
        layout.addLayout(buttons)

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
            self.get_auth().connect()
            self.refresh_accounts()
            QMessageBox.information(
                self,
                "Account connected",
                "The Microsoft account was connected.",
            )
        except AuthenticationError as exc:
            QMessageBox.warning(self, "Microsoft sign-in", str(exc))
        except Exception:
            logging.exception("Unexpected Microsoft sign-in error")
            QMessageBox.critical(
                self,
                "Microsoft sign-in",
                "Sign-in could not be completed. Check your connection and try again.",
            )

    def refresh_accounts(self):
        self.account_list.clear()
        try:
            accounts = self.get_auth().accounts()
        except AuthenticationError:
            return

        for account in accounts:
            username = account.get("username", "Microsoft account")
            item = QListWidgetItem(f"{username} — Connected")
            item.setData(Qt.ItemDataRole.UserRole, account.get("home_account_id"))
            self.account_list.addItem(item)

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
