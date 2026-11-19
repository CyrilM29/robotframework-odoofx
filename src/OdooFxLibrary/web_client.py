"""Pure logic of the web channel: anchors of the Odoo web client, readings of
its address and of its classes, JSON-RPC bodies of the web session.

No browser here, only functions of strings, so everything is unit tested
without Odoo. The anchors were observed on Odoo 16 and 19 Community (plans
``specs/exploration_web_odoo16.md`` and ``specs/exploration_web_odoo19.md``).
Their divergences are absorbed by selectors common to both, or by reading the
address in the form the client shows (the ``/web#`` fragment of Odoo 16, the
``/odoo/`` path of Odoo 19), never by a version number.
"""

import json
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit

from .rpc import OdooRpcError, series_of

LOGIN_PATH = "/web/login"
LOGIN_FORM = f'form[action="{LOGIN_PATH}"]'
LOGIN_FIELD = f'{LOGIN_FORM} input[name="login"]'
PASSWORD_FIELD = f'{LOGIN_FORM} input[name="password"]'
# Odoo 19 adds two website search forms and a show-password button: the submit
# button is always looked up inside the login form.
LOGIN_SUBMIT = f'{LOGIN_FORM} button[type="submit"]'
LOGIN_ERROR = f"{LOGIN_FORM} .alert-danger"
CLIENT_READY = "body.o_web_client nav.o_main_navbar"
CLIENT_OR_LOGIN_ERROR = f"{CLIENT_READY}, {LOGIN_ERROR}"

APPS_MENU_TOGGLE = "nav.o_main_navbar .o_navbar_apps_menu button"
USER_MENU_TOGGLE = "nav.o_main_navbar .o_user_menu button.dropdown-toggle"
# Odoo 19 renders dropdown entries in a popover outside their menu: no ancestor.
LOGOUT_ENTRY = '.dropdown-item[data-menu="logout"]'

ACTION = ".o_action_manager > .o_action"
# Odoo 19 mounts a window action's controller before its renderer: the rows of
# a list, the cards of a kanban or the sheet of a form come with the renderer.
VIEW_CONTROLLER_CLASS = "o_view_controller"
RENDERER = ":is(.o_renderer, .o_form_renderer)"
LIST_ROWS = f"{ACTION} tbody tr.o_data_row"
# Odoo 19 kanban ghosts carry the record class too.
KANBAN_CARDS = f"{ACTION} .o_kanban_record:not(.o_kanban_ghost)"
PAGER_LIMIT = f"{ACTION} .o_pager_limit"
# The view switcher of an action with several views marks the one shown.
VIEW_SWITCH_ACTIVE = f"{ACTION} .o_switch_view.active"
FACETS = f"{ACTION} .o_searchview .o_searchview_facet"
FILTER_FACETS = f"{FACETS}:has(.fa-filter)"
# The current crumb is a .breadcrumb-item on Odoo 16 and outside the list on 19:
# counting the previous ones plus one holds on both.
PREVIOUS_CRUMBS = f"{ACTION} .o_control_panel .breadcrumb-item:not(.active)"
CURRENT_CRUMB = f"{ACTION} .o_control_panel :is(.breadcrumb-item.active, .o_last_breadcrumb_item.active)"
FORM_SAVED = f"{ACTION} .o_form_saved"
FORM_DIRTY = f"{ACTION} .o_form_dirty"
# Odoo 19 adds folded duplicates without data-value.
STATUSBAR_CURRENT = f'{ACTION} .o_statusbar_status button[data-value][aria-checked="true"]'

