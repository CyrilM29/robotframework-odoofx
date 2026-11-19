"""Keywords for the lines of a one2many field of an Odoo form (the lines of a sales order...).

A cell is read on its input while the line is edited, on its text otherwise
(an empty input, such as the one Odoo 19 keeps in a product cell, never
hides the text). A line is added by an add link and filled while it is the
line in edition: a field of a line is looked up inside that line only, since
an order and its lines both have a ``name``. The lines shown are read once the
list shows as many lines as the server stores for the record: right after a
save, Odoo 16 draws the list again and shows it empty for a moment (measured).

The add links carry neither name nor context in the page: which one adds a
section or a note is read in the form view's arch, where each ``create`` of
the list's ``control`` sets the ``default_display_type`` of the line it adds.
A row tells its kind by its class ``o_is_<display_type>`` (Odoo 16 and 19).
"""

import json
import re
from typing import Any, Optional
from xml.etree import ElementTree

from robot.api.deco import keyword

from . import web_client as wc
from . import web_numbers as wn
from .rpc import OdooRpcError

_NUMBER_TYPES = ("float", "integer", "monetary")
_DEFAULT_DISPLAY_TYPE = re.compile(r"""['"]default_display_type['"]\s*:\s*['"]([a-z_]+)['"]""")
# The kind of a row: false for a plain line, line_section, line_note..., undefined outside a section and note list.
_KIND = ("[...row.classList].filter((name) => name.startsWith('o_is_')).map((name) => name.slice(5))"
         ".find((kind) => kind === 'false' || kind.startsWith('line_'))")
_ROW_KIND = f"(row) => {{ const kind = {_KIND}; return kind === undefined ? null : kind !== 'false' && kind; }}"
_LINE_CELLS = ("(field) => [...field.querySelectorAll('tr.o_data_row')].map((row) => { "
               f"const kind = {_KIND}; const line = {{}}; "
               "for (const cell of row.querySelectorAll('td[name]')) { "
               f"const label = kind && kind !== 'false' && cell.querySelector('{wc.LINE_LABEL}'); "
               "const input = cell.querySelector('input:not([type=hidden]), textarea'); "
               f"line[label ? '{wc.LINE_LABEL_FIELD}' : cell.getAttribute('name')] = "
               "((input || {}).value || cell.textContent).trim(); } "
               "if (kind !== undefined) { line.display_type = kind !== 'false' && kind; } return line; })")
_EDITED_POSITION = (f"(field) => [...field.querySelectorAll({json.dumps(wc.SHOWN_LINES)})]"
                    ".findIndex((row) => row.classList.contains('o_selected_row')) + 1")


def _shows_lines(count: int) -> str:
    return f"(field) => field.querySelectorAll({json.dumps(wc.SHOWN_LINES)}).length === {int(count)}"


