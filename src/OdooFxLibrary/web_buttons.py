"""Keywords that press the buttons of an Odoo form (``action_confirm``...), built on the Browser library.

A button that calls a method of the record is pressed by its technical name,
never by its label: Odoo saves the form first when it holds changes, then
calls the method. It is a write, so it needs a web session opened with
``allow_write`` and is journaled like the RPC writes; the keyword waits for
the server's answer to the button, then for the form shown saved again (or a
dialog the method opened).

A button that opens an action carries in the page the number of its action,
which differs from one database to the next: it is named by the external id
of its action, read through the web session. Opening a window action writes
nothing; its dialog's model is kept for the dialog keywords.

A button whose view declares ``confirm`` makes Odoo ask a question in a
dialog of its own before any call (the cancel button of an order on Odoo 19):
it is pressed only when the caller accepts that question.
"""

import json
from typing import Any, Optional
from xml.etree import ElementTree

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact


def _error_body(response: Any) -> dict:
    """The ``error`` of an Odoo answer to a button, ``{}`` when the call succeeded."""
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {}
    return ((body or {}).get("error") if isinstance(body, dict) else None) or {}


def _error_of(response: Any) -> str:
    """The message of an Odoo error answer to a button, ``""`` when the call succeeded."""
    error = _error_body(response)
    if not error:
        return ""
    data = error.get("data") or {}
    return compact(data.get("message") or error.get("message") or "error")


def error_class_of(response: Any) -> str:
    """The class of the exception an Odoo error answer names (``odoo.exceptions.UserError``), in any language."""
    return str((_error_body(response).get("data") or {}).get("name") or "")


def _form_buttons(node: ElementTree.Element):
    """The buttons of the form itself, never those of a list a field embeds."""
    for child in node:
        if child.tag == "button":
            yield child
        elif child.tag != "field":
            yield from _form_buttons(child)


def button_confirmation(arch: str, name: str) -> Optional[str]:
    """The question a form view's arch has Odoo ask before calling method ``name``, ``None`` when it asks none."""
    questions = {node.get("confirm") or None for node in _form_buttons(ElementTree.fromstring(arch))
                 if node.get("name") == name and node.get("type") == "object"}
    if len(questions) > 1:
        # Only their visibility tells such buttons apart, and the page does not show which one was drawn.
        raise OdooRpcError(f"The form view has several buttons named {name} that do not ask the same question "
                           "first: the one shown cannot be told, nothing was pressed")
    return questions.pop() if questions else None


