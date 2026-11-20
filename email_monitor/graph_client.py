import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests


LOGGER = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
PAGE_SIZE = 100

MESSAGE_FIELDS = ",".join([
    "id",
    "subject",
    "from",
    "toRecipients",
    "receivedDateTime",
    "sentDateTime",
    "body",
    "bodyPreview",
    "conversationId",
    "webLink",
    "internetMessageId",
    "hasAttachments",
])

FOLDERS = [
    ("inbox", "Inbox", "receivedDateTime"),
    ("sentitems", "Sent Items", "sentDateTime"),
]


class GraphAPIError(Exception):
    """A Microsoft Graph request failed."""


class GraphMailClient:
    def __init__(self, authentication, timeout=30):
        self.authentication = authentication
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_recent_messages(self, account, limit_per_folder=50):
        """Read a limited number of recent messages from both mail folders."""
        if not 1 <= limit_per_folder <= 1000:
            raise ValueError("limit_per_folder must be between 1 and 1000")

        return self._fetch_messages(
            account=account,
            limit_per_folder=limit_per_folder,
        )

    def fetch_messages_from_last_days(self, account, days=60):
        """Read all Inbox and Sent Items messages from the previous 1–60 days."""
        if not 1 <= days <= 60:
            raise ValueError("days must be between 1 and 60")

        return self._fetch_messages(
            account=account,
            days=days,
            limit_per_folder=None,
        )

    def fetch_messages_since(
        self,
        account,
        since_by_folder,
        overlap_seconds=300,
    ):
        """Read messages newer than each folder's last sync time."""
        if not isinstance(since_by_folder, dict):
            raise ValueError("since_by_folder must be a dictionary")

        if not 0 <= overlap_seconds <= 86400:
            raise ValueError("overlap_seconds must be between 0 and 86400")

        for _folder_id, folder_label, _date_field in FOLDERS:
            if not since_by_folder.get(folder_label):
                raise ValueError(
                    f"A last-sync timestamp is required for {folder_label}."
                )

        return self._fetch_messages(
            account=account,
            since_by_folder=since_by_folder,
            overlap_seconds=overlap_seconds,
            limit_per_folder=None,
        )

    def _fetch_messages(
        self,
        account,
        days=None,
        since_by_folder=None,
        overlap_seconds=300,
        limit_per_folder=None,
    ):
        token_result = self.authentication.acquire_for(account)
        access_token = token_result.get("access_token")
        if not access_token:
            raise GraphAPIError("Microsoft did not provide a Graph access token.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Prefer": 'outlook.body-content-type="text"',
        }

        messages = []
        history_cutoff = None
        if days is not None:
            history_cutoff = self._format_utc(
                datetime.now(timezone.utc) - timedelta(days=days)
            )

        for folder_id, folder_label, date_field in FOLDERS:
            folder_url = (
                f"{GRAPH_BASE_URL}/me/mailFolders/{folder_id}/messages"
            )
            params = {
                "$top": min(limit_per_folder or PAGE_SIZE, PAGE_SIZE),
                "$select": MESSAGE_FIELDS,
            }

            if since_by_folder is not None:
                cutoff = self._format_cutoff(
                    since_by_folder[folder_label],
                    overlap_seconds,
                )
                params["$filter"] = f"{date_field} ge {cutoff}"
                params["$orderby"] = f"{date_field} desc"
            elif history_cutoff:
                params["$filter"] = f"{date_field} ge {history_cutoff}"
                params["$orderby"] = f"{date_field} desc"
            else:
                params["$orderby"] = f"{date_field} desc"

            folder_messages = self._read_folder(
                folder_url=folder_url,
                folder_label=folder_label,
                headers=headers,
                params=params,
                limit=limit_per_folder,
            )
            messages.extend(folder_messages)

        return messages

    def _read_folder(self, folder_url, folder_label, headers, params, limit):
        results = []
        next_url = folder_url
        next_params = params

        while next_url and (limit is None or len(results) < limit):
            self._validate_graph_url(next_url)

            try:
                response = self.session.get(
                    next_url,
                    headers=headers,
                    params=next_params,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                LOGGER.warning(
                    "Microsoft Graph request failed for %s",
                    folder_label,
                )
                raise GraphAPIError(
                    f"Could not reach Microsoft Graph for {folder_label}."
                ) from exc

            if response.status_code != 200:
                LOGGER.warning(
                    "Microsoft Graph returned HTTP %s for %s",
                    response.status_code,
                    folder_label,
                )
                raise GraphAPIError(
                    f"Microsoft Graph returned HTTP {response.status_code} "
                    f"for {folder_label}."
                )

            try:
                page = response.json()
            except ValueError as exc:
                raise GraphAPIError(
                    "Microsoft Graph returned an unreadable response."
                ) from exc

            page_messages = page.get("value")
            if not isinstance(page_messages, list):
                raise GraphAPIError(
                    "Microsoft Graph returned an unexpected message list."
                )

            for message in page_messages:
                message["fin_alert_folder"] = folder_label
                results.append(message)

                if limit is not None and len(results) >= limit:
                    break

            next_url = page.get("@odata.nextLink")
            next_params = None

        return results

    @staticmethod
    def _format_cutoff(value, overlap_seconds):
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("Invalid last-sync timestamp.") from exc
        else:
            raise ValueError("Invalid last-sync timestamp.")

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        timestamp -= timedelta(seconds=overlap_seconds)
        return GraphMailClient._format_utc(timestamp)

    @staticmethod
    def _format_utc(value):
        return (
            value.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _validate_graph_url(url):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/")
        ):
            raise GraphAPIError("Microsoft Graph returned an invalid paging URL.")
