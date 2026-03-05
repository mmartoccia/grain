"""Tests for Python slop checks."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from grain.checks.python_checks import (
    ObviousComment,
    NakedExcept,
    RestatedDocstring,
    VagueTodo,
    SingleImplAbc,
    GenericVarname,
    TagComment,
)

CONFIG = {
    "grain": {"fail_on": [], "warn_only": [], "ignore": []},
    "python": {"generic_varnames": ["process_data", "handle_response", "get_result", "do_thing"]},
    "markdown": {"hedge_words": []},
}


# ---------------------------------------------------------------------------
# OBVIOUS_COMMENT
# ---------------------------------------------------------------------------

class TestObviousComment:
    check = ObviousComment()

    def test_fires_on_restatement(self):
        source = """\
# return result
return result
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 1
        assert violations[0].rule == "OBVIOUS_COMMENT"
        assert violations[0].line == 1

    def test_passes_on_meaningful_comment(self):
        source = """\
# Cap retries to avoid thundering herd
return min(retries, MAX_RETRIES)
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []

    def test_single_line(self):
        source = "x = 1\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert violations == []

    def test_fires_on_write_cache(self):
        # comment words: {write, data, cache}, code tokens: {write, data, cache}
        source = """\
# write data to cache
write_data_to_cache(data)
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 1

    def test_no_fire_on_suppressed(self):
        source = """\
# return result  # grain: ignore OBVIOUS_COMMENT
return result
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NAKED_EXCEPT
# ---------------------------------------------------------------------------

class TestNakedExcept:
    check = NakedExcept()

    def test_fires_on_bare_except(self):
        source = """\
try:
    do_something()
except Exception as e:
    logger.error(e)
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "NAKED_EXCEPT" for v in violations)

    def test_fires_on_except_pass(self):
        source = """\
try:
    do_something()
except Exception:
    pass
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "NAKED_EXCEPT" for v in violations)

    def test_passes_when_reraise(self):
        source = """\
try:
    do_something()
except Exception as e:
    logger.error(e)
    raise
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_passes_specific_exception(self):
        source = """\
try:
    do_something()
except ValueError as e:
    logger.error(e)
"""
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []

    def test_syntax_error_file(self):
        source = "def foo(:\n    pass\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# RESTATED_DOCSTRING
# ---------------------------------------------------------------------------

class TestRestatedDocstring:
    check = RestatedDocstring()

    def test_fires_on_gets_the_data(self):
        source = '''\
def get_data():
    """Gets the data."""
    pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "RESTATED_DOCSTRING" for v in violations)

    def test_fires_on_class_restatement(self):
        source = '''\
class DataProcessor:
    """A class for processing data."""
    pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "RESTATED_DOCSTRING" for v in violations)

    def test_passes_meaningful_docstring(self):
        source = '''\
def get_data():
    """Fetch records from the upstream cache, applying TTL-based invalidation."""
    pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_passes_no_docstring(self):
        source = '''\
def get_data():
    pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# VAGUE_TODO
# ---------------------------------------------------------------------------

class TestVagueTodo:
    check = VagueTodo()

    def test_fires_on_implement_this(self):
        source = "# TODO: implement this\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "VAGUE_TODO" for v in violations)

    def test_fires_on_add_error_handling(self):
        source = "# TODO: add error handling\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "VAGUE_TODO" for v in violations)

    def test_fires_on_improve_performance(self):
        source = "# TODO: improve performance\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "VAGUE_TODO" for v in violations)

    def test_passes_specific_todo(self):
        source = "# TODO: replace edge-density heuristic with MobileNet (needs ~50MB model)\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_passes_fixme_with_reason(self):
        source = "# FIXME: blocked by upstream bug in requests>=2.31 -- see issue #4521\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []

    def test_no_todo(self):
        source = "x = 1  # increment x\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# SINGLE_IMPL_ABC
# ---------------------------------------------------------------------------

class TestSingleImplAbc:
    check = SingleImplAbc()

    def test_fires_on_single_concrete_impl(self):
        source = '''\
import abc

class Fetcher(abc.ABC):
    @abc.abstractmethod
    def fetch(self):
        pass

class HttpFetcher(Fetcher):
    def fetch(self):
        return requests.get(self.url)
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "SINGLE_IMPL_ABC" for v in violations)

    def test_passes_multiple_impls(self):
        source = '''\
import abc

class Fetcher(abc.ABC):
    @abc.abstractmethod
    def fetch(self):
        pass

class HttpFetcher(Fetcher):
    def fetch(self):
        return requests.get(self.url)

