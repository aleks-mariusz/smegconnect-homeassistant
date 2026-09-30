"""Services for SmegConnect appliances."""
from __future__ import annotations

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

        seconds_since_midnight = _seconds_since_midnight()

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

            await coordinator.api.send_command(
                device_code,
                device_type_id,
                CMD_MANUAL_CLOCK,
                [{"parameterKey": "manualClock", "parameterValue": seconds_since_midnight}],
            )
            await coordinator.async_request_refresh()

            _LOGGER.debug(
                "Sent %s=%s to %s",
                CMD_MANUAL_CLOCK,
                seconds_since_midnight,
                device_code,
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


def _seconds_since_midnight() -> int:
    now = dt_util.now()
    return (now.hour * 3600) + (now.minute * 60) + now.second
