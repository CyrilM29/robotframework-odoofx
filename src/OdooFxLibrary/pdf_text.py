"""The text of a PDF and the amounts Odoo writes in it: pure logic, no Odoo, no network.

Measured on Odoo 19 (2026-11-19, plan ``specs/rapport_pdf_odoo19.md``): pypdf
extracts the no-break space as an ordinary space, follows the order of the
PDF's stream (the invoice total comes first; ``layout`` gives the visual
order), cuts a reference at its hyphen when the template wraps it, and yields
the private-use glyph of an icon font. Odoo writes an amount with the
document's language (``res.lang``: decimal point, thousands separator,
grouping), the currency's decimals and symbol, a no-break space between them,
and a zero width no-break space after a minus sign.
"""

import io
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence, Union

PDF_HEADER = b"%PDF-"
EXTRA_NAME = "robotframework-odoofx[pdf]"

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_LINE_END_HYPHEN = re.compile(r"-[^\S\n]*\n\s*")
_WHITESPACE = re.compile(r"\s+")


def _is_private_use(char: str) -> bool:
    return unicodedata.category(char) == "Co"


def normalize_pdf_text(text: str) -> str:
    """``text`` as a PDF assertion compares it, the same for the PDF and the expected value.

    NFC form; zero width characters and private-use glyphs removed; every
    Unicode space becomes a space; a hyphen that ends a line joins the next
    one (a reference the template wrapped is whole again); runs of spaces and
    line breaks become one space.
    """
    text = unicodedata.normalize("NFC", text or "").translate(_ZERO_WIDTH)
    text = "".join(" " if char != "\n" and unicodedata.category(char) == "Zs" else char
                   for char in text if not _is_private_use(char))
    text = _LINE_END_HYPHEN.sub("-", text)
    return _WHITESPACE.sub(" ", text).strip()


def extract_pdf_text(pdf: bytes, layout: bool = False) -> str:
    """The raw text of every page of ``pdf``, joined by line breaks.

    Fails naming the cause: not a PDF, the extra not installed, an error of
    the extractor (its exception class), or no text layer at all, never an
    empty reading.
    """
    if not isinstance(pdf, (bytes, bytearray)) or not bytes(pdf[:5]) == PDF_HEADER:
        raise AssertionError("Not a PDF: the content does not start with %PDF-")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise AssertionError(f"pypdf module not installed: install the extra {EXTRA_NAME}") from None
    try:
        reader = PdfReader(io.BytesIO(bytes(pdf)))
        mode = "layout" if layout else "plain"
        pages = [page.extract_text(extraction_mode=mode) or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - the extractor's own failure is named, never swallowed
        raise AssertionError(f"pypdf could not read the PDF text: {type(exc).__name__}: {exc}") from None
    text = "\n".join(pages)
    if not text.strip():
        raise AssertionError(f"The PDF has no text layer: {len(pages)} page(s), no text extracted "
                             "(a scanned or image-only PDF cannot be asserted on its text)")
    return text


def _grouping(grouping: Union[str, Sequence[int]]) -> list:
    if isinstance(grouping, str):
        grouping = [int(part) for part in re.findall(r"-?\d+", grouping)]
    return list(grouping)


def group_digits(digits: str, grouping: Union[str, Sequence[int]], separator: str) -> str:
    """``digits`` grouped from the right as ``res.lang`` says: ``[3, 0]`` repeats groups of three, ``-1`` stops."""
    groups: list = []
    rest = digits
    sizes = _grouping(grouping)
    size = 0
    for index in range(len(rest) + len(sizes)):
        if not rest:
            break
        if index < len(sizes):
            if sizes[index] == -1:
                break
            if sizes[index] != 0:
                size = sizes[index]
        if size <= 0:
            break
        groups.insert(0, rest[-size:])
        rest = rest[:-size]
    if rest:
        groups.insert(0, rest)
    return separator.join(groups)


def format_odoo_amount(amount: Union[int, float, str, Decimal], decimals: int, decimal_point: str,
                       thousands_sep: str, grouping: Union[str, Sequence[int]], symbol: str = "",
                       position: str = "after") -> str:
    """``amount`` as Odoo writes it in a document: rounded half up to the currency's ``decimals``,
    grouped and punctuated by the language, the symbol before or after with a no-break space."""
    value = Decimal(str(amount)).quantize(Decimal(1).scaleb(-int(decimals)), rounding=ROUND_HALF_UP)
    sign, text = ("-", f"{-value:f}") if value < 0 else ("", f"{value:f}")
    whole, _, fraction = text.partition(".")
    number = group_digits(whole, grouping, thousands_sep)
    if int(decimals) > 0:
        number = f"{number}{decimal_point}{fraction}"
    number = number.replace(" ", "\N{NO-BREAK SPACE}")
    if sign:
        number = "-\N{ZERO WIDTH NO-BREAK SPACE}" + number
    if not symbol:
        return number
    if position == "before":
        return f"{symbol}\N{NO-BREAK SPACE}{number}"
    return f"{number}\N{NO-BREAK SPACE}{symbol}"
