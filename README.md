# grain

Anti-slop linter for AI-assisted codebases. Detects AI-generated code and documentation patterns before they land in version control.

## What it does

AI code has tells. `grain` flags them so a human can decide whether to keep, rewrite, or suppress. It does not auto-fix -- fixing requires judgment.

## Quick start

```bash
pip install grain        # from PyPI (coming soon)
pip install -e .         # from source
```

## Usage

```bash
grain check [files...]      # check specific files
grain check --all           # check entire repo
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

[grain.python]
generic_varnames = ["process_data", "handle_response", "get_result", "do_thing"]

[grain.markdown]
hedge_words = ["robust", "seamless", "leverage", "cutting-edge", "powerful",
               "you might want to", "consider using", "it's worth noting", "note that"]
```

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
    rev: v0.1.0
    hooks:
      - id: grain
```

## Output format

```
path/to/file.py:42  [FAIL] OBVIOUS_COMMENT  "# return result" restates the following line
path/to/README.md:7  [FAIL] HEDGE_WORD  "robust" signals AI-generated prose
```

Exit 0 = clean. Exit 1 = errors found (pre-commit blocks the commit).
