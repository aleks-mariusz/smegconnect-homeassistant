"""Recovery regression tests using the installed HA coordinator/timer implementation.

Run with HA dependencies available: python -m unittest discover -s tests -v
No appliance or cloud requests are made.
"""
import asyncio
import tempfile
import unittest
from datetime import timedelta
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.smegconnect import coordinator as module
from custom_components.smegconnect.api import SmegApiError
from custom_components.smegconnect.websocket import SmegWebSocket


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        frame.async_setup(self.hass)
        self.api = MagicMock()
        self.api.get_device_info = AsyncMock(return_value={
            "highLevelDeviceStatus": {"status": {"currTempOven": 212, "cloudConnected": True}}
        })
        self.api.get_devices = AsyncMock(return_value=[{"deviceCode": "oven", "deviceTypeId": 7}])
        self.coordinator = module.SmegCoordinator(self.hass, MagicMock(), self.api)
        self.coordinator.data = {"oven": {"deviceTypeId": 7, "state": {"currTempOven": 22}}}
        self.unsub = None

    async def asyncTearDown(self):
        if self.unsub:
            self.unsub()
        await self.coordinator.async_stop()
        self.directory.cleanup()

    async def test_disconnect_restarts_polling_without_existing_timer(self):
        c = self.coordinator
        c.update_interval = None
        self.unsub = c.async_add_listener(lambda: None)
        self.assertIsNone(c._unsub_refresh)
        with patch.object(c, "_schedule_reconnect"):
            await c._on_ws_disconnect(None)
        self.api.get_device_info.assert_awaited_once_with("oven")
        self.assertEqual(c.data["oven"]["state"]["currTempOven"], 212)
        self.assertIsNotNone(c._unsub_refresh)

    async def test_busy_device_cannot_starve_other_device_reconciliation(self):
        c = self.coordinator
        c._ws_connected = True
        c.update_interval = timedelta(milliseconds=50)
        c.data["chiller"] = {"deviceTypeId": 12, "state": {}}
        self.unsub = c.async_add_listener(lambda: None)
        for _ in range(120):
            await c._on_ws_message({"deviceCode": "chiller", "status": {"temperature": 21}})
            await asyncio.sleep(0.01)
        self.assertGreater(self.api.get_device_info.await_count, 0)
        self.assertEqual(c.data["oven"]["state"]["currTempOven"], 212)

    async def test_startup_failure_retries_beyond_three_and_recovers(self):
        c = self.coordinator
        self.assertFalse(self.hass.is_running)
        sockets = []

        def socket(*args, **kwargs):
            ws = MagicMock()
            ws.async_connect = AsyncMock(side_effect=ConnectionError("test outage") if len(sockets) < 4 else None)
            ws.async_disconnect = AsyncMock()
            sockets.append(ws)
            return ws

        with (patch.object(module, "SmegWebSocket", side_effect=socket),
              patch.object(module, "async_get_clientsession"),
              patch.object(module, "_RECONNECT_INITIAL", 0.001),
              patch.object(module, "_RECONNECT_MAX", 0.003)):
            await c._start_websocket()
            self.assertIsNotNone(c._reconnect_task)
            await asyncio.wait_for(asyncio.shield(c._reconnect_task), 2)
        self.assertEqual(len(sockets), 5)
        self.assertTrue(c._ws_connected)
        self.assertEqual(c.update_interval, timedelta(seconds=60))
        self.assertGreater(self.api.get_device_info.await_count, 0)
        for ws in sockets[:4]:
            self.assertTrue(ws.async_disconnect.called)
        await c._on_ws_message({"deviceCode": "oven", "status": {"currTempOven": 214}})
        self.assertEqual(c._stomp_failures, 0)

    async def test_silent_connected_socket_replaced_while_rest_recovers(self):
        c = self.coordinator
        c._ws_connected = True
        c._last_ws_message = monotonic() - 181
        c._ws = MagicMock(async_disconnect=AsyncMock())
        with patch.object(c, "_schedule_reconnect") as reconnect:
            await c.async_refresh()
        c._ws.async_disconnect.assert_awaited_once()
        reconnect.assert_called_once()
        self.assertFalse(c._ws_connected)
        self.assertEqual(c.data["oven"]["state"]["currTempOven"], 212)

    async def test_rest_response_cannot_overwrite_push_received_during_request(self):
        c = self.coordinator

        async def fetch(code):
            await c._on_ws_message({"deviceCode": code, "status": {"currTempOven": 215}})
            return {"highLevelDeviceStatus": {"status": {"currTempOven": 210}}}

        self.api.get_device_info.side_effect = fetch
        await c.async_refresh()
        self.assertEqual(c.data["oven"]["state"]["currTempOven"], 215)

    async def test_rest_failure_is_visible_and_later_refresh_recovers(self):
        c = self.coordinator
        c._ws_connected = True
        self.api.get_device_info.side_effect = SmegApiError("test cloud outage")
        await c.async_refresh()
        self.assertFalse(c.last_update_success)
        self.api.get_device_info.side_effect = None
        await c.async_refresh()
        self.assertTrue(c.last_update_success)

    async def test_unload_cancels_retry_and_poll_timer(self):
        c = self.coordinator
        self.unsub = c.async_add_listener(lambda: None)
        c._record_ws_failure()
        task = c._reconnect_task
        await c.async_stop()
        self.assertTrue(task.done())
        self.assertIsNone(c._unsub_refresh)
        with patch.object(c, "async_request_refresh") as refresh:
            await c._on_ws_disconnect(None)
            refresh.assert_not_called()


class WebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disconnected = AsyncMock()
        self.message = AsyncMock()
        self.client = SmegWebSocket(MagicMock(), MagicMock(), self.disconnected, self.message)

    async def test_close_frame_finishes_receive(self):
        self.client._ws = MagicMock()
        self.client._ws.receive = AsyncMock(return_value=MagicMock(type=aiohttp.WSMsgType.CLOSE))
        self.assertIsNone(await self.client._recv_stomp_frame())
        self.client._ws.receive.assert_awaited_once()

    async def test_listener_close_cleans_up_heartbeat_and_socket_once(self):
        c = self.client
        c._running = True
        ws = c._ws = MagicMock(closed=False, send_str=AsyncMock(), close=AsyncMock())
        c._heartbeat_task = asyncio.create_task(asyncio.sleep(100))
        heartbeat = c._heartbeat_task
        with patch.object(c, "_recv_stomp_frame", AsyncMock(return_value=None)):
            await c._listen()
        self.assertTrue(heartbeat.done())
        ws.close.assert_awaited_once()
        self.disconnected.assert_awaited_once_with(None)
        self.assertIsNone(c._ws)

    async def test_callback_exception_is_not_swallowed_as_json_error(self):
        self.message.side_effect = RuntimeError("test callback defect")
        with self.assertRaisesRegex(RuntimeError, "callback defect"):
            await self.client._dispatch({"command": "MESSAGE", "body": '{"deviceCode":"oven"}'})

    async def test_invalid_json_does_not_call_coordinator(self):
        await self.client._dispatch({"command": "MESSAGE", "body": "{"})
        self.message.assert_not_awaited()

    async def test_intentional_disconnect_does_not_schedule_reconnect(self):
        c = self.client
        c._running = True
        async def receive():
            await asyncio.sleep(100)
        with patch.object(c, "_recv_stomp_frame", side_effect=receive):
            c._listen_task = asyncio.create_task(c._listen())
            await asyncio.sleep(0)
            await c.async_disconnect()
        self.disconnected.assert_not_awaited()
