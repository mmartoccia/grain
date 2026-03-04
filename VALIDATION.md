# grain -- First Real-World Validation

**Target:** `~/clawd/memory/projects/personal/ventures/openclaw-wearable-sdk/`  
**Date:** 2026-03-04  
**Files checked:** 72 (.py and .md, excluding .venv, .git, __pycache__)  
**Command:** `grain check --all` from repo root  

## Summary

| Severity | Count |
|----------|-------|
| FAIL (errors) | 170 |
| WARN (warnings) | 14 |
| **Total violations** | **184** |

## Violations by Rule

| Rule | Count | Type |
|------|-------|------|
| NAKED_EXCEPT | 156 | error |
| OBVIOUS_COMMENT | 9 | error |
| VAGUE_TODO | 1 | error |
| OBVIOUS_HEADER | 2 | warn |
| BULLET_PROSE | 1 | warn |
| RESTATED_DOCSTRING | 9 | warn |
| **Total** | **178** | |

## Signal Analysis

### NAKED_EXCEPT (156 errors) -- Dominant pattern

The SDK is saturated with broad `except Exception` clauses that swallow errors silently. This is the #1 AI-generated code tell in hardware abstraction layers -- the model writes defensive wrappers around every BLE/USB/hardware call without distinguishing recoverable from fatal errors.

**Hotspots:**
- `openclaw_embodiment/hal/reachy2_reference.py` -- 40+ instances
- `openclaw_embodiment/hal/even_g2_reference.py` -- 24 instances  
- `openclaw_embodiment/discovery/discovery_loop.py` -- 18 instances
- `openclaw_embodiment/hal/pi3_reference.py` -- 10 instances

**Verdict:** Real signal. Hardware-level code needs selective exception handling -- each `except Exception` here likely hides a class of hardware failure that should surface differently.

### OBVIOUS_COMMENT (9 errors) -- Clear AI tell

Comments that directly restate the following line:
```
context_builder.py:82   "Calculate awareness level" → calc_awareness_level()
context_builder.py:87   "Generate deterministic summary" → generate_summary()
discovery_loop.py:361   "Push report immediately on anomaly" → push_report_on_anomaly()
audio_trigger.py:48     "Sample rate" → SAMPLE_RATE = 16000
```

**Verdict:** Real signal. These are exactly the kinds of comments AI adds to "explain" self-documenting code. All safe to delete.

### RESTATED_DOCSTRING (9 warnings) -- Mostly signal

```
hal/base.py:113   read_sample() → "Read sample"
hal/base.py:117   set_sample_rate() → "Set sample rate"
hal/base.py:133   capture_frame() → "Capture frame"
hal/base.py:157   start_recording() → "Start recording"
hal/base.py:161   stop_recording() → "Stop recording"
```

**Verdict:** Real signal in `hal/base.py`. These are abstract base class stubs where the docstring adds zero value. The test class flags (`TestAwarenessLevelCalculation`, `TestConflictDetection`) are borderline -- test class names are usually descriptive enough that the docstring restating them is fine. Could be suppressed or moved to `warn_only`.

### VAGUE_TODO (1 error)

```
hal/distiller_reference.py:380   "Calibrate on actual Distiller footage"
```

**Verdict:** Borderline. "Calibrate on actual Distiller footage" is more specific than generic filler but lacks an approach or reason. The TODO could be improved: "Calibrate face-detection threshold on actual Distiller footage (currently mocked at 0.6)".

### OBVIOUS_HEADER (2 warnings)

```
README.md:215  "Contributing" → content restates it
README.md:225  "License" → content restates it
```

**Verdict:** Real signal. "## Contributing" followed by "See CONTRIBUTING.md" is pure boilerplate.

### BULLET_PROSE (1 warning)

```
examples/hero_demo/README.md:17  short bullet list
```

**Verdict:** Real signal.

## False Positive Analysis

A small number of OBVIOUS_COMMENT hits are borderline:

```
reachy2_reference.py:489  "reachy2-sdk: reachy.audio.get_doa() -> float (azimuth)"
reachy2_reference.py:721  "reachy2-sdk: reachy.head.set_expression(expression_name)"
```

These are SDK API reference comments preceding the actual call -- they add the external API signature as context. They fire because the comment tokens overlap with the code tokens. These are legitimate documentation comments that should be suppressed with `# grain: ignore OBVIOUS_COMMENT`.

**Estimated false positive rate:** ~2/184 = ~1%. Acceptable for a pre-commit gate.

## Conclusion

`grain` ran cleanly on 72 files in ~3 seconds (after fixing a markdown parser infinite loop for lines containing `|` that don't start with `|`).

The signal quality is high:
- NAKED_EXCEPT dominates (84% of errors) -- this is the single most expensive AI-generated pattern in hardware code; each one is a silent failure mode
- OBVIOUS_COMMENT fired on real restatement comments (not noise)
- RESTATED_DOCSTRING caught genuine stub docstrings in the HAL base
- No major false positive clusters

**Recommended `.grain.toml` for this repo:**

```toml
[grain]
fail_on = ["NAKED_EXCEPT", "OBVIOUS_COMMENT", "VAGUE_TODO", "VAGUE_COMMIT"]
warn_only = ["RESTATED_DOCSTRING", "SINGLE_IMPL_ABC", "BULLET_PROSE", "OBVIOUS_HEADER"]
ignore = []
```

The NAKED_EXCEPT wall (156 violations) would block any commit until addressed -- which is the correct behavior. Hardware abstraction layers should handle errors explicitly.
