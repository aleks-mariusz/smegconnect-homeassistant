# Changelog

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