# Form entry, observed on Odoo 16 and 19 (plans specs/saisie_contact_web_odoo16.md and _odoo19.md).
NEW_RECORD_BUTTON = f"{ACTION} .o_control_panel :is(button.o_list_button_add, button.o-kanban-button-new)"
# The element that carries the form's state: o_form_saved, o_form_dirty, or neither for a new record.
FORM_STATE = f"{ACTION} :is(.o_form_editable, .o_form_readonly)"
FORM_VIEW = f"{ACTION}.o_form_view"
SAVE_BUTTON = f"{ACTION} .o_form_button_save"
DISCARD_BUTTON = f"{ACTION} .o_form_button_cancel"
INVALID_FIELDS = f"{ACTION} .o_field_invalid[name]"
ERROR_DIALOG = ".modal .modal-body"
SAVE_OUTCOME = f"{FORM_STATE}.o_form_saved, {INVALID_FIELDS}, {ERROR_DIALOG}"
# Odoo 16 date widgets carry a hidden input beside the one typed in.
TEXT_INPUT = ":is(input:not([type=hidden]):not([type=file]), textarea)"
AUTOCOMPLETE_MENU = ".o-autocomplete--dropdown-menu"
# Create, Create and edit, Search more: options that would write or open a dialog, never picked.
AUTOCOMPLETE_ITEMS = "li.o-autocomplete--dropdown-item:not(.o_m2o_dropdown_option)"
READONLY_CLASS = "o_readonly_modifier"
NEW_RECORD_SEGMENT = "new"
# Lines of a one2many field (plan specs/devis_web_odoo16.md): the first add link adds a product line.
LINE_ADD = ".o_field_x2many_list_row_add a"
EDITED_LINE = "tr.o_selected_row"
SHOWN_LINES = "tr.o_data_row"
# Sections and notes (plans specs/devis_web_odoo16.md and _odoo19.md, DV-6): a row carries o_is_<display_type>
# (o_is_false for a plain line); a deletable row its trash button, which Odoo 19 gives no section.
LINE_DELETE = "td.o_list_record_remove button[name=delete]"
# Odoo 19 gives a section and a subsection the menu of its row instead (plan specs/suppression_section_web_odoo19.md):
# it opens outside the list, and its delete entry is told by its trash icon, never by its translated label.
SECTION_MENU = "td.o_list_section_options button.dropdown-toggle"
OPEN_MENU = ".o-overlay-container .o-dropdown--menu"
SECTION_DELETE = f"{OPEN_MENU} .o-dropdown-item:has(i.fa-trash)"
# Odoo 19 has no name widget on a section or a note: its text is typed in the product cell, whose
# widget (account's ProductLabelSectionAndNoteField) edits the line's name.
LINE_LABEL = ".o_field_product_label_section_and_note_cell"
LINE_LABEL_FIELD = "name"
# The answer of an object button; Playwright reads a bare path as a whole-URL glob.
CALL_BUTTON_RESPONSE = "**/web/dataset/call_button**"
# Odoo 16 and 19 mark with disabled="1" the buttons they disable for the time of a button's action, the reload
# of the record included, then remove the mark: none left means the action is over.
BUTTONS_SETTLED = ("() => !document.querySelector('.o_action_manager button[disabled=\"1\"], "
                   ".o-overlay-container button[disabled=\"1\"]')")
# A dialog a button opened (plans specs/devis_web_odoo16.md and _odoo19.md, DV-8): the same on Odoo 16 and 19, its
# form inside, the buttons of the wizard's footer in its modal footer, its close cross in its header.
DIALOG = ".o_dialog .modal"
DIALOG_FORM = f"{DIALOG} .o_form_view"
DIALOG_CLOSE = f"{DIALOG}:has(.o_form_view) .modal-header .btn-close"
DIALOG_FIELD_WAIT = "3s"
# The message Odoo shows over a wizard it refused (an error): a dialog without a form, with its own close cross
# (DV-10, measured on Odoo 16 and 19).
DIALOG_MESSAGE = f"{DIALOG}:not(:has(.o_form_view))"
DIALOG_MESSAGE_CLOSE = f"{DIALOG_MESSAGE} .modal-header .btn-close"
DIALOG_MESSAGE_OK = f"{DIALOG_MESSAGE} .modal-footer button.btn-primary"
ACTION_LOAD_RESPONSE = "**/web/action/load**"
ISO_DATE = "%Y-%m-%d"
# Odoo 19 shows a date as a button whose value attribute holds it in the user's format; a click opens the input.
DATE_BUTTON = "button.o_input"
# The date a widget shows, read in ONE call in the page: Odoo 19 replaces the input by its button after Tab, so
# counting the input then reading it races (measured on 2026-10-26).
SHOWN_DATE = ("(widget) => { const input = widget.querySelector(" + json.dumps(TEXT_INPUT) + "); "
              "if (input) return input.value; const button = widget.querySelector(" + json.dumps(DATE_BUTTON) + "); "
              "return button ? (button.getAttribute('value') || '') : ''; }")
