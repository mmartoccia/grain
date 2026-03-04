"""Markdown-specific slop checks."""
from __future__ import annotations

import re
from typing import Iterator

from grain.checks.base import BaseCheck, Violation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_md_blocks(source: str) -> list[dict]:
    """
    Parse markdown into a flat list of block dicts:
      {"type": "header"|"para"|"bullet_list"|"table"|"other",
       "line": <1-indexed>, "content": ...}
    """
    lines = source.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Header
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped.lstrip("#").strip()
            blocks.append({"type": "header", "line": i + 1, "level": level, "content": text})
            i += 1

        # Table
        elif "|" in stripped and stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                table_lines.append({"line": i + 1, "raw": lines[i]})
                i += 1
            blocks.append({"type": "table", "line": table_lines[0]["line"], "rows": table_lines})

        # Bullet list
        elif re.match(r"^[-*+]\s", stripped) or re.match(r"^\d+\.\s", stripped):
            bullet_lines = []
            while i < len(lines):
                raw = lines[i]
                s = raw.strip()
                # Check for indented (sub-bullet) lines FIRST
                if bullet_lines and (raw.startswith("  ") or raw.startswith("\t")):
                    bullet_lines[-1]["has_sub"] = True
                    i += 1
                elif re.match(r"^[-*+]\s", s) or re.match(r"^\d+\.\s", s):
                    bullet_lines.append({"line": i + 1, "raw": raw, "content": re.sub(r"^[-*+\d.]+\s+", "", s)})
                    i += 1
                else:
                    break
            blocks.append({"type": "bullet_list", "line": bullet_lines[0]["line"], "items": bullet_lines})

        # Paragraph / other
        elif stripped:
            para_start = i
            para_lines = []
            while i < len(lines):
                s = lines[i].strip()
                # Stop at blank lines, headings, table lines (starting with |), bullets
                if not s:
                    break
                if s.startswith("#"):
                    break
                if s.startswith("|"):
                    break
                if re.match(r"^[-*+]\s", s) or re.match(r"^\d+\.\s", s):
                    break
                para_lines.append(lines[i])
                i += 1
            if para_lines:
                blocks.append({"type": "para", "line": para_start + 1, "content": " ".join(para_lines)})
            else:
                # Couldn't consume this line as para -- skip it to avoid infinite loop
                i += 1
        else:
            i += 1

    return blocks


# ---------------------------------------------------------------------------
# 1. HEDGE_WORD
# ---------------------------------------------------------------------------

_DEFAULT_HEDGE_WORDS = [
    "robust", "seamless", "leverage", "cutting-edge", "powerful",
    "you might want to", "consider using", "it's worth noting",
    "note that", "state-of-the-art", "best-in-class", "world-class",
    "game-changing", "revolutionary", "innovative", "comprehensive",
    "streamline", "empower", "synergy", "holistic",
]


class HedgeWord(BaseCheck):
    rule = "HEDGE_WORD"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        hedge_words = config.get("markdown", {}).get("hedge_words", _DEFAULT_HEDGE_WORDS)
        lines = source.splitlines()
        in_code_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Track fenced code blocks
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            # Skip indented code blocks (4-space indent)
            if line.startswith("    "):
                continue
            lower = line.lower()
            for phrase in hedge_words:
                if phrase.lower() in lower:
                    # Check for grain: ignore suppression
                    if "grain: ignore" in lower:
                        continue
                    yield Violation(
                        path=path,
                        line=i + 1,
                        rule=self.rule,
                        message=f'"{phrase}" signals AI-generated prose',
                    )
                    break  # one violation per line


# ---------------------------------------------------------------------------
# 2. THANKS_OPENER
# ---------------------------------------------------------------------------

_THANKS_PATTERN = re.compile(
    r"^\s*(?:thanks?\s+(?:you\s+)?for\s+(?:your\s+)?(?:interest|contribut\w+)|"
    r"thank\s+you\s+for\s+contribut\w+)",
    re.IGNORECASE,
)


class ThanksOpener(BaseCheck):
    rule = "THANKS_OPENER"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        # Only flag in README or CONTRIBUTING files
        import os
        basename = os.path.basename(path).upper()
        if not any(k in basename for k in ("README", "CONTRIBUTING", "CONTRIB")):
            return

        lines = source.splitlines()
        # Check first 5 non-empty lines
        checked = 0
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            if _THANKS_PATTERN.match(line):
                yield Violation(
                    path=path,
                    line=i + 1,
                    rule=self.rule,
                    message='"Thanks for your interest/contributing" opener is an AI tell',
                )
                return
            checked += 1
            if checked >= 5:
                break


# ---------------------------------------------------------------------------
# 3. OBVIOUS_HEADER
# ---------------------------------------------------------------------------

