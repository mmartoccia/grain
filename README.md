# grain

Anti-slop linter for AI-assisted codebases. Detects AI-generated code and documentation patterns before they land in version control.

## What it does

AI code has tells. `grain` flags them so a human can decide whether to keep, rewrite, or suppress.

## Why not ruff / pylint / semgrep?

Those tools check syntax, style, types, and known bug patterns. They're essential. grain doesn't replace them.

grain catches **behavioral patterns specific to AI code generation** that traditional linters miss:

- **Silent exception swallowing** -- AI wraps everything in try/except with no re-raise. ruff has `E722` for bare except, but doesn't check whether the handler re-raises or just logs and moves on.
- **Docstring padding** -- AI restates the function name as a sentence and calls it documentation. No existing linter flags this.
- **Hedge words** -- filler words in docs that signal AI-generated prose saying nothing. No linter checks for this.
- **Echo comments** -- comments that restate the next line of code. AI adds these reflexively. Existing linters check comment *style*, not *content*.
- **Vague TODOs** -- "implement this" with no approach. Traditional linters flag missing TODOs, not empty ones.

semgrep can do custom pattern matching, but requires writing YAML rules per pattern. grain ships with these rules built-in and adds `.grain.toml` for custom patterns without learning a new DSL.

Run grain alongside ruff/pylint. They solve different problems.

## Quick start

```bash
pip install grain-lint   # from PyPI
pip install -e .         # from source
```

## Usage

```bash
grain check [files...]      # check specific files
grain check --all           # check entire repo
grain check --fix           # auto-fix safe violations in place
grain install               # install git hooks into .git/hooks/
grain status                # show current config and enabled checks
grain suppress FILE:LINE RULE  # add inline suppression comment
```

## Checks

### Python

| Rule | Severity | Description |
|------|----------|-------------|
| OBVIOUS_COMMENT | error | comment restates the following line |
| NAKED_EXCEPT | error | broad except clause with no re-raise |
| RESTATED_DOCSTRING | warn | docstring just expands the function/class name |
| VAGUE_TODO | error | TODO without specific approach or reason |
| SINGLE_IMPL_ABC | warn | ABC with exactly one concrete implementation |
| GENERIC_VARNAME | error | function named with AI filler (process_data, etc.) |
| TAG_COMMENT | warn | untagged comment -- requires `# TAG: description` format (opt-in) |

### Markdown

| Rule | Severity | Description |
|------|----------|-------------|
| HEDGE_WORD | error | AI filler words -- see `hedge_words` in config |
| THANKS_OPENER | error | README/CONTRIBUTING opens with "Thanks for contributing" |
| OBVIOUS_HEADER | warn | header content fully restated in following paragraph |
| BULLET_PROSE | warn | short bullet list that reads better as a sentence |
| TABLE_OVERKILL | warn | table with 1 row or constant column |

### Commit messages

| Rule | Severity | Description |
|------|----------|-------------|
| VAGUE_COMMIT | error | subject too generic (update, fix bug, wip...) |
| AND_COMMIT | error | subject contains "and" -- do one thing per commit |
| NO_CONTEXT | error | fix/feat with no description of what changed |

## Config

Create `.grain.toml` in your repo root:

```toml
[grain]
fail_on = ["OBVIOUS_COMMENT", "NAKED_EXCEPT", "HEDGE_WORD", "VAGUE_TODO", "VAGUE_COMMIT"]
warn_only = ["RESTATED_DOCSTRING", "SINGLE_IMPL_ABC", "BULLET_PROSE"]
ignore = []
exclude = ["tests/*", "migrations/*"]

[grain.python]
generic_varnames = ["process_data", "handle_response", "get_result", "do_thing"]
# allowed_comment_tags = ["TODO", "BUG", "FIX", "PERF", "NOTE", "HACK", "FIXME", "XXX", "SAFETY", "REVIEW"]

[grain.markdown]
hedge_words = ["robust", "seamless", "leverage", "cutting-edge", "powerful",
               "you might want to", "consider using", "it's worth noting", "note that"]
```

## Custom Rules

Define your own pattern-matching rules in `.grain.toml`. Each custom rule has a name, a regex pattern, a file glob, a message, and an optional severity. grain evaluates them alongside built-in rules.

```toml
[[grain.custom_rules]]
name = "CONST_SETTING"
pattern = '^\s*[A-Z_]{2,}\s*=\s*\d+'
files = "*.py"
message = "top-level constant assignment -- use config or env vars"
severity = "warn"

[[grain.custom_rules]]
name = "PRINT_DEBUG"
pattern = '^\s*print\s*\('
files = "*.py"
message = "print() call -- use logging instead"
severity = "error"

[[grain.custom_rules]]
name = "FIXME_DEADLINE"
pattern = 'FIXME(?!.*\d{4}-\d{2}-\d{2})'
files = "*.py"
message = "FIXME without a deadline date (YYYY-MM-DD)"
severity = "warn"
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Uppercase + underscores (e.g. `MY_RULE`) |
| `pattern` | yes | Python regex, matched per-line |
| `files` | yes | File glob (e.g. `*.py`, `*.md`) |
| `message` | yes | Human-readable violation message |
| `severity` | no | `"warn"` (default) or `"error"` |

Custom rule names work with `ignore`, `fail_on`, and `warn_only` just like built-in rules. Invalid rules (bad regex, missing fields) are skipped with a warning.

## Opt-in rules

Some rules are strict enough that they're off by default. Add them to `warn_only` or `fail_on` in `.grain.toml` to activate:

```toml
[grain]
warn_only = ["TAG_COMMENT"]
```

**TAG_COMMENT** requires every comment to use a structured tag format (`# TODO: ...`, `# NOTE: ...`, etc.). Section headers, dividers, shebangs, `type: ignore`, and `noqa` are automatically skipped.

## Suppression

Add `# grain: ignore RULE_NAME` to the offending line:

```python
except Exception as e:  # grain: ignore NAKED_EXCEPT
    pass  # intentional -- this is a top-level catch
```

Or use the CLI:

```bash
grain suppress src/main.py:42 NAKED_EXCEPT
```

## pre-commit framework

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/mmartoccia/grain
    rev: v0.3.0
    hooks:
      - id: grain
```

## FAQ

**What's the false positive rate?**
Depends on the rule. NAKED_EXCEPT and VAGUE_TODO have near-zero false positives. OBVIOUS_COMMENT and RESTATED_DOCSTRING occasionally flag legitimate comments where overlap is coincidental. Use `# grain: ignore RULE_NAME` for those cases, or adjust thresholds in the source.

**Does grain support auto-fix?**
Yes. `grain check --fix` auto-fixes safe rules (OBVIOUS_COMMENT removal, VAGUE_TODO annotation). Rules requiring judgment (NAKED_EXCEPT, RESTATED_DOCSTRING) are reported but not auto-fixed.

**Can I write custom rules without learning semgrep YAML?**
Yes. Custom rules use simple regex + file glob in `.grain.toml`. See the Custom Rules section above.

**Does grain work with pre-commit?**
Yes. See the pre-commit section. The `--fix` flag is not recommended in pre-commit hooks (fixes should be reviewed, not auto-applied in CI).

**Python only?**
For now. The architecture supports adding language-specific check modules. PRs welcome.

## Output format

```
path/to/file.py:42  [FAIL] OBVIOUS_COMMENT  "# return result" restates the following line
path/to/README.md:7  [FAIL] HEDGE_WORD  "robust" signals AI-generated prose
```

Exit 0 = clean. Exit 1 = errors found (pre-commit blocks the commit).
