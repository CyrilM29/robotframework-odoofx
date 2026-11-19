"""Keywords that open a record in the web client by its id (a quotation a suite created over RPC...).

The address is the one of the web client shown, never chosen by version: an ``/odoo/...`` path (Odoo 17 and
later) opens ``/odoo/<model>/<id>``, a ``/web#...`` fragment (Odoo 16) opens ``/web#id=<id>&model=<model>``
with the form view. The record is first found through the web session, so that a missing or unreadable record
is refused before the page changes; once shown, the form must carry that model and that id. The page left may
show no view at all (Discuss, the first page of Odoo 19 after the login): its view is read only when it has one.
"""

import re
from urllib.parse import urlencode, urlsplit

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError

_MODEL = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def record_address(current_url: str, model: str, record_id: int) -> str:
    """The address of the form of record ``record_id`` of ``model``, in the scheme of ``current_url``."""
    if not _MODEL.match(model or ""):
        raise OdooRpcError(f"Not a model name: {model!r} (a technical name such as sale.order)")
    if isinstance(record_id, bool) or not str(record_id).isdigit() or int(record_id) < 1:
        raise OdooRpcError(f"Not a record id: {record_id!r} (a positive integer)")
    location = wc.parse_web_location(current_url)
    parts = urlsplit(current_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if location["scheme"] == "path":
        return f"{origin}/odoo/{model}/{int(record_id)}"
    return f"{origin}/web#" + urlencode({"id": int(record_id), "model": model, "view_type": "form"})


class OdooWebRecordKeywords:
    """Records opened by id in the web channel of `OdooFxLibrary`, mixed into it."""

    @keyword("Open Odoo Web Record By Id")
    def open_odoo_web_record_by_id(self, model: str, record_id: int) -> int:
        """Open the form of the record ``record_id`` of ``model`` in the web client and return its id.

        The record is found through the web session first, an archived one
        included (Odoo shows it with its ribbon): a record that does not
        exist, or that the user cannot read, is refused before the page
        changes, and so is leaving a form with unsaved changes (Odoo would
        save them). The address follows the one the web client shows
        (``/odoo/<model>/<id>`` from Odoo 17, ``/web#id=...&model=...`` on
        Odoo 16). Waits for the form view, then checks that it shows that
        model and that id. A record already shown in its form is left as it
        is. The refusals (a record missing or unreadable, an unsaved form)
        are held by unit tests, not played live.

        Example:
        | ${opened}=    `Open Odoo Web Record By Id`    sale.order    ${quotation_id}
        | Should Be Equal As Integers    ${opened}    ${quotation_id}
        | `Select Odoo Web Form Tab`    order_lines
        """
        if not self.odoo_web_client_is_shown():
            raise OdooRpcError("The web client is not shown: log in first (Log In To Odoo Web Client)")
        current = self._browser("Get Url")
        address = record_address(current, model, record_id)
        record_id = int(record_id)
        if self._browser("Get Element Count", wc.ACTION):
            view = self.get_odoo_web_view()
            if view["view_type"] == "form" and view["model"] == model and view["record_id"] == record_id:
                return record_id
        # An archived record opens too, as the web client opens it by its address.
        if not self._call_web_session(model, "search_count", [[["id", "=", record_id]]],
                                      {"context": {"active_test": False}}):
            raise OdooRpcError(f"No record {record_id} of {model} the user can read: nothing opened")
        self._refuse_leaving_unsaved_form("Open Odoo Web Record By Id")
        self._mark_current_view()
        self._browser("Go To", address)
        self._wait_for_new_view()
        self._web_filled = set()
        shown = self.get_odoo_web_view()
        if (shown["view_type"], shown["model"], shown["record_id"]) != ("form", model, record_id):
            raise OdooRpcError(f"Odoo shows a {shown['view_type']} view of {shown['model']} "
                               f"(record {shown['record_id']}) instead of the form of {model} {record_id}")
        return record_id