def line_add_types(arch: str, field: str) -> list:
    """The display types of the lines the add links of ``field`` add, in their order (``None`` for a plain line).

    Read in a form view's arch: the ``create`` entries of the ``control`` of
    the field's list (its buttons are no links); a list without ``control``
    has one link, for a plain line."""
    found = []
    for node in ElementTree.fromstring(arch).iter("field"):
        lists = [child for child in node if child.tag in ("list", "tree")] if node.get("name") == field else []
        if not lists:
            continue
        control = lists[0].find("control")
        if control is None:
            found.append([None])
            continue
        found.append([(_DEFAULT_DISPLAY_TYPE.search(create.get("context") or "") or [None, None])[1]
                      for create in control if create.tag == "create"])
    if not found:
        raise OdooRpcError(f"The form view holds no list of lines for field {field}")
    if any(types != found[0] for types in found[1:]):
        raise OdooRpcError(f"The form view holds lists of field {field} with different add links: {found}")
    return found[0]


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

    def _form_view(self, toolbar: bool = False) -> dict:
        """The form view shown (``arch``, and its ``toolbar`` when asked): the one its action names, else the
        model's default form."""
        location = wc.parse_web_location(self._browser("Get Url"))
        view_id = False
        if location["action"] and not (location["scheme"] == "path" and location["model"]):
            views = self._read_window_action(location["action"], ["views"])["views"]
            view_id = next((view for view, view_type in views if view_type == "form"), False)
        views = self._call_web_session(self.get_odoo_web_view()["model"], "get_views", [], {
            "views": [[view_id, "form"]], "options": {"toolbar": True} if toolbar else {}})
        return views["views"]["form"]

    def _form_view_arch(self) -> str:
        return self._form_view()["arch"]

    def _add_link_of(self, field: str, display_type: str, links: int) -> int:
        types = line_add_types(self._form_view_arch(), field)
        if len(types) != links:
            raise OdooRpcError(f"Field {field} shows {links} add links, its view declares {len(types)}: "
                               "a link is hidden, the links cannot be told apart")
        if display_type not in types:
            raise OdooRpcError(f"Field {field} offers no link that adds a {display_type} line: "
                               f"its links add {types}")
        return types.index(display_type)

    @keyword("Add Odoo Web Line")
    def add_odoo_web_line(self, field: str, display_type: Optional[str] = None) -> int:
        """Add a line to the one2many field ``field`` (``order_line``) and return its position (1 for the first).

        Without ``display_type`` the first add link is clicked (a product line
        on a sales order). With it (``line_section``, ``line_note``), the
        link the form view associates with that type in its arch, never by
        its label; the line added must show that type. Waits until the list
        shows one line more, in edition. Fill it with `Fill Odoo Web Line
        Field`; nothing is written before `Save Odoo Web Record`.

        Example:
        | ${position}=    `Add Odoo Web Line`    order_line
        | Should Be Equal As Integers    ${position}    1
        | `Fill Odoo Web Line Field`    order_line    product_template_id    ${product_id}
        | ${position}=    `Add Odoo Web Line`    order_line    display_type=line_section
        | Should Be Equal As Integers    ${position}    2
        """
        widget = self._single_widget(field)
        add = f"{widget} {wc.LINE_ADD}"
        links = self._browser("Get Element Count", add)
        if not links:
            raise OdooRpcError(f"Field {field} offers no line to add: read-only, or not a list of lines")
        link = self._add_link_of(field, display_type, links) if display_type else 0
        shown = self._count_lines(widget)
        self._web_filled.add(field)
        self._browser("Click", f"css={add} >> nth={link}")
        try:
            self._browser("Wait For Function", _shows_lines(shown + 1), f"css={widget}")
        except Exception:
            raise OdooRpcError(f"Field {field} added no line: the line in edition may be invalid "
                               f"({self.get_odoo_web_invalid_fields()})") from None
        edited = f"{widget} {wc.EDITED_LINE}"
        self._browser("Wait For Elements State", edited, "visible")
        if display_type:
            added = self._browser("Evaluate JavaScript", edited, _ROW_KIND)
            if added != display_type:
                raise OdooRpcError(f"The link of field {field} for {display_type} added a {added!r} line")
        return self._browser("Evaluate JavaScript", widget, _EDITED_POSITION)

    @keyword("Fill Odoo Web Line Field")
    def fill_odoo_web_line_field(self, field: str, line_field: str, value: Any) -> None:
        """Enter ``value`` in the field ``line_field`` of the line of ``field`` in edition.

        The same values as `Fill Odoo Web Field`: a product by its exact name
        or its database id (read on the line's model), a quantity typed as
        text. Typed text is committed by the ``change`` event the browser
        fires on leaving a field, never by Tab, which on the last cell of the
        last line adds a line. The text of a section or a note is its
        ``name``: Odoo 19 shows no ``name`` field on such a line and types it
        in the product cell, which this keyword fills then. The value is read
        back on the line at once.

        Example:
        | `Fill Odoo Web Line Field`    order_line    product_template_id    ${product_id}
        | `Fill Odoo Web Line Field`    order_line    product_uom_qty    2.4
        | `Add Odoo Web Line`    order_line    display_type=line_note
        | `Fill Odoo Web Line Field`    order_line    name    ${marker} Note
        """
        edited = f"{self._single_widget(field)} {wc.EDITED_LINE}"
        if self._browser("Get Element Count", edited) != 1:
            raise OdooRpcError(f"No line of field {field} is in edition: add one with Add Odoo Web Line")
        widget = f'{edited} .o_field_widget[name="{wc.require_field_name(line_field)}"]'
        if self._browser("Get Element Count", widget) == 1:
            self._fill_widget(widget, self._line_relation(field)["relation"], line_field, value, in_line=True)
            return
        label = f"{edited} {wc.LINE_LABEL}"
        if (line_field != wc.LINE_LABEL_FIELD or not self._browser("Evaluate JavaScript", edited, _ROW_KIND)
                or self._browser("Get Element Count", label) != 1):
            raise OdooRpcError(f"The line of {field} in edition shows no field {line_field}")
        self._type_text(label, line_field, str(value), in_line=True)

    @keyword("Get Odoo Web Lines")
    def get_odoo_web_lines(self, field: str) -> list:
        """The lines the field ``field`` shows: one dictionary per line, cell text by field name.

        On a saved record, waits until the list shows as many lines as the
        server stores for it (read through the web session), so that a list
        drawn again after a save is never read empty. Texts are the client's,
        in the user's language and number format: compare stored values by a
        read through the session. In a list of sections and notes each line
        also holds its ``display_type`` (``False`` for a plain line,
        ``line_section``, ``line_note``) and the text of a section or a note
        under ``name``, also on Odoo 19 where the product cell shows it.

        Example:
        | ${lines}=    `Get Odoo Web Lines`    order_line
        | Length Should Be    ${lines}    1
        | Should Be Equal    ${lines}[0][product_template_id]    ${product_name}
        | Should Be Equal    ${lines}[0][display_type]    ${FALSE}
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

    @keyword("Get Odoo Web Line Field Value")
    def get_odoo_web_line_field_value(self, field: str, position: int, line_field: str) -> Any:
        """The value the line at ``position`` (1 for the first) of the one2many field ``field`` shows in ``line_field``.

        A numeric field of the line (``float``, ``integer`` or ``monetary``,
        its type read on the model of the lines) is read as a number, the way
        `Get Odoo Web Field Value` reads one: the text shown, in the number
        format of the user's language, without the currency symbol; an
        integer for an ``integer`` field, ``None`` for an empty cell. Any
        other field is the text of its cell, as `Get Odoo Web Lines` gives
        it, after the same wait for the lines the record stores.

        Example:
        | `Select Odoo Web Form Tab`    order_lines
        | ${quantity}=    `Get Odoo Web Line Field Value`    order_line    1    product_uom_qty
        | Should Be Equal As Numbers    ${quantity}    1234.4
        """
        name = wc.require_field_name(line_field)
        lines = self.get_odoo_web_lines(field)
        if not 1 <= int(position) <= len(lines):
            raise OdooRpcError(f"Field {field} shows {len(lines)} lines: there is no line {position}")
        cells = lines[int(position) - 1]
        if name not in cells:
            raise OdooRpcError(f"Line {position} of field {field} shows no field {line_field}")
        model = self._line_relation(field)["relation"]
        kind = (self._call_web_session(model, "fields_get", [[name]], {"attributes": ["type"]}).get(name) or {})
        if kind.get("type") not in _NUMBER_TYPES:
            return cells[name]
        lang = self._lang_format()
        number = wn.read_shown_number(cells[name], lang["decimal_point"], lang["thousands_sep"])
        return int(number) if number is not None and kind["type"] == "integer" else number

    @keyword("Delete Odoo Web Line")
    def delete_odoo_web_line(self, field: str, position: int) -> int:
        """Delete the line at ``position`` (1 for the first) of the one2many field ``field`` by its delete button.

        Waits until the list shows one line less and returns how many it
        shows. Nothing is written before `Save Odoo Web Record`, which then
        deletes the line in the database. A line without delete button is
        refused: on Odoo 19 a section has none, its menu deletes it with all
        its lines.

        Example:
        | `Add Odoo Web Line`    order_line    display_type=line_note
        | `Fill Odoo Web Line Field`    order_line    name    ${marker} Note
        | `Save Odoo Web Record`
        | ${left}=    `Delete Odoo Web Line`    order_line    2
        | Should Be Equal As Integers    ${left}    1
        | `Save Odoo Web Record`
        """
        widget = self._single_widget(field)
        shown = self._count_lines(widget)
        if not 1 <= int(position) <= shown:
            raise OdooRpcError(f"Field {field} shows {shown} lines: there is no line {position}")
        button = f"css={widget} {wc.SHOWN_LINES} >> nth={int(position) - 1} >> css={wc.LINE_DELETE}"
        if self._browser("Get Element Count", button) != 1:
            raise OdooRpcError(f"Line {position} of field {field} offers no delete button")
        self._web_filled.add(field)
        self._browser("Click", button)
        try:
            self._browser("Wait For Function", _shows_lines(shown - 1), f"css={widget}")
        except Exception:
            raise OdooRpcError(f"Line {position} of field {field} is still shown: Odoo kept it") from None
        return shown - 1
