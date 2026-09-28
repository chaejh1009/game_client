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


def draw_measurement_cards(view: RenderSupport, panel: AnalyticsPanelPort) -> None:
    """Draw published measurements below the fixed game region."""
    for kind, title, tint in (
            ('load', '최근 수업 측정', ACCENT),
            ('metrics', '분석 전달 상태', TRAIN)):
        rect = view.measurement_cards[kind]
        pygame.draw.rect(view.screen, CARD, rect, border_radius=10)
        pygame.draw.rect(view.screen, tint, rect, width=1, border_radius=10)
        previous = view.screen.get_clip()
        view.screen.set_clip(rect.inflate(-10, -8))
        x, y = rect.x + 14, rect.y + 12
        view.text(title, (x, y), tint, view.font)
        view.button(kind + '_refresh', '조회', getattr(panel, kind + '_pending'))
        data = getattr(panel, kind + '_data')
        message = getattr(panel, kind + '_message')
        if data is None:
            view.wrapped(message, x, y + 45, rect.width - 28,
                         color=ERROR if '실패' in message or '확인' in message else PENDING)
        elif kind == 'load':
            load = data['load']
            view.text(f"생성: {load['generated_at'][:40]}", (x, y + 39), MUTED, view.tiny)
            profile = load['profile']
            view.text(f"설정 접속 {profile.get('clients', '—')}개 · "
                      f"측정 {profile.get('seconds', '—')}초", (x, y + 59), MUTED, view.small)
            lines = (
                f"연결 성공 {load['connected_success']}개 · 최대 {load['connected_peak']}개",
                f"시도 {load['attempt_count']}건 · 성공 {load['success_count']}건 · 오류 {load['error_count']}건",
                f"소요 {load['elapsed_seconds']:.1f}초 · 처리율 {load['success_per_second']:.2f}건/초",
                f"RTT 표본 {load['rtt_sample_count']}건 · 평균 {_rtt(load['rtt_mean_ms'])} · p95 {_rtt(load['rtt_p95_ms'])}",
            )
            for index, line in enumerate(lines):
                view.text(line, (x, y + 84 + index * 22), INK, view.tiny)
            view.text('room_id', (x, y + 183), tint, view.tiny)
            view.text('이번 연결 수', (x + 118, y + 183), tint, view.tiny)
            view.text('성공 응답 수', (x + 260, y + 183), tint, view.tiny)
            for index, row in enumerate(load['by_room'][:4]):
                row_y = y + 203 + index * 18
                view.text(str(row['room_id'])[:14], (x, row_y), INK, view.tiny)
                view.text(f"{row['connected']}개", (x + 118, row_y), INK, view.tiny)
                view.text(f"{row['success_count']}건", (x + 260, row_y), INK, view.tiny)
            if len(load['by_room']) > 4:
                view.text(f"외 {len(load['by_room']) - 4}개 방", (x, y + 278), MUTED, view.tiny)
            elif not load['by_room']:
                view.text('방별 측정 없음', (x, y + 203), MUTED, view.tiny)
        else:
            metrics = data['metrics']
            lines = (
                f"측정 생성: {metrics['generated_at'][:40]}",
                f"구간 시작: {metrics['window_start'][:40]}",
                f"구간 끝: {metrics['window_end'][:40]}",
                f"확정 {metrics['confirmed_count']}건 · 발행 표시 대기 {metrics['pending_mark_count']}건",
                f"Kafka 알려진 지연 {metrics['kafka'].get('known_lag_sum', '—')}건"
                + ('' if metrics['kafka']['lag_complete'] else ' · 일부 위치 미확인'),
                'Spark 진행 시각: ' +
                str((metrics['spark_progress'] or {}).get('timestamp') or '표본 없음')[:40],
            )
            for index, line in enumerate(lines):
                view.wrapped(line, x, y + 44 + index * 35, rect.width - 28,
                             font=view.tiny, color=INK if index >= 3 else MUTED)
        if data is not None and message:
            view.text(message[:55], (x, rect.bottom - 25),
                      PENDING if getattr(panel, kind + '_pending') else ERROR, view.tiny)
        view.screen.set_clip(previous)


