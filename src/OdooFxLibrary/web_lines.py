"""Keywords for the lines of a one2many field of an Odoo form (the lines of a sales order...).

A cell is read on its input while the line is edited, on its text otherwise
(an empty input, such as the one Odoo 19 keeps in a product cell, never
hides the text). A line is added by the field's first add link and filled while it is the
line in edition: a field of a line is looked up inside that line only, since
an order and its lines both have a ``name``. The lines shown are read once the
list shows as many lines as the server stores for the record: right after a
save, Odoo 16 draws the list again and shows it empty for a moment (measured).
"""

import json
from typing import Any

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError

_LINE_CELLS = ("(field) => [...field.querySelectorAll('tr.o_data_row')].map((row) => Object.fromEntries("
               "[...row.querySelectorAll('td[name]')].map((cell) => [cell.getAttribute('name'), "
               "((cell.querySelector('input:not([type=hidden]), textarea') || {}).value || cell.textContent)"
               ".trim()])))")


def _shows_lines(count: int) -> str:
    return f"(field) => field.querySelectorAll({json.dumps(wc.SHOWN_LINES)}).length === {int(count)}"


class OdooWebLineKeywords:
    """Lines of one2many fields in the web channel of `OdooFxLibrary`, mixed into it."""

    def _line_relation(self, field: str) -> dict:
        model = self.get_odoo_web_view()["model"]
        definition = self._call_web_session(model, "fields_get", [[field]], {
            "attributes": ["type", "relation", "relation_field"]}).get(field) or {}
        if definition.get("type") != "one2many":
            raise OdooRpcError(f"{model}.{field} is not a one2many field: it holds no lines")
        return definition

    def _count_lines(self, widget: str) -> int:
        return self._browser("Get Element Count", f"{widget} {wc.SHOWN_LINES}")

    @keyword("Add Odoo Web Line")
    def add_odoo_web_line(self, field: str) -> int:
        """Add a line to the one2many field ``field`` (``order_line``) by its first add link.

        On a sales order the first link adds a product line (the next ones a
        section or a note). Waits until the list shows one line more, in
        edition; returns its position (1 for the first). Fill it with `Fill
        Odoo Web Line Field`; nothing is written before `Save Odoo Web Record`.

        Example:
        | ${position}=    `Add Odoo Web Line`    order_line
        | Should Be Equal As Integers    ${position}    1
        """
        widget = self._single_widget(field)
        add = f"{widget} {wc.LINE_ADD}"
        if not self._browser("Get Element Count", add):
            raise OdooRpcError(f"Field {field} offers no line to add: read-only, or not a list of lines")
        shown = self._count_lines(widget)
        self._web_filled.add(field)
        self._browser("Click", f"css={add} >> nth=0")
        self._browser("Wait For Function", _shows_lines(shown + 1), f"css={widget}")
        self._browser("Wait For Elements State", f"{widget} {wc.EDITED_LINE}", "visible")
        return shown + 1

    @keyword("Fill Odoo Web Line Field")
    def fill_odoo_web_line_field(self, field: str, line_field: str, value: Any) -> None:
        """Enter ``value`` in the field ``line_field`` of the line of ``field`` in edition.

        The same values as `Fill Odoo Web Field`: a product by its exact name
        or its database id (read on the line's model), a quantity typed as
        text, then left so that Odoo takes it. The value is read back on the
        line at once.

        Example:
        | `Fill Odoo Web Line Field`    order_line    product_template_id    ${product_id}
        | `Fill Odoo Web Line Field`    order_line    product_uom_qty    2
        """
        edited = f"{self._single_widget(field)} {wc.EDITED_LINE}"
        if self._browser("Get Element Count", edited) != 1:
            raise OdooRpcError(f"No line of field {field} is in edition: add one with Add Odoo Web Line")
        widget = f'{edited} .o_field_widget[name="{wc.require_field_name(line_field)}"]'
        if self._browser("Get Element Count", widget) != 1:
            raise OdooRpcError(f"The line of {field} in edition shows no field {line_field}")
        self._fill_widget(widget, self._line_relation(field)["relation"], line_field, value)

    @keyword("Get Odoo Web Lines")
    def get_odoo_web_lines(self, field: str) -> list:
        """The lines the field ``field`` shows: one dictionary per line, cell text by field name.

        On a saved record, waits until the list shows as many lines as the
        server stores for it (read through the web session), so that a list
        drawn again after a save is never read empty. Texts are the client's,
        in the user's language and number format: compare stored values by a
        read through the session.

        Example:
        | ${lines}=    `Get Odoo Web Lines`    order_line
        | Length Should Be    ${lines}    1
        | Should Be Equal    ${lines}[0][product_template_id]    ${product_name}
        """
        widget = self._single_widget(field)
        record_id = wc.parse_web_location(self._browser("Get Url"))["record_id"]
        if record_id is not None and not self._browser("Get Element Count", wc.FORM_DIRTY):
            definition = self._line_relation(field)
            stored = self._call_web_session(definition["relation"], "search_count", [
                [[definition["relation_field"], "=", record_id]]], {})
            try:
                self._browser("Wait For Function", _shows_lines(stored), f"css={widget}")
            except Exception:
                raise OdooRpcError(f"Field {field} shows {self._count_lines(widget)} lines, "
                                   f"the record stores {stored}") from None
        return self._browser("Evaluate JavaScript", widget, _LINE_CELLS)
