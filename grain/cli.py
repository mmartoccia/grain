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

    # Filter by extension
    files = [f for f in files if f.endswith((".py", ".md", ".markdown"))]
    if not files:
        print("grain: no .py or .md files to check")
        return 0

    violations = run_checks(files, config)
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

    # commit-msg
    p_cmsg = sub.add_parser("commit-msg", help="Check a commit message file")
    p_cmsg.add_argument("msg_file", help="Path to commit message file (e.g. .git/COMMIT_EDITMSG)")

    # install
    p_install = sub.add_parser("install", help="Install git hooks")
    p_install.add_argument("--force", action="store_true", help="Overwrite existing hooks")

    # status
    sub.add_parser("status", help="Show current config and enabled checks")

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
        "suppress": cmd_suppress,
    }

    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
