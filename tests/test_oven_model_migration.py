"""Scenario tests for the oven raw-model migration (v0.2.6) and STOMP delta merge.

Ground truth (see captures/evidence-20261114-oven-model-migration/ and
session_handoff.md):

- Between 2026-10-17 and 2026-11-11 Smeg migrated ovens to the Plus-era raw
  data model: /info and STOMP pushes stopped carrying "appl", "doorState",
  "childlock", "currStepTargetTempSet", "failureCode", "failureLabel",
  "CBpartlNumber", "CBtemperaure" and now serve ~528 raw fields
  (applState1_*/applState2_* bits, int enums). Every entity went
  unavailable/unknown while the appliance itself was fine.
- The SmegConnect Plus app decodes the raw model client-side
  (OvenStatusTransformer.java, KmpOvenAttributes.java, OngoingCycleHelper.java);
  coordinator._apply_oven_status_transform reproduces the v1 status strings.
- STOMP pushes are DELTAS (2-9 fields + cloudConnected, ~every 2s for a busy
  oven) — _on_ws_message used to REPLACE the whole state dict with the delta,
  wiping all other fields until the next 60s REST poll.

Fixture values are transcribed from the captured payloads:
  OLD = pre-migration v1 status (2026-08 capture, oven-60 SOP6606WS2PNR)
  NEW = post-migration raw status (2026-11-14 capture, same oven, healthy)

Run:  python3 tests/test_oven_model_migration.py
(no pytest/HA dependency — AST extraction into a stub harness)
"""
import ast
import asyncio
import builtins
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COORDINATOR = ROOT / "custom_components" / "smegconnect" / "coordinator.py"
CONST = ROOT / "custom_components" / "smegconnect" / "const.py"

failures: list[str] = []


def check(name, actual, expected):
    if actual != expected:
        failures.append(f"{name}: expected {expected!r}, got {actual!r}")


def load_function(path, name, extra_globals):
    """Extract a real function via AST and run it in a stub harness."""
    src = path.read_text()
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name
    )
    globals_ = dict(extra_globals)
    exec(ast.get_source_segment(src, fn), globals_)
    return globals_[name]


