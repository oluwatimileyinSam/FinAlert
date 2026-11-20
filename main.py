import sys

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class FinAlertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinAlert")
        self.resize(1000, 650)

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
            self.make_page("Finance overview", "Connect an account to get started.")
        )
        self.pages.addWidget(
            self.make_page("Microsoft accounts", "Connected mailboxes will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Telegram", "Telegram notification settings will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Finance activity", "Detected finance activity will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Notification history", "Sent notifications will appear here.")
        )
        self.pages.addWidget(
            self.make_page("Monitoring settings", "Monitoring controls will appear here.")
        )

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self.pages)
        self.setCentralWidget(content)

        self.addDockWidget(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.DockWidgetArea.LeftDockWidgetArea,
            self._make_navigation_dock(),
        )

    def _make_navigation_dock(self):
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("FinAlert", self)
        dock.setWidget(self.navigation)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        return dock

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


def main():
    application = QApplication(sys.argv)
    window = FinAlertWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
