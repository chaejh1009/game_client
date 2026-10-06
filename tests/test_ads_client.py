"""Authenticated ad selection, public images and main-thread display contracts."""
import asyncio
from io import BytesIO
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))

import aiohttp
from aiohttp import web
import pygame
from yarl import URL
from ads_panel import AdsPanelState
from client_app import ClientApp
from queue import Queue
from messages import Result
from network_ads import AdsClient, IMAGE_LIMIT, creative_path
from network_errors import Failure
from panels import AnalyticsPanelState, HistoryPanelState
from render import Renderer
from state import Config, State


DECISION = dict(empty=False, decision_id='decision-1', campaign_id=4,
                title='광고 테스트', creative_path='/static/ads/creatives/sample.png',
                slot_id='village-board', bid_units=30, policy_version='v1')


class AdsTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.mode = 'ok'
        self.app = web.Application()
        self.app.router.add_get('/static/ads/creatives/sample.png', self.image)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.origin = f'http://127.0.0.1:{port}'
        game_app = web.Application()
        game_app.router.add_route('*', '/api/ads/decision/', self.decision)
        self.game_runner = web.AppRunner(game_app)
        await self.game_runner.setup()
        game_site = web.TCPSite(self.game_runner, '127.0.0.1', 0)
        await game_site.start()
        self.game_origin = f'http://127.0.0.1:{game_site._server.sockets[0].getsockname()[1]}'
        self.game_session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True),
                                                  trust_env=False)
        self.game_session.cookie_jar.update_cookies(
            {'sessionid': 'game-session', 'csrftoken': 'game-csrf'}, response_url=URL(self.game_origin))
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(),
                                             trust_env=False, timeout=aiohttp.ClientTimeout(total=5))
        self.results = []
        self.client = AdsClient(self.session, self.origin, self.results.append,
                                game_session=self.game_session, game_origin=self.game_origin)

    async def asyncTearDown(self):
        await self.session.close()
        await self.game_session.close()
        await self.game_runner.cleanup()
        await self.runner.cleanup()

    async def decision(self, request):
        self.requests.append(request)
        if self.mode in ('post', 'text', 'post_empty', 'post_failure', 'post_missing_csrf'):
            if request.method == 'GET':
                return web.Response(status=405, headers={'Allow': 'POST'})
            self.assertEqual(request.headers['X-CSRFToken'], 'game-csrf')
            self.assertEqual(request.headers['Origin'], self.game_origin)
            self.assertEqual(request.headers['Referer'], self.game_origin + '/play/')
            slot_id = (await request.json())['slot_id']
            if self.mode == 'post_empty':
                return web.json_response({'ad': None})
            if self.mode == 'post_failure':
                return web.json_response({'error': 'ads_unavailable'}, status=503)
        else:
            slot_id = request.query['slot_id']
        self.assertIn(slot_id, ('village-board', 'lobby-banner'))
        if slot_id == 'lobby-banner':
            self.assertNotIn('Cookie', request.headers)
        else:
            self.assertEqual(request.cookies.get('sessionid'), 'game-session')
        self.assertEqual(request.host, URL(self.game_origin).authority)
        if self.mode == 'empty':
            return web.json_response({'empty': True})
        if self.mode == 'auth':
            return web.Response(status=302, headers={'Location': '/accounts/login/'})
        if self.mode == 'html':
            return web.Response(text='<html>login</html>', content_type='text/html')
        if self.mode == 'missing':
            return web.Response(status=404)
        if self.mode == 'unavailable':
            return web.json_response({'error': 'ads_unavailable'}, status=503)
        data = dict(DECISION, slot_id=slot_id)
        if self.mode == 'text':
            data.pop('empty')
            data.pop('creative_path')
            data['bid_amount'] = data.pop('bid_units')
            data['body'] = '로비 광고 본문\n두 번째 줄'
        if self.mode == 'badpath':
            data['creative_path'] = '/static/ads/creatives/%2e%2e/private.png'
        response = web.json_response(data)
        response.set_cookie('gateway_cookie', 'must-never-leave-this-response')
        return response

    async def image(self, request):
        self.requests.append(request)
        for key in ('Cookie', 'X-CSRFToken', 'Authorization', 'X-Media-Key', 'Origin'):
            self.assertNotIn(key, request.headers)
        if self.mode == 'redirect':
            return web.Response(status=302, headers={'Location': '/api/ads/decision/'})
        if self.mode == 'mime':
            return web.Response(body=b'html', content_type='text/html')
        if self.mode == 'length':
            return web.Response(body=b'x' * (IMAGE_LIMIT + 1), content_type='image/png')
        response = web.StreamResponse(headers={'Content-Type': 'image/png'})
        await response.prepare(request)
        try:
            for _ in range(129 if self.mode == 'chunked' else 1):
                await response.write(b'x' * 16384)
            await response.write_eof()
        except (ConnectionResetError, aiohttp.ClientConnectionError):
            pass
        return response

    async def test_game_selection_and_public_image_never_leak_credentials(self):
        await self.client.select(7)
        self.assertEqual([r.kind for r in self.results], ['ads_decision', 'ads_image'])
        self.assertEqual(self.results[-1].decision_id, 'decision-1')
        self.assertEqual(self.results[-1].request_id, 7)
        self.assertEqual(len(self.results[-1].image_bytes), 16384)
        self.assertNotIn('creative_path', self.results[0].ad)
        self.assertEqual(len(self.session.cookie_jar), 0)

    async def test_both_slots_are_independent(self):
        await asyncio.gather(self.client.select(1), self.client.select(1, 'lobby-banner'))
        for slot in ('village-board', 'lobby-banner'):
            results = [r for r in self.results if r.slot_id == slot]
            self.assertEqual([r.kind for r in results], ['ads_decision', 'ads_image'])
            self.assertEqual(results[0].ad['slot_id'], slot)

    async def test_post_fallback_with_csrf_and_text_response(self):
        for mode, kinds in (('post', ['ads_decision', 'ads_image']),
                            ('text', ['ads_decision', 'ads_text']),
                            ('post_empty', ['ads_decision']),
                            ('post_failure', ['ads_error'])):
            with self.subTest(mode=mode):
                self.mode = mode
                self.results.clear()
                await self.client.select(8)
                self.assertEqual([r.kind for r in self.results], kinds)
                self.assertTrue(all(r.slot_id == 'village-board' for r in self.results))
        self.assertIn('503', self.results[0].message)

    async def test_lobby_uses_public_session_before_login(self):
        self.game_session.cookie_jar.clear()
        await self.client.select(1, 'lobby-banner')
        self.assertEqual([r.kind for r in self.results], ['ads_decision', 'ads_image'])
        self.assertNotIn('Cookie', self.requests[0].headers)

    async def test_lobby_rejects_legacy_authenticated_route_without_post(self):
        for mode, expected in (('post', 'HTTP 405'), ('auth', '허용하지'),
                               ('unavailable', 'HTTP 503')):
            self.mode = mode
            self.requests.clear()
            self.results.clear()
            await self.client.select(1, 'lobby-banner')
            self.assertEqual(len(self.requests), 1)
            self.assertEqual(self.results[0].kind, 'ads_error')
            self.assertIn(expected, self.results[0].message)

    async def test_post_without_csrf_does_not_send_request(self):
        self.mode = 'post_missing_csrf'
        self.game_session.cookie_jar.clear(lambda cookie: cookie.key == 'csrftoken')
        await self.client.select(1)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.results[0].kind, 'ads_error')
        self.assertIn('다시 로그인', self.results[0].message)

    async def test_selection_errors_explain_the_failure(self):
        for mode, expected in (('auth', '다시 로그인'), ('missing', 'API 설정'),
                               ('unavailable', 'HTTP 503'), ('html', '응답 형식')):
            with self.subTest(mode=mode):
                self.mode = mode
                self.results.clear()
                await self.client.select(3)
                self.assertEqual(self.results[0].kind, 'ads_error')
                self.assertIn(expected, self.results[0].message)

    async def test_rejections_keep_title_without_image_success(self):
        for mode in ('redirect', 'mime', 'length', 'chunked', 'badpath'):
            with self.subTest(mode=mode):
                self.mode = mode
                self.requests.clear()
                self.results.clear()
                await self.client.select(2)
                self.assertEqual([r.kind for r in self.results], ['ads_decision', 'ads_image_error'])
                self.assertEqual(self.results[0].ad['title'], DECISION['title'])
                self.assertEqual(len(self.requests), 1 if mode == 'badpath' else 2)

    async def test_empty_and_auth_html_never_download(self):
        for mode, kind in (('empty', 'ads_decision'), ('auth', 'ads_error'), ('html', 'ads_error')):
            self.mode = mode
            self.results.clear()
            self.requests.clear()
            await self.client.select(3)
            self.assertEqual([r.kind for r in self.results], [kind])
            self.assertEqual(len(self.requests), 1)


