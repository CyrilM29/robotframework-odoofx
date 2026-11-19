"""Keywords that fill and save Odoo forms through the web client, built on the Browser library.

A value is typed or picked the way a user does it, then read back on the
screen: a field the client did not take fails the keyword at once. A
relational value is picked among the client's proposals by its exact name,
never through the Create or Search more options, which would write or open a
dialog. Typed text is committed by leaving the field (Tab): Odoo marks the
form as changed only then. In a line of a one2many it is committed by the
``change`` event the browser fires on leaving a field: Tab on the last cell of
the last line adds a line (Odoo 16 and 19).
"""

import json
from typing import Any, Optional

from robot.api import logger
from robot.api.deco import keyword

from . import web_client as wc
from . import web_numbers as wn
from .rpc import OdooRpcError, compact

# Each proposal as [its whole text, its label without what it sets apart, that set-apart text]: Odoo 19 shows a
# product's internal reference in a muted span after its name, where Odoo 16 shows the display name whole.
_PROPOSALS = (f"(widget) => [...widget.querySelectorAll('{wc.AUTOCOMPLETE_ITEMS}')].map((item) => {{ "
              "const label = item.cloneNode(true); label.querySelectorAll('.text-muted').forEach((n) => n.remove()); "
              "const aside = [...item.querySelectorAll('.text-muted')].map((n) => n.textContent.trim()).join(' '); "
              "return [item.textContent.trim(), label.textContent.trim(), aside]; })")
_TAGS = ("(widget) => [...widget.querySelectorAll('.o_tag')]"
         ".map((tag) => (tag.querySelector('.o_tag_badge_text') || tag).textContent.trim())")
_CHECKED_RADIO = "(widget) => (widget.querySelector('input.o_radio_input:checked') || {}).id || ''"
_INVALID_NAMES = ("(action) => [...action.querySelectorAll('.o_field_invalid[name]')]"
                  ".map((field) => field.getAttribute('name'))")
_CHANGE = "(input) => input.dispatchEvent(new Event('change', {bubbles: true}))"


def _includes(script: str, text: str) -> str:
    """A predicate for Browser's ``Wait For Function``: the texts ``script`` lists include ``text``."""
    return f"(element) => ({script})(element).includes({json.dumps(text)})"


