"""Tests for custom regex-based checks."""
from __future__ import annotations

import logging
import re

import pytest

from grain.checks.custom_checks import CustomRegexCheck, load_custom_rules
from grain.checks.base import Violation


def _make_config(custom_rules: list[dict] | None = None, **grain_overrides) -> dict:
    """Build a minimal config dict with custom rules."""
    grain = {
        "fail_on": [],
        "warn_only": [],
        "ignore": [],
        "exclude": [],
        "custom_rules": custom_rules or [],
    }
    grain.update(grain_overrides)
    return {"grain": grain, "python": {}, "markdown": {}}


def _make_check(
    name: str = "TEST_RULE",
    pattern: str = r"bad_pattern",
    files: str = "*.py",
    message: str = "test message",
    severity: str = "warn",
) -> CustomRegexCheck:
    return CustomRegexCheck(
        name=name,
        pattern=re.compile(pattern),
        files=files,
        message=message,
        severity=severity,
    )


# ---- test_custom_rule_matches_pattern ----

def test_custom_rule_matches_pattern():
    check = _make_check(pattern=r"print\(")
    source = 'x = 1\nprint("hello")\ny = 2\n'
    violations = list(check.check("test.py", source, {}))
    assert len(violations) == 1
    assert violations[0].line == 2
    assert violations[0].rule == "TEST_RULE"


# ---- test_custom_rule_respects_file_glob ----

def test_custom_rule_respects_file_glob():
    check = _make_check(files="*.py")
    assert check.matches_file("foo.py") is True
    assert check.matches_file("src/bar.py") is True
    assert check.matches_file("README.md") is False
    assert check.matches_file("notes.txt") is False


# ---- test_custom_rule_respects_grain_ignore ----

def test_custom_rule_respects_grain_ignore():
    check = _make_check(pattern=r"print\(")
    source = 'print("kept")\nprint("suppressed")  # grain: ignore\n'
    violations = list(check.check("test.py", source, {}))
    assert len(violations) == 1
    assert violations[0].line == 1


# ---- test_custom_rule_severity_default_warn ----

def test_custom_rule_severity_default_warn():
    rules = load_custom_rules(_make_config([{
        "name": "MY_RULE",
        "pattern": r"bad",
        "files": "*.py",
        "message": "bad thing",
    }]))
    assert len(rules) == 1
    assert rules[0].default_severity == "warn"


# ---- test_custom_rule_severity_override_from_config ----

def test_custom_rule_severity_override_from_config():
    rules = load_custom_rules(_make_config([{
        "name": "MY_RULE",
        "pattern": r"bad",
        "files": "*.py",
        "message": "bad thing",
        "severity": "error",
    }]))
    assert len(rules) == 1
    assert rules[0].default_severity == "error"

    # Check violations carry that severity
    violations = list(rules[0].check("test.py", "this is bad\n", {}))
    assert violations[0].severity == "error"


# ---- test_invalid_regex_skipped_gracefully ----

def test_invalid_regex_skipped_gracefully(caplog):
    with caplog.at_level(logging.WARNING):
        rules = load_custom_rules(_make_config([{
            "name": "BAD_REGEX",
            "pattern": r"[invalid(",
            "files": "*.py",
            "message": "won't load",
        }]))
    assert len(rules) == 0
    assert "invalid regex" in caplog.text


# ---- test_invalid_rule_missing_fields_skipped ----

def test_invalid_rule_missing_fields_skipped(caplog):
    with caplog.at_level(logging.WARNING):
        rules = load_custom_rules(_make_config([
            {"name": "NO_PATTERN", "files": "*.py", "message": "hi"},  # missing pattern
            {"pattern": r"x", "files": "*.py", "message": "hi"},       # missing name
            {"name": "OK_RULE", "pattern": r"x", "files": "*.py", "message": "ok"},  # valid
        ]))
    assert len(rules) == 1
    assert rules[0].rule == "OK_RULE"
    assert "missing required fields" in caplog.text


# ---- test_multiple_custom_rules ----

def test_multiple_custom_rules():
    rules = load_custom_rules(_make_config([
        {"name": "RULE_A", "pattern": r"aaa", "files": "*.py", "message": "found aaa"},
        {"name": "RULE_B", "pattern": r"bbb", "files": "*.py", "message": "found bbb"},
    ]))
    assert len(rules) == 2

    source = "aaa\nbbb\nccc\n"
    all_violations = []
    for r in rules:
        all_violations.extend(r.check("test.py", source, {}))
    assert len(all_violations) == 2
    rule_names = {v.rule for v in all_violations}
    assert rule_names == {"RULE_A", "RULE_B"}


