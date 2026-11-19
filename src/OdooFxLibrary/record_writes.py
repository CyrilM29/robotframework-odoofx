"""Keywords that write over RPC, and the journal every write goes through.

Writes are off unless the connection was opened with ``allow_write=${TRUE}``.
Each write is journaled before it is sent (``planned``), then settled
(``done``, ``failed``) or left ``unknown`` when the request may have reached
the server without an answer: such a write is read back and reconciled, never
sent again. The journal holds field names and ids, never values; the HTTP and
web keywords append to the same journal.
"""

from typing import Any, Callable, Union

from robot.api import logger
from robot.api.deco import keyword

from .rpc import OdooRpcError


class OdooRecordWriteKeywords:
    """Writes of OdooFxLibrary: create, update, delete, call a method, and the write journal."""

    def _journaled_write(self, operation: str, model: str, ids: list, fields: list,
                         act: Callable[[Any], Any], method: str = "") -> Any:
        channel = self._require_channel()
        if not self._info["allow_write"]:
            raise OdooRpcError(
                f"Writes are off: {operation} on {model} refused, connect with allow_write=${{TRUE}}")
        entry = {"seq": len(self._journal) + 1, "phase": "planned", "operation": operation,
                 "database": self._info["database"], "model": model, "method": method,
                 "ids": list(ids), "fields": sorted(fields)}
        self._journal.append(entry)
        logger.info(f"write {entry['seq']} planned: {operation} {model} {method} {entry['ids']}")
        try:
            result = act(channel)
        except OdooRpcError as exc:
            entry["phase"] = "unknown" if exc.unknown_outcome else "failed"
            entry["error"] = str(exc)
            logger.info(f"write {entry['seq']} {entry['phase']}: {exc}")
            raise
        except Exception as exc:
            entry["phase"] = "unknown"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            logger.info(f"write {entry['seq']} unknown: {entry['error']}")
            raise
        entry["phase"] = "done"
        logger.info(f"write {entry['seq']} done")
        return result

    @staticmethod
    def _as_ids(record_id: Union[int, list]) -> list:
        return [record_id] if isinstance(record_id, int) else list(record_id)

    @keyword("Create Odoo Record")
    def create_odoo_record(self, model: str, values: dict) -> int:
        """Create one record of ``model`` from ``values`` and return its database id.

        Needs ``allow_write``. Put a `New Odoo Run Marker` in a free-text field
        so the record can be identified and removed.

        Example:
        | ${marker}=    `New Odoo Run Marker`    prefix=ODOOFX-DEVIS16
        | &{values}=    Create Dictionary    name=${marker} client    comment=${marker}    is_company=${TRUE}
        | ${client_id}=    `Create Odoo Record`    res.partner    ${values}
        """
        created = self._journaled_write(
            "create", model, [], list(values),
            lambda channel: channel.create(model, values))
        self._journal[-1]["ids"] = [created]
        return created

    @keyword("Update Odoo Record")
    def update_odoo_record(self, model: str, record_id: Union[int, list], values: dict) -> bool:
        """Write ``values`` on the identified record(s). Needs ``allow_write``.

        Example:
        | &{values}=    Create Dictionary    date_order=2000-01-01 00:00:00
        | `Update Odoo Record`    sale.order    ${quotation_id}    ${values}
        """
        ids = self._as_ids(record_id)
        return self._journaled_write(
            "update", model, ids, list(values),
            lambda channel: channel.write(model, ids, values))

    @keyword("Delete Odoo Record")
    def delete_odoo_record(self, model: str, record_id: Union[int, list]) -> bool:
        """Delete the identified record(s). Needs ``allow_write``.

        Odoo refuses what the application itself refuses (a confirmed sales
        order, for instance): the refusal is raised, the record stays, and the
        way back goes through the model's own action (cancel) first.

        Example:
        | `Delete Odoo Record`    sale.order    ${quotation_id}
        | `Odoo Record Should Not Exist`    sale.order    ${quotation_id}
        """
        ids = self._as_ids(record_id)
        return self._journaled_write(
            "delete", model, ids, [], lambda channel: channel.unlink(model, ids))

    @keyword("Call Odoo Record Method")
    def call_odoo_record_method(self, model: str, record_id: Union[int, list],
                                method: str, **kwargs) -> Any:
        """Call a public method of the model on the identified record(s), for instance
        ``action_confirm`` or ``action_cancel``. Needs ``allow_write``.

        Named arguments after ``method`` are passed on to the method, except
        ``context``, a dict that becomes the call's context (for instance
        ``context=${{{"disable_cancel_warning": True}}}``). Returns what the
        method returns: a method that opens a wizard returns its action and
        does not do the work, check the state afterwards.

        Example:
        | `Call Odoo Record Method`    sale.order    ${quotation_id}    action_confirm
        | `Call Odoo Record Method`    sale.order    ${quotation_id}    action_cancel
        | ...    context=${{{"disable_cancel_warning": True}}}
        | `Odoo Record State Should Be`    sale.order    ${quotation_id}    cancel
        """
        ids = self._as_ids(record_id)
        context = kwargs.pop("context", None)
        return self._journaled_write(
            "call", model, ids, list(kwargs),
            lambda channel: channel.call(model, method, ids, kwargs, context), method=method)

    @keyword("Get Odoo Write Journal")
    def get_odoo_write_journal(self, since: int = 0) -> list:
        """Return the writes of this library instance after entry ``since``, oldest first.

        Each entry has ``seq``, ``phase`` (``planned``, ``done``, ``failed``,
        ``unknown``), ``operation``, ``database``, ``model``, ``method``,
        ``ids`` and the field names written, never their values; a write the
        HTTP keywords sent also has ``channel`` ``http`` and its ``route``. A ``planned``
        or ``unknown`` entry is reconciled by reading the record, never sent
        again. The journal is that of the whole process: take the last ``seq``
        before a test (``${since}``) to judge only what the test wrote.

        Example:
        | ${journal}=    `Get Odoo Write Journal`
        | ${mark}=    Get Length    ${journal}
        | ${written}=    `Get Odoo Write Journal`    since=${mark}
        | Should Be Empty    ${written}
        """
        return [dict(entry) for entry in self._journal if entry["seq"] > since]

    @keyword("Odoo Write Journal Should Hold No Unknown Outcome")
    def odoo_write_journal_should_hold_no_unknown_outcome(self, since: int = 0) -> None:
        """Fail when a write after entry ``since`` is ``planned`` or ``unknown``.

        Those two phases mean a write whose effect is not known: read the record
        instead of trusting the run. ``since`` (the last ``seq`` read before the
        test) keeps an earlier test's entry from failing the ones that follow.

        Example:
        | `Call Odoo Record Method`    sale.order    ${quotation_id}    action_confirm
        | `Odoo Write Journal Should Hold No Unknown Outcome`    since=${mark}
        """
        doubtful = [entry for entry in self.get_odoo_write_journal(since)
                    if entry["phase"] in ("planned", "unknown")]
        if doubtful:
            raise AssertionError(
                "Writes with an unknown effect: " + ", ".join(
                    f"#{e['seq']} {e['operation']} {e['model']} {e['phase']}" for e in doubtful))

    @keyword("Reconcile Odoo Write")
    def reconcile_odoo_write(self, seq: int, reason: str) -> None:
        """Settle a ``planned`` or ``unknown`` journal entry once the record was read back.

        ``seq`` is the entry's number, ``reason`` says what the reading showed (for
        instance ``state read back as sent``). The entry becomes ``reconciled`` and
        no longer fails `Odoo Write Journal Should Hold No Unknown Outcome`. A write
        is never sent again: the reading IS the reconciliation.

        Example:
        | Run Keyword And Expect Error    GLOB:*None result cannot be sent*
        | ...    `Call Odoo Record Method`    sale.order    ${quotation_id}    action_quotation_sent
        | `Odoo Record State Should Be`    sale.order    ${quotation_id}    sent
        | ${written}=    `Get Odoo Write Journal`    since=${mark}
        | `Reconcile Odoo Write`    ${written}[-1][seq]    state of quotation ${quotation_id} read back as sent
        | `Odoo Last Write Should Be`    reconciled
        """
        entry = next((e for e in self._journal if e["seq"] == seq), None)
        if entry is None:
            raise OdooRpcError(f"No journal entry {seq}")
        if entry["phase"] not in ("planned", "unknown"):
            raise OdooRpcError(
                f"Journal entry {seq} is {entry['phase']}: only a planned or unknown write is reconciled")
        if not reason.strip():
            raise OdooRpcError("A reconciliation states what the reading showed")
        entry["phase"] = "reconciled"
        entry["reconciled"] = reason
        logger.info(f"write {seq} reconciled: {reason}")

    @keyword("Odoo Last Write Should Be")
    def odoo_last_write_should_be(self, phase: str) -> None:
        """Fail unless the last journaled write is in ``phase`` (``done``, ``failed``...).

        Example:
        | &{values}=    Create Dictionary    client_order_ref=ODOOFX-DEVIS16-no-client
        | Run Keyword And Expect Error    GLOB:*sale.order.create failed*
        | ...    `Create Odoo Record`    sale.order    ${values}
        | `Odoo Last Write Should Be`    failed
        """
        if not self._journal:
            raise AssertionError("The write journal is empty")
        actual = self._journal[-1]["phase"]
        if actual != phase:
            raise AssertionError(f"The last write is {actual!r}, expected {phase!r}")
