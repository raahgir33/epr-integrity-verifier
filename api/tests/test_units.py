"""Tests for app/ingest/units.py. Pure functions, no I/O."""

import datetime

import pytest

from app.ingest.units import (
    kg_to_t,
    normalize_digits,
    parse_date_ddmmyyyy,
    parse_datetime_ist,
    parse_indian_number,
    t_to_kg,
)


def test_parse_indian_number_with_grouping():
    assert parse_indian_number("1,23,450.00") == 123450.0


def test_parse_indian_number_without_grouping():
    assert parse_indian_number("450.50") == 450.5


def test_parse_indian_number_negative():
    assert parse_indian_number("-1,200.00") == -1200.0


def test_kg_to_t_and_back():
    assert kg_to_t(10500) == 10.5
    assert t_to_kg(10.5) == 10500


def test_parse_date_ddmmyyyy():
    assert parse_date_ddmmyyyy("05/04/2025") == datetime.date(2025, 4, 5)


def test_parse_date_ddmmyyyy_end_of_year():
    assert parse_date_ddmmyyyy("31/03/2026") == datetime.date(2026, 3, 31)


def test_parse_datetime_ist_is_timezone_aware():
    dt = parse_datetime_ist("05-04-2025 14:32")
    assert dt.year == 2025
    assert dt.month == 4
    assert dt.day == 5
    assert dt.hour == 14
    assert dt.minute == 32
    assert dt.tzinfo is not None
    assert dt.utcoffset() == datetime.timedelta(hours=5, minutes=30)


def test_normalize_digits_is_noop_on_ascii():
    assert normalize_digits("1,23,450.00") == "1,23,450.00"


def test_normalize_digits_converts_devanagari():
    # Hand-crafted: the generator never actually produces this (it always
    # prints ASCII digits, even on Hindi-labelled documents), but a real
    # Hindi document could, so parsing must handle it.
    devanagari = "१,२३,४५०.००"
    assert normalize_digits(devanagari) == "1,23,450.00"


def test_parse_indian_number_handles_devanagari_digits():
    assert parse_indian_number("१०.५०") == 10.5


def test_parse_date_ddmmyyyy_handles_devanagari_digits():
    assert parse_date_ddmmyyyy("०५/०४/२०२५") == datetime.date(2025, 4, 5)


def test_parse_indian_number_rejects_garbage():
    with pytest.raises(ValueError):
        parse_indian_number("not a number")
