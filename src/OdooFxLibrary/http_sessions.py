"""HTTP sessions of `OdooFxLibrary`, the session keywords of RequestsLibrary absorbed.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/SessionKeywords.py``, MIT License,
Copyright (c) 2016 Bulkan Evcimen), rewritten. The keyword names, the order, names and defaults of
their parameters are those of the upstream (``tests/data/requestslibrary-0.9.7-surface.json``), so a
suite written for RequestsLibrary keeps working; they are the absorbed surface, outside the naming
rule of the library's own keywords. What changed: the timeout and cookies of a session belong to that
session (the upstream kept the last session's on the library, for every session and every request
without a session), a Robot ``Secret`` is accepted in ``headers`` and ``auth``, and the log masks the
secrets it recognizes (``http_log.py``).
"""

import logging
import warnings
from collections.abc import Mapping
from http.cookiejar import CookieJar
from typing import Any, Optional

import requests
from requests.cookies import merge_cookies
from requests.sessions import merge_setting
from robot.api import logger
from robot.api.deco import keyword
from robot.utils import ConnectionCache
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

from .http_log import masked_headers, masked_url
from .http_requests import revealed

DEFAULT_RETRY_METHOD_LIST = sorted(Retry.DEFAULT_ALLOWED_METHODS)
NO_SESSION = "No sessions created"
QUIET_LOGGERS = ("requests", "urllib3")
TRUE_TEXTS = ("true", "yes", "on", "1")
FALSE_TEXTS = ("false", "no", "off", "0", "")


def verify_of(verify: Any) -> Any:
    """``verify`` as requests wants it: a boolean, or the path of a CA bundle."""
    if isinstance(verify, str) and verify.strip().lower() in TRUE_TEXTS + FALSE_TEXTS:
        return verify.strip().lower() in TRUE_TEXTS
    return verify


def cookies_of(cookies: Any) -> Any:
    """The cookies a session sends: a mapping copied, a cookie jar kept as given (its domains and paths with it)."""
    if not cookies:
        return None
    if isinstance(cookies, Mapping) and not isinstance(cookies, CookieJar):
        return dict(cookies)
    return cookies


def cookies_merged(jar: CookieJar, cookies: Any) -> CookieJar:
    """``jar`` with ``cookies`` merged in: a cookie given by name replaces every cookie of that name in the jar."""
    if isinstance(cookies, Mapping) and not isinstance(cookies, CookieJar):
        for cookie in [cookie for cookie in jar if cookie.name in cookies]:
            jar.clear(cookie.domain, cookie.path, cookie.name)
        for name, value in cookies.items():
            jar.set_cookie(requests.cookies.create_cookie(name, value))
        return jar
    return merge_cookies(jar, cookies)


def retry_of(max_retries: Any, backoff_factor: Any, retry_status_list: Any,
             retry_method_list: Any) -> Optional[Retry]:
    """The retry policy of a session, or None when ``max_retries`` is 0."""
    try:
        total = int(max_retries)
        statuses = [int(status) for status in retry_status_list] if retry_status_list else None
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Error converting session parameter: {exc}") from None
    if total <= 0:
        return None
    return Retry(total=total, backoff_factor=float(backoff_factor), status_forcelist=statuses,
                 allowed_methods=list(retry_method_list) if retry_method_list else None)


