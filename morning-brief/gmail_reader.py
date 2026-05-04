from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parseaddr, parsedate_to_datetime
import re
from typing import Any

from dateutil import parser as dateparser

from google_auth import GoogleAuthError, gmail_service


class GmailReaderError(RuntimeError):
    pass


@dataclass
class EmailItem:
    sender: str
    subject: str
    date: datetime | None
    snippet: str
    labels: list[str]
    score: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "subject": self.subject,
            "date": self.date,
            "snippet": self.snippet,
            "labels": self.labels,
        }


NOISE_TERMS = [
    "unsubscribe",
    "newsletter",
    "promotion",
    "promo",
    "promotional",
    "sale",
    "deal",
    "shop ",
    "just dropped",
    "introducing:",
    "bestselling",
    "new colorways",
    "monthly deals",
    "youtube videos",
    "recommending right now",
    "archival artwork",
    "redfin",
    "zillow",
    "realtor.com",
    "open house",
    "recommended rental",
    "recommended home",
    "homes for sale",
    "apartments.com",
    "new listing",
    "price drop",
    "offers due",
    "receipt",
    "invoice paid",
    "order confirmation",
    "delivery update",
    "no-reply",
    "noreply",
    "notification",
    "calendar invitation",
    "accepted:",
    "declined:",
    "tentatively accepted:",
    "facebook",
    "instagram",
    "linkedin",
]

URGENT_TERMS = [
    "urgent",
    "asap",
    "deadline",
    "due",
    "overdue",
    "action required",
    "payment",
    "bill",
    "doctor",
    "dentist",
    "appointment",
    "school",
    "daycare",
    "stratford",
    "teacher",
    "staff",
    "travel",
    "flight",
    "tenant",
    "rental",
    "lease",
    "liz",
    "family",
]

PRIORITY_SENDERS = [
    "liz",
    "stratford",
    "school",
    "daycare",
    "doctor",
    "dentist",
    "pediatric",
    "tenant",
    "property",
    "manager",
]


def _term_in_text(term: str, text: str) -> bool:
    normalized = term.lower()
    if re.fullmatch(r"[a-z0-9 ]+", normalized):
        return re.search(rf"\b{re.escape(normalized)}\b", text) is not None
    return normalized in text


def _normalized_sender(sender: str) -> str:
    sender = sender.lower()
    sender = re.sub(r"\bme\b", "", sender)
    sender = re.sub(r"[^a-z0-9]+", " ", sender)
    return re.sub(r"\s+", " ", sender).strip()


