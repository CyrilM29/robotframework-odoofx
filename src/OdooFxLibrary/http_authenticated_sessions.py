"""The authenticated HTTP sessions of `OdooFxLibrary`, the session kinds of RequestsLibrary absorbed.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/SessionKeywords.py``, MIT License,
Copyright (c) 2016 Bulkan Evcimen), rewritten. Names, parameters and defaults are the upstream's. As for
`Create Session`: the timeout and cookies belong to the session, ``debug`` is inert, a Robot ``Secret`` is
accepted in ``headers`` and in the password of ``auth`` and revealed into the session only, and the log
of the creation names the kind of authentication, never its secret (the upstream wrote ``headers`` and
``cookies`` in clear). Changed, by decision of the owner of 2026-11-07: `Create Client Cert Session`
refuses a missing ``client_certs`` before it registers anything, and takes the single path of a PEM that
holds both the certificate and the key as it is. NTLM needs the optional extra ``ntlm``
(``requests_ntlm``). The lab targets answer none of the handshakes. A unit test plays the Digest one against a
double that issues the challenge and checks the response; for NTLM and a client certificate the unit tests hold
only the part of the library (the NTLM authentication built from the domain, the user and the password, the
certificate handed to the transport): no NTLM exchange and no TLS presentation is played anywhere.
"""

from typing import Any

import requests
from robot.api import logger
from robot.api.deco import keyword

from .http_log import masked_headers, masked_url
from .http_requests import revealed
from .http_sessions import DEFAULT_RETRY_METHOD_LIST


def ntlm_auth_class() -> Any:
    """The ``HttpNtlmAuth`` class of ``requests_ntlm``, or an error that names the extra to install."""
    try:
        from requests_ntlm import HttpNtlmAuth
    except ImportError:
        raise AssertionError("requests_ntlm module not installed: install the extra robotframework-odoofx[ntlm]") \
            from None
    return HttpNtlmAuth


