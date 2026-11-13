"""Shared validation for quantities and record identifiers."""

from math import isfinite

MAX_DATABASE_INTEGER = 2**63 - 1
MAX_PIECES = 1_000_000_000


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
