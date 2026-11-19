"""
OdooFxLibrary : Core Robot Framework library for Odoo test automation.

Provides keywords for:
- Web UI automation, built on the Browser library (module ``web``)
- RPC access to the Odoo backend (XML-RPC up to Odoo 18, JSON-2 from Odoo 19)
- ORM reads: counts, records, selection values, record states

Version: 0.1.0 (bootstrap phase)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Union

from robot.api import logger
from robot.api.deco import keyword, library
from robot.api.types import Secret

from .http_keywords import OdooHttpKeywords
from .orm import OdooOrmKeywords
from .record_writes import OdooRecordWriteKeywords
from .report_pdf import OdooReportPdfKeywords
from .session_context import OdooSessionContextKeywords
from .web_channel import OdooWebChannelKeywords
from .rpc import (
    OdooRpcError, choose_channel, detect_version, open_channel, series_of, server_time,
)

QUOTATION_MODEL = "sale.order"
GROUPS_RENAMED_SERIES = 19


def _reveal(secret: Union[Secret, str]) -> str:
    return secret.value if isinstance(secret, Secret) else str(secret)


@library
class OdooFxLibrary(OdooWebChannelKeywords, OdooOrmKeywords, OdooSessionContextKeywords,
                    OdooHttpKeywords, OdooRecordWriteKeywords, OdooReportPdfKeywords):
    """Odoo test automation library for Robot Framework.

    *Connection.* `Connect To Odoo` proves the target (URL, database, version)
    before any other keyword works. The channel follows the server version:
    JSON-2 with an API key from Odoo 19, XML-RPC with a password before. On
    Odoo 19 a password only works with ``channel=xmlrpc``, which Odoo 19
    deprecates (removal announced for Odoo 22).

    *Secrets.* Pass the password or API key as a Robot Framework ``Secret``
    variable (``-v PASSWORD:Secret:...``) or an environment variable, never a
    literal in a suite. The library never logs it nor returns it.

    *States.* Assertions compare technical state codes (``draft``, ``sale``),
    never translated labels.

    *Writes.* Off by default: `Create Odoo Record`, `Update Odoo Record`,
    `Delete Odoo Record` and `Call Odoo Record Method` refuse to run unless the
    connection was opened with ``allow_write=${TRUE}``. Pair it with
    ``expected_series`` so a suite aimed at one Odoo version refuses to write
    to another. Every write is journaled (`Get Odoo Write Journal`): ``planned``
    before the call, then ``done``, ``failed`` or ``unknown`` (the request may
    have reached the server without an answer: read the record to find out,
    never send it again). Mark what a run creates with `New Odoo Run Marker` so
    it can be found again and removed; `Odoo Record Should Not Exist` proves a
    removal on the identified record.

    *Examples.* A keyword's example is taken from a green suite of the
    workbench, played on the ``odoo16`` lab instance: ``${quotation_id}`` and
    ``${client_id}`` name a draft quotation and its client created by the run,
    ``${mark}`` the journal length read before the test.

    *Context.* Odoo applies no preference of the user to an RPC call (no
    language, every company of the user): `Set Odoo Session Context` gives the
    connection a context sent with every call, under the ``context`` a keyword
    passes; `Get Odoo User Context` reads the user's own preferences.

    *HTTP.* The session and request keywords of RequestsLibrary are absorbed,
    under their names and arguments (`Create Session`, `GET On Session`,
    `POST On Session`...), the secrets they recognize masked in the log; `Create Odoo Http
    Session` opens an authenticated web session on the proven target.

    *Web channel.* Built on the Browser library, which opens the page:
    `Log In To Odoo Web Client` proves the target through the web session,
    then the ``Odoo Web`` keywords navigate by external ids, read the view,
    and fill, save or discard a form (`Fill Odoo Web Field`, `Save Odoo Web Record`).

    *Reports.* `Get Odoo Report Pdf` reads the PDF Odoo prints by its report
    route, on a web session of `Create Odoo Http Session`; `Get Pdf Text` and
    `Pdf Should Contain` assert its normalized text (the extra
    ``robotframework-odoofx[pdf]``), `Get Odoo Formatted Amount` writes an
    amount as Odoo does in a document of a language.

    *Structure.* `Get Odoo Model Fields`, `Get Odoo Model Relations`,
    `Search Odoo Models` and `Get Odoo Module State` read the database's
    structure; `Call Odoo Model Method` calls a method that needs no record.

    `Create New Quotation` is still a skeleton that does nothing but warn, so
    a suite that calls it proves nothing about it.
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = "0.3.0"

    def __init__(self):
        self._channel = None
        self._info = None
        self._journal = []
        self._web_writes = False
        self._web_filled = set()
        self._dialog_model = None
        self._dialog_filled = set()

    def _require_channel(self):
        if self._channel is None:
            raise OdooRpcError("Not connected: call Connect To Odoo first")
        return self._channel

    def _require_channel_info(self) -> dict:
        self._require_channel()
        return self._info

    @keyword("Connect To Odoo")
    def connect_to_odoo(self, url: str, database: str, login: str,
                        password: Union[Secret, str], channel: str = "auto",
                        allow_write: bool = False,
                        expected_series: Optional[int] = None) -> dict:
        """Connect to an Odoo instance and prove the target.

        ``channel`` is ``auto`` (JSON-2 from Odoo 19, XML-RPC before),
        ``xmlrpc`` or ``json2``. With JSON-2, ``password`` is the API key and
        ``login`` is not used. ``allow_write`` opts in to the write keywords,
        and to the writes the HTTP keywords send to this target's RPC routes.
        ``expected_series`` (16, 19...) makes the connection fail, before any
        login, when the server runs another major version. Returns the
        connection info (url, database, server_version, series, channel, uid,
        allow_write), never the secret.

        Example:
        | ${info}=    `Connect To Odoo`    http://127.0.0.1:8016    odoo16    admin    ${PASSWORD}
        | ...    allow_write=${TRUE}    expected_series=16
        | Should Be Equal    ${info}[channel]    xmlrpc
        """
        secret = _reveal(password)
        if not secret:
            raise OdooRpcError("Empty password or API key")
        if not database:
            raise OdooRpcError("The database must be named explicitly")
        base = url.rstrip("/")
        server_version = detect_version(base)
        series = series_of(server_version)
        if expected_series is not None and series != expected_series:
            raise OdooRpcError(
                f"Wrong target: {base} runs Odoo {server_version}, expected series {expected_series}")
        chosen = choose_channel(channel, series)
        self.disconnect_from_odoo()
        try:
            self._channel = open_channel(base, database, login, secret, chosen)
        except OdooRpcError as exc:
            if channel == "auto" and chosen == "json2":
                raise OdooRpcError(f"{exc}. channel=auto chose JSON-2, which needs an API key "
                                   "as the password; pass channel=xmlrpc to use a password") from None
            raise
        self._info = {
            "url": base,
            "database": database,
            "server_version": server_version,
            "series": series,
            "channel": chosen,
            "uid": self._channel.uid,
            "allow_write": bool(allow_write),
        }
        logger.info(f"Connected to {base} database {database}: Odoo {server_version}, "
                    f"channel {chosen}, uid {self._channel.uid}, writes "
                    f"{'allowed' if allow_write else 'off'}")
        return dict(self._info)

    @keyword("Get Odoo Connection Info")
    def get_odoo_connection_info(self) -> dict:
        """Return the proven target of the current connection (no secret).

        Example:
        | ${info}=    `Get Odoo Connection Info`
        | Should Be Equal As Integers    ${info}[series]    16
        """
        self._require_channel()
        return dict(self._info)

    @keyword("Count Odoo Records")
    def count_odoo_records(self, model: str, domain: Optional[list] = None,
                           context: Optional[dict] = None) -> int:
        """Count the records of ``model`` matching ``domain`` (all when empty).

        ``context`` is the call's context, for instance ``${{{"lang": "en_US"}}}``
        or ``${{{"active_test": False}}}`` to count archived records too.

        A count proves a target's demo data. To prove a presence or a
        disappearance, read the identified record instead of comparing counts.

        Example:
        | ${marker}=    `New Odoo Run Marker`    prefix=ODOOFX-DEVIS16
        | ${count}=    `Count Odoo Records`    sale.order    ${{[["client_order_ref", "=", $marker]]}}
        | Should Be Equal As Integers    ${count}    0
        """
        return self._require_channel().search_count(model, domain or [], context=context)

    @keyword("Search Read Odoo Records")
    def search_read_odoo_records(self, model: str, domain: Optional[list] = None,
                                 fields: Optional[list] = None, limit: int = 0,
                                 order: str = "", context: Optional[dict] = None) -> list:
        """Return the records of ``model`` matching ``domain`` as a list of dicts.

        ``context`` is the call's context (``lang``, ``active_test``...).

        Example:
        | ${lines}=    `Search Read Odoo Records`    sale.order.line    ${{[["order_id", "=", $quotation_id]]}}
        | ...    fields=${{["product_id", "product_uom_qty"]}}
        | Length Should Be    ${lines}    1
        """
        return self._require_channel().search_read(
            model, domain or [], fields=fields, limit=limit, order=order, context=context)

    @keyword("Get Odoo Server Time")
    def get_odoo_server_time(self) -> str:
        """Return the server's clock as an Odoo datetime string (UTC, one second).

        Read from the HTTP ``Date`` header: the only clock a client can trust to
        bracket what a run created, for instance ``[["create_date", ">=", t0]]``.

        Example:
        | ${t0}=    `Get Odoo Server Time`
        | ${count}=    `Count Odoo Records`    product.product    ${{[["create_date", ">=", $t0]]}}
        | ...    context=${{{"active_test": False}}}
        | Should Be Equal As Integers    ${count}    0
        """
        return server_time(self._require_channel_info()["url"])

    @keyword("Get Field Selection Values")
    def get_field_selection_values(self, model: str, field: str) -> list:
        """Return the technical codes of a selection field, in declaration order.

        Example:
        | ${states}=    `Get Field Selection Values`    sale.order    state
        | Should Contain    ${states}    sale
        """
        definition = self._require_channel().fields_get(
            model, ["type", "selection"]).get(field)
        if definition is None:
            raise OdooRpcError(f"{model} has no field {field!r}")
        if definition.get("type") != "selection":
            raise OdooRpcError(f"{model}.{field} is a {definition.get('type')} field, not a selection")
        return [code for code, _label in definition["selection"]]

    @keyword("Count Odoo Records By State")
    def count_odoo_records_by_state(self, model: str, state_field: str = "state") -> dict:
        """Return ``{state code: record count}`` for every code of ``state_field``.

        Example:
        | ${counts}=    `Count Odoo Records By State`    sale.order
        | Should Be True    ${counts}[sale] > 0
        """
        return {code: self.count_odoo_records(model, [[state_field, "=", code]])
                for code in self.get_field_selection_values(model, state_field)}

    @keyword("Get Odoo Record State")
    def get_odoo_record_state(self, model: str, record: Union[int, list],
                              state_field: str = "state",
                              context: Optional[dict] = None) -> str:
        """Return the state code of one identified record.

        ``record`` is a database id or a domain that must match exactly one
        record: anything else fails, so a state is never read off a guess.
        ``context`` is the call's context (``active_test``...).

        Example:
        | ${state}=    `Get Odoo Record State`    sale.order    ${quotation_id}
        | Should Be Equal    ${state}    draft
        """
        domain = [["id", "=", record]] if isinstance(record, int) else record
        found = self._require_channel().search_read(
            model, domain, fields=[state_field], limit=2, context=context)
        if len(found) != 1:
            raise OdooRpcError(
                f"Expected exactly one {model} record for {domain}, found {len(found)}")
        return found[0][state_field]

    @keyword("Odoo Record State Should Be")
    def odoo_record_state_should_be(self, model: str, record: Union[int, list],
                                    expected_state: str, state_field: str = "state") -> None:
        """Fail unless the identified record is in ``expected_state`` (a state code).

        An ``expected_state`` that is not a code of ``state_field`` fails too,
        so a translated label can never pass by accident.

        Example:
        | `Odoo Record State Should Be`    sale.order    ${quotation_id}    draft
        """
        codes = self.get_field_selection_values(model, state_field)
        if expected_state not in codes:
            raise AssertionError(
                f"{expected_state!r} is not a {model}.{state_field} code, expected one of {codes}")
        actual = self.get_odoo_record_state(model, record, state_field)
        if actual != expected_state:
            raise AssertionError(
                f"{model} {record} is in state {actual!r}, expected {expected_state!r}")

    @keyword("Assert Quotation Status Is")
    def assert_quotation_status_is(self, expected_status: str,
                                   quotation: Union[int, str, None] = None) -> None:
        """Assert that a sales quotation is in ``expected_status``, a state code.

        ``expected_status`` is ``draft``, ``sent``, ``sale``, ``done`` or
        ``cancel``, never the translated label. ``quotation`` is the order
        reference (``S00042``) or its database id.

        Example:
        | `Assert Quotation Status Is`    draft    ${quotation_id}
        """
        if quotation is None:
            raise OdooRpcError("No quotation identified: pass quotation=<reference or id>")
        record = quotation if isinstance(quotation, int) else [["name", "=", quotation]]
        self.odoo_record_state_should_be(QUOTATION_MODEL, record, expected_status)

    @keyword("Resolve Odoo External Id")
    def resolve_odoo_external_id(self, external_id: str, expected_model: str) -> int:
        """Return the database id behind an external id such as ``product.product_product_1``.

        Fails unless the identifier names exactly one record of ``expected_model``.
        An external id does not depend on the language of the instance, unlike a
        product name or a menu label.

        Example:
        | ${product_id}=    `Resolve Odoo External Id`    product.product_product_1    product.product
        """
        module, separator, name = external_id.partition(".")
        if not (module and separator and name):
            raise OdooRpcError(f"{external_id!r} is not a module.name external id")
        rows = self._require_channel().search_read(
            "ir.model.data", [["module", "=", module], ["name", "=", name]],
            fields=["model", "res_id"])
        if len(rows) != 1:
            raise OdooRpcError(
                f"External id {external_id} is not exactly one record (found {len(rows)})")
        if rows[0]["model"] != expected_model:
            raise OdooRpcError(
                f"External id {external_id} names a {rows[0]['model']}, not a {expected_model}")
        return rows[0]["res_id"]

    @keyword("Get Odoo Config Parameter")
    def get_odoo_config_parameter(self, key: str) -> str:
        """Return a system parameter such as ``web.base.url`` (readable by an administrator only).

        The instance's own base address names the address a suite was pointed at.

        Example:
        | ${base}=    `Get Odoo Config Parameter`    web.base.url
        | Should Be Equal    ${base}    http://127.0.0.1:8016
        """
        rows = self._require_channel().search_read(
            "ir.config_parameter", [["key", "=", key]], fields=["value"])
        if len(rows) != 1:
            raise OdooRpcError(f"System parameter {key} is not exactly one record (found {len(rows)})")
        return rows[0]["value"]

    def _user_in_group(self, user_id: int, group_external_id: str) -> bool:
        group_id = self.resolve_odoo_external_id(group_external_id, "res.groups")
        field = "group_ids" if self._info["series"] >= GROUPS_RENAMED_SERIES else "groups_id"
        return bool(self._require_channel().search_count(
            "res.users", [["id", "=", user_id], [field, "in", [group_id]]]))

    @keyword("Odoo User Should Be In Group")
    def odoo_user_should_be_in_group(self, user_id: int, group_external_id: str) -> None:
        """Fail unless the user belongs to the group named by its external id.

        The field holding a user's groups is named after the server series
        (``groups_id`` before Odoo 19, ``group_ids`` from 19).

        Example:
        | ${info}=    `Get Odoo Connection Info`
        | `Odoo User Should Be In Group`    ${info}[uid]    sales_team.group_sale_salesman
        """
        if not self._user_in_group(user_id, group_external_id):
            raise AssertionError(f"User {user_id} is not in group {group_external_id}")

    @keyword("Odoo User Should Not Be In Group")
    def odoo_user_should_not_be_in_group(self, user_id: int, group_external_id: str) -> None:
        """Fail when the user belongs to the group named by its external id (a precondition).

        Example:
        | ${info}=    `Get Odoo Connection Info`
        | `Odoo User Should Not Be In Group`    ${info}[uid]    sale.group_auto_done_setting
        """
        if self._user_in_group(user_id, group_external_id):
            raise AssertionError(f"User {user_id} is in group {group_external_id}")

    @keyword("Get Odoo Record")
    def get_odoo_record(self, model: str, record: Union[int, list],
                        fields: Optional[list] = None, context: Optional[dict] = None) -> dict:
        """Return the named ``fields`` (all when empty) of one identified record.

        ``record`` is a database id or a domain that must match exactly one record.

        Example:
        | ${quotation}=    `Get Odoo Record`    sale.order    ${quotation_id}    fields=${{["partner_id"]}}
        | Should Be Equal As Integers    ${quotation}[partner_id][0]    ${client_id}
        """
        domain = [["id", "=", record]] if isinstance(record, int) else record
        found = self._require_channel().search_read(
            model, domain, fields=fields, limit=2, context=context)
        if len(found) != 1:
            raise OdooRpcError(
                f"Expected exactly one {model} record for {domain}, found {len(found)}")
        return found[0]

    @keyword("Odoo Record Exists")
    def odoo_record_exists(self, model: str, record_id: int) -> bool:
        """Return whether the record with this database id exists (archived ones count).

        Example:
        | ${present}=    `Odoo Record Exists`    sale.order    ${quotation_id}
        | Should Be True    ${present}
        """
        return bool(self._record_count(model, record_id))

    @keyword("Odoo Record Should Exist")
    def odoo_record_should_exist(self, model: str, record_id: int) -> None:
        """Fail unless the record with this database id exists (archived ones count).

        Example:
        | `Odoo Record Should Exist`    sale.order    ${quotation_id}
        """
        if not self._record_count(model, record_id):
            raise AssertionError(f"{model} {record_id} does not exist")

    @keyword("Odoo Record Should Not Exist")
    def odoo_record_should_not_exist(self, model: str, record_id: int) -> None:
        """Fail if the record with this database id still exists (archived ones count).

        A removal is proven on the identified record, never on a count that
        went back to its previous value.

        Example:
        | `Delete Odoo Record`    res.partner    ${client_id}
        | `Odoo Record Should Not Exist`    res.partner    ${client_id}
        """
        if self._record_count(model, record_id):
            raise AssertionError(f"{model} {record_id} still exists")

    def _record_count(self, model: str, record_id: int) -> int:
        return self._require_channel().search_count(
            model, [["id", "=", record_id]], context={"active_test": False}, session=False)

    @keyword("New Odoo Run Marker")
    def new_odoo_run_marker(self, prefix: str = "ODOOFX") -> str:
        """Return a unique label such as ``ODOOFX-20260930T203012-9f3a1c``.

        Put it in a free-text field of every record a run creates, so the run's
        data can be identified, found again and removed.

        Example:
        | ${marker}=    `New Odoo Run Marker`    prefix=ODOOFX-DEVIS16
        | Should Start With    ${marker}    ODOOFX-DEVIS16-
        """
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"

    @keyword("Create New Quotation")
    def create_new_quotation(self) -> None:
        """Skeleton: creates nothing and returns nothing. The write path is not implemented yet."""
        logger.warn("Create New Quotation is a skeleton and created nothing")

    @keyword("Disconnect From Odoo")
    def disconnect_from_odoo(self) -> None:
        """Close the current connection, if any.

        Example:
        | `Disconnect From Odoo`
        | Run Keyword And Expect Error    GLOB:*Not connected*    `Get Odoo Connection Info`
        """
        if self._channel is not None:
            self._channel.close()
        self._channel = None
        self._info = None
