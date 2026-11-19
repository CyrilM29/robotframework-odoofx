"""Keywords that archive, unarchive and delete the record of a form through its Actions menu.

The entry is never told by its translated label. Odoo 19 gives each entry an icon (``oi-archive``,
``oi-unarchive``, ``fa-trash-o``, read in ``form_controller.js`` and measured). Odoo 16 gives them neither icon nor
key, only their label: there the entry is found at the position the code of Odoo gives it (``getActionMenuItems``:
archive or unarchive when the form holds a writable ``active`` field, then duplicate when it may create and
duplicate, then delete when it may delete, then the server actions of the view's toolbar), and the menu must show
exactly that many entries, or nothing is clicked (decision of the owner, 2026-11-16). Which way is taken follows
what the menu shows, never a version number.

Archive and Delete have Odoo ask a question in a box of its own before any call; Unarchive asks none. Every entry
but Delete saves a form holding changes before it acts, so a form that is not saved is refused before any click.
"""

import json
import re
from typing import Optional
from xml.etree import ElementTree

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact
from .web_buttons import _error_of, error_class_of

ACTIONS_MENU_TOGGLE = f"{wc.ACTION} .o_cp_action_menus button.dropdown-toggle:has(i.fa-cog)"
# Odoo 19 opens the menu in the overlay, Odoo 16 inside the control panel.
ACTIONS_MENU_ENTRIES = ":is(.o-overlay-container, .o_cp_action_menus) .o-dropdown--menu .o_menu_item"
ENTRY_ICONS = {"archive": "oi-archive", "unarchive": "oi-unarchive", "delete": "fa-trash-o"}
METHODS = {"archive": "action_archive", "unarchive": "action_unarchive", "delete": "unlink"}
# A box Odoo opens to ask a question (plans specs/recherche_archivage_web_odoo19.md and _odoo16.md): no form inside,
# a footer with a primary button that accepts and a secondary one that refuses.
CONFIRMATION = f"{wc.DIALOG_MESSAGE}:has(.modal-footer button.btn-secondary)"
CONFIRMATION_ACCEPT = f"{CONFIRMATION} .modal-footer button.btn-primary"
CONFIRMATION_REFUSE = f"{CONFIRMATION} .modal-footer button.btn-secondary"
_ASKED = "data-odoofx-asked"
_MARK_ASKED = f"(element) => element.setAttribute('{_ASKED}', '1')"
_FALSE = re.compile(r"^(false|0)", re.IGNORECASE)


def _allowed(root: ElementTree.Element, name: str) -> bool:
    # archParseBoolean of Odoo 16: an attribute starting with false or 0 forbids, an absent one allows.
    value = root.get(name)
    return not value or not _FALSE.match(value)


def form_fields(arch: str) -> set:
    """The fields of the form itself, never those of a list a field embeds."""
    names = set()

    def visit(node: ElementTree.Element) -> None:
        for child in node:
            if child.tag == "field":
                names.add(child.get("name"))
            else:
                visit(child)

    visit(ElementTree.fromstring(arch))
    return names


def callback_entries(arch: str, readonly: dict, record_active: Optional[bool]) -> list:
    """The entries Odoo puts first in the Actions menu of a saved record, in their order (Odoo 16 code).

    ``readonly`` maps ``active`` (or ``x_active``) to the readonly of its definition; ``record_active`` is the
    value of that field on the record."""
    root = ElementTree.fromstring(arch)
    fields = form_fields(arch)
    entries = []
    active = next((name for name in ("active", "x_active") if name in fields), None)
    if active and not readonly.get(active, False):
        entries.append("archive" if record_active else "unarchive")
    if _allowed(root, "create") and _allowed(root, "duplicate"):
        entries.append("duplicate")
    if _allowed(root, "delete"):
        entries.append("delete")
    return entries


def reload_matcher(model: str) -> str:
    """A response matcher for the read Odoo makes of the record after its method: ``web_read`` from Odoo 17,
    ``read`` on Odoo 16 (code of both), told by the route, never by a version."""
    return (f"(response) => ['web_read', 'read'].some((method) => response.url()"
            f".endsWith('/web/dataset/call_kw/{model}/' + method))")


# A view shown again, or a page without view (Discuss, where Odoo 19 goes back to after a record opened by its id):
# the controller of a window action is mounted before its renderer on Odoo 19.
_VIEW_SETTLED = (f"() => !document.querySelector({json.dumps(wc.ACTION)}) || "
                 f"!!document.querySelector({json.dumps(wc.ACTION + ' ' + wc.RENDERER)})")


