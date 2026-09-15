"""Local HTTP contract tests; no Django or third-party test framework required."""
import asyncio
import os
from pathlib import Path
from queue import Empty
import sys
import threading
import time
import unittest

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))
from aiohttp import web
from network import NetworkWorker
from state import Request, State

PLAYER = dict(player_id=7, room_id=2, x=3, y=4, coins=5, version=6)
OTHER = dict(player_id=8, room_id=2, x=9, y=10, coins=1, version=2)

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
                await ws.send_json({'type': 'snapshot', 'players': [PLAYER, OTHER]})
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
        self.worker = NetworkWorker(self.origin)
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

        for update in updates:
            state.apply(update)
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

    def test_login_focus_blocks_movement(self):
        state = State(focus='username')
        self.assertFalse(state.begin_command('move', 1.0, 'left'))
        self.assertFalse(state.command_pending)
        self.assertIn('로그인 입력 중', state.message)

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
        other = NetworkWorker(self.origin)
        other.start()
        try:
            other.submit(Request('login', 'student', 'test-only'))
            self.assertEqual(other.results.get(timeout=5).kind, 'api')
            self.assertEqual(other.results.get(timeout=5).kind, 'player')
        finally:
            other.stop()
            other.thread.join(2)
        self.assertIsNot(self.worker._session.cookie_jar, other._session.cookie_jar)

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
        self.assertTrue(self.worker._session.closed)

if __name__ == '__main__':
    unittest.main()
