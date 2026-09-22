#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Guard : No em-dash (U+2014) anywhere in the repo.

The em-dash is the #1 tell of AI-generated text. This script enforces the rule
mechanically across all repo files.

Usage:
    python scripts/check_no_em_dash.py
    python scripts/check_no_em_dash.py --fix  # (not yet implemented)

Exit code: 0 if clean, 1 if violations found.
"""

import re
import sys
from pathlib import Path

# Files and counts allowed to contain em-dashes (rule exemptions)
ALLOWED = {
    "CLAUDE.md": 1,  # The rule itself is documented here
    "scripts/check_no_em_dash.py": 2,  # EM_DASH definition + error message
    "RULES.md": 1,  # Example in rule #13 documentation
    ".github/copilot-instructions.md": 1,  # Mirror of rule for Copilot
}

# Patterns to scan (prose, code, config and CI: everything but _vendor/)
PATTERNS = [
    "**/*.md",
    "**/*.py",
    "**/*.robot",
    "**/*.resource",
    "**/*.toml",
    "**/*.yml",
    "**/*.yaml",
    "**/*.json",
    "**/*.txt",
    "**/*.js",
    "**/*.mjs",
    "**/*.html",
]

# Folders to skip
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}

EM_DASH = "—"


def check_file(filepath):
    """
    Check a file for em-dashes.

    Returns:
        (violation_count, lines_with_violations)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, OSError):
        return 0, []

    violations = []
    total = 0
    for line_num, line in enumerate(content.split("\n"), start=1):
        occurrences = line.count(EM_DASH)
        if occurrences:
            violations.append((line_num, line.strip()))
            total += occurrences

    return total, violations


def main():
    # Windows consoles default to cp1252, which cannot print the report.
    # Done here rather than at import time so pytest's capture stays intact.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    repo_root = Path(__file__).parent.parent

    total_violations = 0
    problem_files = []

    # Scan all files
    for pattern in PATTERNS:
        for filepath in repo_root.glob(pattern):
            # Skip directories in SKIP_DIRS
            if any(part in SKIP_DIRS for part in filepath.parts):
                continue

            # Skip vendored code
            if "_vendor" in filepath.parts:
                continue

            relative_path = filepath.relative_to(repo_root)
            count, violations = check_file(filepath)

            if count > 0:
                # Check if this file is allowed (normalize path separators)
                relative_path_str = str(relative_path).replace("\\", "/")
                allowed_count = ALLOWED.get(relative_path_str, 0)
                if count > allowed_count:
                    problem_files.append(
                        (relative_path_str, count, allowed_count, violations)
                    )
                    total_violations += count - allowed_count

    # Report
    if problem_files:
        print(f"❌ Found {total_violations} em-dash violation(s):\n")
        for filepath, count, allowed, violations in problem_files:
            print(f"  {filepath}: {count} occurrence(s) (allowed: {allowed})")
            for line_num, line in violations[:3]:  # Show first 3
                print(f"    Line {line_num}: {line[:70]}")
            if len(violations) > 3:
                print(f"    ... and {len(violations) - 3} more")
            print()
        print(
            "To fix: replace em-dash (—) with: colon (:), comma (,), parentheses, "
            "or split the sentence."
        )
        print(f"French: space before colon « term : definition »")
        print(f"English: no space « term: definition »")
        return 1
    else:
        print("✓ No em-dash violations found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
