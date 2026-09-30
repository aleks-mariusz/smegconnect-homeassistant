"""Smeg cloud REST API client."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .auth import SmegAuth
from .const import API_BASE, DEVICE_TYPE_BLAST_CHILLER, DEVICE_TYPE_COMMAND_VERSION

_LOGGER = logging.getLogger(__name__)


class SmegApiError(Exception):
    """Raised when an API call fails."""


class SmegApi:
    """Wraps all Smeg cloud REST endpoints."""

    def __init__(self, session: aiohttp.ClientSession, auth: SmegAuth) -> None:
        self._session = session
        self._auth = auth

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return all devices enrolled to this account."""
        headers = await self._auth.get_headers()
        async with self._session.get(
            f"{API_BASE}/api/v1/devices", headers=headers
        ) as resp:
            await _check(resp)
            data = await resp.json()
        # Response: {"devices": {"<code>": {...}, ...}}
        return list(data.get("devices", {}).values())

    async def get_device_info(self, device_code: str) -> dict[str, Any]:
        """Return full device info including state and availableCommands."""
        headers = await self._auth.get_headers()
        async with self._session.get(
            f"{API_BASE}/api/v1/devices/{device_code}/info", headers=headers
        ) as resp:
            await _check(resp)
            return await resp.json()

    async def send_command(
        self,
        device_code: str,
        device_type_id: int,
        command_code: str,
        params: list[dict[str, Any]] | None = None,
    ) -> None:
        """Send a command to a device. Raises SmegApiError on non-202."""
        headers = await self._auth.get_headers()
        version = DEVICE_TYPE_COMMAND_VERSION.get(device_type_id, "3.0")
        endpoint_version = "v2" if device_type_id == DEVICE_TYPE_BLAST_CHILLER else "v1"
        body = {
            "deviceCommandCode": command_code,
            "version": version,
            "deviceCommandParameterInstances": params or [],
        }
        async with self._session.post(
            f"{API_BASE}/api/{endpoint_version}/devices/{device_code}/commands",
            headers=headers,
            json=body,
        ) as resp:
            await _check(resp, expected_range=(200, 202))


async def _check(
    resp: aiohttp.ClientResponse,
    expected: int = 200,
    expected_range: tuple[int, ...] | None = None,
) -> None:
    ok = expected_range if expected_range else (expected,)
    if resp.status in ok:
        return
    text = await resp.text()
    raise SmegApiError(f"HTTP {resp.status}: {text[:200]}")
