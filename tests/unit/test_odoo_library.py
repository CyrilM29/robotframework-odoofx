"""Off-Odoo tests for OdooFxLibrary (RULES.md convention 5)."""
import re
from pathlib import Path

from OdooFxLibrary import OdooFxLibrary, __version__

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_KEYWORDS = {
    "Connect To Odoo",
    "Navigate To Menu",
    "Create New Quotation",
    "Assert Quotation Status Is",
    "Disconnect From Odoo",
}


def _registered_keywords():
    members = vars(OdooFxLibrary).values()
    return {getattr(m, "robot_name", None) for m in members if callable(m)}


def test_keywords_are_registered_under_business_names():
    assert EXPECTED_KEYWORDS <= _registered_keywords()


def test_connect_stores_session_and_disconnect_clears_it():
    lib = OdooFxLibrary()
    assert lib._session is None

    session = lib.connect_to_odoo("http://localhost:8069", "user@example.com", "pw")
    assert session == {
        "url": "http://localhost:8069",
        "email": "user@example.com",
        "password": "pw",
    }
    assert lib._session is session

    lib.disconnect_from_odoo()
    assert lib._session is None


def test_library_scope_is_global():
    assert OdooFxLibrary.ROBOT_LIBRARY_SCOPE == "GLOBAL"


def test_version_is_the_same_in_package_library_and_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert __version__ == declared
    assert OdooFxLibrary.ROBOT_LIBRARY_VERSION == declared