NATIVE_SELECT = "select"
# Odoo 19 draws a selection as a menu of its own: an input opens it, its options float in a popover.
SELECT_MENU_TOGGLER = "input.o_select_menu_toggler"
SELECT_MENU = ".o_select_menu_menu"
SELECT_MENU_ITEMS = f"{SELECT_MENU} .o_select_menu_item"
CHECKBOX = 'input[type="checkbox"]'
NUMBER_CLASSES = ("o_field_float", "o_field_integer", "o_field_monetary")
INTEGER_CLASS = "o_field_integer"
RECORD_IN_ADDRESS = ("() => /[#&]id=[0-9]+/.test(location.hash)"
                     " || /^[/]odoo[/].+[/][0-9]+$/.test(location.pathname)")

SESSION_INFO_ROUTE = "/web/session/get_session_info"
CALL_KW_ROUTE = "/web/dataset/call_kw/{model}/{method}"
SESSION_EXPIRED = "odoo.http.SessionExpiredException"
READ_METHODS = frozenset({"fields_get", "get_views", "search_count", "search_read"})

VIEW_TYPES = ("list", "kanban", "form", "calendar", "pivot", "graph", "activity",
              "map", "gantt", "cohort", "hierarchy")
_VIEW_CLASS = re.compile(r"^o_(%s)_view$" % "|".join(VIEW_TYPES))
_XMLID = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_.]+$")
_FIELD = re.compile(r"^[a-z_][a-z0-9_]*$")
_SERVER_SERIE = re.compile(r"^((?:saas~)?\d+\.\d+)")


def require_xmlid(value: str) -> str:
    """``value`` if it is an external id (``module.name``), else a clear error."""
    if not _XMLID.match(str(value)):
        raise OdooRpcError(f"Expected a menu external id such as sale.sale_menu_root, got {value!r}")
    return str(value)


def require_field_name(value: str) -> str:
    """``value`` if it is a technical field name (``name``, ``partner_id``), else a clear error."""
    if not _FIELD.match(str(value)):
        raise OdooRpcError(f"Expected a technical field name such as name, got {value!r}")
    return str(value)


def server_serie_of(server_version: str) -> str:
    """The serie Odoo names a server by (``16.0``, ``saas~17.2``), read on its version string."""
    match = _SERVER_SERIE.match(str(server_version))
    if match is None:
        raise OdooRpcError(f"Unrecognised Odoo server version: {server_version!r}")
    return match.group(1)


def app_entry(xmlid: str) -> str:
    return f'a.o_app[data-menu-xmlid="{require_xmlid(xmlid)}"]'


def section_entry(xmlid: str) -> str:
    """A menu of the current application, in its bar or in an opened dropdown."""
    return (f'css=[data-menu-xmlid="{require_xmlid(xmlid)}"]'
            f':not(.o_menu_brand):not(.o_app) >> visible=true')


def field_widget(field: str) -> str:
    """The widget of ``field`` (technical name) in the view shown."""
    return f'{ACTION} .o_field_widget[name="{require_field_name(field)}"]'


def form_tab(page: str) -> str:
    """The tab of the notebook page named ``page`` (its ``name`` in the form view)."""
    return f'{ACTION} .o_notebook a.nav-link[name="{require_field_name(page)}"]'


def widget_kind(classes: str) -> str:
    """How a field widget is filled, read on its classes: ``tags``, ``many2one``, ``radio``, ``date``,
    ``selection``, ``boolean``, ``number`` or ``text``."""
    tokens = str(classes).split()
    if "o_field_many2many_tags" in tokens:
        return "tags"
    # Specialised many2one widgets keep the word: o_field_res_partner_many2one,
    # o_field_sol_product_many2one, o_field_many2one_avatar_user.
    if any(token.startswith("o_field_") and "many2one" in token for token in tokens):
        return "many2one"
    if "o_field_radio" in tokens:
        return "radio"
    if "o_field_date" in tokens:
        return "date"
    if "o_field_selection" in tokens:
        return "selection"
    if "o_field_boolean" in tokens:
        return "boolean"
    if any(token in NUMBER_CLASSES for token in tokens):
        return "number"
    return "text"


