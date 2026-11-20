import configparser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from notifications.telegram_client import TelegramClient, TelegramError


class TelegramSettingsWidget(QWidget):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.config_path = Path(config_path)

        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Paste the token from BotFather")

        self.chat_id_input = QLineEdit()
        self.chat_id_input.setPlaceholderText("Choose a discovered chat or enter its ID")

        self.include_body = QCheckBox("Include email body excerpt in alerts")
        self.body_length = QSpinBox()
        self.body_length.setRange(0, 3000)
        self.body_length.setSingleStep(100)
        self.body_length.setSuffix(" characters")
        self.include_body.toggled.connect(self.body_length.setEnabled)

        self.status = QLabel("Telegram is not configured.")
        self.status.setWordWrap(True)
        self.status.setObjectName("SecondaryText")

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        heading = QLabel("Telegram configuration")
        heading.setObjectName("SectionHeading")
        description = QLabel(
            "Configure where FinAlert sends notifications. The bot token is "
            "saved in the operating system credential store, not in the "
            "configuration file. Start a conversation with your bot before "
            "finding its chat ID."
        )
        description.setObjectName("SecondaryText")
        description.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(description)

        panel = QFrame()
        panel.setObjectName("EmptyPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 22, 22, 22)
        panel_layout.setSpacing(16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setSpacing(12)
        form.addRow("Bot token", self.token_input)

        destination_row = QWidget()
        destination_layout = QHBoxLayout(destination_row)
        destination_layout.setContentsMargins(0, 0, 0, 0)
        destination_layout.setSpacing(8)

        destination_layout.addWidget(self.chat_id_input, 1)
        find_chat_button = QPushButton("Find chat ID")
        find_chat_button.setObjectName("SecondaryButton")
        find_chat_button.clicked.connect(self.find_chat_id)
        destination_layout.addWidget(find_chat_button)

        form.addRow("Destination", destination_row)
        form.addRow("Email content", self.include_body)

        body_row = QHBoxLayout()
        body_row.addWidget(QLabel("Excerpt length"))
        body_row.addWidget(self.body_length)
        body_row.addStretch()
        form.addRow("", body_row)

        panel_layout.addLayout(form)
        panel_layout.addWidget(self.status)

        buttons = QHBoxLayout()

        save_button = QPushButton("Save settings")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self.save_settings)

        test_button = QPushButton("Test bot")
        test_button.setObjectName("SecondaryButton")
        test_button.clicked.connect(self.test_bot)

        send_test_button = QPushButton("Send test message")
        send_test_button.setObjectName("SecondaryButton")
        send_test_button.clicked.connect(self.send_test_message)

        buttons.addWidget(save_button)
        buttons.addWidget(test_button)
        buttons.addWidget(send_test_button)
        buttons.addStretch()

        panel_layout.addLayout(buttons)
        layout.addWidget(panel)
        layout.addStretch()

    def _read_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(self.config_path, encoding="utf-8")
        return config

    def _load_settings(self):
        config = self._read_config()

        if not config.has_section("Telegram"):
            return

        self.chat_id_input.setText(
            config.get("Telegram", "CHAT_ID", fallback="")
        )
        self.include_body.setChecked(
            config.getboolean(
                "Telegram",
                "INCLUDE_EMAIL_BODY",
                fallback=True,
            )
        )
        self.body_length.setValue(
            config.getint(
                "Telegram",
                "BODY_LENGTH",
                fallback=3000,
            )
        )
        self.body_length.setEnabled(self.include_body.isChecked())

    def _save_settings(self):
        token = self.token_input.text().strip()
        if token:
            TelegramClient.save_bot_token(token)
            self.token_input.clear()

        config = self._read_config()
        if not config.has_section("Telegram"):
            config.add_section("Telegram")

        config.set("Telegram", "CHAT_ID", self.chat_id_input.text().strip())
        config.set(
            "Telegram",
            "INCLUDE_EMAIL_BODY",
            str(self.include_body.isChecked()).lower(),
        )
        config.set("Telegram", "BODY_LENGTH", str(self.body_length.value()))

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as config_file:
            config.write(config_file)

    def _make_client(self):
        self._save_settings()
        chat_id = self.chat_id_input.text().strip() or None
        return TelegramClient(chat_id)

    def save_settings(self):
        try:
            self._save_settings()
            self.status.setText(
                "Settings saved. The bot token is stored securely on this device."
            )
        except TelegramError as exc:
            self.status.setText(str(exc))
        except OSError:
            self.status.setText("FinAlert could not write the local settings file.")

    def test_bot(self):
        try:
            bot = self._make_client().test_connection()
            bot_name = bot.get("username") or bot.get("first_name") or "Telegram bot"
            self.status.setText(f"Connected to @{bot_name}.")
        except TelegramError as exc:
            self.status.setText(str(exc))
        except OSError:
            self.status.setText("FinAlert could not write the local settings file.")

    def find_chat_id(self):
        try:
            chats = self._make_client().get_recent_chats()
            if not chats:
                self.status.setText(
                    "No chat found. Open your bot in Telegram, press Start, "
                    "send /start, then try again."
                )
                return

            choices = [
                f"{chat['name']} ({chat['type']}) — {chat['id']}"
                for chat in chats
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                "Choose Telegram destination",
                "Chat:",
                choices,
                0,
                False,
            )

            if not accepted:
                return

            selected_index = choices.index(selected)
            chat_id = chats[selected_index]["id"]
            self.chat_id_input.setText(chat_id)
            self._save_settings()
            self.status.setText("Telegram destination saved.")

        except TelegramError as exc:
            self.status.setText(str(exc))
        except OSError:
            self.status.setText("FinAlert could not write the local settings file.")

    def send_test_message(self):
        try:
            self._make_client().send_message(
                "FinAlert test message. Telegram notifications are connected."
            )
            self.status.setText(
                "Test message sent. Check the configured Telegram destination."
            )
        except TelegramError as exc:
            self.status.setText(str(exc))
        except OSError:
            self.status.setText("FinAlert could not write the local settings file.")