class OdooHttpAuthenticatedSessionKeywords:
    """`Create Custom Session`, `Create Digest Session`, `Create Client Cert Session`, `Create Ntlm Session`."""

    def _open_authenticated_session(self, kind: str, alias: str, url: str, auth: Any, secrets: set,
                                    headers: Any, cookies: Any, timeout: Any, proxies: Any, verify: Any,
                                    max_retries: Any, backoff_factor: Any, disable_warnings: Any,
                                    retry_status_list: Any, retry_method_list: Any) -> requests.Session:
        logger.info(f"Creating {kind} session {alias}: url={masked_url(url)}, headers={masked_headers(headers)}, "
                    f"auth={type(auth).__name__ if auth is not None else None}, timeout={timeout}, verify={verify}")
        session = self._register_http_session(
            alias, url, headers=revealed(headers, secrets), cookies=cookies, auth=auth, timeout=timeout,
            proxies=proxies, verify=verify, max_retries=max_retries, backoff_factor=backoff_factor,
            disable_warnings=disable_warnings, retry_status_list=retry_status_list,
            retry_method_list=retry_method_list)
        session.odoofx_secrets.update(secrets)
        return session

    @keyword("Create Custom Session")
    def create_custom_session(self, alias, url, auth, headers={}, cookies={}, timeout=None, proxies=None,
                              verify=False, debug=0, max_retries=3, backoff_factor=0.10, disable_warnings=0,
                              retry_status_list=[], retry_method_list=DEFAULT_RETRY_METHOD_LIST):
        """Create an HTTP session to ``url`` authenticated by ``auth``, any ``requests`` authentication.

        ``auth`` is an object of ``requests.auth`` (``HTTPBasicAuth``, a
        subclass of ``AuthBase``...), mounted on the session as given. The
        other arguments are those of `Create Session`. Returns the session.

        Example:
        | ${basic}=    Evaluate    requests.auth.HTTPBasicAuth("odoofx-probe", "lot3")
        | `Create Custom Session`    custom-auth    http://127.0.0.1:8016    ${basic}
        | ${page}=    `GET On Session`    custom-auth    /web/login
        | Should Be Equal As Integers    ${page.status_code}    200
        """
        secrets = set()
        return self._open_authenticated_session(
            "custom", alias, url, revealed(auth, secrets), secrets, headers, cookies, timeout, proxies, verify,
            max_retries, backoff_factor, disable_warnings, retry_status_list, retry_method_list)

    @keyword("Create Digest Session")
    def create_digest_session(self, alias, url, auth, headers={}, cookies={}, timeout=None, proxies=None,
                              verify=False, debug=0, max_retries=3, backoff_factor=0.10, disable_warnings=0,
                              retry_status_list=[], retry_method_list=DEFAULT_RETRY_METHOD_LIST):
        """Create an HTTP session to ``url`` with HTTP Digest authentication.

        ``auth`` is a user name and a password (two elements; the upstream's
        documentation said three, copied from NTLM), the password possibly a
        Robot ``Secret``. The session answers a server's Digest challenge
        (``401`` with ``WWW-Authenticate: Digest``); Odoo issues none, so on
        the lab targets the session reaches Odoo without authenticating: the
        handshake is held by a unit test. The other arguments are those of
        `Create Session`. Returns the session.

        Example:
        | `Create Digest Session`    digest-auth    http://127.0.0.1:8016
        | ...    ${{["odoofx-probe", $PASSWORD]}}
        | ${page}=    `GET On Session`    digest-auth    /web/login
        | Should Be True    'Authorization' not in $page.request.headers
        """
        secrets = set()
        digest = requests.auth.HTTPDigestAuth(*revealed(auth, secrets)) if auth else None
        return self._open_authenticated_session(
            "digest", alias, url, digest, secrets, headers, cookies, timeout, proxies, verify, max_retries,
            backoff_factor, disable_warnings, retry_status_list, retry_method_list)

    @keyword("Create Client Cert Session")
    def create_client_cert_session(self, alias, url, headers={}, cookies={}, client_certs=None, timeout=None,
                                   proxies=None, verify=False, debug=0, max_retries=3, backoff_factor=0.10,
                                   disable_warnings=0, retry_status_list=[],
                                   retry_method_list=DEFAULT_RETRY_METHOD_LIST):
        """Create an HTTP session to ``url`` that presents a client certificate over TLS.

        ``client_certs`` is the pair of PEM files (certificate, key), or the
        single path of a PEM holding both, taken as it is. Without it the
        keyword fails before any session is registered (the upstream failed
        after registering it). requests checks that the files exist before
        each request, even over plain HTTP, where it never presents them: the
        lab targets are HTTP, the TLS presentation is not verified there. The
        other arguments are those of `Create Session`. Returns the session.

        Example:
        | ${pair}=    Create List    tests/data/http/streaming-upload-probe.txt    tests/data/http/streaming-upload-probe.txt
        | `Create Client Cert Session`    client-cert    http://127.0.0.1:8016    client_certs=${pair}
        | ${page}=    `GET On Session`    client-cert    /web/login
        | Should Be Equal As Integers    ${page.status_code}    200
        | Run Keyword And Expect Error    GLOB:*client_certs*    `Create Client Cert Session`    no-cert    http://127.0.0.1:8016
        """
        if not client_certs:
            raise ValueError("client_certs names the client certificate and its key: [certificate, key], "
                             "or the path of one PEM file holding both")
        session = self._open_authenticated_session(
            "client certificate", alias, url, None, set(), headers, cookies, timeout, proxies, verify, max_retries,
            backoff_factor, disable_warnings, retry_status_list, retry_method_list)
        session.cert = client_certs if isinstance(client_certs, str) else tuple(client_certs)
        return session

    @keyword("Create Ntlm Session")
    def create_ntlm_session(self, alias, url, auth, headers={}, cookies={}, timeout=None, proxies=None,
                            verify=False, debug=0, max_retries=3, backoff_factor=0.10, disable_warnings=0,
                            retry_status_list=[], retry_method_list=DEFAULT_RETRY_METHOD_LIST):
        """Create an HTTP session to ``url`` with NTLM authentication, behind the optional extra ``ntlm``.

        ``auth`` is the domain, the user name and the password (three
        elements, the password possibly a Robot ``Secret``), sent as
        ``domain\\user``. Without ``requests_ntlm`` (``pip install
        robotframework-odoofx[ntlm]``) the keyword fails before any session
        is registered, its message starting as the upstream's (``requests_ntlm
        module not installed``). No lab target answers NTLM: the handshake is
        not verified live. The other arguments are those of `Create Session`.
        Returns the session.

        Example:
        | Run Keyword And Expect Error    GLOB:requests_ntlm module not installed*
        | ...    `Create Ntlm Session`    ntlm-auth    http://127.0.0.1:8016
        | ...    ${{["ODOOFX-PROBE", "odoofx-probe", $PASSWORD]}}
        """
        ntlm = ntlm_auth_class()
        if len(auth) != 3:
            raise AssertionError(f"Incorrect number of authentication arguments - expected 3, got {len(auth)}")
        secrets = set()
        domain, user, password = revealed(list(auth), secrets)
        return self._open_authenticated_session(
            "NTLM", alias, url, ntlm(f"{domain}\\{user}", password), secrets, headers, cookies, timeout, proxies,
            verify, max_retries, backoff_factor, disable_warnings, retry_status_list, retry_method_list)