# ---- test_const_setting_example ----

def test_const_setting_example():
    """The actual CONST_SETTING use case from Reddit."""
    rules = load_custom_rules(_make_config([{
        "name": "CONST_SETTING",
        "pattern": r"^\s*[A-Z_]{2,}\s*=\s*\d+",
        "files": "*.py",
        "message": "top-level constant assignment -- use config or env vars",
        "severity": "warn",
    }]))
    assert len(rules) == 1

    source = (
        "import os\n"
        "MAX_RETRIES = 3\n"
        "TIMEOUT = 30\n"
        "def foo():\n"
        "    x = 1\n"
        "    return x\n"
    )
    violations = list(rules[0].check("settings.py", source, {}))
    assert len(violations) == 2
    assert violations[0].line == 2
    assert violations[1].line == 3
    assert all(v.severity == "warn" for v in violations)


# ---- test_empty_custom_rules ----

def test_empty_custom_rules():
    rules = load_custom_rules(_make_config([]))
    assert rules == []

    # Also test with no custom_rules key at all
    rules2 = load_custom_rules({"grain": {}})
    assert rules2 == []

    # And completely empty config
    rules3 = load_custom_rules({})
    assert rules3 == []


# ---- test_invalid_name_format ----

def test_invalid_name_format(caplog):
    """Names must be uppercase + underscores."""
    with caplog.at_level(logging.WARNING):
        rules = load_custom_rules(_make_config([
            {"name": "lowercase", "pattern": r"x", "files": "*.py", "message": "bad name"},
            {"name": "Mixed_Case", "pattern": r"x", "files": "*.py", "message": "bad name"},
            {"name": "VALID_NAME", "pattern": r"x", "files": "*.py", "message": "ok"},
        ]))
    assert len(rules) == 1
    assert rules[0].rule == "VALID_NAME"


# ---- test_invalid_severity_defaults_to_warn ----

def test_invalid_severity_defaults_to_warn(caplog):
    with caplog.at_level(logging.WARNING):
        rules = load_custom_rules(_make_config([{
            "name": "SEV_TEST",
            "pattern": r"x",
            "files": "*.py",
            "message": "test",
            "severity": "critical",  # invalid
        }]))
    assert len(rules) == 1
    assert rules[0].default_severity == "warn"


# ---- test_custom_rule_in_runner (integration) ----

def test_custom_rule_in_runner(tmp_path):
    """Integration test: custom rules work through run_checks."""
    from grain.runner import run_checks

    # Write a test file
    py_file = tmp_path / "app.py"
    py_file.write_text("print('debug')\nx = 1\n")

    config = _make_config(
        custom_rules=[{
            "name": "PRINT_DEBUG",
            "pattern": r"^\s*print\s*\(",
            "files": "*.py",
            "message": "print() call -- use logging instead",
            "severity": "error",
        }],
    )

    violations = run_checks([str(py_file)], config)
    custom_violations = [v for v in violations if v.rule == "PRINT_DEBUG"]
    assert len(custom_violations) == 1
    assert custom_violations[0].severity == "error"


# ---- test_custom_rule_ignored_by_config ----

def test_custom_rule_ignored_by_config(tmp_path):
    """Custom rules respect ignore list in config."""
    from grain.runner import run_checks

    py_file = tmp_path / "app.py"
    py_file.write_text("print('debug')\n")

    config = _make_config(
        custom_rules=[{
            "name": "PRINT_DEBUG",
            "pattern": r"^\s*print\s*\(",
            "files": "*.py",
            "message": "print() call",
            "severity": "error",
        }],
        ignore=["PRINT_DEBUG"],
    )

    violations = run_checks([str(py_file)], config)
    custom_violations = [v for v in violations if v.rule == "PRINT_DEBUG"]
    assert len(custom_violations) == 0


# ---- test_custom_rule_file_glob_no_match_in_runner ----

def test_custom_rule_file_glob_no_match_in_runner(tmp_path):
    """Custom rules don't run on files that don't match their glob."""
    from grain.runner import run_checks

    py_file = tmp_path / "app.py"
    py_file.write_text("print('debug')\n")

    config = _make_config(
        custom_rules=[{
            "name": "PRINT_DEBUG",
            "pattern": r"^\s*print\s*\(",
            "files": "*.js",  # Won't match .py files
            "message": "print() call",
            "severity": "error",
        }],
    )

    violations = run_checks([str(py_file)], config)
    custom_violations = [v for v in violations if v.rule == "PRINT_DEBUG"]
    assert len(custom_violations) == 0
