"""Which HTTP requests write on Odoo, and whether one may be sent: the pure logic of the HTTP write guard.

Decision of the owner of 2026-11-07 (ODOOFX-225): an HTTP request that writes on Odoo through its RPC
routes passes the lock of the RPC channel (``allow_write`` of the proven connection), the write journal,
and is sent once. The call is read from the route and the body, never from the HTTP verb: Odoo runs a
call of ``/web/dataset/call_kw`` whatever the verb, GET, OPTIONS and HEAD included, ignores the model
and method of its path for those of its body, and runs an XML-RPC call by OPTIONS (measured on Odoo 16
and 19). The routes are recognized on any host, so that another origin of the same server is no way
round the proven target. A method outside the list of reads counts as a write (refused by default); a
call of ``call_button``, ``resequence`` or a website form is always a write; the database service and
the database manager (``/web/database/...``) send their reads only, never anything else. The path is
normalized first (percent-encoding, repeated slashes, ``.`` and ``..``), so that ``//jsonrpc`` is
``/jsonrpc``. The database a call names (in an XML-RPC or ``/jsonrpc`` body, or the ``X-Odoo-Database``
header of JSON-2) must be the proven one; the database of a web session is not read. Every other request (a login, a page,
a report, a third-party API) is no Odoo call for the guard and keeps the behaviour of RequestsLibrary.
"""

import json
import posixpath
import re
import xmlrpc.client
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import unquote, urlsplit

from .rpc import GATEWAY_ERRORS

READ_METHODS = frozenset({
    "search_count", "search", "search_read", "read", "name_search", "name_get", "fields_get", "default_get",
    "check_access_rights", "has_access", "read_group", "formatted_read_group", "web_search_read", "web_read",
    "web_read_group", "get_views",
})
DB_READ_METHODS = frozenset({"list"})
COMMON_READ_METHODS = frozenset({"version", "about", "login", "authenticate"})
ALWAYS_WRITES = frozenset({"call_button", "resequence", "website_form"})
DATABASE_MANAGER_READS = ("manager", "selector", "list")
UNKNOWN = "?"


@dataclass(frozen=True)
class OdooRpcCall:
    """An Odoo call a request carries: its route, service, model, method, the database its body names,
    the ids it targets and the names of the fields it writes (never their values)."""

    route: str
    service: str
    model: str
    method: str
    database: str = ""
    ids: tuple = ()
    fields: tuple = ()

    @property
    def name(self) -> str:
        return f"{self.model}.{self.method}"


def read_url_origin(url: str) -> tuple:
    """The scheme, host and port of ``url``, lower case and the default port made explicit."""
    parts = urlsplit(str(url))
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or {"http": 80, "https": 443}.get(
        parts.scheme.lower())


def shown_origin(url: str) -> str:
    scheme, host, port = read_url_origin(url)
    return f"{scheme}://{host}:{port}"


def _json_of(json_body: Any, data: Any) -> dict:
    if isinstance(json_body, dict):
        return json_body
    if isinstance(data, (str, bytes)):
        try:
            parsed = json.loads(data)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(value: Any) -> str:
    return value if isinstance(value, str) and value else UNKNOWN


def _ids_of(args: Any) -> tuple:
    first = args[0] if isinstance(args, (list, tuple)) and args else None
    if isinstance(first, int) and not isinstance(first, bool):
        return (first,)
    if isinstance(first, (list, tuple)) and all(isinstance(i, int) and not isinstance(i, bool) for i in first):
        return tuple(first)
    return ()


def _fields_of(args: Any, kwargs: Any = None) -> tuple:
    candidates = list(args) if isinstance(args, (list, tuple)) else []
    if isinstance(kwargs, dict):
        candidates += [kwargs.get(name) for name in ("vals", "values", "vals_list")]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
            candidate = candidate[0]
        if isinstance(candidate, dict) and candidate:
            return tuple(sorted(str(name) for name in candidate))
    return ()


def _object_call(route: str, model: Any, method: Any, database: Any, args: Any, kwargs: Any) -> OdooRpcCall:
    return OdooRpcCall(route, "object", _text(model), _text(method), database if isinstance(database, str) else "",
                       _ids_of(args), _fields_of(args, kwargs))


def _execute_call(route: str, service: Any, method: Any, args: Any) -> OdooRpcCall:
    if service == "object":
        if method not in ("execute_kw", "execute") or not isinstance(args, (list, tuple)) or len(args) < 5:
            return OdooRpcCall(route, "object", UNKNOWN, _text(method))
        return _object_call(route, args[3], args[4], args[0], args[5] if len(args) > 5 else (),
                            args[6] if len(args) > 6 else None)
    return OdooRpcCall(route, service if service in ("db", "common") else UNKNOWN, service or UNKNOWN, _text(method))


def normalized_path(url: str) -> str:
    """The path of ``url`` as a server resolves it: percent-encoding decoded, repeated slashes, ``.`` and ``..``
    collapsed, no final slash; a path that resolves to an Odoo route is recognized as that route."""
    path = re.sub(r"/{2,}", "/", unquote(urlsplit(str(url)).path) or "/")
    return posixpath.normpath(path).rstrip("/") or "/"


