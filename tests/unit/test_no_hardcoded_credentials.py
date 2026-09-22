"""RULES.md convention 11: no credential with a default value.

In specs/, resources/, tests/ and variables/, a Robot variable whose name
carries PASSWORD, PWD, SECRET, TOKEN or KEY keeps ``${EMPTY}`` as its default.
Secrets enter through ``-v NAME:value`` or the environment.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("specs", "resources", "tests", "variables")
SENSITIVE = re.compile(r"PASSWORD|PWD|SECRET|TOKEN|KEY", re.I)
VARIABLE_LINE = re.compile(r"^\s*(\$\{[^}]+\})(?:\s{2,}|\t)(.*?)\s*$")

# relative posix path -> reason the default value is acceptable
EXCEPTIONS = {}


def find_hardcoded(text):
    """Yield (line number, variable name, value) for sensitive defaults."""
    in_variables = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("***"):
            in_variables = line.strip("* \t").lower() == "variables"
            continue
        if not in_variables:
            continue
        match = VARIABLE_LINE.match(line)
        if not match:
            continue
        name, value = match.groups()
        if SENSITIVE.search(name) and value not in ("", "${EMPTY}"):
            yield lineno, name, value


def _robot_files():
    for directory in SCANNED_DIRS:
        base = ROOT / directory
        if base.is_dir():
            yield from sorted(base.rglob("*.robot"))
            yield from sorted(base.rglob("*.resource"))


def test_detects_a_password_default():
    text = "*** Variables ***\n${ODOO_URL}    http://x\n${PASSWORD}    admin\n"
    assert list(find_hardcoded(text)) == [(3, "${PASSWORD}", "admin")]


def test_accepts_empty_default_and_ignores_non_sensitive_names():
    text = "*** Variables ***\n${ODOO_URL}    http://x\n${API_TOKEN}    ${EMPTY}\n"
    assert list(find_hardcoded(text)) == []


def test_only_the_variables_section_is_inspected():
    text = "*** Test Cases ***\nLogin\n    ${PASSWORD}=    Get Secret    vault\n"
    assert list(find_hardcoded(text)) == []


@pytest.mark.parametrize("path", list(_robot_files()), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_real_tree_has_no_credential_default(path):
    rel = path.relative_to(ROOT).as_posix()
    if rel in EXCEPTIONS:
        pytest.skip(EXCEPTIONS[rel])
    found = list(find_hardcoded(path.read_text(encoding="utf-8")))
    assert found == [], f"{rel}: {found}"
