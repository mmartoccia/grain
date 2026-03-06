"""grain runner -- orchestrates checks, collects violations, formats output."""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from grain.checks.base import Violation
from grain.checks.python_checks import PYTHON_CHECKS, OPT_IN_PYTHON_CHECKS
from grain.checks.markdown_checks import MARKDOWN_CHECKS
from grain.checks.commit_checks import COMMIT_CHECKS
from grain.checks.custom_checks import load_custom_rules
from grain.config import load_config


# Rules that can be auto-fixed without human judgment
SAFE_FIX_RULES = {"OBVIOUS_COMMENT", "VAGUE_TODO", "HEDGE_WORD"}


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
    # Activate opt-in checks that are explicitly listed in fail_on or warn_only
    active_opt_ins = {
        rule: check for rule, check in OPT_IN_PYTHON_CHECKS.items()
        if rule in fail_on or rule in warn_only
    }
    custom_rules = load_custom_rules(config)

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

        checks = (PYTHON_CHECKS + list(active_opt_ins.values())) if kind == "python" else MARKDOWN_CHECKS

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

        # Run custom rules that match this file
        for custom in custom_rules:
            if custom.rule in ignore_rules:
                continue
            if not custom.matches_file(filepath):
                continue
            for v in custom.check(str(path), source, config):
                if v.rule in ignore_rules:
                    continue
                # Custom checks handle grain:ignore internally
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


# ---------------------------------------------------------------------------
# Auto-fix logic
# ---------------------------------------------------------------------------

def _apply_fix(
    path: str,
    line: int,
    rule: str,
    source_lines: list[str],
    config: dict,
) -> tuple[bool, str]:
    """
    Apply a fix for a single violation. Returns (success, description).
    Modifies source_lines in place.
    """
    if line < 1 or line > len(source_lines):
        return False, "line out of range"

    idx = line - 1
    target = source_lines[idx]

    if rule == "OBVIOUS_COMMENT":
        stripped = target.strip()
        if stripped.startswith("#"):
            source_lines[idx] = None  # mark for deletion
            return True, "removed comment"
        return False, "not a standalone comment line"

    if rule == "VAGUE_TODO":
        if " -- [needs approach]" in target:
            return False, "already annotated"
        todo_match = re.search(r"(#\s*(?:TODO|FIXME|HACK|XXX)\s*:?\s*.+)", target, re.IGNORECASE)
        if todo_match:
            annotation = " -- [needs approach]"
            insert_pos = todo_match.end()
            new_line = target[:insert_pos] + annotation + target[insert_pos:]
            source_lines[idx] = new_line.rstrip() + "\n" if target.endswith("\n") else new_line.rstrip()
            return True, "annotated TODO"
        return False, "could not find TODO pattern"

    if rule == "HEDGE_WORD":
        hedge_words = config.get("markdown", {}).get("hedge_words", [])
        if not hedge_words:
            from grain.checks.markdown_checks import _DEFAULT_HEDGE_WORDS
            hedge_words = _DEFAULT_HEDGE_WORDS

        lower = target.lower()
        for phrase in hedge_words:
            if phrase.lower() in lower:
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                new_line = pattern.sub("", target, count=1)
                if new_line.strip() == "" or new_line.strip() == target.strip():
                    return False, "deletion would break line"
                new_line = re.sub(r"  +", " ", new_line)
                new_line = re.sub(r" ,", ",", new_line)
                new_line = re.sub(r" \.", ".", new_line)
                source_lines[idx] = new_line
                return True, f"removed '{phrase}'"
        return False, "hedge word not found"

    return False, f"rule {rule} not auto-fixable"


def apply_fixes(
    files: list[str],
    violations: list[Violation],
    config: dict,
) -> tuple[list[str], list[Violation]]:
    """
    Apply auto-fixes for safe rules. Returns (fix_messages, remaining_violations).
    Modifies files in place.
    """
    fix_messages: list[str] = []
    remaining: list[Violation] = []

    violations_by_file: dict[str, list[Violation]] = {}
    for v in violations:
        violations_by_file.setdefault(v.path, []).append(v)

    for filepath, file_violations in violations_by_file.items():
        path = Path(filepath)
        if not path.exists():
            remaining.extend(file_violations)
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            remaining.extend(file_violations)
            continue

        lines = source.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"

        file_violations.sort(key=lambda v: -v.line)

        modified = False
        for v in file_violations:
            if v.rule not in SAFE_FIX_RULES:
                remaining.append(v)
                continue

            success, desc = _apply_fix(v.path, v.line, v.rule, lines, config)
            if success:
                fix_messages.append(f"FIXED {v.path}:{v.line} {v.rule} -- {desc}")
                modified = True
            else:
                remaining.append(v)

        if modified:
            final_lines = [ln for ln in lines if ln is not None]
            path.write_text("".join(final_lines), encoding="utf-8")

    return fix_messages, remaining
