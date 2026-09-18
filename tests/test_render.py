"""Headless contract tests for the responsibility-split render layer."""
import ast
import copy
import os
from pathlib import Path
import sys
import unittest


os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
CLIENT_DIR = Path(__file__).resolve().parents[1] / 'client'
sys.path.insert(0, str(CLIENT_DIR))

import pygame

from client_app import ClientApp
from controller import ClientController
from messages import Result
from panels import AnalyticsPanelState, HistoryPanelState
from render import Renderer
from state import Config, State


PLAYER = dict(player_id=7, room_id=2, x=3, y=2, coins=5, version=6)
OTHER = dict(player_id=8, room_id=2, x=9, y=10, coins=1, version=2)


class RenderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.renderer = Renderer(Config.load())
        self.analytics = AnalyticsPanelState()
        self.history = HistoryPanelState()

    def test_renderer_exposes_all_application_hit_targets(self):
        expected = {
            'username', 'password', 'login',
            'up', 'down', 'left', 'right', 'gather', 'train',
            'refresh', 'logout', 'delivery', 'analytics', 'history_panel',
            'analytics_refresh', 'ingest_refresh', 'api_player', 'api_history',
        }
        self.assertEqual(expected, set(self.renderer.controls))
        for target in self.renderer.controls.values():
            self.assertIsInstance(target.collidepoint((target.x, target.y)), bool)

    def test_login_draw_is_read_only(self):
        state = State(username='student', password='secret')
        before = copy.deepcopy(state.__dict__)

        self.renderer.draw(state, self.analytics, self.history)

        self.assertEqual(before, state.__dict__)

    def test_game_and_overlay_draw_are_read_only(self):
        state = State(
            authenticated=True,
            player=PLAYER.copy(),
            players={OTHER['player_id']: OTHER.copy()},
            ws_connected=True,
            ws_json={'type': 'state', **PLAYER},
            api_status=200,
            api_json=PLAYER.copy(),
            api_path='/api/player/',
            delivery_source='mysql-outbox',
            event_count=12,
            pending_publish_count=3,
        )
        state.players[PLAYER['player_id']] = state.player
        state.online_count = len(state.players)
        self.analytics.visible = True
        self.analytics.available = True
        self.analytics.source_topic = 'game.actions.v1'
        self.analytics.source_kind = 'kafka-summary'
        self.analytics.generated_at = '2026-09-18T00:00:00+00:00'
        self.analytics.event_count = 2
        self.analytics.raw_record_count = 5
        self.analytics.by_action = ({'action_label': '이동', 'count': 2},)
        self.analytics.by_room = ({'room_id': 2, 'count': 2},)
        self.history.visible = True
        self.history.scope = 'current-player'
        self.history.limit = 20
        self.history.events = ({
            'event_time': '2026-09-18T00:00:00+00:00',
            'event_type': 'player.trained',
            'payload': {'transition': {'step': 1, 'reward': 1}},
        },)
        before = (
            copy.deepcopy(state.__dict__),
            copy.deepcopy(self.analytics.__dict__),
            copy.deepcopy(self.history.__dict__),
        )

        self.renderer.draw(state, self.analytics, self.history)

        self.assertEqual(before[0], state.__dict__)
        self.assertEqual(before[1], self.analytics.__dict__)
        self.assertEqual(before[2], self.history.__dict__)

    def test_analytics_panel_uses_requested_labels(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.analytics.visible = True
        self.analytics.available = True
        self.analytics.source_topic = 'game.actions.v1'
        self.analytics.source_kind = 'kafka-summary'
        self.analytics.generated_at = '2026-09-18T00:00:00+00:00'
        self.analytics.event_count = 3
        self.analytics.raw_record_count = 9
        self.analytics.by_action = (
            {'action_label': '이동', 'count': 2},
            {'action_label': '채굴', 'count': 1},
        )
        self.analytics.by_room = ({'room_id': 2, 'count': 3},)
        labels = []
        self.renderer._view.text = (
            lambda value, *_args, **_kwargs: labels.append(str(value)))

        self.renderer.draw(state, self.analytics, self.history)

        self.assertIn('고유 행동 수', labels)
        self.assertIn('원본 전달 행 수', labels)
        self.assertIn('고정 snapshot · 마지막 집계 기준', labels)
        self.assertTrue(any('접속자 수·잔액·현재 화면 이동 횟수' in item
                            for item in labels))

    def test_analytics_missing_and_error_are_not_rendered_as_zero(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.analytics.visible = True
        self.analytics.apply(Result('analytics', player={'available': False}))
        labels = []
        self.renderer._view.text = (
            lambda value, *_args, **_kwargs: labels.append(str(value)))

        self.renderer.draw(state, self.analytics, self.history)

        self.assertIn('행동 집계가 아직 없습니다', labels)
        self.assertNotIn('0', labels)

        self.analytics.apply(Result('analytics_error', '집계 조회 실패'))
        labels.clear()
        self.renderer.draw(state, self.analytics, self.history)
        self.assertTrue(any('집계 조회 실패' in item for item in labels))
        self.assertNotIn('0', labels)

    def test_room_list_remains_visible_after_kafka_card_is_drawn(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.analytics.visible = True
        self.analytics.available = True
        self.analytics.event_count = 210
        self.analytics.raw_record_count = 230
        self.analytics.by_action = (
            {'action_label': '이동', 'count': 90},
            {'action_label': '채굴', 'count': 80},
            {'action_label': '수련', 'count': 40},
        )
        self.analytics.by_room = tuple(
            {'room_id': f'room-{index}', 'count': index * 10}
            for index in range(1, 7)
        )
        expected = {f'방 room-{index}' for index in range(1, 5)} | {'외 2개 방'}
        view = self.renderer._view
        original_text = view.text
        rendered_rows = {}

        def capture_room_text(value, pos, color=None, font=None):
            if color is None:
                original_text(value, pos, font=font)
            else:
                original_text(value, pos, color, font)
            if str(value) in expected:
                bounds = (font or view.font).render(str(value), True, (255, 255, 255))
                bounds = bounds.get_rect(topleft=pos)
                self.assertTrue(view.screen.get_clip().contains(bounds))
                rendered_rows[str(value)] = (
                    bounds, pygame.image.tobytes(view.screen.subsurface(bounds), 'RGB'))

        view.text = capture_room_text
        self.renderer.draw(state, self.analytics, self.history)

        self.assertEqual(expected, set(rendered_rows))
        for label, (bounds, pixels) in rendered_rows.items():
            with self.subTest(label=label):
                self.assertEqual(
                    pixels, pygame.image.tobytes(view.screen.subsurface(bounds), 'RGB'),
                    '방별 목록이 이후에 그려진 카드나 텍스트에 가려졌습니다.')

    def test_ingest_panel_uses_published_snapshot_labels(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.analytics.visible = True
        self.analytics.ingest_available = True
        self.analytics.ingest_source = 'kafka-actions-v1'
        self.analytics.ingest_generated_at = '2026-09-18T00:00:00+00:00'
        self.analytics.ingest_record_count = 24
        self.analytics.ingest_event_count = 15
        self.analytics.ingest_duplicate_record_count = 3
        self.analytics.ingest_by_action = (
            {'event_type': 'player.moved', 'count': 11},
        )
        labels = []
        buttons = []
        self.renderer._view.text = (
            lambda value, *_args, **_kwargs: labels.append(str(value)))
        self.renderer._view.button = (
            lambda name, label, *_args, **_kwargs: buttons.append((name, label)))

        self.renderer.draw(state, self.analytics, self.history)

        self.assertIn('Kafka 수집 통계', labels)
        self.assertIn('수집 레코드', labels)
        self.assertIn('고유 사건', labels)
        self.assertIn('재전달 레코드', labels)
        self.assertIn(('ingest_refresh', '통계 다시 읽기'), buttons)
        self.assertTrue(any('이미 게시된 결과를 읽습니다' in item for item in labels))

    def test_ingest_missing_and_error_are_not_rendered_as_zero(self):
        state = State(authenticated=True, player=PLAYER.copy())
        self.analytics.visible = True
        self.analytics.apply(Result('ingest', player={
            'available': False, 'reason': 'summary_not_created',
        }))
        labels = []
        self.renderer._view.text = (
            lambda value, *_args, **_kwargs: labels.append(str(value)))

        self.renderer.draw(state, self.analytics, self.history)

        self.assertTrue(any('생성되지 않았습니다' in item for item in labels))
        self.assertNotIn('0', labels)

        self.analytics.apply(Result('ingest_error', '마지막 수집 통계를 읽을 수 없음'))
        labels.clear()
        self.renderer.draw(state, self.analytics, self.history)
        self.assertTrue(any('마지막 수집 통계를 읽을 수 없음' in item for item in labels))
        self.assertNotIn('0', labels)

    def test_render_modules_do_not_import_other_concrete_layers(self):
        forbidden = {
            'controller', 'network', 'network_api', 'network_auth', 'network_ws',
            'panels', 'state',
        }
        for path in CLIENT_DIR.glob('render*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
            self.assertFalse(forbidden & imports, f'{path.name}: {forbidden & imports}')


class AnalyticsRequestRoutingTests(unittest.TestCase):
    def test_user_request_submits_once_and_refresh_is_event_only(self):
        class Worker:
            def __init__(self):
                self.requests = []

            def submit(self, request):
                self.requests.append(request)

        state = State(authenticated=True)
        analytics = AnalyticsPanelState()
        history = HistoryPanelState()
        worker = Worker()
        controller = ClientController(state, analytics, history, worker)
        app = ClientApp(None, state, analytics, history, worker, controller, None)

        self.assertTrue(controller.request_analytics())
        self.assertFalse(controller.request_analytics())
        self.assertEqual(['analytics'], [item.kind for item in worker.requests])
        self.assertNotIn('analytics_refresh', app._control_names())

        controller.apply_result(Result('analytics', player={'available': False}))
        self.assertIn('analytics_refresh', app._control_names())
        self.assertIn('ingest_refresh', app._control_names())
        self.assertEqual(['analytics'], [item.kind for item in worker.requests])

        self.assertTrue(controller.request_ingest())
        self.assertFalse(controller.request_ingest())
        self.assertEqual(['analytics', 'ingest'], [item.kind for item in worker.requests])
        controller.apply_result(Result('ingest', player={
            'available': False, 'reason': 'summary_not_created',
        }))
        self.assertTrue(controller.request_ingest())
        self.assertEqual(['analytics', 'ingest', 'ingest'],
                         [item.kind for item in worker.requests])


if __name__ == '__main__':
    unittest.main()
