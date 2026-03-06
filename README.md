# grain

**Anti-slop linter for AI-assisted codebases.**

Detects AI-generated code patterns before they land in version control -- and generates structured work queues so AI agents can repair them automatically.

---

## The loop

```
grain check --all --json > violations.json   # scan
↓
AI agent reads violations.json               # plan
↓
agent fixes file by file, re-runs grain      # execute
↓
grain check --all --json                     # verify
↓
exit when empty                              # done
```

Grain is designed for both sides of this loop: it's the quality gate *and* the task queue. Most linters are human-facing gates. Grain is built to drive agentic remediation workflows.

---

## Agentic workflow

### `--json` output

```bash
grain check --all --json
```

Emits structured violations instead of human-readable text:

```json
[
  {
    "file": "scripts/daemon.py",
    "line": 54,
    "rule": "NAKED_EXCEPT",
    "severity": "error",
    "message": "broad except clause with no re-raise -- swallows unexpected errors",
    "fixable": true
  }
]
```

Every violation includes `fixable: bool`. An agent can filter `fixable: false` (judgment calls) for human review while batch-processing the rest automatically.

### `grain worklog` -- multi-session repair state

For large codebases (hundreds of violations), repair may span multiple agent runs or agent crashes. The worklog tracks progress across sessions so agents don't re-examine already-clean files.

```bash
grain worklog init      # snapshot current violations -> .grain-worklog.json
grain worklog status    # progress: 42/738 resolved, 696 remaining (412 auto-fixable)
grain worklog next      # print next unresolved violation as JSON
grain worklog done FILE LINE RULE  # mark a violation resolved
```

**Agent loop using worklog:**

```bash
grain worklog init
while true; do
  next=$(grain worklog next)
  [ "$next" = "null" ] && break
  # agent fixes the violation
  grain worklog done "$file" "$line" "$rule"
done
grain check --all  # final verification
```

The worklog survives agent restarts and can be committed alongside the codebase to coordinate multiple agents on the same repair effort.

---

## What it detects

AI code has tells. `grain` flags them so humans -- or agents -- can decide whether to keep, rewrite, or suppress.

### Python

| Rule | Severity | Auto-fix | Description |
|------|----------|----------|-------------|
| OBVIOUS_COMMENT | error | ✅ | comment restates the following line |
| NAKED_EXCEPT | error | ✅ | broad except clause with no re-raise |
| RESTATED_DOCSTRING | warn | ❌ | docstring just expands the function/class name |
| VAGUE_TODO | error | ✅ | TODO without specific approach or reason |
| SINGLE_IMPL_ABC | warn | ❌ | ABC with exactly one concrete implementation |
| GENERIC_VARNAME | error | ❌ | function named with AI filler (process_data, etc.) |
| TAG_COMMENT | warn | ❌ | untagged comment (opt-in strict mode) |

### Markdown

| Rule | Severity | Auto-fix | Description |
|------|----------|----------|-------------|
| HEDGE_WORD | error | ✅ | AI filler words (robust, seamless, leverage...) |
| THANKS_OPENER | error | ❌ | README opens with "Thanks for contributing" |
| OBVIOUS_HEADER | warn | ❌ | header restated in following paragraph |
| BULLET_PROSE | warn | ❌ | short bullets that read better as a sentence |
| TABLE_OVERKILL | warn | ❌ | table with 1 row or constant column |

### Commit messages

| Rule | Severity | Description |
|------|----------|-------------|
| VAGUE_COMMIT | error | subject too generic (update, fix bug, wip...) |
| AND_COMMIT | error | subject contains "and" -- one thing per commit |
| NO_CONTEXT | error | fix/feat with no description of what changed |

---

## Why not ruff / pylint / semgrep?

Those tools check syntax, style, types, and known bug patterns. They're essential. Grain doesn't replace them.

Grain catches **behavioral patterns specific to AI code generation** that traditional linters miss:

- **Silent exception swallowing** -- AI wraps everything in try/except with no re-raise. ruff has `E722` for bare except, but doesn't check whether the handler re-raises or just logs and moves on.
- **Docstring padding** -- AI restates the function name as a sentence. No existing linter flags this.
- **Hedge words** -- filler words in docs that signal AI-generated prose saying nothing.
- **Echo comments** -- comments that restate the next line of code. AI adds these reflexively.
- **Vague TODOs** -- "implement this" with no approach.

