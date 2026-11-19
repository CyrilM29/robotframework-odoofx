"""Keywords for the dialog a form button opened (a wizard such as ``sale.advance.payment.inv``), built on Browser.

A dialog's form says nothing of its model: it is the one of the action that
opened it (`Click Odoo Web Form Button`), and its fields are filled and read
through that model like those of the form shown. A button of its footer is
pressed by its technical name, and by its id when several share the name (the
invoice wizard of Odoo 16 has two ``create_invoices``); it calls a method of
the wizard, a write journaled like the others, after which Odoo closes the
dialog and shows what the method returned: another dialog, another view, or
the form reloaded. Odoo may refuse the wizard when it saves it (Odoo 16
checks its constraints there, before any call) or in the method (Odoo 19):
either way it shows its message over the wizard, in a dialog without a form.
"""

from typing import Any, Optional

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact
from .web_buttons import _error_of, error_class_of


class OdooWebDialogKeywords:
    """Dialogs of the web channel of `OdooFxLibrary`, mixed into it."""

    def _require_dialog(self) -> str:
        if self._browser("Get Element Count", wc.DIALOG_FORM) != 1:
            raise OdooRpcError("No dialog with a form is shown")
        if not self._dialog_model:
            raise OdooRpcError("The model of the dialog shown is not known: open it with Click Odoo Web Form Button")
        return self._dialog_model

    def _single_dialog_widget(self, field: str) -> str:
        widget = wc.dialog_field_widget(field)
        try:
            # A field the wizard shows on a computed condition was twice missing just after the dialog opened on
            # Odoo 19, then present (ODOOFX-220): give its rendering a few seconds before counting it.
            self._browser("Wait For Elements State", f"css={widget} >> nth=0", "attached", wc.DIALOG_FIELD_WAIT)
        except Exception:
            pass  # the count below names a field that never showed
        shown = self._browser("Get Element Count", widget)
        if shown != 1:
            raise OdooRpcError(f"The dialog shows {shown} widgets of field {field}, expected one")
        return widget

    def _forget_dialog(self) -> None:
        self._dialog_model, self._dialog_filled = None, set()

    def _close_dialog_messages(self) -> None:
        """Close the messages Odoo shows over the dialog (a refusal), the newest first; none writes."""
        shown = self._browser("Get Element Count", wc.DIALOG_MESSAGE)
        for left in reversed(range(shown)):
            self._browser("Click", f"css={wc.DIALOG_MESSAGE_CLOSE} >> nth=-1")
            self._browser("Wait For Condition", "Element Count", f"css={wc.DIALOG_MESSAGE}", "==", left)

    @keyword("Odoo Web Dialog Is Open")
    def odoo_web_dialog_is_open(self) -> bool:
        """``True`` when a dialog with a form is shown (a wizard), ``False`` otherwise.

        Example:
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | ${open}=    `Odoo Web Dialog Is Open`
        | Should Be True    ${open}
        """
        return bool(self._browser("Get Element Count", wc.DIALOG_FORM))

    @keyword("Fill Odoo Web Dialog Field")
    def fill_odoo_web_dialog_field(self, field: str, value: Any) -> None:
        """Enter ``value`` in the field of technical name ``field`` of the dialog shown.

        The same values as `Fill Odoo Web Field`, read on the dialog's model
        (the one of the action that opened it). Writes nothing before a button
        of the dialog is pressed (`Click Odoo Web Dialog Button`).

        Example:
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | `Fill Odoo Web Dialog Field`    amount    10
        | `Close Odoo Web Dialog`
        """
        model = self._require_dialog()
        widget = self._single_dialog_widget(field)
        self._dialog_filled.add(field)
        self._fill_widget(widget, model, field, value)

    @keyword("Get Odoo Web Dialog Field Value")
    def get_odoo_web_dialog_field_value(self, field: str) -> Any:
        """The value the dialog shown holds in the field ``field``, as `Get Odoo Web Field Value` reads it.

        Example:
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | ${method}=    `Get Odoo Web Dialog Field Value`    advance_payment_method
        | Should Be Equal    ${method}    percentage
        | `Fill Odoo Web Dialog Field`    amount    10
        | ${amount}=    `Get Odoo Web Dialog Field Value`    amount
        | Should Be Equal As Numbers    ${amount}    10
        | `Close Odoo Web Dialog`
        """
        model = self._require_dialog()
        return self._read_widget(self._single_dialog_widget(field), field, model)

    @keyword("Close Odoo Web Dialog")
    def close_odoo_web_dialog(self) -> None:
        """Close the dialog shown by its close cross, without writing anything; waits until it is gone.

        A dialog without a form left over it (the message of a refusal) is
        closed first, by its own cross.

        Example:
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | `Close Odoo Web Dialog`
        | ${open}=    `Odoo Web Dialog Is Open`
        | Should Not Be True    ${open}
        """
        if not self.odoo_web_dialog_is_open():
            raise OdooRpcError("No dialog with a form is shown")
        self._close_dialog_messages()
        self._browser("Click", f"css={wc.DIALOG_CLOSE}")
        self._browser("Wait For Elements State", f"css={wc.DIALOG}", "detached")
        self._forget_dialog()

    @keyword("Click Odoo Web Dialog Button")
    def click_odoo_web_dialog_button(self, name: str, button_id: Optional[str] = None) -> dict:
        """Press the button of technical name ``name`` of the dialog's footer, by ``button_id`` when several share it.

        Only a button that calls a method of the wizard (``type="object"``).
        Needs a web session opened with ``allow_write``; journaled as a
        ``call`` of ``name`` on the dialog's model with the fields entered in
        the dialog: ``done`` once the server answered and Odoo showed what the
        method returned, ``failed`` when Odoo refused, at the save of the
        wizard or in its method (its message is reported, then closed: the
        wizard is left as it was, to be corrected or closed; the entry keeps
        the message and the class of Odoo's exception, ``error_class``, the
        same in every language), ``unknown`` when
        no outcome showed. Returns ``dialog`` (``True`` when the method opened
        another dialog), and otherwise the ``model`` and ``record_id`` of the
        view then shown (the invoice a wizard created, or the form reloaded).

        Example:
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | `Fill Odoo Web Dialog Field`    amount    0
        | Run Keyword And Expect Error    GLOB:*Odoo refused create_invoices:*
        | ...    `Click Odoo Web Dialog Button`    create_invoices    button_id=create_invoice_open
        | `Close Odoo Web Dialog`
        | `Click Odoo Web Form Button`    sale.action_view_sale_advance_payment_inv
        | `Fill Odoo Web Dialog Field`    amount    10
        | ${shown}=    `Click Odoo Web Dialog Button`    create_invoices    button_id=create_invoice_open
        | Should Be Equal    ${shown}[model]    account.move
        """
        model = self._require_dialog()
        button = f"css={wc.dialog_button(name, button_id)} >> visible=true"
        shown = self._browser("Get Element Count", button)
        if shown != 1:
            raise OdooRpcError(f"The dialog shows {shown} buttons named {name}"
                               f"{' with id ' + button_id if button_id else ''}, expected one: name its id too")
        kind = self._optional_attribute(button, "type")
        if kind != "object":
            raise OdooRpcError(f"Button {name} of the dialog is of type {kind!r}: only a button that calls a "
                               "method of the wizard is pressed here")
        entry = self._journal_web_write("Click Odoo Web Dialog Button", "call", name, model, None,
                                        self._dialog_filled)
        self._mark_current_view()
        try:
            promise = self._browser("Promise To", "Wait For Response", wc.dialog_answer(model))
            self._browser("Click", button)
            response = self._browser("Wait For", promise)
        except Exception as exc:
            self._settle(entry, "unknown", f"{type(exc).__name__}: {compact(exc)}")
            raise
        refusal = _error_of(response)
        if refusal:
            self._settle(entry, "failed", refusal, error_class_of(response))
            self._unmark_current_view()
            try:
                self._browser("Wait For Elements State", f"css={wc.DIALOG_MESSAGE} >> nth=0", "visible")
                self._close_dialog_messages()
            except Exception as exc:
                raise OdooRpcError(f"Odoo refused {name}: {refusal}; its message did not show or close: "
                                   f"{compact(exc)}") from exc
            raise OdooRpcError(f"Odoo refused {name}: {refusal}")
        action = wc.action_of(response)
        try:
            self._wait_for_dialog_outcome(action)
        except Exception as exc:
            self._settle(entry, "unknown", f"answered, but what it returned did not show: {compact(exc)}")
            raise
        self._settle(entry, "done")
        if action and action.get("type") == "ir.actions.act_window" and action.get("target") == "new":
            self._dialog_model, self._dialog_filled = action.get("res_model"), set()
            return {"dialog": True, "model": self._dialog_model, "record_id": None}
        self._forget_dialog()
        view = self.get_odoo_web_view()
        return {"dialog": False, "model": view["model"], "record_id": view["record_id"]}

    def _wait_for_dialog_outcome(self, action: Optional[dict]) -> None:
        """Wait for what the wizard's method returned: another dialog, another view, or the form reloaded."""
        window = bool(action and action.get("type") == "ir.actions.act_window")
        if window and action.get("target") == "new":
            self._browser("Wait For Function", wc.BUTTONS_SETTLED)
            self._browser("Wait For Elements State", f"css={wc.DIALOG_FORM}", "visible")
            self._unmark_current_view()
            return
        self._browser("Wait For Elements State", f"css={wc.DIALOG}", "detached")
        if window:
            self._wait_for_new_view()
        else:
            self._unmark_current_view()
        self._browser("Wait For Function", wc.BUTTONS_SETTLED)
