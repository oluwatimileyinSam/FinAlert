import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class FinanceDatabase:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.initialize()

        if os.name != "nt":
            self.database_path.chmod(0o600)

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    account_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    internet_message_id TEXT,
                    folder TEXT NOT NULL,
                    subject TEXT,
                    sender_name TEXT,
                    sender_address TEXT,
                    recipients_json TEXT NOT NULL DEFAULT '[]',
                    received_at TEXT,
                    sent_at TEXT,
                    conversation_id TEXT,
                    web_link TEXT,
                    finance_category TEXT,
                    classification_json TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (account_id, message_id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_activity
                    ON messages (account_id, received_at, sent_at);

                CREATE TABLE IF NOT EXISTS notification_history (
                    account_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    sent_at TEXT,
                    error_code TEXT,
                    PRIMARY KEY (account_id, message_id, channel),
                    FOREIGN KEY (account_id, message_id)
                        REFERENCES messages (account_id, message_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    account_id TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    delta_link TEXT,
                    last_sync_at TEXT,
                    PRIMARY KEY (account_id, folder)
                );
                """
            )

    def save_messages(self, account_id, messages):
        """Save message metadata and return the number of newly seen messages."""
        if not account_id:
            raise ValueError("account_id is required")

        inserted = 0

        with self._connect() as connection:
            for message in messages:
                message_id = message.get("id")
                if not message_id:
                    continue

                sender = (
                    message.get("from", {})
                    .get("emailAddress", {})
                )
                recipients = [
                    item.get("emailAddress", {})
                    for item in message.get("toRecipients", [])
                ]

                values = (
                    message.get("internetMessageId"),
                    message.get("fin_alert_folder", "Unknown"),
                    message.get("subject"),
                    sender.get("name"),
                    sender.get("address"),
                    json.dumps(recipients, ensure_ascii=False),
                    message.get("receivedDateTime"),
                    message.get("sentDateTime"),
                    message.get("conversationId"),
                    message.get("webLink"),
                )

                existing = connection.execute(
                    """
                    SELECT 1
                    FROM messages
                    WHERE account_id = ? AND message_id = ?
                    """,
                    (account_id, message_id),
                ).fetchone()

                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO messages (
                            account_id,
                            message_id,
                            internet_message_id,
                            folder,
                            subject,
                            sender_name,
                            sender_address,
                            recipients_json,
                            received_at,
                            sent_at,
                            conversation_id,
                            web_link
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (account_id, message_id, *values),
                    )
                    inserted += 1
                else:
                    connection.execute(
                        """
                        UPDATE messages
                        SET internet_message_id = ?,
                            folder = ?,
                            subject = ?,
                            sender_name = ?,
                            sender_address = ?,
                            recipients_json = ?,
                            received_at = ?,
                            sent_at = ?,
                            conversation_id = ?,
                            web_link = ?,
                            last_seen_at = CURRENT_TIMESTAMP
                        WHERE account_id = ? AND message_id = ?
                        """,
                        (*values, account_id, message_id),
                    )

        return inserted

    def save_classification(
        self,
        account_id,
        message_id,
        finance_category,
        details,
    ):
        details_json = json.dumps(details or {}, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE messages
                SET finance_category = ?,
                    classification_json = ?
                WHERE account_id = ? AND message_id = ?
                """,
                (
                    finance_category,
                    details_json,
                    account_id,
                    message_id,
                ),
            )

    def list_messages(self, account_id=None, limit=100):
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        query = """
            SELECT *
            FROM messages
        """
        parameters = []

        if account_id:
            query += " WHERE account_id = ?"
            parameters.append(account_id)

        query += """
            ORDER BY COALESCE(received_at, sent_at, first_seen_at) DESC
            LIMIT ?
        """
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [dict(row) for row in rows]

    def list_notification_history(self, account_id=None, limit=100):
        """Return recent notification attempts with their email details."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        query = """
            SELECT
                n.account_id,
                n.message_id,
                n.channel,
                n.status,
                n.attempted_at,
                n.sent_at,
                n.error_code,
                m.folder,
                m.subject,
                m.sender_name,
                m.sender_address,
                m.finance_category
            FROM notification_history AS n
            INNER JOIN messages AS m
                ON m.account_id = n.account_id
                AND m.message_id = n.message_id
        """
        parameters = []

        if account_id:
            query += " WHERE n.account_id = ?"
            parameters.append(account_id)

        query += " ORDER BY n.attempted_at DESC LIMIT ?"
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [dict(row) for row in rows]

    def notification_was_sent(self, account_id, message_id, channel):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM notification_history
                WHERE account_id = ? AND message_id = ? AND channel = ?
                """,
                (account_id, message_id, channel),
            ).fetchone()

        return row is not None and row["status"] == "sent"

    def record_notification(
        self,
        account_id,
        message_id,
        channel,
        status,
        error_code=None,
    ):
        if status not in {"pending", "sent", "failed"}:
            raise ValueError("status must be pending, sent, or failed")

        now = datetime.now(timezone.utc).isoformat()
        sent_at = now if status == "sent" else None

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_history (
                    account_id,
                    message_id,
                    channel,
                    status,
                    attempted_at,
                    sent_at,
                    error_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (account_id, message_id, channel)
                DO UPDATE SET
                    status = excluded.status,
                    attempted_at = excluded.attempted_at,
                    sent_at = excluded.sent_at,
                    error_code = excluded.error_code
                """,
                (
                    account_id,
                    message_id,
                    channel,
                    status,
                    now,
                    sent_at,
                    error_code,
                ),
            )

    def get_sync_state(self, account_id, folder):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT delta_link, last_sync_at
                FROM sync_state
                WHERE account_id = ? AND folder = ?
                """,
                (account_id, folder),
            ).fetchone()

        return dict(row) if row else None

    def save_sync_state(
        self,
        account_id,
        folder,
        delta_link=None,
        last_sync_at=None,
    ):
        if last_sync_at is None:
            sync_time = datetime.now(timezone.utc)
        elif isinstance(last_sync_at, datetime):
            sync_time = last_sync_at
        else:
            try:
                sync_time = datetime.fromisoformat(
                    str(last_sync_at).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("Invalid last-sync timestamp.") from exc

        if sync_time.tzinfo is None:
            sync_time = sync_time.replace(tzinfo=timezone.utc)
        else:
            sync_time = sync_time.astimezone(timezone.utc)

        sync_time_text = sync_time.isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_state (
                    account_id,
                    folder,
                    delta_link,
                    last_sync_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (account_id, folder)
                DO UPDATE SET
                    delta_link = excluded.delta_link,
                    last_sync_at = excluded.last_sync_at
                """,
                (account_id, folder, delta_link, sync_time_text),
            )
