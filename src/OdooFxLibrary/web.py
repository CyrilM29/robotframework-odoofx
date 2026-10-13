"""Keywords of the web channel, built on the Browser library.

Browser (Playwright) drives the page: opening the browser, the context and
the page stays its job, in the suite or its resources. This module adds what
is proper to Odoo: the anchors of its web client, the proof of the target
through the web session, the reading of the current view, and reads through
the session cookie, which never send the secret again.
"""

from typing import Optional, Union
from urllib.parse import urlsplit

from robot.api import logger
from robot.api.deco import keyword
from robot.api.types import Secret
from robot.libraries.BuiltIn import BuiltIn
from robot.utils import escape

from . import web_client as wc
from .rpc import OdooRpcError, detect_version, series_of

# Set on the controller shown before a gesture: the view that replaces it has
# no such attribute, the old one keeps it (the client mounts a new element per
# action, even when the address does not change).
_STALE = "data-odoofx-stale"
_MARK_STALE = f"(element) => element.setAttribute('{_STALE}', '1')"
_NEW_VIEW = f"css={wc.ACTION}:not([{_STALE}])"


class OdooWebKeywords:
    """The web channel of `OdooFxLibrary`, mixed into it."""

    def _browser(self, name: str, *args):
        # run_keyword reads its arguments as Robot data: unescaped, a typed value
        # or a script would lose its backslashes, resolve ${...} and bind name=.
        return BuiltIn().run_keyword(f"Browser.{name}",
                                     *(escape(arg) if isinstance(arg, str) else arg for arg in args))

    def _origin(self) -> str:
        parts = urlsplit(self._browser("Get Url"))
        return f"{parts.scheme}://{parts.netloc}"

    def _optional_attribute(self, selector: str, name: str) -> Optional[str]:
        if name not in self._browser("Get Attribute Names", selector):
            return None
        return self._browser("Get Attribute", selector, name)

    def _mark_current_view(self) -> None:
        if self._browser("Get Element Count", wc.ACTION):
            self._browser("Evaluate JavaScript", wc.ACTION, _MARK_STALE)

    def _wait_for_new_view(self) -> None:
        self._browser("Wait For Elements State", _NEW_VIEW, "visible")
        classes = self._optional_attribute(_NEW_VIEW, "class") or ""
        if wc.VIEW_CONTROLLER_CLASS in classes.split():
            self._browser("Wait For Elements State", f"{_NEW_VIEW} >> css={wc.RENDERER} >> nth=0", "visible")

    def _form_is_unsaved(self) -> bool:
        if self._browser("Get Element Count", wc.FORM_STATE) != 1:
            # A form view whose state cannot be read is held unsaved: leaving it may write.
            return bool(self._browser("Get Element Count", wc.FORM_VIEW))
        if self._browser("Get Element Count", wc.FORM_DIRTY):
            return True
        return wc.parse_web_location(self._browser("Get Url"))["record_id"] is None

    def _refuse_leaving_unsaved_form(self, gesture: str) -> None:
        # Odoo saves a form it leaves: a failed test would write what it left half-typed.
        if self._form_is_unsaved():
            raise OdooRpcError(f"{gesture} refused: the form shown holds unsaved changes that Odoo would save "
                               "on leaving it; call Save Odoo Web Record or Discard Odoo Web Changes first")

    def _call_web_session(self, model: str, method: str, args: list, kwargs: dict):
        if method not in wc.READ_METHODS:
            raise OdooRpcError(f"{method} is not a read method of the web session channel")
        route = wc.CALL_KW_ROUTE.format(model=model, method=method)
        body = wc.jsonrpc_body({"model": model, "method": method, "args": args, "kwargs": kwargs})
        return wc.jsonrpc_result(self._browser("Http", route, "POST", body), route)

    @keyword("Get Odoo Server Version")
    def get_odoo_server_version(self, url: str) -> dict:
        """Read the version of the server at ``url`` without authentication.

        The proof a suite opens with, before any browser or secret: returns
        ``url``, ``server_version``, its ``server_serie`` (``16.0``, compared
        exactly, so that a ``saas~16.x`` is told apart) and its major ``series``.

        Example:
        | ${version}=    `Get Odoo Server Version`    http://127.0.0.1:8016
        | Should Be Equal    ${version}[server_serie]    16.0
        """
        base = url.rstrip("/")
        server_version = detect_version(base)
        return {"url": base, "server_version": server_version,
                "server_serie": wc.server_serie_of(server_version), "series": series_of(server_version)}

    @keyword("Log In To Odoo Web Client")
    def log_in_to_odoo_web_client(self, url: str, database: str, login: str,
                                  password: Union[Secret, str],
                                  expected_series: Optional[int] = None,
                                  allow_write: bool = False) -> dict:
        """Log in through the login page of ``database`` and prove the target.

        Needs a page opened by Browser (``New Page``). ``expected_series`` (16,
        19...) makes the keyword fail before the login page is even opened when
        the server runs another major version; once logged in, the web session
        must name ``database`` and the same series. The secret is filled with
        Browser's ``Fill Secret`` and never logged. Returns the session's
        target (url, database, server_version, series, uid, login, lang,
        base_url, allow_write), never the secret.

        ``allow_write`` opts in to the gestures that write through the screen
        (`Save Odoo Web Record`), journaled like the RPC writes; it is off by
        default, as for `Connect To Odoo`. Pair it with ``expected_series``.

        Example:
        | ${session}=    `Log In To Odoo Web Client`    http://127.0.0.1:8016    odoo16    admin    ${PASSWORD}
        | ...    expected_series=16    allow_write=${TRUE}
        | Should Be Equal    ${session}[database]    odoo16
        | Should Be True    ${session}[allow_write]
        """
        self._web_writes = False
        secret = password if isinstance(password, Secret) else Secret(str(password))
        if not secret.value:
            raise OdooRpcError("Empty password")
        if not database:
            raise OdooRpcError("The database must be named explicitly")
        base = url.rstrip("/")
        server_version = detect_version(base)
        if expected_series is not None and series_of(server_version) != expected_series:
            raise OdooRpcError(
                f"Wrong target: {base} runs Odoo {server_version}, expected series {expected_series}")
        self._browser("Go To", wc.login_url(base, database))
        self._browser("Wait For Elements State", wc.LOGIN_FIELD, "visible")
        self._browser("Fill Text", wc.LOGIN_FIELD, login)
        self._browser("Fill Secret", wc.PASSWORD_FIELD, secret)
        self._browser("Click", wc.LOGIN_SUBMIT)
        self._browser("Wait For Elements State", wc.CLIENT_OR_LOGIN_ERROR, "visible")
        if self._browser("Get Element Count", wc.LOGIN_ERROR):
            raise OdooRpcError(f"Odoo refused the login {login!r} on database {database}")
        info = self.get_odoo_web_session_info()
        if info["database"] != database:
            raise OdooRpcError(f"Wrong target: the web session is on database {info['database']}, "
                               f"expected {database}")
        if expected_series is not None and info["series"] != expected_series:
            raise OdooRpcError(f"Wrong target: the web session runs series {info['series']}, "
                               f"expected {expected_series}")
        self._web_writes = bool(allow_write)
        logger.info(f"Logged in to {base} database {database} as {login}: Odoo "
                    f"{info['server_version']}, uid {info['uid']}, writes "
                    f"{'allowed' if allow_write else 'off'}")
        return {**info, "allow_write": self._web_writes}

    @keyword("Get Odoo Web Session Info")
    def get_odoo_web_session_info(self) -> dict:
        """Return the target of the open web session (no secret), read from the server.

        Fails when the session is closed or expired; `Odoo Web Session Is Open`
        answers the same question without failing.

        Example:
        | ${session}=    `Get Odoo Web Session Info`
        | Should Be Equal    ${session}[base_url]    http://127.0.0.1:8016
        """
        response = self._browser("Http", wc.SESSION_INFO_ROUTE, "POST", wc.jsonrpc_body({}))
        return wc.summarize_session(wc.jsonrpc_result(response, wc.SESSION_INFO_ROUTE), self._origin())

    @keyword("Odoo Web Session Is Open")
    def odoo_web_session_is_open(self) -> bool:
        """``True`` when the server still knows the page's web session, ``False`` otherwise.

        A page that shows no server address yet (``about:blank``) has no session.

        Example:
        | ${open}=    `Odoo Web Session Is Open`
        | Should Be True    ${open}
        """
        if urlsplit(self._browser("Get Url")).scheme not in ("http", "https"):
            return False
        try:
            self.get_odoo_web_session_info()
        except wc.OdooWebSessionExpired:
            return False
        return True

    @keyword("Odoo Web Client Is Shown")
    def odoo_web_client_is_shown(self) -> bool:
        """``True`` when the page shows the logged-in web client (its main menu bar).

        Example:
        | ${shown}=    `Odoo Web Client Is Shown`
        | Should Be True    ${shown}
        """
        return bool(self._browser("Get Element Count", wc.CLIENT_READY))

    @keyword("Navigate To Menu")
    def navigate_to_menu(self, *menu_xmlids: str) -> None:
        """Open a menu through the main menu, by external ids, never by label.

        The first id is the application's root menu (``sale.sale_menu_root``),
        chosen in the applications menu; the next ones are menus of that
        application, a dropdown group before its entry
        (``sale.sale_order_menu    sale.menu_sale_quotations``). Waits until
        the view of the reached menu replaces the one shown before, even when
        the address stays the same.

        Example:
        | `Navigate To Menu`    sale.sale_menu_root
        | `Navigate To Menu`    sale.sale_menu_root    sale.sale_order_menu    sale.menu_sale_quotations
        """
        if not menu_xmlids:
            raise OdooRpcError("Navigate To Menu needs at least the application's root menu")
        root, *sections = [wc.require_xmlid(xmlid) for xmlid in menu_xmlids]
        self._refuse_leaving_unsaved_form("Navigate To Menu")
        self._mark_current_view()
        self._browser("Click", wc.APPS_MENU_TOGGLE)
        self._browser("Click", wc.app_entry(root))
        self._wait_for_new_view()
        for xmlid in sections:
            selector = wc.section_entry(xmlid)
            classes = self._optional_attribute(selector, "class") or ""
            if "dropdown-toggle" in classes.split():
                self._browser("Click", selector)
                continue
            self._mark_current_view()
            self._browser("Click", selector)
            self._wait_for_new_view()

    @keyword("Get Odoo Web Current App")
    def get_odoo_web_current_app(self) -> str:
        """The external id of the application whose menu bar is shown.

        Read on the brand of the menu bar, which carries it on Odoo 16 and 19.

        Example:
        | ${app}=    `Get Odoo Web Current App`
        | Should Be Equal    ${app}    sale.sale_menu_root
        """
        brand = "nav.o_main_navbar .o_menu_brand"
        xmlid = self._optional_attribute(brand, "data-menu-xmlid")
        if not xmlid:
            raise OdooRpcError("The menu bar names no application")
        return xmlid

    @keyword("Get Odoo Web View")
    def get_odoo_web_view(self) -> dict:
        """The view shown: ``model``, ``view_type`` (``list``, ``kanban``, ``form``...),
        ``action`` and ``record_id`` (``None`` outside a record).

        The type is read on the view's classes; the address (Odoo 16) and the
        active button of the view switcher (actions with several views) must
        agree with it when they name one. The model is read on the address (Odoo 16)
        or, when the address does not carry it (Odoo 19), on the action it
        names, through the web session.

        Example:
        | ${view}=    `Get Odoo Web View`
        | Should Be Equal    ${view}[model]    sale.order
        | Should Be Equal    ${view}[view_type]    list
        """
        location = wc.parse_web_location(self._browser("Get Url"))
        view_type = wc.view_type_from_classes(self._browser("Get Attribute", f"css={wc.ACTION}", "class"))
        if location["view_type"] and location["view_type"] != view_type:
            raise OdooRpcError(f"The address names a {location['view_type']} view, "
                               f"the page shows a {view_type} view")
        if self._browser("Get Element Count", wc.VIEW_SWITCH_ACTIVE) == 1:
            switched = wc.view_type_from_switch(self._browser("Get Attribute", wc.VIEW_SWITCH_ACTIVE, "class"))
            if switched and switched != view_type:
                raise OdooRpcError(f"The view switcher marks a {switched} view, the page shows a {view_type} view")
        model = location["model"] or self._model_of_action(location["action"])
        return {"model": model, "view_type": view_type, "action": location["action"],
                "record_id": location["record_id"]}

    def _model_of_action(self, action: Optional[str]) -> str:
        if not action:
            raise OdooRpcError("The address names no action")
        model, domain = wc.action_lookup(action)
        found = self._call_web_session(model, "search_read", [], {
            "domain": domain, "fields": ["res_model"] if model != "ir.model.data" else ["res_id"],
            "limit": 1})
        if found and model == "ir.model.data":
            found = self._call_web_session("ir.actions.act_window", "search_read", [], {
                "domain": [["id", "=", found[0]["res_id"]]], "fields": ["res_model"], "limit": 1})
        if not found:
            raise OdooRpcError(f"No window action matches the address segment {action!r}")
        return found[0]["res_model"]

    @keyword("Count Odoo Web View Records")
    def count_odoo_web_view_records(self) -> int:
        """The records the list (rows) or kanban (cards, without the empty ghosts) shows.

        Example:
        | ${shown}=    `Count Odoo Web View Records`
        | Should Be True    ${shown} >= 1
        """
        view_type = wc.view_type_from_classes(self._browser("Get Attribute", f"css={wc.ACTION}", "class"))
        if view_type == "list":
            return self._browser("Get Element Count", wc.LIST_ROWS)
        if view_type == "kanban":
            return self._browser("Get Element Count", wc.KANBAN_CARDS)
        raise OdooRpcError(f"A {view_type} view shows no records to count")

    @keyword("Get Odoo Web Pager Total")
    def get_odoo_web_pager_total(self) -> Optional[int]:
        """The total the pager of the view announces, ``None`` when the view has no pager.

        Example:
        | ${total}=    `Get Odoo Web Pager Total`
        | Should Not Be Equal    ${total}    ${NONE}
        """
        if not self._browser("Get Element Count", wc.PAGER_LIMIT):
            return None
        return wc.parse_count(self._browser("Get Text", wc.PAGER_LIMIT))

    @keyword("Count Odoo Web Search Facets")
    def count_odoo_web_search_facets(self, kind: str = "all") -> int:
        """The facets of the search bar: ``all``, or ``filter`` for filters only.

        Example:
        | ${filters}=    `Count Odoo Web Search Facets`    filter
        | Should Be Equal As Integers    ${filters}    1
        """
        selectors = {"all": wc.FACETS, "filter": wc.FILTER_FACETS}
        if kind not in selectors:
            raise OdooRpcError(f"Unknown facet kind {kind!r}, expected one of {sorted(selectors)}")
        return self._browser("Get Element Count", selectors[kind])

    @keyword("Get Odoo Web Breadcrumb Depth")
    def get_odoo_web_breadcrumb_depth(self) -> int:
        """How many views the breadcrumb holds, the current one included.

        The previous views plus the current one, each counted on the page: a
        view without any breadcrumb answers 0.

        Example:
        | ${depth}=    `Get Odoo Web Breadcrumb Depth`
        | Should Be Equal As Integers    ${depth}    1
        """
        return (self._browser("Get Element Count", wc.PREVIOUS_CRUMBS)
                + self._browser("Get Element Count", wc.CURRENT_CRUMB))

    @keyword("Open Odoo Web Record")
    def open_odoo_web_record(self, position: int = 1, field: Optional[str] = None) -> int:
        """Open the record at ``position`` (1 for the first) of the list or kanban shown.

        A list row opens by the cell of ``field`` (its technical name, such as
        ``name``), or by its first data cell when no field is named (the
        selection cell before it only selects). Name a field whose cell is
        plain text: a cell with an editable widget (priority, toggle) would
        change the record instead of opening it. Waits for the form view;
        returns the record id the address carries.

        Example:
        | ${order_id}=    `Open Odoo Web Record`    1    field=name
        | ${view}=    `Get Odoo Web View`
        | Should Be Equal As Integers    ${view}[record_id]    ${order_id}
        """
        shown = self.count_odoo_web_view_records()
        if not 1 <= position <= shown:
            raise OdooRpcError(f"No record at position {position}: the view shows {shown}")
        view_type = self.get_odoo_web_view()["view_type"]
        if view_type == "list":
            target = wc.list_cell(position, field)
        elif field:
            raise OdooRpcError(f"A {view_type} view has no cells: field={field!r} applies to a list")
        else:
            target = f"css={wc.KANBAN_CARDS} >> nth={position - 1}"
        self._mark_current_view()
        self._browser("Click", target)
        self._wait_for_new_view()
        self._web_filled = set()
        record_id = wc.parse_web_location(self._browser("Get Url"))["record_id"]
        if record_id is None:
            raise OdooRpcError("The opened view names no record in its address")
        return record_id

    @keyword("Get Odoo Web List Cell Text")
    def get_odoo_web_list_cell_text(self, position: int, field: str) -> str:
        """The text the list shows in the cell of ``field`` (technical name) of the row at ``position``.

        Read before opening a row, it ties the record opened to the row
        clicked (its reference, its name), which the address alone cannot.

        Example:
        | ${reference}=    `Get Odoo Web List Cell Text`    1    name
        | Should Start With    ${reference}    S
        """
        view_type = wc.view_type_from_classes(self._browser("Get Attribute", f"css={wc.ACTION}", "class"))
        if view_type != "list":
            raise OdooRpcError(f"A {view_type} view has no cells: the cell text is read on a list")
        shown = self._browser("Get Element Count", wc.LIST_ROWS)
        if not 1 <= position <= shown:
            raise OdooRpcError(f"No row at position {position}: the list shows {shown}")
        return self._browser("Get Text", wc.list_cell(position, field)).strip()

    @keyword("Go Back Through Odoo Web Breadcrumb")
    def go_back_through_odoo_web_breadcrumb(self) -> None:
        """Return to the previous view by its breadcrumb and wait until it is shown again.

        Example:
        | `Go Back Through Odoo Web Breadcrumb`
        | ${depth}=    `Get Odoo Web Breadcrumb Depth`
        | Should Be Equal As Integers    ${depth}    1
        """
        if self.get_odoo_web_breadcrumb_depth() < 2:
            raise OdooRpcError("The breadcrumb holds no previous view")
        self._refuse_leaving_unsaved_form("Go Back Through Odoo Web Breadcrumb")
        self._mark_current_view()
        self._browser("Click", f"css={wc.PREVIOUS_CRUMBS} >> nth=-1 >> css=a")
        self._wait_for_new_view()

    @keyword("Get Odoo Web Statusbar Value")
    def get_odoo_web_statusbar_value(self) -> str:
        """The technical value (``draft``, ``sale``...) of the current step of the form's status bar.

        Example:
        | ${step}=    `Get Odoo Web Statusbar Value`
        | ${orders}=    `Search Read Odoo Records Through Web Session`    sale.order    ${{[["id", "=", $order_id]]}}
        | ...    fields=${{["state"]}}
        | Should Be Equal    ${step}    ${orders}[0][state]
        """
        if not self._browser("Get Element Count", wc.STATUSBAR_CURRENT):
            raise OdooRpcError("The view shows no status bar with a current step")
        return self._browser("Get Attribute", wc.STATUSBAR_CURRENT, "data-value")

    @keyword("Odoo Web Form Should Be Saved")
    def odoo_web_form_should_be_saved(self) -> None:
        """Fail unless the form shown holds no pending change.

        Example:
        | `Odoo Web Form Should Be Saved`
        """
        if self._browser("Get Element Count", wc.FORM_DIRTY):
            raise AssertionError("The form holds pending changes")
        if not self._browser("Get Element Count", wc.FORM_SAVED):
            raise AssertionError("No saved form is shown")

    @keyword("Log Out Of Odoo Web Client")
    def log_out_of_odoo_web_client(self) -> None:
        """Log out through the user menu and wait for the login page.

        Refused while a form holds unsaved changes, which Odoo would save on
        leaving it (measured on Odoo 19): save or discard them first. The
        same holds for `Navigate To Menu` and `Go Back Through Odoo Web Breadcrumb`.

        Example:
        | `Log Out Of Odoo Web Client`
        | ${open}=    `Odoo Web Session Is Open`
        | Should Not Be True    ${open}
        """
        self._refuse_leaving_unsaved_form("Log Out Of Odoo Web Client")
        self._browser("Click", wc.USER_MENU_TOGGLE)
        self._browser("Click", wc.LOGOUT_ENTRY)
        self._browser("Wait For Elements State", wc.LOGIN_FIELD, "visible")
        self._web_writes = False

    @keyword("Count Odoo Records Through Web Session")
    def count_odoo_records_through_web_session(self, model: str, domain: Optional[list] = None,
                                               context: Optional[dict] = None) -> int:
        """Count the records of ``model`` matching ``domain``, with the page's session cookie.

        The same route on Odoo 16 and 19, where the RPC channel changes
        protocol and secret. Without ``allowed_company_ids`` in ``context``
        the count spans every company of the user, not only the one the
        screen shows.

        Example:
        | ${count}=    `Count Odoo Records Through Web Session`    sale.order    context=${{{"active_test": False}}}
        | Should Be True    ${count} > 0
        """
        return self._call_web_session(model, "search_count", [domain or []], {"context": context or {}})

    @keyword("Search Read Odoo Records Through Web Session")
    def search_read_odoo_records_through_web_session(
            self, model: str, domain: Optional[list] = None, fields: Optional[list] = None,
            limit: int = 0, order: str = "", context: Optional[dict] = None) -> list:
        """Return the records of ``model`` matching ``domain``, with the page's session cookie.

        Example:
        | ${last}=    `Search Read Odoo Records Through Web Session`    sale.order    fields=${{["id"]}}    limit=1
        | ...    order=id desc    context=${{{"active_test": False}}}
        | Length Should Be    ${last}    1
        """
        return self._call_web_session(model, "search_read", [], {
            "domain": domain or [], "fields": fields or [], "limit": limit or None,
            "order": order or None, "context": context or {}})
