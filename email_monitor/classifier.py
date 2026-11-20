import html
import re


FINANCE_SIGNAL_RE = re.compile(
    r"\b(?:invoice|invoicing|billing|bill|payment|remittance|"
    r"purchase order|accounts payable|accounts receivable|"
    r"balance due|overdue|past due|wire transfer|bank transfer|"
    r"bank account|bank statement|bank transaction|bank fee|"
    r"bank charge|bank details|credit card|debit card|"
    r"card payment|card transaction|card charge|card purchase|"
    r"card statement|ach|ach transfer|ach payment|"
    r"automated clearing house|direct deposit|direct debit|"
    r"electronic funds transfer|cash deposit|cash withdrawal|"
    r"standing order|check payment|cheque payment|"
    r"transaction alert|transaction notification|account activity|"
    r"credit note|debit note|refund|reimbursement|"
    r"statement of account|financial transaction|"
    r"transaction receipt|transaction)\b",
    re.IGNORECASE,
)

DISPUTE_RE = re.compile(
    r"\b(?:dispute|disputed|billing error|incorrect amount|"
    r"wrong amount|duplicate charge|incorrect invoice|"
    r"contest(?:ed|ing)? the invoice)\b",
    re.IGNORECASE,
)

CLARIFICATION_RE = re.compile(
    r"\b(?:please clarify|need clarification|more information required|"
    r"request for clarification|could you explain|please explain)\b",
    re.IGNORECASE,
)

OVERDUE_RE = re.compile(
    r"\b(?:overdue|past due|payment is late|payment was late|"
    r"overdue invoice|late payment)\b",
    re.IGNORECASE,
)

PROMISE_RE = re.compile(
    r"\b(?:will|shall|plan to|planning to|expect to|"
    r"scheduled to|intend to)\s+(?:make\s+)?(?:the\s+)?payment\b"
    r"|\bpayment\s+(?:will|shall)\s+be\s+(?:made|sent|processed)\b"
    r"|\b(?:pay|settle|remit)\s+(?:the\s+invoice\s+)?(?:by|on)\b"
    r"|\bpayment\s+is\s+scheduled\b",
    re.IGNORECASE,
)

REPORTED_SENT_RE = re.compile(
    r"\b(?:payment|funds|wire transfer|bank transfer|remittance)\s+"
    r"(?:(?:has|have|was|were)\s+)?(?:been\s+)?"
    r"(?:sent|transferred|remitted|initiated)\b"
    r"|\b(?:we|i)\s+(?:have\s+)?"
    r"(?:sent|transferred|remitted)\s+(?:the\s+)?"
    r"(?:payment|funds|money)\b",
    re.IGNORECASE,
)

REPORTED_RECEIVED_RE = re.compile(
    r"\b(?:payment|funds|transfer)\s+"
    r"(?:(?:has|have|was|were)\s+)?(?:been\s+)?"
    r"(?:received|credited|deposited|cleared)\b"
    r"|\b(?:we|i)\s+(?:have\s+)?received\s+"
    r"(?:the\s+)?(?:payment|funds|transfer)\b",
    re.IGNORECASE,
)

REPORTED_PAID_RE = re.compile(
    r"\b(?:we|i)\s+(?:have\s+)?paid\b"
    r"|\b(?:invoice|balance)\s+(?:has\s+been\s+)?paid\b"
    r"|\bpaid\s+(?:the\s+)?invoice\b",
    re.IGNORECASE,
)

REMINDER_RE = re.compile(
    r"\b(?:payment reminder|friendly reminder|reminder to pay|"
    r"payment is due|invoice is due|upcoming payment)\b",
    re.IGNORECASE,
)

FOLLOW_UP_RE = re.compile(
    r"\b(?:following up|follow[- ]?up|checking in|"
    r"second request|awaiting payment|awaiting your response)\b",
    re.IGNORECASE,
)

INVOICE_NUMBER_PATTERNS = [
    re.compile(
        r"\binvoice\s*(?:number|no\.?|#|id)\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9/_-]{2,})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\binv\s*[-:#]\s*([A-Z0-9][A-Z0-9/_-]{2,})",
        re.IGNORECASE,
    ),
]

NUMBER_PATTERN = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
CURRENCY_CODES = (
    r"USD|EUR|GBP|CAD|AUD|NZD|JPY|CNY|INR|CHF|SEK|NOK|DKK|"
    r"SGD|HKD|MXN|BRL|ZAR|AED"
)

