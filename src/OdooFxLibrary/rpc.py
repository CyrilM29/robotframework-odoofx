"""RPC channels to an Odoo server: XML-RPC (14 to 18) and JSON-2 (19 and later).

Both channels expose the same three read operations, so a keyword never
depends on the wire protocol. Secrets stay private to the channel objects and
never appear in an error message or a ``repr``.
"""

from __future__ import annotations

import re
import xmlrpc.client
from collections.abc import Mapping
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import requests

TIMEOUT = 30
ERROR_LIMIT = 300
JSON2_FIRST_SERIES = 19
GATEWAY_ERRORS = (502, 503, 504)
NONE_RESULT = "cannot marshal None"
CHANNELS = ("auto", "xmlrpc", "json2")


class OdooRpcError(RuntimeError):
    """A failure talking to Odoo, worded on one short line.

    ``unknown_outcome`` is true when the request may have reached the server
    without an answer (timeout, dropped connection, gateway error): a write
    that fails this way is reconciled by reading, never sent again."""

    def __init__(self, message: str, unknown_outcome: bool = False):
        super().__init__(message)
        self.unknown_outcome = unknown_outcome


def compact(text: object, limit: int = ERROR_LIMIT) -> str:
    """The last non-empty line of a server message, cut to ``limit`` characters.

    Odoo answers an error with a whole Python traceback whose useful part is
    its last line."""
    lines = [line.strip() for line in str(text).strip().splitlines() if line.strip()]
    last = lines[-1] if lines else ""
    return last if len(last) <= limit else last[:limit] + "..."


def series_of(server_version: str) -> int:
    """Major series of a ``server_version`` (``16.0-20250909`` gives 16, ``saas~17.2`` gives 17)."""
    match = re.search(r"(\d+)\.\d+", str(server_version))
    if match is None:
        raise OdooRpcError(f"Unrecognised Odoo server version: {server_version!r}")
    return int(match.group(1))


