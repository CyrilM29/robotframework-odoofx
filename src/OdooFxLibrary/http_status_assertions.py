"""The status assertions of `OdooFxLibrary`, the response checks of RequestsLibrary absorbed.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/RequestsKeywords.py`` and
``SessionKeywords.py``, MIT License, Copyright (c) 2016 Bulkan Evcimen), rewritten. Names and parameters
are the upstream's, and so is the check, that of the request keywords. Two changes, decided by the owner on
2026-11-07 after two false greens of the upstream measured live: `Request Should Be Successful` judges the
response it is given even when it failed (the upstream tested ``if not response``, false for a 4xx or 5xx
response, and judged the last response instead), and a request that fails without a response clears the
last response (the upstream kept the former one, so that `Status Should Be` without a response judged a
stale one). As for the request keywords, an expected status may be a number.
"""

from typing import Any

import requests
from robot.api.deco import keyword

from .http_requests import check_status


class OdooHttpStatusAssertionKeywords:
    """`Status Should Be` and `Request Should Be Successful`, mixed into `OdooFxLibrary`."""

    def _response_to_check(self, response: Any) -> requests.Response:
        given = getattr(self, "_last_http_response", None) if response is None else response
        if given is None:
            raise AssertionError("No response to check: the last request got none, or none was sent")
        if not isinstance(given, requests.Response):
            raise AssertionError(f"Not a response: {type(given).__name__} given, a response of a request expected")
        return given

    @keyword("Status Should Be")
    def status_should_be(self, expected_status, response=None, msg=None):
        """Fail unless ``response`` has the ``expected_status``; without ``response``, the last response.

        ``expected_status`` is checked as by `GET On Session`: a code
        (``200``, ``${404}``), a name (``Not Found``, ``OK``), or ``any``.
        ``msg`` opens the failure message, which names the URL, masked like
        the log. The last response is that of the last request keyword of
        OdooFxLibrary (never one of RequestsLibrary); a request that failed
        without a response leaves none, and the keyword then fails saying so.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${not_found}=    `GET On Session`    anonymous    /web/content/res.users/2/image_128    expected_status=404
        | `Status Should Be`    404
        | `GET On Session`    anonymous    /web/login
        | `Status Should Be`    200
        | `Status Should Be`    Not Found    ${not_found}
        """
        check_status(expected_status, self._response_to_check(response), msg)

    @keyword("Request Should Be Successful")
    def request_should_be_successful(self, response=None):
        """Fail when ``response`` has a 4xx or 5xx status; without ``response``, judge the last response.

        Unlike upstream, a response given is judged even when it failed: the
        upstream replaced a failed response by the last one, so that a 404
        passed once a 200 had followed. The failure names the status and the
        URL, masked like the log.

        Example:
        | `Create Session`    anonymous    http://127.0.0.1:8016
        | ${not_found}=    `GET On Session`    anonymous    /web/content/res.users/2/image_128    expected_status=404
        | `GET On Session`    anonymous    /web/login
        | `Request Should Be Successful`
        | Run Keyword And Expect Error    GLOB:*404 Client Error*    `Request Should Be Successful`    ${not_found}
        """
        check_status(None, self._response_to_check(response))
