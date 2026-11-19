"""Keywords for the sections of a list of lines in the web client (the sections of a sales order...).

Odoo 19 gives a section, and a subsection, no delete button: the menu of its row deletes it with every line
Odoo attaches to it, the lines below it up to the next section, or for a subsection up to the next section or
subsection, so that a section takes its subsections along (``deleteSection`` of the ``account`` module, read
in its code, then measured). Odoo 16 shows no such menu: the delete button of a section removes its row
alone, its lines stay, and `Delete Odoo Web Section` refuses there before any click. A row is known by its
``data-id``, an identity of the client that stays while a line is deleted: the deletion is waited for as the
rows Odoo keeps, never as a count.
"""

import json

from robot.api.deco import keyword

from . import web_client as wc
from . import web_lines as wl
from .rpc import OdooRpcError

SECTION_KINDS = ("line_section", "line_subsection")
_ROWS = (f"(field) => [...field.querySelectorAll({json.dumps(wc.SHOWN_LINES)})]"
         f".map((row) => ({{id: row.dataset.id || null, kind: ({wl._ROW_KIND})(row)}}))")


_EDITED_INVALID = f"{wc.EDITED_LINE} .o_field_invalid"


def _settled(kept: list, watch_invalid: bool = True) -> str:
    """Odoo shows exactly the rows ``kept``, or gave up: the line in edition holds an invalid field.

    Without ``watch_invalid`` (the section deleted is itself the line in edition, already marked invalid),
    only the rows are waited for."""
    expected = json.dumps(json.dumps(kept, separators=(",", ":")))
    rows = (f"JSON.stringify([...field.querySelectorAll({json.dumps(wc.SHOWN_LINES)})]"
            f".map((row) => row.dataset.id || null)) === {expected}")
    gave_up = f" || !!field.querySelector({json.dumps(_EDITED_INVALID)})" if watch_invalid else ""
    return f"(field) => {rows}{gave_up}"


def section_block(kinds: list, position: int) -> list:
    """The positions (1 for the first) of the lines Odoo deletes with the section at ``position``.

    ``kinds`` holds the kind of each line shown, in their order:
    ``line_section``, ``line_subsection``, ``line_note``, or a false value
    for a plain line. The block is the section and the lines below it up to
    the next section; for a subsection, up to the next section or
    subsection."""
    index = int(position) - 1
    if not 0 <= index < len(kinds):
        raise OdooRpcError(f"The list shows {len(kinds)} lines: there is no line {position}")
    if kinds[index] not in SECTION_KINDS:
        shown = "a plain line" if not kinds[index] else f"a {kinds[index]} line"
        raise OdooRpcError(f"Line {position} is {shown}, not a section: delete it with Delete Odoo Web Line")
    stops = SECTION_KINDS if kinds[index] == "line_subsection" else ("line_section",)
    end = index + 1
    while end < len(kinds) and kinds[end] not in stops:
        end += 1
    return list(range(index + 1, end + 1))


class OdooWebSectionKeywords:
    """Sections of the lists of lines in the web channel of `OdooFxLibrary`, mixed into it."""

    @keyword("Delete Odoo Web Section")
    def delete_odoo_web_section(self, field: str, position: int) -> int:
        """Delete the section at ``position`` (1 for the first) of the one2many field ``field`` with its lines.

        As Odoo 19 does it: the entry of the section's menu marked by the
        trash icon (never by its label) deletes the section and the lines
        below it up to the next section; a subsection, up to the next
        section or subsection; a section takes its subsections along. Waits
        until the list shows exactly the lines Odoo keeps, in their order,
        and returns how many it shows. Nothing is written before `Save Odoo
        Web Record`, which then deletes the lines in the database (played
        live on a draft quotation; a confirmed order is not played).

        Refused before any click, nothing changed: a position outside the
        lines; a line that is no section (`Delete Odoo Web Line` deletes it);
        a section without menu, as on Odoo 16, where the delete button of a
        section removes its row alone and its lines stay. A menu without the
        delete entry (a section that runs past the page of the list) is
        closed, then refused: held by a unit test, not played live. When a
        line in edition cannot leave the edition, Odoo deletes nothing and
        says nothing: the keyword fails at once and names the invalid fields;
        when another line in edition already holds a field marked invalid
        (Odoo gave up once), it is refused before any click. When the section
        is itself the line in edition, only its rows are waited for: the code
        of Odoo 19 deletes it without leaving the edition (read in that code,
        held by a unit test, not played live).

        Example on Odoo 19:
        | ${lines}=    `Get Odoo Web Lines`    order_line
        | Length Should Be    ${lines}    6
        | ${left}=    `Delete Odoo Web Section`    order_line    1
        | Should Be Equal As Integers    ${left}    3
        | ${saved_id}=    `Save Odoo Web Record`
        | Should Be Equal As Integers    ${saved_id}    ${quotation_id}

        Example on Odoo 16, where a section offers no menu:
        | Run Keyword And Expect Error    GLOB:*offers no section menu*
        | ...    `Delete Odoo Web Section`    order_line    1
        """
        widget = self._single_widget(field)
        rows = self._browser("Evaluate JavaScript", widget, _ROWS)
        block = section_block([row["kind"] for row in rows], position)
        if any(not row["id"] for row in rows):
            raise OdooRpcError(f"The lines of field {field} carry no data-id: the lines Odoo keeps cannot be told")
        menu = f"css={widget} {wc.SHOWN_LINES} >> nth={int(position) - 1} >> css={wc.SECTION_MENU}"
        if self._browser("Get Element Count", menu) != 1:
            raise OdooRpcError(f"Line {position} of field {field} offers no section menu: the delete button of a "
                               "section removes its row alone here (Delete Odoo Web Line), its lines stay")
        kept = [row["id"] for index, row in enumerate(rows, 1) if index not in block]
        invalid_before = self._browser("Get Element Count", f"{widget} {_EDITED_INVALID}")
        if invalid_before and self._browser("Evaluate JavaScript", widget, wl._EDITED_POSITION) != int(position):
            raise OdooRpcError(f"Section {position} of field {field} refused before any click: the line in edition "
                               f"already holds invalid fields ({self.get_odoo_web_invalid_fields()}), Odoo would "
                               "keep the section")
        self._browser("Click", menu)
        self._browser("Wait For Elements State", f"css={wc.OPEN_MENU}", "visible")
        if self._browser("Get Element Count", f"css={wc.SECTION_DELETE}") != 1:
            self._browser("Keyboard Key", "press", "Escape")
            self._browser("Wait For Elements State", f"css={wc.OPEN_MENU}", "detached")
            raise OdooRpcError(f"The menu of line {position} of field {field} offers no delete entry: the section "
                               "may run past the page of the list, or deleting is not allowed")
        self._web_filled.add(field)
        self._browser("Click", f"css={wc.SECTION_DELETE}")
        try:
            self._browser("Wait For Function", _settled(kept, not invalid_before), f"css={widget}")
        except Exception:
            raise OdooRpcError(f"Section {position} of field {field} is not deleted as Odoo deletes it: the list "
                               f"shows {self._count_lines(widget)} lines, {len(kept)} expected") from None
        shown = [row["id"] for row in self._browser("Evaluate JavaScript", widget, _ROWS)]
        if shown != kept:
            raise OdooRpcError(f"Odoo kept section {position} of field {field}: the line in edition cannot leave the "
                               f"edition ({self.get_odoo_web_invalid_fields()})")
        return len(kept)
