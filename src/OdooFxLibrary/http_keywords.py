"""The HTTP channel of `OdooFxLibrary`: sessions plain or authenticated, requests on a session or without one,
status assertions, the Odoo web session."""

from .http_authenticated_sessions import OdooHttpAuthenticatedSessionKeywords
from .http_odoo_session import OdooHttpOdooSessionKeywords
from .http_requests import OdooHttpRequestKeywords
from .http_requests_without_session import OdooHttpSessionLessRequestKeywords
from .http_sessions import OdooHttpSessionKeywords
from .http_status_assertions import OdooHttpStatusAssertionKeywords


class OdooHttpKeywords(OdooHttpSessionKeywords, OdooHttpAuthenticatedSessionKeywords, OdooHttpRequestKeywords,
                       OdooHttpSessionLessRequestKeywords, OdooHttpStatusAssertionKeywords,
                       OdooHttpOdooSessionKeywords):
    """The HTTP keywords of `OdooFxLibrary`, mixed into it."""