def _rtt(value) -> str:
    return '표본 없음' if value is None else f'{value:.1f} ms'


def draw_analytics_panel(view: RenderSupport,
                         panel: AnalyticsPanelPort | None) -> None:
    if panel is None or not panel.visible:
        return
    rect = pygame.Rect(
        view.map_rect.x + 16,
        view.map_rect.y - 8,
        view.map_rect.width - 32,
        720 - view.map_rect.y - 24,
    )
    pygame.draw.rect(view.screen, BG, rect, border_radius=12)
    pygame.draw.rect(view.screen, ACCENT, rect, width=2, border_radius=12)
    previous = view.screen.get_clip()
    view.screen.set_clip(rect.inflate(-4, -4))
    x, y = rect.x + 18, rect.y + 14
    queries_pending = panel.pending or panel.ingest_pending or panel.windows_pending
    for name, label, selected in (
        ('analytics_summary', '기존 통계', panel.analytics_view == 'summary'),
        ('analytics_windows', '시간 창', panel.analytics_view == 'windows'),
    ):
        view.button(name, label, color=ACCENT if selected else (84, 113, 122))
    if panel.analytics_view == 'windows':
        _draw_windows_panel(view, panel, rect)
        view.screen.set_clip(previous)
        return
    view.text('확정 사실 집계', (x, y), ACCENT, view.font)
    view.button('analytics_refresh', '새로 읽기', queries_pending)
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
    elif panel.available is False:
        view.text('아직 집계 없음', (x, y + 42), PENDING, view.font)
    elif panel.available is not True:
        view.wrapped(
            panel.message or '통계를 읽지 않았습니다.',
            x,
            y + 42,
            rect.width - 36,
            color=MUTED,
        )
    else:
        source_label = {'raw': 'DB 내보내기 스냅샷',
                        'delta': 'event_id별 고유 사실 Delta'}[panel.source]
        view.text(f'원천: {source_label} · schema v{panel.schema_version}',
                  (x, y + 36), MUTED, view.small)
        view.text(f'집계 생성 시각: {panel.generated_at[:40]}',
                  (x, y + 58), MUTED, view.small)

        metric_y = y + 82
        metrics = [('고유 확정 사실 수', panel.event_count)]
        if panel.record_count is not None:
            metrics.append(('선택한 원천의 행 수', panel.record_count))
        metric_width = (rect.width - 54) // len(metrics)
        for index, (label, value) in enumerate(metrics):
            metric = pygame.Rect(
                x + index * (metric_width + 18), metric_y, metric_width, 48)
            pygame.draw.rect(view.screen, CARD, metric, border_radius=7)
            view.text(label, (metric.x + 10, metric.y + 7), MUTED, view.tiny)
            view.text(str(value), (metric.x + 10, metric.y + 23), INK, view.font)

        table_y = metric_y + 68
        table_width = (rect.width - 54) // 2
        for table_index, (title, rows, label_key) in enumerate((
            ('event_type별', panel.by_action, 'event_type'),
            ('room_id별', panel.by_room, 'room_id'),
        )):
            table_x = x + table_index * (table_width + 18)
            view.text(title, (table_x, table_y - 18), ACCENT, view.small)
            if not rows:
                view.text('게시할 그룹 없음', (table_x + 4, table_y), MUTED, view.tiny)
            for index, row in enumerate(rows[:4]):
                row_y = table_y + index * 18
                count = str(row['count'])
                count_x = table_x + table_width - 8 - view.tiny.size(count)[0]
                row_clip = view.screen.get_clip()
                view.screen.set_clip(row_clip.clip(pygame.Rect(
                    table_x + 4, row_y, max(0, count_x - table_x - 12), 18)))
                view.text(str(row[label_key]), (table_x + 4, row_y), INK, view.tiny)
                view.screen.set_clip(row_clip)
                view.text(count, (count_x, row_y), INK, view.tiny)
            if len(rows) > 4:
                view.text(f'외 {len(rows) - 4}개 그룹',
                          (table_x + 4, table_y + 72), MUTED, view.tiny)

    ingest = pygame.Rect(x - 8, rect.y + 274, rect.width - 20, rect.bottom - rect.y - 288)
    pygame.draw.rect(view.screen, CARD, ingest, border_radius=9)
    pygame.draw.rect(view.screen, TRAIN, ingest, width=1, border_radius=9)
    ingest_x, ingest_y = ingest.x + 10, ingest.y + 10
    view.text('Kafka 수집 통계', (ingest_x, ingest_y), TRAIN, view.font)
    view.button('ingest_refresh', '통계 다시 읽기', queries_pending)
    view.text('이미 게시된 결과를 읽습니다 · Spark 실행 없음 · Kafka 연결 없음',
              (ingest_x, ingest_y + 34), MUTED, view.tiny)
    view.wrapped(
        '확정 사실은 먼저 수집됩니다. 뒤 시각의 레코드로 watermark가 진행된 뒤 창이 확정됩니다. '
        '창 요 약을 갱신한 다음 통계를 조회하세요.',
        ingest_x, ingest_y + 53, ingest.width - 20, font=view.tiny, color=MUTED,
    )
    if panel.ingest_pending:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 88,
                     ingest.width - 20, color=PENDING)
    elif panel.ingest_error:
        view.wrapped(panel.ingest_error, ingest_x, ingest_y + 88,
                     ingest.width - 20, color=ERROR)
    elif panel.ingest_available is False:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 88,
                     ingest.width - 20, color=PENDING)
    elif panel.ingest_available is True:
        view.text(f'source: {panel.ingest_source[:42]}',
                  (ingest_x, ingest_y + 87), MUTED, view.small)
        view.text(f'생성: {panel.ingest_generated_at[:34]}',
                  (ingest_x, ingest_y + 106), MUTED, view.small)
        metric_y = ingest_y + 128
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
        action_y = metric_y + 44
        view.text('event_type별', (ingest_x, action_y), TRAIN, view.tiny)
        for index, row in enumerate(panel.ingest_by_action[:4]):
            row_y = action_y + 17 + index * 16
            view.text(str(row['event_type'])[:30], (ingest_x + 4, row_y), INK, view.tiny)
            view.text(str(row['count']), (ingest.right - 42, row_y), INK, view.tiny)
        if not panel.ingest_by_action:
            view.text('행동별 수집 항목 없음', (ingest_x + 4, action_y + 17), MUTED,
                      view.tiny)
    else:
        view.wrapped(panel.ingest_message, ingest_x, ingest_y + 88,
                     ingest.width - 20, color=MUTED)

    if panel.error:
        view.text(f'행동 집계 갱신 실패: {panel.error[:52]}',
                  (x, rect.bottom - 40), ERROR, view.tiny)
    view.text('접속자 수·잔액·현재 화면 이동 횟수와 다른 집계입니다.',
              (x, rect.bottom - 25), MUTED, view.tiny)
    view.text('고정 snapshot · 마지막 집계 기준',
              (rect.right - 188, rect.bottom - 25), PENDING, view.tiny)
    view.screen.set_clip(previous)


