"""Offline contract checks for the client history API path."""

import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

import aiohttp

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))

from messages import Request, Result
from network import NetworkWorker
from network_api import ApiClient
from network_auth import DjangoAuth
from network_errors import Failure
from network_validation import ResponseValidator
from network_ws import GameSocketClient
from panels import HistoryPanelState
from state import State


HISTORY = {
    'scope': 'current-player',
    'limit': 20,
    'events': [{
        'schema_version': 1,
        'event_id': '8a0b52f1-12dc-4434-a1a5-b86be381145a',
        'event_type': 'player.moved',
        'player_id': 7,
        'room_id': 'room-01',
        'event_time': '2026-09-16T01:02:03+00:00',
        'payload': {
            'x': 3,
            'y': 4,
            'coins': 5,
            'version': 6,
            'command_id': 'must-not-display',
            'transition': {'step': 3, 'reward': 1, 'secret': 'must-not-display'},
        },
        'csrfToken': 'must-not-display',
    }],
    'username': 'must-not-display',
}


def make_worker(origin='http://127.0.0.1:8000'):
    return NetworkWorker(
        origin,
        DjangoAuth,
        ApiClient,
        GameSocketClient,
        ResponseValidator(),
    )


class HistoryClientTests(unittest.TestCase):
    def test_train_gate_and_confirmed_state_update(self):
        player = {'player_id': 7, 'room_id': 'room-01', 'x': 3, 'y': 2,
                  'coins': 5, 'version': 6}
        state = State(authenticated=True, player=player.copy(), ws_connected=True)
        self.assertTrue(state.begin_command('train', 10.0))
        self.assertEqual(state.player['coins'], 5)
        state.apply(Result('state', player={
            'player_id': 8, 'room_id': 'room-01', 'x': 1, 'y': 1,
            'coins': 99, 'version': 2,
        }))
        self.assertTrue(state.command_pending)
        self.assertEqual(state.player['coins'], 5)
        state.apply(Result('command', '개인 수련을 완료했습니다.', player={
            **player, 'coins': 6, 'version': 7,
        }, action='train'))
        self.assertFalse(state.command_pending)
        self.assertEqual(state.player['coins'], 6)

        wrong_tile = State(authenticated=True, player={**player, 'x': 2},
                           ws_connected=True)
        disconnected = State(authenticated=True, player=player.copy(), ws_connected=False)
        self.assertFalse(wrong_tile.begin_command('train', 10.0))
        self.assertFalse(disconnected.begin_command('train', 10.0))

    def test_train_command_contains_only_type_and_uuid(self):
        async def exercise():
            sent = []
            client = GameSocketClient(
                None,
                'http://127.0.0.1:8000',
                ResponseValidator(),
                lambda _result: None,
            )

            class Ws:
                closed = False

                async def send_json(self, payload):
                    sent.append(payload)
                    asyncio.get_running_loop().call_soon(
                        client._command_waiter.set_result,
                        {'player_id': 7, 'room_id': 'room-01', 'x': 3, 'y': 2,
                         'coins': 6, 'version': 7})

            client._ws = Ws()
            player = await client.command('train', '')
            return sent, player

        sent, player = asyncio.run(exercise())
        self.assertEqual(set(sent[0]), {'type', 'command_id'})
        self.assertEqual(sent[0]['type'], 'train')
        self.assertEqual(str(uuid.UUID(sent[0]['command_id'])), sent[0]['command_id'])
        self.assertEqual(player['coins'], 6)

    def test_train_success_queues_history_on_same_worker(self):
        async def exercise():
            worker = make_worker()
            worker._authenticated = True

            class Auth:
                def clear(self):
                    pass

            class Api:
                pass

            class Socket:
                async def command(_self, action, direction):
                    self.assertEqual((action, direction), ('train', ''))
                    return {
                        'player_id': 7,
                        'room_id': 'room-01',
                        'x': 3,
                        'y': 2,
                        'coins': 6,
                        'version': 7,
                    }

            await worker._dispatch(
                Request('command', action='train'), Auth(), Api(), Socket())
            return worker.results.get_nowait(), worker.requests.get_nowait()

        command, follow_up = asyncio.run(exercise())
        self.assertEqual(command.kind, 'command')
        self.assertEqual(command.action, 'train')
        self.assertEqual(follow_up.kind, 'history')

    def test_only_matching_own_state_acknowledges_command(self):
        async def exercise():
            results = []
            client = GameSocketClient(
                None,
                'http://127.0.0.1:8000',
                ResponseValidator(),
                results.append,
            )
            client._player_id = 7
            client._command_id = 'mine'
            client._command_waiter = asyncio.get_running_loop().create_future()
            checks = []
            messages = [
                {'type': 'state', 'player_id': 8, 'room_id': 'room-01',
                 'x': 1, 'y': 1, 'coins': 0, 'version': 1, 'command_id': 'mine'},
                {'type': 'state', 'player_id': 7, 'room_id': 'room-01',
                 'x': 3, 'y': 2, 'coins': 5, 'version': 6, 'command_id': 'other'},
                {'type': 'state', 'player_id': 7, 'room_id': 'room-01',
                 'x': 3, 'y': 2, 'coins': 6, 'version': 7, 'command_id': 'mine'},
            ]

            class Ws:
                close_code = None

                def __aiter__(self):
                    self.index = 0
                    return self

                async def __anext__(self):
                    if self.index >= len(messages):
                        raise StopAsyncIteration
                    if self.index:
                        checks.append(client._command_waiter.done())
                    data = messages[self.index]
                    self.index += 1
                    return type('Message', (), {
                        'type': aiohttp.WSMsgType.TEXT,
                        'data': json.dumps(data),
                    })()

            client._ws = Ws()
            await client._listen()
            return checks, client._command_waiter.result(), results

        checks, acknowledged, results = asyncio.run(exercise())
        self.assertEqual(checks, [False, False])
        self.assertEqual(acknowledged['coins'], 6)
        self.assertEqual([item.kind for item in results],
                         ['state', 'ws_event', 'ws_event'])
        self.assertEqual(results[0].player['player_id'], 8)

    def test_history_panel_accepts_extended_and_legacy_rows(self):
        panel = HistoryPanelState()
        panel.wait_for_train()
        self.assertFalse(panel.visible)
        extended = HISTORY['events'][0]
        legacy = {**extended, 'payload': {
            'x': 1, 'y': 2, 'coins': 0, 'version': 1, 'transition': None,
        }}
        handled = panel.apply(Result('history', player={
            'scope': 'current-player', 'limit': 20,
            'events': [extended, legacy],
        }))
        self.assertFalse(handled)
        self.assertFalse(panel.visible)
        self.assertEqual(panel.events[0]['payload']['transition']['step'], 3)
        self.assertIsNone(panel.events[1]['payload']['transition'])
        panel.show()
        self.assertTrue(panel.visible)

    def test_history_allowlist(self):
        safe = ResponseValidator().validate_history(HISTORY)
        self.assertEqual(safe, {
            'scope': 'current-player',
            'limit': 20,
            'events': [{
                'schema_version': 1,
                'event_id': '8a0b52f1-12dc-4434-a1a5-b86be381145a',
                'event_type': 'player.moved',
                'player_id': 7,
                'room_id': 'room-01',
                'event_time': '2026-09-16T01:02:03+00:00',
                'payload': {
                    'x': 3, 'y': 4, 'coins': 5, 'version': 6,
                    'transition': {'step': 3, 'reward': 1},
                },
            }],
        })
        self.assertNotIn('must-not-display', repr(safe))

    def test_http_history_emits_sanitized_api_panel_result(self):
        class Content:
            async def iter_chunked(self, _size):
                yield json.dumps(HISTORY).encode('utf-8')

        class Response:
            status = 200
            content_type = 'application/json'
            content = Content()

        class Context:
            async def __aenter__(self):
                return Response()

            async def __aexit__(self, *_args):
                return False

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(('GET', url, kwargs))
                return Context()

        async def exercise():
            session = Session()
            results = []
            client = ApiClient(
                session,
                'http://127.0.0.1:8000',
                ResponseValidator(),
                results.append,
            )
            history = await client.get_history()
            return session, history, results[0]

        session, history, api_result = asyncio.run(exercise())
        self.assertEqual(session.calls[0][0:2], (
            'GET', 'http://127.0.0.1:8000/api/history/'))
        self.assertEqual(api_result.kind, 'api')
        self.assertEqual(api_result.api_path, '/api/history/')
        self.assertEqual(api_result.status, 200)
        self.assertEqual(api_result.player, history)
        self.assertNotIn('must-not-display', repr(history))

    def test_history_dispatch_uses_fixed_path_and_updates_panel_state(self):
        async def exercise():
            worker = make_worker()
            worker._authenticated = True
            calls = []

            class Auth:
                def clear(self):
                    pass

            class Api:
                async def get_history(self):
                    calls.append(('GET', '/api/history/'))
                    worker.results.put_nowait(Result(
                        'api', status=200, player=HISTORY,
                        api_path='/api/history/'))
                    return HISTORY

            class Socket:
                pass

            await worker._dispatch(Request('history'), Auth(), Api(), Socket())
            api_result = worker.results.get_nowait()
            history_result = worker.results.get_nowait()
            return calls, api_result, history_result

        calls, api_result, history_result = asyncio.run(exercise())
        self.assertEqual(calls, [('GET', '/api/history/')])
        self.assertEqual(history_result.kind, 'history')
        state = State(authenticated=True, busy=True)
        state.apply(api_result)
        state.apply(history_result)
        self.assertEqual(state.api_path, '/api/history/')
        self.assertEqual(state.api_status, 200)
        self.assertFalse(state.busy)

    def test_history_redirect_and_unauthorized_request_relogin(self):
        class Content:
            async def iter_chunked(self, _size):
                if False:
                    yield b''

        class Jar:
            def clear(self):
                pass

        class Session:
            def __init__(self, status):
                self.status = status
                self.cookie_jar = Jar()

            def get(self, _url, **_kwargs):
                status = self.status

                class Response:
                    content_type = 'text/html'
                    content = Content()

                    async def __aenter__(self):
                        self.status = status
                        return self

                    async def __aexit__(self, *_args):
                        return False

                return Response()

        async def exercise(status):
            worker = make_worker()
            worker._authenticated = True
            auth = type('Auth', (), {
                'clear': lambda self: self.session.cookie_jar.clear(),
                'session': Session(status),
            })()
            api = ApiClient(
                auth.session,
                'http://127.0.0.1:8000',
                ResponseValidator(),
                worker.results.put,
            )

            class Socket:
                async def close(self):
                    pass

            await worker._dispatch(Request('history'), auth, api, Socket())
            results = []
            while not worker.results.empty():
                results.append(worker.results.get_nowait())
            return worker, results

        for status in (302, 401):
            with self.subTest(status=status):
                worker, results = asyncio.run(exercise(status))
                error = next(item for item in results if item.kind == 'history_error')
                self.assertTrue(error.needs_login)
                self.assertIn('로그인이 필요합니다', error.message)
                self.assertFalse(worker._authenticated)

    def test_history_rejects_invalid_shape(self):
        invalid = {**HISTORY, 'events': [{**HISTORY['events'][0], 'payload': {'x': 1}}]}
        with self.assertRaises(Failure):
            ResponseValidator().validate_history(invalid)


if __name__ == '__main__':
    unittest.main()
