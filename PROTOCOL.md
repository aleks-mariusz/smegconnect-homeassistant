# SmegConnect — Protocol & API Reference

> Reverse-engineered from SmegConnect 2.15 and SmegConnect Plus APKs, confirmed via live proxy captures (August 2026).

This document describes the Smeg cloud API used by this integration. It is intended for contributors adding support for new device types or debugging integration behaviour.

---

## Platform

Smeg smart appliances use **ADB Italia's ioCentro** IoT platform — not a Smeg-proprietary system. The same CB (Connectivity Board) firmware and API structure is shared with other appliance brands (Whirlpool 6th Sense Live, Fisher & Paykel, etc.).

```
HA / SmegConnect App
        │  HTTPS REST + STOMP/WebSocket
        ▼
Smeg Cloud  (smegcons.prod-platform.smegconnect.com)
        │  MQTT/TLS on port 8883
        ▼
AWS IoT Core  (smegcons.mqtt.iocentro.io)
        │  device-initiated, persistent MQTT session
        ▼
Connectivity Board (CB) inside appliance
```

The CB connects outbound to AWS IoT using its own device certificate provisioned at manufacture. HA communicates exclusively via the Smeg cloud REST + STOMP — there is no supported runtime local control API after provisioning.

---

## API Base URLs

| | URL |
|---|---|
| REST API | `https://smegcons.prod-platform.smegconnect.com` |
| WebSocket | `wss://ws.prod-platform.smegconnect.com/register/websocket` |
| Tenant ID | `smegcons` (sent as `x-tenant` header on every request) |

---

## Authentication

### Login (v1 — used by this integration)

```
POST /api/v1/auth/token
x-tenant: smegcons
Content-Type: application/json;charset=UTF-8

Body: {"username": "user@example.com", "password": "secret"}

Response 200:
{
  "accessToken": "<JWT — RS256, Cognito-signed>",
  "refreshToken": "<encrypted JWT>",
  "iotUserCode": "<UUID — permanent user identifier>"
}
```

Store `iotUserCode` permanently — it is used for STOMP topic subscription and never changes across token refreshes.

### Token Refresh

```
POST /api/v1/auth/refreshToken
x-tenant: smegcons

Body: {"refreshToken": "<refreshToken>"}
Response 200: {"accessToken": "..."}
```

Verified 2026-10-17: refresh responses omit `refreshToken`. Keep the existing
refresh token, replacing it only if a response explicitly supplies a new one.

### Required headers (all authenticated requests)

```
Authorization: Bearer <accessToken>
x-tenant: smegcons
Content-Type: application/json;charset=UTF-8
accept-hlsschema: 3.0
Cache-Control: no-cache
```

---

## Device Discovery

### List all devices

```
GET /api/v1/devices

Response:
{
  "devices": {
    "<deviceCode>": {
      "deviceCode": "<UUID>",
      "deviceTypeId": 7,
      "modelNumber": "0000491139",
      "serialNumber": "...",
      "firmwareRev": "v1.8.1-...",
      "deviceTypeName": "OVEN",
      ...
    }
  }
}
```

`deviceTypeId` values:

| typeId | Device | CBapplianceCategoryId |
|---|---|---|
| 2 | Dishwasher | 17 |
| 4 | Wine Cooler | 34 |
| 7 | Oven | 4 |
| 12 | Blast Chiller | 47 |

The v1 listing returns **all enrolled devices** regardless of which app (SmegConnect or SmegConnect Plus) was used to provision them.

### Get device state

```
GET /api/v1/devices/<deviceCode>/info

Response:
{
  "highLevelDeviceStatus": {
    "status": { <state fields — see below> }
  },
  "availableCommands": [...]
}
```

Call once at startup for initial state. During normal operation, state arrives via STOMP push — do not poll `/info` while WebSocket is connected.

---

## Sending Commands

```
POST /api/v1/devices/<deviceCode>/commands

Body:
{
  "deviceCommandCode": "<command>",
  "version": "4.0",
  "deviceCommandParameterInstances": [
    {"parameterKey": "<key>", "parameterValue": "<value>"}
  ]
}

Response: 202 Accepted
```

