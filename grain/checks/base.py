"""Base types for grain checks."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Rules with safe auto-fix implementations (kept in sync with runner.SAFE_FIX_RULES)
_FIXABLE_RULES = {"OBVIOUS_COMMENT", "VAGUE_TODO", "HEDGE_WORD", "NAKED_EXCEPT"}


@dataclass
class Violation:
    path: str
    line: int
    rule: str
    message: str
    severity: str = "error"  # "error" or "warn"

    @property
    def fixable(self) -> bool:
        """True if grain --fix can resolve this violation automatically."""
        return self.rule in _FIXABLE_RULES

    def format(self) -> str:
        sev = "WARN" if self.severity == "warn" else "FAIL"
        return f"{self.path}:{self.line}  [{sev}] {self.rule}  {self.message}"

    def to_dict(self) -> dict:
        """Serialise to a dict for --json output (agentic consumption)."""
        return {
            "file": self.path,
            "line": self.line,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "fixable": self.fixable,
        }


class BaseCheck(abc.ABC):
    """Abstract base for all grain checks."""

    rule: str = ""

    @abc.abstractmethod
    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        """Yield Violations found in source."""
        ...
