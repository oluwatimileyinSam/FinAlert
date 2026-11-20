import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from license_manager import LicenseError, LicenseManager


LOGGER = logging.getLogger("FinAlert.license")


class LicenseTask(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.operation()
        except LicenseError as exc:
            self.result_ready.emit(False, str(exc))
        except Exception:
            LOGGER.exception("Unexpected license operation error")
            self.result_ready.emit(
                False,
                "FinAlert could not complete the license check. Try again.",
            )
        else:
            self.result_ready.emit(True, "")


class LicenseActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = LicenseManager()
        self.task = None
        self.pending_mode = self.manager.pending_path.exists()

        self.setWindowTitle("Activate FinAlert")
        self.setModal(True)
        self.setFixedWidth(480)

        self._build_ui()
        self._update_activation_mode()

        if self.manager.license_path.exists() or self.pending_mode:
            self.status_label.setText("Checking your FinAlert activation…")
            self._start_task(self.manager.check_saved_license)
        else:
            self.status_label.setText(
                "Enter your one-time license key to activate FinAlert."
            )

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_icon = QLabel("F")
        brand_icon.setObjectName("BrandIcon")
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setFixedSize(42, 42)

        brand_name = QLabel("FinAlert")
        brand_name.setObjectName("BrandName")

        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand_name)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        heading = QLabel("Activate FinAlert")
        heading.setObjectName("Heading")
        layout.addWidget(heading)

        description = QLabel(
            "Redeem your license key once. It will be locked to this device."
        )
        description.setObjectName("Description")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.key_input = QLineEdit()
        self.key_input.setObjectName("LicenseKeyInput")
        self.key_input.setPlaceholderText("PF-XXXX-XXXX-…")
        self.key_input.setClearButtonEnabled(True)
        self.key_input.returnPressed.connect(self._activate)
        layout.addWidget(self.key_input)

        self.status_label = QLabel()
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_button = QPushButton("Quit")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.clicked.connect(self.reject)

        self.activate_button = QPushButton("Activate license")
        self.activate_button.setObjectName("PrimaryButton")
        self.activate_button.clicked.connect(self._activate)

        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.activate_button)
        layout.addLayout(button_row)

        footer = QLabel("License activation requires an internet connection.")
        footer.setObjectName("Footer")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self.setStyleSheet(
            """
            QDialog {
                background: #f5f7fb;
                color: #202a3a;
            }
            QLabel#BrandIcon {
                background: #2f6fed;
                color: white;
                border-radius: 9px;
                font-size: 23px;
                font-weight: 700;
            }
            QLabel#BrandName {
                color: #202a3a;
                font-size: 17px;
                font-weight: 700;
                padding-left: 7px;
            }
            QLabel#Heading {
                color: #202a3a;
                font-size: 23px;
                font-weight: 700;
                padding-top: 8px;
            }
            QLabel#Description, QLabel#Footer {
                color: #65738a;
                font-size: 13px;
            }
            QLabel#Status {
                color: #44536a;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit#LicenseKeyInput {
                background: white;
                color: #202a3a;
                border: 1px solid #cbd5e2;
                border-radius: 7px;
                padding: 11px 12px;
                font-size: 14px;
                selection-background-color: #2f6fed;
            }
            QLineEdit#LicenseKeyInput:focus {
                border: 1px solid #2f6fed;
            }
            QPushButton {
                border-radius: 7px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton#PrimaryButton {
                background: #2f6fed;
                color: white;
                border: 1px solid #2f6fed;
            }
            QPushButton#PrimaryButton:hover {
                background: #245fd1;
            }
            QPushButton#PrimaryButton:disabled {
                background: #9bb7ef;
                border-color: #9bb7ef;
            }
            QPushButton#SecondaryButton {
                background: white;
                color: #35445a;
                border: 1px solid #d7deea;
            }
            QPushButton#SecondaryButton:hover {
                background: #f6f8fc;
            }
            QPushButton#SecondaryButton:disabled {
                color: #8793a5;
            }
            """
        )

    def _update_activation_mode(self):
        self.pending_mode = self.manager.pending_path.exists()
        self.key_input.setVisible(not self.pending_mode)
        self.activate_button.setText(
            "Retry activation" if self.pending_mode else "Activate license"
        )

    def _start_task(self, operation):
        if self.task is not None and self.task.isRunning():
            return

        self.key_input.setEnabled(False)
        self.activate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

        task = LicenseTask(operation)
        self.task = task
        task.result_ready.connect(self._on_task_result)
        task.finished.connect(lambda: self._clear_task(task))
        task.start()

    def _clear_task(self, task):
        if self.task is task:
            self.task = None
        task.deleteLater()

    def _on_task_result(self, succeeded, message):
        if succeeded:
            self.accept()
            return

        self._update_activation_mode()
        self.key_input.setEnabled(not self.pending_mode)
        self.activate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

        if message == "Enter a license key to activate FinAlert.":
            message = "Enter your one-time license key to activate FinAlert."

        self.status_label.setText(message)

    def _activate(self):
        if self.pending_mode:
            self.status_label.setText("Retrying the pending activation…")
            self._start_task(self.manager.check_saved_license)
            return

        license_key = self.key_input.text().strip()
        if not license_key:
            self.status_label.setText("Enter your license key first.")
            self.key_input.setFocus()
            return

        self.status_label.setText("Activating this device…")
        self._start_task(lambda: self.manager.activate(license_key))

    def closeEvent(self, event):
        if self.task is not None and self.task.isRunning():
            event.ignore()
            return
        super().closeEvent(event)


class LicenseDialog(LicenseActivationDialog):
    def __init__(self, invalid_reason=None, parent=None):
        super().__init__(parent)
        if invalid_reason:
            self.status_label.setText(invalid_reason)


def ensure_license(parent=None):
    dialog = LicenseDialog(parent=parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
