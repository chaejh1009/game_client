"""Ad event HTTP, acknowledgment, retry and main-thread routing regressions."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
from queue import Queue
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))

import aiohttp
from aiohttp import web
from yarl import URL
from ads_panel import AdsPanelState
from client_app import ClientApp
from controller import ClientController
from messages import Request, Result
from network import NetworkWorker
from network_api import AdEventRejected, ApiClient
from network_errors import Failure
from panels import AnalyticsPanelState, HistoryPanelState
from state import State


def acknowledgment(kind='impression', created=True):
    return {'event_id': 'd1:' + kind, 'event_type': kind, 'created': created}


def event_result(kind='impression', **kwargs):
    return Result('ad_event', request_id=1, decision_id='d1', event_type=kind,
                  ad_event=acknowledgment(kind), **kwargs)


class EventTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.status = 200
        self.payload = dict(acknowledgment(), secret='never-display')
        self.content_type = 'application/json'
        self.raw = None
        self.calls = []
        app = web.Application()
        app.router.add_post('/api/ads/events/', self.receive)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.origin = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        self.session.cookie_jar.update_cookies(
            {'sessionid': 'game-session', 'csrftoken': 'game-csrf'},
            response_url=URL(self.origin))
        self.results = []
        self.api = ApiClient(self.session, self.origin, None, self.results.append)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def receive(self, request):
        self.calls.append(await request.json())
        self.assertEqual(request.cookies['sessionid'], 'game-session')
        self.assertEqual(request.headers['X-CSRFToken'], 'game-csrf')
        self.assertEqual(request.headers['Origin'], self.origin)
        self.assertEqual(request.headers['Referer'], self.origin + '/play/')
        if self.raw is not None:
            return web.Response(body=self.raw, content_type=self.content_type, status=self.status)
        return web.json_response(self.payload, status=self.status,
                                 headers={'Location': '/must-not-follow/'} if self.status == 302 else None)

    async def test_success_and_idempotent_ack_are_safely_projected(self):
        for kind, created in (('impression', True), ('impression', False), ('click', True)):
            self.payload = dict(acknowledgment(kind, created), secret='never-display')
            self.assertEqual(await self.api.post_ad_event('d1', kind), acknowledgment(kind, created))
            self.assertEqual(self.calls[-1], {'decision_id': 'd1', 'event_type': kind})
            self.assertEqual(self.results[-1].api_path, '/api/ads/events/')
            self.assertEqual(self.results[-1].player, acknowledgment(kind, created))
            self.assertNotIn('game-csrf', repr(self.results[-1]))

    async def test_invalid_input_and_missing_csrf_never_post(self):
        for decision, kind in (('', 'click'), ('x' * 129, 'click'), (None, 'click'), ('d1', 'other')):
            with self.assertRaises(Failure):
                await self.api.post_ad_event(decision, kind)
        self.session.cookie_jar.clear()
        with self.assertRaises(Failure) as caught:
            await self.api.post_ad_event('d1', 'impression')
        self.assertTrue(caught.exception.needs_login)
        self.assertEqual(self.calls, [])

    async def test_permanent_rejections_and_login_expiry(self):
        for status in (302, 401, 400, 403, 404):
            self.status = status
            self.payload = {'error': 'impression_required', 'secret': 'never-display'}
            with self.subTest(status=status), self.assertRaises(AdEventRejected) as caught:
                await self.api.post_ad_event('d1', 'click')
            self.assertTrue(caught.exception.event_rejected)
            self.assertEqual(caught.exception.needs_login, status in (302, 401))
            self.assertIsNone(self.results[-1].player)
            self.assertNotIn('never-display', str(caught.exception))
        self.assertEqual(len(self.calls), 5)

    async def test_transient_status_and_invalid_acknowledgments(self):
        self.status = 503
        with self.assertRaises(Failure) as caught:
            await self.api.post_ad_event('d1', 'impression')
        self.assertFalse(getattr(caught.exception, 'event_rejected', False))
        self.status = 200
        for payload in ({}, [], dict(acknowledgment(), event_id='other:impression'),
                        dict(acknowledgment(), event_type='click'), dict(acknowledgment(), created=1)):
            self.payload = payload
            with self.subTest(payload=payload), self.assertRaises(Failure):
                await self.api.post_ad_event('d1', 'impression')
            self.assertIsNone(self.results[-1].player)
        for raw, mime in ((b'<html/>', 'text/html'), (b'{', 'application/json'),
                          (b' ' * 65537, 'application/json')):
            self.raw, self.content_type = raw, mime
            with self.assertRaises((Failure, ValueError)):
                await self.api.post_ad_event('d1', 'impression')
            self.assertIsNone(self.results[-1].player)


class EventStateTests(unittest.TestCase):
    def setUp(self):
        self.worker = Mock()
        self.state = State(authenticated=True)
        self.analytics, self.history = AnalyticsPanelState(), HistoryPanelState()
        self.controller = ClientController(self.state, self.analytics, self.history, self.worker)
        self.panel = AdsPanelState(request_id=1, decision={'decision_id': 'd1', 'empty': False},
                                   image_status='준비', displayed=True)
        self.clock = patch('controller.time.monotonic', return_value=100)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_display_and_impression_ack_required_before_click(self):
        self.panel.displayed = False
        self.assertFalse(self.controller.request_ad_event(self.panel, 'impression'))
        self.panel.displayed = True
        self.assertFalse(self.controller.request_ad_event(self.panel, 'click'))
        self.assertTrue(self.controller.request_ad_event(self.panel, 'impression'))
        self.assertFalse(self.controller.request_ad_event(self.panel, 'impression'))
        self.assertFalse(self.panel.begin(200, True))
        self.panel.apply_event(event_result(), 100)
        self.assertTrue(self.controller.request_ad_event(self.panel, 'click'))
        self.assertFalse(self.controller.request_ad_event(self.panel, 'click'))
        self.assertFalse(self.panel.begin(200, True))
        self.panel.apply_event(event_result('click'), 100)
        self.assertFalse(self.controller.request_ad_event(self.panel, 'click'))
        self.assertTrue(self.panel.begin(200, True))
        self.assertEqual([c.args[0].event_type for c in self.worker.submit.call_args_list],
                         ['impression', 'click'])

    def test_retry_keeps_same_decision_and_waits_two_seconds(self):
        for kind in ('impression', 'click'):
            self.panel.reset_events()
            self.panel.impression_ok = kind == 'click'
            self.assertTrue(self.controller.request_ad_event(self.panel, kind))
            first = self.worker.submit.call_args.args[0]
            self.panel.apply_event(replace(event_result(kind), kind='ad_event_error',
                                          message='HTTP 503', ad_event=None), 98.5)
            self.assertFalse(self.panel.begin(200, True))
            self.assertFalse(self.controller.request_ad_event(self.panel, kind))
            with patch('controller.time.monotonic', return_value=100.5):
                self.assertTrue(self.controller.request_ad_event(self.panel, kind))
            self.assertEqual(self.worker.submit.call_args.args[0], first)
            self.panel.apply_event(event_result(kind), 101)

    def test_stale_malformed_and_duplicate_results(self):
        self.panel.impression_pending = True
        for result in (replace(event_result(), request_id=0), replace(event_result(), decision_id='old'),
                       replace(event_result(), slot_id='lobby-banner'), replace(event_result(), event_type='other')):
            self.panel.apply_event(result, 100)
            self.assertTrue(self.panel.impression_pending)
        self.panel.apply_event(replace(event_result(), ad_event=acknowledgment(created=1)), 100)
        self.assertFalse(self.panel.impression_ok)
        self.assertEqual(self.panel.event_retry_at, 102)
        self.panel.impression_pending = True
        self.panel.apply_event(replace(event_result(), ad_event=acknowledgment(created=False)), 102)
        self.assertTrue(self.panel.impression_ok)
        self.panel.apply_event(replace(event_result(), kind='ad_event_error', event_rejected=True), 103)
        self.assertFalse(self.panel.event_rejected)

    def test_permanent_rejection_selects_new_ad_and_resets_events(self):
        self.panel.impression_ok = True
        self.controller.request_ad_event(self.panel, 'click')
        self.panel.apply_event(replace(event_result('click'), kind='ad_event_error',
                                      event_rejected=True, message='rejected'), 100)
        self.assertFalse(self.panel.click_requested)
        self.assertFalse(self.controller.request_ad_event(self.panel, 'click'))
        self.assertFalse(self.panel.begin(101.9, True))
        self.assertTrue(self.panel.begin(102, True))
        self.panel.apply(Result('ads_decision', request_id=2,
                                ad={'decision_id': 'd2', 'empty': False}), 102)
        self.assertFalse(self.panel.event_rejected)
        self.assertFalse(self.panel.impression_ok)
        self.assertEqual(self.panel.event_error, '')

    def test_lobby_logout_and_closing_never_send_events(self):
        for panel, auth, closing in ((replace(self.panel, slot_id='lobby-banner'), True, False),
                                     (self.panel, False, False), (self.panel, True, True),
                                     (replace(self.panel, decision={'empty': True}), True, False)):
            self.state.authenticated, self.state.closing = auth, closing
            self.assertFalse(self.controller.request_ad_event(panel, 'impression'))
        self.worker.submit.assert_not_called()
        lobby = replace(self.panel, slot_id='lobby-banner')
        self.assertTrue(lobby.begin(100, True))  # No pre-login impression requirement.
        self.panel.impression_pending = True
        self.panel.clear()
        self.panel.apply_event(event_result(), 100)
        self.assertFalse(self.panel.impression_ok)

    def test_mouse_visibility_and_login_expiry_routing(self):
        worker = SimpleNamespace(results=Queue())
        worker.get_result_nowait = worker.results.get_nowait
        app = ClientApp(None, self.state, self.analytics, self.history, worker,
                        self.controller, None, self.panel, AdsPanelState(slot_id='lobby-banner'))
        renderer = Mock()
        renderer.controls = {'ad_click': Mock()}
        renderer.controls['ad_click'].collidepoint.return_value = True
        self.panel.impression_ok = True
        app._handle_mouse(SimpleNamespace(pos=(1, 2)), renderer)
        self.assertTrue(self.panel.click_pending)
        self.analytics.visible = True
        with patch.object(app, '_control_names', return_value=()):
            app._handle_mouse(SimpleNamespace(pos=(1, 2)), renderer)
        self.assertEqual(self.worker.submit.call_count, 1)
        worker.results.put(replace(event_result('click'), kind='ad_event_error', needs_login=True))
        app._drain_results()
        self.assertFalse(self.state.authenticated)
        self.assertEqual(self.panel.decision, {})


class EventWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_preserves_event_identity_and_permanent_error(self):
        api, auth, socket = Mock(), Mock(), Mock()
        from unittest.mock import AsyncMock
        api.post_ad_event = AsyncMock(return_value=acknowledgment())
        worker = NetworkWorker('http://localhost', None, None, None, None)
        worker._authenticated = True
        request = Request('ad_event', request_id=7, decision_id='d1', event_type='impression')
        await worker._dispatch(request, auth, api, socket)
        result = worker.get_result_nowait()
        self.assertEqual((result.kind, result.request_id, result.decision_id, result.event_type),
                         ('ad_event', 7, 'd1', 'impression'))
        self.assertEqual(result.ad_event, acknowledgment())
        api.post_ad_event.side_effect = AdEventRejected('rejected')
        await worker._dispatch(request, auth, api, socket)
        result = worker.get_result_nowait()
        self.assertEqual(result.kind, 'ad_event_error')
        self.assertTrue(result.event_rejected)
        self.assertEqual(result.request_id, 7)

    async def test_events_do_not_block_commands_and_cancel_on_shutdown(self):
        from unittest.mock import AsyncMock
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def blocked(*args):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        api = SimpleNamespace(post_ad_event=blocked)
        socket = SimpleNamespace(command=AsyncMock(return_value={}), shutdown=AsyncMock())
        auth = SimpleNamespace(clear=Mock())
        worker = NetworkWorker('http://localhost', lambda *a: auth, lambda *a: api,
                               lambda *a: socket, None)
        worker._authenticated = True
        request = Request('ad_event', request_id=1, decision_id='d1', event_type='impression')
        worker.submit(request)
        task = asyncio.create_task(worker._serve())
        try:
            await asyncio.wait_for(started.wait(), 1)
            worker.submit(request)
            worker.submit(Request('command', action='move', direction='up'))
            for _ in range(50):
                if socket.command.called:
                    break
                await asyncio.sleep(.02)
            self.assertTrue(socket.command.called)
            result = worker.get_result_nowait()
            self.assertEqual(result.kind, 'ad_event_error')
            self.assertEqual(result.decision_id, 'd1')
        finally:
            worker.stop()
            await asyncio.wait_for(task, 1)
        self.assertTrue(cancelled.is_set())
        socket.shutdown.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
