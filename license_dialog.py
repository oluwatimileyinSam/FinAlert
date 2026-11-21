import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
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
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("LicenseHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setObjectName("BrandIcon")
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setFixedSize(42, 42)

        logo_path = Path(__file__).resolve().parent / "assets" / "fin_alert_logo.svg"
        logo_pixmap = QPixmap(str(logo_path))

        if logo_pixmap.isNull():
            brand_icon.setText("F")
        else:
            brand_icon.setPixmap(logo_pixmap)
            brand_icon.setScaledContents(True)

        brand_text = QVBoxLayout()
        brand_name = QLabel("FinAlert")
        brand_name.setObjectName("BrandName")
        brand_subtitle = QLabel("BY PERENNIS FONS")
        brand_subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(brand_name)
        brand_text.addWidget(brand_subtitle)

        brand_row.addWidget(brand_icon)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()

        eyebrow = QLabel("SECURE DEVICE ACTIVATION")
        eyebrow.setObjectName("LicenseEyebrow")

        heading = QLabel("Activate FinAlert")
        heading.setObjectName("Heading")

        description = QLabel(
            "Redeem your one-time license key to unlock FinAlert. "
            "Activation locks the key to this device."
        )
        description.setObjectName("Description")
        description.setWordWrap(True)

        hero_layout.addLayout(brand_row)
        hero_layout.addSpacing(3)
        hero_layout.addWidget(eyebrow)
        hero_layout.addWidget(heading)
        hero_layout.addWidget(description)

        panel = QFrame()
        panel.setObjectName("ActivationPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(11)

        key_label = QLabel("License key")
        key_label.setObjectName("KeyLabel")

        self.key_input = QLineEdit()
        self.key_input.setObjectName("LicenseKeyInput")
        self.key_input.setPlaceholderText("PF-XXXX-XXXX-…")
        self.key_input.setClearButtonEnabled(True)
        self.key_input.returnPressed.connect(self._activate)

        self.status_label = QLabel()
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)

        panel_layout.addWidget(key_label)
        panel_layout.addWidget(self.key_input)
        panel_layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_button = QPushButton("Quit")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)

        self.activate_button = QPushButton("Activate license")
        self.activate_button.setObjectName("PrimaryButton")
        self.activate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activate_button.clicked.connect(self._activate)

        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.activate_button)

        footer = QLabel(
            "Online activation required  ·  One key, one device"
        )
        footer.setObjectName("Footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)

        layout.addWidget(hero)
        layout.addWidget(panel)
        layout.addLayout(button_row)
        layout.addWidget(footer)

        self.setStyleSheet(
            """
            QDialog {
                background: #f3f6fa;
                color: #202a3a;
            }
            QFrame#LicenseHero {
                background: #101a2e;
                border: 1px solid #233550;
                border-radius: 16px;
            }
            QFrame#ActivationPanel {
                background: white;
                border: 1px solid #e0e6ef;
                border-radius: 14px;
            }
            QLabel#BrandIcon {
                background: transparent;
                color: #61e6c5;
                border-radius: 9px;
                font-size: 23px;
                font-weight: 700;
            }
            QLabel#BrandName {
                color: white;
                font-size: 17px;
                font-weight: 700;
                padding-left: 7px;
            }
            QLabel#BrandSubtitle {
                color: #aab8cc;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 1px;
                padding-left: 7px;
            }
            QLabel#LicenseEyebrow {
                color: #61e6c5;
                font-size: 9px;
                font-weight: 750;
                letter-spacing: 1.3px;
            }
            QLabel#Heading {
                color: #f4f7fb;
                font-size: 25px;
                font-weight: 750;
            }
            QLabel#Description {
                color: #b9c5d6;
                font-size: 12px;
            }
            QLabel#KeyLabel {
                color: #19263a;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#Status {
                background: #f4f7fa;
                color: #44536a;
                border: 1px solid #e6ebf1;
                border-radius: 8px;
                padding: 9px 10px;
                font-size: 11px;
                min-height: 28px;
            }
            QLabel#Footer {
                color: #718096;
                font-size: 10px;
            }
            QLineEdit#LicenseKeyInput {
                background: white;
                color: #202a3a;
                border: 1px solid #cbd5e2;
                border-radius: 8px;
                padding: 11px 12px;
                font-size: 14px;
                selection-background-color: #167f72;
            }
            QLineEdit#LicenseKeyInput:focus {
                border: 1px solid #167f72;
            }
            QPushButton {
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: 650;
            }
            QPushButton#PrimaryButton {
                background: #167f72;
                color: white;
                border: 1px solid #167f72;
            }
            QPushButton#PrimaryButton:hover {
                background: #126c61;
            }
            QPushButton#PrimaryButton:disabled {
                background: #9bbdb6;
                border-color: #9bbdb6;
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