def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]+", text.lower()))


class ObviousHeader(BaseCheck):
    rule = "OBVIOUS_HEADER"

    STOPWORDS = {"the", "a", "an", "is", "are", "to", "for", "of", "in",
                 "on", "and", "or", "with", "from", "it", "this", "that",
                 "be", "as", "at", "by", "we", "you", "your", "can", "will",
                 "about", "how", "what", "when", "where", "which", "who"}

    @staticmethod
    def _token_covered(header_tok: str, content_toks: set[str]) -> bool:
        """Return True if header_tok is covered by any content token (prefix match, min 4 chars)."""
        if header_tok in content_toks:
            return True
        min_prefix = 4
        for c in content_toks:
            overlap_len = min(len(header_tok), len(c))
            if overlap_len >= min_prefix and (
                header_tok.startswith(c[:min_prefix]) or c.startswith(header_tok[:min_prefix])
            ):
                return True
        return False

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        blocks = _parse_md_blocks(source)
        for i, block in enumerate(blocks):
            if block["type"] != "header":
                continue
            # Look for the next content block
            next_block = None
            for j in range(i + 1, len(blocks)):
                if blocks[j]["type"] in ("para", "bullet_list"):
                    next_block = blocks[j]
                    break
                if blocks[j]["type"] == "header":
                    break  # another header -- no adjacent content
            if not next_block:
                continue
            header_words = _words(block["content"]) - self.STOPWORDS
            if not header_words:
                continue
            if next_block["type"] == "para":
                content_text = next_block["content"]
            else:
                content_text = " ".join(item["content"] for item in next_block["items"])
            content_words = _words(content_text) - self.STOPWORDS
            # Header is "obvious" if all its words are covered by content (with prefix matching)
            # AND the content is short (≤12 words) -- rich content is not a restatement
            content_word_count = len(content_text.split())
            if (
                header_words
                and content_word_count <= 12
                and all(self._token_covered(h, content_words) for h in header_words)
            ):
                yield Violation(
                    path=path,
                    line=block["line"],
                    rule=self.rule,
                    message=f'header "{block["content"]}" adds no navigation value -- content restates it',
                    severity="warn",
                )


# ---------------------------------------------------------------------------
# 4. BULLET_PROSE
# ---------------------------------------------------------------------------

class BulletProse(BaseCheck):
    rule = "BULLET_PROSE"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        blocks = _parse_md_blocks(source)
        for block in blocks:
            if block["type"] != "bullet_list":
                continue
            items = block["items"]
            # Criteria: < 4 items, no sub-bullets, each item < 5 words
            if len(items) >= 4:
                continue
            if any(item.get("has_sub") for item in items):
                continue
            if all(len(item["content"].split()) < 5 for item in items):
                yield Violation(
                    path=path,
                    line=block["line"],
                    rule=self.rule,
                    message="short bullet list would read better as a sentence",
                    severity="warn",
                )


# ---------------------------------------------------------------------------
# 5. TABLE_OVERKILL
# ---------------------------------------------------------------------------

def _parse_table_rows(table_rows: list[dict]) -> list[list[str]]:
    """Parse table rows into lists of cell strings, skipping separator rows."""
    rows = []
    for row in table_rows:
        raw = row["raw"].strip()
        if re.match(r"^\|[-:| ]+\|$", raw):
            continue  # separator row
        cells = [c.strip() for c in raw.strip("|").split("|")]
        rows.append(cells)
    return rows


class TableOverkill(BaseCheck):
    rule = "TABLE_OVERKILL"

    def check(self, path: str, source: str, config: dict) -> Iterator[Violation]:
        blocks = _parse_md_blocks(source)
        for block in blocks:
            if block["type"] != "table":
                continue
            rows = _parse_table_rows(block["rows"])
            if not rows:
                continue
            data_rows = rows[1:]  # skip header row
            # Check 1: only 1 data row
            if len(data_rows) == 1:
                yield Violation(
                    path=path,
                    line=block["line"],
                    rule=self.rule,
                    message="table with a single data row -- use a sentence instead",
                    severity="warn",
                )
                continue
            # Check 2: 2 columns, one column always the same value
            if not data_rows:
                continue
            num_cols = len(rows[0])
            if num_cols == 2:
                for col_idx in range(2):
                    values = [r[col_idx] for r in data_rows if len(r) > col_idx]
                    if len(set(v.lower() for v in values)) == 1:
                        yield Violation(
                            path=path,
                            line=block["line"],
                            rule=self.rule,
                            message=f"2-column table where column {col_idx + 1} is always the same value",
                            severity="warn",
                        )
                        break


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MARKDOWN_CHECKS = [
    HedgeWord(),
    ThanksOpener(),
    ObviousHeader(),
    BulletProse(),
    TableOverkill(),
]