def form_button(name: str) -> str:
    """A button of the form's header or button box, by its technical name (``action_confirm``)."""
    if not re.match(r"^[A-Za-z0-9_.]+$", str(name)):
        raise OdooRpcError(f"Expected the technical name of a button such as action_confirm, got {name!r}")
    return f'{ACTION} :is(.o_form_statusbar, .o_statusbar_buttons, .oe_button_box) button[name="{name}"]'


def dialog_field_widget(field: str) -> str:
    """The widget of ``field`` (technical name) in the form of the dialog shown."""
    return f'{DIALOG_FORM} .o_field_widget[name="{require_field_name(field)}"]'


def dialog_button(name: str, button_id: Optional[str] = None) -> str:
    """A button of the dialog's footer by its technical name, and by its id when several share the name."""
    if not re.match(r"^[A-Za-z0-9_.]+$", str(name)):
        raise OdooRpcError(f"Expected the technical name of a button such as create_invoices, got {name!r}")
    selector = f'{DIALOG} .modal-footer button[name="{name}"]'
    if button_id:
        if not re.match(r"^[A-Za-z0-9_-]+$", str(button_id)):
            raise OdooRpcError(f"Expected the id of a button such as create_invoice_open, got {button_id!r}")
        selector += f'[id="{button_id}"]'
    return selector


def dialog_answer(model: str) -> str:
    """Matcher of the answer that settles a button of a wizard of ``model``: the call of its method, or the save of
    the wizard when it carries Odoo's refusal (Odoo 16 checks the wizard's constraints there, before any call)."""
    if not re.match(r"^[a-z0-9_.]+$", str(model)):
        raise OdooRpcError(f"Expected the technical name of a model such as sale.advance.payment.inv, got {model!r}")
    saves = json.dumps([f"/web/dataset/call_kw/{model}/{method}" for method in ("create", "web_save")])
    # A JavaScript predicate (Browser runs it in Playwright): no dollar sign nor backslash, which Robot would expand.
    return ("async (response) => { const url = response.url(); "
            "if (url.includes('/web/dataset/call_button')) return true; "
            f"if (!{saves}.some((path) => url.endsWith(path))) return false; "
            "try { return Boolean((await response.json()).error); } catch (error) { return false; } }")


def action_of(response: Any) -> Optional[dict]:
    """The action a button's answer returns (``res_model``, ``target``...), ``None`` when it returns none."""
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    result = body.get("result") if isinstance(body, dict) else None
    return result if isinstance(result, dict) and result.get("type") else None


def format_date(iso_date: str, date_format: str) -> str:
    """An ISO date (``2026-12-31``) written the way the user's language shows it (``%d/%m/%Y``)."""
    try:
        return datetime.strptime(str(iso_date), ISO_DATE).strftime(date_format)
    except ValueError:
        raise OdooRpcError(f"Expected an ISO date such as 2026-12-31, got {iso_date!r}") from None


def parse_date(shown: str, date_format: str) -> str:
    """The ISO date of a date shown in the user's format, ``""`` for an empty field."""
    if not str(shown).strip():
        return ""
    return datetime.strptime(str(shown).strip(), date_format).strftime(ISO_DATE)


def matching_proposals(proposals: list, own_name: str, display_name: str) -> list:
    """Positions of the autocomplete proposals that show the record: its display name whole (Odoo 16), or its own
    name with the rest of its display name set apart (Odoo 19 shows a product's internal reference in a muted span).

    ``proposals`` lists ``[whole text, label, set-apart text]`` per proposal."""
    return [position for position, (whole, label, aside) in enumerate(proposals)
            if whole == display_name or (label == own_name and aside and aside in display_name)]


def proposal_shown(script: str, own_name: str, display_name: str) -> str:
    """A predicate for Browser's ``Wait For Function``: a proposal ``script`` lists shows the record, as
    `matching_proposals` reads it."""
    own, display = json.dumps(own_name, ensure_ascii=False), json.dumps(display_name, ensure_ascii=False)
    return (f"(widget) => ({script})(widget).some(([whole, label, aside]) => whole === {display} || "
            f"(label === {own} && aside !== '' && {display}.includes(aside)))")


def widget_shows_date(text: str) -> str:
    """A predicate for Browser's ``Wait For Function``: the date widget shows ``text``, in its input or its button."""
    return f"(widget) => ({SHOWN_DATE})(widget) === {json.dumps(text, ensure_ascii=False)}"