def read_odoo_rpc_call(url: str, json_body: Any = None, data: Any = None,
                       database_header: str = "") -> Optional[OdooRpcCall]:
    """The Odoo call a request to ``url`` with this body carries, or None when the route is no Odoo call.

    ``database_header`` is the ``X-Odoo-Database`` header the request sends, the database of a JSON-2 call."""
    path = normalized_path(url)
    if path == "/web/dataset/call_kw" or path.startswith("/web/dataset/call_kw/") or path in (
            "/web/dataset/call_button", "/web/dataset/resequence"):
        params = _json_of(json_body, data).get("params")
        params = params if isinstance(params, dict) else {}
        route = path.rsplit("/", 1)[-1] if not path.startswith("/web/dataset/call_kw") else "call_kw"
        if route == "resequence":
            return OdooRpcCall(route, "object", _text(params.get("model")), "resequence",
                               ids=tuple(params.get("ids") or ()), fields=(params.get("field") or "sequence",))
        return _object_call(route, params.get("model"), params.get("method"), "", params.get("args"),
                            params.get("kwargs"))
    if path.startswith("/json/2/"):
        model, _, method = path[len("/json/2/"):].rpartition("/")
        body = _json_of(json_body, data)
        return OdooRpcCall("json2", "object", _text(model), _text(method), database_header or "",
                           tuple(body.get("ids") or ()), _fields_of((), body))
    if path.startswith("/website/form/"):
        return OdooRpcCall("website_form", "object", _text(path[len("/website/form/"):]), "create")
    if path.startswith("/web/database/") and path.rsplit("/", 1)[-1] not in DATABASE_MANAGER_READS:
        return OdooRpcCall("database_manager", "db", "db", path.rsplit("/", 1)[-1])
    service = {"/xmlrpc/2/object": "object", "/xmlrpc/object": "object", "/xmlrpc/2/db": "db",
               "/xmlrpc/db": "db", "/xmlrpc/2/common": "common", "/xmlrpc/common": "common"}.get(path)
    if service:
        try:
            args, method = xmlrpc.client.loads(data if isinstance(data, (str, bytes)) else b"")
        except Exception:
            args, method = (), None
        return _execute_call("xmlrpc", service, method, args)
    if path == "/jsonrpc":
        params = _json_of(json_body, data).get("params")
        params = params if isinstance(params, dict) else {}
        return _execute_call("jsonrpc", params.get("service"), params.get("method"), params.get("args"))
    return None


def is_odoo_read_call(call: OdooRpcCall) -> bool:
    """True for a call of the list of reads; False for every other call, an unreadable body included."""
    if call.route in ALWAYS_WRITES:
        return False
    if call.service == "common":
        return call.method in COMMON_READ_METHODS
    if call.service == "db":
        return call.method in DB_READ_METHODS
    return call.service == "object" and call.method in READ_METHODS


def is_never_sent(call: OdooRpcCall) -> bool:
    """True for a call of the database service or the database manager other than ``list``: never sent."""
    return call.service == "db" and not is_odoo_read_call(call)


def refusal_of(call: OdooRpcCall, verb: str, url: str, connection: Optional[dict]) -> Optional[str]:
    """Why the write ``call`` may not be sent by ``verb`` to ``url`` under ``connection``, or None."""
    where = f"HTTP {verb.upper()} {call.route} {call.name}"
    if is_never_sent(call):
        return f"Odoo database service refused: {where} is never sent by the HTTP keywords"
    if verb.lower() == "head":
        return f"A write is never sent by HEAD: {where} would run with no answer to tell its outcome"
    if connection is None:
        return f"Not connected: call Connect To Odoo first, {where} is a write on Odoo"
    if read_url_origin(url) != read_url_origin(connection["url"]):
        return (f"{where} refused: {shown_origin(url)} is not the proven target "
                f"{shown_origin(connection['url'])}")
    if call.database and call.database != connection["database"]:
        return f"{where} refused: database {call.database} is not the proven database {connection['database']}"
    if not connection["allow_write"]:
        return (f"Writes are off: {call.method} on {call.model} refused ({where}), connect with "
                "allow_write=${TRUE}")
    return None


def _created_ids(call: OdooRpcCall, result: Any) -> tuple:
    if call.method != "create" or isinstance(result, bool):
        return ()
    if isinstance(result, int):
        return (result,)
    if isinstance(result, dict) and isinstance(result.get("id"), int):
        return (result["id"],)
    if isinstance(result, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in result):
        return tuple(result)
    return ()


def read_write_outcome(call: OdooRpcCall, status: int, content: bytes) -> tuple:
    """The phase (``done``, ``failed``, ``unknown``), the error and the ids created of a write Odoo answered."""
    if 300 <= status < 400:
        return "failed", f"HTTP {status}: redirected, not followed, the call did not run", ()
    if status in GATEWAY_ERRORS:
        return "unknown", f"HTTP {status}: a gateway answered, the call may have run: reconcile by reading", ()
    if status >= 400:
        name = (_json_of(None, content).get("name") or "") if call.route == "json2" else ""
        return "failed", f"HTTP {status}" + (f" {name}" if name else ""), ()
    if call.route == "xmlrpc":
        try:
            (result,), _ = xmlrpc.client.loads(content)
        except xmlrpc.client.Fault as fault:
            return "failed", f"XML-RPC fault {fault.faultCode}", ()
        except Exception:
            return "unknown", "answer not read: outcome unknown", ()
        return "done", "", _created_ids(call, result)
    try:
        body = json.loads(content)
    except ValueError:
        return "unknown", "answer not read: outcome unknown", ()
    if call.route == "json2":
        return "done", "", _created_ids(call, body)
    if isinstance(body, dict) and body.get("error"):
        error = body["error"]
        name = (error.get("data") or {}).get("name") if isinstance(error, dict) else ""
        return "failed", f"Odoo refused the call: {name or 'error'}", ()
    if isinstance(body, dict) and "result" in body:
        return "done", "", _created_ids(call, body["result"])
    if call.route == "website_form" and isinstance(body, dict) and isinstance(body.get("id"), int):
        return "done", "", (body["id"],)
    return "unknown", "answer not read: outcome unknown", ()