AMOUNT_RE = re.compile(
    rf"(?<!\w)(?:(?P<currency_before>{CURRENCY_CODES}|[$€£¥₹])\s*"
    rf"(?P<amount_before>{NUMBER_PATTERN})"
    rf"|(?P<amount_after>{NUMBER_PATTERN})\s*"
    rf"(?P<currency_after>{CURRENCY_CODES}))",
    re.IGNORECASE,
)

DATE_PATTERN = (
    r"(?:"
    r"\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December|Jan|Feb|Mar|Apr|Jun|"
    r"Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|\d{1,2}\s+(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan|Feb|Mar|Apr|"
    r"Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)(?:\s+\d{4})?"
    r")"
)


def _message_text(message):
    subject = message.get("subject") or ""
    preview = message.get("bodyPreview") or ""
    body = message.get("body") or ""

    if isinstance(body, dict):
        body = body.get("content") or ""

    body = html.unescape(str(body))
    body = re.sub(r"<[^>]*>", " ", body)

    return f"{subject}\n{preview}\n{body}"


def _extract_invoice_number(text):
    for pattern in INVOICE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_amounts(text):
    amounts = []
    seen = set()

    for match in AMOUNT_RE.finditer(text):
        currency = (
            match.group("currency_before")
            or match.group("currency_after")
        )
        amount = (
            match.group("amount_before")
            or match.group("amount_after")
        )

        value = f"{currency} {amount}".strip()
        key = value.casefold()
        if key not in seen:
            amounts.append(value)
            seen.add(key)

    return amounts


def _extract_context_date(text, label_pattern):
    match = re.search(
        rf"(?:{label_pattern})\s*(?:is|on|by|:)?\s*({DATE_PATTERN})",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def classify_message(message):
    """Classify one Graph message without inventing missing information."""
    subject = message.get("subject") or ""
    text = _message_text(message)
    finance_signals = list(dict.fromkeys(FINANCE_SIGNAL_RE.findall(text)))
    relevant = bool(finance_signals)

    sender = (
        message.get("from", {})
        .get("emailAddress", {})
    )
    folder = message.get("fin_alert_folder", "Unknown")

    category = None
    payment_status = None

    if relevant:
        if DISPUTE_RE.search(text):
            category = "invoice_dispute"
        elif CLARIFICATION_RE.search(text):
            category = "payment_clarification"
        elif OVERDUE_RE.search(text):
            category = "overdue_invoice"
        elif PROMISE_RE.search(text):
            category = "payment_promised"
            payment_status = "promised"
        elif REPORTED_SENT_RE.search(text):
            category = "payment_reported_sent"
            payment_status = "reported_sent"
        elif REPORTED_RECEIVED_RE.search(text):
            category = "payment_reported_received"
            payment_status = "reported_received"
        elif REPORTED_PAID_RE.search(text):
            category = "payment_reported_paid"
            payment_status = "reported_paid"
        elif REMINDER_RE.search(text):
            category = "payment_reminder"
        elif FOLLOW_UP_RE.search(text):
            category = "finance_follow_up"
        elif re.search(r"\binvoice\b", text, re.IGNORECASE):
            category = "invoice_activity"
        else:
            category = "finance_related"

    invoice_date = _extract_context_date(
        text,
        r"(?:invoice date|date of invoice|issued on)",
    )
    due_date = _extract_context_date(
        text,
        r"(?:due date|payment due(?: date)?|due by|payable by)",
    )
    promised_date = None
    if payment_status == "promised":
        promised_date = _extract_context_date(
            text,
            r"(?:promised payment date|pay|remit|settle)",
        )

    return {
        "is_finance_related": relevant,
        "category": category,
        "confidence": "medium" if relevant else "none",
        "evidence_terms": finance_signals,
        "direction": "outgoing" if folder == "Sent Items" else "incoming",
        "folder": folder,
        "message_id": message.get("id"),
        "internet_message_id": message.get("internetMessageId"),
        "subject": subject,
        "sender_name": sender.get("name"),
        "sender_address": sender.get("address"),
        "received_at": message.get("receivedDateTime"),
        "sent_at": message.get("sentDateTime"),
        "conversation_id": message.get("conversationId"),
        "web_link": message.get("webLink"),
        "invoice_number": _extract_invoice_number(text),
        "amounts": _extract_amounts(text),
        "invoice_date": invoice_date,
        "due_date": due_date,
        "payment_status": payment_status,
        "payment_independently_verified": False,
        "payment_verification_note": (
            "An email claim is not independent payment verification."
            if payment_status
            else None
        ),
        "promised_payment_date": promised_date,
    }
