"""RULES.md convention 15: what ships to PyPI and what stays private.

The export is a whitelist. These tests pin the boundary so a pattern change in
scripts/export_public_tree.py cannot leak a private file without failing here.
"""
import pytest

export = pytest.importorskip(
    "export_public_tree", reason="private export tooling, not shipped to PyPI"
)

PUBLIC = [
    "pyproject.toml",
    "README.md",
    "README.fr.md",
    "LICENSE",
    "NOTICE",
    ".gitignore",
    "src/OdooFxLibrary/__init__.py",
    "src/OdooFxLibrary/odoo_library.py",
    "specs/odoo_smoke.robot",
    "tests/unit/test_odoo_library.py",
    "resources/sales.resource",
    "docs/guide.md",
    "scripts/check_no_em_dash.py",
    ".github/workflows/ci.yml",
]

PRIVATE = [
    "CLAUDE.md",
    "RULES.md",
    "ROADMAP.md",
    ".claude/settings.json",
    ".claude/agents/odoo-planner.md",
    ".github/copilot-instructions.md",
    "comms/backlog-produit.md",
    "memory/MEMORY.md",
    "memory/README.md",
    "tools/README.md",
    "tools/.gitignore",
    "tools/recorder_web/src/main.js",
    "tools/recorder_web/package.json",
    "scripts/export_public_tree.py",
    "scripts/hook_agent_permissions.py",
    ".robotmcp_artifacts/run.json",
    "src/OdooFxLibrary/__pycache__/odoo_library.cpython-312.pyc",
    "tests/unit/.pytest_cache/v/cache/nodeids",
]


@pytest.mark.parametrize("rel", PUBLIC)
def test_public_files_are_exported(rel):
    assert export.is_exported(rel), f"{rel} should ship to PyPI"


@pytest.mark.parametrize("rel", PRIVATE)
def test_private_files_stay_private(rel):
    assert not export.is_exported(rel), f"{rel} must never reach the public repo"


def test_bare_file_pattern_matches_at_repo_root_only():
    assert export._matches("README.md", "README.md")
    assert not export._matches("memory/README.md", "README.md")
    assert not export._matches("tools/.gitignore", ".gitignore")


def test_directory_pattern_covers_the_tree_but_not_lookalikes():
    assert export._matches("src", "src/**")
    assert export._matches("src/a/b.py", "src/**")
    assert not export._matches("srcfoo/b.py", "src/**")


def test_windows_separators_are_normalized():
    assert export._matches("src\\OdooFxLibrary\\odoo_library.py", "src/**")


def test_clean_target_keeps_the_public_clone_history(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text("stale private file\n", encoding="utf-8")
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "MEMORY.md").write_text("stale private file\n", encoding="utf-8")

    export.clean_target(tmp_path)

    assert (tmp_path / ".git" / "HEAD").exists()
    assert [p.name for p in tmp_path.iterdir()] == [".git"]