`version` is `"4.0"` for ovens (typeId=7) and blast chillers (typeId=12). Commands are delivered to the device via MQTT. The state change arrives in the next STOMP push (~1–5 seconds later).

---

## Command Reference

### Oven (typeId=7, DATAMODEL 2306/2818)

| Command code | Parameter key | Values | Notes |
|---|---|---|---|
| `applFeature` | `appl` | `"ON"` / `"OFF"` | Oven power on/off |
| `currStepTargetTempSetFeature` | `currStepTargetTempSet` | integer (°C) | Set temperature — does **not** turn oven on |
| `lightFeature` | `light` | `"ON"` / `"OFF"` | Cavity light |
| `keepWarmFeature` | `keepWarm` | `"ON"` / `"OFF"` | Keep-warm mode |
| `childlockFeature` | `childlock` | `"OFF"` / `"ON"` | Lock panel — **`"OFF"` engages lock** (see note) |
| `ecoLightFeature` | `ecoLight` | `"ON"` / `"OFF"` | Eco light mode |
| `ecoLogicFeature` | `ecoLogic` | `"ON"` / `"OFF"` | Eco heating mode |
| `soundActivFeature` | `soundActiv` | `"ON"` / `"OFF"` | Audible alerts |
| `digClockFeature` | `digClock` | `"ON"` / `"OFF"` | Digital clock style |
| `dispBrightnessFeature` | `dispBrightness` | integer 0–100 | Display brightness |
| `timer1Feature` / `timer2Feature` / `timer3Feature` | `timer1` / `timer2` / `timer3` | integer (seconds) | Countdown timers |
| `waterHardnessFeature` | `waterHardness` | integer 1–5 | Steam boiler limescale |
| `tempFormatFeature` | `tempFormat` | `"°C"` / `"°F"` | Temperature unit |
| `hourFormatFeature` | `hourFormat` | `"24h"` / `"12h"` | Clock format |
| `weightFormatFeature` | `weightFormat` | `"kg"` / `"oz"` | Weight unit |

> **Child lock note:** The oven firmware stores `childlock="OFF"` when the lock IS engaged and `childlock="ON"` when disengaged. Sending `childlockFeature` with `parameterValue: "OFF"` activates the panel lock. This is a firmware naming quirk — the integration handles it transparently.

### Blast Chiller (typeId=12, DATAMODEL 3332)

Blast chiller uses `RemCmd` variants and integer values instead of strings.

| Command code | Parameter key | Values | Notes |
|---|---|---|---|
| `applRemCmdFeature` | `applRemCmd` | `"1"` / `"0"` | Power on/off |
| `childlockRemCmdFeature` | `childlockRemCmd` | `"1"` / `"0"` | Child lock (1 = lock engaged) |
| `soundActivRemCmdFeature` | `soundActivRemCmd` | `"1"` / `"0"` | Sound |
| `digClockRemCmdFeature` | `digClockRemCmd` | `"1"` / `"0"` | Digital clock |
| `dispBrightnessFeature` | `dispBrightness` | integer | Display brightness |
| `stepOneTargetTempSetFeature` | `stepOneTargetTempSet` | integer (°C) | Step 1 target temperature |
| `stepTwoTargetTempSetFeature` | `stepTwoTargetTempSet` | integer (°C) | Step 2 target temperature |
| `stepThreeTargetTempSetFeature` | `stepThreeTargetTempSet` | integer (°C) | Step 3 target temperature |
| `timer1Feature` / `timer2Feature` | `timer1` / `timer2` | integer (seconds) | Countdown timers |
| `currSeqStartCmd` | *(none)* | seqId as param | Start a named chilling program |
| `currSeqStopCmd` | *(none)* | — | Stop current sequence |
| `tempFormatFeature` | `tempFormat` | `"0"` / `"1"` | 0=°C, 1=°F |
| `hourFormatFeature` | `hourFormat` | `"0"` / `"1"` | 0=24h, 1=12h |
| `weightFormatFeature` | `weightFormat` | `"0"` / `"1"` | 0=kg, 1=oz |

---

## Blast Chiller Bit Decoding

