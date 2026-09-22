"""Tests for scripts/check_no_em_dash.py (RULES.md convention 13).

Pure logic on throwaway files first, then the real tree: that last test is what
keeps the rule from decaying silently commit after commit. The banned character
is never written literally here, it is taken from the guard itself.
"""
import subprocess
import sys
from pathlib import Path

import pytest

import check_no_em_dash as guard

ROOT = Path(__file__).resolve().parents[2]
EM = guard.EM_DASH
EN_DASH = chr(0x2013)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_guard_targets_u2014():
    assert EM == chr(0x2014)


def test_check_file_reports_line_number_and_excerpt(tmp_path):
    path = _write(tmp_path, "doc.md", f"clean line\na term {EM} its explanation\n")
    count, violations = guard.check_file(path)
    assert count == 1
    assert violations == [(2, f"a term {EM} its explanation")]


def test_check_file_counts_every_occurrence_on_one_line(tmp_path):
    # A closed parenthetical carries two: an ALLOWED count of 1 must not hide
    # the second one.
    path = _write(tmp_path, "doc.md", f"a {EM} b {EM} c\n")
    count, violations = guard.check_file(path)
    assert count == 2
    assert len(violations) == 1


def test_check_file_ignores_en_dash_and_hyphen(tmp_path):
    path = _write(tmp_path, "doc.md", f"range 0.31{EN_DASH}0.35, compound-word\n")
    assert guard.check_file(path) == (0, [])


def test_check_file_tolerates_binary_content(tmp_path):
    path = tmp_path / "blob.md"
    path.write_bytes(b"\xff\xfe\x00binary")
    assert guard.check_file(path) == (0, [])


def test_guard_scans_config_and_ci_files():
    scanned = {pattern.rsplit(".", 1)[-1] for pattern in guard.PATTERNS}
    assert {"md", "py", "robot", "resource", "toml", "yml", "json", "js"} <= scanned


@pytest.mark.parametrize("rel, allowed", sorted(guard.ALLOWED.items()))
def test_allowed_entries_pin_an_exact_count(rel, allowed):
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} is not part of this tree (private file)")
    count, _ = guard.check_file(path)
    assert count == allowed, f"{rel}: {count} em-dash(es), ALLOWED pins {allowed}"


def test_real_tree_passes_the_guard():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_no_em_dash.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout
