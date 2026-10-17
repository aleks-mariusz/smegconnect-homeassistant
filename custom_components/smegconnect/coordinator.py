"""DataUpdateCoordinator for Smeg — one per config entry (account).

State delivery:
  Primary:  STOMP WebSocket push (real-time, ~1-5s latency)
  Reconciliation: REST every 60s, or every 10s when WebSocket is unavailable

self.data layout:
  {
    "<deviceCode>": {
      "deviceCode": "...",
      "deviceTypeId": 7,
      "modelNumber": "...",
      "serialNumber": "...",
      "firmwareRev": "...",
      "deviceTypeName": "OVEN",
      "state": { <200+ status fields> },
      "availableCommands": [...],
    },
    ...
  }
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmegApi, SmegApiError
from .auth import SmegAuth
from .const import BLAST_CHILLER_ALARM_MAP, BLAST_CHILLER_BIT_MAP, DEVICE_TYPE_BLAST_CHILLER
from .websocket import SmegWebSocket

_LOGGER = logging.getLogger(__name__)

_POLL_INTERVAL_POLL = timedelta(seconds=10)   # when falling back to polling (STOMP down)
_POLL_INTERVAL_PUSH = timedelta(seconds=60)   # independent of incoming pushes
_PUSH_SILENCE_TIMEOUT = 180

# Seconds before the first reconnect attempt; doubles each time (30 → 60 → 120 → 240 …)
_RECONNECT_INITIAL   = 30
_RECONNECT_MAX       = 300


class SmegCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Single coordinator for one Smeg cloud account."""

    def __init__(
        self,
        hass: HomeAssistant,
        auth: SmegAuth,
        api: SmegApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="smeg",
            update_interval=_POLL_INTERVAL_POLL,
        )
        self.auth = auth
        self.api = api
        self._ws: SmegWebSocket | None = None
        self._ws_connected = False
        self._reconnect_task: asyncio.Task | None = None
        self._reconnecting = False
        self._stomp_failures = 0      # consecutive STOMP connection failures
        self._stopped = False
        self._last_ws_message: float | None = None
        self._last_rest_update: float | None = None
        self._push_generation: dict[str, int] = {}
        self.data: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Fetch device list + initial state, then try WebSocket."""
        await self._fetch_all_devices()
        await self._start_websocket()

    async def async_stop(self) -> None:
        """Called when the config entry is unloaded."""
        if self._stopped:
            return
        self._stopped = True
        self._reconnecting = True   # block new reconnects
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.async_disconnect()
        await self.async_shutdown()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator override (polling fallback)
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        if self._stopped:
            return self.data

        if (
            self._ws_connected
            and self._last_ws_message is not None
            and monotonic() - self._last_ws_message > _PUSH_SILENCE_TIMEOUT
        ):
            _LOGGER.warning("Smeg WebSocket has no device messages for %ds — reconnecting",
                            _PUSH_SILENCE_TIMEOUT)
            if self._ws:
                await self._ws.async_disconnect()
            self._record_ws_failure()

        for code in list(self.data):
            try:
                generation = self._push_generation.get(code, 0)
                info = await self.api.get_device_info(code)
                # A newer push can arrive while the HTTP request is in flight.
                if generation != self._push_generation.get(code, 0):
                    continue
                state = info.get("highLevelDeviceStatus", {}).get("status", {})
                if self.data[code].get("deviceTypeId") == DEVICE_TYPE_BLAST_CHILLER:
                    state = self._apply_blast_chiller_bit_map(state)
                self.data[code]["state"] = state
            except SmegApiError as err:
                raise UpdateFailed(f"Failed to poll {code}: {err}") from err
        self._last_rest_update = monotonic()
        return self.data

    # ------------------------------------------------------------------
    # WebSocket management
    # ------------------------------------------------------------------

    async def _start_websocket(self) -> None:
        if self._stopped:
            return
        if self._ws:
            await self._ws.async_disconnect()

        session = async_get_clientsession(self.hass)
        self._ws = SmegWebSocket(
            session,
            self.auth,
            on_disconnect=self._on_ws_disconnect,
            on_message=self._on_ws_message,
        )
        try:
            await self._ws.async_connect()
            self._ws_connected = True
            self._last_ws_message = monotonic()
            self.update_interval = _POLL_INTERVAL_PUSH
        except asyncio.CancelledError:
            await self._ws.async_disconnect()
            raise
        except Exception:
            await self._ws.async_disconnect()
            if self._stopped or self.hass.is_stopping:
                return
            _LOGGER.warning("Failed to connect WebSocket — using polling", exc_info=True)
            self._record_ws_failure()

    def _record_ws_failure(self) -> None:
        self._ws_connected = False
        self.update_interval = _POLL_INTERVAL_POLL
        self._stomp_failures += 1
        self._schedule_reconnect()

    async def _on_ws_disconnect(self, _payload: None) -> None:
        """Called by SmegWebSocket when the connection drops or gets a STOMP ERROR."""
        if self._stopped:
            return
        self._record_ws_failure()
        _LOGGER.warning(
            "Smeg WebSocket disconnected (failure %d) — REST polling and automatic retry",
            self._stomp_failures,
        )
        # Setting update_interval does NOT schedule a timer in HA. Explicitly
        # refresh so fallback starts even when the previous timer was absent.
        await self.async_request_refresh()

    async def _on_ws_message(self, payload: dict[str, Any]) -> None:
        """Called by SmegWebSocket on each inbound state push."""
        _LOGGER.debug("STOMP MESSAGE payload keys=%s", list(payload.keys()))

        device_code = payload.get("deviceCode")
        status = payload.get("status")
        if self._stopped or not device_code or not isinstance(status, dict) or not status:
            return
        if device_code not in self.data:
            _LOGGER.debug("State push for unknown device %s — ignoring", device_code)
            return

        self._stomp_failures = 0
        self._last_ws_message = monotonic()
        self._push_generation[device_code] = self._push_generation.get(device_code, 0) + 1
        if self.data[device_code].get("deviceTypeId") == DEVICE_TYPE_BLAST_CHILLER:
            status = self._apply_blast_chiller_bit_map(status)
        self.data[device_code]["state"] = status
        # async_set_updated_data resets the REST timer on every push: a chatty
        # device would starve reconciliation for another device missing pushes.
        self.last_update_success = True
        self.async_update_listeners()

    def _schedule_reconnect(self) -> None:
        if self._reconnecting or self._stopped:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.async_create_background_task(
            self._reconnect_loop(), name="smeg_ws_reconnect"
        )

    async def _reconnect_loop(self) -> None:
        self._reconnecting = True
        try:
            while not self._stopped:
                delay = min(_RECONNECT_INITIAL * 2 ** min(max(self._stomp_failures - 1, 0), 4),
                            _RECONNECT_MAX)
                _LOGGER.debug("WebSocket reconnect in %ds", delay)
                await asyncio.sleep(delay)
                try:
                    await self._start_websocket()
                    if self._ws_connected:
                        await self.async_request_refresh()
                        # Re-check: a STOMP ERROR frame can arrive during the fetch
                        # (listen task runs while we await HTTP). If it did, _ws_connected
                        # is now False — loop back and try again rather than falsely
                        # declaring success.
                        if not self._ws_connected:
                            continue
                        _LOGGER.info("Smeg WebSocket reconnected successfully")
                        return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _LOGGER.debug("Reconnect attempt failed", exc_info=True)
        except asyncio.CancelledError:
            pass
        finally:
            self._reconnecting = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_blast_chiller_bit_map(state: dict[str, Any]) -> dict[str, Any]:
        """Translate raw applState2_* bits to logical named fields for blast chillers.

        Mirrors BlastChillerStatusTransformer.java in the SmegConnect Plus APK.
        Also synthesises oven-compatible aliases (e.g. 'childlock') so the same
        binary_sensor/switch descriptors work for both device types.
        """
        for raw_field, named_field in BLAST_CHILLER_BIT_MAP.items():
            if raw_field in state:
                state[named_field] = state[raw_field]

        # Synthesise oven-compatible string aliases used by existing sensor descriptors.
        appl_on = state.get("applRemCmd")
        if appl_on is not None:
            state["appl"] = "ON" if appl_on == 1 else "OFF"

        door = state.get("doorRemCmd")
        if door is not None:
            state["doorState"] = "OPEN" if door == 1 else "CLOSE"

        child = state.get("childlockRemCmd")
        if child is not None:
            # childlockRemCmd=1 means locked. Synthesise childlock="ON" when locked,
            # consistent with the oven's direct childlock field ("ON" = lock engaged).
            state["childlock"] = "ON" if child == 1 else "OFF"

        # Synthesise alarm summary fields from individual alarmStatus_NNN bits.
        # isAlarmActive in BlastChillerStatusKt.java requires BOTH bit N and bit N+1
        # to equal 1 for the alarm to be considered active. Checking only one field
        # produced false positives because the firmware sets individual bits to 1
        # during normal operation.
        active_alarms = [
            label
            for prefix, bit, label in BLAST_CHILLER_ALARM_MAP
            if (state.get(f"{prefix}_{bit:03d}", 0) == 1
                and state.get(f"{prefix}_{bit + 1:03d}", 0) == 1)
        ]
        state["chiller_alarm_active"] = len(active_alarms) > 0
        state["chiller_alarm_description"] = (
            ", ".join(active_alarms) if active_alarms else "None"
        )

        return state

    async def _fetch_all_devices(self) -> None:
        devices_raw = await self.api.get_devices()
        for dev in devices_raw:
            code = dev["deviceCode"]
            try:
                info = await self.api.get_device_info(code)
            except SmegApiError:
                _LOGGER.warning("Could not fetch info for device %s", code)
                info = {}

            existing_state = self.data.get(code, {}).get("state", {})
            state = info.get("highLevelDeviceStatus", {}).get("status", existing_state)
            type_id = dev.get("deviceTypeId", 0)
            if type_id == DEVICE_TYPE_BLAST_CHILLER:
                state = self._apply_blast_chiller_bit_map(state)
            self.data[code] = {
                **dev,
                "state": state,
                "availableCommands": info.get("availableCommands", []),
            }
