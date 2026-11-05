"""Scenario tests for the Cooking Remaining Time sensor (cook_remaining).

`currSeqDuration` is a live countdown of REMAINING time, not the sequence
total: the firmware decrements it as the cook progresses. Verified against the
2026-09 Charles capture (smegconnect-commands-oven.chlz): a 60 s step reported
duration 59 -> 54 -> 33 while currSeqElapsedTime counted 0 -> 6 -> 27, i.e.
duration + elapsed == configured total at every snapshot, and the Smeg app
computes "ready at" as now + currSeqDuration (OngoingCycleHelper.java /
TimeExtKt.calculateEndTime). Subtracting elapsed therefore double-counts and
reaches 0 at the cook's halfway point.

Run:  python3 tests/test_cook_remaining.py
(no pytest/HA dependency — native_value is pulled out with ast and run in a
stub harness)
"""
import ast
import sys
import types
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "custom_components" / "smegconnect" / "sensor.py"


def load_native_value():
    src = SRC.read_text()
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "native_value"
    )
    globals_ = {
        "FAILURE_LABEL_NONE": "notification.none",
        "APPLIANCE_CATEGORY_NAMES": {},
        "Any": object,
    }
    exec(ast.get_source_segment(src, fn), globals_)
    return globals_["native_value"]


NATIVE_VALUE = load_native_value()


def value_for(state, key="cook_remaining", state_field="currSeqDuration"):
    """Invoke the extracted native_value against a state dict."""
    self = types.SimpleNamespace(
        _state=state,
        entity_description=types.SimpleNamespace(
            key=key, state_field=state_field, value_fn=None,
        ),
    )
    return NATIVE_VALUE(self)


def main():
    scenarios = [
        # (label, state, expected)
        ("S1 standby — duration 0 reports unknown",
         {"currSeqDuration": 0, "currSeqElapsedTime": 0}, None),
        ("S2 cooking start blip (phase cooking, duration still 0) — unknown",
         {"currSeqDuration": 0, "currSeqElapsedTime": 0,
          "currStepCookingPhase": "cooking"}, None),
        ("S3 ~1 s into 60 s step — 59 s left",
         {"currSeqDuration": 59, "currSeqElapsedTime": 0}, 59),
        ("S4 ~6 s in — firmware countdown used as-is (old code gave 48)",
         {"currSeqDuration": 54, "currSeqElapsedTime": 6}, 54),
        ("S5 ~27 s in — old code gave 6",
         {"currSeqDuration": 33, "currSeqElapsedTime": 27}, 33),
        ("S6 halfway regression: 60-min cook, 40 min in (20 min left) — "
         "old code gave 0",
         {"currSeqDuration": 1200, "currSeqElapsedTime": 2400}, 1200),
        ("S7 missing field — unknown",
         {}, None),
        ("S8 non-numeric value — unknown",
         {"currSeqDuration": "n/a"}, None),
        ("S9 elapsed sensor untouched (counts up, raw seconds)",
         {"currSeqElapsedTime": 27}, 27),
    ]

    passed = 0
    for label, state, expected in scenarios:
        if label.startswith("S9"):
            got = value_for(state, key="cook_elapsed", state_field="currSeqElapsedTime")
        else:
            got = value_for(state)
        ok = got == expected
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + ("" if ok else f"   (got {got!r}, expected {expected!r})"))

    print(f"\n{passed}/{len(scenarios)} passed")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
