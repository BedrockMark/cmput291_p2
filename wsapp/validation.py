"""Parsing and validation of user-entered values.

Every parser takes the raw text, returns the parsed value, and raises
ValueError with a user-facing message when the input is invalid. They are
designed to be passed to ui.prompt_parsed. No parser touches the database,
so invalid input can never change stored data.
"""

import re
from datetime import datetime

from .db import DATE_FORMAT

MAX_TOP_N = 20
MAX_REVIEWER_LEN = 80
MAX_COMMENT_LEN = 500
MIN_RATING, MAX_RATING = 1, 5

_INT_RE = re.compile(r"[+-]?[0-9]+")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_int(text, low=None, high=None):
    """Parse a whole number, optionally requiring low <= value <= high.

    Rejects decimals ("2.5"), exponents ("1e3"), and non-ASCII digits.
    """
    text = text.strip()
    if not _INT_RE.fullmatch(text):
        raise ValueError(f"'{text}' is not a whole number.")
    value = int(text)
    if low is not None and value < low:
        raise ValueError(f"value must be at least {low}.")
    if high is not None and value > high:
        raise ValueError(f"value must be at most {high}.")
    return value


def parse_positive_int(text):
    """Parse an integer >= 1 (seat counts, minimum review counts)."""
    return parse_int(text, low=1)


def parse_top_n(text):
    """Parse n for operations 3 and 4: an integer from 1 to 20."""
    return parse_int(text, low=1, high=MAX_TOP_N)


def parse_rating(text):
    """Parse a review rating: an integer from 1 to 5."""
    return parse_int(text, low=MIN_RATING, high=MAX_RATING)


def parse_date(text):
    """Parse a strict YYYY-MM-DD calendar date into a datetime.date.

    Real calendar validation (including leap days) is done by strptime, e.g.
    2028-02-29 is valid but 2027-02-29 and 2026-04-31 are not.
    """
    text = text.strip()
    if not _DATE_RE.fullmatch(text):
        raise ValueError("date must be in YYYY-MM-DD format.")
    try:
        return datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{text} is not a valid calendar date.") from None


def parse_text(text, field, max_len):
    """Trim `text` and require 1..max_len characters; return the trimmed text."""
    text = text.strip()
    if not text:
        raise ValueError(f"{field} must not be empty.")
    if len(text) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters.")
    return text


def parse_reviewer(text):
    """Reviewer display name: 1-80 characters after trimming."""
    return parse_text(text, "Name", MAX_REVIEWER_LEN)


def parse_comment(text):
    """Review comment: 1-500 characters after trimming."""
    return parse_text(text, "Comment", MAX_COMMENT_LEN)


def parse_category(text):
    """Optional category filter: lowercased, or None when left blank.

    An unrecognized category is NOT an error (spec: it simply has no results).
    """
    text = text.strip().lower()
    return text or None


def parse_port(text):
    """Parse a TCP port number (1-65535) from the command line."""
    return parse_int(text, low=1, high=65535)
