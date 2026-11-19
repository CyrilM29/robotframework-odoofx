"""HTTP requests on a session of `OdooFxLibrary`, the request keywords of RequestsLibrary absorbed.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/RequestsOnSessionKeywords.py``,
``RequestsKeywords.py`` and ``SessionKeywords.py``, MIT License, Copyright (c) 2016 Bulkan Evcimen),
rewritten. Names and parameters are the upstream's (the absorbed surface), and so are the status check
and the redirect defaults (followed, except by HEAD). Three changes: an expected status may be given as
a number; a Robot ``Secret`` given in ``json``, ``data``, ``params``, ``headers``, ``cookies`` or ``auth``
of a request, at any depth of their dictionaries, lists and tuples, is revealed only when the request is
sent (Robot's own TRACE log then shows ``<secret>``), never in ``files`` or the URL, and its value is
masked in the log and the failure messages wherever it appears; and the URL
that a status failure, a connection error or a timeout names is masked like the log; and a file given as
the body is closed even when the request fails. One addition, proper
to Odoo: the write guard of ``http_odoo_write_guard.py`` (a write through Odoo's RPC routes passes the
lock of the proven connection, the write journal, and is sent once).

The upstream warned when the URL was not passed by position (an ``=`` in it read by Robot as a named
argument); that warning is not kept: Robot reads the real signature here and refuses the call before
anything is sent (``expected 2 to 5 non-named arguments, got 1``). Escape the ``=`` (``\\=``), pass
``url=`` by name, or give the query string in ``params``.
"""

from contextlib import contextmanager
from typing import Any, Iterator, Optional
from urllib.parse import urljoin, urlsplit

import requests
from requests.status_codes import codes
from robot.api import logger
from robot.api.deco import keyword
from robot.api.types import Secret

from .http_log import masked_message, masked_secrets, masked_url, request_lines, response_lines
from .http_odoo_write_guard import (OdooRpcCall, is_odoo_read_call, read_odoo_rpc_call, read_write_outcome,
                                    refusal_of)
from .rpc import OdooRpcError

ANY_STATUS = ("any", "anything")
REVEALED_ARGUMENTS = ("json", "data", "params", "headers", "cookies", "auth")


