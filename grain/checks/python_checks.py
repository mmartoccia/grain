"""Python-specific slop checks."""
from __future__ import annotations

import ast
import re
import tokenize
import io
from typing import Iterator

from grain.checks.base import BaseCheck, Violation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize_words(text: str) -> set[str]:
    """Lower-case word tokens from arbitrary text."""
    return set(re.findall(r"[a-zA-Z]+", text.lower()))


def _snake_to_words(name: str) -> set[str]:
    """Split snake_case / CamelCase into word set."""
    # CamelCase split
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
    return set(w for w in name.lower().split("_") if w)


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Simple suffix-stripping stemmer for docstring/name comparison
_STEM_SUFFIXES = [
    ("ations", 4), ("izing", 3), ("ation", 4), ("izes", 3), ("ized", 3),
    ("ing", 3), ("ion", 3), ("or", 3), ("er", 3), ("ed", 3), ("es", 3), ("s", 3),
]


def _stem(word: str) -> str:
    for suffix, min_root in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_root:
            return word[: -len(suffix)]
    return word


def _stem_set(words: set[str]) -> set[str]:
    return {_stem(w) for w in words}


# ---------------------------------------------------------------------------
# 1. OBVIOUS_COMMENT
# ---------------------------------------------------------------------------

class ObviousComment(BaseCheck):
    rule = "OBVIOUS_COMMENT"

    # Stopwords to ignore in overlap calculation
    STOPWORDS = {"the", "a", "an", "is", "are", "was", "to", "for", "of",
                 "in", "on", "and", "or", "with", "from", "that", "this",
                 "it", "be", "as", "by", "at", "we", "self", "return",
                 "if", "else", "def", "class", "import", "not", "new"}

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        lines = source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            comment_text = stripped.lstrip("#").strip()
            # Skip suppression comments
            if "grain: ignore" in comment_text.lower() or "noqa" in comment_text.lower():
                continue
            # Look at the *next* non-blank line
            next_line = ""
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                if candidate and not candidate.startswith("#"):
                    next_line = candidate
                    break
            if not next_line:
                continue
            comment_words = _tokenize_words(comment_text) - self.STOPWORDS
            code_words = _tokenize_words(next_line) - self.STOPWORDS
            if not comment_words or not code_words:
                continue
            ratio = _overlap_ratio(comment_words, code_words)
            if ratio >= 0.6:
                yield Violation(
                    path=path,
                    line=i + 1,
                    rule=self.rule,
                    message=f'"{comment_text}" restates the following line',
                )


# ---------------------------------------------------------------------------
# 2. NAKED_EXCEPT
# ---------------------------------------------------------------------------

class NakedExcept(BaseCheck):
    rule = "NAKED_EXCEPT"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # Bare `except:` or `except Exception`/`except BaseException`
            is_broad = (
                node.type is None
                or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in ("Exception", "BaseException")
                )
                or (
                    isinstance(node.type, ast.Attribute)
                    and node.type.attr in ("Exception", "BaseException")
                )
            )
            if not is_broad:
                continue
            # Check if body contains a re-raise
            has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(ast.Module(body=node.body, type_ignores=[])))
            if not has_raise:
                yield Violation(
                    path=path,
                    line=node.lineno,
                    rule=self.rule,
                    message="broad except clause with no re-raise -- swallows unexpected errors",
                )


# ---------------------------------------------------------------------------
# 3. RESTATED_DOCSTRING
# ---------------------------------------------------------------------------

class RestatedDocstring(BaseCheck):
    rule = "RESTATED_DOCSTRING"

    # Keep action verbs OUT of stopwords so they get stemmed to match function name tokens.
    # But structural wrapper words ("class", "function", "method") are safe to suppress.
    STOPWORDS = {"the", "a", "an", "is", "are", "was", "to", "for", "of",
                 "in", "on", "and", "or", "with", "from", "that", "this",
                 "it", "be", "as", "by", "at", "used", "instance",
                 "class", "function", "method", "object", "simple", "basic"}

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            name_words = _snake_to_words(node.name) - self.STOPWORDS
            # Take only first sentence of docstring for comparison
            first_sentence = re.split(r"[.!?\n]", docstring)[0]
            doc_words = _tokenize_words(first_sentence) - self.STOPWORDS
            if not name_words or not doc_words:
                continue
            # Use stemmed comparison for better recall (gets→get, processor→process)
            name_stems = _stem_set(name_words)
            doc_stems = _stem_set(doc_words)
            ratio = _overlap_ratio(name_stems, doc_stems)
            if ratio >= 0.7:
                yield Violation(
                    path=path,
                    line=node.lineno,
                    rule=self.rule,
                    message=f'docstring for "{node.name}" just restates the name',
                    severity="warn",
                )


