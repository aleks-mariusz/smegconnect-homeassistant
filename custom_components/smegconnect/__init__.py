"""SmegConnect integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmegApi
from .auth import SmegAuth
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_IOT_USER_CODE,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SmegCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smeg from a config entry."""
    session = async_get_clientsession(hass)

    # Migrate legacy config entry titles (created before title format was established)
    email = entry.data.get(CONF_USERNAME, "")
    expected_title = f"Devices registered on SmegConnect to {email}"
    if entry.title != expected_title:
        hass.config_entries.async_update_entry(entry, title=expected_title)

    auth = SmegAuth(
        session,
        access_token=entry.data[CONF_ACCESS_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        iot_user_code=entry.data[CONF_IOT_USER_CODE],
    )

    # Persist refreshed tokens back to the config entry so they survive restarts
    async def _save_tokens(access_token: str, refresh_token: str) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
            },
        )

    auth.on_tokens_refreshed = _save_tokens

    api = SmegApi(session, auth)
    coordinator = SmegCoordinator(hass, auth, api)

    try:
        await coordinator.async_setup()
    except Exception as err:
        _LOGGER.error("Failed to set up Smeg integration: %s", err)
        # Try re-logging with stored credentials on setup failure
        try:
            _LOGGER.info("Attempting re-login with stored credentials")
            tokens = await SmegAuth.login(
                session,
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
            )
            auth._access_token = tokens["accessToken"]
            auth._refresh_token = tokens["refreshToken"]
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_ACCESS_TOKEN: tokens["accessToken"],
                    CONF_REFRESH_TOKEN: tokens["refreshToken"],
                },
            )
            await coordinator.async_setup()
        except Exception as retry_err:
            _LOGGER.error("Re-login also failed: %s", retry_err)
            return False

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    async def _async_stop_coordinator(_event=None) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_coordinator)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SmegCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
