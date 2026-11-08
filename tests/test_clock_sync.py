"""Scenario tests for the clock-sync service and Panel Clock sensor.

Ground truth from Charles captures of the SmegConnect Plus app setting clocks
successfully (see session_handoff.md):

- 2026-08-20 capture, blast chiller: POST /api/v2/devices/{code}/commands,
  manualClockFeature, parameterValue as JSON STRING ("70204").
- 2026-11-08 capture, both ovens: POST /api/v1/devices/{code}/commands,
  manualClockFeature, parameterValue as JSON INTEGER (60475), sent bare as the
  first command of the session (no timezone/source/appl preamble).
- A JSON-string value to an oven is echoed into its state but silently dropped
  by the panel firmware — the root cause of the clock-sync defect.
- The cloud 202s regardless; the app's own /info read 3 s after a set still
  showed the old clock, so adoption verdicts need spaced reads.
- /info returns the panel's live ticking clock (seconds precision).

These tests extract the real helpers from services.py / sensor.py and exercise
every observed scenario. Run:  python3 tests/test_clock_sync.py
(no pytest/HA dependency — AST extraction into a stub harness)
"""
import ast
import builtins
import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ROOT / "custom_components" / "smegconnect" / "services.py"
SENSOR = ROOT / "custom_components" / "smegconnect" / "sensor.py"
CONST = ROOT / "custom_components" / "smegconnect" / "const.py"
API = ROOT / "custom_components" / "smegconnect" / "api.py"

MIDNIGHT = datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc)

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


DT_UTIL = types.SimpleNamespace(
    now=lambda: datetime(2026, 11, 8, 16, 34, 15, tzinfo=timezone.utc),
    start_of_local_day=lambda: MIDNIGHT,
)

services_globals = {
    "dt_util": DT_UTIL,
    "_LOGGER": types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    ),
    "asyncio": asyncio,
    "DEVICE_TYPE_BLAST_CHILLER": 3332,
    "DEVICE_TYPE_OVEN": 2,
}
sensor_globals = {"dt_util": DT_UTIL, "timedelta": timedelta}

# ---------------------------------------------------------------- scenarios
rc_on = load_function(SERVICES, "_remote_control_on", services_globals)
check("rc oven ON", rc_on({"remoteControl": "ON"}), True)
check("rc oven OFF", rc_on({"remoteControl": "OFF"}), False)
check("rc oven lowercase", rc_on({"remoteControl": "on"}), True)
check("rc chiller 1", rc_on({"remoteControl": 1}), True)
check("rc chiller 0", rc_on({"remoteControl": 0}), False)
check("rc string 1", rc_on({"remoteControl": "1"}), True)
check("rc bool true", rc_on({"remoteControl": True}), True)
check("rc bool false", rc_on({"remoteControl": False}), False)
check("rc missing fail-open", rc_on({}), True)
check("rc None fail-open", rc_on({"remoteControl": None}), True)

seconds_of_day = load_function(SERVICES, "_seconds_of_day", services_globals)
check(
    "seconds raw (app sent 60475 = 16:47:55)",
    seconds_of_day(datetime(2026, 11, 8, 16, 47, 55)),
    60475,
)
check("seconds midnight", seconds_of_day(datetime(2026, 11, 8, 0, 0, 0)), 0)
check("seconds 23:59:59", seconds_of_day(datetime(2026, 11, 8, 23, 59, 59)), 86399)

param_value = load_function(SERVICES, "_clock_param_value", services_globals)
check("param oven int", param_value(60475, 2), 60475)
check("param oven type", type(param_value(60475, 2)), int)
check("param chiller str", param_value(70204, 3332), "70204")
check("param chiller type", type(param_value(70204, 3332)), str)

panel_clock = load_function(SENSOR, "_panel_clock_datetime", sensor_globals)
got = panel_clock(59640)
check("panel 16:34", (got.hour, got.minute, got.second, got.tzinfo is not None), (16, 34, 0, True))
check("panel string digits", panel_clock("59640") == got, True)
mid = panel_clock(0)
check("panel midnight valid", (mid.hour, mid.minute), (0, 0))
late = panel_clock(86399)
check("panel 23:59:59", (late.hour, late.minute, late.second), (23, 59, 59))
check("panel None", panel_clock(None), None)
check("panel garbage", panel_clock("abc"), None)
check("panel out of range high", panel_clock(86400), None)
check("panel out of range low", panel_clock(-1), None)

extract = load_function(SERVICES, "_extract_manual_clock", services_globals)
check("extract nested", extract({"highLevelDeviceStatus": {"status": {"manualClock": 59640}}}), 59640)
check("extract string value", extract({"highLevelDeviceStatus": {"status": {"manualClock": "59640"}}}), "59640")
check("extract empty", extract({}), None)
check("extract no status", extract({"highLevelDeviceStatus": {}}), None)

adopted = load_function(SERVICES, "_clock_adopted", services_globals)
check("adopted exact", adopted(59640, 59640), True)
check("adopted +60 tick", adopted(59700, 59640), True)
check("adopted +90 boundary", adopted(59730, 59640), True)
check("adopted +91 rejected", adopted(59731, 59640), False)
check("adopted fossil +1h", adopted(59640 + 3600, 59640), False)
check("adopted None", adopted(None, 59640), False)
check("adopted garbage", adopted("abc", 59640), False)
check("adopted numeric string", adopted("59640", 59640), True)

# ------------------------------------------------- _verify_clock_adopted
# Stub asyncio.sleep advancing a fake clock; scripted /info responses replay
# the sequences observed in the captures: slow adoption (the app's own read
# 3 s after a set still showed the old clock) and the state echo of the
# commanded value followed by the untouched +1 h fossil.
NOW = [datetime(2026, 11, 8, 16, 34, 0, tzinfo=timezone.utc)]