The blast chiller firmware encodes several state fields as positional bits in `applState1_*` and `applState2_*` arrays rather than as named fields. The integration decodes these using the bit map from `BlastChillerStatusTransformer.java` in the SmegConnect Plus APK (ADF 0526, confirmed August 2026).

### State bit map

| Raw field | Decoded field | Meaning |
|---|---|---|
| `applState1_000` | `applRemCmd` | 1 = on, 0 = off |
| `applState1_002` | `doorRemCmd` | 1 = door open, 0 = door closed |
| `applState2_001` | `childlockRemCmd` | 1 = locked, 0 = unlocked |
| `applState2_003` | `showroomRemCmd` | 1 = showroom mode on |
| `applState2_007` | `soundActivRemCmd` | 1 = sound on |
| `applState2_013` | `digClockRemCmd` | 1 = digital clock on |

Sources: `BlastChillerStatusTransformer.java` (the 5 named renames), `BlastChillerStatusKt.java` (direct reads of remaining bits). `applState1_002` → door state found by tracing `getDoorState()` through the status builder. All confirmed present in live v1 API responses.

The integration synthesises oven-compatible aliases from these decoded values:
- `appl` (`"ON"`/`"OFF"`) from `applRemCmd`
- `doorState` (`"OPEN"`/`"CLOSE"`) from `doorRemCmd`
- `childlock` (`"OFF"`=locked/`"ON"`=unlocked) from `childlockRemCmd` — inverted to match oven convention

**Other bits observed in live captures but not mapped:**

The live API response includes many additional `applState1_*` and `applState2_*` bits that are non-zero during chilling operation (e.g. `applState2_000`, `applState2_002`, `applState2_006`, `applState2_012`, `applState2_014`, `applState2_016`). These are declared as string constants in `KmpBlastChillerAttributes` but are **not read by any UI or domain code** in the APK — the app ignores them. They are likely internal firmware state bits (compressor running, fan state, cooling phase, etc.) with no semantic labels in the APK. Mapping them requires empirical testing: toggle appliance features and observe which bits change.

### Alarm decoding

Blast chiller alarms are encoded in `alarmStatus_NNN` and `alarmStatus2_NNN` bit fields. An alarm is active only when **two consecutive bits both equal 1** — this matches the `isAlarmActive()` logic in `BlastChillerStatusKt.java`:

```python
# alarm active when alarmStatus_N == 1 AND alarmStatus_(N+1) == 1
is_active = (state.get(f"alarmStatus_{bit:03d}") == 1 and
             state.get(f"alarmStatus_{bit+1:03d}") == 1)
```

Confirmed alarm bit positions (from APK source):

| Bit index | Alarm |
|---|---|
| 0 | Probe fault |
| 4 | Compressor fault |
| 6 | Cell resistance fault |
| 8 | Evaporator fan fault |
| 26 | Power and connectivity board fault |
| 28 | Power and meat probe board fault |
| 30 | Power and display board fault |
| alarmStatus2 bit 10 | Display and touch fault |

---

## Real-time Updates (STOMP over WebSocket)

The integration connects to a raw STOMP WebSocket at startup and subscribes to the user's state-change topic. All state changes arrive via this connection — REST polling is only used as fallback when the WebSocket is unavailable.

```
URL:      wss://ws.prod-platform.smegconnect.com/register/websocket
Protocol: Raw STOMP over WebSocket (NOT SockJS — use the /websocket suffix)
```

**STOMP CONNECT headers:**
```
Authorization: Bearer <accessToken>
x-tenant: smegcons
```

**Subscribe:**
```
SUBSCRIBE /status/change/<iotUserCode>
```

**Incoming message format:**
```json
{
  "deviceCode": "<device-uuid>",
  "status": { <same fields as /info status object> },
  "stateTimestamp": 1234567890
}
```

**Reconnection:** The integration uses exponential backoff (30s → 60s → 120s → max 5 min). After 3 consecutive failures it switches to 10-second REST polling until HA is restarted.

> **Important:** Use `wss://.../register/websocket` (raw STOMP path), not `wss://.../register/{server}/{session}/websocket` (SockJS path). Spring accepts CONNECT on the SockJS path but rejects SUBSCRIBE with an internal channel error.

