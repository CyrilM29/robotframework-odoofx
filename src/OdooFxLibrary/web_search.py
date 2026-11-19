"""The search bar of the web client: a text searched on a field of the search view, its filters, its facets.

No anchor of the page names the field of a proposal nor the filter of an entry: a proposal carries a counter
of the client, an entry its translated label only (measured on Odoo 19, read in the code of 16 and 19). A field
or a filter is therefore named by its technical name and found by its POSITION among the visible elements of
the action's search view, read in its arch (decision of the owner, 2026-11-16); then the domain the client
sends with its search is checked against the one the arch gives, so that a shifted position never passes in
silence.

The client proposes, for a text, one entry per visible ``<field>`` of the arch, in their order, except the
fields whose type does not read the text (a number, a date) and the selection and boolean fields, which
propose one entry per option whose label matches (``search_bar.js`` of 16 and 19): such a field before the
one searched makes its position unknowable, and the search is refused before anything is typed.
"""

import ast
import json
from typing import Any, Optional
from xml.etree import ElementTree

from robot.api.deco import keyword

from . import web_client as wc
from .rpc import OdooRpcError, compact

# One proposal whatever the text (CHAR_FIELDS of search_bar.js, and properties, which 16 parses as text).
ONE_PROPOSAL_TYPES = frozenset({"char", "html", "many2many", "many2one", "one2many", "text", "properties"})

# Anchors measured on Odoo 16 and 19 (plans specs/recherche_archivage_web_odoo16.md and _odoo19.md): the proposals
# float in the overlay on 19 and stay in the search bar on 16; the custom filter entry of 19 carries no id.
SEARCH_INPUT = f"{wc.ACTION} .o_searchview input.o_searchview_input"
PROPOSALS = ".o_searchview_autocomplete :is(li.o_menu_item, .o-dropdown-item)"
FIELD_PROPOSALS = f"{PROPOSALS}[id]:not(.o_indent)"
SUB_PROPOSALS = f"{PROPOSALS}.o_indent"
FILTER_MENU_TOGGLE = (f"{wc.ACTION} .o_control_panel :is(button.o_searchview_dropdown_toggler, "
                      ".o_filter_menu > button.dropdown-toggle)")
FILTER_ENTRIES = ".o_filter_menu [role=menuitemcheckbox]:not(.o_add_custom_filter)"
FACET_REMOVE = ".o_facet_remove"
SEARCH_RESPONSE = "**/web_search_read"
NAME_SEARCH_RESPONSE = "**/name_search"
_TRUE = {"1", "True", "true"}
_FALSE = {"0", "False", "false"}


def _is_invisible(node: ElementTree.Element) -> bool:
    # Odoo 16 renders the invisibility of a search item in a JSON modifiers attribute, without invisible.
    if node.get("modifiers"):
        try:
            hidden = json.loads(node.get("modifiers")).get("invisible", False)
        except (ValueError, AttributeError):
            raise OdooRpcError(f"The modifiers of {node.tag} {node.get('name')!r} cannot be read") from None
        if isinstance(hidden, (bool, int)):
            return bool(hidden)
        raise OdooRpcError(f"The search view hides {node.tag} {node.get('name')!r} under the condition {hidden!r}: "
                           "whether it is shown cannot be told, nor the position of what follows it")
    value = node.get("invisible")
    if value is None or value in _FALSE:
        return False
    if value in _TRUE:
        return True
    raise OdooRpcError(f"The search view hides {node.tag} {node.get('name')!r} under the expression {value!r}: "
                       "whether it is shown cannot be told, nor the position of what follows it")


def _groups_by(node: ElementTree.Element) -> bool:
    return "group_by" in (node.get("context") or "")