def detect_version(url: str) -> str:
    """The ``server_version`` of the server at ``url``, without authentication.

    ``/web/version`` exists from Odoo 19 and avoids the deprecated XML-RPC
    endpoints; ``common.version`` answers on every earlier version."""
    try:
        reply = requests.get(f"{url}/web/version", timeout=TIMEOUT)
        if reply.status_code == 200:
            return str(reply.json()["version"])
    except (requests.RequestException, ValueError, KeyError):
        pass
    try:
        return str(xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").version()["server_version"])
    except (OSError, xmlrpc.client.Error, KeyError) as exc:
        raise OdooRpcError(f"Cannot read the Odoo version at {url}: {compact(exc)}") from None


def choose_channel(requested: str, series: int) -> str:
    if requested not in CHANNELS:
        raise OdooRpcError(f"Unknown channel {requested!r}, expected one of {CHANNELS}")
    if requested == "auto":
        return "json2" if series >= JSON2_FIRST_SERIES else "xmlrpc"
    return requested


def plain(value: Any) -> Any:
    """``value`` with plain dicts and lists only.

    Robot Framework hands a ``DotDict`` to a keyword that received a
    ``Create Dictionary``: a dict subclass the XML-RPC marshaller refuses."""
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def _context(context: Optional[dict]) -> dict:
    return plain(context) if context else {}


#: Odoo's XML-RPC fault codes that stand for an exception family: the fault string
#: is then the bare message, without the exception's name. Any other exception comes
#: with its traceback, whose last line names it.
_FAULT_FAMILIES = {
    2: "odoo.exceptions.UserError",
    3: "odoo.exceptions.AccessDenied",
    4: "odoo.exceptions.AccessError",
}


def _fault_text(fault: xmlrpc.client.Fault) -> str:
    """The fault as one line that names the Odoo exception (its family for a coded fault).

    JSON-2 names the exact class (``ValidationError`` for a validation); XML-RPC only
    gives the family of a coded fault (``UserError`` for both)."""
    text = compact(fault.faultString)
    family = _FAULT_FAMILIES.get(fault.faultCode)
    return f"{family}: {text}" if family and family not in text else text


def server_time(url: str) -> str:
    """The server's clock as an Odoo datetime string (UTC, one second).

    Read from the HTTP ``Date`` header of the login page: no authentication, and
    the only clock a client can trust to bracket what it created."""
    try:
        reply = requests.get(f"{url}/web/login", timeout=TIMEOUT)
        stamp = parsedate_to_datetime(reply.headers["Date"])
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise OdooRpcError(f"Cannot read the server time at {url}: {compact(exc)}") from None
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _send_once(base):
    """A transport that never replays a request.

    The standard transport silently sends a request again, once, when the
    connection drops before the answer: harmless for a read, but a write could
    then run twice (a duplicated ``create``)."""

    class SendOnce(base):
        def request(self, host, handler, request_body, verbose=False):
            return self.single_request(host, handler, request_body, verbose)

    return SendOnce()


def _write_proxy(url: str) -> xmlrpc.client.ServerProxy:
    base = xmlrpc.client.SafeTransport if url.startswith("https") else xmlrpc.client.Transport
    return xmlrpc.client.ServerProxy(url, transport=_send_once(base), allow_none=True)


class XmlRpcChannel:
    """``execute_kw`` over ``/xmlrpc/2``. Deprecated by Odoo 19, removal announced for 22."""

    name = "xmlrpc"

    def __init__(self, url: str, database: str, login: str, password: str):
        self._database = database
        self._password = password
        try:
            common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
            self.uid = common.authenticate(database, login, password, {})
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooRpcError(f"XML-RPC authentication call failed: {compact(exc)}") from None
        if not self.uid:
            raise OdooRpcError(
                f"Authentication refused for login {login!r} on database {database!r}")
        self._object = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self._object_once = _write_proxy(f"{url}/xmlrpc/2/object")

    def __repr__(self) -> str:
        return f"XmlRpcChannel(database={self._database!r}, uid={self.uid})"

    def _call(self, model: str, method: str, args: list, kwargs: dict,
              write: bool = False) -> Any:
        proxy = self._object_once if write else self._object
        try:
            return proxy.execute_kw(
                self._database, self.uid, self._password, model, method,
                plain(args), plain(kwargs))
        except xmlrpc.client.Fault as exc:
            if NONE_RESULT in exc.faultString:
                raise OdooRpcError(
                    f"{model}.{method} ran on the server but its None result cannot be sent "
                    "over XML-RPC (an Odoo limitation): read the record to see the effect",
                    unknown_outcome=True) from None
            raise OdooRpcError(f"{model}.{method} failed: {_fault_text(exc)}") from None
        except TypeError as exc:
            raise OdooRpcError(f"{model}.{method} arguments cannot be encoded: {compact(exc)}") from None
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooRpcError(f"{model}.{method} unreachable: {compact(exc)}",
                               unknown_outcome=True) from None

    def search_count(self, model: str, domain: list, context: Optional[dict] = None) -> int:
        return self._call(model, "search_count", [domain], {"context": _context(context)})

    def search_read(self, model: str, domain: list, fields: Optional[list] = None,
                    limit: int = 0, offset: int = 0, order: str = "",
                    context: Optional[dict] = None) -> list:
        kwargs: dict = {"context": _context(context)}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return self._call(model, "search_read", [domain], kwargs)

    def fields_get(self, model: str, attributes: Optional[list] = None,
                   context: Optional[dict] = None) -> dict:
        kwargs: dict = {"context": _context(context)}
        if attributes:
            kwargs["attributes"] = attributes
        return self._call(model, "fields_get", [], kwargs)

    def create(self, model: str, values: dict, context: Optional[dict] = None) -> int:
        return self._call(model, "create", [values], {"context": _context(context)}, write=True)

    def write(self, model: str, ids: list, values: dict, context: Optional[dict] = None) -> bool:
        return self._call(model, "write", [ids, values], {"context": _context(context)},
                          write=True)

    def unlink(self, model: str, ids: list, context: Optional[dict] = None) -> bool:
        return self._call(model, "unlink", [ids], {"context": _context(context)}, write=True)

    def call(self, model: str, method: str, ids: list, kwargs: Optional[dict] = None,
             context: Optional[dict] = None) -> Any:
        return self._call(model, method, [ids], {**(kwargs or {}), "context": _context(context)},
                          write=True)

    def call_model(self, model: str, method: str, kwargs: Optional[dict] = None,
                   context: Optional[dict] = None, write: bool = False) -> Any:
        # No positional argument at all: a list of ids would land on the method's
        # first parameter (name_search received it as its name).
        return self._call(model, method, [], {**(kwargs or {}), "context": _context(context)},
                          write=write)

    def close(self) -> None:
        self._object("close")()
        self._object_once("close")()


class Json2Channel:
    """``POST /json/2/<model>/<method>`` with a ``Bearer`` API key (Odoo 19 and later).

    Arguments go by name; the answer is the method's return value, errors are
    HTTP statuses."""

    name = "json2"

    def __init__(self, url: str, database: str, api_key: str):
        self._url = url
        self._database = database
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"
        if database:
            self._session.headers["X-Odoo-Database"] = database
        self.uid = self._call("res.users", "context_get", {}).get("uid")

    def __repr__(self) -> str:
        return f"Json2Channel(database={self._database!r}, uid={self.uid})"

    def _call(self, model: str, method: str, payload: dict) -> Any:
        try:
            reply = self._session.post(
                f"{self._url}/json/2/{model}/{method}", json=plain(payload), timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise OdooRpcError(f"{model}.{method} unreachable: {compact(exc)}",
                               unknown_outcome=True) from None
        if reply.status_code != 200:
            raise OdooRpcError(
                f"{model}.{method} answered HTTP {reply.status_code}: {self._message(reply)}",
                unknown_outcome=reply.status_code in GATEWAY_ERRORS)
        return reply.json()

    @staticmethod
    def _message(reply: requests.Response) -> str:
        try:
            body = reply.json()
            message = compact(body.get("message") or reply.reason)
            name = body.get("name")
            return f"{name}: {message}" if name else message
        except (ValueError, AttributeError):
            return compact(reply.reason or reply.text)

    def search_count(self, model: str, domain: list, context: Optional[dict] = None) -> int:
        return self._call(model, "search_count",
                          {"domain": domain, "context": _context(context)})

    def search_read(self, model: str, domain: list, fields: Optional[list] = None,
                    limit: int = 0, offset: int = 0, order: str = "",
                    context: Optional[dict] = None) -> list:
        payload: dict = {"domain": domain, "context": _context(context)}
        if fields:
            payload["fields"] = fields
        if limit:
            payload["limit"] = limit
        if offset:
            payload["offset"] = offset
        if order:
            payload["order"] = order
        return self._call(model, "search_read", payload)

    def fields_get(self, model: str, attributes: Optional[list] = None,
                   context: Optional[dict] = None) -> dict:
        payload: dict = {"context": _context(context)}
        if attributes:
            payload["attributes"] = attributes
        return self._call(model, "fields_get", payload)

    def create(self, model: str, values: dict, context: Optional[dict] = None) -> int:
        created = self._call(model, "create",
                             {"vals_list": [values], "context": _context(context)})
        return created[0] if isinstance(created, list) else created

    def write(self, model: str, ids: list, values: dict, context: Optional[dict] = None) -> bool:
        return self._call(model, "write",
                          {"ids": ids, "vals": values, "context": _context(context)})

    def unlink(self, model: str, ids: list, context: Optional[dict] = None) -> bool:
        return self._call(model, "unlink", {"ids": ids, "context": _context(context)})

    def call(self, model: str, method: str, ids: list, kwargs: Optional[dict] = None,
             context: Optional[dict] = None) -> Any:
        return self._call(model, method,
                          {**(kwargs or {}), "ids": ids, "context": _context(context)})

    def call_model(self, model: str, method: str, kwargs: Optional[dict] = None,
                   context: Optional[dict] = None, write: bool = False) -> Any:
        return self._call(model, method, {**(kwargs or {}), "context": _context(context)})

    def close(self) -> None:
        self._session.close()


def open_channel(url: str, database: str, login: str, secret: str, channel: str):
    """The channel named by ``channel`` (resolved against the server version by the caller)."""
    if channel == "json2":
        return Json2Channel(url, database, secret)
    return XmlRpcChannel(url, database, login, secret)
