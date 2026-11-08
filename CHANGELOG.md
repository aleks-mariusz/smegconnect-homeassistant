# Changelog

## 0.2.5b2 — 2026-11-08 (beta)

Supersedes 0.2.5b1 (same changes plus the items below; supersedes-tag created
only as a beta iteration, production 0.2.5 will consolidate).

### New

- The **Panel Clock** diagnostic sensor gains a `clock_source` attribute
  (e.g. `mains frequency`, `RTC`). This is the decisive diagnostic for oven
  clock sync: panels running from the internal RTC revert *any* remote clock
  set within moments — including sets made by the official app — while
  panels set to *mains frequency* on the appliance display adopt and keep
  them. Read-only; the source is a panel-side setting the ovens' command
  catalog does not expose remotely.

### Documented

- README: oven clock-source requirement for `sync_clock`, and the RTC
  re-assert behaviour under Limitations & Known Issues.

## 0.2.5b1 — 2026-11-08 (beta)

### New

- New diagnostic **Panel Clock** sensor for every oven and the blast chiller.
  It reports the appliance front panel's own time-of-day, so clock drift
  (e.g. the +1 h left behind by a DST change) and the outcome of a clock sync
  are visible in Home Assistant without walking to the appliance.

### Fixes

- **Clock sync now actually works on ovens.** The cloud accepts a clock
  command with HTTP 202 regardless, but oven firmware silently drops a
  `manualClock` value sent as a JSON string (it echoes the value into the
  device state without applying it — the panel keeps its old clock). Charles
  captures of the SmegConnect Plus app show the app sends the value typed per
  data model: a JSON **integer** to ovens, a JSON string to the blast
  chiller. The integration now matches the app exactly, sends raw
  seconds-since-local-midnight (no minute rounding), and needs no preamble
  commands.
- **`sync_clock` no longer reports success it cannot verify.** It skips
  appliances whose remote control is off (previously a silent 202 no-op),
  then confirms adoption with two spaced state reads — past the brief state
  echo and past MQTT command latency — and logs a warning telling you to set
  the clock on the appliance display if the panel did not adopt the new time.

## 0.2.4 — 2026-11-07

### Fixes

- Fix a `NameError` crash in the cavity-temperature tracker introduced in
  0.2.3: the `CAVITY_TEMP_MAX_PLAUSIBLE_STANDBY` constant was used but never
  imported. The crash fired whenever an oven in standby had no freshness
  tracker yet (typically right after a restart) and dropped both push and
  REST updates for the appliance — seen as repeated "Smeg WebSocket listener
  failed" warnings with frozen sensors. Adds static name-resolution tests
  that verify every name the tracker references is defined at module level
  and every `.const` import exists (the scenario harness stubs globals and
  could not catch this class of bug).

## 0.2.3 — 2026-11-05

### Corrected sensors

- Fix **Cooking Remaining Time** showing wrong (near-zero) values during a
  cook. `currSeqDuration` is a live countdown of the remaining time, not the
  sequence total — the firmware decrements it as the cook progresses
  (`duration + elapsed` stays equal to the configured step duration, and the
  Smeg app computes "ready at" as now + `currSeqDuration`). The sensor now
  reports the countdown as-is instead of subtracting elapsed time a second
  time, which reached 0 at the cook's halfway point. Outside an active cook
  the sensor reports `unknown` instead of 0 s.
- Suppress the oven's **frozen cavity temperature** in standby (firmware
  defect: the connectivity board stops refreshing `currTempOven` after a
  program ends). The reading is trusted while a program runs and for a
  90-minute cool-down window after it ends, then reported as `unknown` with
  the last trusted value in the `last_accurate_value` attribute. Trust
  resumes when a new program starts, the value changes, or the connectivity
  board reboots. The oven climate entity's current temperature applies the
  same suppression.

## 0.2.2 — 2026-10-17

### Reliable state updates

- Fix REST fallback never starting after a WebSocket disconnect, leaving sensor
  readings frozen indefinitely.
- Reconcile cloud state independently every 60 seconds, or every 10 seconds while
  disconnected. Frequent pushes from one appliance cannot block another's updates.
- Retry WebSocket connections automatically with exponential backoff capped at
  five minutes, including failures during startup. Remove the permanent
  three-failure cutoff.
- Detect silent WebSocket connections and reconnect after three minutes without
  valid device messages, checked during periodic reconciliation.
- Preserve a newer push received while a REST request is in flight.
- Clean up connection tasks and sockets, bound HTTP request timeouts, and make
  listener errors visible.

### Authentication and diagnostics

- Fix token renewal when Smeg returns only an access token. Retain the existing
  refresh token unless the server rotates it, and persist both tokens together.
- Add credential-free integration diagnostics for connection state, retries,
  push/REST update ages and polling interval.

### Promoted from earlier beta releases

- Route blast chiller commands through the v2 API.
- Add the `smegconnect.sync_clock` service and validation logging.
- Cancel reconnect tasks during Home Assistant shutdown.

### Verification and updating

15 regression tests passed against Home Assistant 2026.10.1, including its real
coordinator scheduling. Live verification confirmed push updates, independent
REST refreshes and two successive token renewals.

Update SmegConnect in HACS and restart Home Assistant to load the Python changes.

Known appliance behavior: some ovens publish an unchanged cavity temperature
while in standby. This release fixes integration transport freezes; it cannot
refresh a measurement that the appliance itself has stopped updating.