class AdsStateTests(unittest.TestCase):
    def test_paths(self):
        for value in ('https://evil/a.png', '//evil/a.png', '/static/ads/creatives/../a.png',
                      '/static/ads/creatives/a\\b.png', '/static/ads/creatives/a.png?q=x',
                      '/static/ads/creatives/a.png#x', '/static/other/a.png',
                      '/static/ads/creatives/%2e%2e/a.png', '/static/ads/creatives/a/./b.png'):
            with self.subTest(path=value), self.assertRaises(Failure):
                creative_path(value)
        self.assertEqual(creative_path(DECISION['creative_path']), DECISION['creative_path'])

    def test_timing_visibility_and_stale_results(self):
        panel = AdsPanelState()
        self.assertFalse(panel.begin(0, False))
        self.assertTrue(panel.begin(0, True))
        panel.apply(Result('ads_decision', ad=DECISION, request_id=1), 1)
        panel.apply(Result('ads_image', decision_id='wrong', image_bytes=b'late', request_id=1), 2)
        self.assertEqual(panel.image_bytes, b'')
        self.assertTrue(panel.pending)
        panel.apply(Result('ads_image', decision_id='decision-1', image_bytes=b'current', request_id=1), 2)
        self.assertFalse(panel.begin(100, True))  # Decode/display before refreshing after hidden time.
        panel.image_ready(True)
        panel.mark_displayed(100)
        self.assertFalse(panel.begin(109, True))
        self.assertFalse(panel.begin(110, False))
        self.assertTrue(panel.begin(110, True))
        self.assertFalse(panel.begin(111, True))
        panel.clear()
        panel.apply(Result('ads_image', decision_id='decision-1', image_bytes=b'late', request_id=1), 112)
        self.assertEqual(panel.image_bytes, b'')

    def test_slot_mismatch_is_ignored(self):
        panel = AdsPanelState(slot_id='lobby-banner')
        panel.begin(0, True)
        panel.apply(Result('ads_decision', ad=DECISION, request_id=1), 1)
        self.assertEqual(panel.decision, {})
        panel.apply(Result('ads_decision', ad=dict(DECISION, slot_id='lobby-banner'),
                           request_id=1, slot_id='lobby-banner'), 1)
        panel.apply(Result('ads_text', decision_id='decision-1', request_id=1,
                           slot_id='lobby-banner'), 2)
        self.assertFalse(panel.pending)
        self.assertEqual(panel.image_status, '준비')

    def test_minimum_refresh_interval(self):
        panel = AdsPanelState()
        panel.begin(0, True)
        panel.apply(Result('ads_decision', ad={'empty': True}, request_id=1), 1)
        self.assertFalse(panel.begin(14.999, True))
        self.assertTrue(panel.begin(15, True))

    def test_ads_display_in_their_respective_scenes(self):
        pygame.display.init()
        pygame.font.init()
        try:
            renderer = Renderer(Config.load())
            board = AdsPanelState()
            lobby = AdsPanelState(slot_id='lobby-banner')
            buffer = BytesIO()
            image = pygame.Surface((40, 40))
            image.fill((230, 80, 40))
            pygame.image.save(image, buffer, 'test.png')
            for panel in (board, lobby):
                panel.begin(0, True)
                panel.apply(Result('ads_decision', ad=dict(DECISION, slot_id=panel.slot_id,
                                   body='로비 광고 본문' if panel is lobby else ''),
                                   request_id=1, slot_id=panel.slot_id), 1)
                panel.apply(Result('ads_text' if panel is lobby else 'ads_image',
                                   decision_id='decision-1', request_id=1,
                                   slot_id=panel.slot_id,
                                   image_bytes=b'' if panel is lobby else buffer.getvalue()), 2)
            renderer.draw(State(authenticated=True), AnalyticsPanelState(),
                          HistoryPanelState(), board, lobby)
            self.assertTrue(board.displayed)
            self.assertFalse(lobby.displayed)
            renderer.draw(State(), AnalyticsPanelState(), HistoryPanelState(), board, lobby)
            self.assertTrue(lobby.displayed)
            for control in ('username', 'password', 'login'):
                self.assertFalse(renderer._view.controls[control].colliderect(renderer._view.lobby_ad_rect))
            self.assertFalse(renderer._view.ad_rect.colliderect(renderer._view.lobby_ad_rect))
            pygame.image.save(renderer._view.display, '/tmp/ads-both-preview.png')
        finally:
            pygame.quit()

    def test_login_screen_applies_only_lobby_results(self):
        class Worker:
            def __init__(self):
                self.results = Queue()
            def get_result_nowait(self):
                return self.results.get_nowait()
        worker = Worker()
        board, lobby = AdsPanelState(), AdsPanelState(slot_id='lobby-banner')
        for panel in (board, lobby):
            panel.begin(0, True)
            worker.results.put(Result('ads_error', 'HTTP 503', slot_id=panel.slot_id, request_id=1))
        app = ClientApp(None, State(), AnalyticsPanelState(), HistoryPanelState(),
                        worker, None, None, board, lobby)
        app._drain_results()
        self.assertEqual(lobby.message, 'HTTP 503')
        self.assertEqual(board.message, '광고 선택 대기')

    def test_surface_decode_blit_flip_and_failure(self):
        pygame.display.init()
        pygame.font.init()
        try:
            renderer = Renderer(Config.load())
            panel = AdsPanelState()
            panel.begin(0, True)
            panel.apply(Result('ads_decision', ad=DECISION, request_id=1), 1)
            buffer = BytesIO()
            image = pygame.Surface((40, 40))
            image.fill((230, 80, 40))
            pygame.image.save(image, buffer, 'test.png')
            panel.apply(Result('ads_image', decision_id='decision-1', image_bytes=buffer.getvalue(), request_id=1), 2)
            state = State(authenticated=True)
            analytics, history = AnalyticsPanelState(), HistoryPanelState()
            renderer.draw(state, analytics, history, panel)
            self.assertTrue(panel.displayed)
            self.assertEqual(panel.image_status, '준비')
            renderer.draw(state, analytics, history, panel)
            pygame.image.save(renderer._view.display, '/tmp/ads-panel-preview.png')
            panel.clear()
            panel.begin(10, True)
            request_id = panel.request_id
            panel.apply(Result('ads_decision', ad=DECISION, request_id=request_id), 10)
            panel.apply(Result('ads_image', decision_id='decision-1', image_bytes=b'not an image', request_id=request_id), 11)
            renderer.draw(state, analytics, history, panel)
            self.assertFalse(panel.displayed)
            self.assertEqual(panel.image_status, '실패')
        finally:
            pygame.quit()


if __name__ == '__main__':
    unittest.main()
