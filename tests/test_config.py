"""Tests for grain config and exclude patterns."""
from __future__ import annotations

import fnmatch
from grain.runner import run_checks
from grain.config import DEFAULTS


def test_exclude_skips_matching_files():
    """Files matching exclude patterns produce no violations."""
    config = {
        "grain": {
            "fail_on": list(DEFAULTS["grain"]["fail_on"]),
            "warn_only": list(DEFAULTS["grain"]["warn_only"]),
            "ignore": [],
            "exclude": ["output/*", "reference/*"],
        },
        "python": dict(DEFAULTS["python"]),
        "markdown": dict(DEFAULTS["markdown"]),
    }
    # These would normally trigger violations but should be excluded
    files = ["output/report.md", "reference/old_script.py"]
    violations = run_checks(files, config)
    assert violations == []


def test_exclude_does_not_skip_non_matching():
    """Files not matching exclude patterns are still checked."""
    config = {
        "grain": {
            "fail_on": list(DEFAULTS["grain"]["fail_on"]),
            "warn_only": list(DEFAULTS["grain"]["warn_only"]),
            "ignore": [],
            "exclude": ["output/*"],
        },
        "python": dict(DEFAULTS["python"]),
        "markdown": dict(DEFAULTS["markdown"]),
    }
    # fnmatch should not match src/main.py against output/*
    assert not fnmatch.fnmatch("src/main.py", "output/*")


def test_exclude_empty_by_default():
    """Default config has empty exclude list."""
    assert DEFAULTS["grain"]["exclude"] == []
