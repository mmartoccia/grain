"""grain config loader -- reads .grain.toml from repo root."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            tomllib = None  # type: ignore

DEFAULTS: dict[str, Any] = {
    "grain": {
        "fail_on": [
            "OBVIOUS_COMMENT",
            "NAKED_EXCEPT",
            "HEDGE_WORD",
            "VAGUE_TODO",
            "VAGUE_COMMIT",
        ],
        "warn_only": [
            "RESTATED_DOCSTRING",
            "SINGLE_IMPL_ABC",
            "BULLET_PROSE",
        ],
        "ignore": [],
        "exclude": [],
    },
    "python": {
        "generic_varnames": [
            "process_data",
            "handle_response",
            "get_result",
            "do_thing",
        ],
    },
    "markdown": {
        "hedge_words": [
            "robust",
            "seamless",
            "leverage",
            "cutting-edge",
            "powerful",
            "you might want to",
            "consider using",
            "it's worth noting",
            "note that",
        ],
    },
}


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from start looking for .grain.toml."""
    if start is None:
        start = Path.cwd()
    current = start.resolve()
    for _ in range(10):
        candidate = current / ".grain.toml"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from path (or auto-discover). Returns merged dict."""
    config = {
        "grain": dict(DEFAULTS["grain"]),
        "python": dict(DEFAULTS["python"]),
        "markdown": dict(DEFAULTS["markdown"]),
    }
    if path is None:
        path = find_config()
    if path is None or not path.exists():
        return config

    if tomllib is None:
        # No TOML parser available -- return defaults
        return config

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Merge grain section
    if "grain" in raw:
        grain_section = raw["grain"]
        for key in ("fail_on", "warn_only", "ignore", "exclude"):
            if key in grain_section:
                config["grain"][key] = grain_section[key]

    # Merge python section (nested under grain.python in TOML)
    py_section = raw.get("grain", {}).get("python", raw.get("python", {}))
    if py_section:
        config["python"].update(py_section)

    # Merge markdown section
    md_section = raw.get("grain", {}).get("markdown", raw.get("markdown", {}))
    if md_section:
        config["markdown"].update(md_section)

    return config