Run grain alongside ruff/pylint. They solve different problems.

---

## Quick start

```bash
pip install grain-lint   # from PyPI
pip install -e .         # from source
```

```bash
grain init               # scaffold .grain.toml with auto-detected excludes
grain check --all        # human-readable scan
grain check --all --json # machine-readable scan (pipe to agents)
grain check --all --fix  # auto-fix safe violations in place
grain worklog init       # start an agentic repair session
grain status             # show current config and enabled checks
grain install            # install git hooks
grain suppress FILE:LINE RULE  # add inline suppression
```

---

## Config

```bash
grain init   # generates .grain.toml with sensible defaults + auto-detected excludes
```

Or manually:

```toml
[grain]
fail_on   = ["OBVIOUS_COMMENT", "NAKED_EXCEPT", "HEDGE_WORD", "VAGUE_TODO", "VAGUE_COMMIT"]
warn_only = ["RESTATED_DOCSTRING", "SINGLE_IMPL_ABC", "BULLET_PROSE"]
ignore    = []
exclude   = ["tests/*", "migrations/*", "reports/*"]

# Files matching these patterns are exempt from NAKED_EXCEPT (intentional in test harnesses)
test_patterns = ["test_*.py", "*_test.py", "tests/*"]

[grain.python]
generic_varnames = ["process_data", "handle_response", "get_result", "do_thing"]

[grain.markdown]
hedge_words = ["robust", "seamless", "leverage", "cutting-edge", "powerful",
               "you might want to", "consider using", "it's worth noting", "note that"]
```

**Note:** Use `exclude` under `[grain]`, not a top-level `[ignore]` section. Grain warns on unknown top-level sections.

---

## Custom Rules

```toml
[[grain.custom_rules]]
name     = "PRINT_DEBUG"
pattern  = '^\s*print\s*\('
files    = "*.py"
message  = "print() call -- use logging instead"
severity = "error"

[[grain.custom_rules]]
name     = "FIXME_DEADLINE"
pattern  = 'FIXME(?!.*\d{4}-\d{2}-\d{2})'
files    = "*.py"
message  = "FIXME without a deadline date (YYYY-MM-DD)"
severity = "warn"
```

---

## Suppression

```python
except Exception as e:  # grain: ignore NAKED_EXCEPT
    pass  # intentional top-level catch
```

```bash
grain suppress src/main.py:42 NAKED_EXCEPT
```

---

## pre-commit

```yaml
repos:
  - repo: https://github.com/mmartoccia/grain
    rev: v0.3.0
    hooks:
      - id: grain
```

---

## Output format

**Human (default):**
```
path/to/file.py:42  [FAIL] OBVIOUS_COMMENT  "# return result" restates the following line
path/to/README.md:7  [FAIL] HEDGE_WORD  "robust" signals AI-generated prose
```

**Machine (`--json`):**
```json
[
  {"file": "path/to/file.py", "line": 42, "rule": "OBVIOUS_COMMENT",
   "severity": "error", "message": "...", "fixable": true}
]
```

Exit 0 = clean. Exit 1 = errors found.

---

## FAQ

**Does grain support auto-fix?**
Yes. `grain check --fix` handles OBVIOUS_COMMENT, VAGUE_TODO, HEDGE_WORD, and NAKED_EXCEPT (minimal safe fix: narrows bare `except` to `except Exception as e: raise`). Rules requiring judgment are reported but not touched.

**Can I use grain to drive an AI agent?**
Yes -- that's the primary agentic use case. Use `--json` to get machine-readable output and `grain worklog` to track multi-session repair progress. See the agentic workflow section above.

**What's the false positive rate?**
Depends on the rule. NAKED_EXCEPT and VAGUE_TODO are near-zero. OBVIOUS_COMMENT occasionally flags legitimate comments where overlap is coincidental. Use `# grain: ignore RULE_NAME` for those.

**Can I write custom rules without learning semgrep YAML?**
Yes. Simple regex + file glob in `.grain.toml`. See Custom Rules above.

**Python only?**
For now. The architecture supports adding language-specific check modules. PRs welcome.
