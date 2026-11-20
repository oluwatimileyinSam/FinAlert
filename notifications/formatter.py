import html
import re


TELEGRAM_TEXT_LIMIT = 4096

CATEGORY_LABELS = {
    "invoice_activity": "Invoice activity",
    "overdue_invoice": "Overdue invoice",
    "payment_promised": "Payment promised",
    "payment_reported_sent": "Payment reportedly sent",
    "payment_reported_received": "Payment reportedly received",
    "payment_reported_paid": "Invoice reportedly paid",
    "payment_reminder": "Payment reminder",
    "payment_clarification": "Payment clarification",
    "invoice_dispute": "Invoice dispute",
    "finance_follow_up": "Finance follow-up",
    "finance_related": "Finance-related email",
}

PAYMENT_STATUS_LABELS = {
    "promised": "Promised by email; not independently verified",
    "reported_sent": "Reported sent by email; not independently verified",
    "reported_received": "Reported received by email; not independently verified",
    "reported_paid": "Reported paid by email; not independently verified",
}

SUGGESTED_ACTIONS = {
    "invoice_activity": "Review the invoice and confirm its details.",
    "overdue_invoice": "Check the account and follow up on the overdue balance.",
    "payment_promised": "Record the promised date and follow up if needed.",
    "payment_reported_sent": "Match the reported payment against your records.",
    "payment_reported_received": "Verify receipt against your bank or ledger.",
    "payment_reported_paid": "Verify the payment against your records before closing the invoice.",
    "payment_reminder": "Check the due date and current payment status.",
    "payment_clarification": "Review the request and prepare a response.",
    "invoice_dispute": "Review the invoice and supporting correspondence.",
    "finance_follow_up": "Review the conversation and decide on the next follow-up.",
    "finance_related": "Review the message and determine whether action is needed.",
}


def _clean_line(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _email_body(message):
    body = message.get("body") or ""

    if isinstance(body, dict):
        body = body.get("content") or ""

    body = html.unescape(str(body))
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</p\s*>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]*>", " ", body)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def _truncate(text, limit):
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1].rstrip() + "…"


def format_finance_notification(
    message,
    classification,
    include_body=True,
    body_length=3000,
    account_label=None,
):
    """Build one plain-text Telegram notification without sending it."""
    category = classification.get("category") or "finance_related"
    category_label = CATEGORY_LABELS.get(category, "Finance-related email")
    direction = classification.get("direction", "incoming").capitalize()
    sender = (
        classification.get("sender_name")
        or classification.get("sender_address")
        or "Unknown sender"
    )
    subject = classification.get("subject") or message.get("subject") or "(No subject)"
    email_date = (
        classification.get("sent_at")
        or classification.get("received_at")
        or message.get("sentDateTime")
        or message.get("receivedDateTime")
        or "Date unavailable"
    )

    lines = [
        f"FinAlert — {category_label}",
        f"Direction: {direction}",
        f"Sender: {_clean_line(sender)}",
        f"Subject: {_clean_line(subject)}",
        f"Date: {_clean_line(email_date)}",
    ]
    if account_label:
        lines.insert(1, f"Mailbox: {_clean_line(account_label)}")

    invoice_number = classification.get("invoice_number")
    if invoice_number:
        lines.append(f"Invoice number: {_clean_line(invoice_number)}")

    amounts = classification.get("amounts") or []
    if amounts:
        lines.append("Amount: " + ", ".join(_clean_line(value) for value in amounts))

    invoice_date = classification.get("invoice_date")
    if invoice_date:
        lines.append(f"Invoice date: {_clean_line(invoice_date)}")

    due_date = classification.get("due_date")
    if due_date:
        lines.append(f"Due date: {_clean_line(due_date)}")

    payment_status = classification.get("payment_status")
    if payment_status:
        status_text = PAYMENT_STATUS_LABELS.get(
            payment_status,
            "Reported by email; not independently verified",
        )
        lines.append(f"Payment status: {status_text}")

    promised_date = classification.get("promised_payment_date")
    if promised_date:
        lines.append(f"Promised payment date: {_clean_line(promised_date)}")

    action = SUGGESTED_ACTIONS.get(
        category,
        SUGGESTED_ACTIONS["finance_related"],
    )
    lines.append(f"Suggested next step: {action}")

    body_excerpt = ""
    if include_body:
        body_excerpt = _email_body(message)
        if not body_excerpt:
            body_excerpt = _clean_line(message.get("bodyPreview"))

    link = (
        classification.get("web_link")
        or message.get("webLink")
    )

    header = "\n".join(lines)
    footer = f"\n\nOpen in Outlook: {link}" if link else ""
    if body_excerpt:
        available_for_body = (
            TELEGRAM_TEXT_LIMIT
            - len(header)
            - len(footer)
            - len("\n\nEmail content:\n")
        )
        requested_limit = max(0, min(int(body_length), 3000))
        excerpt_limit = max(0, min(requested_limit, available_for_body))
        body_excerpt = _truncate(body_excerpt, excerpt_limit)
        body_section = f"\n\nEmail content:\n{body_excerpt}"
    elif include_body:
        body_section = "\n\nEmail content: No body text was available."
    else:
        body_section = ""

    result = header + body_section + footer
    return _truncate(result, TELEGRAM_TEXT_LIMIT)
