"""Run the local JSONL game-event replay client.

Usage from the project root:
    client/.venv/bin/python replay_client/main.py
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

try:  # Supports both `python replay_client/main.py` and `python -m replay_client.main`.
    from .config import Config
    from .model import (
        ReplayDataError,
        ReplayEngine,
        duplicate_event,
        event_payload,
        load_jsonl,
        make_event,
        save_jsonl,
    )
    from .ui import ReplayUI
except ImportError:  # pragma: no cover - direct script execution path
    from config import Config
    from model import (
        ReplayDataError,
        ReplayEngine,
        duplicate_event,
        event_payload,
        load_jsonl,
        make_event,
        save_jsonl,
    )
    from ui import ReplayUI


class ReplayApp:
    def __init__(self, config: Config, data_override: str | None = None,
                 player_id: str | None = None) -> None:
        self.config = config
        self.screen = pygame.display.set_mode((config.window_width, config.window_height))
        pygame.display.set_caption("Replay Client · 행동데이터 재생")
        self.ui = ReplayUI(self.screen, config)
        self.events: list[dict[str, Any]] = []
        self.all_events: list[dict[str, Any]] = []
        self.source_indices: list[int] = []
        self.player_ids: list[str] = []
        self.active_player = player_id
        self.engine = ReplayEngine(self.events)
        self.source_path: Path | None = None
        self.selected_index: int | None = None
        self.dirty = False
        self.message = "JSONL을 불러오는 중…"
        self.message_kind = "info"
        self.load_data(data_override or str(config.data_path), initial=True)

    def resolve_path(self, value: str) -> Path:
        path = Path(value.strip()).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (self.config.base_dir / path).resolve()

    def refresh_view(self, index: int = 0, *, autoplay: bool = False) -> None:
        self.player_ids = list(dict.fromkeys(str(e['player_id']) for e in self.all_events))
        self.source_indices = [i for i, e in enumerate(self.all_events)
                               if str(e['player_id']) == self.active_player]
        self.events = [self.all_events[i] for i in self.source_indices]
        self.engine.replace_events(self.events)
        self.ui.active_player = self.active_player or '—'
        self.ui.timeline_scroll = 0
        self.ui.followed_cursor = None
        self.selected_index = min(index, len(self.events) - 1) if self.events else None
        self.ui.set_selection(self.selected_index,
                              self.events[self.selected_index] if self.events else None)
        if autoplay:
            self.engine.toggle_play()

    def change_player(self, direction: int) -> None:
        if not self.player_ids:
            return
        current = self.player_ids.index(self.active_player) if self.active_player in self.player_ids else -1
        self.active_player = self.player_ids[(current + direction) % len(self.player_ids)]
        self.refresh_view(autoplay=True)
        self.set_message(f'P{self.active_player} · {len(self.events)}개 재생 중')

    def set_message(self, message: str, kind: str = "info") -> None:
        self.message = message
        self.message_kind = kind

    def load_data(self, raw_path: str, *, initial: bool = False) -> None:
        path = self.resolve_path(raw_path)
        try:
            events = load_jsonl(path)
        except ReplayDataError as exc:
            if initial:
                self.ui.set_path(path)
            self.set_message(str(exc), "error")
            return

        self.all_events = events
        ids = list(dict.fromkeys(str(e['player_id']) for e in events))
        if self.active_player is None or (not initial and self.active_player not in ids):
            self.active_player = ids[0]
        self.source_path = path
        self.dirty = False
        self.ui.set_path(path)
        self.refresh_view(autoplay=True)
        if not self.events:
            self.set_message(f'유저 {self.active_player} 없음 · 유저 선택 버튼을 사용하세요.', 'error')
            return
        status = "자동 재생 중" if self.engine.playing else "재생 대기"
        self.set_message(f"P{self.active_player} · {len(self.events)}개 · {status}", "success")

    def save_data(self) -> None:
        if not self.all_events:
            self.set_message("저장할 이벤트가 없습니다.", "error")
            return
        try:
            save_jsonl(self.config.save_path, self.all_events)
        except ReplayDataError as exc:
            self.set_message(str(exc), "error")
            return
        self.source_path = self.config.save_path
        self.dirty = False
        self.ui.set_path(self.source_path)
        self.set_message(f"편집본 저장됨 · {self.config.save_path.name}", "success")

    @staticmethod
    def parse_int(value: str, label: str) -> int:
        value = value.strip()
        if not value or value in ("-", "+"):
            raise ValueError(f"{label} 값을 입력하세요.")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{label}은(는) 정수여야 합니다.") from exc

    @staticmethod
    def parse_player(value: str) -> int | str:
        value = value.strip()
        if not value:
            raise ValueError("player_id 값을 입력하세요.")
        try:
            return int(value)
        except ValueError:
            return value

    def apply_editor(self) -> None:
        if self.selected_index is None or self.selected_index >= len(self.events):
            self.set_message("먼저 타임라인에서 이벤트를 선택하세요.", "error")
            return
        try:
            event_type = self.ui.inputs["event_type"].strip()
            if not event_type:
                raise ValueError("event_type 값을 입력하세요.")
            player_id = self.parse_player(self.ui.inputs["player_id"])
            version = self.parse_int(self.ui.inputs["version"], "version")
            x = self.parse_int(self.ui.inputs["x"], "x")
            y = self.parse_int(self.ui.inputs["y"], "y")
            coins = self.parse_int(self.ui.inputs["coins"], "coins")
            room_id = self.ui.inputs["room_id"].strip()
            event_time = self.ui.inputs["event_time"].strip()
            if not room_id:
                raise ValueError("room_id 값을 입력하세요.")
            if not event_time:
                raise ValueError("event_time 값을 입력하세요.")
        except ValueError as exc:
            self.set_message(str(exc), "error")
            return

        index = self.selected_index
        updated = copy.deepcopy(self.events[index])
        updated["event_type"] = event_type
        updated["player_id"] = player_id
        updated["room_id"] = room_id
        updated["event_time"] = event_time
        payload = event_payload(updated)
        payload.update({"x": x, "y": y, "coins": coins, "version": version})
        updated["payload"] = payload
        self.all_events[self.source_indices[index]] = updated
        self.dirty = True
        self.active_player = str(player_id)
        self.refresh_view(index)
        self.set_message(f"#{index + 1:04d} 이벤트가 수정되었습니다.", "success")

    def add_event(self) -> None:
        player_id: int | str = self.parse_player(self.active_player or '1')
        if self.ui.inputs.get("player_id", "").strip():
            try:
                player_id = self.parse_player(self.ui.inputs["player_id"])
            except ValueError:
                pass
        new_event = make_event(self.events, player_id)
        insert_at = (self.source_indices[self.selected_index] + 1
                     if self.selected_index is not None else len(self.all_events))
        self.all_events.insert(insert_at, new_event)
        self.active_player = str(player_id)
        self.dirty = True
        self.refresh_view(sum(str(e['player_id']) == self.active_player
                              for e in self.all_events[:insert_at]))
        self.set_message(f"새 이벤트 #{self.selected_index + 1:04d} 추가됨", "success")

    def duplicate_selected(self) -> None:
        if self.selected_index is None or self.selected_index >= len(self.events):
            self.set_message("복제할 이벤트를 선택하세요.", "error")
            return
        index = self.selected_index
        duplicated = duplicate_event(self.events[index])
        self.all_events.insert(self.source_indices[index] + 1, duplicated)
        self.dirty = True
        self.refresh_view(index + 1)
        self.set_message(f"#{index + 1:04d} 이벤트를 복제했습니다.", "success")

    def delete_selected(self) -> None:
        if self.selected_index is None or self.selected_index >= len(self.events):
            self.set_message("삭제할 이벤트를 선택하세요.", "error")
            return
        index = self.selected_index
        del self.all_events[self.source_indices[index]]
        self.dirty = True
        self.refresh_view(index)
        self.set_message(f"#{index + 1:04d} 이벤트를 삭제했습니다. 저장 전까지는 임시 변경입니다.", "success")

    def select_event(self, index: int, *, seek: bool = True) -> None:
        if index < 0 or index >= len(self.events):
            return
        self.selected_index = index
        if seek:
            self.engine.seek(index)
        self.ui.set_selection(index, self.events[index])
        self.set_message(f"#{index + 1:04d} 선택됨", "info")

    def apply_engine_event(self) -> None:
        if self.engine.cursor < 0 or self.engine.cursor >= len(self.events):
            return
        self.selected_index = self.engine.cursor
        self.ui.set_selection(self.selected_index, self.events[self.selected_index])

    def seek_progress(self, mouse_x: int) -> None:
        rect = self.ui.hit_regions.get("progress")
        if rect is None or not self.events:
            return
        ratio = max(0.0, min(1.0, (mouse_x - rect.left) / rect.width))
        index = round(ratio * (len(self.events) - 1))
        self.select_event(index)

    def handle_region_click(self, name: str, position: tuple[int, int]) -> None:
        if name == "load":
            self.load_data(self.ui.inputs["path"])
        elif name == "save":
            self.save_data()
        elif name.startswith("row:"):
            self.select_event(int(name.split(":", 1)[1]))
        elif name == "progress":
            self.seek_progress(position[0])
        elif name == "reset":
            self.engine.reset()
            self.set_message("처음 상태로 돌아갔습니다.", "info")
        elif name == "prev":
            self.engine.step_previous()
            self.apply_engine_event()
        elif name == "next":
            self.engine.playing = False
            if self.engine.step_next() is not None:
                self.apply_engine_event()
        elif name == "toggle_play":
            playing = self.engine.toggle_play()
            self.set_message("재생 중" if playing else "일시정지", "info")
            self.apply_engine_event()
        elif name == "end":
            if self.events:
                self.engine.seek(len(self.events) - 1)
                self.apply_engine_event()
                self.set_message("마지막 이벤트로 이동했습니다.", "info")
        elif name.startswith("speed:"):
            self.engine.speed = float(name.split(":", 1)[1])
            self.set_message(f"재생 속도 {self.engine.speed:g}x", "info")
        elif name == "apply":
            self.apply_editor()
        elif name == "duplicate":
            self.duplicate_selected()
        elif name == "delete":
            self.delete_selected()
        elif name == "add":
            self.add_event()
        elif name == 'player_prev':
            self.change_player(-1)
        elif name == 'player_next':
            self.change_player(1)
        elif name.startswith("field:"):
            self.engine.playing = False
            self.ui.focus_field(name.split(":", 1)[1])
        else:
            self.ui.focus = None

    def handle_mouse_down(self, event: pygame.event.Event) -> None:
        position = event.pos
        for name, rect in reversed(list(self.ui.hit_regions.items())):
            if rect.collidepoint(position):
                self.handle_region_click(name, position)
                return
        self.ui.focus = None

    def handle_key_down(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_s and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
            self.save_data()
            return
        if self.ui.focus is not None:
            action = self.ui.handle_key(event.key, event.mod)
            if action == "load":
                self.load_data(self.ui.inputs["path"])
            elif action == "apply":
                self.apply_editor()
            return
        if event.key == pygame.K_SPACE:
            playing = self.engine.toggle_play()
            self.set_message("재생 중" if playing else "일시정지", "info")
            self.apply_engine_event()
        elif event.key == pygame.K_LEFT:
            self.engine.step_previous()
            self.apply_engine_event()
        elif event.key == pygame.K_RIGHT:
            self.engine.playing = False
            if self.engine.step_next() is not None:
                self.apply_engine_event()
        elif event.key == pygame.K_HOME:
            self.engine.reset()
            self.set_message("처음 상태로 돌아갔습니다.", "info")
        elif event.key == pygame.K_END and self.events:
            self.engine.seek(len(self.events) - 1)
            self.apply_engine_event()

    def run(self) -> int:
        clock = pygame.time.Clock()
        pygame.key.start_text_input()
        running = True
        try:
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.handle_mouse_down(event)
                    elif event.type == pygame.MOUSEWHEEL:
                        if self.ui.timeline_panel.collidepoint(pygame.mouse.get_pos()):
                            self.ui.timeline_scroll -= event.y
                    elif event.type == pygame.TEXTINPUT:
                        self.ui.handle_text_input(event.text)
                    elif event.type == pygame.KEYDOWN:
                        self.handle_key_down(event)
                    elif event.type == pygame.DROPFILE:
                        self.load_data(event.file)

                applied = self.engine.update(clock.get_time() / 1000.0)
                if applied is not None:
                    self.apply_engine_event()
                if self.ui.focus:
                    rect = self.ui.hit_regions.get("field:" + self.ui.focus)
                    if rect is not None:
                        pygame.key.set_text_input_rect(rect)
                self.ui.draw(
                    self.events,
                    self.engine,
                    source_path=self.source_path,
                    save_path=self.config.save_path,
                    dirty=self.dirty,
                    message=self.message,
                    message_kind=self.message_kind,
                )
                # Present the newly drawn surface to the actual OS window.
                pygame.display.flip()
                clock.tick(60)
        finally:
            pygame.key.stop_text_input()
        return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JSONL game-event replay client")
    parser.add_argument(
        "--data",
        help="처음 불러올 JSONL 경로. 생략하면 replay_client/config.json을 사용합니다.",
    )
    parser.add_argument('--player', help='재생할 player_id. 생략하면 파일의 첫 유저를 선택합니다.')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        config = Config.load()
    except (OSError, ValueError, TypeError) as exc:
        print(f"replay_client/config.json을 확인하세요: {exc}")
        return 1
    args = parse_args(argv if argv is not None else sys.argv[1:])
    pygame.display.init()
    pygame.font.init()
    try:
        app = ReplayApp(config, args.data, args.player)
        return app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