class OdooHttpSessionKeywords:
    """The HTTP sessions of `OdooFxLibrary`, mixed into it: created, found by alias, updated, closed."""

    def _http_sessions(self) -> ConnectionCache:
        cache = getattr(self, "_http_session_cache", None)
        if cache is None:
            cache = self._http_session_cache = ConnectionCache(NO_SESSION)
        return cache

    def _http_session(self, alias: str) -> requests.Session:
        return self._http_sessions().switch(alias)

    def _register_http_session(self, alias: str, url: str, **settings: Any) -> requests.Session:
        session = self._build_http_session(url, **settings)
        self._http_sessions().register(session, alias=alias)
        return session

    @staticmethod
    def _build_http_session(url: str, headers: Any = None, cookies: Any = None,
                            auth: Any = None, timeout: Any = None, proxies: Any = None,
                            verify: Any = False, max_retries: Any = 3, backoff_factor: Any = 0.10,
                            disable_warnings: Any = 0, retry_status_list: Any = None,
                            retry_method_list: Any = None) -> requests.Session:
        session = requests.Session()
        session.headers.update(dict(headers or {}))
        if auth:
            session.auth = auth
        if proxies:
            session.proxies = dict(proxies)
        retry = retry_of(max_retries, backoff_factor, retry_status_list,
                         DEFAULT_RETRY_METHOD_LIST if retry_method_list is None else retry_method_list)
        if retry is not None:
            for prefix in ("http://", "https://"):
                session.mount(prefix, requests.adapters.HTTPAdapter(max_retries=retry))
        session.verify = verify_of(verify)
        if disable_warnings:
            for name in QUIET_LOGGERS:
                logging.getLogger(name).setLevel(logging.ERROR)
            if session.verify is False:
                warnings.simplefilter("ignore", InsecureRequestWarning)
        session.url = url
        session.odoofx_secrets = set()
        session.odoofx_timeout = timeout
        session.odoofx_cookies = cookies_of(cookies)
        return session

    @keyword("Create Session")
    def create_session(self, alias, url, headers={}, cookies={}, auth=None, timeout=None, proxies=None,
                       verify=False, debug=0, max_retries=3, backoff_factor=0.10, disable_warnings=0,
                       retry_status_list=[], retry_method_list=DEFAULT_RETRY_METHOD_LIST):
        """Create an HTTP session to ``url`` and name it ``alias`` for the ``... On Session`` keywords.

        The arguments are those of RequestsLibrary's keyword of the same name.
        ``headers`` and ``cookies`` are sent with every request of the session;
        ``auth`` is a user name and a password for HTTP Basic authentication;
        ``timeout`` is the default timeout of the session's requests (seconds,
        or a connect and read pair); ``verify`` checks the server's TLS
        certificate (``True``, ``False``, or the path of a CA bundle; ``False``
        by default, as upstream); ``max_retries``, ``backoff_factor``,
        ``retry_status_list`` and ``retry_method_list`` retry a request whose
        connection failed (POST is not retried by default: it may write twice);
        ``disable_warnings`` silences the logs of requests and urllib3 below
        ERROR and the warning of an unverified certificate; unlike upstream, it
        leaves Python's root logger alone (a change for the whole process).
        ``debug`` is accepted for compatibility and changes nothing, a reduction
        made on purpose: the raw exchange it dumped upstream carried every
        secret in clear; the log of each request already shows its headers and
        body, the secrets it recognizes masked.

        Unlike upstream, the timeout and cookies belong to this session only,
        and a value of ``headers`` or an element of ``auth`` may be a Robot
        ``Secret`` (a token, a password): it is revealed into the session
        (the ``requests.Session`` returned holds it), never into a log: the
        log of the creation shows ``<secret>``, and the log and the failure
        messages of every request of the session mask its value wherever it
        appears. Returns the session (a ``requests.Session``).

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${page}=    `GET On Session`    anonymous    /web/login
        | Should Be Equal As Integers    ${page.status_code}    200
        | `Create Session`    probe-header    http://127.0.0.1:8016
        | ...    headers=${{{"X-Odoofx-Probe": robot.api.types.Secret("lot2")}}}
        | ${with_header}=    `GET On Session`    probe-header    /web/login
        | Should Be Equal    ${with_header.request.headers}[X-Odoofx-Probe]    lot2
        """
        logger.info(f"Creating session {alias}: url={masked_url(url)}, headers={masked_headers(headers)}, "
                    f"timeout={timeout}, verify={verify}")
        secrets = set()
        session = self._register_http_session(
            alias, url, headers=revealed(headers, secrets), cookies=cookies,
            auth=requests.auth.HTTPBasicAuth(*revealed(auth, secrets)) if auth else None, timeout=timeout,
            proxies=proxies,
            verify=verify, max_retries=max_retries, backoff_factor=backoff_factor,
            disable_warnings=disable_warnings, retry_status_list=retry_status_list,
            retry_method_list=retry_method_list)
        session.odoofx_secrets.update(secrets)
        return session

    @keyword("Update Session")
    def update_session(self, alias, headers=None, cookies=None):
        """Merge ``headers`` and ``cookies`` into those of the session named ``alias``.

        A header or a cookie of the same name is replaced, whatever the domain
        the server gave that cookie: lending a ``session_id`` to a session that
        already holds the anonymous one Odoo sets on its pages makes it send
        the lent one. Unlike upstream, which kept a cookie already in the
        session (``requests.cookies.merge_cookies`` never overwrites a name), so
        that the update was ignored without a word. A cookie jar is merged by
        domain and path. A value may be a Robot ``Secret`` (a session cookie, a
        token): it is revealed into the session only, and masked in the log
        of its requests wherever it appears.

        Example:
        | `Create Session`    borrowing    http://127.0.0.1:8016
        | `GET On Session`    borrowing    /web/login
        | `Update Session`    borrowing
        | ...    cookies=${{{"session_id": robot.api.types.Secret($logged.cookies["session_id"])}}}
        | ${borrowed}=    `GET On Session`    borrowing    /web/content/res.users/2/image_128
        | Should Be Equal As Integers    ${borrowed.status_code}    200
        """
        session = self._http_session(alias)
        secrets = set()
        session.headers = merge_setting(revealed(headers, secrets), session.headers)
        session.cookies = cookies_merged(session.cookies, revealed(cookies, secrets))
        session.odoofx_secrets = getattr(session, "odoofx_secrets", set()) | secrets

    @keyword("Session Exists")
    def session_exists(self, alias):
        """Return whether a session named ``alias`` has been created and not deleted.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${exists}=    `Session Exists`    anonymous
        | Should Be True    $exists is True
        | ${never}=    `Session Exists`    never-created
        | Should Be True    $never is False
        """
        try:
            self._http_sessions().get_connection(alias)
            return True
        except RuntimeError:
            return False

    @keyword("Delete All Sessions")
    def delete_all_sessions(self):
        """Close every HTTP session of the library; their aliases no longer exist, and no last response stays.

        Unlike upstream, the last response is cleared too (decision of the owner
        of 2026-11-07): under one library instance shared by several missions,
        `Status Should Be` without a response judged a response another target
        had given.

        A web session of Odoo opened by `Create Odoo Http Session` is closed on
        the client side; Odoo lets the server-side session expire by itself.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | `Delete All Sessions`
        | ${exists}=    `Session Exists`    anonymous
        | Should Be True    $exists is False
        """
        logger.info("Deleting all sessions")
        self._http_sessions().close_all()
        self._last_http_response = None
