"""Keywords that switch the view of the action shown in the web client (its list, its kanban...).

The switcher of an action with several views shows one button per view, of class ``o_switch_view o_<type>``, the
one shown marked ``active`` (Odoo 16 and 19). A new view is a new controller: the switch is waited for as the view
that replaces the previous one, like a menu opened.
"""

import re

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError

_VIEW_TYPE = re.compile(r"^[a-z][a-z_]*$")


def switch_button(view_type: str) -> str:
    """The button of the view switcher that shows the ``view_type`` view (``list``, ``kanban``)."""
    if not _VIEW_TYPE.match(view_type or ""):
        raise OdooRpcError(f"Not a view type: {view_type!r} (list, kanban...)")
    return f"{wc.ACTION} .o_control_panel button.o_switch_view.o_{view_type}"


class OdooWebViewKeywords:
    """The view switcher in the web channel of `OdooFxLibrary`, mixed into it."""

    @keyword("Switch Odoo Web View")
    def switch_odoo_web_view(self, view_type: str) -> dict:
        """Show the ``view_type`` view (``list``, ``kanban``) of the action shown, by its view switcher.

        Waits for the view that replaces the previous one, then checks that
        it is of that type, and returns it as `Get Odoo Web View` does. A
        view already shown is left as it is. Writes nothing. Refused: an
        action whose switcher offers no such view, a form shown (a form has
        no switcher), a form with unsaved changes.

        Example:
        | ${view}=    `Switch Odoo Web View`    list
        | Should Be Equal    ${view}[view_type]    list
        | ${view}=    `Switch Odoo Web View`    kanban
        | Should Be Equal    ${view}[view_type]    kanban
        """
        button = switch_button(view_type)
        if self._browser("Get Element Count", button) != 1:
            shown = self.get_odoo_web_view()["view_type"]
            raise OdooRpcError(f"The {shown} view shown offers no switch to a {view_type} view")
        if "active" in (self._optional_attribute(button, "class") or "").split():
            return self.get_odoo_web_view()
        self._refuse_leaving_unsaved_form("Switch Odoo Web View")
        self._mark_current_view()
        self._browser("Click", button)
        self._wait_for_new_view()
        shown = self.get_odoo_web_view()
        if shown["view_type"] != view_type:
            raise OdooRpcError(f"Odoo shows a {shown['view_type']} view instead of the {view_type} view")
        return shown
