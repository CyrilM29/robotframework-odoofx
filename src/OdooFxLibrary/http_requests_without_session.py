"""HTTP requests without a session of `OdooFxLibrary`, the session-less keywords of RequestsLibrary absorbed.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/RequestsKeywords.py``, MIT License,
Copyright (c) 2016 Bulkan Evcimen), rewritten. Names and parameters are the upstream's; the status
check, the ``Secret`` revealed at sending and the masked log are those of `GET On Session`. What
changed: a request without a session sends no cookie and no timeout but its own (the upstream sent the
cookies and the timeout of the last session created), and a write on Odoo is guarded as by `POST On
Session`, a request without a session included.
"""

from robot.api.deco import keyword

from .http_requests import check_status


class OdooHttpSessionLessRequestKeywords:
    """GET, POST, PUT, PATCH, DELETE, HEAD and OPTIONS without a session, mixed into `OdooFxLibrary`."""

    def _request_without_session(self, method, url, expected_status, msg, **kwargs):
        response = self._send_http(method, None, url, **kwargs)
        check_status(expected_status, response, msg)
        return response

    @keyword("GET")
    def session_less_get(self, url, params=None, expected_status=None, msg=None, **kwargs):
        """Send a GET request to the full ``url``, without a session, and return the response.

        ``params``, ``expected_status``, ``msg`` and the other requests
        arguments are those of `GET On Session`. No cookie is sent but those
        given here (``cookies=``), and no timeout applies but ``timeout=``:
        unlike upstream, the last session created lends neither. A redirect is
        followed. A write on Odoo is guarded as by `POST On Session`.

        Example:
        | ${page}=    `GET`    http://127.0.0.1:8016/web/login
        | Should Be Equal As Integers    ${page.status_code}    200
        | Should Be True    'Cookie' not in $page.request.headers
        """
        return self._request_without_session("get", url, expected_status, msg, params=params, **kwargs)

    @keyword("POST")
    def session_less_post(self, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a POST request to the full ``url``, without a session, and return the response.

        ``data`` and ``json`` are the body, as for `POST On Session`; no cookie
        nor timeout of a session is sent, as for `GET`. A write on Odoo is
        guarded as by `POST On Session`.

        Example:
        | ${posted}=    `POST`    http://127.0.0.1:8016/web/session/get_session_info
        | ...    json=${{{"jsonrpc": "2.0", "method": "call", "params": {}}}}
        | Should Be Equal    ${posted.json()}[error][data][name]    odoo.http.SessionExpiredException
        """
        return self._request_without_session("post", url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("PUT")
    def session_less_put(self, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a PUT request to the full ``url``, without a session, and return the response.

        As `PUT On Session`, without a session: no cookie nor timeout of one.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | ${put}=    `PUT`    http://127.0.0.1:8016/web/login    expected_status=400
        | Should Be Equal    ${put.request.method}    PUT
        """
        return self._request_without_session("put", url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("PATCH")
    def session_less_patch(self, url, data=None, json=None, expected_status=None, msg=None, **kwargs):
        """Send a PATCH request to the full ``url``, without a session, and return the response.

        As `PATCH On Session`, without a session: no cookie nor timeout of one.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | ${patch}=    `PATCH`    http://127.0.0.1:8016/web/login    expected_status=400
        | Should Be Equal    ${patch.request.method}    PATCH
        """
        return self._request_without_session("patch", url, expected_status, msg, data=data, json=json, **kwargs)

    @keyword("DELETE")
    def session_less_delete(self, url, expected_status=None, msg=None, **kwargs):
        """Send a DELETE request to the full ``url``, without a session, and return the response.

        As `DELETE On Session`, without a session: no cookie nor timeout of one.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | ${delete}=    `DELETE`    http://127.0.0.1:8016/web/login    expected_status=400
        | Should Be Equal    ${delete.request.method}    DELETE
        """
        return self._request_without_session("delete", url, expected_status, msg, **kwargs)

    @keyword("HEAD")
    def session_less_head(self, url, expected_status=None, msg=None, **kwargs):
        """Send a HEAD request to the full ``url``, without a session, and return the response.

        As `HEAD On Session`: no body, and a redirect is NOT followed unless
        ``allow_redirects=${TRUE}``; a write on Odoo is never sent by HEAD.

        Example:
        | ${head}=    `HEAD`    http://127.0.0.1:8016/web
        | Should Be Equal As Integers    ${head.status_code}    303
        | Should Contain    ${head.headers}[Location]    /web/login
        """
        return self._request_without_session("head", url, expected_status, msg, **kwargs)

    @keyword("OPTIONS")
    def session_less_options(self, url, expected_status=None, msg=None, **kwargs):
        """Send an OPTIONS request to the full ``url``, without a session, and return the response.

        As `OPTIONS On Session`, without a session: a redirect is followed.
        A write on Odoo is guarded as by `POST On Session`.

        Example:
        | ${options}=    `OPTIONS`    http://127.0.0.1:8016/web
        | Should Be Equal As Integers    ${options.history[0].status_code}    303
        | Should Be Equal    ${options.history[0].request.method}    OPTIONS
        """
        return self._request_without_session("options", url, expected_status, msg, **kwargs)
