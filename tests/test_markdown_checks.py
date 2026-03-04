"""Tests for Markdown slop checks."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from grain.checks.markdown_checks import (
    HedgeWord,
    ThanksOpener,
    ObviousHeader,
    BulletProse,
    TableOverkill,
)

CONFIG = {
    "grain": {"fail_on": [], "warn_only": [], "ignore": []},
    "python": {"generic_varnames": []},
    "markdown": {
        "hedge_words": [
            "robust", "seamless", "leverage", "cutting-edge", "powerful",
            "you might want to", "consider using", "it's worth noting", "note that",
        ]
    },
}


# ---------------------------------------------------------------------------
# HEDGE_WORD
# ---------------------------------------------------------------------------

class TestHedgeWord:
    check = HedgeWord()

    def test_fires_on_robust(self):
        source = "This is a robust solution.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "HEDGE_WORD" for v in violations)

    def test_fires_on_leverage(self):
        source = "You can leverage the existing APIs.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "HEDGE_WORD" for v in violations)

    def test_fires_on_note_that(self):
        source = "Note that this requires Python 3.11.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "HEDGE_WORD" for v in violations)

    def test_passes_clean_prose(self):
        source = "This module reads configuration from `.grain.toml` in the repo root.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_skips_code_block(self):
        source = """\
```python
# robust error handling example
try:
    pass
```
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("README.md", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# THANKS_OPENER
# ---------------------------------------------------------------------------

class TestThanksOpener:
    check = ThanksOpener()

    def test_fires_on_thanks_for_contributing(self):
        source = "Thanks for contributing to this project!\n\nHere's how to get started.\n"
        violations = list(self.check.check("CONTRIBUTING.md", source, CONFIG))
        assert any(v.rule == "THANKS_OPENER" for v in violations)

    def test_fires_on_thank_you(self):
        source = "Thank you for your interest in this project.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "THANKS_OPENER" for v in violations)

    def test_passes_direct_opener(self):
        source = "# grain\n\nAnti-slop linter for AI-assisted codebases.\n"
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_skips_non_readme(self):
        source = "Thank you for your interest in this project.\n"
        violations = list(self.check.check("src/main.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("README.md", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# OBVIOUS_HEADER
# ---------------------------------------------------------------------------

class TestObviousHeader:
    check = ObviousHeader()

    def test_fires_on_redundant_header(self):
        source = """\
## Installation

Install the package using pip.
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "OBVIOUS_HEADER" for v in violations)

    def test_passes_header_with_value(self):
        source = """\
## Installation

Run `pip install grain` then add a `.grain.toml` to your repo root.
Configure `fail_on` and `warn_only` to match your team's tolerance.
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_passes_header_with_subsections(self):
        source = """\
## Configuration

### fail_on

Rules that block the commit.

### warn_only

Rules that print but don't block.
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("README.md", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# BULLET_PROSE
# ---------------------------------------------------------------------------

class TestBulletProse:
    check = BulletProse()

    def test_fires_on_short_list(self):
        source = """\
- Fast
- Simple
- Free
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "BULLET_PROSE" for v in violations)

    def test_passes_longer_items(self):
        source = """\
- Detects obvious restatement comments that add no value
- Flags broad except clauses that swallow unexpected errors
- Identifies docstrings that just repeat the function name
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_passes_four_or_more_items(self):
        source = """\
- A
- B
- C
- D
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_passes_with_sub_bullets(self):
        source = """\
- Fast
  - Reason A
- Simple
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("README.md", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# TABLE_OVERKILL
# ---------------------------------------------------------------------------

class TestTableOverkill:
    check = TableOverkill()

    def test_fires_on_single_row_table(self):
        source = """\
| Name | Value |
|------|-------|
| foo  | bar   |
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "TABLE_OVERKILL" for v in violations)

    def test_fires_on_constant_column(self):
        source = """\
| Name | Type |
|------|------|
| foo  | str  |
| bar  | str  |
| baz  | str  |
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert any(v.rule == "TABLE_OVERKILL" for v in violations)

    def test_passes_varied_table(self):
        source = """\
| Name | Type |
|------|------|
| foo  | str  |
| bar  | int  |
| baz  | bool |
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_passes_multi_row_varied(self):
        source = """\
| Check | Severity | Description |
|-------|----------|-------------|
| OBVIOUS_COMMENT | error | restates code |
| NAKED_EXCEPT | error | swallows errors |
| RESTATED_DOCSTRING | warn | name-repeat |
"""
        violations = list(self.check.check("README.md", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("README.md", "", CONFIG))
        assert violations == []
