import configparser

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app_config import CONFIG_PATH
from license_manager import LicenseError, verify_license_key


def load_saved_license():
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8")
    return config.get("License", "KEY", fallback="").strip()


def save_license_key(license_key):
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8")

    if not config.has_section("License"):
        config.add_section("License")

    config.set("License", "KEY", license_key.strip())
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
        config.write(config_file)


class LicenseDialog(QDialog):
    def __init__(self, invalid_reason=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate FinAlert")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        heading = QLabel("Enter your FinAlert license key")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)

        description = QLabel(
            "A valid license key is required to use FinAlert."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        if invalid_reason:
            message = QLabel(invalid_reason)
            message.setWordWrap(True)
            message.setStyleSheet("color: #b42318;")
            layout.addWidget(message)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("FINALERT1.…")
        self.key_input.setClearButtonEnabled(True)
        layout.addWidget(self.key_input)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_button = QPushButton("Quit")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        activate_button = QPushButton("Activate")
        activate_button.setDefault(True)
        activate_button.clicked.connect(self.activate_license)
        buttons.addWidget(activate_button)

        layout.addLayout(buttons)

    def activate_license(self):
        license_key = self.key_input.text().strip()
        if not license_key:
            QMessageBox.warning(
                self,
                "License key required",
                "Enter your FinAlert license key.",
            )
            return

        try:
            payload = verify_license_key(license_key)
        except LicenseError as exc:
            QMessageBox.warning(self, "Invalid license", str(exc))
            return

        try:
            save_license_key(license_key)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Could not save license",
                f"FinAlert could not save the license locally: {exc}",
            )
            return

        QMessageBox.information(
            self,
            "FinAlert activated",
            f"License activated for {payload['customer']}.",
        )
        self.accept()


def ensure_license(parent=None):
    """Return True when a saved or newly entered license is valid."""
    invalid_reason = None
    saved_key = load_saved_license()

    if saved_key:
        try:
            verify_license_key(saved_key)
            return True
        except LicenseError as exc:
            invalid_reason = str(exc)

    dialog = LicenseDialog(invalid_reason=invalid_reason, parent=parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
