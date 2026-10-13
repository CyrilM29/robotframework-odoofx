"""Selection fields and checkboxes of an Odoo form, filled and read through the web client.

A selection is chosen by the technical code of its option, never by its label:
labels are translated and differ between versions (the second option of
``sale.order.picking_policy`` ends with « produits » on Odoo 16, « articles »
on 19). The code is turned into the label the user's language shows by
``fields_get`` through the web session. Odoo 16 draws a native ``select``;
Odoo 19 a menu of its own, opened by its input, whose options float in a
popover outside the field. A checkbox is clicked only when its state differs
from the one asked.
"""

from typing import Any

from . import web_client as wc
from .rpc import OdooRpcError

_MENU_LABELS = "(menu) => [...menu.querySelectorAll('.o_select_menu_item')].map((item) => item.textContent.trim())"


class OdooWebChoiceKeywords:
    """Selections and checkboxes of the web channel of `OdooFxLibrary`, used by `Fill Odoo Web Field`."""

    def _selection_options(self, model: str, field: str) -> list:
        context = {"lang": self.get_odoo_web_session_info()["lang"]}
        definition = self._call_web_session(model, "fields_get", [[field]], {
            "attributes": ["type", "selection"], "context": context}).get(field) or {}
        if definition.get("type") != "selection":
            raise OdooRpcError(f"{model}.{field} is not a selection field: no option to choose")
        return definition["selection"]

    def _read_selection(self, widget: str, field: str, options: list) -> Any:
        native = f"{widget} {wc.NATIVE_SELECT}"
        if self._browser("Get Element Count", native):
            return wc.native_option_code(self._browser("Get Property", native, "value"))
        toggler = f"{widget} {wc.SELECT_MENU_TOGGLER}"
        if self._browser("Get Element Count", toggler):
            return wc.selection_code(field, options, self._browser("Get Property", toggler, "value"))
        return wc.selection_code(field, options, self._browser("Get Text", widget))

    def _pick_selection(self, widget: str, model: str, field: str, code: Any) -> None:
        options = self._selection_options(model, field)
        label = wc.selection_label(field, options, code)
        native = f"{widget} {wc.NATIVE_SELECT}"
        toggler = f"{widget} {wc.SELECT_MENU_TOGGLER}"
        if self._browser("Get Element Count", native) == 1:
            self._browser("Select Options By", native, "label", label)
        elif self._browser("Get Element Count", toggler) == 1:
            self._choose_in_menu(toggler, field, label)
        else:
            raise OdooRpcError(f"Field {field} offers no list of options to choose from")
        shown = self._read_selection(widget, field, options)
        if str(shown) != str(code):
            raise OdooRpcError(f"Field {field} shows the option {shown!r} after choosing {code!r}")

    def _choose_in_menu(self, toggler: str, field: str, label: str) -> None:
        self._browser("Click", toggler)
        self._browser("Wait For Elements State", f"css={wc.SELECT_MENU_ITEMS} >> nth=0", "visible")
        labels = self._browser("Evaluate JavaScript", f"css={wc.SELECT_MENU}", _MENU_LABELS) or []
        if labels.count(label) != 1:
            raise OdooRpcError(f"Field {field} lists {labels.count(label)} options shown {label!r}: {labels}")
        self._browser("Click", f"css={wc.SELECT_MENU_ITEMS} >> nth={labels.index(label)}")
        try:
            self._browser("Wait For Function", wc.input_settles_on(label), f"css={toggler}")
        except Exception:
            shown = self._browser("Get Property", toggler, "value")
            raise OdooRpcError(f"Field {field} shows {shown!r} after choosing {label!r}") from None

    def _set_checkbox(self, widget: str, field: str, value: Any) -> None:
        wanted = wc.checkbox_wanted(value)
        box = f"{widget} {wc.CHECKBOX}"
        if self._browser("Get Element Count", box) != 1:
            raise OdooRpcError(f"Field {field} shows no single checkbox")
        if self._browser("Get Checkbox State", box) != wanted:
            self._browser("Click", box)
        if self._browser("Get Checkbox State", box) != wanted:
            raise OdooRpcError(f"Field {field} did not take the state {wanted}")

    def _read_checkbox(self, widget: str) -> bool:
        return self._browser("Get Checkbox State", f"{widget} {wc.CHECKBOX}")
