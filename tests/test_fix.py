"""Tests for --fix auto-fix functionality."""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from grain.runner import run_checks, apply_fixes, SAFE_FIX_RULES
from grain.checks.base import Violation

CONFIG = {
    "grain": {"fail_on": [], "warn_only": [], "ignore": []},
    "python": {"generic_varnames": ["process_data"]},
    "markdown": {"hedge_words": ["robust", "seamless"]},
}


class TestFixObviousComment:
    """Test that --fix removes OBVIOUS_COMMENT lines."""

    def test_removes_obvious_comment(self):
        source = """\
# return the result
return result
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            obvious = [v for v in violations if v.rule == "OBVIOUS_COMMENT"]
            assert len(obvious) >= 1

            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            fixed_source = Path(path).read_text()
            assert "# return the result" not in fixed_source
            assert "return result" in fixed_source

            assert any("OBVIOUS_COMMENT" in msg and "removed" in msg for msg in fix_msgs)
        finally:
            os.unlink(path)

    def test_preserves_non_comment_lines(self):
        source = """\
def foo():
    # return the value
    return value
    x = 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            apply_fixes([path], violations, CONFIG)

            fixed_source = Path(path).read_text()
            assert "def foo():" in fixed_source
            assert "return value" in fixed_source
            assert "x = 1" in fixed_source
        finally:
            os.unlink(path)


class TestFixVagueTodo:
    """Test that --fix annotates VAGUE_TODO lines."""

    def test_annotates_vague_todo(self):
        source = """\
# TODO: implement this
def foo():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            vague = [v for v in violations if v.rule == "VAGUE_TODO"]
            assert len(vague) >= 1

            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            fixed_source = Path(path).read_text()
            assert "-- [needs approach]" in fixed_source
            assert any("VAGUE_TODO" in msg and "annotated" in msg for msg in fix_msgs)
        finally:
            os.unlink(path)

    def test_does_not_double_annotate(self):
        source = """\
# TODO: implement this -- [needs approach]
def foo():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            fixed_source = Path(path).read_text()
            count = fixed_source.count("-- [needs approach]")
            assert count == 1
        finally:
            os.unlink(path)


class TestFixDoesNotModifyUnsafe:
    """Test that --fix does NOT modify rules requiring judgment."""

    def test_naked_except_not_fixed(self):
        source = """\
try:
    do_something()
except Exception as e:
    logger.error(e)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            naked = [v for v in violations if v.rule == "NAKED_EXCEPT"]
            assert len(naked) >= 1

            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            remaining_naked = [v for v in remaining if v.rule == "NAKED_EXCEPT"]
            assert len(remaining_naked) >= 1

            fixed_source = Path(path).read_text()
            assert "except Exception as e:" in fixed_source
        finally:
            os.unlink(path)

    def test_generic_varname_not_fixed(self):
        source = """\
def process_data(data):
    return data
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            generic = [v for v in violations if v.rule == "GENERIC_VARNAME"]
            assert len(generic) >= 1

            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            remaining_generic = [v for v in remaining if v.rule == "GENERIC_VARNAME"]
            assert len(remaining_generic) >= 1
        finally:
            os.unlink(path)


class TestExitCodes:
    """Test exit code behavior with --fix."""

    def test_exit_zero_when_all_fixable(self):
        source = """\
# return the result
return result
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            from grain.runner import determine_exit_code
            code = determine_exit_code(remaining)
            assert code == 0
        finally:
            os.unlink(path)

    def test_exit_one_when_unfixable_remain(self):
        source = """\
# return the result
return result

try:
    do_something()
except Exception as e:
    logger.error(e)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            from grain.runner import determine_exit_code
            code = determine_exit_code(remaining)
            assert code == 1
        finally:
            os.unlink(path)


class TestSafeFixRules:
    """Test the SAFE_FIX_RULES constant."""

    def test_safe_rules_defined(self):
        assert "OBVIOUS_COMMENT" in SAFE_FIX_RULES
        assert "VAGUE_TODO" in SAFE_FIX_RULES
        assert "HEDGE_WORD" in SAFE_FIX_RULES

    def test_unsafe_rules_excluded(self):
        # NAKED_EXCEPT is now auto-fixable (minimal safe fix: narrow to Exception as e + raise)
        assert "NAKED_EXCEPT" in SAFE_FIX_RULES
        assert "RESTATED_DOCSTRING" not in SAFE_FIX_RULES
        assert "SINGLE_IMPL_ABC" not in SAFE_FIX_RULES
        assert "GENERIC_VARNAME" not in SAFE_FIX_RULES
        assert "TAG_COMMENT" not in SAFE_FIX_RULES


class TestFixHedgeWord:
    """Test that --fix handles HEDGE_WORD in markdown."""

    def test_removes_hedge_word(self):
        source = """\
# My Project

This is a robust solution for data processing.
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(source)
            f.flush()
            path = f.name

        try:
            violations = run_checks([path], CONFIG)
            hedge = [v for v in violations if v.rule == "HEDGE_WORD"]
            assert len(hedge) >= 1

            fix_msgs, remaining = apply_fixes([path], violations, CONFIG)

            fixed_source = Path(path).read_text()
            assert "robust" not in fixed_source.lower()
            assert "solution for data processing" in fixed_source
        finally:
            os.unlink(path)
