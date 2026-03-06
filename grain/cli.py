"""grain CLI entry point."""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

from grain.config import load_config, find_config
from grain.runner import (
    run_checks,
    format_violations,
    determine_exit_code,
    apply_fixes,
    _get_staged_files,
    _get_all_files,
)


# ---------------------------------------------------------------------------
# Subcommand: check
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    config = load_config()

    if args.all:
        files = _get_all_files(Path.cwd())
    elif args.files:
        files = args.files
    else:
        files = _get_staged_files()
        if not files:
            print("grain: no staged files to check (use --all to check everything)")
            return 0

    files = [f for f in files if f.endswith((".py", ".md", ".markdown"))]
    if not files:
        print("grain: no .py or .md files to check")
        return 0

    violations = run_checks(files, config)

    if args.fix and violations:
        fix_messages, remaining = apply_fixes(files, violations, config)
        for msg in fix_messages:
            print(msg)
        if fix_messages and remaining:
            print()
        violations = remaining

    if getattr(args, "json", False):
        import json as _json
        payload = [v.to_dict() for v in violations]
        print(_json.dumps(payload, indent=2))
        return determine_exit_code(violations)

    output = format_violations(violations)
    print(output, end="")
    return determine_exit_code(violations)


# ---------------------------------------------------------------------------
# Subcommand: commit-msg
# ---------------------------------------------------------------------------

def cmd_commit_msg(args: argparse.Namespace) -> int:
    config = load_config()
    msg_file = args.msg_file
    try:
        commit_msg = Path(msg_file).read_text(encoding="utf-8")
    except OSError as e:
        print(f"grain: cannot read commit message file: {e}", file=sys.stderr)
        return 1

    violations = run_checks([], config, commit_msg=commit_msg)
    output = format_violations(violations)
    print(output, end="")
    return determine_exit_code(violations)


# ---------------------------------------------------------------------------
# Subcommand: install
# ---------------------------------------------------------------------------

_PRE_COMMIT_HOOK = """\
#!/bin/sh
# grain pre-commit hook -- installed by `grain install`
exec grain check
"""

_COMMIT_MSG_HOOK = """\
#!/bin/sh
# grain commit-msg hook -- installed by `grain install`
exec grain commit-msg "$1"
"""


def cmd_install(args: argparse.Namespace) -> int:
    hooks_dir = Path(".git") / "hooks"
    if not hooks_dir.exists():
        print("grain: .git/hooks not found -- are you in a git repo?", file=sys.stderr)
        return 1

    for name, content in [("pre-commit", _PRE_COMMIT_HOOK), ("commit-msg", _COMMIT_MSG_HOOK)]:
        hook_path = hooks_dir / name
        if hook_path.exists() and not args.force:
            print(f"grain: {hook_path} already exists (use --force to overwrite)")
            continue
        hook_path.write_text(content)
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"grain: installed {hook_path}")

    return 0


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    config = load_config()
    cfg_path = find_config()

    print(f"grain v0.1.2")
    print(f"config: {cfg_path or '(defaults -- no .grain.toml found)'}")
    print()
    print(f"fail_on:   {', '.join(config['grain']['fail_on']) or '(none)'}")
    print(f"warn_only: {', '.join(config['grain']['warn_only']) or '(none)'}")
    print(f"ignore:    {', '.join(config['grain']['ignore']) or '(none)'}")
    exclude = config["grain"].get("exclude", [])
    if exclude:
        print(f"exclude:   {', '.join(exclude)}")
    else:
        print(f"exclude:   (none)")
    test_patterns = config["grain"].get("test_patterns", ["test_*.py", "*_test.py", "tests/*"])
    print(f"test_patterns: {', '.join(test_patterns)}")
    print()
    print("Python generic varnames:", ", ".join(config["python"]["generic_varnames"]))
    print("Markdown hedge words:", ", ".join(config["markdown"]["hedge_words"]))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: suppress
# ---------------------------------------------------------------------------

