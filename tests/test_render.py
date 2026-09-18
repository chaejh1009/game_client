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
            'api_player', 'api_history',
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
        self.analytics.schema_version = 1
        self.analytics.generated_at = '2026-09-18T00:00:00+00:00'
        self.analytics.event_count = 2
        self.analytics.by_action = ({'event_type': 'player.moved', 'count': 2},)
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


if __name__ == '__main__':
    unittest.main()