# ---------------------------------------------------------------------------
# 4. VAGUE_TODO
# ---------------------------------------------------------------------------

_VAGUE_TODO_PATTERN = re.compile(
    r"#\s*(?:TODO|FIXME|HACK|XXX)\s*:?\s*(.+)", re.IGNORECASE
)

# Generic vague phrases -- presence alone is NOT a pass; absence of specifics is the flag
_VAGUE_PHRASES = re.compile(
    r"\b(implement\s+this|add\s+error\s+handling|improve\s+performance|"
    r"fix\s+this|handle\s+this|update\s+this|clean\s+up|refactor\s+this|"
    r"make\s+this\s+better|optimize\s+this|do\s+this|finish\s+this|"
    r"add\s+logging|add\s+tests|add\s+validation|handle\s+edge\s+cases)\b",
    re.IGNORECASE,
)

# Indicators of specificity: numbers, library/model names, parentheticals, etc.
_SPECIFIC_INDICATORS = re.compile(
    r"(\d+[A-Za-z%]+|~\d+|v\d|https?://|\(.*?\)|\busing\b.*\b\w{5,}\b|"
    r"\breplace\b|\bswitch\b|\bport\b|\bmigrate\b|\bbackfill\b|\bsee\b|\bref\b|"
    r"\bbecause\b|\bdue\s+to\b|\bblocked\s+by\b|\bwaiting\s+on\b|"
    r"\buntil\b|\bafter\b|\bonce\b|\bwhen\b)",
    re.IGNORECASE,
)


class VagueTodo(BaseCheck):
    rule = "VAGUE_TODO"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        lines = source.splitlines()
        for i, line in enumerate(lines):
            m = _VAGUE_TODO_PATTERN.search(line)
            if not m:
                continue
            body = m.group(1).strip()
            # Skip suppression
            if "grain: ignore" in body.lower():
                continue
            # Fail if body is a vague phrase OR lacks specific indicators
            is_vague = bool(_VAGUE_PHRASES.search(body))
            has_specific = bool(_SPECIFIC_INDICATORS.search(body)) and len(body.split()) > 4
            if is_vague or not has_specific:
                yield Violation(
                    path=path,
                    line=i + 1,
                    rule=self.rule,
                    message=f'TODO lacks specific approach or reason: "{body}"',
                )


# ---------------------------------------------------------------------------
# 5. SINGLE_IMPL_ABC
# ---------------------------------------------------------------------------

class SingleImplAbc(BaseCheck):
    rule = "SINGLE_IMPL_ABC"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        # Identify ABCs: inherit from ABC or ABCMeta, or have @abstractmethod members
        def is_abc(cls: ast.ClassDef) -> bool:
            for base in cls.bases:
                name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if name in ("ABC", "ABCMeta"):
                    return True
            for node in ast.walk(cls):
                if isinstance(node, ast.FunctionDef):
                    for dec in node.decorator_list:
                        dec_name = dec.id if isinstance(dec, ast.Name) else getattr(dec, "attr", "")
                        if dec_name == "abstractmethod":
                            return True
            return False

        abc_names = {cls.name for cls in classes if is_abc(cls)}

        for abc_cls in abc_names:
            # Find concrete subclasses (inherit from this ABC, don't themselves have abstractmethods)
            concrete = [
                cls for cls in classes
                if cls.name != abc_cls
                and any(
                    (isinstance(b, ast.Name) and b.id == abc_cls) or
                    (isinstance(b, ast.Attribute) and b.attr == abc_cls)
                    for b in cls.bases
                )
                and not is_abc(cls)
            ]
            if len(concrete) == 1:
                abc_node = next(c for c in classes if c.name == abc_cls)
                yield Violation(
                    path=path,
                    line=abc_node.lineno,
                    rule=self.rule,
                    message=f'"{abc_cls}" has exactly one concrete implementation ("{concrete[0].name}") -- premature abstraction',
                    severity="warn",
                )


# ---------------------------------------------------------------------------
# 6. GENERIC_VARNAME
# ---------------------------------------------------------------------------

_DEFAULT_GENERIC = {
    "process_data", "handle_response", "get_result", "do_thing",
    "process_input", "handle_data", "get_data", "process_response",
    "handle_input", "do_stuff", "do_work",
}


class GenericVarname(BaseCheck):
    rule = "GENERIC_VARNAME"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        generic = set(config.get("python", {}).get("generic_varnames", [])) | _DEFAULT_GENERIC

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in generic:
                    yield Violation(
                        path=path,
                        line=node.lineno,
                        rule=self.rule,
                        message=f'"{node.name}" is a generic AI-filler function name',
                    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PYTHON_CHECKS = [
    ObviousComment(),
    NakedExcept(),
    RestatedDocstring(),
    VagueTodo(),
    SingleImplAbc(),
    GenericVarname(),
]
