"""Keywords that read the structure of an Odoo database over the RPC channel.

Models, their fields and relations, installed modules, and calls of model
methods that need no record (``name_search``, ``default_get``...). They work
on the connection `Connect To Odoo` opened and proved, through XML-RPC up to
Odoo 18 and JSON-2 from Odoo 19.
"""

from typing import Any, Optional

from robot.api.deco import keyword

from .rpc import OdooRpcError

FIELD_ATTRIBUTES = ("type", "string", "required", "readonly", "relation", "relation_field",
                    "store", "selection")
RELATIONAL_TYPES = ("many2one", "one2many", "many2many")
# Model methods that only read: callable without allow_write and never journaled.
READ_MODEL_METHODS = frozenset({
    "check_access_rights", "default_get", "fields_get", "get_views", "has_access",
    "name_search", "read_group", "search", "search_count", "search_read",
})
MODULE_INSTALLED = "installed"


def relations_of(fields: dict) -> list:
    """The relational fields of a ``fields_get`` answer, sorted by name."""
    return [{"field": name, "type": definition["type"], "relation": definition.get("relation"),
             "relation_field": definition.get("relation_field")}
            for name, definition in sorted(fields.items())
            if definition.get("type") in RELATIONAL_TYPES]


class OdooOrmKeywords:
    """Model, field and module introspection of `OdooFxLibrary`, mixed into it."""

    @keyword("Get Odoo Model Fields")
    def get_odoo_model_fields(self, model: str, attributes: Optional[list] = None) -> dict:
        """Return ``{field name: definition}`` for every field of ``model``.

        Each definition holds the ``attributes`` asked for, by default ``type``,
        ``string`` (the label, in the connection's language: never assert on
        it), ``required``, ``readonly``, ``relation``, ``relation_field``,
        ``store`` and ``selection``; Odoo leaves out those a field does not have.

        Example:
        | ${fields}=    `Get Odoo Model Fields`    res.partner
        | Should Be Equal    ${fields}[country_id][relation]    res.country
        """
        return self._require_channel().fields_get(model, list(attributes or FIELD_ATTRIBUTES))

    @keyword("Get Odoo Field Definition")
    def get_odoo_field_definition(self, model: str, field: str) -> dict:
        """Return the definition of one ``field`` of ``model``; fail when the model has no such field.

        Example:
        | ${definition}=    `Get Odoo Field Definition`    res.partner    child_ids
        | Should Be Equal    ${definition}[relation_field]    parent_id
        """
        definition = self.get_odoo_model_fields(model).get(field)
        if definition is None:
            raise OdooRpcError(f"{model} has no field {field!r}")
        return definition

    @keyword("Odoo Field Exists")
    def odoo_field_exists(self, model: str, field: str) -> bool:
        """``True`` when ``model`` has a field named ``field``, ``False`` otherwise.

        Fields come and go between versions (``res.partner`` lost ``mobile`` in
        Odoo 19): ask before relying on one.

        Example:
        | ${exists}=    `Odoo Field Exists`    res.partner    mobile
        | Should Be True    ${exists}
        """
        return field in self._require_channel().fields_get(model, ["type"])

    @keyword("Get Odoo Model Relations")
    def get_odoo_model_relations(self, model: str) -> list:
        """The relational fields of ``model``, sorted by name: ``field``, ``type``
        (``many2one``, ``one2many``, ``many2many``), ``relation`` (the model
        pointed at) and ``relation_field`` (the inverse field of a one2many,
        ``None`` otherwise).

        Example:
        | ${relations}=    `Get Odoo Model Relations`    res.partner
        | ${country}=    Evaluate    [r for r in $relations if r["field"] == "country_id"][0]
        | Should Be Equal    ${country}[type]    many2one
        """
        return relations_of(self._require_channel().fields_get(
            model, ["type", "relation", "relation_field"]))

    @keyword("Search Odoo Models")
    def search_odoo_models(self, pattern: str = "", limit: int = 0) -> list:
        """The models whose technical name contains ``pattern`` (all when empty), sorted by name.

        Each one gives ``model`` (``sale.order.line``), ``name`` (its label, in
        the connection's language) and ``transient`` (``True`` for a wizard).

        Example:
        | ${models}=    `Search Odoo Models`    sale.order
        | ${names}=    Evaluate    [m["model"] for m in $models]
        | Should Contain    ${names}    sale.order.line
        """
        domain = [["model", "ilike", pattern]] if pattern else []
        found = self._require_channel().search_read(
            "ir.model", domain, ["model", "name", "transient"], limit=int(limit), order="model")
        return [{"model": row["model"], "name": row["name"], "transient": bool(row["transient"])}
                for row in found]

    @keyword("Get Odoo Module State")
    def get_odoo_module_state(self, module: str) -> str:
        """The state code of ``module`` (``installed``, ``uninstalled``, ``to upgrade``...).

        Fails when the database knows no module of that technical name.

        Example:
        | ${state}=    `Get Odoo Module State`    sale_stock
        | Should Be Equal    ${state}    installed
        """
        found = self._require_channel().search_read(
            "ir.module.module", [["name", "=", module]], ["state"], limit=1)
        if not found:
            raise OdooRpcError(f"The database knows no module named {module!r}")
        return found[0]["state"]

    @keyword("Odoo Module Should Be Installed")
    def odoo_module_should_be_installed(self, module: str) -> None:
        """Fail unless ``module`` is installed on the target.

        Example:
        | `Odoo Module Should Be Installed`    contacts
        """
        state = self.get_odoo_module_state(module)
        if state != MODULE_INSTALLED:
            raise AssertionError(f"Module {module} is {state}, not {MODULE_INSTALLED}")

    @keyword("Call Odoo Model Method")
    def call_odoo_model_method(self, model: str, method: str, **kwargs) -> Any:
        """Call a public method of ``model`` that works on no record, and return its result.

        Arguments go by name (``name=Azure Interior``), except ``context``, a
        dict that becomes the call's context. A read method (``name_search``,
        ``default_get``, ``fields_get``, ``get_views``, ``search``,
        ``search_read``, ``search_count``, ``read_group``,
        ``check_access_rights``, ``has_access``) runs on any connection; any
        other method may write, so it needs ``allow_write`` and is journaled
        like `Call Odoo Record Method`.

        Example:
        | ${azure_id}=    `Resolve Odoo External Id`    base.res_partner_12    res.partner
        | ${found}=    `Call Odoo Model Method`    res.partner    name_search    name=Azure Interior
        | Should Contain    ${{[pair[0] for pair in $found]}}    ${azure_id}
        """
        context = kwargs.pop("context", None)
        if method in READ_MODEL_METHODS:
            return self._require_channel().call_model(model, method, kwargs, context)
        return self._journaled_write(
            "call", model, [], list(kwargs),
            lambda channel: channel.call_model(model, method, kwargs, context, write=True),
            method=method)