def revealed(value: Any, found: Optional[set] = None) -> Any:
    """``value`` with every Robot ``Secret`` replaced by its value, at any depth of dicts, lists and tuples.

    The values revealed are added to ``found``, so that the log and the failure messages mask them.
    """
    if isinstance(value, Secret):
        if found is not None and value.value:
            found.add(str(value.value))
        return value.value
    if isinstance(value, dict):
        return {key: revealed(item, found) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(revealed(item, found) for item in value)
    return value


def joined_url(base: str, url: str) -> str:
    """``url`` joined to the session's ``base``, a full URL in ``url`` winning (as upstream)."""
    if base and url and not base.endswith("/"):
        base += "/"
    if base and url and url.startswith("/"):
        url = url[1:]
    return urljoin(base, url)


def status_code_of(expected: Any) -> Optional[int]:
    """The status code ``expected`` names, None for ``any``; a code, its text or its name (``Not Found``)."""
    if isinstance(expected, bool) or not isinstance(expected, (int, str)):
        raise ValueError(f"Invalid expected status {expected!r}: a status code, its name, or any")
    if isinstance(expected, int):
        return expected
    if expected.strip().lower() in ANY_STATUS:
        return None
    try:
        return int(expected)
    except ValueError:
        code = codes.get(expected.strip().lower().replace(" ", "_"))
    if code is None:
        raise ValueError(f"Unknown named status {expected!r}")
    return code


def check_status(expected: Any, response: requests.Response, msg: Optional[str] = None) -> None:
    """Fail unless ``response`` has the ``expected`` status; without one, fail on a 4xx or 5xx (as upstream)."""
    secrets = getattr(response, "odoofx_secrets", ())
    if expected is None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(masked_secrets(str(exc).replace(str(response.url), str(masked_url(response.url))),
                                                    secrets), response=response) from None
        return
    code = status_code_of(expected)
    if code is not None and response.status_code != code:
        prefix = f"{msg} " if msg else ""
        raise AssertionError(masked_secrets(f"{prefix}Url: {masked_url(response.url)} Expected status: "
                                            f"{response.status_code} != {code}", secrets))


def timeout_of(timeout: Any) -> Any:
    if timeout is None:
        return None
    if isinstance(timeout, (tuple, list)):
        return float(timeout[0]), float(timeout[1])
    return float(timeout)


@contextmanager
def sent_once(session: Optional[requests.Session], url: str) -> Iterator[None]:
    """``session`` sends to the origin of ``url`` with no retry for the time of the block: a write is sent once.

    A request without a session goes through requests' own session, which retries nothing.
    """
    if session is None:
        yield
        return
    parts = urlsplit(url)
    prefix = f"{parts.scheme}://{parts.netloc}/"
    previous = session.adapters.get(prefix)
    session.mount(prefix, requests.adapters.HTTPAdapter(max_retries=0))
    try:
        yield
    finally:
        session.adapters.pop(prefix).close()
        if previous is not None:
            session.mount(prefix, previous)


def database_header_of(session: Optional[requests.Session], headers: Any) -> str:
    """The ``X-Odoo-Database`` header a request sends, its own winning over its session's, or ``""``."""
    for source in (headers, session.headers if session is not None else None):
        for name, value in (source or {}).items():
            if str(name).lower() == "x-odoo-database" and value is not None:
                return str(value)
    return ""


def never_reached(exc: requests.RequestException) -> bool:
    """True when the request never reached the server, so that its write did not run."""
    if isinstance(exc, (requests.ConnectTimeout, requests.exceptions.InvalidURL, requests.exceptions.MissingSchema,
                        requests.exceptions.InvalidSchema)):
        return True
    return isinstance(exc, requests.ConnectionError) and "NewConnectionError" in repr(exc)


class OdooHttpRequestKeywords:
    """The requests on a session of `OdooFxLibrary` (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS), mixed into it."""

    def _request_on_session(self, method: str, alias: str, url: str, expected_status: Any, msg: Any,
                            **kwargs: Any) -> requests.Response:
        self._last_http_response = None
        response = self._send_http(method, self._http_session(alias), url, **kwargs)
        check_status(expected_status, response, msg)
        return response

    def _plan_odoo_http_write(self, call: OdooRpcCall, method: str, target: str) -> dict:
        connection = self._info if getattr(self, "_channel", None) is not None else None
        refusal = refusal_of(call, method, target, connection)
        if refusal:
            raise OdooRpcError(refusal)
        entry = {"seq": len(self._journal) + 1, "phase": "planned", "operation": "call", "channel": "http",
                 "route": call.route, "database": connection["database"], "model": call.model,
                 "method": call.method, "ids": list(call.ids), "fields": list(call.fields)}
        self._journal.append(entry)
        logger.info(f"write {entry['seq']} planned: call {call.model} {call.method} over HTTP "
                    f"{method.upper()} {call.route} {entry['ids']}")
        return entry

    @staticmethod
    def _settle_http_write(entry: dict, phase: str, error: str = "", created: tuple = ()) -> None:
        entry["phase"] = phase
        if error:
            entry["error"] = error
        if created:
            entry["ids"] = list(created)
        logger.info(f"write {entry['seq']} {phase}{': ' + error if error else ''}")

    def _send_http(self, method: str, session: Optional[requests.Session], url: str,
                   **kwargs: Any) -> requests.Response:
        self._last_http_response = None
        try:
            return self._send_http_once(method, session, url, kwargs)
        finally:
            for sent in list((kwargs.get("files") or {}).values()) + [kwargs.get("data")]:
                if hasattr(sent, "close") and hasattr(sent, "read"):
                    sent.close()

    def _send_http_once(self, method: str, session: Optional[requests.Session], url: str,
                        kwargs: dict) -> requests.Response:
        timeout = kwargs.pop("timeout", None)
        if timeout is None and session is not None:
            timeout = session.odoofx_timeout
        secrets = set(getattr(session, "odoofx_secrets", ()))
        cookies = revealed(kwargs.pop("cookies", session.odoofx_cookies if session is not None else None), secrets)
        for name in REVEALED_ARGUMENTS:
            if name in kwargs:
                kwargs[name] = revealed(kwargs[name], secrets)
        sender = getattr(session, method) if session is not None else getattr(requests, method)
        target = joined_url(session.url if session is not None else "", url)
        call = read_odoo_rpc_call(target, kwargs.get("json"), kwargs.get("data"),
                                  database_header_of(session, kwargs.get("headers")))
        entry = None
        if call is not None and not is_odoo_read_call(call):
            entry = self._plan_odoo_http_write(call, method, target)
            kwargs["allow_redirects"] = False
        try:
            with sent_once(session if entry is not None else None, target):
                response = sender(target, timeout=timeout_of(timeout), cookies=cookies, **kwargs)
        except requests.RequestException as exc:
            sent = getattr(exc.request, "url", None) or target
            message = masked_secrets(masked_message(masked_message(str(exc), sent), target), secrets)
            if entry is not None:
                self._settle_http_write(entry, "failed" if never_reached(exc) else "unknown",
                                        f"{type(exc).__name__}: {message}"[:300])
            raise type(exc)(message, request=exc.request, response=exc.response) from None
        if entry is not None:
            self._settle_http_write(entry, *read_write_outcome(call, response.status_code, response.content))
        response.odoofx_secrets = frozenset(secrets)
        logger.info(masked_secrets(request_lines(response, secrets), secrets))
        logger.info(masked_secrets(response_lines(response, secrets), secrets))
        self._last_http_response = response
        return response

    @keyword("Get File For Streaming Upload")
    def get_file_for_streaming_upload(self, path):
        """Open the file at ``path`` in binary mode and return it, to send as the ``data`` of a request.

        The file is streamed, never read into memory. A request keyword closes
        it once the request is sent, and also when the request fails or is
        refused (the upstream closed it after a successful send only).

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${upload}=    `Get File For Streaming Upload`    tests/data/http/streaming-upload-probe.txt
        | `POST On Session`    anonymous    /web/login    data=${upload}    expected_status=400
        | Should Be True    $upload.closed
        """
        return open(path, "rb")

    @keyword("GET On Session")
    def get_on_session(self, alias, url, params=None, expected_status=None, msg=None, **kwargs):
        """Send a GET request on the session named ``alias`` and return the response.

        ``url`` is joined to the session's URL (a full URL replaces it);
        ``params`` is the query string, as a dictionary, a list of pairs or a
        string. Without ``expected_status`` the keyword fails on a 4xx or 5xx
        status; ``expected_status`` names the status the response must have
        (``200``, ``${404}``, ``Not Found``), ``any`` accepts every status, and
        ``msg`` opens the failure message. Other requests arguments
        (``headers``, ``cookies``, ``timeout``, ``allow_redirects``...) go by
        name. A redirect is followed, as upstream: an Odoo route that sends an
        anonymous visitor to ``/web/login`` answers 200 with the login page.
        A write on Odoo is guarded as by `POST On Session`: Odoo runs a call of
        ``call_kw`` by GET too.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${page}=    `GET On Session`    anonymous    /web/login
        | Should Be Equal As Integers    ${page.status_code}    200
        | `GET On Session`    anonymous    /web/content/res.users/2/image_128    expected_status=404
        """
        return self._request_on_session("get", alias, url, expected_status, msg, params=params, **kwargs)

    @keyword("POST On Session")
    def post_on_session(self, alias, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a POST request on the session named ``alias`` and return the response.

        ``data`` is a form (a dictionary or pairs), bytes or a file; ``json`` a
        value sent as a JSON body. The status is checked as by `GET On Session`.
        Odoo's JSON-RPC routes answer an error with status 200: the error is in
        the body (``error.data.name``), which the status check does not read.

        A write on Odoo is guarded, whatever the verb: a call of its RPC routes
        (``/web/dataset/call_kw``, ``call_button``, ``resequence``,
        ``/json/2/...``, ``/xmlrpc/2/object``, ``/jsonrpc``) or a website form,
        read from the body (Odoo ignores the model and method of the path of
        ``call_kw``), whose method is not a read (``search_read``, ``read``,
        ``search_count``...: an unknown method counts as a write), on any host.
        It is refused before anything is sent unless `Connect To Odoo` proved
        that target, by the same origin (the path normalized first) and the
        same database when the call names one (an XML-RPC or ``/jsonrpc``
        body, the ``X-Odoo-Database`` header of JSON-2; the database of a web
        session is not read), and opened it with
        ``allow_write=${TRUE}`` (``Not connected``, ``not the proven target``,
        ``not the proven database``, ``Writes are off``); a write by HEAD, the
        database service but ``list``, and the database manager are never
        sent. A gateway status (502, 503, 504) leaves the outcome unknown. An accepted write
        enters `Get Odoo Write Journal` (channel ``http``), is sent once, with
        no retry and no redirect followed, and its outcome is read in the
        answer (``done``, ``failed``, ``unknown`` to reconcile by reading).
        Every other request keeps the behaviour of RequestsLibrary. The guard
        is a net against an accident (a wrong target, a forgotten write, a
        double send), not a security boundary: Odoo's access rights stay the
        control on the server.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${session_info}=    `POST On Session`    anonymous    /web/session/get_session_info
        | ...    json=${{{"jsonrpc": "2.0", "method": "call", "params": {}}}}
        | Should Be Equal As Integers    ${session_info.status_code}    200
        | Should Be Equal    ${session_info.json()}[error][data][name]    odoo.http.SessionExpiredException
        | `Disconnect From Odoo`
        | Run Keyword And Expect Error    GLOB:*Not connected: call Connect To Odoo first*
        | ...    `POST On Session`    anonymous    /web/dataset/call_kw
        | ...    json=${{{"jsonrpc": "2.0", "method": "call", "params": {"model": "res.partner", "method": "create", "args": [{"name": "ODOOFX-GARDE16"}], "kwargs": {}}}}}
        """
        return self._request_on_session("post", alias, url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("PUT On Session")
    def put_on_session(self, alias, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a PUT request on the session named ``alias`` and return the response.

        ``data`` and ``json`` are the body, as for `POST On Session`; the
        status is checked as by `GET On Session`. Odoo's web routes refuse a
        PUT they do not declare with status 400.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${put}=    `PUT On Session`    anonymous    /web/login    json=${{{"odoofx_probe": "lot2"}}}    expected_status=400
        | Should Be Equal    ${put.request.method}    PUT
        """
        return self._request_on_session("put", alias, url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("PATCH On Session")
    def patch_on_session(self, alias, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a PATCH request on the session named ``alias`` and return the response.

        ``data`` and ``json`` are the body, as for `POST On Session`; the
        status is checked as by `GET On Session`.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${patch}=    `PATCH On Session`    anonymous    /web/session/get_session_info
        | ...    json=${{{"jsonrpc": "2.0", "method": "call", "params": {}}}}
        | Should Be Equal    ${patch.json()}[error][data][name]    odoo.http.SessionExpiredException
        """
        return self._request_on_session("patch", alias, url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("DELETE On Session")
    def delete_on_session(self, alias, url, expected_status=None, msg=None, **kwargs):
        """Send a DELETE request on the session named ``alias`` and return the response.

        A body, when the route wants one, goes by name (``data=``, ``json=``);
        the status is checked as by `GET On Session`.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${delete}=    `DELETE On Session`    anonymous    /web/login    expected_status=400
        | Should Be Equal    ${delete.request.method}    DELETE
        """
        return self._request_on_session("delete", alias, url, expected_status, msg, **kwargs)

    @keyword("HEAD On Session")
    def head_on_session(self, alias, url, expected_status=None, msg=None, **kwargs):
        """Send a HEAD request on the session named ``alias`` and return the response, which has no body.

        Unlike the other verbs, a redirect is NOT followed unless
        ``allow_redirects=${TRUE}`` (as upstream): an Odoo route that sends an
        anonymous visitor to ``/web/login`` answers its 303 and its
        ``Location``. The status is checked as by `GET On Session`, a 3xx
        being no failure. A write on Odoo is never sent by HEAD (Odoo would run
        it, and an answer without a body cannot tell its outcome).

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${kept}=    `HEAD On Session`    anonymous    /web
        | Should Be Equal As Integers    ${kept.status_code}    303
        | Should Contain    ${kept.headers}[Location]    /web/login
        """
        return self._request_on_session("head", alias, url, expected_status, msg, **kwargs)

    @keyword("OPTIONS On Session")
    def options_on_session(self, alias, url, expected_status=None, msg=None, **kwargs):
        """Send an OPTIONS request on the session named ``alias`` and return the response.

        A redirect is followed, as by `GET On Session`; the status is checked
        the same way. A write on Odoo is guarded as by `POST On Session`: Odoo
        runs a call of ``call_kw`` and of XML-RPC by OPTIONS too.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${followed}=    `OPTIONS On Session`    anonymous    /web
        | Should Be Equal As Integers    ${followed.history[0].status_code}    303
        | Should Be Equal    ${followed.history[0].request.method}    OPTIONS
        """
        return self._request_on_session("options", alias, url, expected_status, msg, **kwargs)
