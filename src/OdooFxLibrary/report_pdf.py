"""Keywords that read an Odoo report as a PDF and assert its text.

The PDF comes from Odoo's report route, ``/report/pdf/<report_name>/<ids>``,
on a web session of the proven target: the route a user's Print button
reaches, never a browser download, which depends on the browser's folder and
settings. The API key alone does not open the route (Odoo answers 303 to the
login page, measured on Odoo 19); a web session opened by `Create Odoo Http
Session` does. A report whose action has ``attachment`` set makes Odoo save
the PDF as an attachment when it prints it: a write behind the caller's back,
refused unless the caller accepts it.
"""

from typing import Union

from robot.api import logger
from robot.api.deco import keyword

from .pdf_text import PDF_HEADER, extract_pdf_text, format_odoo_amount, normalize_pdf_text
from .rpc import OdooRpcError, TIMEOUT

REPORT_MODEL = "ir.actions.report"
REPORT_FIELDS = ["report_name", "model", "report_type", "attachment", "attachment_use"]
PDF_CONTENT_TYPE = "application/pdf"
EXCERPT_LENGTH = 300


def report_route(report_name: str, record_ids: Union[int, str, list]) -> str:
    """``/report/pdf/<report_name>/<ids>``, the ids joined by commas."""
    if isinstance(record_ids, (list, tuple)):
        ids = [int(record_id) for record_id in record_ids]
    else:
        ids = [int(part) for part in str(record_ids).split(",") if part.strip()]
    if not ids:
        raise OdooRpcError("No record to print: give one id or a list of ids")
    return f"/report/pdf/{report_name}/{','.join(str(record_id) for record_id in ids)}"


def judged_pdf(status: int, content_type: str, location: str, body: bytes, route: str) -> bytes:
    """``body`` when Odoo answered a PDF; otherwise the failure names what came back, never the body."""
    if status in (301, 302, 303, 307, 308):
        raise AssertionError(f"{route}: Odoo answered {status} towards {location or 'no Location'}, "
                             "the session is not logged in (an API key alone does not open a report)")
    if status != 200:
        raise AssertionError(f"{route}: Odoo answered HTTP {status}")
    if not (content_type or "").lower().startswith(PDF_CONTENT_TYPE):
        raise AssertionError(f"{route}: Odoo answered {content_type or 'no Content-Type'}, not a PDF")
    if not bytes(body[:5]) == PDF_HEADER:
        raise AssertionError(f"{route}: the content does not start with %PDF-")
    return bytes(body)


def text_of(pdf: Union[bytes, bytearray, str], layout: bool = False) -> str:
    """The normalized text of ``pdf``: a PDF's bytes are extracted, a text is only normalized."""
    if isinstance(pdf, str):
        return normalize_pdf_text(pdf)
    return normalize_pdf_text(extract_pdf_text(pdf, layout=layout))


