"""Offline regressions for finalized-window transport and panel state."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from queue import Queue
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))

from controller import ClientController
from messages import Request, Result
from network import NetworkWorker
from network_api import ApiClient
from network_errors import Failure
from network_validation import ResponseValidator
from panels import AnalyticsPanelState, HistoryPanelState
from state import State


ORIGIN = 'http://127.0.0.1:8000'
PATH = '/api/analytics/windows/'
PLAYER = {'player_id': 7, 'room_id': 'room-01', 'x': 3, 'y': 2,
          'coins': 12, 'version': 9}
ROW = {'kind': 'tumbling', 'window_start': '2026-09-22T10:00:00+09:00',
       'window_end': '2026-09-22T10:05:00+09:00',
       'event_type': 'player.moved', 'count': 8}
WINDOWS = {'available': True, 'generated_at': '2026-09-22T10:06:00+09:00',
           'windows': [ROW, {**ROW, 'kind': 'sliding', 'count': 13}]}


class FakeResponse:
    def __init__(self, payload=WINDOWS, status=200,
                 content_type='application/json', error=None):
        self.status = status
        self.content_type = content_type
        self.body = (json.dumps(payload).encode() if not isinstance(payload, bytes)
                     else payload)
        self.error = error
        self.content = self
        self.read_count = 0

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self

    async def __aexit__(self, *_args):
        return False

    async def iter_chunked(self, size):
        self.read_count += 1
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class RecordingWorker:
    def __init__(self):
        self.requests = []

    def submit(self, request):
        self.requests.append(request)


class WindowsValidationTests(unittest.TestCase):
    def test_projection_removes_raw_records_and_authentication_fields(self):
        payload = deepcopy(WINDOWS)
        for key in ('auth', 'cookies', 'csrf', 'raw_value', 'evidence', 'player'):
            payload[key] = 'must-not-display'
            payload['windows'][0][key] = 'must-not-display'
        safe = ResponseValidator().validate_windows(payload)
        self.assertEqual(safe, WINDOWS)
        self.assertNotIn('must-not-display', repr(safe))
        self.assertIsNot(safe['windows'][0], payload['windows'][0])

    def test_unavailable_is_distinct_from_available_empty(self):
        validator = ResponseValidator()
        self.assertEqual(validator.validate_windows({
            'available': False, 'generated_at': None, 'windows': [],
            'auth': 'must-not-display',
        }), {'available': False})
        empty = {**WINDOWS, 'windows': []}
        self.assertEqual(validator.validate_windows(empty), empty)

    def test_rejects_invalid_top_level_shape_and_bounds(self):
        invalid = [{}, {'available': 1}, {'available': 'true'}]
        invalid += [{**WINDOWS, 'generated_at': value}
                    for value in (None, '', 42, 'x' * 121)]
        invalid += [{**WINDOWS, 'windows': value}
                    for value in (None, {}, (), [ROW] * 101, [None])]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(Failure):
                ResponseValidator().validate_windows(payload)

    def test_rejects_invalid_row_types_and_bounds(self):
        invalid_values = {
            'kind': ('all', None, 1, ['tumbling']),
            'window_start': ('', None, 1, 'x' * 121),
            'window_end': ('', None, 1, 'x' * 121),
            'event_type': ('', None, 1, 'x' * 81),
            'count': (-1, True, 1.5, '1', None),
        }
        for key, values in invalid_values.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(Failure):
                    ResponseValidator().validate_windows({
                        **WINDOWS, 'windows': [{**ROW, key: value}]})
        boundary = {**ROW, 'count': 0, 'window_start': 'x' * 120,
                    'window_end': 'y' * 120, 'event_type': 'z' * 80}
        self.assertEqual(len(ResponseValidator().validate_windows({
            **WINDOWS, 'windows': [boundary] * 100})['windows']), 100)


class WindowsTransportTests(unittest.TestCase):
    def dispatch(self, response):
        session = FakeSession(response)
        auth_calls = []
        socket_calls = []
        worker = NetworkWorker(ORIGIN, None, None, None, ResponseValidator())
        worker._authenticated = True
        api = ApiClient(session, ORIGIN, ResponseValidator(), worker.results.put)

        class Auth:
            def clear(self):
                auth_calls.append('clear')

        class Socket:
            async def close(self):
                socket_calls.append('close')

        asyncio.run(worker._dispatch(Request('windows'), Auth(), api, Socket()))
        results = []
        while not worker.results.empty():
            results.append(worker.get_result_nowait())
        return session, worker, results, auth_calls, socket_calls

    def test_one_get_uses_injected_session_and_emits_safe_inspector_result(self):
        payload = deepcopy(WINDOWS)
        payload['cookies'] = 'must-not-display'
        payload['windows'][0]['raw_value'] = 'must-not-display'
        session, worker, results, _, _ = self.dispatch(FakeResponse(payload))
        self.assertEqual(session.calls, [(ORIGIN + PATH, {
            'headers': {'Accept': 'application/json'}, 'allow_redirects': False})])
        self.assertIsInstance(worker.requests, Queue)
        self.assertIsInstance(worker.results, Queue)
        self.assertEqual([item.kind for item in results], ['api', 'windows'])
        self.assertEqual((results[0].api_path, results[0].status), (PATH, 200))
        self.assertEqual(results[0].player, WINDOWS)
        self.assertEqual(results[1].player, WINDOWS)
        self.assertNotIn('must-not-display', repr(results))

    def test_html_and_failed_status_bodies_are_never_decoded(self):
        for status, content_type in ((200, 'text/html'), (302, 'text/html'),
                                     (401, 'text/html'), (403, 'application/json'),
                                     (500, 'application/json'), (503, 'text/html')):
            with self.subTest(status=status, content_type=content_type):
                response = FakeResponse(b'<html>must-not-display</html>', status,
                                        content_type)
                _, worker, results, auth, socket = self.dispatch(response)
                self.assertEqual(response.read_count, 0)
                self.assertEqual([r.kind for r in results], ['api', 'windows_error'])
                self.assertEqual((results[0].api_path, results[0].status), (PATH, status))
                self.assertIsNone(results[0].player)
                self.assertNotIn('must-not-display', repr(results))
                if status in (302, 401):
                    self.assertTrue(results[1].needs_login)
                    self.assertIn('로그인이 필요합니다', results[1].message)
                    self.assertFalse(worker._authenticated)
                    self.assertEqual((auth, socket), (['clear'], ['close']))
                else:
                    self.assertFalse(results[1].needs_login)
                    self.assertTrue(worker._authenticated)

    def test_invalid_json_schema_and_oversized_bodies_do_not_leak(self):
        for payload in (b'not JSON must-not-display', [],
                        {**WINDOWS, 'windows': [{'count': 'must-not-display'}]},
                        b'x' * 65537):
            with self.subTest(payload_type=type(payload).__name__):
                _, _, results, _, _ = self.dispatch(FakeResponse(payload))
                self.assertEqual(results[-1].kind, 'windows_error')
                self.assertIsNone(results[0].player)
                self.assertNotIn('must-not-display', repr(results))

    def test_timeout_yields_retryable_windows_error_and_clears_pending(self):
        _, worker, results, _, _ = self.dispatch(FakeResponse(
            error=TimeoutError('must-not-display')))
        self.assertEqual(results[0].api_path, PATH)
        self.assertIsNone(results[0].status)
        self.assertEqual(results[-1].kind, 'windows_error')
        self.assertIn('시간 초과', results[-1].message)
        self.assertFalse(results[-1].needs_login)
        self.assertTrue(worker._authenticated)
        panel = AnalyticsPanelState(windows_pending=True)
        panel.apply(results[-1])
        self.assertFalse(panel.windows_pending)
        self.assertTrue(panel.begin_windows(True, False))
        self.assertNotIn('must-not-display', repr(results))


class WindowsPanelTests(unittest.TestCase):
    def setUp(self):
        self.state = State(authenticated=True, player=PLAYER.copy(), ws_connected=True)
        self.panel = AnalyticsPanelState()
        self.history = HistoryPanelState(visible=True)
        self.worker = RecordingWorker()
        self.controller = ClientController(
            self.state, self.panel, self.history, self.worker)

    def test_refresh_is_explicit_gated_and_does_not_change_player(self):
        self.controller.select_analytics_view('windows')
        self.assertEqual(self.worker.requests, [])
        self.assertTrue(self.controller.request_windows())
        self.assertFalse(self.controller.request_windows())
        self.assertFalse(self.controller.request_ingest())
        self.assertFalse(self.controller.submit('logout'))
        self.assertFalse(self.history.visible)
        self.assertEqual([r.kind for r in self.worker.requests], ['windows'])
        self.controller.apply_result(Result('api', api_path=PATH, status=200,
                                            player=WINDOWS))
        self.controller.apply_result(Result('windows', player=WINDOWS))
        self.assertEqual(self.state.player, PLAYER)
        self.assertEqual(self.state.online_count, 1)
        self.assertTrue(self.state.ws_connected)
        self.assertEqual((self.state.api_path, self.state.api_status), (PATH, 200))
        self.assertEqual(self.panel.windows_generated_at, WINDOWS['generated_at'])
        self.assertFalse(self.panel.windows_pending)
        self.assertTrue(self.controller.request_windows())
        self.assertEqual([r.kind for r in self.worker.requests], ['windows', 'windows'])

    def test_filters_pages_and_tabs_are_local(self):
        rows = [{**ROW, 'kind': kind, 'count': count}
                for count, kind in enumerate(['tumbling'] * 7 + ['sliding'] * 5)]
        self.controller.apply_result(Result('windows', player={**WINDOWS, 'windows': rows}))
        self.assertEqual(self.panel.window_page_count, 3)
        seen = list(self.panel.window_page_rows)
        self.controller.change_window_page(1)
        seen += list(self.panel.window_page_rows)
        self.controller.change_window_page(1)
        seen += list(self.panel.window_page_rows)
        self.assertEqual(seen, rows)
        self.controller.change_window_page(10)
        self.assertEqual(self.panel.window_page, 2)
        self.controller.select_window_kind('tumbling')
        self.assertEqual(self.panel.window_page, 0)
        self.assertEqual(self.panel.visible_windows, tuple(rows[:7]))
        self.assertEqual(self.panel.window_page_count, 2)
        self.controller.select_window_kind('sliding')
        self.assertEqual(self.panel.visible_windows, tuple(rows[7:]))
        self.assertEqual(self.panel.window_page_count, 1)
        self.controller.select_window_kind('all')
        self.controller.change_window_page(-5)
        self.assertEqual(self.panel.window_page, 0)
        self.assertEqual(self.panel.visible_windows, tuple(rows))
        for view in ('windows', 'summary', 'windows'):
            self.controller.select_analytics_view(view)
        self.assertEqual(self.worker.requests, [])
        self.assertEqual(self.state.player, PLAYER)

    def test_unavailable_empty_and_failed_refresh_have_distinct_states(self):
        validator = ResponseValidator()
        self.controller.apply_result(Result('windows', player=WINDOWS))
        self.controller.apply_result(Result('windows', player=validator.validate_windows(
            {'available': False})))
        self.assertEqual(self.panel.windows_message, '아직 창 요약 없음')
        self.assertFalse(self.panel.windows_available)
        self.assertEqual((self.panel.windows, self.panel.windows_generated_at), ((), ''))
        self.controller.apply_result(Result('windows', player={**WINDOWS, 'windows': []}))
        self.assertEqual(self.panel.windows_message, '확정된 게시 대상 창 없음')
        self.assertTrue(self.panel.windows_available)
        self.assertEqual(self.panel.windows_generated_at, WINDOWS['generated_at'])
        self.controller.request_windows()
        self.controller.apply_result(Result('windows_error', '서버 요청 실패 (HTTP 503).'))
        self.assertFalse(self.panel.windows_pending)
        self.assertIn('503', self.panel.windows_error)
        self.assertEqual(self.state.player, PLAYER)

    def test_login_expiry_clears_windows_and_account(self):
        self.controller.apply_result(Result('windows', player=WINDOWS))
        self.controller.apply_result(Result(
            'windows_error', '로그인이 필요합니다.', needs_login=True))
        self.assertFalse(self.state.authenticated)
        self.assertIsNone(self.state.player)
        self.assertEqual(self.panel.windows, ())
        self.assertEqual(self.panel.windows_generated_at, '')
        self.assertIsNone(self.panel.windows_available)
        self.assertFalse(self.panel.visible)
        self.assertFalse(self.controller.request_windows())


class WindowsWorkerTests(unittest.TestCase):
    def test_slow_windows_uses_login_session_keeps_commands_live_and_cancels_before_close(self):
        events = []
        sessions = []
        get_calls = []
        started = threading.Event()
        session_options = []

        class SlowResponse(FakeResponse):
            async def iter_chunked(self, _size):
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    events.append('windows_cancelled')
                yield b''

        class Session:
            def __init__(self, **kwargs):
                session_options.append(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                events.append('session_closed')

            def get(self, url, **kwargs):
                get_calls.append((url, kwargs, threading.get_ident()))
                return SlowResponse() if url == ORIGIN + PATH else FakeResponse(PLAYER)

        class Auth:
            def __init__(self, session, _origin):
                sessions.append(session)

            async def login(self, username, password):
                events.append('login')

            def clear(self):
                events.append('auth_cleared')

        class Socket:
            def __init__(self, session, *_args):
                sessions.append(session)

            async def connect(self, _player_id):
                return PLAYER.copy(), {'type': 'state', **PLAYER}

            def start_listener(self):
                pass

            async def command(self, action, direction):
                return {**PLAYER, 'x': PLAYER['x'] + 1, 'version': PLAYER['version'] + 1}

            async def shutdown(self):
                events.append('socket_shutdown')

        def api_factory(session, *args):
            sessions.append(session)
            return ApiClient(session, *args)

        worker = NetworkWorker(ORIGIN, Auth, api_factory, Socket, ResponseValidator())

        def result_until(kind):
            while True:
                result = worker.results.get(timeout=2)
                if result.kind == 'fatal':
                    self.fail(result.message)
                if result.kind == kind:
                    return result

        with patch('network.aiohttp.ClientSession', Session):
            worker.start()
            try:
                login = Request('login', 'student', 'test-only')
                worker.submit(login)
                self.assertEqual(result_until('player').player, PLAYER)
                self.assertEqual((login.username, login.password), ('', ''))
                worker.submit(Request('windows'))
                self.assertTrue(started.wait(2))
                worker.submit(Request('windows'))
                self.assertIn('이미 진행 중', result_until('windows_error').message)
                worker.submit(Request('command', action='move', direction='right'))
                self.assertEqual(result_until('command').player['x'], PLAYER['x'] + 1)
            finally:
                worker.stop()
                worker.thread.join(2)
            self.assertFalse(worker.is_alive())

        self.assertEqual(len(session_options), 1)
        self.assertEqual(len(sessions), 3)
        self.assertTrue(all(session is sessions[0] for session in sessions))
        timeout = session_options[0]['timeout']
        self.assertEqual((timeout.total, timeout.connect, timeout.sock_read), (4, 2, 2))
        self.assertFalse(session_options[0]['trust_env'])
        windows_calls = [call for call in get_calls if call[0] == ORIGIN + PATH]
        self.assertEqual(len(windows_calls), 1)
        self.assertFalse(windows_calls[0][1]['allow_redirects'])
        self.assertNotEqual(windows_calls[0][2], threading.get_ident())
        self.assertEqual(events[-4:], [
            'windows_cancelled', 'socket_shutdown', 'auth_cleared', 'session_closed'])


if __name__ == '__main__':
    unittest.main()
