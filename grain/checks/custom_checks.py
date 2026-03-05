"""Custom regex-based checks loaded from .grain.toml."""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Iterator

from grain.checks.base import BaseCheck, Violation

logger = logging.getLogger(__name__)


class CustomRegexCheck(BaseCheck):
    """A user-defined regex check loaded from [[grain.custom_rules]]."""

    def __init__(
        self,
        name: str,
        pattern: re.Pattern,
        files: str,
        message: str,
        severity: str = "warn",
    ) -> None:
        self.rule = name
        self.pattern = pattern
        self.files_glob = files
        self._message = message
        self.default_severity = severity

    def matches_file(self, filepath: str) -> bool:
        """Check if filepath matches this rule's file glob."""
        # Match against basename and full path
        basename = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
        return fnmatch.fnmatch(basename, self.files_glob) or fnmatch.fnmatch(filepath, self.files_glob)

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        """Yield Violations for lines matching the regex pattern."""
        for lineno, line in enumerate(source.splitlines(), start=1):
            if self.pattern.search(line):
                # Respect inline suppression
                if "grain: ignore" in line.lower():
                    continue
                yield Violation(
                    path=path,
                    line=lineno,
                    rule=self.rule,
                    message=self._message,
                    severity=self.default_severity,
                )


def load_custom_rules(config: dict) -> list[CustomRegexCheck]:
    """Parse [[grain.custom_rules]] from config, return list of check instances.

    Invalid rules are logged and skipped.
    """
    raw_rules = config.get("grain", {}).get("custom_rules", [])
    checks: list[CustomRegexCheck] = []

    for i, rule in enumerate(raw_rules):
        # Validate required fields
        missing = [f for f in ("name", "pattern", "files", "message") if f not in rule]
        if missing:
            logger.warning(
                "Custom rule #%d: skipping -- missing required fields: %s",
                i + 1,
                ", ".join(missing),
            )
            continue

        name = rule["name"]
        # Validate name format: uppercase letters and underscores only
        if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
            logger.warning(
                "Custom rule #%d (%r): skipping -- name must be uppercase letters, digits, and underscores",
                i + 1,
                name,
            )
            continue

        # Validate regex
        try:
            pattern = re.compile(rule["pattern"])
        except re.error as e:
            logger.warning(
                "Custom rule #%d (%s): skipping -- invalid regex: %s",
                i + 1,
                name,
                e,
            )
            continue

        severity = rule.get("severity", "warn")
        if severity not in ("warn", "error"):
            logger.warning(
                "Custom rule #%d (%s): invalid severity %r, defaulting to 'warn'",
                i + 1,
                name,
                severity,
            )
            severity = "warn"

        checks.append(
            CustomRegexCheck(
                name=name,
                pattern=pattern,
                files=rule["files"],
                message=rule["message"],
                severity=severity,
            )
        )

    return checks
