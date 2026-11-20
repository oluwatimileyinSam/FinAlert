import configparser
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_config import (
    CONFIG_PATH,
    microsoft_settings,
    save_scan_interval_seconds,
    scan_interval_seconds,
)
from authentication.microsoft import AuthenticationError, MicrosoftAuth
from email_monitor.pipeline import (
    FinanceScanner,
    SYNC_FOLDERS,
    default_database_path,
)
from notifications.service import NotificationService
from notifications.telegram_client import TelegramError
from storage.database import FinanceDatabase
from notifications.telegram_settings import TelegramSettingsWidget


logging.basicConfig(level=logging.INFO)

NAVIGATION_ITEMS = [
    ("Dashboard", "Overview"),
    ("Microsoft accounts", "Accounts"),
    ("Telegram", "Telegram"),
    ("Finance activity", "Activity"),
    ("Notification history", "Notifications"),
    ("Monitoring settings", "Settings"),
]


class FinAlertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinAlert")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        self.auth = None
        self.database = FinanceDatabase(default_database_path())
        self.connected_account_count = 0
        self.nav_buttons = []

        self.pages = QStackedWidget()
        self.page_title = QLabel()
        self.account_status = QLabel("Monitoring not started")

        self.pages.addWidget(self.make_dashboard_page())
        self.pages.addWidget(self.make_accounts_page())
        self.telegram_settings = TelegramSettingsWidget(CONFIG_PATH)
        self.pages.addWidget(self.telegram_settings)
        self.pages.addWidget(self.make_finance_page())
        self.pages.addWidget(self.make_notification_history_page())
        self.pages.addWidget(self.make_settings_page())

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.make_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 24)
        content_layout.setSpacing(18)
        content_layout.addWidget(self.make_topbar())
        content_layout.addWidget(self.pages, 1)

        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.setStyleSheet(self.stylesheet())
        self.navigate(0)
        self.refresh_accounts()
        self.refresh_finance_activity()
        self.refresh_notification_history()

    def make_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)

        brand = QHBoxLayout()
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
            brand_icon.setStyleSheet("background: white;")

        brand_text = QVBoxLayout()
        brand_name = QLabel("FinAlert")
        brand_name.setObjectName("BrandName")
        brand_subtitle = QLabel("BY PERENNIS FONS")
        brand_subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(brand_name)
        brand_text.addWidget(brand_subtitle)

        brand.addWidget(brand_icon)
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(30)

        section_label = QLabel("WORKSPACE")
        section_label.setObjectName("SidebarSection")
        layout.addWidget(section_label)

        for index, (label, _title) in enumerate(NAVIGATION_ITEMS):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self.navigate(page_index)
            )
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()

        footer = QLabel("Secure mailbox monitoring")
        footer.setObjectName("SidebarFooter")
        layout.addWidget(footer)

        return sidebar

    def make_topbar(self):
        topbar = QFrame()
        topbar.setObjectName("Topbar")
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(0, 0, 0, 14)

        self.page_title.setObjectName("PageTitle")
        self.account_status.setObjectName("StatusPill")

        layout.addWidget(self.page_title)
        layout.addStretch()
        layout.addWidget(self.account_status)
        return topbar

    def make_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("DashboardHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.setSpacing(24)

        introduction = QVBoxLayout()
        introduction.setSpacing(11)

        eyebrow = QLabel("FINALERT  /  MAILBOX INTELLIGENCE")
        eyebrow.setObjectName("HeroEyebrow")

        headline = QLabel("See the signal.\nStay ahead of the noise.")
        headline.setObjectName("HeroTitle")

        description = QLabel(
            "A focused view of financial activity across your connected mailboxes."
        )
        description.setObjectName("HeroCopy")
        description.setWordWrap(True)

        manage_button = QPushButton("Manage mailboxes  →")
        manage_button.setObjectName("HeroButton")
        manage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_button.clicked.connect(lambda: self.navigate(1))

        introduction.addWidget(eyebrow)
        introduction.addWidget(headline)
        introduction.addWidget(description)
        introduction.addSpacing(4)
        introduction.addWidget(manage_button, 0, Qt.AlignmentFlag.AlignLeft)

        signal_panel = QFrame()
        signal_panel.setObjectName("HeroSignal")
        signal_layout = QVBoxLayout(signal_panel)
        signal_layout.setContentsMargins(20, 18, 20, 18)
        signal_layout.setSpacing(7)

        signal_label = QLabel("MONITORING FOCUS")
        signal_label.setObjectName("SignalEyebrow")

        signal_mark = QLabel("◉")
        signal_mark.setObjectName("SignalMark")
        signal_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        signal_title = QLabel("Inbox + Sent Items")
        signal_title.setObjectName("SignalTitle")
        signal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        signal_detail = QLabel("Initial discovery  ·  up to 60 days")
        signal_detail.setObjectName("SignalDetail")
        signal_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        signal_layout.addWidget(signal_label)
        signal_layout.addWidget(signal_mark, 1)
        signal_layout.addWidget(signal_title)
        signal_layout.addWidget(signal_detail)

        hero_layout.addLayout(introduction, 3)
        hero_layout.addWidget(signal_panel, 2)
        layout.addWidget(hero)

        cards = QHBoxLayout()
        cards.setSpacing(14)

        self.accounts_value = QLabel("0")
        self.activities_value = QLabel("0")
        self.overdue_value = QLabel("0")
        self.telegram_value = QLabel("Not configured")

        cards.addWidget(
            self.make_stat_card("Connected mailboxes", self.accounts_value)
        )
        cards.addWidget(
            self.make_stat_card("Finance activity", self.activities_value)
        )
        cards.addWidget(
            self.make_stat_card("Overdue invoices", self.overdue_value)
        )
        cards.addWidget(
            self.make_stat_card("Telegram", self.telegram_value)
        )
        layout.addLayout(cards)

        section_header = QHBoxLayout()
        recent_title = QLabel("Activity stream")
        recent_title.setObjectName("SectionHeading")

        section_caption = QLabel("RECENT FINANCIAL SIGNALS")
        section_caption.setObjectName("ActivityCaption")

        section_header.addWidget(recent_title)
        section_header.addSpacing(10)
        section_header.addWidget(section_caption)
        section_header.addStretch()

        view_all = QPushButton("View all  →")
        view_all.setObjectName("TextButton")
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.clicked.connect(lambda: self.navigate(3))
        section_header.addWidget(view_all)

        layout.addLayout(section_header)

        self.dashboard_table = self.make_activity_table()
        layout.addWidget(self.dashboard_table, 1)

        return page

    def make_accounts_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        eyebrow = QLabel("IDENTITY CONTROL")
        eyebrow.setObjectName("AccountEyebrow")

        heading = QLabel("Connected mailboxes")
        heading.setObjectName("SectionHeading")

        description = QLabel(
            "Bring each Microsoft mailbox into one secure view. "
            "FinAlert requests read-only access to your email."
        )
        description.setObjectName("SecondaryText")
        description.setWordWrap(True)

        panel = QFrame()
        panel.setObjectName("AccountPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(12)

        panel_title = QLabel("Microsoft accounts")
        panel_title.setObjectName("AccountPanelTitle")

        panel_detail = QLabel(
            "Select a mailbox to scan it or disconnect it from FinAlert."
        )
        panel_detail.setObjectName("SecondaryText")

        self.account_list = QListWidget()
        self.account_list.setObjectName("AccountList")

        panel_layout.addWidget(panel_title)
        panel_layout.addWidget(panel_detail)
        panel_layout.addWidget(self.account_list, 1)

        connect_button = QPushButton("Connect Microsoft account")
        connect_button.setObjectName("PrimaryButton")
        connect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_button.clicked.connect(self.connect_account)

        scan_button = QPushButton("Scan last 60 days")
        scan_button.setObjectName("SecondaryButton")
        scan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_button.clicked.connect(self.scan_selected_account)

        disconnect_button = QPushButton("Disconnect")
        disconnect_button.setObjectName("SecondaryButton")
        disconnect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        disconnect_button.clicked.connect(self.disconnect_account)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(connect_button)
        actions.addStretch()
        actions.addWidget(scan_button)
        actions.addWidget(disconnect_button)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(panel, 1)
        layout.addLayout(actions)

        return page

    def make_notification_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        eyebrow = QLabel("TELEGRAM  /  DELIVERY AUDIT")
        eyebrow.setObjectName("HistoryEyebrow")

        heading = QLabel("Notification history")
        heading.setObjectName("SectionHeading")

        description = QLabel(
            "Trace each alert back to its mailbox, message, and delivery attempt."
        )
        description.setObjectName("SecondaryText")
        description.setWordWrap(True)

        panel = QFrame()
        panel.setObjectName("HistoryPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(12)

        panel_header = QHBoxLayout()
        panel_title = QLabel("Recent delivery attempts")
        panel_title.setObjectName("HistoryPanelTitle")

        channel_label = QLabel("TELEGRAM")
        channel_label.setObjectName("HistoryChannel")

        panel_header.addWidget(panel_title)
        panel_header.addStretch()
        panel_header.addWidget(channel_label)

        self.notification_summary = QLabel("No notification history yet.")
        self.notification_summary.setObjectName("HistorySummary")
        self.notification_summary.setWordWrap(True)

        self.notification_table = QTableWidget(0, 6)
        self.notification_table.setHorizontalHeaderLabels([
            "Mailbox",
            "Direction",
            "Status",
            "Category",
            "Subject",
            "Attempted",
        ])
        self.notification_table.setObjectName("ActivityTable")
        self.notification_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.notification_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.notification_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.notification_table.setAlternatingRowColors(True)
        self.notification_table.verticalHeader().setVisible(False)
        self.notification_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        panel_layout.addLayout(panel_header)
        panel_layout.addWidget(self.notification_summary)
        panel_layout.addWidget(self.notification_table, 1)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(panel, 1)

        return page

    def make_finance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        eyebrow = QLabel("MAILBOX SIGNAL  /  CLASSIFIED ACTIVITY")
        eyebrow.setObjectName("FinanceEyebrow")

        heading = QLabel("Finance activity")
        heading.setObjectName("SectionHeading")

        description = QLabel(
            "Review transaction-related messages found across Inbox and Sent Items."
        )
        description.setObjectName("SecondaryText")
        description.setWordWrap(True)

        panel = QFrame()
        panel.setObjectName("FinancePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(12)

        panel_header = QHBoxLayout()
        panel_title = QLabel("Detected activity")
        panel_title.setObjectName("FinancePanelTitle")

        folders_label = QLabel("INBOX  +  SENT ITEMS")
        folders_label.setObjectName("FinanceFolders")

        panel_header.addWidget(panel_title)
        panel_header.addStretch()
        panel_header.addWidget(folders_label)

        self.finance_table = self.make_activity_table()

        panel_layout.addLayout(panel_header)
        panel_layout.addWidget(self.finance_table, 1)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(panel, 1)

        return page

    def make_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        heading = QLabel("Monitoring settings")
        heading.setObjectName("SectionHeading")

        description = QLabel(
            "Choose how often the background monitor checks connected mailboxes."
        )
        description.setObjectName("SecondaryText")

        panel = QFrame()
        panel.setObjectName("StatCard")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(16)

        interval_row = QHBoxLayout()
        interval_label = QLabel("Mailbox check interval")
        interval_label.setObjectName("StatLabel")

        self.scan_interval_input = QSpinBox()
        self.scan_interval_input.setRange(15, 3600)
        self.scan_interval_input.setSingleStep(15)
        self.scan_interval_input.setSuffix(" seconds")
        self.scan_interval_input.setValue(scan_interval_seconds())

        interval_row.addWidget(interval_label)
        interval_row.addStretch()
        interval_row.addWidget(self.scan_interval_input)
        panel_layout.addLayout(interval_row)

        save_button = QPushButton("Save settings")
        save_button.setObjectName("PrimaryButton")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(self.save_monitoring_settings)
        panel_layout.addWidget(save_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.settings_status = QLabel(
            "The saved interval applies the next time background monitoring starts."
        )
        self.settings_status.setObjectName("SecondaryText")

        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(panel)
        layout.addWidget(self.settings_status)
        layout.addStretch()
        return page

    def save_monitoring_settings(self):
        try:
            save_scan_interval_seconds(self.scan_interval_input.value())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Monitoring settings", str(exc))
            return

        self.settings_status.setText(
            "Settings saved. The interval applies when background monitoring starts."
        )

    def make_placeholder_page(self, title, description_text):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setObjectName("SectionHeading")
        description = QLabel(description_text)
        description.setObjectName("SecondaryText")

        panel = QFrame()
        panel.setObjectName("EmptyPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 22, 22, 22)
        panel_layout.addWidget(description)
        panel_layout.addStretch()

        layout.addWidget(heading)
        layout.addWidget(panel, 1)
        return page

    @staticmethod
    def make_stat_card(label, value_label):
        card = QFrame()
        card.setObjectName("StatCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        label_widget = QLabel(label)
        label_widget.setObjectName("StatLabel")
        value_label.setObjectName("StatValue")

        layout.addWidget(label_widget)
        layout.addWidget(value_label)
        return card

    @staticmethod
    def make_activity_table():
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels([
            "Direction",
            "Category",
            "Subject",
            "Sender",
            "Date",
        ])
        table.setObjectName("ActivityTable")
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        return table

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.page_title.setText(NAVIGATION_ITEMS[index][0])

        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def stylesheet(self):
        return """
            QWidget {
                color: #1c2738;
                font-family: "Segoe UI", "SF Pro Text", Arial;
                font-size: 13px;
            }
            QMainWindow {
                background: #f4f6fa;
            }
            QFrame#Sidebar {
                background: #14213a;
                border: none;
            }
            QLabel#BrandIcon {
                background: #2f6fed;
                color: white;
                border-radius: 10px;
                font-size: 22px;
                font-weight: 700;
                min-width: 42px;
                max-width: 42px;
                min-height: 42px;
                max-height: 42px;
            }
            QLabel#BrandName {
                color: white;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#BrandSubtitle {
                color: #91a1bc;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 1px;
            }
            QLabel#SidebarSection {
                color: #8292ad;
                font-size: 10px;
                font-weight: 700;
                padding: 0 10px 6px 10px;
            }
            QPushButton#NavButton {
                background: transparent;
                color: #c1ccdc;
                border: none;
                border-radius: 7px;
                text-align: left;
                padding: 11px 12px;
                font-weight: 500;
            }
            QPushButton#NavButton:hover {
                background: #20314e;
                color: white;
            }
            QPushButton#NavButton:checked {
                background: #263a5d;
                color: white;
                font-weight: 600;
            }
            QLabel#SidebarFooter {
                color: #8292ad;
                font-size: 11px;
                padding: 8px 10px;
            }
            QFrame#Topbar {
                background: transparent;
                border: none;
                border-bottom: 1px solid #e3e8f0;
            }
            QLabel#PageTitle {
                color: #172338;
                font-size: 16px;
                font-weight: 650;
            }
            QLabel#StatusPill {
                background: #e9edf4;
                color: #56647a;
                border-radius: 12px;
                padding: 6px 11px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#SectionHeading {
                color: #19263a;
                font-size: 19px;
                font-weight: 650;
            }
            QLabel#SecondaryText {
                color: #718096;
                font-size: 12px;
            }
            QFrame#StatCard, QFrame#EmptyPanel {
                background: white;
                border: 1px solid #e4e9f1;
                border-radius: 10px;
            }
            QLabel#StatLabel {
                color: #718096;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#StatValue {
                color: #172338;
                font-size: 22px;
                font-weight: 700;
            }
            QLineEdit, QSpinBox {
                background-color: #ffffff;
                color: #1c2738;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 10px;
                selection-background-color: #2f6fed;
                selection-color: white;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #2f6fed;
            }
            QLineEdit::placeholder {
                color: #7b8797;
            }
            QCheckBox {
                color: #35445a;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background: white;
                border: 1px solid #aeb8c7;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background: #2f6fed;
                border-color: #2f6fed;
            }
            QTableWidget#ActivityTable, QListWidget#AccountList {
                background: white;
                alternate-background-color: #f8fafd;
                border: 1px solid #e4e9f1;
                border-radius: 9px;
                gridline-color: #edf0f5;
                selection-background-color: #eaf1ff;
                selection-color: #1c2738;
            }
            QHeaderView::section {
                background: #f8fafd;
                color: #66758a;
                border: none;
                border-bottom: 1px solid #e4e9f1;
                padding: 10px;
                font-size: 11px;
                font-weight: 650;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #edf0f5;
            }
            QPushButton#PrimaryButton, QPushButton#SecondaryButton,
            QPushButton#TextButton {
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
            QPushButton#SecondaryButton {
                background: white;
                color: #35445a;
                border: 1px solid #d7deea;
            }
            QPushButton#SecondaryButton:hover {
                background: #f6f8fc;
            }
            QPushButton#TextButton {
                background: transparent;
                color: #2f6fed;
                border: none;
            }
            QPushButton#TextButton:hover {
                background: #eaf1ff;
            }
        
            QFrame#DashboardHero {
                background: #101a2e;
                border: 1px solid #233550;
                border-radius: 18px;
            }
            QLabel#HeroEyebrow, QLabel#SignalEyebrow {
                color: #61e6c5;
                font-size: 10px;
                font-weight: 750;
                letter-spacing: 1.4px;
            }
            QLabel#HeroTitle {
                color: #f4f7fb;
                font-size: 29px;
                font-weight: 750;
            }
            QLabel#HeroCopy {
                color: #b9c5d6;
                font-size: 13px;
            }
            QFrame#HeroSignal {
                background: #17243b;
                border: 1px solid #2b405c;
                border-radius: 15px;
                min-width: 225px;
            }
            QLabel#SignalMark {
                color: #61e6c5;
                font-size: 53px;
                font-weight: 400;
            }
            QLabel#SignalTitle {
                color: #f4f7fb;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#SignalDetail {
                color: #aab8cc;
                font-size: 10px;
            }
            QLabel#ActivityCaption {
                color: #8292a9;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QFrame#StatCard {
                border-radius: 13px;
                border-color: #e0e6ef;
            }
            QPushButton#HeroButton {
                background: #61e6c5;
                color: #0d1b2a;
                border: 1px solid #61e6c5;
                border-radius: 8px;
                padding: 10px 15px;
                font-weight: 700;
            }
            QPushButton#HeroButton:hover {
                background: #83f0d4;
                border-color: #83f0d4;
            }
            QPushButton#TextButton {
                color: #167f72;
            }
            QPushButton#TextButton:hover {
                background: #e5f7f3;
            }

            QLabel#AccountEyebrow {
                color: #167f72;
                font-size: 10px;
                font-weight: 750;
                letter-spacing: 1.3px;
            }
            QFrame#AccountPanel {
                background: #ffffff;
                border: 1px solid #e0e6ef;
                border-radius: 14px;
            }
            QLabel#AccountPanelTitle {
                color: #19263a;
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#HistoryEyebrow {
                color: #167f72;
                font-size: 10px;
                font-weight: 750;
                letter-spacing: 1.3px;
            }
            QFrame#HistoryPanel {
                background: #ffffff;
                border: 1px solid #e0e6ef;
                border-radius: 14px;
            }
            QLabel#HistoryPanelTitle {
                color: #19263a;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#HistoryChannel {
                background: #e5f7f3;
                color: #167f72;
                border-radius: 8px;
                padding: 5px 9px;
                font-size: 9px;
                font-weight: 750;
                letter-spacing: 1px;
            }
            QLabel#HistorySummary {
                background: #f4f7fa;
                color: #526277;
                border: 1px solid #e6ebf1;
                border-radius: 8px;
                padding: 9px 11px;
                font-size: 11px;
            }

            QLabel#FinanceEyebrow {
                color: #167f72;
                font-size: 10px;
                font-weight: 750;
                letter-spacing: 1.3px;
            }
            QFrame#FinancePanel {
                background: #ffffff;
                border: 1px solid #e0e6ef;
                border-radius: 14px;
            }
            QLabel#FinancePanelTitle {
                color: #19263a;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#FinanceFolders {
                background: #edf2f8;
                color: #526277;
                border-radius: 8px;
                padding: 5px 9px;
                font-size: 9px;
                font-weight: 750;
                letter-spacing: 0.8px;
            }
"""

    def get_auth(self):
        if self.auth is None:
            client_id, authority = microsoft_settings()
            if not client_id:
                raise AuthenticationError(
                    "Set MICROSOFT_CLIENT_ID in your local settings."
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

            account_id = FinanceScanner._get_account_id(account)
            has_previous_sync = all(
                self.database.get_sync_state(account_id, folder)
                for folder in SYNC_FOLDERS
            )
            self.scan_account(
                account,
                initial_history=not has_previous_sync,
            )

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
        selected_item = self.account_list.currentItem()
        if selected_item is None:
            QMessageBox.information(
                self,
                "Scan mailbox",
                "Select a connected Microsoft account first.",
            )
            return

        account_id = selected_item.data(Qt.ItemDataRole.UserRole)

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

    def scan_account(self, account, initial_history=True):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            scanner = FinanceScanner(
                self.get_auth(),
                self.database,
            )
            if initial_history:
                result = scanner.scan_initial_history(account, days=60)
            else:
                result = scanner.scan_since_last_sync(account)

            self.refresh_finance_activity()

            if result["activities"]:
                try:
                    notification_result = NotificationService(
                        self.database,
                        CONFIG_PATH,
                    ).send_activities(
                        result["account_id"],
                        result["activities"],
                        account_label=account.get("username"),
                    )
                    telegram_status = (
                        f"\nTelegram alerts: {notification_result['sent']} sent, "
                        f"{notification_result['skipped']} already sent, "
                        f"{notification_result['failed']} failed."
                    )
                except TelegramError as exc:
                    telegram_status = f"\nTelegram alerts not sent: {exc}"
            else:
                telegram_status = "\nTelegram alerts: No finance emails found."

            self.refresh_notification_history()

            dialog_title = (
                "60-day scan complete"
                if initial_history
                else "Mailbox scan complete"
            )
            QMessageBox.information(
                self,
                dialog_title,
                f"Messages scanned: {result['total_messages_scanned']}\n"
                f"Finance messages found: {result['finance_messages_found']}\n"
                f"New finance records saved: "
                f"{result['new_finance_messages_recorded']}"
                f"{telegram_status}",
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
            accounts = []

        self.connected_account_count = len(accounts)

        for account in accounts:
            username = account.get("username", "Microsoft account")
            item = QListWidgetItem(f"{username}  ·  Connected")
            item.setData(
                Qt.ItemDataRole.UserRole,
                account.get("home_account_id"),
            )
            self.account_list.addItem(item)

        if self.account_list.count():
            self.account_list.setCurrentRow(0)

        self.refresh_dashboard()

    def refresh_finance_activity(self):
        records = self.database.list_messages(limit=1000)

        self.populate_activity_table(self.finance_table, records)
        self.populate_activity_table(self.dashboard_table, records[:5])

        overdue_count = sum(
            record.get("finance_category") == "overdue_invoice"
            for record in records
        )
        self.activities_value.setText(str(len(records)))
        self.overdue_value.setText(str(overdue_count))
        self.refresh_dashboard()

    def refresh_notification_history(self):
        records = self.database.list_notification_history(limit=100)

        mailbox_names = {}
        try:
            for account in self.get_auth().accounts():
                mailbox_names[FinanceScanner._get_account_id(account)] = (
                    account.get("username") or "Microsoft account"
                )
        except AuthenticationError:
            pass

        self.notification_table.setRowCount(0)
        if records:
            self.notification_summary.setText(
                f"Showing {len(records)} recent notification attempts."
            )
        else:
            self.notification_summary.setText("No notification history yet.")

        for record in records:
            row_index = self.notification_table.rowCount()
            self.notification_table.insertRow(row_index)

            folder = record.get("folder")
            if folder == "Sent Items":
                direction = "Sent"
            elif folder == "Inbox":
                direction = "Received"
            else:
                direction = folder or "Unknown"

            values = [
                mailbox_names.get(
                    record.get("account_id"),
                    "Disconnected account",
                ),
                direction,
                (record.get("status") or "unknown").capitalize(),
                record.get("finance_category") or "Finance-related",
                record.get("subject") or "(No subject)",
                record.get("attempted_at") or "",
            ]

            for column, value in enumerate(values):
                self.notification_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(str(value)),
                )

    @staticmethod
    def populate_activity_table(table, records):
        table.setRowCount(0)

        for record in records:
            row_index = table.rowCount()
            table.insertRow(row_index)

            direction = (
                "Sent"
                if record.get("folder") == "Sent Items"
                else "Received"
            )
            values = [
                direction,
                record.get("finance_category") or "Finance related",
                record.get("subject") or "(No subject)",
                (
                    record.get("sender_name")
                    or record.get("sender_address")
                    or "Unknown sender"
                ),
                (
                    record.get("sent_at")
                    or record.get("received_at")
                    or record.get("first_seen_at")
                    or ""
                ),
            ]

            for column, value in enumerate(values):
                table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def refresh_dashboard(self):
        self.accounts_value.setText(str(self.connected_account_count))
        self.account_status.setText(
            f"{self.connected_account_count} connected "
            f"· Monitoring not started"
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
    if "--background" in sys.argv[1:]:
        from email_monitor.background_runner import main as background_main
        return background_main()

    application = QApplication(sys.argv)
    application.setStyle("Fusion")

    from license_dialog import ensure_license

    if not ensure_license():
        return 0

    window = FinAlertWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