def search_view_items(arch: str) -> dict:
    """The ``fields`` and the ``filters`` of a search view's arch, in their order, each with ``visible``.

    A field: ``name``, ``operator``, ``filter_domain``. A filter of the filter menu (never a group-by, never
    a filter of the search panel): ``name``, ``domain``, ``date`` (the field of a date filter, ``None``
    otherwise), ``group`` (filters between two separators share a group)."""
    root = ElementTree.fromstring(arch)
    fields, filters, group = [], [], 0

    def visit(node: ElementTree.Element) -> None:
        nonlocal group
        for child in node:
            if child.tag == "searchpanel":
                continue
            if child.tag == "separator":
                group += 1
            elif child.tag == "field":
                group += 1
                fields.append({"name": child.get("name"), "operator": child.get("operator"),
                               "filter_domain": child.get("filter_domain"), "visible": not _is_invisible(child)})
            elif child.tag == "filter":
                if not _groups_by(child):
                    filters.append({"name": child.get("name"), "domain": child.get("domain") or "[]",
                                    "date": child.get("date"), "group": group,
                                    "visible": not _is_invisible(child)})
            else:
                visit(child)

    visit(root)
    return {"fields": fields, "filters": filters}


def _named(items: list, name: str, kind: str) -> dict:
    found = [item for item in items if item["name"] == name]
    if not found:
        shown = [item["name"] for item in items if item["visible"]]
        raise OdooRpcError(f"The search view has no {kind} {name}: its visible {kind}s are {shown}")
    if not found[0]["visible"]:
        raise OdooRpcError(f"The {kind} {name} is invisible in the search view: the search bar does not offer it")
    return found[0]


def proposal_position(fields: list, types: dict, name: str) -> int:
    """The position (1 for the first) of the proposal of field ``name`` for any text, among the proposals.

    ``fields`` comes from `search_view_items`, ``types`` maps a field name to its type."""
    target = _named(fields, name, "field")
    if types.get(name) not in ONE_PROPOSAL_TYPES:
        raise OdooRpcError(f"Field {name} is a {types.get(name)} field: the search bar proposes it only for some "
                           "texts, a text search on it is not offered by this keyword")
    position = 0
    for field in fields:
        if not field["visible"]:
            continue
        if field is target:
            return position + 1
        if types.get(field["name"]) not in ONE_PROPOSAL_TYPES:
            raise OdooRpcError(f"Field {field['name']} ({types.get(field['name'])}) comes before {name} in the "
                               "search view and proposes a number of entries that depends on the text: the "
                               f"position of {name} cannot be told")
        position += 1
    raise AssertionError("unreachable: the target is a visible field")


def exact_proposal_count(fields: list, types: dict) -> Optional[int]:
    """How many field proposals any text gets, ``None`` when a visible field makes it depend on the text."""
    visible = [field for field in fields if field["visible"]]
    if any(types.get(field["name"]) not in ONE_PROPOSAL_TYPES for field in visible):
        return None
    return len(visible)


def _menu_filters(filters: list) -> list:
    # A date filter is a menu of periods (a submenu on Odoo 16, an accordion on 19), never a checkable entry.
    return [item for item in filters if item["visible"] and not item["date"]]


def visible_filter_position(filters: list, name: str) -> int:
    """The position (1 for the first) of filter ``name`` among the checkable entries of the filter menu."""
    target = _named(filters, name, "filter")
    if target["date"]:
        raise OdooRpcError(f"Filter {name} is a date filter (a menu of periods): not offered by this keyword")
    return _menu_filters(filters).index(target) + 1


def menu_filter_count(filters: list) -> int:
    """How many checkable entries the filter menu shows: its visible filters, date filters aside."""
    return len(_menu_filters(filters))


def evaluate_domain(text: str, names: dict) -> list:
    """The domain written ``text`` in an arch, with only the ``names`` given (``self``, ``uid``...).

    Refused when the domain calls a function or names anything else (``context_today()``): the domain the
    client would send cannot be computed, so it cannot be checked."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise OdooRpcError(f"The domain {text!r} of the search view cannot be read: {exc.msg}") from None

    def value(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [value(item) for item in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return -node.operand.value
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        raise OdooRpcError(f"The domain {text!r} of the search view uses {ast.unparse(node)!r}: the domain the "
                           "client sends cannot be computed, nor checked")

    result = value(tree.body)
    if not isinstance(result, list):
        raise OdooRpcError(f"The domain {text!r} of the search view is not a list")
    return result


def field_search_domain(field: dict, text: str, record: Optional[dict] = None, char_like: bool = True) -> list:
    """The domain the client sends for ``text`` searched on ``field``, or for the proposal of ``record``.

    ``record`` (``id`` and ``display_name``) is a sub-proposal of a many2one field: the client searches its id,
    under the field's operator, ``=`` by default; a ``filter_domain`` reads the name shown as ``self``."""
    label = record["display_name"] if record else text.strip()
    value = record["id"] if record else text.strip()
    if field["filter_domain"]:
        return evaluate_domain(field["filter_domain"], {"self": label.strip(), "raw_value": value})
    default = "=" if record or not char_like else "ilike"
    return [[field["name"], field["operator"] or default, value]]


