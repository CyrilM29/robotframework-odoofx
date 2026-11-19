"""An authenticated Odoo web session for the HTTP keywords of `OdooFxLibrary`.

Odoo answers its JSON-RPC routes with status 200 even when it refuses the call: a wrong password on
``/web/session/authenticate`` comes back 200 with ``odoo.exceptions.AccessDenied`` in the body
(measured on Odoo 16 and 19). The session is therefore judged on the body, then proven by a second
read of the session it opened.
"""

from typing import Any, Union

from robot.api import logger
from robot.api.deco import keyword
from robot.api.types import Secret

from .rpc import OdooRpcError, TIMEOUT

AUTHENTICATE_ROUTE = "/web/session/authenticate"
SESSION_INFO_ROUTE = "/web/session/get_session_info"


def json_rpc(params: dict) -> dict:
    return {"jsonrpc": "2.0", "method": "call", "params": params}


def error_name(body: Any) -> str:
    """The name of the exception an Odoo JSON-RPC answer carries, or ``""``."""
    error = body.get("error") if isinstance(body, dict) else None
    if not error:
        return ""
    return (error.get("data") or {}).get("name") or error.get("message") or "error"


class OdooHttpOdooSessionKeywords:
    """`Create Odoo Http Session` of `OdooFxLibrary`, mixed into it."""

    def _json_rpc_result(self, session, route: str, params: dict, refused: str) -> dict:
        reply = session.post(f"{session.url}{route}", json=json_rpc(params), timeout=TIMEOUT)
        if reply.status_code != 200:
            raise OdooRpcError(f"{refused}: Odoo answered HTTP {reply.status_code}")
        try:
            body = reply.json()
        except ValueError:
            raise OdooRpcError(f"{refused}: Odoo did not answer JSON-RPC") from None
        name = error_name(body)
        result = body.get("result") if isinstance(body, dict) else None
        if name or not isinstance(result, dict):
            raise OdooRpcError(f"{refused}: {name or 'no result'}")
        return result

    def _log_in_web_session(self, session, database: str, login: str, secret: str) -> tuple:
        logged = self._json_rpc_result(session, AUTHENTICATE_ROUTE,
                                       {"db": database, "login": login, "password": secret},
                                       f"Odoo refused the web login of {login!r} on database {database}")
        found = self._json_rpc_result(session, SESSION_INFO_ROUTE, {},
                                      f"The web session of {login!r} on database {database} was not kept")
        version = (found.get("server_version_info") or [None])[0]
        proof = {"database": found.get("db"), "series": version, "uid": found.get("uid")}
        return proof, {"database": database, "uid": logged.get("uid")}

    @keyword("Create Odoo Http Session")
    def create_odoo_http_session(self, alias: str, login: str, password: Union[Secret, str]) -> dict:
        """Open an Odoo web session on the proven target, name it ``alias``, and prove it.

        The target is the one `Connect To Odoo` proved: its URL, database and
        series. The session logs in with ``login`` and ``password`` (the user's
        password: an API key does not open a web session), then reads the
        session back (``get_session_info``) and fails unless its database and
        series are the proven target's and its user the one the login gave. A refusal is named by Odoo's exception
        (``odoo.exceptions.AccessDenied``), never with the secret, which is not
        logged. The ``... On Session`` keywords then reach the routes a logged
        user reaches (``/web/content/...``, ``/report/pdf/...``). Returns the
        session's alias, URL, database, series and uid.

        Example:
        | ${connection}=    `Get Odoo Connection Info`
        | ${web}=    `Create Odoo Http Session`    odoo-web    admin    ${PASSWORD}
        | Should Be Equal As Integers    ${web}[uid]    ${connection}[uid]
        | ${pdf}=    `GET On Session`    odoo-web    /report/pdf/sale.report_saleorder/7
        | Should Start With    ${pdf.headers}[Content-Type]    application/pdf
        """
        info = self._require_channel_info()
        secret = password.value if isinstance(password, Secret) else str(password)
        if not secret:
            raise OdooRpcError("Empty password: a web session needs the user's password")
        database, series = info["database"], info["series"]
        session = self._build_http_session(info["url"], verify=True, max_retries=0)
        try:
            proof, expected = self._log_in_web_session(session, database, login, secret)
        except Exception:
            session.close()
            raise
        if proof != dict(expected, series=series) or not proof["uid"]:
            session.close()
            raise OdooRpcError(f"The web session is not the proven target's: {proof}, expected "
                               f"{dict(expected, series=series)}")
        self._http_sessions().register(session, alias=alias)
        logger.info(f"Web session {alias}: {login} on {info['url']} database {database}, series {series}, "
                    f"uid {proof['uid']}")
        return {"alias": alias, "url": info["url"], **proof}
