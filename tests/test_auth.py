"""Token renewal contract regression tests; no network access."""
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.smegconnect.auth import SmegAuth, SmegAuthError


class AuthTests(unittest.IsolatedAsyncioTestCase):
    def auth_for_response(self, data):
        response = MagicMock(status=200, json=AsyncMock(return_value=data))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post.return_value = context
        auth = SmegAuth(session, "old-access", "existing-refresh", "user")
        auth.on_tokens_refreshed = AsyncMock()
        return auth

    async def test_access_only_response_preserves_and_persists_refresh_token(self):
        auth = self.auth_for_response({"accessToken": "new-access"})
        await auth._do_refresh()
        self.assertEqual(auth._access_token, "new-access")
        self.assertEqual(auth._refresh_token, "existing-refresh")
        auth.on_tokens_refreshed.assert_awaited_once_with("new-access", "existing-refresh")
        # Renewal continues to use the retained token on subsequent refreshes.
        await auth._do_refresh()
        self.assertEqual(auth._session.post.call_args.kwargs["json"],
                         {"refreshToken": "existing-refresh"})

    async def test_rotated_refresh_token_is_persisted(self):
        auth = self.auth_for_response({"accessToken": "new-access", "refreshToken": "new-refresh"})
        await auth._do_refresh()
        auth.on_tokens_refreshed.assert_awaited_once_with("new-access", "new-refresh")

    async def test_invalid_response_does_not_partially_replace_tokens(self):
        auth = self.auth_for_response({"accessToken": "new-access", "refreshToken": None})
        with self.assertRaises(SmegAuthError):
            await auth._do_refresh()
        self.assertEqual(auth._access_token, "old-access")
        self.assertEqual(auth._refresh_token, "existing-refresh")
        auth.on_tokens_refreshed.assert_not_awaited()
