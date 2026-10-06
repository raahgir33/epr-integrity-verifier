"""Deterministic parsing: Indian number formats, units (kg/t), IST datetimes.

The model never does this arithmetic — Gemini extracts values exactly as
printed (strings); everything here turns those printed strings into
canonical numbers/dates. Digits are normalized from Devanagari to ASCII
first: this project's own generator always prints ASCII digits (confirmed
in scripts/dossier_gen/shipments.py — only field *labels* switch script on
Hindi documents, not values), but a real Hindi document could print numeric
values in Devanagari script, so parsing here stays robust either way.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_DEVANAGARI_DIGITS = "०१२३४५६७८९"
_DEVANAGARI_TO_ASCII = str.maketrans(_DEVANAGARI_DIGITS, "0123456789")


def normalize_digits(printed: str) -> str:
    """Devanagari digits (०-९) -> ASCII (0-9). A no-op on ASCII-only input."""
    return printed.translate(_DEVANAGARI_TO_ASCII)


def parse_indian_number(printed: str) -> float:
    """'1,23,450.00' -> 123450.0. Digit-grouping commas are simply stripped,
    so both Indian and plain Western grouping parse the same way."""
    cleaned = normalize_digits(printed).replace(",", "").strip()
    return float(cleaned)


def kg_to_t(kg: float) -> float:
    return kg / 1000.0


def t_to_kg(t: float) -> float:
    return t * 1000.0


def parse_date_ddmmyyyy(printed: str) -> date:
    """'05/04/2025' -> date(2025, 4, 5)."""
    cleaned = normalize_digits(printed).strip()
    return datetime.strptime(cleaned, "%d/%m/%Y").date()


def parse_datetime_ist(printed: str) -> datetime:
    """'05-04-2025 14:32' -> timezone-aware datetime in Asia/Kolkata."""
    cleaned = normalize_digits(printed).strip()
    naive = datetime.strptime(cleaned, "%d-%m-%Y %H:%M")
    return naive.replace(tzinfo=IST)
