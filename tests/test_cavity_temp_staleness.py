"""Scenario tests for the cavity-temperature staleness tracker.

The oven CB stops refreshing currTempOven at the standby transition (firmware
defect; see cavity-temp-freeze-analysis.md). The tracker in coordinator.py
annotates the state dict so sensor/climate entities can suppress the fossil.
These tests extract the real function from the source and exercise it against
every scenario observed in the Oct 2026 investigation.

Run:  python3 tests/test_cavity_temp_staleness.py
(no pytest/HA dependency — the function is pulled out with ast and run in a
stub harness)
"""
import ast
import builtins
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "custom_components" / "smegconnect" / "coordinator.py"

NOW = [datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)]


def load_function():
    src = SRC.read_text()
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_update_cavity_temp_freshness"
    )
    globals_ = {
        "dt_util": types.SimpleNamespace(utcnow=lambda: NOW[0]),
        "_LOGGER": types.SimpleNamespace(debug=lambda *a, **k: None),
        "CAVITY_TEMP_STALE_GRACE": timedelta(minutes=90),
        "CAVITY_TEMP_MAX_PLAUSIBLE_STANDBY": 45.0,
        "DEVICE_TYPE_OVEN": 7,
    }
    exec(ast.get_source_segment(src, fn), globals_)
    return globals_["_update_cavity_temp_freshness"]


def fresh_coord():
    c = types.SimpleNamespace()
    c.data = {"oven1": {"deviceTypeId": 7, "state": {}}}
    c._prev_cb_uptime = {}
    return c


def mkstep(update, c):
    def step(updates, advance_min=0):
        NOW[0] += timedelta(minutes=advance_min)
        state = {"currTempOven": 22, "currStepCookingPhase": "standby", "CBupTime": 100000}
        state.update(updates)
        update(c, "oven1", state)
        c.data["oven1"]["state"] = state
        tracker = c.data["oven1"].get("cavityTempTracker") or {}
        return {"stale": state.get("cavityTempStale"), "tracker": tracker}
    return step


def main() -> int:
    update = load_function()
    results = []

    # --- Basic trust model -------------------------------------------------
    c = fresh_coord(); step = mkstep(update, c)
    r = step({"currTempOven": 180, "currStepCookingPhase": "cooking"})
    results.append(("S1 cooking -> trusted", r["stale"] is False))
    r = step({"currTempOven": 201, "currStepCookingPhase": "standby"})
    results.append(("S2 program end -> transition observed, grace", r["stale"] is False and r["tracker"].get("observed_transition") is True))
    r = step({"currTempOven": 201}, advance_min=30)
    results.append(("S2b +30min still grace", r["stale"] is False))
    r = step({"currTempOven": 201}, advance_min=61)
    results.append(("S2c +91min -> stale", r["stale"] is True))
    r = step({"currTempOven": 23}, advance_min=10)
    results.append(("S3 value changed while stale -> revived", r["stale"] is False and r["tracker"] == {}))

    # --- CB reboot revival (observed 2026-10-07 12:37) ---------------------
    step({"currTempOven": 150, "currStepCookingPhase": "cooking"}, advance_min=1)
    step({"currTempOven": 150, "currStepCookingPhase": "standby"}, advance_min=0)
    step({"currTempOven": 150}, advance_min=120)
    r = step({"currTempOven": 150, "CBupTime": 5000}, advance_min=1)
    results.append(("S4 CB reboot -> revived", r["stale"] is False and r["tracker"] == {}))

    # --- HA restart mid-freeze (observed 2026-10-01 / 2026-10-07) ----------
    c2 = fresh_coord()
    NOW[0] = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    state = {"currTempOven": 114, "currStepCookingPhase": "standby", "CBupTime": 100000}
    update(c2, "oven1", state)
    results.append(("S5 restart+elevated fossil -> stale immediately", state.get("cavityTempStale") is True))

    c3 = fresh_coord()
    state = {"currTempOven": 22, "currStepCookingPhase": "standby", "CBupTime": 100000}
    update(c3, "oven1", state)
    results.append(("S5b restart+ambient -> trusted", state.get("cavityTempStale") is False))

    # --- Tracker lost across device-dict rebuild (fetch_all_devices) -------
    c4 = fresh_coord(); step = mkstep(update, c4)
    step({"currTempOven": 180, "currStepCookingPhase": "cooking"}, advance_min=1)
    c4.data["oven1"].pop("cavityTempTracker", None)
    r = step({"currTempOven": 180, "currStepCookingPhase": "standby"}, advance_min=0)
    results.append(("S6 tracker lost, transition re-observed -> grace", r["stale"] is False and r["tracker"].get("observed_transition") is True))

    # --- Blast chillers are not ovens --------------------------------------
    c5 = fresh_coord()
    c5.data["chill"] = {"deviceTypeId": 12, "state": {}}
    state = {"currTempOven": 999, "currStepCookingPhase": "standby", "CBupTime": 1}
    update(c5, "chill", state)
    results.append(("S7 chiller untouched", "cavityTempStale" not in state))

    # --- Full overnight replay (real Oct 5-6 chronology) --------------------
    c6 = fresh_coord(); step = mkstep(update, c6)
    step({"currTempOven": 235, "currStepCookingPhase": "cooking"}, advance_min=1)
    r = step({"currTempOven": 201, "currStepCookingPhase": "standby"}, advance_min=70)
    results.append(("S8 transition -> grace", r["stale"] is False))
    r = step({"currTempOven": 201}, advance_min=89)
    results.append(("S8a +89min still grace", r["stale"] is False))
    r = step({"currTempOven": 201}, advance_min=2)
    results.append(("S8b +91min -> stale", r["stale"] is True))
    r = step({"currTempOven": 201}, advance_min=600)
    results.append(("S8c 10h later still stale", r["stale"] is True))
    r = step({"currTempOven": 26, "currStepCookingPhase": "cooking"}, advance_min=1)
    results.append(("S8d next program -> trusted again", r["stale"] is False))

    # --- Missing reading must not crash or leave a stale flag ---------------
    c7 = fresh_coord()
    state = {"currStepCookingPhase": "standby", "CBupTime": 1}
    update(c7, "oven1", state)
    results.append(("S9 missing temp -> no crash, no stale flag", "cavityTempStale" not in state))

    # --- Static check: every name the tracker references must resolve -------
    # The stub harness above masks module-level name resolution — v0.2.3
    # shipped a NameError because CAVITY_TEMP_MAX_PLAUSIBLE_STANDBY was used
    # but never imported. Verify the function only references names that are
    # defined at coordinator module level, and that .const imports exist.
    src = SRC.read_text()
    tree = ast.parse(src)
    module_names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            module_names.update(t.id for t in targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)

    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_update_cavity_temp_freshness")
    local_names = {a.arg for a in ast.walk(fn) if isinstance(a, ast.arg)}
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            local_names.add(node.id)
    referenced = {n.id for n in ast.walk(fn)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    unresolved = referenced - local_names - module_names - set(dir(builtins))
    results.append(("S10 tracker references resolve at module level", not unresolved))
    if unresolved:
        print(f"        unresolved names: {sorted(unresolved)}")

    const_tree = ast.parse((SRC.parent / "const.py").read_text())
    const_names = set()
    for node in const_tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            const_names.update(t.id for t in targets if isinstance(t, ast.Name))
    missing = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "const":
            missing.update(a.name for a in node.names if a.name not in const_names)
    results.append(("S11 .const imports all defined in const.py", not missing))
    if missing:
        print(f"        missing from const.py: {sorted(missing)}")

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
