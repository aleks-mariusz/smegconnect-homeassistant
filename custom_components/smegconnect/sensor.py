"""Sensor entities for Smeg appliances."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    APPLIANCE_CATEGORY_NAMES,
    DEVICE_TYPE_BLAST_CHILLER,
    DEVICE_TYPE_OVEN,
    DOMAIN,
    FAILURE_LABEL_NONE,
    decode_fw_version,
)
from .coordinator import SmegCoordinator
from .entity import SmegEntity


@dataclass(frozen=True, kw_only=True)
class SmegSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with Smeg-specific fields."""

    state_field: str = ""
    device_types: tuple[int, ...] = ()
    # Optional transform applied to the raw state value before returning.
    value_fn: Callable[[Any], Any] | None = None


SENSOR_DESCRIPTIONS: tuple[SmegSensorDescription, ...] = (
    # -----------------------------------------------------------------------
    # Oven — primary sensors
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="cavity_temperature",
        name="Cavity Temperature",
        state_field="currTempOven",
        device_types=(DEVICE_TYPE_OVEN,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SmegSensorDescription(
        key="target_temperature",
        name="Target Temperature",
        state_field="currStepTargetTempSet",
        device_types=(DEVICE_TYPE_OVEN,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SmegSensorDescription(
        key="cook_elapsed",
        name="Cooking Elapsed Time",
        state_field="currSeqElapsedTime",
        device_types=(DEVICE_TYPE_OVEN,),
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SmegSensorDescription(
        key="cook_remaining",
        name="Cooking Remaining Time",
        state_field="currSeqDuration",
        device_types=(DEVICE_TYPE_OVEN,),
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SmegSensorDescription(
        key="cook_phase",
        name="Cooking Phase",
        state_field="currStepCookingPhase",
        device_types=(DEVICE_TYPE_OVEN,),
    ),
    # -----------------------------------------------------------------------
    # Oven — error/failure sensors (diagnostic)
    # failureCode=0 / failureLabel="notification.none" → no error → returns None
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="error_description",
        name="Error Description",
        state_field="failureLabel",
        device_types=(DEVICE_TYPE_OVEN,),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="error_code",
        name="Error Code",
        state_field="failureCode",
        device_types=(DEVICE_TYPE_OVEN,),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # -----------------------------------------------------------------------
    # Blast chiller — alarm sensor (diagnostic)
    # coordinator synthesises chiller_alarm_description from alarmStatus_* bits
    # using BLAST_CHILLER_ALARM_MAP (source: BlastChillerStatusKt.java in Plus APK).
    # Returns "None" when no alarms active; comma-separated fault names otherwise.
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="chiller_alarm_description",
        name="Active Alarms",
        state_field="chiller_alarm_description",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # -----------------------------------------------------------------------
    # Shared — Wi-Fi / connectivity (diagnostic)
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="wifi_signal",
        name="Wi-Fi Signal",
        state_field="CBWiFiLevel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="wifi_ssid",
        name="Wi-Fi Network",
        state_field="CBstaWifiSSID",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # -----------------------------------------------------------------------
    # Shared — connectivity board identity (diagnostic)
    # -----------------------------------------------------------------------
    # Brand ID omitted: always 1 (Smeg) — no diagnostic value.
    SmegSensorDescription(
        key="category_id",
        name="Category ID (APPL_CAT_ID)",
        state_field="CBapplianceCategoryId",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Human-readable decode of Category ID (4=Oven, 47=Blast Chiller etc.)
    SmegSensorDescription(
        key="category_name",
        name="Appliance Category",
        state_field="CBapplianceCategoryId",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: APPLIANCE_CATEGORY_NAMES.get(int(v), str(v)) if v is not None else None,
    ),
    SmegSensorDescription(
        key="model_id",
        name="Model ID (APPL_MODEL_ID)",
        state_field="CBapplianceModelId",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="data_model_id",
        name="Data Model ID (APPL_DATAMODEL_ID)",
        state_field="CBapplianceDataModelId",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="compliance_id",
        # Static IEC/EN compliance certification ID — changes only if Smeg recertifies
        # after a major firmware update. Disabled by default as it rarely changes.
        name="SW Compliance ID",
        state_field="CBcomplianceId",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # CB part number — oven firmware has a typo "CBpartlNumber"; chiller uses "CBpartNumber"
    SmegSensorDescription(
        key="part_number",
        name="CB Part Number",
        state_field="CBpartlNumber",
        device_types=(DEVICE_TYPE_OVEN,),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SmegSensorDescription(
        key="chiller_part_number",
        name="CB Part Number",
        state_field="CBpartNumber",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # -----------------------------------------------------------------------
    # Shared — decoded firmware versions (diagnostic)
    #
    # Encoding: oven = 24-bit little-endian int; blast chiller = 4-char base64.
    # Both decoded to "major.minor.patch" via decode_fw_version().
    #
    # Parenthetical labels are what appears on the appliance's own screen
    # (physical display diagnostics menu) and in the SmegConnect app Product tab.
    # -----------------------------------------------------------------------
    # Connectivity Board — shown in app Connectivity tab and on physical screen
    SmegSensorDescription(
        key="cb_firmware",
        name="CB Firmware (SOFTW CB)",
        state_field="CBSwRelease",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Power board — shows on physical screen diagnostics
    SmegSensorDescription(
        key="main_software",
        name="Main Software (SOFTW)",
        state_field="pwrBoardFwRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="power_board_kernel",
        name="Power Board Kernel (KERNEL POWER)",
        state_field="pwrBoardKernlRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="parameter_software",
        # PARSW = Parameter Software — stores machine-specific calibration & settings.
        # The PARSW number (e.g. 0436 for oven, 0526 for chiller) is the ADF variant
        # and is static per device; it is not exposed via the live API.
        name="Parameter Software (PARSW)",
        state_field="pwrBoardParFwRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    # Display board (TFT)
    SmegSensorDescription(
        key="display_firmware",
        name="Display Firmware (FIRMW TFT)",
        state_field="dispBoardFwRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="display_kernel",
        name="Display Kernel (KERNEL TFT)",
        state_field="dispBoardKernlRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="display_schema",
        name="Display Schema (SCHTX)",
        state_field="dispBoardParFwRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    # Meat probe board
    SmegSensorDescription(
        key="probe_firmware",
        name="Meat Probe Firmware (MASTER PROBE)",
        state_field="meatProbeBoardFwRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="probe_kernel",
        name="Meat Probe Kernel (KERNEL PROBE)",
        state_field="meatProbeBoardKernlRel",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=decode_fw_version,
    ),
    SmegSensorDescription(
        key="cb_temperature",
        name="Connectivity Board Temperature",
        state_field="CBtemperaure",   # firmware typo preserved
        device_types=(DEVICE_TYPE_OVEN,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="chiller_cb_temperature",
        name="Connectivity Board Temperature",
        state_field="CBtemperature",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SmegSensorDescription(
        key="compressor_runtime",
        name="Compressor Runtime",
        state_field="compressorWorkTime",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # -----------------------------------------------------------------------
    # Blast chiller — primary sensors
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="cavity_temperature",
        name="Cavity Temperature",
        state_field="currTempCavity",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SmegSensorDescription(
        key="step1_target_temp",
        name="Step 1 Target Temperature",
        state_field="stepOneTargetTempSet",
        device_types=(DEVICE_TYPE_BLAST_CHILLER,),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # -----------------------------------------------------------------------
    # Shared — meat probe temperature
    # Returns None when probe is not connected — the reading is meaningless.
    # -----------------------------------------------------------------------
    SmegSensorDescription(
        key="meat_probe_temperature",
        name="Meat Probe Temperature",
        state_field="currTempMeatProbe",
        device_types=(DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmegCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SmegSensorEntity] = []

    for device_code, device in coordinator.data.items():
        type_id = device.get("deviceTypeId", 0)
        for desc in SENSOR_DESCRIPTIONS:
            if type_id in desc.device_types:
                entities.append(SmegSensorEntity(coordinator, device_code, desc))

    async_add_entities(entities)


class SmegSensorEntity(SmegEntity, SensorEntity):
    """A sensor entity for a Smeg appliance state field."""

    entity_description: SmegSensorDescription

    def __init__(
        self,
        coordinator: SmegCoordinator,
        device_code: str,
        description: SmegSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_code)
        self.entity_description = description
        self._attr_unique_id = f"{device_code}_{description.key}"

    @property
    def native_value(self) -> Any:
        value = self._state.get(self.entity_description.state_field)
        key = self.entity_description.key

        # --- Cavity temperature (firmware staleness defect) ---
        # The oven CB stops refreshing currTempOven at the standby transition;
        # past the grace window the reading is a fossil. Report 'unknown' and
        # keep the last trusted value in attributes (see coordinator).
        if key == "cavity_temperature" and self._state.get("cavityTempStale"):
            return None

        # --- Meat probe temperature ---
        # Return None when probe is not electrically connected.
        # Oven: meatProbeInserted = string ("meat probe not inserted as expected")
        # Blast chiller: meatProbeInserted = integer 0
        if key == "meat_probe_temperature":
            inserted_raw = self._state.get("meatProbeInserted", "")
            inserted_str = str(inserted_raw).lower()
            if "not inserted" in inserted_str or inserted_str in ("0", "false", ""):
                return None
            if value is None:
                return None
            try:
                if int(value) >= 65000:   # oven firmware sentinel (65530)
                    return None
            except (TypeError, ValueError):
                pass
            return value

        # --- Error Description ---
        # Returns "None" (visible string) when no error, actual label when error active.
        if key == "error_description":
            if int(self._state.get("failureCode", 0)) == 0:
                return "None"
            if value is None:
                return "None"
            label = str(value)
            if label.lower() == FAILURE_LABEL_NONE.lower():
                return "None"
            return label

        # --- Error Code ---
        # Returns "None" (visible string) when no error (failureCode == 0).
        if key == "error_code":
            try:
                code = int(value) if value is not None else 0
                return "None" if code == 0 else code
            except (TypeError, ValueError):
                return "None"

        # --- Cooking remaining time ---
        if key == "cook_remaining":
            if value is None:
                return None
            elapsed = self._state.get("currSeqElapsedTime", 0)
            try:
                return max(0, int(value) - int(elapsed))
            except (TypeError, ValueError):
                pass

        # --- Apply value_fn transform (e.g. firmware version decode) ---
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(value)

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Cavity-temperature staleness context (see coordinator tracker).

        Only ovens carry the tracker fields; other devices get no attributes.
        """
        if self.entity_description.key != "cavity_temperature":
            return None
        if "cavityTempStale" not in self._state and "cavityTempLastAccurate" not in self._state:
            return None
        attrs: dict[str, Any] = {}
        if self._state.get("cavityTempStale"):
            attrs["stale"] = True
            attrs["stale_since"] = self._state.get("cavityTempStaleSince")
            attrs["note"] = (
                "Oven firmware stops updating cavity temperature in standby; "
                "this reading is frozen and suppressed"
            )
        else:
            attrs["stale"] = False
        last_accurate = self._state.get("cavityTempLastAccurate")
        if last_accurate is not None:
            attrs["last_accurate_value"] = last_accurate
        return attrs