def cmd_suppress(args: argparse.Namespace) -> int:
    """Add inline suppression comment to a file at a given line."""
    location = args.location  # FILE:LINE
    rule = args.rule

    try:
        filepath, lineno_str = location.rsplit(":", 1)
        lineno = int(lineno_str)
    except ValueError:
        print(f"grain: invalid location format '{location}' -- use FILE:LINE", file=sys.stderr)
        return 1

    path = Path(filepath)
    if not path.exists():
        print(f"grain: file not found: {filepath}", file=sys.stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    if lineno < 1 or lineno > len(lines):
        print(f"grain: line {lineno} out of range for {filepath}", file=sys.stderr)
        return 1

    target = lines[lineno - 1]
    if "grain: ignore" in target:
        print(f"grain: {filepath}:{lineno} already has suppression")
        return 0

    lines[lineno - 1] = target.rstrip() + f"  # grain: ignore {rule}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"grain: suppressed {rule} at {filepath}:{lineno}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: worklog  (agentic repair state tracker)
# ---------------------------------------------------------------------------

import json as _json

_WORKLOG_FILE = ".grain-worklog.json"


def _load_worklog() -> dict:
    p = Path(_WORKLOG_FILE)
    if not p.exists():
        return {}
    try:
        return _json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"grain: cannot read worklog: {e}", file=sys.stderr)
        return {}


def _save_worklog(data: dict) -> None:
    Path(_WORKLOG_FILE).write_text(_json.dumps(data, indent=2), encoding="utf-8")


def cmd_worklog(args: argparse.Namespace) -> int:
    cmd = getattr(args, "worklog_cmd", None)

    if cmd == "init":
        config = load_config()
        files = _get_all_files(Path.cwd())
        files = [f for f in files if f.endswith((".py", ".md", ".markdown"))]
        violations = run_checks(files, config)
        entries = [v.to_dict() for v in violations]
        for e in entries:
            e["resolved"] = False
        data = {
            "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "total": len(entries),
            "violations": entries,
        }
        _save_worklog(data)
        print(f"grain worklog: captured {len(entries)} violations -> {_WORKLOG_FILE}")
        fixable = sum(1 for e in entries if e["fixable"])
        print(f"  {fixable} auto-fixable  |  {len(entries) - fixable} require judgment")
        return 0

    if cmd == "status":
        data = _load_worklog()
        if not data:
            print("grain worklog: no worklog found -- run `grain worklog init`")
            return 1
        violations = data.get("violations", [])
        total = len(violations)
        resolved = sum(1 for v in violations if v.get("resolved"))
        remaining = total - resolved
        fixable_remaining = sum(1 for v in violations if not v.get("resolved") and v.get("fixable"))
        print(f"grain worklog: {resolved}/{total} resolved  |  {remaining} remaining  ({fixable_remaining} auto-fixable)")
        if remaining:
            by_rule: dict[str, int] = {}
            for v in violations:
                if not v.get("resolved"):
                    by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1
            for rule, count in sorted(by_rule.items(), key=lambda x: -x[1]):
                print(f"  {count:4d}  {rule}")
        return 0

    if cmd == "next":
        data = _load_worklog()
        violations = data.get("violations", [])
        for v in violations:
            if not v.get("resolved"):
                print(_json.dumps(v, indent=2))
                return 0
        print(_json.dumps(None))
        return 0

    if cmd == "done":
        data = _load_worklog()
        violations = data.get("violations", [])
        matched = 0
        for v in violations:
            if v["file"] == args.file and v["line"] == args.line and v["rule"] == args.rule:
                v["resolved"] = True
                matched += 1
        if not matched:
            print(f"grain worklog: no matching violation found for {args.file}:{args.line} {args.rule}", file=sys.stderr)
            return 1
        _save_worklog(data)
        resolved = sum(1 for v in violations if v.get("resolved"))
        print(f"grain worklog: marked resolved ({resolved}/{len(violations)} total)")
        return 0

    # No subcommand -- show help
    print("usage: grain worklog {init,status,next,done}")
    return 1


# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------