def module_global_names(path):
    """Top-level names a module defines (imports + assignments)."""
    tree = ast.parse(path.read_text())
    names = set(dir(builtins))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def assert_names_resolve(path, function_names):
    """S10/S11 lesson: every name an extracted function references must resolve
    at module level — the stub harness otherwise masks missing imports. Function
    parameters and local assignments count as resolved bindings."""
    src = path.read_text()
    tree = ast.parse(src)
    module_names = module_global_names(path)
    for fname in function_names:
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == fname
        )
        args = fn.args
        bound = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
        refs = {
            node.id for node in ast.walk(fn)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        missing = refs - module_names - bound
        if missing:
            failures.append(f"{path.name}:{fname}: unresolved names {sorted(missing)}")


# ---------------------------------------------------------------- fixtures
# const.py values loaded for real so the tests track the source of truth.
const_src = CONST.read_text()
const_tree = ast.parse(const_src)
const_globals: dict = {"timedelta": __import__("datetime").timedelta}
for node in const_tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if isinstance(targets[0], ast.Name):
            try:
                exec(ast.get_source_segment(const_src, node), const_globals)
            except Exception as err:
                failures.append(f"const.py: could not eval {targets[0].id}: {err}")

OVEN_BIT_MAP = const_globals["OVEN_BIT_MAP"]
OVEN_INT_STRING_MAPS = const_globals["OVEN_INT_STRING_MAPS"]
BLAST_CHILLER_BIT_MAP = const_globals["BLAST_CHILLER_BIT_MAP"]
BLAST_CHILLER_ALARM_MAP = const_globals["BLAST_CHILLER_ALARM_MAP"]
FAILURE_LABEL_NONE = const_globals["FAILURE_LABEL_NONE"]
DEVICE_TYPE_OVEN = 7
DEVICE_TYPE_BLAST_CHILLER = 12

LOGGER_STUB = types.SimpleNamespace(
    debug=lambda *a, **k: None,
    info=lambda *a, **k: None,
    warning=lambda *a, **k: None,
)

# Post-migration raw model, transcribed from the healthy 2026-11-14 /info
# capture of oven-60 (c2b22f43) — entity-relevant subset.
NEW_RAW = {
    "applState1_000": 0, "applState1_001": 0, "applState1_002": 0,
    "applState1_004": 0,
    "applState2_001": 0, "applState2_007": 1, "applState2_009": 0,
    "applState2_011": 0, "applState2_013": 0,
    "currStepTargetTempSetState": 0,
    "currStepCookingPhase": 0, "currTempOven": 20,
    "remoteControl": 1, "ovenBusy": 0, "meatProbeInserted": 0,
    "tempFormat": 0, "hourFormat": 0, "weightFormat": 0,
    "alarmLast": 0, "alarmLastOccurredTime": 0,
    "CBpartNumber": "CB43903", "CBtemperature": 38,
    "cloudConnected": True,
}
# Entity-relevant values of the SAME oven pre-migration (2026-08 capture).
OLD_EXPECTED = {
    "appl": "OFF", "doorState": "CLOSE", "childlock": "OFF", "light": "OFF",
    "keepWarm": "OFF", "ecoLight": "OFF", "soundActiv": "ON", "digClock": "OFF",
    "currStepTargetTempSet": 0, "currStepCookingPhase": "standby",
    "tempFormat": "°C", "hourFormat": "24h", "weightFormat": "kg",
    "ovenBusy": "oven not busy", "failureCode": 0,
    "failureLabel": "notification.none",
}

# ---------------------------------------------------------------- extraction
oven_transform = load_function(
    COORDINATOR,
    "_apply_oven_status_transform",
    {
        "OVEN_BIT_MAP": OVEN_BIT_MAP,
        "OVEN_INT_STRING_MAPS": OVEN_INT_STRING_MAPS,
        "FAILURE_LABEL_NONE": FAILURE_LABEL_NONE,
        "Any": object,
    },
)

fake_smeg_ns = types.SimpleNamespace(
    _apply_oven_status_transform=oven_transform,
    _apply_blast_chiller_bit_map=load_function(
        COORDINATOR,
        "_apply_blast_chiller_bit_map",
        {
            "BLAST_CHILLER_BIT_MAP": BLAST_CHILLER_BIT_MAP,
            "BLAST_CHILLER_ALARM_MAP": BLAST_CHILLER_ALARM_MAP,
        },
    ),
)
dispatch = load_function(
    COORDINATOR,
    "_transform_state",
    {
        "SmegCoordinator": fake_smeg_ns,
        "DEVICE_TYPE_BLAST_CHILLER": DEVICE_TYPE_BLAST_CHILLER,
        "DEVICE_TYPE_OVEN": DEVICE_TYPE_OVEN,
        "Any": object,
    },
)

on_ws_message = load_function(
    COORDINATOR,
    "_on_ws_message",
    {"_LOGGER": LOGGER_STUB, "monotonic": time.monotonic, "Any": object},
)


class StubCoordinator:
    """Minimal self for the extracted _on_ws_message."""

    def __init__(self, data):
        self.data = data
        self._stopped = False
        self._push_generation = {}
        self._stomp_failures = 3
        self._last_ws_message = None
        self.last_update_success = False
        self.listeners_called = 0
        self.freshness_calls = []

    _transform_state = staticmethod(dispatch)

    def _update_cavity_temp_freshness(self, code, state):
        self.freshness_calls.append(state)

    def async_update_listeners(self):
        self.listeners_called += 1


def push(stub, payload):
    """Await the extracted async _on_ws_message."""
    asyncio.run(on_ws_message(stub, payload))


# ------------------------------------------------- static name resolution
assert_names_resolve(
    COORDINATOR,
    [
        "_transform_state",
        "_apply_oven_status_transform",
        "_apply_blast_chiller_bit_map",
        "_on_ws_message",
    ],
)

# ------------------------------------------------- S1: full parity, healthy oven
# Transforming the captured raw model must reproduce every entity-relevant
# value the v1 model served for the same (healthy, idle) oven.
out = oven_transform(dict(NEW_RAW))
for field, expected in OLD_EXPECTED.items():
    check(f"S1 old-parity {field}", out.get(field), expected)
# Raw fields survive alongside the aliases (delta merging relies on them).
check("S1 raw bits kept", out["applState1_000"], 0)
check("S1 cloudConnected kept", out["cloudConnected"], True)
# ecoLogic: no bit mapping exists anywhere in the Plus app — must stay absent
# (Unknown) rather than be invented.
check("S1 ecoLogic not invented", "ecoLogic" in out, False)

# ------------------------------------------------- S2: bit polarity (1 = active)
bit_states = {
    "applState1_000": "appl", "applState1_001": "light",
    "applState2_001": "childlock", "applState2_007": "soundActiv",
    "applState2_009": "keepWarm", "applState2_011": "ecoLight",
    "applState2_013": "digClock",
}
for raw, alias in bit_states.items():
    on = oven_transform({raw: 1})
    off = oven_transform({raw: 0})
    check(f"S2 {alias} bit=1", on.get(alias), "ON")
    check(f"S2 {alias} bit=0", off.get(alias), "OFF")
door = oven_transform({"applState1_002": 1})
check("S2 doorState bit=1", door.get("doorState"), "OPEN")
check("S2 doorState bit=0", oven_transform({"applState1_002": 0}).get("doorState"), "CLOSE")

# ------------------------------------------------- S3: cooking phase ints
# 0=standby (live-verified), 1=Scheduled→"waiting delay", 6=Completed→"end of
# cooking" (OngoingCycleHelper.java), 2-5/7-10/14-17=Ongoing→"cooking".
for raw, expected in [
    (0, "standby"), (1, "waiting delay"), (2, "cooking"), (6, "end of cooking"),
    (9, "cooking"), (17, "cooking"),
]:
    check(f"S3 phase {raw}", oven_transform({"currStepCookingPhase": raw}).get("currStepCookingPhase"), expected)
# Unmapped int passes through untouched (no invented semantics)…
check("S3 phase unknown passthrough", oven_transform({"currStepCookingPhase": 11}).get("currStepCookingPhase"), 11)
# …and a pre-migration string payload is never touched.
check("S3 phase string kept", oven_transform({"currStepCookingPhase": "cooking"}).get("currStepCookingPhase"), "cooking")

# ------------------------------------------------- S4: format enums
check("S4 tempFormat 1", oven_transform({"tempFormat": 1}).get("tempFormat"), "°F")
check("S4 hourFormat 1", oven_transform({"hourFormat": 1}).get("hourFormat"), "12h")
check("S4 weightFormat 1", oven_transform({"weightFormat": 1}).get("weightFormat"), "oz")
check("S4 unknown int passthrough", oven_transform({"tempFormat": 7}).get("tempFormat"), 7)
check("S4 string passthrough", oven_transform({"tempFormat": "°C"}).get("tempFormat"), "°C")

# ------------------------------------------------- S5: target temperature alias
check("S5 target temp", oven_transform({"currStepTargetTempSetState": 180}).get("currStepTargetTempSet"), 180)
check("S5 target temp zero", oven_transform({"currStepTargetTempSetState": 0}).get("currStepTargetTempSet"), 0)
# v1 field name still wins when the raw alias is absent (revert safety).
check("S5 v1 field untouched", oven_transform({"currStepTargetTempSet": 190}).get("currStepTargetTempSet"), 190)

# ------------------------------------------------- S6: error-field synthesis
healthy = oven_transform({"alarmLast": 0})
check("S6 healthy failureCode", healthy.get("failureCode"), 0)
check("S6 healthy failureLabel", healthy.get("failureLabel"), FAILURE_LABEL_NONE)
# alarmLast != 0: semantics unverified — fields must stay absent so entities
# show Unknown instead of a false "None"/off on a problem sensor.
alarmed = oven_transform({"alarmLast": 5})
check("S6 alarmed failureCode absent", "failureCode" in alarmed, False)
check("S6 alarmed failureLabel absent", "failureLabel" in alarmed, False)
# Pre-migration payload carries real failure fields — never overwrite.
check(
    "S6 v1 failure untouched",
    oven_transform({"failureCode": 3, "failureLabel": "Err", "alarmLast": 0}).get("failureCode"),
    3,
)
# alarmLast missing entirely → treated as healthy (field always present in both models).
check("S6 no alarmLast", oven_transform({}).get("failureCode"), 0)

# ------------------------------------------------- S7: typo-field aliases
check("S7 part number", oven_transform({"CBpartNumber": "CB43903"}).get("CBpartlNumber"), "CB43903")
check("S7 cb temperature", oven_transform({"CBtemperature": 38}).get("CBtemperaure"), 38)
# v1 payload has only the typo'd fields — untouched.
only_typo = {"CBpartlNumber": "CBOLD", "CBtemperaure": 30, "alarmLast": 0}
out_typo = oven_transform(dict(only_typo))
check("S7 v1 typo fields kept", (out_typo.get("CBpartlNumber"), out_typo.get("CBtemperaure")),
      ("CBOLD", 30))

# ------------------------------------------------- S8: idempotency (merged deltas re-run it)
once = oven_transform(dict(NEW_RAW))
check("S8 idempotent", oven_transform(dict(once)), once)

# ------------------------------------------------- S9: dispatch by device type
check("S9 oven dispatch", "appl" in dispatch(DEVICE_TYPE_OVEN, dict(NEW_RAW)), True)
chiller = dispatch(DEVICE_TYPE_BLAST_CHILLER, {"applState2_001": 1, "alarmStatus_000": 0})
check("S9 chiller dispatch", chiller.get("childlockRemCmd"), 1)
passthrough = {"someField": 1}
check("S9 unknown type untouched", dispatch(3, passthrough), passthrough)

# ------------------------------------------------- S10: STOMP delta merge
# Real-world shape: a busy oven pushes 2-9 changed fields ~every 2s; the
# pre-migration bug REPLACED state with the delta, wiping everything else.
initial_full = dict(NEW_RAW)
initial_full["currTempOven"] = 185
initial_full["currStepTargetTempSetState"] = 200
initial_full["remoteControl"] = 1
coordinator = StubCoordinator({
    "oven-60": {"deviceCode": "oven-60", "deviceTypeId": DEVICE_TYPE_OVEN,
                "state": dict(initial_full)},
})
# Delta: only light toggled + the always-present cloudConnected.
push(
    coordinator,
    {"deviceCode": "oven-60", "status": {"cloudConnected": True, "applState1_001": 1}},
)
merged = coordinator.data["oven-60"]["state"]
check("S10 delta applied (light ON)", merged.get("light"), "ON")
check("S10 prior temp retained", merged.get("currTempOven"), 185)
check("S10 prior target retained", merged.get("currStepTargetTempSetState"), 200)
check("S10 generation bumped", coordinator._push_generation["oven-60"], 1)
check("S10 stomp failures reset", coordinator._stomp_failures, 0)
check("S10 listeners notified", coordinator.listeners_called, 1)
check("S10 freshness got merged dict", coordinator.freshness_calls[-1] is merged, True)

# A second delta continues from the first merge (no lost updates).
push(
    coordinator,
    {"deviceCode": "oven-60",
     "status": {"cloudConnected": True, "applState1_001": 0, "currTempOven": 186}},
)
merged2 = coordinator.data["oven-60"]["state"]
check("S10b second delta light OFF", merged2.get("light"), "OFF")
check("S10b temp updated", merged2.get("currTempOven"), 186)
check("S10b generation bumped again", coordinator._push_generation["oven-60"], 2)

# Freshness must receive the TRANSFORMED (string-phase) dict — the standby
# detection in _update_cavity_temp_freshness compares against "standby".
check(
    "S10c freshness sees string phase",
    coordinator.freshness_calls[-1].get("currStepCookingPhase"),
    "standby",
)

# ------------------------------------------------- S11: push guards
coordinator2 = StubCoordinator({"oven-60": {"deviceTypeId": DEVICE_TYPE_OVEN, "state": {}}})
push(coordinator2, {"deviceCode": "unknown-dev", "status": {"a": 1}})
check("S11 unknown device ignored", coordinator2.data["oven-60"].get("state"), {})
push(coordinator2, {"deviceCode": "oven-60", "status": {}})
check("S11 empty status ignored", coordinator2.data["oven-60"].get("state"), {})
coordinator2._stopped = True
push(coordinator2, {"deviceCode": "oven-60", "status": {"applState1_000": 1}})
check("S11 stopped ignored", coordinator2.data["oven-60"].get("state"), {})

# ------------------------------------------------- S12: first push with empty prior state
coordinator3 = StubCoordinator({"oven-60": {"deviceTypeId": DEVICE_TYPE_OVEN, "state": {}}})
push(coordinator3, {"deviceCode": "oven-60", "status": dict(NEW_RAW)})
state3 = coordinator3.data["oven-60"]["state"]
check("S12 boot-from-push appl", state3.get("appl"), "OFF")
check("S12 boot-from-push phase", state3.get("currStepCookingPhase"), "standby")

# ------------------------------------------------- summary
if failures:
    print(f"FAILED: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("All oven-model-migration scenarios passed.")
