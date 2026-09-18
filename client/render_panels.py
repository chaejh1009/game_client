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
    rect = pygame.Rect(
        view.map_rect.x + 16,
        view.map_rect.y - 8,
        view.map_rect.width - 32,
        view.config.window_height - view.map_rect.y - 24,
    )
    pygame.draw.rect(view.screen, BG, rect, border_radius=12)
    pygame.draw.rect(view.screen, ACCENT, rect, width=2, border_radius=12)
    previous = view.screen.get_clip()
    view.screen.set_clip(rect.inflate(-4, -4))
    x, y = rect.x + 18, rect.y + 14
    view.text('행동 집계 snapshot', (x, y), ACCENT, view.font)
    if panel.pending:
        view.text('저장된 집계 결과를 읽는 중…', (x, y + 42), MUTED, view.small)
    elif panel.error and panel.available is not True:
        view.wrapped(
            panel.error,
            x,
            y + 42,
            rect.width - 36,
            color=ERROR,
        )
        view.button('analytics_refresh', '다시 조회', False)
    elif panel.available is False:
        view.text('행동 집계가 아직 없습니다', (x, y + 42), PENDING, view.font)
        view.button('analytics_refresh', '조회', False)
    elif panel.available is not True:
        view.wrapped(
            panel.message or '통계를 읽지 않았습니다.',
            x,
            y + 42,
            rect.width - 36,
            color=MUTED,
        )
        view.button('analytics_refresh', '다시 조회', False)
    else:
        view.text(f'topic: {panel.source_topic[:52]}', (x, y + 34), MUTED, view.small)
        view.text(f'kind: {panel.source_kind[:52]}', (x, y + 54), MUTED, view.small)
        view.text(f'생성: {panel.generated_at[:40]}', (x, y + 74), MUTED, view.small)

        metric_y = y + 102
        metric_width = (rect.width - 54) // 2
        for index, (label, value) in enumerate((
            ('고유 행동 수', panel.event_count),
            ('원본 전달 행 수', panel.raw_record_count),
        )):
            metric = pygame.Rect(
                x + index * (metric_width + 18), metric_y, metric_width, 48)
            pygame.draw.rect(view.screen, CARD, metric, border_radius=7)
            view.text(label, (metric.x + 10, metric.y + 7), MUTED, view.tiny)
            view.text(str(value), (metric.x + 10, metric.y + 23), INK, view.font)

        action_y = metric_y + 68
        view.text('행동별', (x, action_y - 18), ACCENT, view.small)
        card_gap = 8
        action_width = (rect.width - 54) * 3 // 5
        card_width = (action_width - card_gap * 2) // 3
        for index in range(3):
            card = pygame.Rect(
                x + index * (card_width + card_gap), action_y, card_width, 54)
            pygame.draw.rect(view.screen, CARD, card, border_radius=7)
            panel_clip = view.screen.get_clip()
            view.screen.set_clip(card.inflate(-12, -8))
            if index < len(panel.by_action):
                row = panel.by_action[index]
                view.text(str(row['action_label'])[:18], (card.x + 8, card.y + 8),
                          MUTED, view.tiny)
                view.text(str(row['count']), (card.x + 8, card.y + 26), INK, view.font)
            else:
                view.text('집계 항목 없음', (card.x + 8, card.y + 18), MUTED, view.tiny)
            view.screen.set_clip(panel_clip)

        room_x, room_y = x + action_width + 18, action_y
        view.text('방별 행동 수', (room_x, room_y - 18), ACCENT, view.small)
        for index, row in enumerate(panel.by_room[:4]):
            row_y = room_y + index * 18
            count = str(row['count'])
            count_x = rect.right - 18 - view.small.size(count)[0]
            panel_clip = view.screen.get_clip()
            view.screen.set_clip(pygame.Rect(
                room_x, row_y, max(0, count_x - room_x - 8), 18))
            view.text(f"방 {str(row['room_id'])[:22]}", (room_x, row_y), INK, view.small)
            view.screen.set_clip(panel_clip)
            view.text(count, (count_x, row_y), INK, view.small)
        if not panel.by_room:
            view.text('방별 집계 항목 없음', (room_x, room_y), MUTED, view.small)
        elif len(panel.by_room) > 4:
            view.text(f'외 {len(panel.by_room) - 4}개 방', (room_x, room_y + 72),
                      MUTED, view.tiny)

    ingest = pygame.Rect(x - 8, rect.y + 274, rect.width - 20, rect.bottom - rect.y - 288)
    pygame.draw.rect(view.screen, CARD, ingest, border_radius=9)
    pygame.draw.rect(view.screen, TRAIN, ingest, width=1, border_radius=9)
    ingest_x, ingest_y = ingest.x + 10, ingest.y + 10
    view.text('Kafka 수집 통계', (ingest_x, ingest_y), TRAIN, view.font)
    view.button('ingest_refresh', '통계 다시 읽기', panel.ingest_pending)
    view.text('이미 게시된 결과를 읽습니다 · Spark 실행 없음 · Kafka 연결 없음',
              (ingest_x, ingest_y + 34), MUTED, view.tiny)
    if panel.ingest_pending:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 58,
                     ingest.width - 20, color=PENDING)
    elif panel.ingest_error:
        view.wrapped(panel.ingest_error, ingest_x, ingest_y + 58,
                     ingest.width - 20, color=ERROR)
    elif panel.ingest_available is False:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 58,
                     ingest.width - 20, color=PENDING)
    elif panel.ingest_available is True:
        view.text(f'source: {panel.ingest_source[:42]}',
                  (ingest_x, ingest_y + 57), MUTED, view.small)
        view.text(f'생성: {panel.ingest_generated_at[:34]}',
                  (ingest_x, ingest_y + 76), MUTED, view.small)
        metric_y = ingest_y + 98
        metric_width = (ingest.width - 32) // 3
        for index, (label, value) in enumerate((
            ('수집 레코드', panel.ingest_record_count),
            ('고유 사건', panel.ingest_event_count),
            ('재전달 레코드', panel.ingest_duplicate_record_count),
        )):
            metric = pygame.Rect(
                ingest_x + index * (metric_width + 6), metric_y,
                metric_width, 42)
            pygame.draw.rect(view.screen, BG, metric, border_radius=6)
            view.text(label, (metric.x + 6, metric.y + 5), MUTED, view.tiny)
            view.text(str(value), (metric.x + 6, metric.y + 20), INK, view.small)
        action_y = metric_y + 52
        view.text('event_type별', (ingest_x, action_y), TRAIN, view.tiny)
        for index, row in enumerate(panel.ingest_by_action[:4]):
            row_y = action_y + 17 + index * 16
            view.text(str(row['event_type'])[:30], (ingest_x + 4, row_y), INK, view.tiny)
            view.text(str(row['count']), (ingest.right - 42, row_y), INK, view.tiny)
        if not panel.ingest_by_action:
            view.text('행동별 수집 항목 없음', (ingest_x + 4, action_y + 17), MUTED,
                      view.tiny)
    else:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 58,
                     ingest.width - 20, color=MUTED)

    if panel.error:
        view.text(f'행동 집계 갱신 실패: {panel.error[:52]}',
                  (x, rect.bottom - 40), ERROR, view.tiny)
    view.text('접속자 수·잔액·현재 화면 이동 횟수와 다른 집계입니다.',
              (x, rect.bottom - 25), MUTED, view.tiny)
    view.text('고정 snapshot · 마지막 집계 기준',
              (rect.right - 188, rect.bottom - 25), PENDING, view.tiny)
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
        or analytics_panel is not None and analytics_panel.ingest_pending
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