_GENERATED_DIR_MARKERS = [
    # Reports / scraped content
    ("reports", "*/reports/*"),
    ("posts", "*/posts/*"),
    ("papers", "*/papers/*"),
    ("transcripts", "*/transcripts/*"),
    ("briefings", "briefings/*"),
    # Test directories
    ("tests", "tests/*"),
    # Common build/cache dirs
    ("dist", "dist/*"),
    ("build", "build/*"),
    ("node_modules", "node_modules/*"),
    (".venv", ".venv/*"),
]

def cmd_init(args: argparse.Namespace) -> int:
    dest = Path(".grain.toml")
    if dest.exists():
        print("grain: .grain.toml already exists -- not overwriting. Edit it manually.")
        return 1

    # Auto-detect generated directories present in repo
    detected_excludes: list[str] = []
    for dirname, pattern in _GENERATED_DIR_MARKERS:
        if any(Path(".").rglob(dirname)):
            detected_excludes.append(f'  "{pattern}",')

    exclude_block = "\n".join(detected_excludes) if detected_excludes else '  # "generated/*",'

    toml = f"""\
[grain]
fail_on   = ["OBVIOUS_COMMENT", "NAKED_EXCEPT", "HEDGE_WORD", "VAGUE_TODO", "VAGUE_COMMIT"]
warn_only = ["RESTATED_DOCSTRING", "SINGLE_IMPL_ABC", "BULLET_PROSE"]

# Paths to skip entirely (fnmatch patterns, relative to repo root).
# grain init auto-detected the following directories:
exclude = [
{exclude_block}
]

# Test file patterns -- NAKED_EXCEPT is exempt in these files.
# test_patterns = ["test_*.py", "*_test.py", "tests/*"]
"""

    dest.write_text(toml, encoding="utf-8")
    print(f"grain: created .grain.toml")
    if detected_excludes:
        print(f"grain: auto-detected {len(detected_excludes)} generated directories -- review exclude list")
    print("grain: run `grain status` to verify config")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="grain",
        description="Anti-slop linter for AI-assisted codebases",
    )
    sub = parser.add_subparsers(dest="command")

    # check
    p_check = sub.add_parser("check", help="Check files for slop")
    p_check.add_argument("files", nargs="*", help="Files to check (default: staged files)")
    p_check.add_argument("--all", action="store_true", help="Check all .py and .md files in repo")
    p_check.add_argument("--fix", action="store_true", help="Auto-fix safe violations in place")
    p_check.add_argument("--json", action="store_true", help="Emit violations as JSON (for agentic workflows)")

    # commit-msg
    p_cmsg = sub.add_parser("commit-msg", help="Check a commit message file")
    p_cmsg.add_argument("msg_file", help="Path to commit message file (e.g. .git/COMMIT_EDITMSG)")

    # install
    p_install = sub.add_parser("install", help="Install git hooks")
    p_install.add_argument("--force", action="store_true", help="Overwrite existing hooks")

    # status
    sub.add_parser("status", help="Show current config and enabled checks")

    # init
    sub.add_parser("init", help="Scaffold a .grain.toml for this repo")

    # worklog
    p_wl = sub.add_parser("worklog", help="Manage agentic repair worklog (.grain-worklog.json)")
    wl_sub = p_wl.add_subparsers(dest="worklog_cmd")
    wl_sub.add_parser("init", help="Snapshot current violations into worklog")
    wl_sub.add_parser("status", help="Show worklog progress (total, fixed, remaining)")
    wl_sub.add_parser("next", help="Print next unfixed violation as JSON")
    p_wl_done = wl_sub.add_parser("done", help="Mark a violation resolved")
    p_wl_done.add_argument("file", help="File path")
    p_wl_done.add_argument("line", type=int, help="Line number")
    p_wl_done.add_argument("rule", help="Rule name")

    # suppress
    p_sup = sub.add_parser("suppress", help="Add inline suppression for a rule at a location")
    p_sup.add_argument("location", help="FILE:LINE")
    p_sup.add_argument("rule", help="Rule name to suppress (e.g. OBVIOUS_COMMENT)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "check": cmd_check,
        "commit-msg": cmd_commit_msg,
        "install": cmd_install,
        "status": cmd_status,
        "init": cmd_init,
        "worklog": cmd_worklog,
        "suppress": cmd_suppress,
    }

    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
