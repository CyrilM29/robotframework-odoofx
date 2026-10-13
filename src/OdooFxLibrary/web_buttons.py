"""Keywords that press the buttons of an Odoo form (``action_confirm``...), built on the Browser library.

A button that calls a method of the record is pressed by its technical name,
never by its label: Odoo saves the form first when it holds changes, then
calls the method. It is a write, so it needs a web session opened with
``allow_write`` and is journaled like the RPC writes; the keyword waits for
the server's answer to the button, then for the form shown saved again (or a
dialog the method opened).
"""

import json
from typing import Any

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact


def _error_of(response: Any) -> str:
    """The message of an Odoo error answer to a button, ``""`` when the call succeeded."""
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return ""
    error = (body or {}).get("error") if isinstance(body, dict) else None
    if not error:
        return ""
    data = error.get("data") or {}
    return compact(data.get("message") or error.get("message") or "error")


class OdooWebButtonKeywords:
    """Form buttons in the web channel of `OdooFxLibrary`, mixed into it."""

    @keyword("Click Odoo Web Form Button")
    def click_odoo_web_form_button(self, name: str) -> dict:
        """Press the button of technical name ``name`` (``action_confirm``) of the form shown.

        Only a button that calls a method of the record (``type="object"``).
        Needs a web session opened with ``allow_write``; journaled as a
        ``call`` of method ``name``: ``done`` once the server answered, Odoo
        enabled its buttons again (the record reloaded) and the form shows it
        saved, ``failed`` when Odoo refused (its
        message is reported, the dialog stays), ``unknown`` when no answer came
        (read the record, never press again blindly). Returns ``record_id``
        and ``dialog`` (``True`` when the method opened a dialog, a wizard).

        Example:
        | ${pressed}=    `Click Odoo Web Form Button`    action_confirm
        | Should Not Be True    ${pressed}[dialog]
        | ${step}=    `Get Odoo Web Statusbar Value`
        | Should Be Equal    ${step}    sale
        """
        record_id = self._require_form()
        button = f"css={wc.form_button(name)} >> visible=true"
        shown = self._browser("Get Element Count", button)
        if shown != 1:
            raise OdooRpcError(f"The form shows {shown} buttons named {name}, expected one")
        kind = self._optional_attribute(button, "type")
        if kind != "object":
            raise OdooRpcError(f"Button {name} is of type {kind!r}: only a button that calls a method of the "
                               "record is pressed here")
        entry = self._journal_web_write("Click Odoo Web Form Button", "call", name,
                                        self.get_odoo_web_view()["model"], record_id)
        try:
            promise = self._browser("Promise To", "Wait For Response", wc.CALL_BUTTON_RESPONSE)
            self._browser("Click", button)
            response = self._browser("Wait For", promise)
        except Exception as exc:
            self._settle(entry, "unknown", f"{type(exc).__name__}: {compact(exc)}")
            raise
        refusal = _error_of(response)
        if refusal:
            self._settle(entry, "failed", refusal)
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
        return {"record_id": saved_id, "dialog": bool(self._browser("Get Element Count", wc.ERROR_DIALOG))}