def input_shows_text(text: str) -> str:
    """A predicate for Browser's ``Wait For Function``: the input shows exactly ``text``."""
    return f"(input) => input.value === {json.dumps(text, ensure_ascii=False)}"


def radio_option(value: str) -> str:
    """The radio input of the option ``value``, whose id ends with ``_<value>`` on Odoo 16 and 19."""
    if not _FIELD.match(str(value)):
        raise OdooRpcError(f"Expected the technical code of an option such as company, got {value!r}")
    return f'input.o_radio_input[id$="_{value}"]'


def radio_value_of(input_id: str) -> str:
    """The option code a radio input's id carries (``radio_field_1_company`` gives ``company``)."""
    match = re.match(r"^radio_field_\d+_(.+)$", str(input_id))
    if match is None:
        raise OdooRpcError(f"Unrecognised radio input id: {input_id!r}")
    return match.group(1)


def selection_label(field: str, options: list, code: Any) -> str:
    """The label of the option ``code`` among the ``[code, label]`` pairs ``fields_get`` gives for ``field``."""
    labels = [label for value, label in options if str(value) == str(code)]
    if not labels:
        raise OdooRpcError(f"Field {field} offers no option {code!r}: its codes are "
                           f"{[value for value, _ in options]}")
    return labels[0]


def selection_code(field: str, options: list, label: str) -> Any:
    """The code of the option shown as ``label``, ``None`` for an empty selection."""
    shown = str(label).strip()
    if not shown:
        return None
    codes = [value for value, text in options if text == shown]
    if len(codes) != 1:
        raise OdooRpcError(f"Field {field} shows {shown!r}, which {len(codes)} of its options carry")
    return codes[0]


def native_option_code(value: str) -> Any:
    """The code a native ``select`` holds: Odoo 16 writes it as JSON (``"one"``), ``false`` for none."""
    try:
        code = json.loads(value)
    except ValueError:
        raise OdooRpcError(f"Unrecognised value of a selection: {value!r}") from None
    return None if code is False else code


def input_settles_on(text: str, milliseconds: int = 500) -> str:
    """A predicate for Browser's ``Wait For Function``: the input has shown ``text`` for ``milliseconds``.

    Odoo 19 draws a selection again with its former value while the record
    takes the new one, after the input already showed it (measured)."""
    return ("(input) => { const now = performance.now(); "
            f"if (input.value !== {json.dumps(text)}) {{ input.odoofxSince = 0; return false; }} "
            f"input.odoofxSince = input.odoofxSince || now; return now - input.odoofxSince >= {int(milliseconds)}; }}")


def checkbox_wanted(value: Any) -> bool:
    """The state asked for a checkbox: a boolean, or its text ``True`` or ``False``."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text not in ("true", "false"):
        raise OdooRpcError(f"Expected ${{TRUE}} or ${{FALSE}} for a checkbox, got {value!r}")
    return text == "true"


def login_url(url: str, database: str) -> str:
    return f"{url}{LOGIN_PATH}?db={database}"


def normalize_view_type(view_type: Optional[str]) -> Optional[str]:
    """``tree`` is the name Odoo 16 actions give the ``list`` view."""
    if not view_type:
        return None
    return "list" if view_type == "tree" else view_type


def view_type_from_classes(classes: str) -> str:
    """The view type a controller's class attribute names (``o_list_view``...)."""
    for token in str(classes).split():
        match = _VIEW_CLASS.match(token)
        if match:
            return match.group(1)
    raise OdooRpcError(f"No view type in the classes of the current action: {classes!r}")


def view_type_from_switch(classes: str) -> Optional[str]:
    """The view type an active view-switcher button names (``o_switch_view o_list active``), if any."""
    names = {f"o_{view_type}": view_type for view_type in VIEW_TYPES}
    return next((names[token] for token in str(classes).split() if token in names), None)


def list_cell(position: int, field: Optional[str] = None) -> str:
    """The cell of a shown list row: the one of ``field``, or the first data cell."""
    cell = f'td.o_data_cell[name="{require_field_name(field)}"]' if field else "td.o_data_cell"
    return f"css={LIST_ROWS} >> nth={position - 1} >> css={cell} >> nth=0"


