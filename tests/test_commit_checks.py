"""Tests for commit message slop checks."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from grain.checks.commit_checks import (
    VagueCommit,
    AndCommit,
    NoContext,
)

CONFIG = {
    "grain": {"fail_on": [], "warn_only": [], "ignore": []},
    "python": {"generic_varnames": []},
    "markdown": {"hedge_words": []},
}


# ---------------------------------------------------------------------------
# VAGUE_COMMIT
# ---------------------------------------------------------------------------

class TestVagueCommit:
    check = VagueCommit()

    def test_fires_on_update(self):
        violations = list(self.check.check("COMMIT_MSG", "update\n", CONFIG))
        assert any(v.rule == "VAGUE_COMMIT" for v in violations)

    def test_fires_on_fix_bug(self):
        violations = list(self.check.check("COMMIT_MSG", "fix bug\n", CONFIG))
        assert any(v.rule == "VAGUE_COMMIT" for v in violations)

    def test_fires_on_misc(self):
        violations = list(self.check.check("COMMIT_MSG", "misc\n", CONFIG))
        assert any(v.rule == "VAGUE_COMMIT" for v in violations)

    def test_fires_on_wip(self):
        violations = list(self.check.check("COMMIT_MSG", "wip\n", CONFIG))
        assert any(v.rule == "VAGUE_COMMIT" for v in violations)

    def test_passes_specific(self):
        msg = "grain: add OBVIOUS_COMMENT check for Python files\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0

    def test_empty_message(self):
        violations = list(self.check.check("COMMIT_MSG", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# AND_COMMIT
# ---------------------------------------------------------------------------

class TestAndCommit:
    check = AndCommit()

    def test_fires_on_and(self):
        msg = "fix auth bug and update docs\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert any(v.rule == "AND_COMMIT" for v in violations)

    def test_passes_no_and(self):
        msg = "fix auth token expiration in refresh flow\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0

    def test_empty_message(self):
        violations = list(self.check.check("COMMIT_MSG", "", CONFIG))
        assert violations == []

    def test_and_in_word_not_flagged(self):
        # "standard", "sand" contain "and" but not as standalone word
        msg = "refactor: use standard library json parser\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NO_CONTEXT
# ---------------------------------------------------------------------------

class TestNoContext:
    check = NoContext()

    def test_fires_on_bare_fix(self):
        msg = "fix: bug\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert any(v.rule == "NO_CONTEXT" for v in violations)

    def test_fires_on_bare_feat(self):
        msg = "feat: thing\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert any(v.rule == "NO_CONTEXT" for v in violations)

    def test_passes_with_detail(self):
        msg = "fix: prevent token expiration race in refresh handler\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0

    def test_passes_with_body(self):
        msg = """\
feat: add grain linter

Detects AI-generated code patterns before they land in version control.
Supports Python and Markdown files. Pre-commit compatible.
"""
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0

    def test_passes_non_conventional(self):
        msg = "bump version to 1.2.3\n"
        violations = list(self.check.check("COMMIT_MSG", msg, CONFIG))
        assert len(violations) == 0

    def test_empty_message(self):
        violations = list(self.check.check("COMMIT_MSG", "", CONFIG))
        assert violations == []
