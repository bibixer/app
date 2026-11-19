"""Shared validation for quantities and record identifiers."""

from math import isfinite
import re
from unicodedata import category

MAX_DATABASE_INTEGER = 2**63 - 1
MAX_PIECES = 1_000_000_000


def identity_text(value, label):
    """Check identity fields after ordinary whitespace has been normalized."""
    joiners = {'\u200c', '\u200d'}
    if value and (not any(category(char)[0] in 'LNPS' for char in value) or
                  any(category(char) in {'Cc', 'Cf'} and char not in joiners for char in value)):
        raise ValueError(f"{label} must contain visible text without hidden formatting characters.")
    return value


def mobile_number(value):
    number = str(value).strip()
    if not re.fullmatch(r'[0-9]{10}', number) or number == '0000000000':
        raise ValueError("Enter a mobile number with exactly 10 digits.")
    return number


def positive_integer(value, maximum=MAX_DATABASE_INTEGER):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= maximum


def finite_number(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value) and value >= minimum
    except OverflowError:
        return False


def record_id(value):
    if isinstance(value, str):
        if not value or len(value) > 19 or not value.isascii() or not value.isdecimal():
            return None
        value = int(value)
    return value if positive_integer(value) else None
