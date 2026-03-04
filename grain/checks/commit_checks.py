"""Commit message slop checks."""
from __future__ import annotations

import re
from typing import Iterator

from grain.checks.base import BaseCheck, Violation

# ---------------------------------------------------------------------------
# 1. VAGUE_COMMIT
# ---------------------------------------------------------------------------

_VAGUE_SUBJECTS = re.compile(
    r"^\s*(?:update|fix\s+bug|add\s+feature|various\s+changes|misc|wip|"
    r"cleanup|clean\s+up|minor\s+changes?|small\s+fix|tweaks?|changes?|"
    r"edits?|improvements?|refactor|stuff|things?|work)\s*$",
    re.IGNORECASE,
)


class VagueCommit(BaseCheck):
    rule = "VAGUE_COMMIT"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        subject = source.splitlines()[0] if source.strip() else ""
        if _VAGUE_SUBJECTS.match(subject.strip()):
            yield Violation(
                path=path,
                line=1,
                rule=self.rule,
                message=f'"{subject.strip()}" is too generic -- describe what actually changed',
            )


# ---------------------------------------------------------------------------
# 2. AND_COMMIT
# ---------------------------------------------------------------------------

class AndCommit(BaseCheck):
    rule = "AND_COMMIT"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        subject = source.splitlines()[0] if source.strip() else ""
        # Match " and " as a connector (case-insensitive), not as part of a word
        if re.search(r"\band\b", subject, re.IGNORECASE):
            yield Violation(
                path=path,
                line=1,
                rule=self.rule,
                message=f'commit subject contains "and" -- do one thing per commit',
            )


# ---------------------------------------------------------------------------
# 3. NO_CONTEXT
# ---------------------------------------------------------------------------

# Conventional commit type prefixes that should have a body or detailed subject
_CONVENTIONAL_PREFIXES = re.compile(
    r"^(?:fix|feat|chore|refactor|perf|test|docs|style|ci|build)(?:\([^)]+\))?:\s*(.+)",
    re.IGNORECASE,
)

# Subjects that are *just* a type label with minimal info
_BARE_SUBJECT = re.compile(
    r"^(?:fix|feat|chore|refactor|perf|test|docs|style|ci|build)(?:\([^)]+\))?:\s*\S.*$",
    re.IGNORECASE,
)

_TOO_SHORT_BODY = re.compile(
    r"^(?:fix|feat)(?:\([^)]+\))?:\s*(?:\w+\s*){1,3}$",
    re.IGNORECASE,
)


class NoContext(BaseCheck):
    rule = "NO_CONTEXT"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        all_lines = source.splitlines()
        lines = [l for l in all_lines if l.strip() and not l.strip().startswith("#")]
        if not lines:
            return
        subject = lines[0]
        m = _CONVENTIONAL_PREFIXES.match(subject)
        if not m:
            return
        body_text = m.group(1).strip()
        word_count = len(body_text.split())
        # Check: does the commit have a description paragraph (blank line then content)?
        has_body = (
            len(all_lines) > 2
            and not all_lines[1].strip()  # blank separator line
            and any(l.strip() for l in all_lines[2:] if not l.strip().startswith("#"))
        )
        # Flag if the subject is very short AND there's no body paragraph
        if word_count <= 3 and not has_body:
            yield Violation(
                path=path,
                line=1,
                rule=self.rule,
                message=f'"{subject.strip()}" -- describe *what* changed, not just the type',
            )
        elif word_count in (4, 5) and not has_body:
            yield Violation(
                path=path,
                line=1,
                rule=self.rule,
                message=f'"{subject.strip()}" -- no description body; add context on *why* this changed',
            )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

COMMIT_CHECKS = [
    VagueCommit(),
    AndCommit(),
    NoContext(),
]
