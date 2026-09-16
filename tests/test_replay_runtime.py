"""Offline regressions including presentation through the actual app loop."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import pygame
from replay_client.config import Config
from replay_client.main import ReplayApp
from replay_client.model import ReplayDataError, load_jsonl, save_jsonl


def event(player, x, y, coins=0, action='player.moved'):
    return dict(event_type=action, player_id=player, room_id='room-01',
                event_time='2026-09-16T00:00:00+00:00',
                payload=dict(x=x, y=y, coins=coins, version=1))


class ReplayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.config = replace(Config.load(), data_path=root / 'input.jsonl',
                              save_path=root / 'output.jsonl')
        self.records = [event(1, 1, 0), event(2, 5, 5), event(1, 2, 0),
                        event(1, 2, 2), event(1, 2, 2, 1, 'player.gathered'),
                        event(2, 6, 5)]
        save_jsonl(self.config.data_path, self.records)
        pygame.display.init()
        pygame.font.init()
        self.addCleanup(pygame.quit)
        network = patch('socket.socket', side_effect=AssertionError('Replay must be offline'))
        network.start()
        self.addCleanup(network.stop)

    def test_real_loop_presents_changing_frames_and_reaches_gather(self):
        app = ReplayApp(self.config, player_id='1')
        app.engine.speed = 8
        self.assertTrue(app.engine.playing)
        frames = []
        present = pygame.display.flip
        get_events = pygame.event.get
        deadline = time.monotonic() + 3

        def present_frame():
            frames.append((app.engine.cursor, pygame.image.tobytes(
                app.screen.subsurface(app.ui.map_rect), 'RGB')))
            present()

        def poll_events():
            if len(frames) >= 12 or time.monotonic() > deadline:
                return [pygame.event.Event(pygame.QUIT)]
            return get_events()

        with patch('pygame.display.flip', side_effect=present_frame), \
             patch('pygame.event.get', side_effect=poll_events):
            app.run()
        self.assertGreaterEqual(len(frames), 12, 'Drawing must be presented to the window')
        self.assertGreater(len({frame[1] for frame in frames}), 1)
        self.assertEqual(app.engine.cursor, 3)
        self.assertEqual(set(app.engine.states), {1})
        self.assertEqual(app.engine.states[1]['coins'], 1)
        self.assertEqual(app.engine.last_event['event_type'], 'player.gathered')

    def test_player_switch_seeks_and_pause(self):
        app = ReplayApp(self.config)
        app.handle_region_click('player_next', (0, 0))
        self.assertEqual(app.active_player, '2')
        self.assertEqual(len(app.events), 2)
        self.assertEqual(set(app.engine.states), {2})
        app.handle_region_click('end', (0, 0))
        self.assertEqual(app.engine.states[2]['x'], 6)
        self.assertFalse(app.engine.playing)
        app.handle_region_click('prev', (0, 0))
        self.assertEqual(app.engine.states[2]['x'], 5)
        app.handle_region_click('toggle_play', (0, 0))
        app.handle_region_click('field:x', (0, 0))
        self.assertFalse(app.engine.playing, 'Editing must retain focus')

    def test_edit_filtered_user_preserves_other_users_and_source(self):
        original_bytes = self.config.data_path.read_bytes()
        app = ReplayApp(self.config, player_id='2')
        app.ui.inputs['x'] = '9'
        app.apply_editor()
        app.duplicate_selected()
        app.delete_selected()
        app.add_event()
        app.save_data()
        saved = load_jsonl(self.config.save_path)
        self.assertEqual([e for e in saved if e['player_id'] == 1],
                         [e for e in self.records if e['player_id'] == 1])
        self.assertEqual(saved[1]['payload']['x'], 9)
        self.assertEqual(len(saved), len(self.records) + 1)
        self.assertEqual(self.config.data_path.read_bytes(), original_bytes)

    def test_replacement_file_and_invalid_file_keep_app_usable(self):
        app = ReplayApp(self.config)
        save_jsonl(self.config.save_path, [event('new-user', 4, 4)])
        app.load_data(str(self.config.save_path))
        self.assertEqual(app.active_player, 'new-user')
        self.assertTrue(app.engine.playing)
        previous = copy.deepcopy(app.events)
        app.load_data(str(self.config.base_dir / 'does-not-exist.jsonl'))
        self.assertEqual(app.events, previous)
        self.assertEqual(app.message_kind, 'error')

    def test_invalid_player_id_rejected_before_replay(self):
        with self.assertRaises(ReplayDataError):
            save_jsonl(self.config.save_path, [event([], 0, 0)])


if __name__ == '__main__':
    unittest.main()