def _record_left(record_id: int) -> str:
    """A page function true once the address no longer names ``record_id`` (``/web#id=`` or ``/odoo/.../<id>``)."""
    return ("() => { const found = location.hash.match(/[#&]id=([0-9]+)/) || location.pathname.match("
            f"/^[/]odoo[/].+[/]([0-9]+)$/); return !found || Number(found[1]) !== {int(record_id)}; }}")


class OdooWebRecordActionKeywords:
    """The Actions menu of a form in the web channel of `OdooFxLibrary`, mixed into it."""

    def _saved_form_record(self, gesture: str) -> int:
        record_id = self._require_form()
        if self._form_is_unsaved():
            # Delete does not save first (skipSave): its changes would be lost instead.
            effect = "lose its changes" if gesture.startswith("Delete") else "save it before acting"
            raise OdooRpcError(f"{gesture} refused before any click: the form is not saved, and Odoo would {effect}; "
                               "call Save Odoo Web Record or Discard Odoo Web Changes first")
        if self.odoo_web_confirmation_is_open():
            raise OdooRpcError(f"{gesture} refused before any click: a question of Odoo is still open")
        return record_id

    def _close_actions_menu(self) -> None:
        # Escape does not close it on Odoo 19 while the focus is on its button: a second click does.
        if self._browser("Get Element Count", ACTIONS_MENU_ENTRIES):
            self._browser("Click", ACTIONS_MENU_TOGGLE)
            self._browser("Wait For Elements State", f"css={ACTIONS_MENU_ENTRIES} >> nth=0", "detached")

    def _entry_by_position(self, gesture: str, model: str, record_id: int, shown: int) -> str:
        view = self._form_view(toolbar=True)
        fields = form_fields(view["arch"])
        names = [name for name in ("active", "x_active") if name in fields]
        readonly, record_active = {}, None
        if names:
            definitions = self._call_web_session(model, "fields_get", [names], {"attributes": ["readonly"]})
            readonly = {name: bool(definitions.get(name, {}).get("readonly")) for name in names}
            found = self._call_web_session(model, "search_read", [], {
                "domain": [["id", "=", record_id]], "fields": names, "context": {"active_test": False}})
            record_active = bool(found and found[0].get(names[0]))
        entries = callback_entries(view["arch"], readonly, record_active)
        server_actions = len(((view.get("toolbar") or {}).get("action")) or [])
        if shown != len(entries) + server_actions:
            raise OdooRpcError(f"The Actions menu shows {shown} entries, the code of Odoo gives {entries} plus "
                               f"{server_actions} server actions: the {gesture} entry cannot be told, nothing clicked")
        if gesture not in entries:
            raise OdooRpcError(f"The Actions menu of {model} {record_id} offers no {gesture} entry: it offers "
                               f"{entries} and {server_actions} server actions")
        return f"css={ACTIONS_MENU_ENTRIES} >> nth={entries.index(gesture)}"

    def _open_entry(self, gesture: str, model: str, record_id: int) -> str:
        if self._browser("Get Element Count", ACTIONS_MENU_TOGGLE) != 1:
            raise OdooRpcError("The form shows no Actions menu")
        self._browser("Click", ACTIONS_MENU_TOGGLE)
        self._browser("Wait For Elements State", f"css={ACTIONS_MENU_ENTRIES} >> nth=0", "visible")
        try:
            if self._browser("Get Element Count", f"{ACTIONS_MENU_ENTRIES} i"):
                entry = f"{ACTIONS_MENU_ENTRIES}:has(i.{ENTRY_ICONS[gesture]})"
                if self._browser("Get Element Count", entry) != 1:
                    raise OdooRpcError(f"The Actions menu of {model} {record_id} offers no {gesture} entry")
                return f"css={entry}"
            return self._entry_by_position(gesture, model, record_id,
                                           self._browser("Get Element Count", ACTIONS_MENU_ENTRIES))
        except Exception:
            self._close_actions_menu()
            raise

    def _answered(self, entry: dict, response, gesture: str, model: str, record_id: int) -> None:
        refusal = _error_of(response)
        if not refusal:
            return
        self._settle(entry, "failed", refusal, error_class_of(response))
        message = f"{wc.DIALOG_MESSAGE}:not([{_ASKED}])"
        left_open = ""
        try:
            self._browser("Wait For Elements State", f"css={message} >> nth=0", "visible")
            self._browser("Click", f"css={message} >> css=.modal-header .btn-close")
            self._browser("Wait For Elements State", f"css={message} >> nth=0", "detached")
        except Exception as exc:
            left_open = f" (its message could not be closed: {compact(exc)})"
        raise OdooRpcError(f"Odoo refused to {gesture} {model} {record_id}: {refusal}{left_open}")

    def _call_through(self, entry: dict, click: str, model: str, method: str, reload: bool):
        """Click ``click``, which has Odoo call ``method``; return its answer and, with ``reload``, the promise of
        the read of the record that follows it."""
        try:
            reread = self._browser("Promise To", "Wait For Response", reload_matcher(model)) if reload else None
            promise = self._browser("Promise To", "Wait For Response", f"**/web/dataset/call_kw/{model}/{method}")
            self._browser("Click", click)
            return self._browser("Wait For", promise), reread
        except Exception as exc:
            self._settle(entry, "unknown", f"{type(exc).__name__}: {compact(exc)}")
            raise

    def _act(self, gesture: str, confirm: bool) -> dict:
        title = f"{gesture.capitalize()} Odoo Web Record"
        record_id = self._saved_form_record(title)
        model = self.get_odoo_web_view()["model"]
        # Odoo shows the next record of the pager, else goes back to the view before: a record opened by its id
        # has neither, and Odoo 16 then stays on a form without record (decision of the owner, 2026-11-16).
        if (gesture == "delete" and confirm and not self._browser("Get Element Count", wc.PREVIOUS_CRUMBS)
                and (self.get_odoo_web_pager_total() or 0) <= 1):
            raise OdooRpcError(f"{title} refused before any click: the form of {model} {record_id} has no view "
                               "before it and no other record in its pager, Odoo would have nowhere to go back to; "
                               "open the record from a list to delete it")
        if confirm and not self._web_writes:
            raise OdooRpcError(f"Writes are off: {title} refused, log in to the web client with allow_write=${{TRUE}}")
        entry_selector = self._open_entry(gesture, model, record_id)
        method = METHODS[gesture]
        if gesture == "unarchive":
            entry = self._journal_web_write(title, "call", method, model, record_id, set())
            response, reread = self._call_through(entry, entry_selector, model, method, True)
            self._answered(entry, response, gesture, model, record_id)
            return self._after_reload(entry, record_id, None, reread)
        self._browser("Click", entry_selector)
        try:
            self._browser("Wait For Elements State", f"css={CONFIRMATION}", "visible")
        except Exception:
            raise OdooRpcError(f"Odoo asked no question after the {gesture} entry of {model} {record_id}: "
                               "nothing accepted, read the record before going on") from None
        question = compact(self._browser("Get Text", f"css={CONFIRMATION} >> css=.modal-body"))
        if not confirm:
            self._dismiss_confirmation()
            return {"record_id": record_id, "confirmed": False, "question": question}
        self._browser("Evaluate JavaScript", f"css={CONFIRMATION}", _MARK_ASKED)
        entry = self._journal_web_write(title, "call", method, model, record_id, set())
        response, reread = self._call_through(entry, f"css={CONFIRMATION_ACCEPT}", model, method,
                                              gesture == "archive")
        self._answered(entry, response, gesture, model, record_id)
        if gesture == "archive":
            return self._after_reload(entry, record_id, question, reread)
        return self._after_delete(entry, record_id, question)

    def _after_reload(self, entry: dict, record_id: int, question: Optional[str], reread) -> dict:
        # The form shows the record saved before the click already: only the read of the record that follows
        # the method says Odoo shows it changed (measured on Odoo 19, the ribbon changing with its answer).
        try:
            self._browser("Wait For", reread)
            self._browser("Wait For Elements State", f"css={CONFIRMATION}", "detached")
            self._browser("Wait For Function", wc.BUTTONS_SETTLED)
            self._browser("Wait For Elements State", f"css={wc.FORM_STATE}.o_form_saved", "visible")
        except Exception as exc:
            self._settle(entry, "unknown", f"answered, but the form did not show the record read again: "
                                           f"{compact(exc)}")
            raise
        self._settle(entry, "done")
        return {"record_id": record_id, "confirmed": question is not None, "question": question}

    def _after_delete(self, entry: dict, record_id: int, question: str) -> dict:
        try:
            self._browser("Wait For Function", _record_left(record_id))
            self._browser("Wait For Elements State", f"css={CONFIRMATION}", "detached")
            self._browser("Wait For Function", _VIEW_SETTLED)
            if self._browser("Get Element Count", wc.FORM_STATE):
                self._browser("Wait For Elements State", f"css={wc.FORM_STATE}.o_form_saved", "visible")
        except Exception as exc:
            self._settle(entry, "unknown", f"answered, but Odoo still shows the record: {compact(exc)}")
            raise
        self._settle(entry, "done")
        self._web_filled = set()
        shown = self.get_odoo_web_view() if self._browser("Get Element Count", wc.ACTION) else None
        return {"record_id": record_id, "confirmed": True, "question": question, "shown": shown}

    @keyword("Archive Odoo Web Record")
    def archive_odoo_web_record(self, confirm: bool = True) -> dict:
        """Archive the record of the form shown through the Archive entry of its Actions menu.

        The entry is told by its icon where the menu shows icons (Odoo 19),
        else by the position the code of Odoo gives it, the menu showing
        exactly the entries that code gives (Odoo 16); never by its label.
        Odoo asks a question first: it is accepted, which needs a web session
        opened with ``allow_write`` and is journaled as a ``call`` of
        ``action_archive`` (``done`` once the form shows the record saved
        again, ``failed`` with Odoo's message and ``error_class`` when Odoo
        refuses, ``unknown`` without an answer). With ``confirm=${FALSE}`` the
        question is refused instead: nothing is written nor journaled.

        Refused before any click: no form, a new record, a form that is not
        saved (Odoo would save it first), a question still open, a menu
        without the entry (a model without ``active``, a record already
        archived). Returns ``record_id``, ``confirmed`` and ``question``, the
        text Odoo asked (translated: read it, never assert it).

        Example:
        | ${archived}=    `Archive Odoo Web Record`
        | Should Be True    ${archived}[confirmed]
        | ${unarchived}=    `Unarchive Odoo Web Record`
        | Should Be Equal    ${unarchived}[question]    ${NONE}
        """
        return self._act("archive", confirm)

    @keyword("Unarchive Odoo Web Record")
    def unarchive_odoo_web_record(self) -> dict:
        """Unarchive the archived record of the form shown through the Unarchive entry of its Actions menu.

        Found as `Archive Odoo Web Record` finds its entry. Odoo asks
        nothing: the click calls ``action_unarchive``, which needs a web
        session opened with ``allow_write`` and is journaled the same way.
        Refused before any click as `Archive Odoo Web Record` is, and when
        the record is not archived (its menu offers no Unarchive entry).
        Returns ``record_id``, ``confirmed`` (``False``) and ``question``
        (``None``).

        Example:
        | `Archive Odoo Web Record`
        | ${unarchived}=    `Unarchive Odoo Web Record`
        | Should Not Be True    ${unarchived}[confirmed]
        """
        return self._act("unarchive", True)

    @keyword("Delete Odoo Web Record")
    def delete_odoo_web_record(self, confirm: bool = True) -> dict:
        """Delete the record of the form shown through the Delete entry of its Actions menu.

        Found as `Archive Odoo Web Record` finds its entry. Odoo asks a
        question first: it is accepted, journaled as a ``call`` of ``unlink``
        (``done`` once Odoo no longer shows the record, ``failed`` with
        Odoo's message and ``error_class`` when Odoo refuses, the message it
        showed then closed and the form left shown, ``unknown`` without an
        answer). Odoo then shows the next record of the pager, or the view
        before the form when none is left. With ``confirm=${FALSE}`` the
        question is refused: nothing is written nor journaled.

        Refused before any click as `Archive Odoo Web Record` is (a form not
        saved included, although Odoo would not save it: its changes would be
        lost), and, the question to be accepted, when the form has no view
        before it and no other record in its pager (a record opened by its
        id): Odoo would have nowhere to go back to, Odoo 16 staying on a form
        without record; refusing the question deletes nothing and is allowed. Returns
        ``record_id``, ``confirmed``, ``question`` and, once deleted,
        ``shown``: the view Odoo shows then (`Get Odoo Web View`), ``None`` on
        a page without view.

        Example:
        | ${refused}=    `Delete Odoo Web Record`    confirm=${FALSE}
        | Should Not Be True    ${refused}[confirmed]
        | ${deleted}=    `Delete Odoo Web Record`
        | Should Be Equal    ${deleted}[shown][view_type]    list
        """
        return self._act("delete", confirm)

    @keyword("Odoo Web Confirmation Is Open")
    def odoo_web_confirmation_is_open(self) -> bool:
        """Whether Odoo shows a question in a box of its own: no form inside, a button that accepts and one that
        refuses (the box of Archive and Delete).

        Example:
        | `Archive Odoo Web Record`    confirm=${FALSE}
        | ${asked}=    `Odoo Web Confirmation Is Open`
        | Should Not Be True    ${asked}
        """
        return bool(self._browser("Get Element Count", CONFIRMATION))

    def _dismiss_confirmation(self) -> None:
        # Kept inside the library (decision of the owner, 2026-11-16): no gesture leaves a question open, so a
        # public keyword would be played by no live suite; confirm=${FALSE} uses it.
        self._browser("Click", f"css={CONFIRMATION_REFUSE}")
        self._browser("Wait For Elements State", f"css={CONFIRMATION}", "detached")
