"""Keywords that fill and save Odoo forms through the web client, built on the Browser library.

A value is typed or picked the way a user does it, then read back on the
screen: a field the client did not take fails the keyword at once. A
relational value is picked among the client's proposals by its exact name,
never through the Create or Search more options, which would write or open a
dialog. Typed text is committed by leaving the field (Tab): Odoo marks the
form as changed only then.
"""

import json
from typing import Any, Optional

from robot.api import logger
from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact

_PROPOSALS = (f"(widget) => [...widget.querySelectorAll('{wc.AUTOCOMPLETE_ITEMS}')]"
              ".map((item) => item.textContent.trim())")
_TAGS = ("(widget) => [...widget.querySelectorAll('.o_tag')]"
         ".map((tag) => (tag.querySelector('.o_tag_badge_text') || tag).textContent.trim())")
_CHECKED_RADIO = "(widget) => (widget.querySelector('input.o_radio_input:checked') || {}).id || ''"
_INVALID_NAMES = ("(action) => [...action.querySelectorAll('.o_field_invalid[name]')]"
                  ".map((field) => field.getAttribute('name'))")


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
                           record_id: Optional[int]) -> dict:
        if not self._web_writes:
            raise OdooRpcError(f"Writes are off: {gesture} refused, log in to the web client "
                               "with allow_write=${TRUE}")
        entry = {"seq": len(self._journal) + 1, "phase": "planned", "operation": operation,
                 "database": self.get_odoo_web_session_info()["database"], "model": model, "method": method,
                 "ids": [record_id] if record_id is not None else [], "fields": sorted(self._web_filled)}
        self._journal.append(entry)
        logger.info(f"write {entry['seq']} planned: {operation} {model} {method} through the web client "
                    f"{entry['ids']}")
        return entry

    @staticmethod
    def _settle(entry: dict, phase: str, error: str = "") -> None:
        entry["phase"] = phase
        if error:
            entry["error"] = error
        logger.info(f"write {entry['seq']} {phase}{': ' + error if error else ''}")

    def _require_form(self) -> Optional[int]:
        if self._browser("Get Element Count", wc.FORM_STATE) != 1:
            raise OdooRpcError("No form is shown")
        return wc.parse_web_location(self._browser("Get Url"))["record_id"]

    def _type_text(self, widget: str, field: str, text: str) -> None:
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target) != 1:
            raise OdooRpcError(f"Field {field} offers no single text input to fill")
        self._browser("Fill Text", target, text)
        self._browser("Press Keys", target, "Tab")
        shown = self._browser("Get Property", target, "value")
        if shown != text:
            raise OdooRpcError(f"Field {field} shows {shown!r} after typing {text!r}")

    def _pick_radio(self, widget: str, field: str, value: str) -> None:
        option = f"{widget} {wc.radio_option(value)}"
        if self._browser("Get Element Count", option) != 1:
            raise OdooRpcError(f"Field {field} offers no option {value!r}")
        self._browser("Click", option)
        if not self._browser("Get Checkbox State", option):
            raise OdooRpcError(f"Field {field} did not take the option {value!r}")

    def _date_format(self) -> str:
        lang = self.get_odoo_web_session_info()["lang"]
        found = self._call_web_session("res.lang", "search_read", [], {
            "domain": [["code", "=", lang]], "fields": ["date_format"], "limit": 1})
        if not found:
            raise OdooRpcError(f"The language {lang!r} of the web session has no date format")
        return found[0]["date_format"]

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
            self._browser("Wait For Function", _includes(_PROPOSALS, name), f"css={widget}")
        except Exception:
            proposals = self._browser("Evaluate JavaScript", widget, _PROPOSALS) or []
            raise OdooRpcError(f"Field {field} proposes no record named {name!r}: {proposals}") from None
        proposals = self._browser("Evaluate JavaScript", widget, _PROPOSALS)
        if proposals.count(name) != 1:
            raise OdooRpcError(f"Field {field} proposes {proposals.count(name)} records named {name!r}: "
                               "name a record whose name is unique")
        self._browser("Click", f"css={widget} {wc.AUTOCOMPLETE_ITEMS} >> nth={proposals.index(name)}")
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
          clicked only when its state differs.

        Fails at once when the field is absent from the view (another tab, see
        `Select Odoo Web Form Tab`), read-only, or does not show the value
        afterwards. Writes nothing to the database before `Save Odoo Web Record`.

        Example:
        | `Fill Odoo Web Field`    name    ${marker} Contact
        | `Fill Odoo Web Field`    company_type    company
        | `Fill Odoo Web Field`    country_id    ${country_id}
        | `Fill Odoo Web Field`    picking_policy    one
        | `Fill Odoo Web Field`    require_payment    ${FALSE}
        """
        self._web_filled.add(field)
        self._fill_widget(self._single_widget(field), None, field, value)

    def _fill_widget(self, widget: str, model: Optional[str], field: str, value: Any) -> None:
        """Fill one field widget; ``model`` owns ``field`` (the view's model when ``None``)."""
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
            self._type_date(widget, field, str(value))
        else:
            self._type_text(widget, field, str(value))

    def _read_widget(self, widget: str, field: str) -> Any:
        kind = wc.widget_kind(self._optional_attribute(f"css={widget}", "class") or "")
        if kind == "selection":
            return self._read_selection(widget, field,
                                        self._selection_options(self.get_odoo_web_view()["model"], field))
        if kind == "boolean":
            return self._read_checkbox(widget)
        if kind == "tags":
            return self._browser("Evaluate JavaScript", widget, _TAGS)
        if kind == "radio":
            checked = self._browser("Evaluate JavaScript", widget, _CHECKED_RADIO)
            return wc.radio_value_of(checked) if checked else None
        if kind == "date":
            return wc.parse_date(self._shown_date(widget), self._date_format())
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target):
            return self._browser("Get Property", f"css={target} >> nth=0", "value")
        return self._browser("Get Text", widget).strip()

    def _shown_date(self, widget: str) -> str:
        """The date a widget shows in the user's format: its input (Odoo 16), or its button's value (Odoo 19)."""
        target = f"{widget} {wc.TEXT_INPUT}"
        if self._browser("Get Element Count", target):
            return self._browser("Get Property", f"css={target} >> nth=0", "value")
        button = f"{widget} {wc.DATE_BUTTON}"
        if self._browser("Get Element Count", button):
            return self._optional_attribute(f"css={button} >> nth=0", "value") or ""
        return ""

    def _type_date(self, widget: str, field: str, iso_date: str) -> None:
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
        self._browser("Press Keys", target, "Tab")
        shown = self._shown_date(widget)
        if wc.parse_date(shown, date_format) != iso_date:
            raise OdooRpcError(f"Field {field} shows {shown!r} after typing {text!r}")

    @keyword("Get Odoo Web Field Value")
    def get_odoo_web_field_value(self, field: str) -> Any:
        """The value the form shows in the field of technical name ``field``.

        The text of an input field or of a read-only field, the name of a
        many2one record, the technical code of the checked radio option or of
        the chosen selection option (``None`` when none is), the state of a
        checkbox (``True`` or ``False``), the list of names of many2many tags,
        the ISO date of a date field (``""`` when empty).

        Example:
        | ${city}=    `Get Odoo Web Field Value`    city
        | Should Be Equal    ${city}    Brest
        | ${policy}=    `Get Odoo Web Field Value`    picking_policy
        | Should Be Equal    ${policy}    one
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

        Odoo saves such a form when the page leaves it, so a teardown asks
        this question and discards before logging out.

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
        open. A saved record without pending change is not saved again.

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
        if record_id is not None and not self._browser("Get Element Count", wc.FORM_DIRTY):
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
        record without pending change is left as it is.

        Example:
        | `Fill Odoo Web Field`    city    Quimper
        | `Discard Odoo Web Changes`
        | ${city}=    `Get Odoo Web Field Value`    city
        | Should Be Equal    ${city}    Brest
        """
        self._web_filled = set()
        if self._require_form() is None:
            self._mark_current_view()
            self._browser("Click", wc.DISCARD_BUTTON)
            self._wait_for_new_view()
            return
        if not self._browser("Get Element Count", wc.FORM_DIRTY):
            return
        self._browser("Click", wc.DISCARD_BUTTON)
        self._browser("Wait For Elements State", f"css={wc.FORM_STATE}.o_form_saved", "visible")
