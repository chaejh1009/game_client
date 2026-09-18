"""Local HTTP contract tests; no Django or third-party test framework required."""
import asyncio
import os
from pathlib import Path
from queue import Empty
import sys
import threading
import time
import unittest
from uuid import UUID

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))
from aiohttp import web
from network import NetworkWorker
from network_api import ApiClient
from network_auth import DjangoAuth
from network_errors import Failure
from network_validation import ResponseValidator
from network_ws import GameSocketClient
from panels import AnalyticsPanelState
from state import Request, Result, State

PLAYER = dict(player_id=7, room_id=2, x=3, y=4, coins=5, version=6)
OTHER = dict(player_id=8, room_id=2, x=9, y=10, coins=1, version=2)


def make_worker(origin):
    return NetworkWorker(
        origin,
        DjangoAuth,
        ApiClient,
        GameSocketClient,
        ResponseValidator(),
    )

class IngestValidationTests(unittest.TestCase):
    def test_unavailable_reason_accepts_omitted_or_bounded_string(self):
        validator = ResponseValidator()
        for fields, expected in (
                ({}, ''),
                ({'reason': ''}, ''),
                ({'reason': 'summary_not_created'}, 'summary_not_created'),
                ({'reason': '가' * 160}, '가' * 160)):
            with self.subTest(fields=fields):
                self.assertEqual(
                    validator.validate_ingest({
                        'available': False, 'record_count': 0, **fields,
                    }),
                    {'available': False, 'reason': expected},
                )

    def test_unavailable_reason_rejects_non_strings_and_overlong_string(self):
        validator = ResponseValidator()
        for reason in (None, 0, False, [], {}, 1, True, ['not_ready'],
                       {'reason': 'not_ready'}, '가' * 161):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(Failure, 'ingest 응답의 reason'):
                    validator.validate_ingest({'available': False, 'reason': reason})


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ready = threading.Event()
        cls.loop = asyncio.new_event_loop()
        cls.calls = []
        cls.commands = []
        cls.mode = 'ok'
        cls.serial = 0
        async def handler(req):
            cls.calls.append((req.method, req.path))
            if req.path == '/ws/play/':
                assert req.cookies.get('sessionid')
                ws = web.WebSocketResponse()
                await ws.prepare(req)
                await ws.send_json({**PLAYER, 'type': 'state'})
                await ws.send_json({'type': 'snapshot', 'players': [
                    {**PLAYER, 'username': 'must-not-display'},
                    {**OTHER, 'csrfToken': 'must-not-display'},
                ]})
                async for message in ws:
                    command = message.json()
                    cls.commands.append(command)
                    state = {**PLAYER, 'type': 'state',
                             'version': PLAYER['version'] + 1,
                             'command_id': command['command_id']}
                    if command['type'] == 'move':
                        direction = command['direction']
                        dx, dy = {'up': (0, -1), 'down': (0, 1),
                                  'left': (-1, 0), 'right': (1, 0)}[direction]
                        state.update(x=PLAYER['x'] + dx, y=PLAYER['y'] + dy)
                    elif command['type'] == 'gather':
                        assert 'direction' not in command
                        state['coins'] = PLAYER['coins'] + 1
                    elif command['type'] == 'train':
                        assert 'direction' not in command
                        state['coins'] = PLAYER['coins'] + 1
                    # Room broadcasts can arrive between a command and its acknowledgement.
                    await ws.send_json({**OTHER, 'type': 'state',
                                        'x': OTHER['x'] + 1,
                                        'command_id': 'another-player-command'})
                    await ws.send_json(state)
                return ws
            if req.path == '/accounts/login/' and req.method == 'GET':
                resp = web.Response(text='<form method="post"></form>', content_type='text/html')
                resp.set_cookie('csrftoken', 'initial')
                return resp
            if req.path == '/accounts/login/' and req.method == 'POST':
                assert req.headers['Origin'] == cls.origin
                assert req.headers['X-CSRFToken'] == req.cookies['csrftoken'] == 'initial'
                assert dict(await req.post()) == {'username': 'student', 'password': 'test-only'}
                if cls.mode == 'bad_credentials':
                    return web.Response(text='<form><p>invalid</p></form>', content_type='text/html')
                cls.serial += 1
                resp = web.Response(status=302, headers={'Location': '/play/'})
                resp.set_cookie('sessionid', str(cls.serial))
                resp.set_cookie('csrftoken', 'rotated')
                return resp
            if req.path == '/accounts/logout/':
                assert req.headers['Origin'] == cls.origin
                assert req.headers['X-CSRFToken'] == req.cookies['csrftoken'] == 'rotated'
                return web.Response(status=302, headers={'Location': '/accounts/login/'})
            if req.path == '/api/player/':
                assert req.cookies.get('sessionid')
                assert req.cookies['csrftoken'] == 'rotated'
                if cls.mode == 'slow':
                    await asyncio.sleep(10)
                if cls.mode in ('302', '401', '403'):
                    return web.Response(status=int(cls.mode), headers={'Location': '/trap'}, text='<html>private</html>')
                if cls.mode == 'html':
                    return web.Response(text='<html>private</html>', content_type='text/html')
                if cls.mode == 'badjson':
                    return web.Response(text='{', content_type='application/json')
                if cls.mode == 'schema':
                    return web.json_response({'password': 'do-not-display'})
                return web.json_response({**PLAYER, 'password': 'do-not-display', 'csrfToken': 'hidden'})
            if req.path == '/api/history/':
                assert req.cookies.get('sessionid')
                assert req.cookies['csrftoken'] == 'rotated'
                if cls.mode == 'history_html':
                    return web.Response(text='<html>private history</html>',
                                        content_type='text/html')
                if cls.mode == 'history_schema':
                    return web.json_response({
                        'scope': 'current-player', 'limit': 20,
                        'events': [{'password': 'must-not-display'}],
                    })
                return web.json_response({
                    'scope': 'current-player',
                    'limit': 20,
                    'events': [{
                        'schema_version': 1,
                        'event_id': '8a0b52f1-12dc-4434-a1a5-b86be381145a',
                        'event_type': 'player.moved',
                        'player_id': PLAYER['player_id'],
                        'room_id': PLAYER['room_id'],
                        'event_time': '2026-09-16T01:02:03+00:00',
                        'payload': {
                            'x': PLAYER['x'], 'y': PLAYER['y'],
                            'coins': PLAYER['coins'], 'version': PLAYER['version'],
                            'command_id': 'must-not-display',
                            'transition': {
                                'step': 3, 'reward': 1,
                                'policy_version': 'must-not-display',
                            },
                        },
                        'csrfToken': 'must-not-display',
                    }],
                    'username': 'must-not-display',
                })
            if req.path == '/api/delivery/':
                assert req.cookies.get('sessionid')
                assert req.cookies['csrftoken'] == 'rotated'
                if cls.mode == 'slow_delivery':
                    await asyncio.sleep(0.25)
                if cls.mode == 'delivery_html':
                    return web.Response(text='<html>private</html>', content_type='text/html')
                if cls.mode in ('delivery_302', 'delivery_401'):
                    status = int(cls.mode.removeprefix('delivery_'))
                    return web.Response(status=status, headers={'Location': '/trap'})
                return web.json_response({
                    'source': 'mysql-outbox',
                    'event_count': 12,
                    'pending_publish_count': 3,
                    'username': 'must-not-display',
                    'csrfToken': 'must-not-display',
                })
            if req.path == '/api/analytics/actions/':
                assert req.cookies.get('sessionid')
                assert req.cookies['csrftoken'] == 'rotated'
                if cls.mode == 'slow_analytics':
                    await asyncio.sleep(0.25)
                if cls.mode == 'analytics_false':
                    return web.json_response({
                        'available': False,
                        'reason': 'summary_not_created',
                        'event_count': 0,
                        'csrfToken': 'must-not-display',
                    })
                if cls.mode == 'analytics_html':
                    return web.Response(text='<html>private analytics</html>',
                                        content_type='text/html')
                if cls.mode in ('analytics_302', 'analytics_401'):
                    status = int(cls.mode.removeprefix('analytics_'))
                    return web.Response(status=status, headers={'Location': '/trap'})
                if cls.mode == 'analytics_schema':
                    return web.json_response({
                        'available': True,
                        'source_topic': 'game.actions',
                        'source_kind': 'kafka',
                        'raw_record_count': 20,
                        'summary': {'password': 'must-not-display'},
                    })
                return web.json_response({
                    'available': True,
                    'source_topic': 'game.actions.v1',
                    'source_kind': 'kafka-summary',
                    'raw_record_count': 24,
                    'summary': {
                        'generated_at': '2026-09-15T03:04:05+00:00',
                        'event_count': 15,
                        'by_action': [
                            {'action_label': '채굴', 'count': 4,
                             'secret': 'hidden'},
                            {'action_label': '이동', 'count': 11},
                        ],
                        'by_room': [{'room_id': 'room-01', 'count': 15}],
                        'source': 'must-not-display',
                    },
                    'csrfToken': 'must-not-display',
                })
            if req.path == '/api/analytics/ingest/':
                assert req.cookies.get('sessionid')
                assert req.cookies['csrftoken'] == 'rotated'
                if cls.mode == 'slow_ingest':
                    await asyncio.sleep(0.25)
                if cls.mode == 'ingest_false':
                    return web.json_response({
                        'available': False,
                        'reason': 'summary_not_created',
                        'record_count': 0,
                        'event_count': 0,
                        'duplicate_record_count': 0,
                        'password': 'must-not-display',
                    })
                if cls.mode == 'ingest_html':
                    return web.Response(text='<html>private ingest</html>',
                                        content_type='text/html')
                if cls.mode == 'ingest_503':
                    return web.Response(status=503, text='not ready')
                if cls.mode in ('ingest_302', 'ingest_401'):
                    status = int(cls.mode.removeprefix('ingest_'))
                    return web.Response(status=status, headers={'Location': '/trap'})
                if cls.mode == 'ingest_schema':
                    return web.json_response({
                        'available': True,
                        'source': 'kafka',
                        'generated_at': '2026-09-15T03:04:05+00:00',
                        'record_count': 20,
                        'password': 'must-not-display',
                    })
                return web.json_response({
                    'available': True,
                    'source': 'kafka-actions-v1',
                    'generated_at': '2026-09-15T03:04:05+00:00',
                    'record_count': 24,
                    'event_count': 15,
                    'duplicate_record_count': 3,
                    'by_action': [
                        {'event_type': 'player.moved', 'count': 11,
                         'raw_value': 'must-not-display'},
                        {'event_type': 'player.gathered', 'count': 4},
                    ],
                    'evidence': 'must-not-display',
                    'csrfToken': 'must-not-display',
                })
            raise AssertionError('Unexpected route / redirect followed')
        async def start():
            app = web.Application()
            app.router.add_route('*', '/{tail:.*}', handler)
            cls.runner = web.AppRunner(app, access_log=None, shutdown_timeout=0.1)
            await cls.runner.setup()
            site = web.TCPSite(cls.runner, '127.0.0.1', 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            cls.origin = f'http://127.0.0.1:{port}'
            cls.ready.set()
        def run():
            asyncio.set_event_loop(cls.loop)
            cls.loop.run_until_complete(start())
            cls.loop.run_forever()
            cls.loop.run_until_complete(cls.runner.cleanup())
            pending = asyncio.all_tasks(cls.loop)
            for task in pending:
                task.cancel()
            cls.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            cls.loop.close()
        cls.server = threading.Thread(target=run)
        cls.server.start()
        if not cls.ready.wait(3):
            raise RuntimeError('mock server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.loop.call_soon_threadsafe(cls.loop.stop)
        cls.server.join(3)

    def setUp(self):
        type(self).mode = 'ok'
        self.calls.clear()
        self.commands.clear()
        self.worker = make_worker(self.origin)
        self.worker.start()

    def tearDown(self):
        self.worker.stop()
        self.worker.thread.join(2)
        self.assertFalse(self.worker.thread.is_alive())

    def result(self):
        results = []
        while True:
            result = self.worker.results.get(timeout=6)
            results.append(result)
            if result.kind not in ('api', 'snapshot', 'state'):
                return result, results

    def result_kind(self, kind):
        seen = []
        while True:
            result = self.worker.results.get(timeout=6)
            seen.append(result)
            if result.kind == kind:
                return result, seen

    def results_until(self, kind):
        return self.result_kind(kind)

    def login(self):
        request = Request('login', 'student', 'test-only')
        self.worker.submit(request)
        result, results = self.result()
        self.assertEqual(request.password, '')
        self.assertNotIn('test-only', repr(request))
        return result, results

    def test_login_rotation_player_logout(self):
        result, results = self.login()
        self.assertEqual(result.kind, 'player')
        self.assertEqual(result.player, PLAYER)
        self.assertEqual(results[0].player, PLAYER)
        self.assertNotIn('hidden', repr(results))
        self.assertNotIn('do-not-display', repr(results))
        self.assertEqual(self.calls, [('GET', '/accounts/login/'), ('POST', '/accounts/login/'),
                                     ('GET', '/api/player/'), ('GET', '/ws/play/')])
        self.worker.submit(Request('logout'))
        self.assertEqual(self.result()[0].kind, 'logged_out')
        self.assertEqual(self.calls[-1], ('POST', '/accounts/logout/'))

    def test_keyboard_and_button_share_command_gate(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.assertTrue(state.begin_command('move', 10.0, 'up'))
        self.assertFalse(state.begin_command('move', 10.1, 'right'))  # One is pending.

        self.assertEqual(self.login()[0].kind, 'player')
        self.worker.submit(Request('command', direction='up'))
        result, updates = self.result_kind('command')
        self.assertEqual(result.kind, 'command')
        self.assertEqual(result.direction, 'up')
        self.assertEqual(result.player['y'], PLAYER['y'] - 1)
        self.assertEqual(self.commands[0]['type'], 'move')
        self.assertTrue(any(item.kind == 'snapshot' for item in updates))
        other_update = next(item for item in updates
                            if item.kind == 'state' and item.player['player_id'] == OTHER['player_id'])
        self.assertEqual(other_update.player['x'], OTHER['x'] + 1)
        self.assertNotIn('must-not-display', repr(updates))

        for update in updates:
            state.apply(update)
            if update is other_update:
                self.assertTrue(state.command_pending)
        self.assertEqual(state.command_status, 'success')
        self.assertEqual(state.player['y'], PLAYER['y'] - 1)
        self.assertEqual(state.players[OTHER['player_id']]['x'], OTHER['x'] + 1)
        self.assertFalse(state.begin_command('move', 10.1, 'right'))  # Shared rate limit.
        self.assertTrue(state.begin_command('move', 10.21, 'right'))

    def test_z_gathers_coin_through_shared_command_path(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.assertTrue(state.begin_command('gather', 20.0))
        self.assertEqual(state.selected_action, 'gather')

        self.assertEqual(self.login()[0].kind, 'player')
        self.worker.submit(Request('command', action='gather'))
        result, _ = self.result_kind('command')
        self.assertEqual(result.kind, 'command')
        self.assertEqual(result.action, 'gather')
        self.assertEqual(result.player['coins'], PLAYER['coins'] + 1)
        self.assertEqual(self.commands[0]['type'], 'gather')
        self.assertNotIn('direction', self.commands[0])

    def test_train_sends_minimal_uuid_command_then_fetches_history(self):
        self.assertEqual(self.login()[0].kind, 'player')
        self.worker.submit(Request('command', action='train'))
        command, results = self.results_until('command')
        self.assertEqual(command.action, 'train')
        self.assertEqual(command.player['coins'], PLAYER['coins'] + 1)
        payload = self.commands[0]
        self.assertEqual(set(payload), {'type', 'command_id'})
        self.assertEqual(payload['type'], 'train')
        self.assertEqual(str(UUID(payload['command_id'])), payload['command_id'])
        self.assertFalse(any(item.kind == 'state'
                             and item.player['player_id'] == PLAYER['player_id']
                             for item in results))
        history, history_results = self.results_until('history')
        self.assertEqual(history.kind, 'history')
        self.assertIn(('GET', '/api/history/'), self.calls)
        api_result = next(item for item in history_results
                          if item.kind == 'api' and item.api_path == '/api/history/')
        transition = api_result.player['events'][0]['payload']['transition']
        self.assertEqual(transition, {'step': 3, 'reward': 1})

    def test_delivery_status_allowlist_cooldown_and_independent_move(self):
        self.assertEqual(self.login()[0].kind, 'player')
        state = State(authenticated=True, player=PLAYER.copy())
        self.assertTrue(state.begin_delivery(10.0))
        self.assertFalse(state.begin_delivery(11.0))

        type(self).mode = 'slow_delivery'
        self.worker.submit(Request('delivery'))
        self.worker.submit(Request('command', direction='up'))
        command, before_command = self.results_until('command')
        self.assertEqual(command.player['y'], PLAYER['y'] - 1)
        self.assertFalse(any(result.kind == 'command_error' for result in before_command))

        delivery, delivery_results = self.results_until('delivery')
        all_results = before_command + delivery_results
        for result in all_results:
            state.apply(result)
        self.assertEqual(delivery.delivery, {
            'source': 'mysql-outbox',
            'event_count': 12,
            'pending_publish_count': 3,
        })
        self.assertEqual(state.delivery_source, 'mysql-outbox')
        self.assertEqual(state.event_count, 12)
        self.assertEqual(state.pending_publish_count, 3)
        self.assertEqual(state.api_path, '/api/delivery/')
        self.assertEqual(state.api_json, delivery.delivery)
        self.assertNotIn('must-not-display', repr(all_results))
        self.assertFalse(state.delivery_pending)
        self.assertFalse(state.begin_delivery(14.99))
        self.assertTrue(state.begin_delivery(15.0))

    def test_delivery_rejects_html_without_reading_it_as_json(self):
        self.assertEqual(self.login()[0].kind, 'player')
        type(self).mode = 'delivery_html'
        self.worker.submit(Request('delivery'))
        result, results = self.results_until('delivery_error')
        self.assertIn('JSON 응답이 아닙니다', result.message)
        self.assertNotIn('<html>', repr(results))

    def test_history_path_allowlist_and_api_panel_result(self):
        self.assertEqual(self.login()[0].kind, 'player')
        self.worker.submit(Request('history'))
        result, results = self.results_until('history')
        api_result = next(item for item in results
                          if item.kind == 'api' and item.api_path == '/api/history/')
        state = State(authenticated=True, busy=True, player=PLAYER.copy())
        for item in results:
            state.apply(item)
        self.assertEqual(result.kind, 'history')
        self.assertEqual(state.api_path, '/api/history/')
        self.assertEqual(state.api_status, 200)
        self.assertEqual(api_result.player['scope'], 'current-player')
        self.assertEqual(api_result.player['limit'], 20)
        self.assertEqual(api_result.player['events'][0]['payload'], {
            'x': PLAYER['x'], 'y': PLAYER['y'],
            'coins': PLAYER['coins'], 'version': PLAYER['version'],
            'transition': {'step': 3, 'reward': 1},
        })
        self.assertFalse(state.busy)
        self.assertNotIn('must-not-display', repr(results))

    def test_history_rejects_html_and_bad_schema(self):
        for mode in ('history_html', 'history_schema'):
            with self.subTest(mode=mode):
                type(self).mode = 'ok'
                self.assertEqual(self.login()[0].kind, 'player')
                type(self).mode = mode
                self.worker.submit(Request('history'))
                result, results = self.results_until('history_error')
                if mode == 'history_html':
                    self.assertIn('JSON 응답이 아닙니다', result.message)
                    self.assertNotIn('<html>', repr(results))
                else:
                    self.assertIn('history event', result.message)
                    self.assertNotIn('must-not-display', repr(results))
                self.worker.submit(Request('logout'))
                self.assertEqual(self.result()[0].kind, 'logged_out')

    def test_delivery_redirect_and_unauthorized_require_login(self):
        for mode in ('delivery_302', 'delivery_401'):
            with self.subTest(mode=mode):
                type(self).mode = 'ok'
                self.assertEqual(self.login()[0].kind, 'player')
                type(self).mode = mode
                self.worker.submit(Request('delivery'))
                result, _ = self.results_until('delivery_error')
                self.assertTrue(result.needs_login)
                self.assertIn('로그인이 필요합니다', result.message)
                self.assertNotIn(('GET', '/trap'), self.calls)

    def test_analytics_true_false_allowlist_and_player_is_unchanged(self):
        self.assertEqual(self.login()[0].kind, 'player')
        self.assertNotIn(('GET', '/api/analytics/actions/'), self.calls)
        player_state = State(authenticated=True, player=PLAYER.copy())
        original_player = player_state.player.copy()
        panel = AnalyticsPanelState()
        self.assertTrue(panel.begin(True, False))

        self.worker.submit(Request('analytics'))
        result, results = self.results_until('analytics')
        api_result = next(item for item in results
                          if item.kind == 'api'
                          and item.api_path == '/api/analytics/actions/')
        player_state.apply(api_result)
        self.assertTrue(panel.apply(result))
        self.assertTrue(panel.available)
        self.assertEqual(panel.source_topic, 'game.actions.v1')
        self.assertEqual(panel.source_kind, 'kafka-summary')
        self.assertEqual(panel.raw_record_count, 24)
        self.assertEqual(panel.event_count, 15)
        self.assertEqual(panel.by_action[0], {
            'action_label': '채굴', 'count': 4,
        })
        self.assertEqual(panel.by_room[0], {'room_id': 'room-01', 'count': 15})
        self.assertEqual(panel.generated_at, '2026-09-15T03:04:05+00:00')
        self.assertEqual(player_state.api_path, '/api/analytics/actions/')
        self.assertEqual(player_state.api_status, 200)
        self.assertEqual(player_state.player, original_player)
        self.assertNotIn('must-not-display', repr(results))
        self.assertNotIn('hidden', repr(results))

        panel.hide()
        self.assertTrue(panel.begin(True, False))
        type(self).mode = 'analytics_false'
        self.worker.submit(Request('analytics'))
        result, results = self.results_until('analytics')
        self.assertTrue(panel.apply(result))
        self.assertFalse(panel.available)
        self.assertIsNone(panel.event_count)
        self.assertIsNone(panel.raw_record_count)
        self.assertEqual(panel.message, '행동 집계가 아직 없습니다')
        api_result = next(item for item in results
                          if item.kind == 'api'
                          and item.api_path == '/api/analytics/actions/')
        self.assertEqual(api_result.player, {'available': False})
        self.assertNotIn('must-not-display', repr(results))

    def test_analytics_rejects_html_and_redirect(self):
        for mode in ('analytics_html', 'analytics_schema',
                     'analytics_302', 'analytics_401'):
            with self.subTest(mode=mode):
                type(self).mode = 'ok'
                self.assertEqual(self.login()[0].kind, 'player')
                type(self).mode = mode
                self.worker.submit(Request('analytics'))
                result, results = self.results_until('analytics_error')
                if mode in ('analytics_html', 'analytics_schema'):
                    if mode == 'analytics_html':
                        self.assertIn('JSON 응답이 아닙니다', result.message)
                        self.assertNotIn('<html>', repr(results))
                    else:
                        self.assertIn('analytics summary', result.message)
                        self.assertNotIn('must-not-display', repr(results))
                    self.worker.submit(Request('logout'))
                    self.assertEqual(self.result()[0].kind, 'logged_out')
                else:
                    self.assertTrue(result.needs_login)
                    self.assertIn('로그인이 필요합니다', result.message)
                    self.assertNotIn(('GET', '/trap'), self.calls)

    def test_analytics_read_does_not_block_movement(self):
        self.assertEqual(self.login()[0].kind, 'player')
        type(self).mode = 'slow_analytics'
        self.worker.submit(Request('analytics'))
        self.worker.submit(Request('command', direction='right'))
        command, results = self.results_until('command')
        self.assertEqual(command.player['x'], PLAYER['x'] + 1)
        self.assertFalse(any(result.kind == 'command_error' for result in results))
        analytics, _ = self.results_until('analytics')
        self.assertEqual(analytics.player['summary']['event_count'], 15)

    def test_ingest_stats_allowlist_statuses_and_no_synthetic_zero(self):
        self.assertEqual(self.login()[0].kind, 'player')
        self.assertNotIn(('GET', '/api/analytics/ingest/'), self.calls)
        panel = AnalyticsPanelState()
        self.assertTrue(panel.begin_ingest(True, False))
        self.worker.submit(Request('ingest'))
        result, results = self.results_until('ingest')
        api_result = next(item for item in results
                          if item.kind == 'api'
                          and item.api_path == '/api/analytics/ingest/')
        self.assertEqual(result.player, {
            'available': True,
            'source': 'kafka-actions-v1',
            'generated_at': '2026-09-15T03:04:05+00:00',
            'record_count': 24,
            'event_count': 15,
            'duplicate_record_count': 3,
            'by_action': [
                {'event_type': 'player.moved', 'count': 11},
                {'event_type': 'player.gathered', 'count': 4},
            ],
        })
        self.assertEqual(api_result.player, result.player)
        self.assertTrue(panel.apply(result))
        self.assertEqual(panel.ingest_source, 'kafka-actions-v1')
        self.assertEqual(panel.ingest_record_count, 24)
        self.assertEqual(panel.ingest_event_count, 15)
        self.assertEqual(panel.ingest_duplicate_record_count, 3)
        self.assertEqual(panel.ingest_by_action[0], {
            'event_type': 'player.moved', 'count': 11,
        })
        self.assertNotIn('must-not-display', repr(results))

        panel.hide()
        self.assertTrue(panel.begin_ingest(True, False))
        type(self).mode = 'ingest_false'
        self.worker.submit(Request('ingest'))
        result, _ = self.results_until('ingest')
        self.assertTrue(panel.apply(result))
        self.assertFalse(panel.ingest_available)
        self.assertIsNone(panel.ingest_record_count)
        self.assertIsNone(panel.ingest_event_count)
        self.assertIsNone(panel.ingest_duplicate_record_count)
        self.assertIn('생성되지 않았습니다', panel.ingest_message)

    def test_ingest_stats_reject_html_schema_503_and_auth_redirect(self):
        for mode in ('ingest_html', 'ingest_schema', 'ingest_503',
                     'ingest_302', 'ingest_401'):
            with self.subTest(mode=mode):
                type(self).mode = 'ok'
                self.assertEqual(self.login()[0].kind, 'player')
                type(self).mode = mode
                self.worker.submit(Request('ingest'))
                result, results = self.results_until('ingest_error')
                if mode == 'ingest_html':
                    self.assertIn('JSON 응답이 아닙니다', result.message)
                    self.assertNotIn('<html>', repr(results))
                elif mode == 'ingest_schema':
                    self.assertIn('ingest 응답의 event_count', result.message)
                    self.assertNotIn('must-not-display', repr(results))
                elif mode == 'ingest_503':
                    self.assertEqual(result.message, '마지막 수집 통계를 읽을 수 없음')
                else:
                    self.assertTrue(result.needs_login)
                    self.assertIn('로그인이 필요합니다', result.message)
                    self.assertNotIn(('GET', '/trap'), self.calls)
                if mode in ('ingest_html', 'ingest_schema'):
                    self.worker.submit(Request('logout'))
                    self.assertEqual(self.result()[0].kind, 'logged_out')

    def test_ingest_read_does_not_block_movement(self):
        self.assertEqual(self.login()[0].kind, 'player')
        type(self).mode = 'slow_ingest'
        self.worker.submit(Request('ingest'))
        self.worker.submit(Request('command', direction='right'))
        command, results = self.results_until('command')
        self.assertEqual(command.player['x'], PLAYER['x'] + 1)
        self.assertFalse(any(result.kind == 'command_error' for result in results))
        ingest, _ = self.results_until('ingest')
        self.assertEqual(ingest.player['event_count'], 15)

    def test_login_focus_blocks_movement(self):
        state = State(focus='username')
        self.assertFalse(state.begin_command('move', 1.0, 'left'))
        self.assertFalse(state.command_pending)
        self.assertIn('로그인 입력 중', state.message)

    def test_player_versions_snapshot_removal_and_disconnect_label(self):
        state = State()
        state.apply(Result('player', player=PLAYER,
                           ws_json={'type': 'state', **PLAYER}))
        self.assertEqual(state.my_player_id, PLAYER['player_id'])

        newer_other = {**OTHER, 'x': 12, 'version': 5, 'coins': 999}
        state.apply(Result('state', player=newer_other))
        state.apply(Result('snapshot', players=(
            {**PLAYER, 'coins': 999, 'version': 5},
            {**OTHER, 'x': 2, 'version': 4},
        )))
        self.assertEqual(state.player['coins'], PLAYER['coins'])
        self.assertEqual(state.players[OTHER['player_id']], newer_other)

        state.apply(Result('state', player={**OTHER, 'x': 1, 'version': 4}))
        self.assertEqual(state.players[OTHER['player_id']]['x'], 12)
        state.apply(Result('state', player={**OTHER, 'x': 13, 'version': 5}))
        self.assertEqual(state.players[OTHER['player_id']]['x'], 13)

        state.apply(Result('snapshot', players=(PLAYER,)))
        self.assertNotIn(OTHER['player_id'], state.players)
        self.assertEqual(state.online_count, 1)
        state.apply(Result('ws_disconnected', '마지막 정보'))
        self.assertFalse(state.ws_connected)
        self.assertEqual(state.online_count, 1)
        self.assertEqual(state.player['coins'], PLAYER['coins'])
        state.apply(Result('player', player={**PLAYER, 'version': 7}))
        self.assertFalse(state.ws_connected)  # HTTP refresh does not reconnect WebSocket.

    def test_status_content_type_and_schema(self):
        for mode in ('302', '401', '403', 'html', 'badjson', 'schema'):
            with self.subTest(mode=mode):
                type(self).mode = mode
                result, results = self.login()
                self.assertEqual(result.kind, 'error')
                self.assertNotIn('/trap', repr(self.calls))
                self.assertNotIn('<html>', repr(results))
                self.assertNotIn('do-not-display', repr(results))
                if mode == '403':
                    self.assertIn('CSRF / Origin', result.message)
                if mode in ('302', '401'):
                    self.assertTrue(result.needs_login)

    def test_separate_cookie_jars(self):
        self.assertEqual(self.login()[0].kind, 'player')
        other = make_worker(self.origin)
        other.start()
        try:
            other.submit(Request('login', 'student', 'test-only'))
            self.assertEqual(other.results.get(timeout=5).kind, 'api')
            self.assertEqual(other.results.get(timeout=5).kind, 'player')
            self.worker.submit(Request('logout'))
            self.assertEqual(self.result()[0].kind, 'logged_out')
            other.submit(Request('player'))
            other_results = []
            while not other_results or other_results[-1].kind != 'player':
                other_results.append(other.results.get(timeout=5))
            self.assertTrue(any(result.kind == 'api' for result in other_results))
            self.assertEqual(other_results[-1].player, PLAYER)
        finally:
            other.stop()
            other.thread.join(2)

    def test_bad_credentials(self):
        type(self).mode = 'bad_credentials'
        result, _ = self.login()
        self.assertEqual(result.kind, 'error')
        self.assertTrue(result.needs_login)
        self.assertIn('로그인에 실패', result.message)

    def test_cancel_inflight_and_timeout(self):
        self.assertEqual(self.login()[0].kind, 'player')
        type(self).mode = 'slow'
        self.worker.submit(Request('player'))
        result, _ = self.result()
        self.assertEqual(result.kind, 'error')
        self.assertIn('시간 초과', result.message)
        self.worker.submit(Request('player'))
        time.sleep(0.1)  # Test harness only, never the UI.
        start = time.monotonic()
        self.worker.stop()
        self.worker.thread.join(1)
        self.assertFalse(self.worker.thread.is_alive())
        self.assertLess(time.monotonic() - start, 1)

if __name__ == '__main__':
    unittest.main()