def _draw_windows_panel(view: RenderSupport, panel: AnalyticsPanelPort,
                        rect: pygame.Rect) -> None:
    x, y = rect.x + 18, rect.y + 14
    view.text('시간 창 통계', (x, y), ACCENT, view.font)
    view.text('확정 시간 창의 전달 레코드 수(중복 전달 포함 가능)',
              (x, y + 48), INK, view.small)
    view.text('시작 포함 · 끝 미포함 [window_start, window_end)',
              (x, y + 72), MUTED, view.small)
    view.wrapped(f'집계 생성 시각: {panel.windows_generated_at or "—"}',
                 x, y + 96, rect.width - 36, font=view.tiny)
    for kind in ('all', 'tumbling', 'sliding'):
        view.button(f'windows_{kind}', kind,
                    color=ACCENT if panel.window_kind == kind else (84, 113, 122))
    view.button('windows_refresh', '새로 읽기',
                panel.pending or panel.ingest_pending or panel.windows_pending)
    view.text('종류 선택·페이지 이동은 받은 결과만 표시합니다.',
              (x, y + 174), MUTED, view.tiny)
    if panel.windows_pending:
        message, color = panel.windows_message, PENDING
    elif panel.windows_error:
        message, color = panel.windows_error, ERROR
    else:
        message, color = panel.windows_message, MUTED
    view.wrapped(message, x, y + 195, rect.width - 36, font=view.tiny, color=color)
    if panel.windows_available is not True or not panel.windows:
        return
    rows = panel.window_page_rows
    if not rows:
        view.text('선택한 종류의 확정된 게시 대상 창 없음',
                  (x, y + 236), PENDING, view.small)
        return

    # Each cell has its own clip: long timestamps/event names cannot cover counts.
    widths = (68, 144, 144, 136, rect.width - 36 - 492)
    labels = ('kind', 'window_start', 'window_end', 'event_type', 'count')
    column_x = x
    for label, width in zip(labels, widths):
        view.text(label, (column_x + 4, y + 224), MUTED, view.tiny)
        column_x += width
    row_height = min(48, (view.controls['windows_previous'].y - (y + 246) - 12) // 5)
    for index, row in enumerate(rows):
        row_rect = pygame.Rect(x, y + 246 + index * row_height,
                               rect.width - 36, row_height - 3)
        pygame.draw.rect(view.screen, CARD, row_rect, border_radius=4)
        column_x = x
        for label, width in zip(labels, widths):
            cell = pygame.Rect(column_x + 4, row_rect.y + 4, width - 8, row_rect.height - 8)
            previous = view.screen.get_clip()
            view.screen.set_clip(previous.clip(cell))
            view.wrapped(row[label], cell.x, cell.y, cell.width, font=view.tiny,
                         color=ACCENT if label == 'count' else INK)
            view.screen.set_clip(previous)
            column_x += width
    view.button('windows_previous', '이전', panel.window_page == 0)
    view.button('windows_next', '다음', panel.window_page + 1 >= panel.window_page_count)
    view.text(f'{panel.window_page + 1} / {panel.window_page_count} · '
              f'{len(panel.visible_windows)}행',
              (x + 210, view.controls['windows_previous'].y + 6), MUTED, view.small)


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
        or analytics_panel is not None and analytics_panel.windows_pending
        or history_panel is not None and history_panel.pending
    )
    view.button(
        'api_player',
        'player',
        disabled,
        ACCENT if state.api_path == '/api/player/' else (84, 113, 122),
    )
    view.button(
        'api_history',
        'history',
        disabled,
        ACCENT if state.api_path == '/api/history/' else (84, 113, 122),
    )
    view.button(
        'api_windows',
        'windows',
        disabled,
        ACCENT if state.api_path == '/api/analytics/windows/' else (84, 113, 122),
    )
    view.button(
        'api_analytics',
        '집계',
        disabled,
        ACCENT if state.api_path == '/api/analytics/' else (84, 113, 122),
    )
    path = state.api_path or '—'
    status = str(state.api_status) if state.api_status is not None else '—'
    view.text(path, (x, y + 54), MUTED, view.tiny)
    view.text(f'status {status}', (x, y + 71), MUTED, view.tiny)
    data = (
        json.dumps(state.api_json, ensure_ascii=False)
        if state.api_json is not None
        else '아직 API 응답이 없습니다.'
    )
    view.wrapped(data, x, y + 90, view.api_panel.width - 24, font=view.tiny, color=INK)
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