class OdooReportPdfKeywords:
    """The report keywords of `OdooFxLibrary`, mixed into it."""

    def _report_action(self, report_name: str) -> dict:
        found = self._require_channel().search_read(
            REPORT_MODEL, [["report_name", "=", report_name]], REPORT_FIELDS, limit=1,
            context={"active_test": False})
        if not found:
            raise OdooRpcError(f"No report action named {report_name!r} on this database")
        return found[0]

    @keyword("Get Odoo Report Pdf")
    def get_odoo_report_pdf(self, report_name: str, record_ids: Union[int, str, list], alias: str,
                            allow_attachment: bool = False) -> bytes:
        """Return the PDF Odoo prints for ``report_name`` on ``record_ids``, through the web session ``alias``.

        ``report_name`` is the technical name of the report action
        (``sale.report_saleorder``, ``account.report_invoice_with_payments``,
        ``stock.report_deliveryslip``), ``record_ids`` an id or a list of ids,
        ``alias`` a session of `Create Odoo Http Session` on the proven target.
        The action is read first, by the RPC connection: an unknown name, a
        report that is not ``qweb-pdf``, or an action whose ``attachment`` is set
        (Odoo would save the PDF as an attachment while printing it) is refused
        before any request; ``allow_attachment=${TRUE}`` accepts that save, on a
        connection opened with ``allow_write=${TRUE}``. The route is called
        without following a redirect and fails naming what Odoo answered: a
        redirect (the session is not logged in), another status (a 500 for an
        unknown record), a type other than ``application/pdf``, or a content
        that does not start with ``%PDF-``. Returns the PDF's bytes, for
        `Get Pdf Text` or `Pdf Should Contain`.

        Example:
        | `Create Odoo Http Session`    odoo-web    ${LOGIN}    ${PASSWORD}
        | ${pdf}=    `Get Odoo Report Pdf`    sale.report_saleorder    ${quotation_id}    odoo-web
        | `Pdf Should Contain`    ${pdf}    ${quotation_name}
        """
        action = self._report_action(report_name)
        if action.get("report_type") != "qweb-pdf":
            raise OdooRpcError(f"{report_name} is a {action.get('report_type')} report, not a PDF one")
        if action.get("attachment"):
            if not allow_attachment:
                raise OdooRpcError(
                    f"{report_name} saves the PDF it prints as an attachment (attachment="
                    f"{action['attachment']!r}): refused before printing; allow_attachment=${{TRUE}} "
                    "accepts that Odoo writes it")
            if not self._require_channel_info().get("allow_write"):
                raise OdooRpcError(
                    f"{report_name} would save an attachment: allow_attachment needs a connection "
                    "opened with allow_write=${TRUE}")
        route = report_route(report_name, record_ids)
        session = self._http_session(alias)
        reply = session.get(f"{session.url}{route}", allow_redirects=False, timeout=TIMEOUT)
        pdf = judged_pdf(reply.status_code, reply.headers.get("Content-Type", ""),
                         reply.headers.get("Location", ""), reply.content, route)
        logger.info(f"{route}: a PDF of {len(pdf)} bytes on session {alias}"
                    + (", attachment accepted" if action.get("attachment") else ""))
        return pdf

    @keyword("Get Pdf Text")
    def get_pdf_text(self, pdf: Union[bytes, bytearray], layout: bool = False) -> str:
        """Return the text of every page of ``pdf``, normalized as `Pdf Should Contain` compares it.

        Normalized: Unicode spaces (the no-break space included) become a
        space, runs of spaces and line breaks one space, the private-use
        glyphs of an icon font and the zero width characters go, a hyphen that
        ends a line joins the next one, and the text takes the NFC form. The
        default extraction follows the PDF's stream (an invoice may give its
        total first); ``layout=${TRUE}`` follows the page's visual order. Fails
        naming the cause: not a PDF, ``pypdf`` not installed (the extra
        ``robotframework-odoofx[pdf]``), an error of the extractor, or no text
        layer at all, never an empty text.

        Example:
        | ${text}=    `Get Pdf Text`    ${pdf}
        | Should Contain    ${text}    ${quotation_name}
        """
        return text_of(pdf, layout=layout)

    @keyword("Pdf Should Contain")
    def pdf_should_contain(self, pdf: Union[bytes, bytearray, str], expected: str) -> None:
        """Fail unless the text of ``pdf`` contains ``expected``, both normalized as `Get Pdf Text` does.

        ``pdf`` is a PDF's bytes or a text `Get Pdf Text` already returned.
        The failure names the value searched and an excerpt of the text.

        Example:
        | ${total}=    `Get Odoo Formatted Amount`    ${amount_total}    USD    fr_FR
        | `Pdf Should Contain`    ${pdf}    ${total}
        """
        text = text_of(pdf)
        wanted = normalize_pdf_text(str(expected))
        if not wanted:
            raise AssertionError("Pdf Should Contain needs a non-empty expected value")
        if wanted not in text:
            raise AssertionError(f"The PDF text does not contain {wanted!r}; it starts with "
                                 f"{text[:EXCERPT_LENGTH]!r}")

    @keyword("Pdf Should Not Contain")
    def pdf_should_not_contain(self, pdf: Union[bytes, bytearray, str], unexpected: str) -> None:
        """Fail when the text of ``pdf`` contains ``unexpected``, both normalized as `Get Pdf Text` does.

        The absence `Should Not Contain` cannot prove on that text: a value
        written with no-break spaces (an amount of `Get Odoo Formatted Amount`)
        is never found in the normalized text, so it always passes. Here both
        sides are normalized alike. The failure names the value found and the
        text around it.

        Example:
        | ${en_total}=    `Get Odoo Formatted Amount`    ${amount_total}    USD    en_US
        | `Pdf Should Not Contain`    ${pdf}    ${en_total}
        """
        text = text_of(pdf)
        unwanted = normalize_pdf_text(str(unexpected))
        if not unwanted:
            raise AssertionError("Pdf Should Not Contain needs a non-empty unexpected value")
        index = text.find(unwanted)
        if index >= 0:
            around = text[max(0, index - 60):index + len(unwanted) + 60]
            raise AssertionError(f"The PDF text contains {unwanted!r}: ...{around}...")

    @keyword("Get Odoo Formatted Amount")
    def get_odoo_formatted_amount(self, amount: Union[int, float, str], currency: str, lang: str) -> str:
        """Return ``amount`` as Odoo writes it in a document of language ``lang`` in ``currency``.

        ``currency`` is the ISO code (``EUR``), ``lang`` the language code
        (``fr_FR``): the language of the document, which is the partner's (the
        user's when the partner has none), not necessarily the user's. Both
        are read by the RPC connection (``res.currency``: symbol, position,
        decimals; ``res.lang``: decimal point, thousands separator, grouping),
        inactive ones included. The amount is rounded half up to the
        currency's decimals, a no-break space separates it from the symbol, as
        Odoo's monetary widget writes it.

        Example:
        | ${total}=    `Get Odoo Formatted Amount`    1230.0    USD    en_US
        | Should Be Equal    ${total}    $\\xa01,230.00
        """
        channel = self._require_channel()
        context = {"active_test": False}
        currencies = channel.search_read("res.currency", [["name", "=", currency]],
                                         ["symbol", "position", "decimal_places"], limit=1, context=context)
        if not currencies:
            raise OdooRpcError(f"No currency {currency!r} on this database")
        langs = channel.search_read("res.lang", [["code", "=", lang]],
                                    ["decimal_point", "thousands_sep", "grouping"], limit=1, context=context)
        if not langs:
            raise OdooRpcError(f"No language {lang!r} on this database")
        found, language = currencies[0], langs[0]
        return format_odoo_amount(amount, found["decimal_places"], language["decimal_point"],
                                  language["thousands_sep"] or "", language["grouping"],
                                  found["symbol"] or "", found["position"] or "after")
