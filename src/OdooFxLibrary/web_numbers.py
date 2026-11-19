"""Pure logic of the numbers the web client shows and takes: written in the user's language, read back as numbers.

Odoo writes a number in the format of ``res.lang`` (its decimal point, its
thousands separator), groups digits with spaces that may be no-break ones,
and puts a currency symbol before or after a monetary amount (measured on
Odoo 16 and 19: ``$ 37 957,80`` under ``fr_FR``, plans
``specs/devis_web_odoo16.md`` and ``_odoo19.md``). Functions of strings
only, unit tested without Odoo.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .rpc import OdooRpcError

# Spaces a language may group digits with, beside its own thousands separator: space, no-break, narrow no-break.
DIGIT_SPACES = (" ", " ", " ")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MINUS_SIGNS = ("-", chr(0x2212))


def _decimal_of(value: Any) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        number = None
    if isinstance(value, bool) or number is None or not number.is_finite():
        raise OdooRpcError(f"Expected a number such as 2.5, got {value!r}")
    return number


def number_text(value: Any, decimal_point: str) -> str:
    """A number (``2``, ``2.5``, ``${2.5}``) written with the decimal point of the user's language (``2,5``)."""
    return format(_decimal_of(value), "f").replace(".", decimal_point)


def input_shows_number(value: Any, decimal_point: str, thousands_sep: str) -> str:
    """A predicate for Browser's ``Wait For Function``: the input shows ``value`` in the user's number format.

    Odoo writes a number again in its own format once it took it (``2`` is
    shown ``2,00``), and may draw the former value first while the line's
    other changes come back: the shown text is read as a number."""
    separators = sorted({sep for sep in (thousands_sep, *DIGIT_SPACES) if sep and sep != decimal_point})
    return ("(input) => { let text = input.value; "
            f"for (const sep of {json.dumps(separators, ensure_ascii=False)}) {{ text = text.split(sep).join(''); }} "
            f"text = text.split({json.dumps(decimal_point, ensure_ascii=False)}).join('.').trim(); "
            f"return text !== '' && Math.abs(Number(text) - {float(_decimal_of(value))!r}) < 1e-9; }}")


def read_shown_number(text: str, decimal_point: str, thousands_sep: str) -> Optional[float]:
    """The number a field shows in the user's format (``$ 37 957,80``, ``37.957,80 €``), ``None`` when it shows none.

    The language's thousands separator and the grouping spaces are dropped,
    its decimal point becomes ``.``, and the first number left is read: a
    currency symbol, before or after it, does not count, and a minus sign
    anywhere before the first digit makes it negative (``-$ 12,50``)."""
    shown = str(text or "")
    for separator in {thousands_sep, *DIGIT_SPACES} - {decimal_point, ""}:
        shown = shown.replace(separator, "")
    if decimal_point:
        shown = shown.replace(decimal_point, ".")
    match = _NUMBER.search(shown)
    if match:
        negative = any(sign in shown[:match.start()] for sign in _MINUS_SIGNS)
        return -float(match.group()) if negative else float(match.group())
    if shown.strip():
        raise OdooRpcError(f"Expected a number in the field, it shows {text!r}")
    return None
