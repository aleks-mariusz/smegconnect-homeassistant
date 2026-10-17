"""Credential-free transport health for SmegConnect diagnostics."""
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    now = monotonic()
    return {
        "websocket_connected": coordinator._ws_connected,
        "consecutive_websocket_failures": coordinator._stomp_failures,
        "reconnect_pending": bool(coordinator._reconnect_task and not coordinator._reconnect_task.done()),
        "last_device_push_age_seconds": (
            round(now - coordinator._last_ws_message, 1)
            if coordinator._last_ws_message is not None else None
        ),
        "last_rest_update_age_seconds": (
            round(now - coordinator._last_rest_update, 1)
            if coordinator._last_rest_update is not None else None
        ),
        "poll_interval_seconds": coordinator.update_interval.total_seconds(),
        "last_update_success": coordinator.last_update_success,
        "device_count": len(coordinator.data),
    }
