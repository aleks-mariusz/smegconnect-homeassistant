"""Smeg cloud authentication — login and proactive JWT token refresh."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import API_BASE, TENANT

_LOGGER = logging.getLogger(__name__)

AUTH_ENDPOINT = f"{API_BASE}/api/v1/auth/token"
REFRESH_ENDPOINT = f"{API_BASE}/api/v1/auth/refreshToken"

# Refresh this many seconds before the JWT actually expires
TOKEN_REFRESH_EARLY_S = 120


class SmegAuthError(Exception):
    """Raised when login or token refresh fails."""


def _jwt_exp(token: str) -> int:
    """Decode the exp claim from a JWT without verifying the signature."""
    try:
        payload_b64 = token.split(".")[1]
        # Base64url padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload["exp"])
    except Exception:
        # If we can't decode it, treat as already expired
        return 0


class SmegAuth:
    """Manages access/refresh tokens for the Smeg cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str,
        iot_user_code: str,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._iot_user_code = iot_user_code
        self._lock = asyncio.Lock()
        # Called after a successful token refresh so the config entry can be updated
        self.on_tokens_refreshed: Any = None

    @classmethod
    async def login(
        cls,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> dict[str, str]:
        """Authenticate with Smeg cloud. Returns {accessToken, refreshToken, iotUserCode}."""
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.post(
            AUTH_ENDPOINT,
            json={"username": username, "password": password},
            headers={"x-tenant": TENANT, "Content-Type": "application/json;charset=UTF-8"},
            timeout=timeout,
        ) as resp:
            _LOGGER.debug("Login response HTTP %s", resp.status)
            if resp.status == 401:
                raise SmegAuthError("Invalid credentials")
            if resp.status != 200:
                raise SmegAuthError(f"Login failed with HTTP {resp.status}")
            return await resp.json(content_type=None)

    @property
    def iot_user_code(self) -> str:
        return self._iot_user_code

    async def get_headers(self) -> dict[str, str]:
        """Return auth headers with a valid (refreshed-if-needed) access token."""
        token = await self._ensure_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "x-tenant": TENANT,
            "Content-Type": "application/json;charset=UTF-8",
            "accept-hlsschema": "3.0",
            "Cache-Control": "no-cache",
        }

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        return await self._ensure_valid_token()

    async def _ensure_valid_token(self) -> str:
        exp = _jwt_exp(self._access_token)
        if time.time() < exp - TOKEN_REFRESH_EARLY_S:
            return self._access_token

        async with self._lock:
            # Re-check after acquiring lock — another coroutine may have refreshed
            exp = _jwt_exp(self._access_token)
            if time.time() < exp - TOKEN_REFRESH_EARLY_S:
                return self._access_token
            await self._do_refresh()

        return self._access_token

    async def _do_refresh(self) -> None:
        _LOGGER.debug("Refreshing Smeg access token")
        async with self._session.post(
            REFRESH_ENDPOINT,
            json={"refreshToken": self._refresh_token},
            headers={"x-tenant": TENANT, "Content-Type": "application/json;charset=UTF-8"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                raise SmegAuthError(f"Token refresh failed with HTTP {resp.status}")
            data = await resp.json()

        # Smeg normally returns only accessToken on refresh (verified live).
        # Keep the existing refresh token unless the server explicitly rotates
        # it. Validate before changing either field so failures are atomic.
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken", self._refresh_token)
        if not isinstance(access_token, str) or not access_token:
            raise SmegAuthError("Token refresh response has no valid accessToken")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise SmegAuthError("Token refresh response has no valid refreshToken")
        self._access_token = access_token
        self._refresh_token = refresh_token

        if self.on_tokens_refreshed is not None:
            try:
                await self.on_tokens_refreshed(
                    self._access_token, self._refresh_token
                )
            except Exception:
                _LOGGER.warning("Failed to persist refreshed tokens", exc_info=True)
