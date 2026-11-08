"""Services for SmegConnect appliances."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.util import dt as dt_util

from .const import (
    CMD_MANUAL_CLOCK,
    DEVICE_TYPE_BLAST_CHILLER,
    DEVICE_TYPE_NAMES,
    DEVICE_TYPE_OVEN,
    DOMAIN,
    SERVICE_SYNC_CLOCK,
)
from .api import SmegApi
from .coordinator import SmegCoordinator

_LOGGER = logging.getLogger(__name__)

_SYNC_CLOCK_SUPPORTED_DEVICE_TYPES = frozenset(
    {DEVICE_TYPE_OVEN, DEVICE_TYPE_BLAST_CHILLER}
)


async def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_CLOCK):
        return

    async def _async_handle_sync_clock(call: ServiceCall) -> None:
        entity_ids = await async_extract_entity_ids(call)
        targets = _resolve_targets(hass, entity_ids)
        if not targets:
            raise HomeAssistantError("Select at least one SmegConnect device target.")

        now = dt_util.now()
        clock_seconds = _seconds_of_day(now)

        # --- Phase 1: send. All devices are commanded back-to-back (~1 s apart)
        # so their clocks land at nearly the same instant, per the automation use
        # case. Verification happens afterwards in phase 2.
        sent: list[tuple[SmegCoordinator, str, str]] = []
        for coordinator, device_code in targets:
            device = coordinator.data.get(device_code)
            if device is None:
                raise HomeAssistantError(
                    f"Smeg device {device_code} is no longer available."
                )

            device_type_id = int(device.get("deviceTypeId", 0))
            if device_type_id not in _SYNC_CLOCK_SUPPORTED_DEVICE_TYPES:
                device_type_name = DEVICE_TYPE_NAMES.get(
                    device_type_id, f"Device type {device_type_id}"
                )
                raise HomeAssistantError(
                    f"Clock sync is not supported for {device_type_name}."
                )

            device_name = DEVICE_TYPE_NAMES.get(
                device_type_id, f"Device type {device_type_id}"
            )
            state = device.get("state", {})
            if not _remote_control_on(state):
                # The cloud accepts commands with 202 while the appliance ignores
                # them, so a plain send would silently do nothing (observed live).
                _LOGGER.warning(
                    "Smeg clock sync skipped for %s (%s): remote control is off "
                    "on the appliance display.",
                    device_code,
                    device_name,
                )
                continue

            # App-exact clock recipe (capture evidence 2026-08-20 + 2026-11-08):
            # plain manualClockFeature, no preamble, value typed per data model.
            # A string value to an oven is echoed into state but silently
            # dropped by the panel — the root cause of the clock sync defect.
            await coordinator.api.send_command(
                device_code,
                device_type_id,
                CMD_MANUAL_CLOCK,
                [{
                    "parameterKey": "manualClock",
                    "parameterValue": _clock_param_value(clock_seconds, device_type_id),
                }],
            )
            await coordinator.async_request_refresh()

            _LOGGER.info(
                "Sent Smeg clock sync to %s (%s): %s=%s",
                device_code,
                device_name,
                CMD_MANUAL_CLOCK,
                clock_seconds,
            )
            sent.append((coordinator, device_code, device_name))

        # --- Phase 2: verify adoption. The cloud returns 202 regardless; ovens
        # are known to refuse remote clock sets at firmware level, and the state
        # briefly echoes the commanded value, so confirmation needs two reads
        # spaced past the echo window.
        if sent:
            results = await asyncio.gather(
                *(
                    _verify_clock_adopted(coordinator.api, device_code)
                    for coordinator, device_code, _ in sent
                )
            )
            for (_, device_code, device_name), adopted in zip(sent, results):
                if adopted:
                    _LOGGER.info("Smeg clock sync confirmed on %s (%s).", device_code, device_name)
                else:
                    _LOGGER.warning(
                        "Smeg clock sync NOT adopted by %s (%s): the appliance "
                        "refused the remote clock set. Set the clock on the "
                        "appliance display; see the Panel Clock sensor for drift.",
                        device_code,
                        device_name,
                    )

    hass.services.async_register(DOMAIN, SERVICE_SYNC_CLOCK, _async_handle_sync_clock)


def _resolve_targets(
    hass: HomeAssistant, entity_ids: set[str]
) -> list[tuple[SmegCoordinator, str]]:
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    targets: list[tuple[SmegCoordinator, str]] = []
    seen_device_ids: set[str] = set()

    for entity_id in entity_ids:
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None or entity_entry.device_id is None:
            continue
        if entity_entry.device_id in seen_device_ids:
            continue

        device_entry = device_registry.async_get(entity_entry.device_id)
        if device_entry is None:
            continue

        device_code = _extract_device_code(device_entry)
        if device_code is None:
            continue

        coordinator = _find_coordinator(hass, device_code)
        if coordinator is None:
            raise HomeAssistantError(
                f"Smeg device {device_code} is not available for commands."
            )

        seen_device_ids.add(entity_entry.device_id)
        targets.append((coordinator, device_code))

    return targets


def _extract_device_code(device_entry: dr.DeviceEntry) -> str | None:
    for identifier_domain, identifier in device_entry.identifiers:
        if identifier_domain == DOMAIN:
            return identifier

    return None


def _find_coordinator(hass: HomeAssistant, device_code: str) -> SmegCoordinator | None:
    for coordinator in hass.data.get(DOMAIN, {}).values():
        if isinstance(coordinator, SmegCoordinator) and device_code in coordinator.data:
            return coordinator

    return None


def _seconds_of_day(now) -> int:
    """Seconds since local midnight. The app sends raw seconds (no alignment):
    captures show e.g. 60475 (16:47:55) and the panels keep seconds."""
    return (now.hour * 3600) + (now.minute * 60) + now.second


def _clock_param_value(seconds_of_day: int, device_type_id: int):
    """manualClock parameter value, typed per the device's data model.

    Capture evidence: ovens (data models 2306/2818) receive a JSON integer
    (2026-11-08 capture); the blast chiller (3332) receives a JSON string
    (2026-08-20 capture). A string to an oven is echoed into its state but
    silently dropped by the panel firmware.
    """
    if device_type_id == DEVICE_TYPE_BLAST_CHILLER:
        return str(seconds_of_day)
    return int(seconds_of_day)


def _remote_control_on(state: dict) -> bool:
    """Whether the appliance reports remote control enabled.

    Ovens report "ON"/"OFF" strings, the blast chiller reports 0/1 (mirrors the
    remote_control binary sensor's on_values). A missing field is treated as
    enabled — the post-send adoption check catches real refusals.
    """
    value = state.get("remoteControl")
    if value is None:
        return True
    return str(value).strip().lower() in ("on", "true", "1")


def _extract_manual_clock(info: dict):
    """Pull manualClock out of a raw /api/v1/devices/{code}/info response."""
    status = info.get("highLevelDeviceStatus")
    if not isinstance(status, dict):
        status = {}
    return status.get("status", {}).get("manualClock")


def _clock_adopted(manual_clock, expected_seconds: int) -> bool:
    """True when the appliance's reported clock is within 90 s of expected."""
    if manual_clock is None:
        return False
    try:
        value = int(manual_clock)
    except (TypeError, ValueError):
        return False
    return abs(value - expected_seconds) <= 90


async def _verify_clock_adopted(api: SmegApi, device_code: str) -> bool:
    """Confirm the appliance actually adopted the clock (two spaced reads).

    The cloud 202s regardless and the appliance state briefly echoes the
    commanded value, so neither an immediate match nor an immediate mismatch
    is trustworthy. The verdict is the SECOND read (+80 s): past the echo
    window (observed decay < 96 s) and past MQTT command latency (the app's
    own /info read 3 s after a set still showed the old clock). Each read
    compares against the live expected time-of-day, so a ticking adopted
    clock passes and a stale +1 h fossil fails.
    """
    for delay in (20, 60):
        await asyncio.sleep(delay)
        now = dt_util.now()
        expected = (now.hour * 3600) + (now.minute * 60) + now.second
        info = await api.get_device_info(device_code)
        adopted = _clock_adopted(_extract_manual_clock(info), expected)
        _LOGGER.debug(
            "Smeg clock verify read for %s: manualClock=%s expected=%s adopted=%s",
            device_code,
            _extract_manual_clock(info),
            expected,
            adopted,
        )
    return bool(adopted)