def _normalized_subject(subject: str) -> str:
    subject = subject.lower()
    subject = re.sub(r"^(re|fw|fwd):\s*", "", subject)
    subject = re.sub(r"\b(it'?s|this is|just|only)\b", " ", subject)
    subject = re.sub(r"\b\d+\s+days?\s+left\s+(to|for)\b", " ", subject)
    subject = re.sub(r"\blast\s+day\s+(to|for)\b", " ", subject)
    subject = re.sub(r"\bcloses?\s+(today|tomorrow)\b", " ", subject)
    subject = re.sub(r"\bdeadline\s+(today|tomorrow)\b", " ", subject)
    subject = re.sub(r"\b(take|complete|submit|fill out|respond to)\b", " ", subject)
    subject = re.sub(r"\b(today|tomorrow|tonight|soon)\b", " ", subject)
    subject = re.sub(r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b", " ", subject)
    subject = re.sub(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b", " ", subject)
    subject = re.sub(r"[^a-z0-9]+", " ", subject)
    words = [
        word
        for word in subject.split()
        if word
        and word
        not in {
            "the",
            "a",
            "an",
            "and",
            "or",
            "for",
            "to",
            "your",
            "our",
            "my",
            "with",
            "about",
            "on",
            "at",
            "in",
        }
    ]
    return " ".join(words)


def email_key(sender: str, subject: str) -> str:
    return f"{_normalized_sender(sender)}::{_normalized_subject(subject)}"


def topic_key(sender: str, subject: str) -> str:
    subject_key = _normalized_subject(subject)
    sender_key = _normalized_sender(sender)
    if any(term in sender_key for term in ["stratford", "school", "daycare"]):
        return f"school::{subject_key}"
    if any(term in sender_key for term in ["redfin", "zillow", "realtor"]):
        return f"real-estate-alert::{subject_key}"
    return f"{sender_key}::{subject_key}"


def _headers(message: dict[str, Any]) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def _is_noise(sender: str, subject: str, snippet: str) -> bool:
    text = f"{sender} {subject} {snippet}".lower()
    if any(term in text for term in ["redfin", "zillow", "realtor.com"]):
        return True
    if any(_term_in_text(term, text) for term in URGENT_TERMS):
        return False
    return any(_term_in_text(term, text) for term in NOISE_TERMS)


def _score(sender: str, subject: str, snippet: str, labels: list[str]) -> int:
    text = f"{sender} {subject} {snippet}".lower()
    score = 0
    score += 5 * sum(1 for term in PRIORITY_SENDERS if _term_in_text(term, text))
    score += 3 * sum(1 for term in URGENT_TERMS if _term_in_text(term, text))
    if "UNREAD" in labels:
        score += 2
    if "IMPORTANT" in labels:
        score += 3
    return score


def filter_rank_emails(
    raw_items: list[dict[str, Any]], limit: int = 5, previously_reported: set[str] | None = None
) -> list[dict[str, Any]]:
    previously_reported = previously_reported or set()
    by_topic: dict[str, dict[str, Any]] = {}
    for raw in raw_items:
        sender = raw.get("sender", "")
        subject = raw.get("subject", "")
        snippet = raw.get("snippet", "")
        labels = raw.get("labels", [])
        if _is_noise(sender, subject, snippet):
            continue
        score = _score(sender, subject, snippet, labels)
        if score < 3:
            continue
        exact_key = email_key(sender, subject)
        if exact_key in previously_reported:
            continue
        item = dict(raw)
        item["_score"] = score
        item["_topic_key"] = topic_key(sender, subject)
        existing = by_topic.get(item["_topic_key"])
        if not existing or (item["_score"], item.get("date") or datetime.min) > (
            existing["_score"],
            existing.get("date") or datetime.min,
        ):
            by_topic[item["_topic_key"]] = item

    ranked = sorted(
        by_topic.values(),
        key=lambda item: (item["_score"], item.get("date") or datetime.min),
        reverse=True,
    )
    for item in ranked:
        item.pop("_score", None)
        item.pop("_topic_key", None)
    return ranked[:limit]


SECTION_HEADER_RE = re.compile(
    r"^(?:Morning brief for\s+)?(?P<date>[A-Z][a-z]+day,\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4})$",
    re.MULTILINE,
)


def _section_bounds(body: str) -> list[tuple[date | None, str]]:
    matches = list(SECTION_HEADER_RE.finditer(body))
    sections: list[tuple[date | None, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        parsed_date = None
        try:
            parsed_date = dateparser.parse(match.group("date")).date()
        except Exception:
            pass
        sections.append((parsed_date, body[match.start() : end]))
    return sections


def extract_reported_email_keys(note_body: str, target_date: date) -> set[str]:
    keys: set[str] = set()
    for section_date, section in _section_bounds(note_body):
        if section_date == target_date:
            continue
        in_email_section = False
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith("📧"):
                in_email_section = True
                continue
            if in_email_section and (not stripped or re.match(r"^[📅🌤📈⚡]", stripped)):
                in_email_section = False
            if not in_email_section or not stripped.startswith("- "):
                continue
            match = re.match(r"^-\s+([^:]+):\s+(.+)$", stripped)
            if match:
                keys.add(email_key(match.group(1), match.group(2)))
    return keys


def _get_message(service, message_id: str) -> EmailItem:
    msg = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        )
        .execute()
    )
    headers = _headers(msg)
    sender_name, sender_addr = parseaddr(headers.get("from", ""))
    sender = sender_name or sender_addr or headers.get("from", "Unknown sender")
    subject = headers.get("subject", "(no subject)").strip()
    labels = msg.get("labelIds", [])
    snippet = msg.get("snippet", "")
    return EmailItem(
        sender=sender,
        subject=subject,
        date=_parse_date(headers.get("date", "")),
        snippet=snippet,
        labels=labels,
    )


def fetch_attention_emails(limit: int = 5) -> list[dict[str, Any]]:
    try:
        service = gmail_service()
        queries = [
            "category:primary is:unread newer_than:24h",
            "category:primary is:unread is:important newer_than:48h",
        ]
        ids: dict[str, None] = {}
        for query in queries:
            result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=25)
                .execute()
            )
            for message in result.get("messages", []):
                ids[message["id"]] = None

        items: list[dict[str, Any]] = []
        for message_id in ids:
            item = _get_message(service, message_id)
            items.append(item.as_dict())

        return filter_rank_emails(items, limit=limit)
    except GoogleAuthError as exc:
        raise GmailReaderError(str(exc)) from exc
    except Exception as exc:
        raise GmailReaderError(f"Gmail read failed: {exc}") from exc
