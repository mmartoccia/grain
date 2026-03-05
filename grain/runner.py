"""grain runner -- orchestrates checks, collects violations, formats output."""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from grain.checks.base import Violation
from grain.checks.python_checks import PYTHON_CHECKS
from grain.checks.markdown_checks import MARKDOWN_CHECKS
from grain.checks.commit_checks import COMMIT_CHECKS
from grain.config import load_config


def _get_staged_files() -> list[str]:
    """Return list of staged files tracked by git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f for f in result.stdout.splitlines() if f.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _get_all_files(root: Path) -> list[str]:
    """Walk repo for all .py and .md files (respects .gitignore roughly)."""
    files = []
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "dist", "build"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            if filename.endswith((".py", ".md", ".markdown")):
                full = os.path.join(dirpath, filename)
                files.append(os.path.relpath(full, root))
    return sorted(files)


def _classify_file(path: str) -> str:
    """Return 'python', 'markdown', or 'unknown'."""
    lower = path.lower()
    if lower.endswith(".py"):
        return "python"
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    return "unknown"


def _should_ignore(rule: str, line: int, source: str) -> bool:
    """Check if a line has a grain: ignore comment."""
    lines = source.splitlines()
    if line <= len(lines):
        target = lines[line - 1].lower()
        if "grain: ignore" in target:
            return True
    return False


def run_checks(
    files: list[str],
    config: dict,
    commit_msg: str | None = None,
) -> list[Violation]:
    """Run all applicable checks. Returns sorted list of Violations."""
    violations: list[Violation] = []
    fail_on: set[str] = set(config["grain"]["fail_on"])
    warn_only: set[str] = set(config["grain"]["warn_only"])
    ignore_rules: set[str] = set(config["grain"]["ignore"])
    exclude_patterns: list[str] = config["grain"].get("exclude", [])

    for filepath in files:
        if any(fnmatch.fnmatch(filepath, pat) for pat in exclude_patterns):
            continue
        path = Path(filepath)
        kind = _classify_file(filepath)
        if kind == "unknown":
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            continue

        checks = PYTHON_CHECKS if kind == "python" else MARKDOWN_CHECKS

        for check in checks:
            if check.rule in ignore_rules:
                continue
            # Determine severity override
            if check.rule in fail_on:
                sev_override = "error"
            elif check.rule in warn_only:
                sev_override = "warn"
            else:
                sev_override = check.rule in fail_on and "error" or "warn"

            for v in check.check(str(path), source, config):
                if v.rule in ignore_rules:
                    continue
                if _should_ignore(v.rule, v.line, source):
                    continue
                # Override severity from config
                if v.rule in fail_on:
                    v.severity = "error"
                elif v.rule in warn_only:
                    v.severity = "warn"
                violations.append(v)

    # Commit message checks
    if commit_msg is not None:
        for check in COMMIT_CHECKS:
            if check.rule in ignore_rules:
                continue
            for v in check.check("COMMIT_MSG", commit_msg, config):
                if v.rule in fail_on:
                    v.severity = "error"
                elif v.rule in warn_only:
                    v.severity = "warn"
                violations.append(v)

    violations.sort(key=lambda v: (v.path, v.line, v.rule))
    return violations


def format_violations(violations: list[Violation], show_summary: bool = True) -> str:
    """Format violations for terminal output."""
    if not violations:
        return "grain: no violations found\n"

    lines = []
    for v in violations:
        lines.append(v.format())

    if show_summary:
        errors = sum(1 for v in violations if v.severity == "error")
        warns = sum(1 for v in violations if v.severity == "warn")
        lines.append("")
        parts = []
        if errors:
            parts.append(f"{errors} error(s)")
        if warns:
            parts.append(f"{warns} warning(s)")
        lines.append(f"grain: {', '.join(parts)} -- fix errors before committing")

    return "\n".join(lines) + "\n"


def determine_exit_code(violations: list[Violation]) -> int:
    """Return 1 if any error-severity violations, 0 otherwise."""
    return 1 if any(v.severity == "error" for v in violations) else 0
