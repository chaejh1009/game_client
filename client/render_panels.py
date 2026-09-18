"""API, analytics, and history panel drawing for the pygame client."""
import json

import pygame

from ports import AnalyticsPanelPort, HistoryPanelPort, StatePort
from render_support import (
    ACCENT,
    BG,
    CARD,
    ERROR,
    INK,
    MUTED,
    PENDING,
    TRAIN,
    RenderSupport,
)


def draw_analytics_panel(view: RenderSupport,
                         panel: AnalyticsPanelPort | None) -> None:
    if panel is None or not panel.visible:
        return
    rect = view.map_rect.inflate(-80, -70)
    pygame.draw.rect(view.screen, BG, rect, border_radius=12)
    pygame.draw.rect(view.screen, ACCENT, rect, width=2, border_radius=12)
    previous = view.screen.get_clip()
    view.screen.set_clip(rect.inflate(-4, -4))
    x, y = rect.x + 18, rect.y + 14
    view.text('확정 이벤트 통계', (x, y), ACCENT, view.font)
    if panel.pending:
        view.text('저장된 집계 결과를 읽는 중…', (x, y + 42), MUTED, view.small)
        view.screen.set_clip(previous)
        return
    if panel.available is False:
        view.text('아직 첫 집계가 없습니다', (x, y + 42), PENDING, view.font)
        view.screen.set_clip(previous)
        return
    if panel.available is not True:
        view.text(panel.message or '통계를 읽지 않았습니다.', (x, y + 42), MUTED,
                  view.small)
        view.screen.set_clip(previous)
        return
    view.text(f'전체 확정 사실 {panel.event_count}', (x, y + 36), INK, view.font)
    view.text(f'생성: {panel.generated_at}', (x, y + 64), MUTED, view.small)
    view.text(f'schema {panel.schema_version}', (rect.right - 92, y + 16), MUTED,
              view.small)
    table_y = y + 100
    column_width = (rect.width - 54) // 2
    for index, (title, rows, label_key) in enumerate((
        ('행동별', panel.by_action, 'event_type'),
        ('방별', panel.by_room, 'room_id'),
    )):
        column_x = x + index * (column_width + 18)
        view.text(title, (column_x, table_y), ACCENT, view.small)
        header = pygame.Rect(column_x, table_y + 24, column_width, 24)
        pygame.draw.rect(view.screen, CARD, header, border_radius=4)
        view.text('항목', (header.x + 8, header.y + 4), MUTED, view.small)
        view.text('count', (header.right - 52, header.y + 4), MUTED, view.small)
        row_y = header.bottom + 4
        for row in rows[:8]:
            row_rect = pygame.Rect(column_x, row_y, column_width, 23)
            pygame.draw.rect(view.screen, CARD, row_rect, width=1, border_radius=3)
            view.text(str(row[label_key])[:22], (row_rect.x + 8, row_rect.y + 3),
                      INK, view.small)
            view.text(str(row['count']), (row_rect.right - 48, row_rect.y + 3), INK,
                      view.small)
            row_y += 25
    view.screen.set_clip(previous)


def draw_api_panel(view: RenderSupport, state: StatePort,
                   analytics_panel: AnalyticsPanelPort | None,
                   history_panel: HistoryPanelPort | None) -> None:
    pygame.draw.rect(view.screen, CARD, view.api_panel, border_radius=10)
    previous = view.screen.get_clip()
    view.screen.set_clip(view.api_panel.inflate(-8, -8))
    x, y = view.api_panel.x + 12, view.api_panel.y + 10
    view.text('API 응답 보기', (x, y), ACCENT, view.small)
    disabled = (
        state.busy
        or state.closing
        or state.command_pending
        or state.delivery_pending
        or analytics_panel is not None and analytics_panel.pending
        or history_panel is not None and history_panel.pending
    )
    view.button(
        'api_player',
        '/api/player/',
        disabled,
        ACCENT if state.api_path == '/api/player/' else (84, 113, 122),
    )
    view.button(
        'api_history',
        '/api/history/',
        disabled,
        ACCENT if state.api_path == '/api/history/' else (84, 113, 122),
    )
    path = state.api_path or '—'
    status = str(state.api_status) if state.api_status is not None else '—'
    view.text(f'{path} · status {status}', (x, y + 62), MUTED, view.small)
    data = (
        json.dumps(state.api_json, ensure_ascii=False)
        if state.api_json is not None
        else '아직 API 응답이 없습니다.'
    )
    view.wrapped(data, x, y + 84, view.api_panel.width - 24, color=INK)
    view.screen.set_clip(previous)


def draw_history_panel(view: RenderSupport,
                       panel: HistoryPanelPort | None) -> None:
    if panel is None or not panel.visible:
        return
    rect = view.map_rect.inflate(-60, -44)
    pygame.draw.rect(view.screen, BG, rect, border_radius=12)
    pygame.draw.rect(view.screen, TRAIN, rect, width=2, border_radius=12)
    previous = view.screen.get_clip()
    view.screen.set_clip(rect.inflate(-4, -4))
    x, y = rect.x + 18, rect.y + 14
    view.text('최근 행동 이력', (x, y), TRAIN, view.font)
    if panel.pending or not panel.events:
        view.text(panel.message, (x, y + 42), MUTED, view.small)
        view.screen.set_clip(previous)
        return
    view.text(f'{panel.scope} · 최대 {panel.limit}개', (x + 150, y + 5), MUTED,
              view.small)
    header_y = y + 42
    view.text('event_time', (x, header_y), MUTED, view.tiny)
    view.text('event_type', (x + 160, header_y), MUTED, view.tiny)
    view.text('transition', (x + 300, header_y), MUTED, view.tiny)
    row_y = header_y + 18
    for event in panel.events[:20]:
        row = pygame.Rect(x, row_y, rect.width - 36, 16)
        pygame.draw.rect(view.screen, CARD, row, border_radius=4)
        event_time = str(event['event_time']).replace('T', ' ')[:19]
        view.text(event_time, (row.x + 8, row.y + 2), INK, view.tiny)
        view.text(str(event['event_type'])[:20], (row.x + 168, row.y + 2), INK,
                  view.tiny)
        transition = event['payload']['transition']
        if transition is None:
            detail = '확장 이전 기록'
            color = PENDING
        else:
            reward = transition['reward']
            detail = f"step {transition['step']} · reward {reward:+g}"
            color = ACCENT if reward >= 0 else ERROR
        view.text(detail, (row.x + 308, row.y + 2), color, view.tiny)
        row_y += 17
    view.screen.set_clip(previous)
