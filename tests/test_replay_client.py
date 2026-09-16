"""Small, dependency-light checks for the standalone replay client."""

import json
import tempfile
import unittest
from pathlib import Path

from replay_client.config import Config
from replay_client.model import (
    ReplayEngine,
    duplicate_event,
    load_jsonl,
    make_event,
    save_jsonl,
)


class ReplayClientTests(unittest.TestCase):
    def test_config_points_at_recorded_jsonl(self):
        config = Config.load()
        self.assertTrue(config.data_path.is_file())
        self.assertEqual(len(load_jsonl(config.data_path)), 544)

    def test_engine_applies_events_in_file_order(self):
        events = load_jsonl(Config.load().data_path)
        engine = ReplayEngine(events)
        for _ in range(5):
            engine.step_next()
        state = engine.states[1]
        self.assertEqual(engine.cursor, 4)
        self.assertEqual((state["x"], state["y"], state["coins"]), (2, 2, 1))
        self.assertEqual(state["event_type"], "player.gathered")

    def test_edit_helpers_keep_jsonl_round_trip(self):
        events = load_jsonl(Config.load().data_path)
        changed = duplicate_event(events[0])
        changed["payload"]["x"] = 9
        appended = make_event(events, 1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "edited.jsonl"
            save_jsonl(output, [changed, appended])
            loaded = load_jsonl(output)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["payload"]["x"], 9)
        self.assertNotEqual(loaded[0]["event_id"], events[0]["event_id"])
        self.assertEqual(loaded[1]["event_type"], "player.moved")


if __name__ == "__main__":
    unittest.main()