def make_verify():
    async def fake_sleep(delay):
        NOW[0] += timedelta(seconds=delay)

    stub_asyncio = types.SimpleNamespace(sleep=fake_sleep)
    g = {
        "asyncio": stub_asyncio,
        "dt_util": types.SimpleNamespace(now=lambda: NOW[0]),
        "_LOGGER": services_globals["_LOGGER"],
        "_clock_adopted": adopted,
        "_extract_manual_clock": extract,
    }
    fn = load_function(SERVICES, "_verify_clock_adopted", g)

    class FakeApi:
        def __init__(self, script):
            self.script = list(script)
            self.calls = 0

        async def get_device_info(self, device_code):
            self.calls += 1
            return self.script.pop(0)

    return fn, FakeApi


def info_with(mc):
    return {"highLevelDeviceStatus": {"status": {"manualClock": mc}}}


async def run_verify_cases():
    fn, FakeApi = make_verify()
    sent = 60475  # 16:47:55, sent at NOW[0]

    # Slow adoption: read 1 (+20 s) still shows the old +1h clock (MQTT
    # latency, as in the app's own capture), read 2 (+80 s) shows adopted.
    NOW[0] = datetime(2026, 11, 8, 16, 47, 55, tzinfo=timezone.utc)
    api = FakeApi([info_with(sent + 3600 + 20), info_with(sent + 81)])
    ok = await fn(api, "dev")
    check("verify slow adoption", ok, True)

    # Echo-then-fossil: read 1 shows the echoed command value (within 90 s),
    # read 2 shows the untouched +1h clock -> must NOT report success.
    NOW[0] = datetime(2026, 11, 8, 16, 47, 55, tzinfo=timezone.utc)
    api = FakeApi([info_with(sent), info_with(sent + 3600 + 80)])
    ok = await fn(api, "dev")
    check("verify echo caught", ok, False)

    # Refusal on both reads (string-to-oven firmware drop).
    NOW[0] = datetime(2026, 11, 8, 16, 47, 55, tzinfo=timezone.utc)
    api = FakeApi([info_with(sent + 3600 + 20), info_with(sent + 3600 + 80)])
    ok = await fn(api, "dev")
    check("verify refusal", ok, False)

    # Genuine prompt adoption on both reads.
    NOW[0] = datetime(2026, 11, 8, 16, 47, 55, tzinfo=timezone.utc)
    api = FakeApi([info_with(sent + 21), info_with(sent + 81)])
    ok = await fn(api, "dev")
    check("verify prompt adoption", ok, True)

    # Missing manualClock in the response never counts as adopted.
    NOW[0] = datetime(2026, 11, 8, 16, 47, 55, tzinfo=timezone.utc)
    api = FakeApi([{}, {}])
    ok = await fn(api, "dev")
    check("verify missing field", ok, False)


asyncio.run(run_verify_cases())

# ---------------------------------------------------------------- static S-checks
services_src = SERVICES.read_text()
sensor_src = SENSOR.read_text()
const_src = CONST.read_text()
api_src = API.read_text()

# App-exact clock recipe: bare manualClockFeature with per-model typed value.
if "_clock_param_value(clock_seconds, device_type_id)" not in services_src:
    failures.append("services.py: clock send must type the value per device model")
if "CMD_LOCAL_TIMEZONE" in services_src or "CMD_LOCAL_TIMEZONE" in const_src:
    failures.append("localTimezone preamble must stay removed (app sends the clock bare)")
if "endpoint_version: str | None" in api_src or "endpoint_version=" in services_src:
    failures.append("endpoint_version override must stay removed (default split is app-exact)")
if '"parameterValue": str(clock_seconds)' in services_src:
    failures.append("services.py: clock value must not be unconditionally stringified")
if "/command\"" in api_src or "/command?" in api_src:
    failures.append("api.py: command path must stay plural /commands")
if "/api/{endpoint_version}/devices/{device_code}/commands" not in api_src:
    failures.append("api.py: plural /commands path with per-type version missing")
if "_remote_control_on(state)" not in services_src:
    failures.append("services.py: remote-control gate must be applied before sending")
if 'key="panel_clock"' not in sensor_src:
    failures.append("sensor.py: panel_clock description missing")
if "SensorDeviceClass.TIMESTAMP" not in sensor_src.split("panel_clock")[1][:400]:
    failures.append("sensor.py: panel_clock must be a TIMESTAMP device class")
if "EntityCategory.DIAGNOSTIC" not in sensor_src.split("panel_clock")[1][:400]:
    failures.append("sensor.py: panel_clock must be diagnostic category")

assert_names_resolve(SERVICES, [
    "_remote_control_on", "_seconds_of_day", "_clock_param_value",
    "_extract_manual_clock", "_clock_adopted", "_verify_clock_adopted",
])
assert_names_resolve(SENSOR, ["_panel_clock_datetime"])

# ---------------------------------------------------------------- report
if failures:
    print(f"FAIL ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("All clock-sync scenarios passed:")
print("  remote-control gate: 10 checks")
print("  raw seconds-of-day: 3 (app-exact, e.g. 60475)")
print("  per-model value typing: 4 (oven int / chiller str)")
print("  panel clock datetime: 9")
print("  manualClock extraction: 4 | adoption tolerance: 8")
print("  two-read verification: 5 scenarios (slow adoption, echo caught,")
print("    refusal, prompt adoption, missing)")
print("  static checks: typed value, bare clock, no tz preamble, plural")
print("    /commands path, rc gate, sensor class/category")
print("  module-level name resolution: services.py + sensor.py")
