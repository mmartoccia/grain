"""Base types for grain checks."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class Violation:
    path: str
    line: int
    rule: str
    message: str
    severity: str = "error"  # "error" or "warn"

    def format(self) -> str:
        sev = "WARN" if self.severity == "warn" else "FAIL"
        return f"{self.path}:{self.line}  [{sev}] {self.rule}  {self.message}"


class BaseCheck(abc.ABC):
    """Abstract base for all grain checks."""

    rule: str = ""

    @abc.abstractmethod
    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        """Yield Violations found in source."""
        ...
