"""Pygame presentation for the replay client.

The UI deliberately keeps data editing in the same window as playback.  This
makes it easy to change one event, save a JSONL variant, and immediately
replay the changed sequence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pygame

try:  # Supports both `python replay_client/main.py` and package imports in tests.
    from .model import ReplayEngine, event_label, event_payload, short_time
except ImportError:  # pragma: no cover - direct script execution path
    from model import ReplayEngine, event_label, event_payload, short_time


BG = (12, 19, 28)
PANEL = (21, 31, 44)
PANEL_ALT = (25, 37, 51)
FIELD = (14, 23, 34)
LINE = (50, 68, 82)
INK = (235, 242, 241)
MUTED = (145, 166, 177)
FAINT = (91, 112, 122)
MINT = (104, 230, 181)
MINT_DARK = (48, 116, 98)
AMBER = (246, 188, 83)
CORAL = (244, 117, 108)
BLUE = (113, 166, 255)
PURPLE = (179, 137, 255)
GRASS = (75, 130, 77)
PATH = (181, 139, 88)


class ReplayUI:
    EDIT_FIELDS = (
        "event_type",
        "player_id",
        "room_id",
        "version",
        "x",
        "y",
        "coins",
        "event_time",
    )

    def __init__(self, screen: pygame.Surface, config: Any) -> None:
        self.screen = screen
        self.config = config
        self.tile_size = config.tile_size
        self.map_rect = pygame.Rect(
            54,
            156,
            config.map_columns * config.tile_size,
            config.map_rows * config.tile_size,
        )
        self.left_panel = pygame.Rect(28, 96, 790, 780)
        self.timeline_panel = pygame.Rect(840, 96, 572, 430)
        self.editor_panel = pygame.Rect(840, 548, 572, 328)
        self.timeline_list = pygame.Rect(854, 180, 544, 330)
        self.hit_regions: dict[str, pygame.Rect] = {}
        self.timeline_scroll = 0
        self.followed_cursor: int | None = None
        self.active_player = '—'
        self.selection: int | None = None
        self.focus: str | None = None
        self.cursor = 0
        self.select_all = False
        self.inputs: dict[str, str] = {
            "path": str(config.data_path),
            "filter": "",
        }
        self.inputs.update({field: "" for field in self.EDIT_FIELDS})
        self.assets: dict[str, pygame.Surface | None] = {}
        self.asset_errors: list[str] = []
        self._prepare_fonts()
        self._prepare_assets()

    def _prepare_fonts(self) -> None:
        font_path = pygame.font.match_font(
            "applesdgothicneo,malgungothic,nanumgothic,notosanscjkkr"
        )
        try:
            self.font = pygame.font.Font(font_path, 18)
            self.small = pygame.font.Font(font_path, 14)
            self.tiny = pygame.font.Font(font_path, 12)
            self.title = pygame.font.Font(font_path, 26)
            self.big = pygame.font.Font(font_path, 34)
        except (OSError, pygame.error):
            self.font = pygame.font.Font(None, 18)
            self.small = pygame.font.Font(None, 14)
            self.tiny = pygame.font.Font(None, 12)
            self.title = pygame.font.Font(None, 26)
            self.big = pygame.font.Font(None, 34)
            self.asset_errors.append("한글 폰트를 찾지 못해 기본 폰트를 사용합니다.")

    def _prepare_assets(self) -> None:
        for name in ("grass", "path", "tree", "house", "hero"):
            path = self.config.asset_dir / f"{name}.png"
            try:
                image = pygame.image.load(str(path)).convert_alpha()
                self.assets[name] = pygame.transform.scale(
                    image, (self.tile_size, self.tile_size)
                )
            except (OSError, pygame.error):
                self.assets[name] = None
                self.asset_errors.append(f"{name}.png 없음")

    def text(
        self,
        value: Any,
        position: tuple[int, int],
        color: tuple[int, int, int] = INK,
        font: pygame.font.Font | None = None,
    ) -> None:
        self.screen.blit((font or self.font).render(str(value), True, color), position)

    @staticmethod
    def fit(value: Any, width: int, font: pygame.font.Font) -> str:
        text = str(value)
        if font.size(text)[0] <= width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > width:
            text = text[:-1]
        return text + suffix

    def panel(self, rect: pygame.Rect, fill: tuple[int, int, int] = PANEL) -> None:
        pygame.draw.rect(self.screen, fill, rect, border_radius=12)
        pygame.draw.rect(self.screen, LINE, rect, width=1, border_radius=12)

    @staticmethod
    def actor_color(player_id: Any) -> tuple[int, int, int]:
        player_key = str(player_id)
        if player_key == "1":
            return MINT
        if player_key == "2":
            return AMBER
        return PURPLE

    def register(self, name: str, rect: pygame.Rect) -> None:
        self.hit_regions[name] = rect.copy()

    def button(
        self,
        name: str,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool = False,
        enabled: bool = True,
        accent: tuple[int, int, int] = MINT,
        font: pygame.font.Font | None = None,
    ) -> None:
        self.register(name, rect)
        if not enabled:
            fill, border, color = (30, 42, 53), LINE, FAINT
        elif active:
            fill, border, color = accent, accent, BG
        else:
            fill, border, color = PANEL_ALT, LINE, INK
        pygame.draw.rect(self.screen, fill, rect, border_radius=7)
        pygame.draw.rect(self.screen, border, rect, width=1, border_radius=7)
        rendered = (font or self.small).render(label, True, color)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def set_path(self, path: Path | str) -> None:
        self.inputs["path"] = str(path)
        self.focus = None

    def set_selection(self, index: int | None, event: dict[str, Any] | None) -> None:
        self.selection = index
        self.focus = None
        self.select_all = False
        if event is None:
            for field in self.EDIT_FIELDS:
                self.inputs[field] = ""
            return
        payload = event_payload(event)
        self.inputs.update(
            {
                "event_type": str(event.get("event_type", "")),
                "player_id": str(event.get("player_id", "")),
                "room_id": str(event.get("room_id", "")),
                "version": str(payload.get("version", "")),
                "x": str(payload.get("x", "")),
                "y": str(payload.get("y", "")),
                "coins": str(payload.get("coins", "")),
                "event_time": str(event.get("event_time", "")),
            }
        )

    def focus_field(self, name: str) -> None:
        self.focus = name
        self.cursor = len(self.inputs.get(name, ""))
        self.select_all = False

    def handle_text_input(self, value: str) -> None:
        if self.focus is None:
            return
        value = "".join(char for char in value if char not in "\r\n")
        if not value:
            return
        current = self.inputs.get(self.focus, "")
        if self.select_all:
            current = ""
            self.cursor = 0
            self.select_all = False
        limit = 500 if self.focus in ("path", "event_time") else 180
        current = current[: self.cursor] + value + current[self.cursor :]
        self.inputs[self.focus] = current[:limit]
        self.cursor = min(limit, self.cursor + len(value))

    def handle_key(self, key: int, modifiers: int = 0) -> str | None:
        if self.focus is None:
            return None
        if key == pygame.K_ESCAPE:
            self.focus = None
            self.select_all = False
            return None
        if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
            if self.focus == "path":
                return "load"
            if self.focus in self.EDIT_FIELDS:
                return "apply"
            self.focus = None
            return None
        if key == pygame.K_a and modifiers & (pygame.KMOD_CTRL | pygame.KMOD_META):
            self.select_all = True
            self.cursor = len(self.inputs.get(self.focus, ""))
            return None
        if key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
            self.select_all = False
        elif key == pygame.K_RIGHT:
            self.cursor = min(len(self.inputs.get(self.focus, "")), self.cursor + 1)
            self.select_all = False
        elif key == pygame.K_HOME:
            self.cursor = 0
            self.select_all = False
        elif key == pygame.K_END:
            self.cursor = len(self.inputs.get(self.focus, ""))
            self.select_all = False
        elif key == pygame.K_BACKSPACE:
            current = self.inputs.get(self.focus, "")
            if self.select_all:
                self.inputs[self.focus] = ""
                self.cursor = 0
                self.select_all = False
            elif self.cursor > 0:
                self.inputs[self.focus] = current[: self.cursor - 1] + current[self.cursor :]
                self.cursor -= 1
        elif key == pygame.K_DELETE:
            current = self.inputs.get(self.focus, "")
            if self.select_all:
                self.inputs[self.focus] = ""
                self.cursor = 0
                self.select_all = False
            elif self.cursor < len(current):
                self.inputs[self.focus] = current[: self.cursor] + current[self.cursor + 1 :]
        return None

    def _draw_input(
        self,
        name: str,
        rect: pygame.Rect,
        label: str,
        *,
        enabled: bool = True,
        placeholder: str = "",
    ) -> None:
        self.register("field:" + name, rect)
        self.text(label, (rect.x, rect.y - 18), FAINT, self.tiny)
        fill = FIELD if enabled else (25, 35, 45)
        border = MINT if self.focus == name and enabled else LINE
        pygame.draw.rect(self.screen, fill, rect, border_radius=6)
        pygame.draw.rect(self.screen, border, rect, width=1, border_radius=6)
        value = self.inputs.get(name, "") if enabled else ""
        rendered_value = value or placeholder
        color = INK if value else FAINT
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-12, -2))
        rendered = self.small.render(rendered_value, True, color)
        self.screen.blit(rendered, (rect.x + 10, rect.y + 7))
        if self.focus == name and enabled and pygame.time.get_ticks() // 500 % 2 == 0:
            before = value[: self.cursor]
            caret_x = rect.x + 10 + self.small.size(before)[0]
            pygame.draw.line(
                self.screen,
                MINT,
                (caret_x, rect.y + 6),
                (caret_x, rect.bottom - 6),
                2,
            )
        self.screen.set_clip(previous_clip)

    def filtered_indices(self, events: list[dict[str, Any]]) -> list[int]:
        needle = self.inputs["filter"].strip().lower()
        if not needle:
            return list(range(len(events)))
        result: list[int] = []
        for index, event in enumerate(events):
            payload = event_payload(event)
            haystack = " ".join(
                str(value).lower()
                for value in (
                    index,
                    event.get("event_type", ""),
                    event.get("player_id", ""),
                    event.get("room_id", ""),
                    payload.get("x", ""),
                    payload.get("y", ""),
                    payload.get("coins", ""),
                    event.get("event_time", ""),
                )
            )
            if needle in haystack:
                result.append(index)
        return result

    def _draw_header(
        self,
        source_path: Path | None,
        save_path: Path,
        dirty: bool,
        message: str,
        message_kind: str,
    ) -> None:
        self.text("REPLAY CLIENT", (28, 18), MINT, self.small)
        self.text("행동데이터 재생 스테이션", (28, 37), INK, self.title)
        path_rect = pygame.Rect(300, 18, 720, 32)
        self._draw_input(
            "path",
            path_rect,
            "불러올 JSONL 경로",
            placeholder="파일 경로를 입력하세요",
        )
        self.button("load", pygame.Rect(1032, 18, 84, 32), "불러오기")
        self.button(
            "save",
            pygame.Rect(1124, 18, 84, 32),
            "저장" + (" •" if dirty else ""),
            enabled=source_path is not None or dirty,
            accent=AMBER,
        )
        color = CORAL if message_kind == "error" else MINT if message_kind == "success" else MUTED
        status_rect = pygame.Rect(1220, 18, 192, 32)
        pygame.draw.rect(self.screen, PANEL, status_rect, border_radius=7)
        pygame.draw.rect(self.screen, LINE, status_rect, width=1, border_radius=7)
        self.text(self.fit(message or "준비됨", 176, self.tiny), (status_rect.x + 9, status_rect.y + 9), color, self.tiny)
        source_text = self.fit(
            f"source  {source_path or '파일을 불러오세요'}",
            630,
            self.tiny,
        )
        self.text(source_text, (300, 58), MUTED, self.tiny)
        save_text = self.fit(f"편집본 저장  {save_path}", 520, self.tiny)
        self.text(save_text, (890, 58), FAINT, self.tiny)

    def _draw_map(self, engine: ReplayEngine) -> None:
        map_card = self.map_rect.inflate(18, 18)
        pygame.draw.rect(self.screen, (16, 27, 32), map_card, border_radius=10)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(self.map_rect)
        path_tiles = {(x, 2) for x in range(self.config.map_columns)} | {
            (2, y) for y in range(self.config.map_rows)
        }
        for y in range(self.config.map_rows):
            for x in range(self.config.map_columns):
                tile_rect = pygame.Rect(
                    self.map_rect.x + x * self.tile_size,
                    self.map_rect.y + y * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )
                name = "path" if (x, y) in path_tiles else "grass"
                image = self.assets.get(name)
                if image is None:
                    pygame.draw.rect(self.screen, PATH if name == "path" else GRASS, tile_rect)
                else:
                    self.screen.blit(image, tile_rect)
                pygame.draw.rect(self.screen, (99, 147, 91), tile_rect, width=1)

        for name, positions, fallback in (
            ("tree", ((5, 4), (12, 3), (16, 10), (8, 12)), (36, 106, 65)),
            ("house", ((7, 6), (14, 8)), (156, 91, 69)),
        ):
            for x, y in positions:
                rect = pygame.Rect(
                    self.map_rect.x + x * self.tile_size,
                    self.map_rect.y + y * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )
                image = self.assets.get(name)
                if image is None:
                    pygame.draw.rect(self.screen, fallback, rect.inflate(-8, -6), border_radius=5)
                else:
                    self.screen.blit(image, image.get_rect(midbottom=rect.midbottom))

        spot = pygame.Rect(
            self.map_rect.x + 2 * self.tile_size,
            self.map_rect.y + 2 * self.tile_size,
            self.tile_size,
            self.tile_size,
        )
        pulse = 2 + int(2 * math.sin(pygame.time.get_ticks() / 260))
        pygame.draw.rect(self.screen, AMBER, spot.inflate(pulse, pulse), width=2, border_radius=5)
        pygame.draw.circle(self.screen, AMBER, spot.center, 4)

        # Player trails are drawn below the actors, so the latest position stays legible.
        trail_layer = pygame.Surface(self.map_rect.size, pygame.SRCALPHA)
        for player_id, points in engine.trails.items():
            if not points:
                continue
            points_on_map = [
                (
                    x * self.tile_size + self.tile_size // 2,
                    y * self.tile_size + self.tile_size // 2,
                )
                for x, y in points
            ]
            base_color = self.actor_color(player_id)
            color = (*base_color, 185)
            if len(points_on_map) > 1:
                pygame.draw.lines(trail_layer, color, False, points_on_map, 3)
            for point in points_on_map[:: max(1, len(points_on_map) // 18)]:
                pygame.draw.circle(trail_layer, color, point, 2)
        self.screen.blit(trail_layer, self.map_rect.topleft)

        for player_id, state in sorted(engine.states.items(), key=lambda item: str(item[0])):
            x = max(0, min(self.config.map_columns - 1, int(state["x"])))
            y = max(0, min(self.config.map_rows - 1, int(state["y"])))
            tile = pygame.Rect(
                self.map_rect.x + x * self.tile_size,
                self.map_rect.y + y * self.tile_size,
                self.tile_size,
                self.tile_size,
            )
            color = self.actor_color(player_id)
            if engine.last_event and engine.last_event.get("player_id") == player_id and engine.flash > 0:
                radius = int(self.tile_size * (0.55 + (0.45 - engine.flash) * 1.1))
                pygame.draw.circle(self.screen, (*color, 90), tile.center, radius, width=2)
            hero = self.assets.get("hero")
            if hero is None:
                pygame.draw.rect(self.screen, color, tile.inflate(-10, -8), border_radius=7)
            else:
                self.screen.blit(hero, hero.get_rect(midbottom=tile.midbottom))
            pygame.draw.rect(self.screen, color, tile.inflate(-3, -3), width=2, border_radius=6)
            label = self.tiny.render(f"P{player_id}", True, color)
            self.screen.blit(label, (tile.x + 3, tile.y + 3))
        self.screen.set_clip(previous_clip)
        pygame.draw.rect(self.screen, LINE, self.map_rect, width=2)

    def _draw_actor_cards(self, engine: ReplayEngine) -> None:
        self.text("ACTORS", (54, 682), MUTED, self.tiny)
        states = list(sorted(engine.states.items(), key=lambda item: str(item[0])))[:2]
        if not states:
            self.text("재생을 시작하면 플레이어 상태가 여기에 나타납니다.", (54, 702), FAINT, self.small)
            return
        card_width = 350
        for offset, (player_id, state) in enumerate(states):
            rect = pygame.Rect(54 + offset * 366, 698, card_width, 48)
            color = self.actor_color(player_id)
            pygame.draw.rect(self.screen, PANEL_ALT, rect, border_radius=7)
            pygame.draw.rect(self.screen, color, rect, width=2, border_radius=7)
            self.text(f"P{player_id}", (rect.x + 12, rect.y + 8), color, self.small)
            self.text(
                f"({state['x']}, {state['y']})",
                (rect.x + 54, rect.y + 8),
                INK,
                self.small,
            )
            self.text(f"coins {state['coins']}", (rect.x + 158, rect.y + 8), INK, self.small)
            self.text(f"v{state['version']}", (rect.right - 45, rect.y + 8), MUTED, self.tiny)

    def _draw_playback(self, engine: ReplayEngine) -> None:
        last = engine.last_event
        if last is None:
            last_label = "마지막 이벤트: 아직 재생하지 않았습니다."
        else:
            payload = event_payload(last)
            last_label = (
                f"마지막  {event_label(last)} · P{last.get('player_id', '?')} · "
                f"({payload.get('x', '?')}, {payload.get('y', '?')}) · {short_time(last.get('event_time'))}"
            )
        self.text(self.fit(last_label, 730, self.small), (54, 755), MUTED, self.small)
        y = 780
        self.button("reset", pygame.Rect(54, y, 60, 40), "처음")
        self.button("prev", pygame.Rect(120, y, 60, 40), "이전")
        self.button(
            "toggle_play",
            pygame.Rect(186, y, 102, 40),
            "일시정지" if engine.playing else "재생",
            active=engine.playing,
        )
        self.button("next", pygame.Rect(294, y, 60, 40), "다음")
        self.button("end", pygame.Rect(360, y, 60, 40), "끝")
        self.text("속도", (438, y + 12), MUTED, self.tiny)
        for offset, speed in enumerate((0.5, 1.0, 2.0, 4.0, 8.0)):
            label = f"{speed:g}x"
            rect = pygame.Rect(470 + offset * 48, y, 44, 40)
            self.button(f"speed:{speed:g}", rect, label, active=engine.speed == speed, font=self.tiny)
        progress_rect = pygame.Rect(54, 842, 730, 10)
        self.register("progress", progress_rect.inflate(0, 16))
        pygame.draw.rect(self.screen, FIELD, progress_rect, border_radius=5)
        fill_width = int(progress_rect.width * engine.progress)
        if fill_width:
            pygame.draw.rect(self.screen, MINT, (progress_rect.x, progress_rect.y, fill_width, progress_rect.height), border_radius=5)
        marker_x = progress_rect.x + int(progress_rect.width * engine.progress)
        pygame.draw.circle(self.screen, INK, (marker_x, progress_rect.centery), 5)
        self.text(
            f"{max(0, engine.cursor + 1):04d} / {len(engine.events):04d}",
            (696, 858),
            MUTED,
            self.tiny,
        )
        self.text("Space 재생/일시정지 · ←/→ 한 이벤트 · Home 처음 · Ctrl+S 저장", (54, 858), FAINT, self.tiny)

    def _draw_timeline(self, events: list[dict[str, Any]], engine: ReplayEngine) -> None:
        self.panel(self.timeline_panel)
        self.text("EVENT TIMELINE", (860, 112), MINT, self.small)
        self.text("행동 순서", (860, 132), INK, self.font)
        self.text(f"{len(events)} events", (1285, 116), MUTED, self.tiny)
        self._draw_input(
            "filter",
            pygame.Rect(854, 148, 544, 26),
            "",
            placeholder="검색  event_type · player · 좌표 · coins",
        )
        indices = self.filtered_indices(events)
        row_height = 23
        visible_rows = self.timeline_list.height // row_height
        max_scroll = max(0, len(indices) - visible_rows)
        self.timeline_scroll = min(max_scroll, max(0, self.timeline_scroll))
        if engine.cursor != self.followed_cursor and engine.cursor in indices:
            active_position = indices.index(engine.cursor)
            if active_position < self.timeline_scroll:
                self.timeline_scroll = active_position
            elif active_position >= self.timeline_scroll + visible_rows:
                self.timeline_scroll = active_position - visible_rows + 1
        self.followed_cursor = engine.cursor
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(self.timeline_list)
        for row, index in enumerate(indices[self.timeline_scroll : self.timeline_scroll + visible_rows]):
            event = events[index]
            rect = pygame.Rect(
                self.timeline_list.x,
                self.timeline_list.y + row * row_height,
                self.timeline_list.width,
                row_height - 2,
            )
            selected = index == self.selection
            current = index == engine.cursor
            fill = (38, 64, 62) if current else (33, 47, 59) if selected else PANEL_ALT if row % 2 else FIELD
            pygame.draw.rect(self.screen, fill, rect, border_radius=4)
            if current:
                pygame.draw.rect(self.screen, MINT, rect, width=1, border_radius=4)
            self.register(f"row:{index}", rect)
            player_id = event.get("player_id", "?")
            color = MINT if player_id == 1 else AMBER if player_id == 2 else PURPLE
            self.text(f"{index + 1:04d}", (rect.x + 8, rect.y + 3), FAINT, self.tiny)
            self.text(f"P{player_id}", (rect.x + 55, rect.y + 3), color, self.tiny)
            self.text(event_label(event), (rect.x + 94, rect.y + 3), INK, self.tiny)
            payload = event_payload(event)
            self.text(
                f"({payload.get('x', '?')}, {payload.get('y', '?')})",
                (rect.x + 146, rect.y + 3),
                INK,
                self.tiny,
            )
            self.text(f"c{payload.get('coins', '?')}", (rect.x + 228, rect.y + 3), AMBER, self.tiny)
            self.text(short_time(event.get("event_time")), (rect.x + 274, rect.y + 3), MUTED, self.tiny)
            self.text(str(event.get("event_type", "")), (rect.right - 140, rect.y + 3), FAINT, self.tiny)
        self.screen.set_clip(previous_clip)
        if not indices:
            self.text("검색 결과가 없습니다.", (870, 195), MUTED, self.small)
        self.text(f"{len(indices)}개 표시 · 마우스 휠로 이동", (860, 512), FAINT, self.tiny)

    def _draw_editor(self, events: list[dict[str, Any]]) -> None:
        self.panel(self.editor_panel)
        self.text("EVENT EDITOR", (860, 564), AMBER, self.small)
        if self.selection is None:
            self.text("타임라인에서 이벤트를 선택하세요.", (1280, 565), FAINT, self.tiny)
        else:
            self.text(f"#{self.selection + 1:04d} 선택됨", (1280, 565), MUTED, self.tiny)
        enabled = self.selection is not None
        x = 856
        self._draw_input("event_type", pygame.Rect(x, 599, 540, 29), "event_type", enabled=enabled, placeholder="player.moved")
        self._draw_input("player_id", pygame.Rect(x, 653, 140, 29), "player_id", enabled=enabled, placeholder="1")
        self._draw_input("room_id", pygame.Rect(x + 152, 653, 170, 29), "room_id", enabled=enabled, placeholder="room-01")
        self._draw_input("version", pygame.Rect(x + 334, 653, 206, 29), "payload.version", enabled=enabled, placeholder="1")
        self._draw_input("x", pygame.Rect(x, 707, 118, 29), "payload.x", enabled=enabled, placeholder="0")
        self._draw_input("y", pygame.Rect(x + 130, 707, 118, 29), "payload.y", enabled=enabled, placeholder="0")
        self._draw_input("coins", pygame.Rect(x + 260, 707, 118, 29), "payload.coins", enabled=enabled, placeholder="0")
        self._draw_input("event_time", pygame.Rect(x, 761, 540, 29), "event_time", enabled=enabled, placeholder="2026-09-11T08:05:28+00:00")
        self.button("apply", pygame.Rect(x, 812, 92, 34), "적용", enabled=enabled, accent=MINT)
        self.button("duplicate", pygame.Rect(x + 102, 812, 92, 34), "복제", enabled=enabled, accent=BLUE)
        self.button("delete", pygame.Rect(x + 204, 812, 92, 34), "삭제", enabled=enabled, accent=CORAL)
        self.button("add", pygame.Rect(x + 306, 812, 112, 34), "새 이벤트", accent=AMBER)
        self.text(self.fit("적용 후 재생은 처음부터", 118, self.tiny), (x + 430, 823), FAINT, self.tiny)

    def draw(
        self,
        events: list[dict[str, Any]],
        engine: ReplayEngine,
        *,
        source_path: Path | None,
        save_path: Path,
        dirty: bool,
        message: str,
        message_kind: str = "info",
    ) -> None:
        self.screen.fill(BG)
        self.hit_regions.clear()
        self._draw_header(source_path, save_path, dirty, message, message_kind)
        self.panel(self.left_panel)
        self.text("REPLAY STAGE", (54, 112), MINT, self.small)
        status = '재생 중' if engine.playing else '재생 완료' if engine.events and engine.cursor == len(engine.events) - 1 else '일시정지'
        self.text(status, (54, 132), MINT if engine.playing else AMBER, self.small)
        self.button('player_prev', pygame.Rect(270, 116, 38, 30), '〈')
        self.text(self.fit(f'유저 {self.active_player} · {len(events)}개', 214, self.small), (320, 123), INK, self.small)
        self.button('player_next', pygame.Rect(544, 116, 38, 30), '〉')
        self.text('유저 선택 · 로컬 재생', (604, 124), MUTED, self.tiny)
        self._draw_map(engine)
        self._draw_actor_cards(engine)
        self._draw_playback(engine)
        self._draw_timeline(events, engine)
        self._draw_editor(events)