---

## Key State Fields

### Fields common to all device types

| Field | Oven value | Blast chiller value |
|---|---|---|
| `cloudConnected` | JSON `true`/`false` | same |
| `remoteControl` | `"ON"` / `"OFF"` | integer `1` / `0` |
| `meatProbeInserted` | `"meat probe inserted"` / `"meat probe not inserted as expected"` | integer `1` / `0` |
| `tempFormat` | `"°C"` / `"°F"` | integer `0` / `1` |
| `hourFormat` | `"24h"` / `"12h"` | integer `0` / `1` |
| `weightFormat` | `"kg"` / `"oz"` | integer `0` / `1` |
| `dispBrightness` | integer | integer |
| `timer1`, `timer2`, `timer3` | integer (seconds) | integer (seconds) |

Blast chiller reports many boolean/enum fields as integers where the oven uses strings. Handle both in the same entity by including both string and integer forms in `on_values`.

### Oven-specific fields

| Field | Description |
|---|---|
| `appl` | `"ON"` / `"OFF"` — appliance on/off |
| `currTempOven` | Current cavity temperature (°C) |
| `currStepTargetTempSet` | Target temperature set-point |
| `currStepCookingPhase` | `"standby"` / `"preheating"` / `"cooking"` / `"cooling"` |
| `doorState` | `"OPEN"` / `"CLOSE"` |
| `light`, `keepWarm`, `ecoLight`, `ecoLogic` | `"ON"` / `"OFF"` |
| `childlock` | `"OFF"` = locked, `"ON"` = unlocked |
| `soundActiv` | `"ON"` / `"OFF"` |
| `failureCode` | Integer — 0 = no fault |
| `failureLabel` | String — `"notification.none"` = no fault |

### Blast chiller–specific fields

| Field | Description |
|---|---|
| `currTempCavity` | Current cavity temperature (°C) |
| `stepOneTargetTempSet` / `stepTwoTargetTempSet` / `stepThreeTargetTempSet` | Chilling step targets |
| `applRemCmd` | 1 = on, 0 = off (from applState1_000) |
| `childlockRemCmd` | 1 = locked, 0 = unlocked (from applState2_001) |
| `soundActivRemCmd` | 1 = on, 0 = off (from applState2_007) |
| `alarmStatus_000`–`alarmStatus_031` | Individual alarm bits |
| `alarmStatus2_000`–`alarmStatus2_031` | Secondary alarm bits |

---

## Implementation Notes

**`version` field in commands:** Always `"4.0"` for ovens and blast chillers. (Dishwashers and wine coolers use `"3.0"` per APK analysis — unconfirmed from live capture.)

**`cloudConnected` capitalisation:** Returns actual Python-style `True`/`False` as a string (capital T/F), not JSON `true`/`false`. `str(True)` = `"True"`.

**Command response is async:** Commands return `202 Accepted` immediately. The appliance state change arrives via STOMP ~1–5 seconds later. Implement optimistic state in the UI but clear it when real state arrives.

**`availableCommands` list:** The `/info` response includes a list of command codes supported by the device. Use this to detect what a specific model variant supports (e.g. steam commands on steam-capable models, probe commands when probe hardware is present).

**Error catalog:** Human-readable error strings are available from the Smeg S3 config CDN at:
`smeg-connect-config-app-prod.s3.eu-central-1.amazonaws.com/smegcons/labels/flatFromService/en.json`
Keys follow the pattern `AlarmNotificationOvenErr1` … `AlarmNotificationOvenErrF` for ovens and `AlarmNotificationBlastChillerErr1` … for blast chillers.

**Firmware version encoding:** Oven firmware fields are 24-bit little-endian integers (`dispBoardFwRel=2564` → `4.10.0`). Blast chiller fields are 4-character base64 strings encoding 3 bytes (`ATEA` → `[1, 49, 0]` → `1.49.0`). The `decode_fw_version()` function in `const.py` handles both.

**Provisioning:** The CB exposes a local HTTPS provisioning API (port 13335) only while in pairing mode. This API is shut down once the device connects to the Smeg cloud — there is no persistent local control interface after provisioning.