class FileFetcher(Fetcher):
    def fetch(self):
        return open(self.path).read()
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_passes_no_abc(self):
        source = '''\
class Fetcher:
    def fetch(self):
        pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []


# ---------------------------------------------------------------------------
# GENERIC_VARNAME
# ---------------------------------------------------------------------------

class TestGenericVarname:
    check = GenericVarname()

    def test_fires_on_process_data(self):
        source = '''\
def process_data(data):
    return data
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "GENERIC_VARNAME" for v in violations)

    def test_fires_on_handle_response(self):
        source = '''\
def handle_response(resp):
    return resp.json()
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert any(v.rule == "GENERIC_VARNAME" for v in violations)

    def test_passes_specific_name(self):
        source = '''\
def parse_satellite_telemetry(raw_bytes):
    return struct.unpack(">HH", raw_bytes)
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []

    def test_configurable_list(self):
        source = '''\
def custom_bad_name(x):
    pass
'''
        custom_config = dict(CONFIG)
        custom_config["python"] = {"generic_varnames": ["custom_bad_name"]}
        violations = list(self.check.check("test.py", source, custom_config))
        assert any(v.rule == "GENERIC_VARNAME" for v in violations)


# ---------------------------------------------------------------------------
# TAG_COMMENT
# ---------------------------------------------------------------------------

class TestTagComment:
    check = TagComment()

    def test_valid_tag_passes(self):
        source = "# TODO: refactor the cache layer to use Redis\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_valid_tag_note_passes(self):
        source = "# NOTE: this is intentionally left blank for alignment\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_untagged_comment_fails(self):
        source = "# this function does important stuff\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 1
        assert violations[0].rule == "TAG_COMMENT"
        assert violations[0].severity == "warn"

    def test_inline_untagged_comment_fails(self):
        source = "x = 1  # increment counter\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 1
        assert violations[0].rule == "TAG_COMMENT"

    def test_shebang_passes(self):
        source = "#!/usr/bin/env python3\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_type_ignore_passes(self):
        source = "x = foo()  # type: ignore[assignment]\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_noqa_passes(self):
        source = "import os  # noqa: F401\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_section_divider_passes(self):
        source = "# -----------------------------------------------\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_blank_comment_passes(self):
        source = "#\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_encoding_declaration_passes(self):
        source = "# -*- coding: utf-8 -*-\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_grain_ignore_passes(self):
        source = "# grain: ignore TAG_COMMENT\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_docstring_comments_skipped(self):
        source = '''\
def foo():
    """This is a docstring.
    It has multiple lines.
    # This looks like a comment but is inside a docstring.
    """
    pass
'''
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_custom_tag_list(self):
        source = "# CUSTOM: this uses a custom tag\n"
        custom_config = {
            **CONFIG,
            "python": {**CONFIG["python"], "allowed_comment_tags": ["CUSTOM", "SPECIAL"]},
        }
        violations = list(self.check.check("test.py", source, custom_config))
        assert len(violations) == 0

    def test_custom_tag_list_rejects_default(self):
        # With custom tags, the default TODO should NOT pass
        source = "# TODO: this should fail with custom tags\n"
        custom_config = {
            **CONFIG,
            "python": {**CONFIG["python"], "allowed_comment_tags": ["CUSTOM"]},
        }
        violations = list(self.check.check("test.py", source, custom_config))
        assert len(violations) == 1
        assert "TODO" in violations[0].message

    def test_section_label_passes(self):
        source = "# Helpers\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_numbered_section_label_passes(self):
        source = "# 1. OBVIOUS_COMMENT\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_section_label_registry_passes(self):
        source = "# Registry\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 0

    def test_violation_message_is_clean(self):
        source = "# this function does important stuff\n"
        violations = list(self.check.check("test.py", source, CONFIG))
        assert len(violations) == 1
        # Message should NOT dump the full allowed tags list
        assert "['BUG'" not in violations[0].message
        assert "use # TAG: description" in violations[0].message

    def test_not_in_default_checks(self):
        # TAG_COMMENT should NOT be in the default PYTHON_CHECKS list
        from grain.checks.python_checks import PYTHON_CHECKS, OPT_IN_PYTHON_CHECKS
        default_rules = {c.rule for c in PYTHON_CHECKS}
        assert "TAG_COMMENT" not in default_rules
        assert "TAG_COMMENT" in OPT_IN_PYTHON_CHECKS

    def test_empty_file(self):
        violations = list(self.check.check("test.py", "", CONFIG))
        assert violations == []