class OdooWebButtonKeywords:
    """Form buttons in the web channel of `OdooFxLibrary`, mixed into it."""

    def _single_button(self, selector: str, name: str, kind: str) -> str:
        button = f"css={selector} >> visible=true"
        shown = self._browser("Get Element Count", button)
        if shown != 1:
            raise OdooRpcError(f"The form shows {shown} buttons named {name}, expected one")
        found = self._optional_attribute(button, "type")
        if found != kind:
            raise OdooRpcError(f"Button {name} is of type {found!r}: only a button of type {kind!r} is pressed here")
        return button

    def _window_action(self, xmlid: str) -> dict:
        module, _, name = wc.require_xmlid(xmlid).partition(".")
        found = self._call_web_session("ir.model.data", "search_read", [], {
            "domain": [["module", "=", module], ["name", "=", name]], "fields": ["model", "res_id"], "limit": 1})
        if not found:
            raise OdooRpcError(f"No action has the external id {xmlid}")
        if found[0]["model"] != "ir.actions.act_window":
            raise OdooRpcError(f"{xmlid} is a {found[0]['model']}: only a window action is opened here")
        action = self._call_web_session("ir.actions.act_window", "search_read", [], {
            "domain": [["id", "=", found[0]["res_id"]]], "fields": ["res_model", "target"], "limit": 1})
        return {"id": found[0]["res_id"], **action[0]}

    def _open_action_button(self, xmlid: str) -> dict:
        record_id = self._require_form()
        if self._form_is_unsaved():
            raise OdooRpcError(f"The form holds unsaved changes that Odoo would save before opening {xmlid}: "
                               "call Save Odoo Web Record or Discard Odoo Web Changes first")
        action = self._window_action(xmlid)
        button = self._single_button(wc.form_button(str(action["id"])), xmlid, "action")
        in_dialog = action["target"] == "new"
        if not in_dialog:
            self._mark_current_view()
        self._browser("Click", button)
        if in_dialog:
            self._browser("Wait For Elements State", f"css={wc.DIALOG_FORM}", "visible")
            self._dialog_model, self._dialog_filled = action["res_model"], set()
        else:
            self._wait_for_new_view()
        return {"record_id": record_id, "dialog": in_dialog, "dialog_model": action["res_model"] if in_dialog else None,
                "question": None}

    @keyword("Click Odoo Web Form Button")
    def click_odoo_web_form_button(self, name: str, confirm: bool = False) -> dict:
        """Press the button ``name`` of the form shown: a method's technical name, or an action's external id.

        A button that calls a method of the record (``type="object"``,
        ``action_confirm``) needs a web session opened with ``allow_write``;
        journaled as a ``call`` of method ``name``: ``done`` once the server
        answered, Odoo enabled its buttons again (the record reloaded) and the
        form shows it saved, ``failed`` when Odoo refused (its message is
        reported, the dialog stays; the entry keeps the message and the class
        of Odoo's exception, ``error_class``, the same in every language),
        ``unknown`` when no answer came (read the record, never press again
        blindly).

        When the form view has Odoo ask a question before the call (its
        ``confirm`` attribute, read in the view's arch: the cancel button of
        an order on Odoo 19), the button is pressed only with ``confirm`` set
        to ``${TRUE}``, which accepts the question; without it, nothing is
        pressed. A button that asks nothing ignores ``confirm``. When the view
        holds several buttons of that name that do not ask the same question,
        the one shown cannot be told and nothing is pressed.

        A button that opens an action (``type="action"``) is named by the
        external id of its action (``sale.action_view_sale_advance_payment_inv``),
        never by the number the page shows, which differs from one database to
        the next; only a window action, opened without writing anything (the
        form must hold no unsaved change, which Odoo would save first): in a
        dialog, whose model the dialog keywords then use (`Fill Odoo Web Dialog
        Field`), or instead of the view shown.

        Returns ``record_id``, ``dialog`` (``True`` when a dialog opened, a
        wizard), ``dialog_model`` (the model of that wizard, ``None`` without
        one) and ``question`` (the question Odoo asked and ``confirm``
        accepted, ``None`` when the button asks none).

        Example:
        | ${pressed}=    `Click Odoo Web Form Button`    action_confirm
        | Should Not Be True    ${pressed}[dialog]
        | ${step}=    `Get Odoo Web Statusbar Value`
        | Should Be Equal    ${step}    sale
        | ${pressed}=    `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | Should Be Equal    ${pressed}[dialog_model]    sale.advance.payment.inv
        | `Close Odoo Web Dialog`
        | ${pressed}=    `Click Odoo Web Form Button`    action_cancel    confirm=${TRUE}
        | Should Be Equal    ${pressed}[question]    ${NONE}
        | Should Be Equal    ${pressed}[dialog_model]    sale.order.cancel
        | `Click Odoo Web Dialog Button`    action_cancel
        """
        if "." in str(name):
            return self._open_action_button(name)
        record_id = self._require_form()
        button = self._single_button(wc.form_button(name), name, "object")
        question = button_confirmation(self._form_view_arch(), name)
        if question and not confirm:
            raise OdooRpcError(f"Button {name} has Odoo ask {question!r} first: nothing was pressed, accept the "
                               "question with confirm=${TRUE}")
        entry = self._journal_web_write("Click Odoo Web Form Button", "call", name,
                                        self.get_odoo_web_view()["model"], record_id)
        try:
            if question:
                # Odoo calls nothing before its question is accepted: the answer is awaited from then on.
                self._browser("Click", button)
                self._browser("Wait For Elements State", f"css={wc.DIALOG_MESSAGE_OK}", "visible")
                promise = self._browser("Promise To", "Wait For Response", wc.CALL_BUTTON_RESPONSE)
                self._browser("Click", f"css={wc.DIALOG_MESSAGE_OK}")
            else:
                promise = self._browser("Promise To", "Wait For Response", wc.CALL_BUTTON_RESPONSE)
                self._browser("Click", button)
            response = self._browser("Wait For", promise)
        except Exception as exc:
            self._settle(entry, "unknown", f"{type(exc).__name__}: {compact(exc)}")
            raise
        refusal = _error_of(response)
        if refusal:
            self._settle(entry, "failed", refusal, error_class_of(response))
            raise OdooRpcError(f"Odoo refused {name}: {refusal}")
        try:
            self._browser("Wait For Function", wc.BUTTONS_SETTLED)
            self._browser("Wait For Elements State",
                          f"css={wc.FORM_STATE}.o_form_saved, {wc.ERROR_DIALOG} >> nth=0", "visible")
        except Exception as exc:
            self._settle(entry, "unknown", f"answered, but no saved form nor dialog showed: {compact(exc)}")
            raise
        saved_id = wc.parse_web_location(self._browser("Get Url"))["record_id"]
        entry["ids"] = [saved_id] if saved_id is not None else entry["ids"]
        self._settle(entry, "done")
        self._web_filled = set()
        dialog = bool(self._browser("Get Element Count", wc.ERROR_DIALOG))
        action = wc.action_of(response)
        dialog_model = None
        if dialog and action and action.get("target") == "new":
            dialog_model = action.get("res_model")
            self._dialog_model, self._dialog_filled = dialog_model, set()
        return {"record_id": saved_id, "dialog": dialog, "dialog_model": dialog_model, "question": question}
