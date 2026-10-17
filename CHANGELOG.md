# Changelog

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
