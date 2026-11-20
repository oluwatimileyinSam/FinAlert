import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


class FinAlertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinAlert")
        self.resize(900, 600)

        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("FinAlert")
        title.setStyleSheet("font-size: 28px; font-weight: 600;")

        message = QLabel("Finance email monitoring, in one place.")
        message.setStyleSheet("font-size: 16px;")

        layout.addWidget(title)
        layout.addWidget(message)
        layout.addStretch()

        self.setCentralWidget(page)


def main():
    application = QApplication(sys.argv)
    window = FinAlertWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
