"""Keywords that hold a context for every RPC call of the connection.

Odoo applies no preference of the user to an RPC call: without a context, a
translated field reads in its source language (``en_US``) and every company of
the user is visible, over XML-RPC as over JSON-2 (measured on Odoo 16 and 19).
The session context is sent with every call of the connection `Connect To Odoo`
opened; the ``context`` a keyword passes is merged over it and wins key by key.
"""

from typing import Any

from robot.api import logger
from robot.api.deco import keyword

from .rpc import OdooRpcError, plain

SOURCE_LANGUAGE = "en_US"
LANGUAGE_KEY = "lang"
TIME_ZONE_KEY = "tz"
COMPANIES_KEY = "allowed_company_ids"


def merged_entries(current: dict, entries: dict) -> dict:
    """``current`` with ``entries`` applied: a ``None`` value removes its key."""
    merged = dict(current)
    for key, value in entries.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = plain(value)
    return merged


def company_ids_of(value: Any) -> list:
    """The company ids of an ``allowed_company_ids`` value, refused unless a non-empty list of integers.

    Odoo reads an empty list as "every company of the user", without a word."""
    if not isinstance(value, (list, tuple)) or not value:
        raise OdooRpcError(f"{COMPANIES_KEY} must be a non-empty list of company ids, got {value!r}; "
                           f"pass {COMPANIES_KEY}=${{NONE}} to see every company of the user")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise OdooRpcError(f"{COMPANIES_KEY} must hold company ids (integers), got {value!r}")
    return list(value)


class OdooSessionContextKeywords:
    """The session context of `OdooFxLibrary`'s RPC connection, mixed into it."""

    @keyword("Set Odoo Session Context")
    def set_odoo_session_context(self, **entries: Any) -> dict:
        """Merge the named entries into the context sent with every RPC call of the connection.

        ``lang`` (a language code), ``tz`` and ``allowed_company_ids`` (a list of
        company ids, the first one the current company) are the usual entries;
        any other context key is passed as given. An entry set to ``${NONE}`` is
        removed. A keyword's own ``context`` wins over the session, key by key.
        Returns the whole session context.

        Refused before anything changes: a ``lang`` that is neither ``en_US``
        (the source language) nor an active language of the database (Odoo 16
        would read the source language without a word, Odoo 19 refuses it on
        the first translated field), a ``tz`` that is not one of the server's
        time zones (the selection of the ``tz`` field of ``res.partner``: Odoo
        reads an unknown one as UTC without a word), and ``allowed_company_ids``
        naming a company the user does not have, or empty (Odoo would read it as
        every company).

        A new `Connect To Odoo` starts with an empty session context. The proofs
        of existence (`Odoo Record Exists`, `Odoo Record Should Not Exist`...)
        leave it out, so that a company of the session cannot hide a record; a
        count or a search made to prove an absence still reads under it.
        The web channel is not affected: the web client sends its own context.

        Example:
        | ${context}=    `Set Odoo Session Context`    lang=fr_FR
        | ${germany}=    `Get Odoo Record`    res.country    57    fields=${{["name"]}}
        | Should Be Equal    ${germany}[name]    Allemagne
        | Run Keyword And Expect Error    GLOB:*Language 'am_ET' is not active in database odoo16*
        | ...    `Set Odoo Session Context`    lang=am_ET
        | `Set Odoo Session Context`    allowed_company_ids=${{[2]}}
        | ${chicago_orders}=    `Count Odoo Records`    sale.order
        | Should Be Equal As Integers    ${chicago_orders}    0
        | ${context}=    `Set Odoo Session Context`    tz=Europe/Brussels
        | Should Be Equal    ${context}[tz]    Europe/Brussels
        | Run Keyword And Expect Error    GLOB:*Time zone 'Mars/Olympus' is not known by database odoo16*
        | ...    `Set Odoo Session Context`    tz=Mars/Olympus
        """
        if not entries:
            raise OdooRpcError("Name at least one entry, for instance lang=fr_FR")
        channel = self._require_channel()
        candidate = merged_entries(channel.session_context, entries)
        if entries.get(LANGUAGE_KEY) is not None:
            self._check_session_language(candidate[LANGUAGE_KEY])
        if entries.get(TIME_ZONE_KEY) is not None:
            self._check_session_time_zone(candidate[TIME_ZONE_KEY])
        if entries.get(COMPANIES_KEY) is not None:
            candidate[COMPANIES_KEY] = self._check_session_companies(candidate[COMPANIES_KEY])
        channel.session_context = candidate
        logger.info(f"Session context: {candidate}")
        return dict(candidate)

    def _check_session_language(self, code: Any) -> None:
        if not isinstance(code, str):
            raise OdooRpcError(f"{LANGUAGE_KEY} must be a language code such as fr_FR, got {code!r}")
        if code == SOURCE_LANGUAGE:
            return
        active = self._require_channel().search_count(
            "res.lang", [["code", "=", code], ["active", "=", True]], session=False)
        if not active:
            raise OdooRpcError(f"Language {code!r} is not active in database {self._info['database']}: "
                               "activate it in Odoo first, or use en_US")

    def _check_session_time_zone(self, name: Any) -> None:
        if not isinstance(name, str):
            raise OdooRpcError(f"{TIME_ZONE_KEY} must be a time zone name such as Europe/Brussels, got {name!r}")
        field = self._require_channel().fields_get("res.partner", ["selection"], session=False).get("tz", {})
        if name not in {code for code, _label in field.get("selection") or []}:
            raise OdooRpcError(f"Time zone {name!r} is not known by database {self._info['database']}: "
                               "name one of the time zones of the field tz of res.partner")

    def _check_session_companies(self, value: Any) -> list:
        company_ids = company_ids_of(value)
        channel = self._require_channel()
        rows = channel.search_read("res.users", [["id", "=", channel.uid]], fields=["company_ids"],
                                   session=False)
        allowed = rows[0]["company_ids"] if rows else []
        foreign = [company for company in company_ids if company not in allowed]
        if foreign:
            raise OdooRpcError(f"{COMPANIES_KEY} names companies user {channel.uid} does not have: "
                               f"{foreign}; the user's companies are {sorted(allowed)}")
        return company_ids

    @keyword("Get Odoo Session Context")
    def get_odoo_session_context(self) -> dict:
        """Return the context sent with every RPC call of the connection (empty after `Connect To Odoo`).

        Example:
        | `Set Odoo Session Context`    lang=fr_FR
        | ${context}=    `Get Odoo Session Context`
        | Dictionaries Should Be Equal    ${context}    ${{{"lang": "fr_FR"}}}
        """
        return dict(self._require_channel().session_context)

    @keyword("Clear Odoo Session Context")
    def clear_odoo_session_context(self) -> None:
        """Empty the session context: RPC calls go back to Odoo's defaults.

        Example:
        | `Set Odoo Session Context`    allowed_company_ids=${{[2]}}
        | `Clear Odoo Session Context`
        | ${context}=    `Get Odoo Session Context`
        | Should Be Empty    ${context}
        """
        self._require_channel().session_context = {}
        logger.info("Session context cleared")

    @keyword("Get Odoo User Context")
    def get_odoo_user_context(self) -> dict:
        """Return the preferences of the connected user as Odoo gives them (``res.users.context_get``).

        Typically ``lang``, ``tz`` and ``uid``: what the web client applies,
        and an RPC call does not unless the session context carries it.

        Example:
        | ${user}=    `Get Odoo User Context`
        | Should Be Equal    ${user}[lang]    fr_FR
        | `Set Odoo Session Context`    lang=${user}[lang]
        """
        return self._require_channel().call_model("res.users", "context_get")