def parse_web_location(url: str) -> dict:
    """Read the action, model, view type and record id the address carries.

    Odoo 16 keeps them in the ``/web#`` fragment (``action=``, ``model=``,
    ``view_type=``, ``id=``). Odoo 19 shows a path, ``/odoo/<action>[/<id>]`` (``/new`` for a new record),
    where ``<action>`` is the action's ``path``, ``action-<id or xmlid>`` or a
    model name; the model then comes from the action (see `action_lookup`).
    """
    parts = urlsplit(url)
    if parts.path.startswith("/odoo"):
        action, record_id = None, None
        for segment in [s for s in parts.path.split("/")[2:] if s]:
            if segment.isdigit() and action is not None:
                record_id = int(segment)
            elif segment == NEW_RECORD_SEGMENT and action is not None:
                record_id = None
            else:
                action, record_id = segment, None
        return {"scheme": "path", "action": action,
                "model": action if action and "." in action and not action.startswith("action-") else None,
                "view_type": None, "record_id": record_id}
    if parts.path.rstrip("/") == "/web":
        params = dict(parse_qsl(parts.fragment))
        record = params.get("id", "")
        return {"scheme": "fragment", "action": params.get("action"), "model": params.get("model"),
                "view_type": normalize_view_type(params.get("view_type")),
                "record_id": int(record) if record.isdigit() else None}
    raise OdooRpcError(f"Not an address of the Odoo web client: {url}")


def action_lookup(action: str) -> tuple:
    """Where to search the action an address names: ``(model, domain)``.

    A bare id is the ``action=`` of an Odoo 16 fragment; an ``/odoo/`` path
    segment is the action's ``path`` (which starts with a letter), ``action-<id>``
    or ``action-<xmlid>``, for which ``ir.model.data`` answers with the action's
    id, to read on ``ir.actions.act_window`` next."""
    if str(action).isdigit():
        return "ir.actions.act_window", [["id", "=", int(action)]]
    if action.startswith("action-"):
        reference = action[len("action-"):]
        if reference.isdigit():
            return "ir.actions.act_window", [["id", "=", int(reference)]]
        module, _, name = require_xmlid(reference).partition(".")
        return "ir.model.data", [["module", "=", module], ["name", "=", name]]
    return "ir.actions.act_window", [["path", "=", action]]


def parse_count(text: str) -> int:
    """An integer shown by the client, whatever the locale's thousands separator."""
    digits = re.sub(r"\D", "", str(text))
    if not digits:
        raise OdooRpcError(f"No number in {text!r}")
    return int(digits)


def jsonrpc_body(params: dict, request_id: int = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": "call", "params": params, "id": request_id})


def jsonrpc_result(response: Any, route: str) -> Any:
    """The ``result`` of a JSON-RPC answer received by Browser's ``Http``.

    An Odoo error becomes one line naming the route and the server exception;
    an expired session says so, so that a caller can tell it apart."""
    status = response.get("status")
    body = response.get("body")
    if not isinstance(body, dict):
        raise OdooRpcError(f"{route} answered HTTP {status} without a JSON body")
    if "error" in body:
        error = body["error"] or {}
        name = (error.get("data") or {}).get("name") or ""
        message = (error.get("data") or {}).get("message") or error.get("message") or "error"
        if name == SESSION_EXPIRED:
            raise OdooWebSessionExpired(f"{route}: the web session is closed or expired")
        raise OdooRpcError(f"{route} failed: {name or 'Odoo error'}: {message}")
    if "result" not in body:
        raise OdooRpcError(f"{route} answered HTTP {status} without a result")
    return body["result"]


def summarize_session(info: dict, url: str) -> dict:
    """The proven target of a web session, as `Connect To Odoo` returns it for RPC."""
    version_info = info.get("server_version_info") or []
    server_version = str(info.get("server_version") or "")
    series = int(version_info[0]) if version_info else series_of(server_version)
    return {
        "url": url,
        "database": info.get("db"),
        "server_version": server_version,
        "series": series,
        "uid": info.get("uid"),
        "login": info.get("username"),
        "lang": (info.get("user_context") or {}).get("lang"),
        "base_url": info.get("web.base.url"),
    }


class OdooWebSessionExpired(OdooRpcError):
    """The web session asked for is closed (never opened, logged out or expired)."""