def _as_lists(domain: Any) -> Any:
    return [_as_lists(item) for item in domain] if isinstance(domain, (list, tuple)) else domain


def domain_holds(sent: Any, expected: list) -> bool:
    """Whether the domain ``sent`` by the client holds ``expected`` as a run of its terms.

    The client joins the conditions of several facets with ``&`` (and those of a group of filters with
    ``|``) around them, never inside them."""
    sent, expected = _as_lists(sent or []), _as_lists(expected)
    if not expected:
        return True
    return any(sent[start:start + len(expected)] == expected for start in range(len(sent) - len(expected) + 1))


def _json_of(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def search_answer(response: Any) -> dict:
    """The ``domain`` a ``web_search_read`` of the client sent, its ``limit`` and the ``total`` Odoo answered."""
    request = _json_of((response or {}).get("request", {}).get("postData")) or {}
    kwargs = (request.get("params") or {}).get("kwargs") or {}
    body = _json_of((response or {}).get("body")) or {}
    if body.get("error"):
        error = body["error"]
        raise OdooRpcError(f"Odoo refused the search: {compact((error.get('data') or {}).get('message') or error)}")
    result = body.get("result") or {}
    if "domain" not in kwargs or "length" not in result:
        raise OdooRpcError("The search request of the web client carries no domain or no total")
    return {"domain": kwargs["domain"], "limit": kwargs.get("limit"), "total": result["length"]}


class OdooWebSearchKeywords:
    """The search bar of the web channel of `OdooFxLibrary`, mixed into it."""

    def _search_view(self) -> dict:
        view = self.get_odoo_web_view()
        if view["view_type"] != "list":
            raise OdooRpcError(f"The view shown is a {view['view_type']} view: the search is played on a list "
                               "(Switch Odoo Web View    list)")
        action = self._read_window_action(view["action"], ["search_view_id"])
        search_view = action.get("search_view_id") or False
        views = self._call_web_session(view["model"], "get_views", [], {
            "views": [[search_view[0] if search_view else False, "search"]], "options": {}})
        types = self._call_web_session(view["model"], "fields_get", [], {"attributes": ["type"]})
        items = search_view_items(views["views"]["search"]["arch"])
        items.update(model=view["model"], types={name: value.get("type") for name, value in types.items()})
        return items

    def _settle_search(self, promise, expected: list, what: str) -> dict:
        answer = search_answer(self._browser("Wait For", promise))
        if not domain_holds(answer["domain"], expected):
            raise OdooRpcError(f"The web client searched {answer['domain']}, the search view gives {expected} for "
                               f"{what}: another entry was chosen, the facet it added stays")
        shown = min(answer["total"], answer["limit"] or answer["total"])
        self._browser("Wait For Function", f"() => document.querySelectorAll({json.dumps(wc.LIST_ROWS)})"
                                           f".length === {int(shown)}")
        return {"total": answer["total"], "domain": answer["domain"],
                "facets": self._browser("Get Element Count", wc.FACETS)}

    def _clear_search_input(self) -> None:
        self._browser("Fill Text", SEARCH_INPUT, "")
        self._browser("Wait For Elements State", f"css={PROPOSALS} >> nth=0", "detached")

    @keyword("Search Odoo Web View")
    def search_odoo_web_view(self, field: str, text: str, record_id: Optional[int] = None) -> dict:
        """Search ``text`` on the field ``field`` of the list shown, through its search bar; return the result.

        ``field`` is the technical name of a field of the action's search
        view (``name``, ``partner_id``). Its proposal is never told by its
        translated label: it is found at the position of the field among the
        visible fields of the search view, read in its arch, then the domain
        the web client sends is checked against the one the arch gives (the
        ``filter_domain`` of the field with ``text``, else its operator), and
        the keyword fails, naming both, when they differ. With ``record_id``
        (a many2one field), the proposals of the field are unfolded and the
        record of that id is chosen, found in the answer of Odoo's
        ``name_search``; the client then searches that record (``child_of``
        or ``=`` its id, per the field's operator).

        Waits for the answer of the client's search and for the list to show
        its rows, and returns ``total`` (the count Odoo answered), ``domain``
        (the domain sent) and ``facets`` (the facets shown). Writes nothing.

        Refused before anything is typed: a view that is not a list, a field
        absent or invisible in the search view, a field whose proposals
        depend on the text (a number, a date, a selection) or one placed after
        such a field, a search bar already holding text. Refused once typed,
        the text cleared: the proposals shown differ from those the arch
        gives, a record not proposed.

        Example:
        | `Switch Odoo Web View`    list
        | ${result}=    `Search Odoo Web View`    name    ${marker}
        | Should Be Equal As Integers    ${result}[total]    2
        | Should Be Equal As Integers    ${result}[facets]    1
        """
        items = self._search_view()
        position = proposal_position(items["fields"], items["types"], field)
        if items["types"].get(field) == "properties":
            raise OdooRpcError(f"Field {field} holds properties: its proposal searches no text")
        if self._browser("Get Element Count", SEARCH_INPUT) != 1:
            raise OdooRpcError("The view shows no search bar")
        if self._browser("Get Property", SEARCH_INPUT, "value"):
            raise OdooRpcError("The search bar already holds text: nothing typed")
        definition = next(item for item in items["fields"] if item["name"] == field)
        self._browser("Fill Text", SEARCH_INPUT, str(text))
        self._browser("Wait For Elements State", f"css={FIELD_PROPOSALS} >> nth=0", "visible")
        shown = self._browser("Get Element Count", FIELD_PROPOSALS)
        exact = exact_proposal_count(items["fields"], items["types"])
        if shown < position or (exact is not None and shown != exact):
            self._clear_search_input()
            expected = exact if exact is not None else f"at least {position}"
            raise OdooRpcError(f"The search bar proposes {shown} fields, the search view gives {expected}: "
                               f"{field} cannot be told")
        proposal = f"css={FIELD_PROPOSALS} >> nth={position - 1}"
        record = None
        target = proposal
        if record_id is not None:
            record = self._unfold_record(proposal, field, int(record_id))
            target = f"css={SUB_PROPOSALS} >> nth={record['index']}"
        expected = field_search_domain(definition, str(text), record)
        promise = self._browser("Promise To", "Wait For Response", SEARCH_RESPONSE)
        self._browser("Click", f"{target} >> css=a:not(.o_expand)")
        return self._settle_search(promise, expected, f"field {field}")

    def _unfold_record(self, proposal: str, field: str, record_id: int) -> dict:
        unfold = f"{proposal} >> css=a.o_expand"
        if self._browser("Get Element Count", unfold) != 1:
            self._clear_search_input()
            raise OdooRpcError(f"Field {field} proposes no records to choose from (it is no many2one)")
        promise = self._browser("Promise To", "Wait For Response", NAME_SEARCH_RESPONSE)
        self._browser("Click", unfold)
        body = _json_of(self._browser("Wait For", promise).get("body")) or {}
        proposed = [entry for entry in body.get("result") or [] if isinstance(entry, list) and len(entry) == 2]
        ids = [entry[0] for entry in proposed]
        if record_id not in ids:
            self._clear_search_input()
            raise OdooRpcError(f"Odoo proposes the records {ids} for field {field}, not {record_id}")
        index = ids.index(record_id)
        name = proposed[index][1]
        sub = f"css={SUB_PROPOSALS} >> nth={index}"
        self._browser("Wait For Elements State", sub, "visible")
        if compact(self._browser("Get Text", sub)) != compact(name):
            self._clear_search_input()
            raise OdooRpcError(f"The proposal {index + 1} of field {field} does not show {name!r}: "
                               "the record cannot be told")
        return {"id": record_id, "display_name": name, "index": index}

    @keyword("Select Odoo Web Search Filter")
    def select_odoo_web_search_filter(self, name: str) -> dict:
        """Apply the filter ``name`` of the search view to the list shown, through the filter menu.

        ``name`` is the technical name of a filter of the action's search
        view (``inactive``, ``my_quotation``). Its entry is never told by its
        translated label: it is found at the position of the filter among the
        checkable filters of the search view, read in its arch, the menu
        having to show exactly that many; the domain the client sends must
        hold the filter's domain, evaluated with the session's ``uid``. The
        menu is closed again. Returns ``total``, ``domain`` and ``facets`` as
        `Search Odoo Web View` does. Writes nothing.

        Refused before any click: a view that is not a list, a filter absent,
        invisible or of dates, a domain the library cannot evaluate (one that
        calls a function), a filter already applied (remove its facet with
        `Remove Odoo Web Search Facet`), a menu that shows another count of
        filters.

        Example:
        | `Switch Odoo Web View`    list
        | ${result}=    `Select Odoo Web Search Filter`    inactive
        | Should Be Equal    ${result}[domain]    ${{[["active", "=", False]]}}
        | Should Be Equal As Integers    ${result}[facets]    1
        """
        items = self._search_view()
        position = visible_filter_position(items["filters"], name)
        definition = next(item for item in items["filters"] if item["name"] == name)
        expected = evaluate_domain(definition["domain"], {"uid": self.get_odoo_web_session_info()["uid"]})
        if not self._browser("Get Element Count", FILTER_ENTRIES):
            self._browser("Click", FILTER_MENU_TOGGLE)
            self._browser("Wait For Elements State", f"css={FILTER_ENTRIES} >> nth=0", "visible")
        try:
            shown = self._browser("Get Element Count", FILTER_ENTRIES)
            if shown != menu_filter_count(items["filters"]):
                raise OdooRpcError(f"The filter menu shows {shown} filters, the search view gives "
                                   f"{menu_filter_count(items['filters'])}: filter {name} cannot be told")
            entry = f"css={FILTER_ENTRIES} >> nth={position - 1}"
            if self._browser("Get Attribute", entry, "aria-checked") == "true":
                raise OdooRpcError(f"Filter {name} is already applied: remove its facet with Remove Odoo Web "
                                   "Search Facet")
            promise = self._browser("Promise To", "Wait For Response", SEARCH_RESPONSE)
            self._browser("Click", entry)
            return self._settle_search(promise, expected, f"filter {name}")
        finally:
            if self._browser("Get Element Count", FILTER_ENTRIES):
                self._browser("Keyboard Key", "press", "Escape")
                self._browser("Wait For Elements State", f"css={FILTER_ENTRIES} >> nth=0", "detached")

    @keyword("Remove Odoo Web Search Facet")
    def remove_odoo_web_search_facet(self, position: int) -> dict:
        """Remove the facet at ``position`` (1 for the first) of the search bar by its cross; return the result.

        A facet carries no technical name (a field searched shows its
        translated label, a filter an icon): its position is the only honest
        designation. Waits for the client's search and for the list to show
        its rows, and returns ``total``, ``domain`` and ``facets`` as `Search
        Odoo Web View` does; the facets shown must be one fewer. Writes
        nothing. Refused: a view that is not a list, a position outside the
        facets.

        Example:
        | `Switch Odoo Web View`    list
        | `Search Odoo Web View`    name    ${marker}
        | ${result}=    `Remove Odoo Web Search Facet`    1
        | Should Be Equal As Integers    ${result}[facets]    0
        | Should Be Empty    ${result}[domain]
        """
        if self.get_odoo_web_view()["view_type"] != "list":
            raise OdooRpcError("The search is played on a list (Switch Odoo Web View    list)")
        before = self._browser("Get Element Count", wc.FACETS)
        if not 1 <= int(position) <= before:
            raise OdooRpcError(f"The search bar shows {before} facets: there is no facet {position}")
        promise = self._browser("Promise To", "Wait For Response", SEARCH_RESPONSE)
        self._browser("Click", f"css={wc.FACETS} >> nth={int(position) - 1} >> css={FACET_REMOVE}")
        result = self._settle_search(promise, [], f"the removal of facet {position}")
        if result["facets"] != before - 1:
            raise OdooRpcError(f"The search bar shows {result['facets']} facets after removing one of {before}")
        return result