class OdooWebFormKeywords:
    """Form entry of the web channel of `OdooFxLibrary`, mixed into it with `OdooWebKeywords`."""

    def _single_widget(self, field: str) -> str:
        widget = wc.field_widget(field)
        shown = self._browser("Get Element Count", widget)
        if shown != 1:
            raise OdooRpcError(f"The view shows {shown} widgets of field {field}, expected one: "
                               "a field of another tab is shown after `Select Odoo Web Form Tab`")
        return widget

    def _journal_web_write(self, gesture: str, operation: str, method: str, model: str,
                           record_id: Optional[int], fields: Optional[set] = None) -> dict:
        if not self._web_writes:
            raise OdooRpcError(f"Writes are off: {gesture} refused, log in to the web client "
                               "with allow_write=${TRUE}")
        entry = {"seq": len(self._journal) + 1, "phase": "planned", "operation": operation,
                 "database": self.get_odoo_web_session_info()["database"], "model": model, "method": method,
                 "ids": [record_id] if record_id is not None else [],
                 "fields": sorted(self._web_filled if fields is None else fields)}
        self._journal.append(entry)
        logger.info(f"write {entry['seq']} planned: {operation} {model} {method} through the web client "
                    f"{entry['ids']}")
        return entry

    @staticmethod
    def _settle(entry: dict, phase: str, error: str = "", error_class: str = "") -> None:
        entry["phase"] = phase
        if error:
            entry["error"] = error
        if error_class:
            entry["error_class"] = error_class
        logger.info(f"write {entry['seq']} {phase}{': ' + error if error else ''}")

    def _typing_marked(self) -> bool:
        """Whether the form shows Odoo's mark of a change, waited for after a typing of the library.

        Odoo 16 marks a field changed only once its onchange answered (measured on odoo16, 2026-11-16): right
        after `Fill Odoo Web Field`, a form still shown saved may be about to change. A typing that changed
        nothing never gets the mark, and costs the wait."""
        if self._browser("Get Element Count", wc.FORM_DIRTY):
            return True
        if not self._web_filled:
            return False
        try:
            self._browser("Wait For Elements State", f"css={wc.FORM_DIRTY}", "visible")
        except Exception:
            return False
        return True

    def _require_form(self) -> Optional[int]:
        if self._browser("Get Element Count", wc.FORM_STATE) != 1:
            raise OdooRpcError("No form is shown")
        return wc.parse_web_location(self._browser("Get Url"))["record_id"]

    def _commit_typed(self, target: str, in_line: bool) -> None:
        if in_line:
            self._browser("Evaluate JavaScript", target, _CHANGE)
        else:
            self._browser("Press Keys", target, "Tab")

    def _type_text(self, widget: str, field: str, text: str, in_line: bool = False) -> None:
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target) != 1:
            raise OdooRpcError(f"Field {field} offers no single text input to fill")
        self._browser("Fill Text", target, text)
        self._commit_typed(target, in_line)
        try:
            self._browser("Wait For Function", wc.input_shows_text(text), f"css={target}")
        except Exception:
            shown = self._browser("Get Property", target, "value")
            raise OdooRpcError(f"Field {field} shows {shown!r} after typing {text!r}") from None

    def _type_number(self, widget: str, field: str, value: Any, in_line: bool = False) -> None:
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target) != 1:
            raise OdooRpcError(f"Field {field} offers no single number input to fill")
        lang = self._lang_format()
        text = wn.number_text(value, lang["decimal_point"])
        self._browser("Fill Text", target, text)
        self._commit_typed(target, in_line)
        try:
            self._browser("Wait For Function", wn.input_shows_number(value, lang["decimal_point"],
                                                                     lang["thousands_sep"]), f"css={target}")
        except Exception:
            shown = self._browser("Get Property", target, "value")
            raise OdooRpcError(f"Field {field} shows {shown!r} after typing {text!r}") from None

    def _pick_radio(self, widget: str, field: str, value: str) -> None:
        option = f"{widget} {wc.radio_option(value)}"
        if self._browser("Get Element Count", option) != 1:
            raise OdooRpcError(f"Field {field} offers no option {value!r}")
        self._browser("Click", option)
        if not self._browser("Get Checkbox State", option):
            raise OdooRpcError(f"Field {field} did not take the option {value!r}")

    def _lang_format(self) -> dict:
        """The date format, decimal point and thousands separator of the web session's language."""
        lang = self.get_odoo_web_session_info()["lang"]
        found = self._call_web_session("res.lang", "search_read", [], {
            "domain": [["code", "=", lang]], "fields": ["date_format", "decimal_point", "thousands_sep"],
            "limit": 1})
        if not found:
            raise OdooRpcError(f"The language {lang!r} of the web session has no format")
        return found[0]

    def _date_format(self) -> str:
        return self._lang_format()["date_format"]

    def _names_of(self, model: str, field: str, record_id: int) -> tuple:
        """What to type to find the record, and the name the client proposes it under.

        A hierarchical name (``Supplier / Office Supplies``) is not found again
        by every version when typed whole (Odoo 19): the record's own ``name``
        is typed when its model has one."""
        definition = self._call_web_session(model, "fields_get", [[field]],
                                            {"attributes": ["type", "relation"]}).get(field) or {}
        relation = definition.get("relation")
        if not relation:
            raise OdooRpcError(f"{model}.{field} is not a relational field: pick its value by name")
        names = ["display_name"]
        if "name" in self._call_web_session(relation, "fields_get", [["name"]], {"attributes": ["type"]}):
            names.append("name")
        context = {"lang": self.get_odoo_web_session_info()["lang"]}
        found = self._call_web_session(relation, "search_read", [], {
            "domain": [["id", "=", int(record_id)]], "fields": names, "limit": 1, "context": context})
        if not found:
            raise OdooRpcError(f"No {relation} record has the id {record_id}")
        return found[0].get("name") or found[0]["display_name"], found[0]["display_name"]

    def _pick_proposal(self, widget: str, field: str, kind: str, typed: str, name: str) -> None:
        self._browser("Fill Text", f"{widget} input.o-autocomplete--input", typed)
        try:
            self._browser("Wait For Function", wc.proposal_shown(_PROPOSALS, typed, name), f"css={widget}")
        except Exception:
            proposals = self._browser("Evaluate JavaScript", widget, _PROPOSALS) or []
            raise OdooRpcError(f"Field {field} proposes no record named {name!r}: "
                               f"{[proposal[0] for proposal in proposals]}") from None
        matches = wc.matching_proposals(self._browser("Evaluate JavaScript", widget, _PROPOSALS), typed, name)
        if len(matches) != 1:
            raise OdooRpcError(f"Field {field} proposes {len(matches)} records named {name!r}: "
                               "name a record whose name is unique")
        self._browser("Click", f"css={widget} {wc.AUTOCOMPLETE_ITEMS} >> nth={matches[0]}")
        if kind == "tags":
            self._browser("Wait For Function", _includes(_TAGS, name), f"css={widget}")
            return
        # Odoo 19 empties the input for a moment while it updates the record.
        target = f"{widget} input.o-autocomplete--input"
        try:
            self._browser("Wait For Function", f"(input) => input.value === {json.dumps(name)}", f"css={target}")
        except Exception:
            shown = self._browser("Get Property", target, "value")
            raise OdooRpcError(f"Field {field} shows {shown!r} after picking {name!r}") from None

    @keyword("Open New Odoo Web Form")
    def open_new_odoo_web_form(self) -> None:
        """Open the form of a new record from the list or kanban shown, by its New button.

        Waits until the form replaces the view. Nothing is written before
        `Save Odoo Web Record`; `Discard Odoo Web Changes` drops the record.

        Example:
        | `Navigate To Menu`    contacts.menu_contacts
        | `Open New Odoo Web Form`
        | ${view}=    `Get Odoo Web View`
        | Should Be Equal    ${view}[view_type]    form
        """
        if not self._browser("Get Element Count", wc.NEW_RECORD_BUTTON):
            raise OdooRpcError("The view shown offers no New button: open a list or a kanban first")
        self._web_filled = set()
        self._mark_current_view()
        self._browser("Click", f"css={wc.NEW_RECORD_BUTTON} >> nth=0")
        self._wait_for_new_view()
        view_type = wc.view_type_from_classes(self._browser("Get Attribute", f"css={wc.ACTION}", "class"))
        if view_type != "form":
            raise OdooRpcError(f"The New button opened a {view_type} view, not a form")

    @keyword("Fill Odoo Web Field")
    def fill_odoo_web_field(self, field: str, value: Any) -> None:
        """Enter ``value`` in the field of technical name ``field`` of the form shown.

        - text, email, phone, url and other input fields: ``value`` is typed,
          then the field is left so that Odoo takes it;
        - radio buttons: ``value`` is the option's technical code (``company``);
        - many2one and many2many tags: ``value`` is the exact name of the
          record to pick, as the client proposes it, or its database id (an
          integer, ``${20}``): the record's names are then read in the user's
          language, its own name is typed and its full name picked, which also
          finds a hierarchical name; a tag is added to those already there;
        - dates: ``value`` is the ISO date (``2026-12-31``), typed in the format
          of the user's language (read in ``res.lang``), never a written format;
        - selections: ``value`` is the option's technical code (``one``), never
          its label, which is translated and changes between versions: the
          label is read through the web session in the user's language, then
          chosen in the field's list (a native one on Odoo 16, a menu on 19);
        - checkboxes: ``value`` is ``${TRUE}`` or ``${FALSE}``; the box is
          clicked only when its state differs;
        - numbers (integer, float, monetary): ``value`` is a number (``2``,
          ``2.5``, ``${2.5}``), typed with the decimal point of the user's
          language (read in ``res.lang``), never a written format; read back
          as a number, whatever format Odoo shows it in afterwards.

        Fails at once when the field is absent from the view (another tab, see
        `Select Odoo Web Form Tab`), read-only, or does not show the value
        afterwards. Writes nothing to the database before `Save Odoo Web Record`.

        Example:
        | `Navigate To Menu`    contacts.menu_contacts
        | `Open New Odoo Web Form`
        | `Fill Odoo Web Field`    name    ${marker} Contact
        | `Fill Odoo Web Field`    company_type    company
        | `Fill Odoo Web Field`    country_id    ${country_id}
        | `Discard Odoo Web Changes`
        | `Navigate To Menu`    sale.sale_menu_root
        | `Open New Odoo Web Form`
        | `Select Odoo Web Form Tab`    other_information
        | `Fill Odoo Web Field`    picking_policy    one
        | `Fill Odoo Web Field`    require_payment    ${FALSE}
        """
        self._web_filled.add(field)
        self._fill_widget(self._single_widget(field), None, field, value)

    def _fill_widget(self, widget: str, model: Optional[str], field: str, value: Any,
                     in_line: bool = False) -> None:
        """Fill one field widget; ``model`` owns ``field`` (the view's model when ``None``), ``in_line`` when
        the widget is in a line of a one2many."""
        classes = self._optional_attribute(f"css={widget}", "class") or ""
        if wc.READONLY_CLASS in classes.split():
            raise OdooRpcError(f"Field {field} is read-only on this form")
        kind = wc.widget_kind(classes)
        if kind == "radio":
            self._pick_radio(widget, field, str(value))
        elif kind == "selection":
            self._pick_selection(widget, model or self.get_odoo_web_view()["model"], field, value)
        elif kind == "boolean":
            self._set_checkbox(widget, field, value)
        elif kind in ("many2one", "tags"):
            if isinstance(value, int):
                typed, name = self._names_of(model or self.get_odoo_web_view()["model"], field, value)
            else:
                typed, name = (str(value),) * 2
            self._pick_proposal(widget, field, kind, typed, name)
        elif kind == "date":
            self._type_date(widget, field, str(value), in_line)
        elif kind == "number":
            self._type_number(widget, field, value, in_line)
        else:
            self._type_text(widget, field, str(value), in_line)

    def _read_widget(self, widget: str, field: str, model: Optional[str] = None) -> Any:
        """Read one field widget; ``model`` owns ``field`` (the view's model when ``None``)."""
        classes = self._optional_attribute(f"css={widget}", "class") or ""
        kind = wc.widget_kind(classes)
        if kind == "selection":
            return self._read_selection(widget, field,
                                        self._selection_options(model or self.get_odoo_web_view()["model"], field))
        if kind == "boolean":
            return self._read_checkbox(widget)
        if kind == "tags":
            return self._browser("Evaluate JavaScript", widget, _TAGS)
        if kind == "radio":
            checked = self._browser("Evaluate JavaScript", widget, _CHECKED_RADIO)
            return wc.radio_value_of(checked) if checked else None
        if kind == "date":
            return wc.parse_date(self._shown_date(widget), self._date_format())
        if kind == "number":
            lang = self._lang_format()
            number = wn.read_shown_number(self._shown_text(widget), lang["decimal_point"], lang["thousands_sep"])
            return int(number) if number is not None and wc.INTEGER_CLASS in classes.split() else number
        return self._shown_text(widget)

    def _shown_text(self, widget: str) -> str:
        """The text a widget shows: its input's value, or its own text when it has no input (read-only)."""
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target):
            return self._browser("Get Property", f"css={target} >> nth=0", "value")
        return self._browser("Get Text", widget).strip()

    def _shown_date(self, widget: str) -> str:
        """The date a widget shows in the user's format: its input (Odoo 16), or its button's value (Odoo 19)."""
        return self._browser("Evaluate JavaScript", widget, wc.SHOWN_DATE) or ""

    def _type_date(self, widget: str, field: str, iso_date: str, in_line: bool = False) -> None:
        date_format = self._date_format()
        text = wc.format_date(iso_date, date_format)
        target = f"{widget} {wc.TEXT_INPUT}"
        button = f"{widget} {wc.DATE_BUTTON}"
        if not self._browser("Get Element Count", target) and self._browser("Get Element Count", button) == 1:
            self._browser("Click", button)
            self._browser("Wait For Elements State", target, "visible")
        if self._browser("Get Element Count", target) != 1:
            raise OdooRpcError(f"Field {field} offers no single date input to fill")
        self._browser("Fill Text", target, text)
        self._commit_typed(target, in_line)
        try:
            self._browser("Wait For Function", wc.widget_shows_date(text), f"css={widget}")
        except Exception:
            shown = self._shown_date(widget)
            raise OdooRpcError(f"Field {field} shows {shown!r} after typing {text!r}") from None

    @keyword("Get Odoo Web Field Value")
    def get_odoo_web_field_value(self, field: str) -> Any:
        """The value the form shows in the field of technical name ``field``.

        The text of an input field or of a read-only field, the name of a
        many2one record, the technical code of the checked radio option or of
        the chosen selection option (``None`` when none is), the state of a
        checkbox (``True`` or ``False``), the list of names of many2many tags,
        the ISO date of a date field (``""`` when empty), the number of a
        float, integer or monetary field, read in the user's format without
        its currency symbol (an integer for an integer field, ``None`` when
        empty).

        Example:
        | `Navigate To Menu`    contacts.menu_contacts
        | `Open New Odoo Web Form`
        | `Fill Odoo Web Field`    city    Brest
        | ${city}=    `Get Odoo Web Field Value`    city
        | Should Be Equal    ${city}    Brest
        | `Discard Odoo Web Changes`
        | `Navigate To Menu`    sale.sale_menu_root
        | `Open New Odoo Web Form`
        | `Select Odoo Web Form Tab`    other_information
        | ${policy}=    `Get Odoo Web Field Value`    picking_policy
        | Should Be Equal    ${policy}    direct
        """
        return self._read_widget(self._single_widget(field), field)

    @keyword("Select Odoo Web Form Tab")
    def select_odoo_web_form_tab(self, page: str) -> None:
        """Show the notebook page named ``page`` (its technical name, ``sales_purchases``) of the form.

        The fields of a page exist on the screen only while it is shown.

        Example:
        | `Select Odoo Web Form Tab`    sales_purchases
        | `Fill Odoo Web Field`    ref    ${marker}
        """
        tab = wc.form_tab(page)
        if self._browser("Get Element Count", tab) != 1:
            raise OdooRpcError(f"The form shows no tab named {page!r}")
        self._browser("Click", tab)
        self._browser("Wait For Elements State", f"{tab}.active", "visible")

    @keyword("Odoo Web Form Is Unsaved")
    def odoo_web_form_is_unsaved(self) -> bool:
        """``True`` when a form is shown with a new record or pending changes, ``False`` otherwise.

        A field the library filled since the last save or discard counts as a
        pending change, even before Odoo marks it (Odoo 16 marks it once the
        field's onchange answered). Odoo saves such a form when the page
        leaves it, so a teardown asks this question and discards before
        logging out.

        Example:
        | ${unsaved}=    `Odoo Web Form Is Unsaved`
        | IF    ${unsaved}    `Discard Odoo Web Changes`
        """
        return self._form_is_unsaved()

    @keyword("Get Odoo Web Invalid Fields")
    def get_odoo_web_invalid_fields(self) -> list:
        """The technical names of the fields the form marks invalid (a required field left empty...).

        Example:
        | ${invalid}=    `Get Odoo Web Invalid Fields`
        | Should Be Equal    ${invalid}    ${{["name"]}}
        """
        return self._browser("Evaluate JavaScript", f"css={wc.ACTION}", _INVALID_NAMES)

    @keyword("Save Odoo Web Record")
    def save_odoo_web_record(self) -> int:
        """Save the form shown and return the id of its record.

        Needs a web session opened with ``allow_write`` (`Log In To Odoo Web
        Client`). Waits until the form shows the record saved. Fails, naming
        the cause, when Odoo refuses: invalid fields (see `Get Odoo Web Invalid
        Fields`) or an error dialog, whose text is reported and which stays
        open. A saved record without pending change is not saved again;
        after a typing, Odoo's mark of the change is waited for first, and a
        typing that changed nothing costs that wait.

        Journaled like the RPC writes (`Get Odoo Write Journal`): operation
        ``save``, method ``web``, the fields entered since the form opened;
        ``planned`` before the click, then ``done`` with the record id,
        ``failed`` on a refusal, or ``unknown`` when no outcome showed (read
        the record, never save again blindly).

        Example:
        | ${contact_id}=    `Save Odoo Web Record`
        | `Odoo Web Form Should Be Saved`
        """
        record_id = self._require_form()
        if record_id is not None and not self._typing_marked():
            self._web_filled = set()
            return record_id
        entry = self._journal_web_write("Save Odoo Web Record", "save", "web", self.get_odoo_web_view()["model"],
                                        record_id)
        try:
            self._browser("Click", wc.SAVE_BUTTON)
            self._browser("Wait For Elements State", f"css={wc.SAVE_OUTCOME} >> nth=0", "visible")
        except Exception as exc:
            self._settle(entry, "unknown", f"{type(exc).__name__}: {compact(exc)}")
            raise
        invalid = self.get_odoo_web_invalid_fields()
        if invalid:
            refusal = f"Odoo refused to save the record: invalid fields {', '.join(invalid)}"
            self._settle(entry, "failed", refusal)
            raise OdooRpcError(refusal)
        if self._browser("Get Element Count", wc.ERROR_DIALOG):
            text = self._browser("Get Text", f"css={wc.ERROR_DIALOG} >> nth=0")
            refusal = f"Odoo refused to save the record: {compact(text)}"
            self._settle(entry, "failed", refusal)
            raise OdooRpcError(refusal)
        try:
            self._browser("Wait For Function", wc.RECORD_IN_ADDRESS)
        except Exception as exc:
            self._settle(entry, "unknown", f"saved form without a record id in its address: {compact(exc)}")
            raise
        saved_id = wc.parse_web_location(self._browser("Get Url"))["record_id"]
        entry["ids"] = [saved_id]
        self._settle(entry, "done")
        self._web_filled = set()
        return saved_id

    @keyword("Discard Odoo Web Changes")
    def discard_odoo_web_changes(self) -> None:
        """Drop the pending changes of the form shown, without writing anything.

        A new record is dropped and the client goes back to the previous view
        (Odoo 16 and 19); a saved record shows its saved values again. A saved
        record without pending change is left as it is; after a typing, Odoo's
        mark of the change is waited for first.

        Example:
        | `Fill Odoo Web Field`    city    Quimper
        | `Discard Odoo Web Changes`
        | ${city}=    `Get Odoo Web Field Value`    city
        | Should Be Equal    ${city}    Brest
        """
        if self._require_form() is None:
            self._web_filled = set()
            self._mark_current_view()
            self._browser("Click", wc.DISCARD_BUTTON)
            self._wait_for_new_view()
            return
        marked = self._typing_marked()
        self._web_filled = set()
        if not marked:
            return
        self._browser("Click", wc.DISCARD_BUTTON)
        self._browser("Wait For Elements State", f"css={wc.FORM_STATE}.o_form_saved", "visible")
