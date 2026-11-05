"""Climate entity for Smeg ovens.

Maps to HVAC modes:
  HVACMode.HEAT  ← appl == "ON"
  HVACMode.OFF   ← appl == "OFF"

HVAC action (sub-state):
  HEATING  ← preheating or cooking
  IDLE     ← standby (oven on but not running a cycle)
  COOLING  ← cooling down after cycle
  OFF      ← oven is off

Power command confirmed from live device query capture and APK bundle:
  applFeature  parameterKey: "appl"  values: "ON" / "OFF"
  (Sys_OpSetPowerOnFeature is NOT in the oven's availableCommands list)

Temperature command (decoupled from power):
  currStepTargetTempSetFeature  parameterKey: "currStepTargetTempSet"  value: int °C
  Setting temperature does NOT turn the oven on — user must explicitly
  set HVAC mode to HEAT to power on.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_APPL,
    CMD_SET_TEMP,
    DEVICE_TYPE_OVEN,
    DOMAIN,
    OVEN_MAX_TEMP,
    OVEN_MIN_TEMP,
    OVEN_TEMP_STEP,
)
from .coordinator import SmegCoordinator
from .entity import SmegEntity

_LOGGER = logging.getLogger(__name__)

_PHASE_TO_ACTION = {
    "preheating": HVACAction.HEATING,
    "cooking": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "standby": HVACAction.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmegCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SmegOvenClimate(coordinator, code)
        for code, dev in coordinator.data.items()
        if dev.get("deviceTypeId") == DEVICE_TYPE_OVEN
    ]
    async_add_entities(entities)


class SmegOvenClimate(SmegEntity, ClimateEntity):
    """Climate entity representing a Smeg oven."""

    _attr_name = "Oven"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = OVEN_MIN_TEMP
    _attr_max_temp = OVEN_MAX_TEMP
    _attr_target_temperature_step = OVEN_TEMP_STEP

    def __init__(self, coordinator: SmegCoordinator, device_code: str) -> None:
        super().__init__(coordinator, device_code)
        self._attr_unique_id = f"{device_code}_climate"
        self._optimistic_hvac_mode: HVACMode | None = None
        self._optimistic_target_temp: float | None = None

    @property
    def hvac_mode(self) -> HVACMode:
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        appl = self._state.get("appl", "OFF")
        return HVACMode.HEAT if str(appl).upper() == "ON" else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        phase = str(self._state.get("currStepCookingPhase", "standby")).lower()
        return _PHASE_TO_ACTION.get(phase, HVACAction.IDLE)

    @property
    def current_temperature(self) -> float | None:
        # Oven CB freezes currTempOven in standby (firmware defect); the
        # coordinator flags it stale past the grace window.
        if self._state.get("cavityTempStale"):
            return None
        val = self._state.get("currTempOven")
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        if self._optimistic_target_temp is not None:
            return self._optimistic_target_temp
        val = self._state.get("currStepTargetTempSet")
        try:
            t = float(val)
            return t if t > 0 else None
        except (TypeError, ValueError):
            return None

    def _check_remote_control(self) -> None:
        rc = self._state.get("remoteControl", "ON")
        if str(rc).lower() not in ("on", "true", "1"):
            raise HomeAssistantError(
                "Remote control is disabled on this appliance. "
                "Enable it on the appliance display before sending commands."
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn oven on (HEAT) or off (OFF). Requires remote control enabled."""
        self._check_remote_control()
        appl_value = "ON" if hvac_mode == HVACMode.HEAT else "OFF"
        await self._send_command(
            CMD_APPL,
            [{"parameterKey": "appl", "parameterValue": appl_value}],
        )
        self._optimistic_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature. Does NOT turn the oven on."""
        temp = kwargs.get("temperature")
        if temp is None:
            return
        await self._send_command(
            CMD_SET_TEMP,
            [{"parameterKey": "currStepTargetTempSet", "parameterValue": int(temp)}],
        )
        self._optimistic_target_temp = float(temp)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic overrides when coordinator delivers real data."""
        self._optimistic_hvac_mode = None
        self._optimistic_target_temp = None
        super()._handle_coordinator_update()

    async def _send_command(self, code: str, params: list) -> None:
        try:
            await self.coordinator.api.send_command(
                self._device_code,
                self._device.get("deviceTypeId", DEVICE_TYPE_OVEN),
                code,
                params,
            )
        except Exception:
            _LOGGER.error(
                "Failed to send command %s to %s", code, self._device_code, exc_info=True
            )
            self._optimistic_hvac_mode = None
            self._optimistic_target_temp = None
            self.async_write_ha_state()
