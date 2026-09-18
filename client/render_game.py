"""Authenticated game-scene drawing for the pygame client."""
import json
import math
import time

from ports import AnalyticsPanelPort, HistoryPanelPort, StatePort
from render_panels import draw_analytics_panel, draw_api_panel, draw_history_panel
from render_support import ACCENT, ERROR, INK, MUTED, PENDING, RenderSupport
from render_world import draw_world


def _command_color(state: StatePort, action: str, direction: str = ''):
    selected = state.selected_action == action
    if action == 'move':
        selected = selected and state.selected_direction == direction
    colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
    return selected, colors.get(state.command_status, ACCENT) if selected else (84, 113, 122)


def _draw_commands(view: RenderSupport, state: StatePort,
                   analytics_panel: AnalyticsPanelPort | None) -> None:
    for name, label in (('up', '↑'), ('left', '←'), ('down', '↓'), ('right', '→')):
        selected, color = _command_color(state, 'move', name)
        disabled = state.busy or state.closing or (state.command_pending and not selected)
        view.button(name, label, disabled, color)
    selected, color = _command_color(state, 'gather')
    disabled = state.busy or state.closing or (state.command_pending and not selected)
    view.button('gather', '채굴', disabled, color)
    _selected, color = _command_color(state, 'train')
    at_train_tile = (
        state.player is not None
        and (state.player['x'], state.player['y']) == (3, 2)
    )
    train_enabled = (
        state.authenticated
        and state.ws_connected
        and at_train_tile
        and not state.command_pending
        and not state.busy
        and not state.closing
    )
    view.button('train', 'X 수련', not train_enabled, color)
    disabled = (
        state.busy
        or state.closing
        or state.command_pending
        or state.delivery_pending
        or analytics_panel is not None and analytics_panel.pending
    )
    view.button('refresh', '갱신', disabled)
    view.button('logout', '로그아웃', disabled)


def _draw_delivery(view: RenderSupport, state: StatePort) -> None:
    pending = state.delivery_pending
    elapsed = time.monotonic() - state.last_delivery_at
    cooling = state.last_delivery_at >= 0 and elapsed < 5.0
    if pending:
        label = '확인 중…'
    elif cooling:
        label = f'{math.ceil(5.0 - elapsed)}초 후'
    else:
        label = '전달 상태'
    view.button('delivery', label, pending or cooling or state.busy or state.closing)
    panel = view.slots['village-board']
    if state.event_count is None:
        counts = '이벤트 — · 발행 대기 —'
    else:
        counts = f'이벤트 {state.event_count} · 발행 대기 {state.pending_publish_count}'
    view.text(counts, (panel.x + 12, panel.y + 52), INK, view.small)
    source = state.delivery_source or '—'
    view.text(f'source: {source}', (panel.x + 12, panel.y + 73), MUTED, view.small)


def _draw_command_status(view: RenderSupport, state: StatePort) -> None:
    statuses = {'pending': '요청 중', 'success': '완료', 'error': '실패'}
    colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
    if state.selected_action == 'gather':
        label = '코인 채굴'
    elif state.selected_action == 'train':
        label = '개인 수련'
    elif state.selected_direction:
        names = {'up': '위쪽', 'down': '아래쪽', 'left': '왼쪽', 'right': '오른쪽'}
        label = f'{names[state.selected_direction]} 이동'
    else:
        label = '방향키 이동 · Z 채굴 · X 수련'
    status = statuses.get(state.command_status)
    if status:
        label += f' · {status}'
    view.wrapped(label, 24, 620, view.map_rect.width,
                 color=colors.get(state.command_status, MUTED))
    view.wrapped(state.message, 24, 646, view.map_rect.width, color=MUTED)


def draw_game(view: RenderSupport, state: StatePort,
              analytics_panel: AnalyticsPanelPort | None,
              history_panel: HistoryPanelPort | None) -> None:
    """Draw the authenticated scene without changing state or panel models."""
    view.text('작은 마을', (24, 24), font=view.title)
    player = state.player
    if player is not None:
        stats = (
            f"room {player['room_id']}  ·  위치 ({player['x']}, {player['y']})"
            f"  ·  coins {player['coins']}  ·  version {player['version']}"
        )
        view.text(stats, (24, 76), MUTED, view.small)
    view.text('채굴 지점 (2, 2)  ·  개인 수련 (3, 2)', (24, 102), PENDING, view.small)
    draw_world(view, state)
    view.draw_slot('village-board')
    view.draw_slot('lobby-banner')

    room = state.room_id if state.room_id is not None else '—'
    stale = '' if state.ws_connected else ' · 마지막 정보'
    room_panel = view.slots['village-board']
    view.text(f'방 {room}', (room_panel.x + 12, room_panel.y + 10), ACCENT, view.small)
    view.wrapped(
        f'온라인 {state.online_count}명{stale}',
        room_panel.x + 12,
        room_panel.y + 30,
        112,
        color=INK if state.ws_connected else PENDING,
    )
    _draw_delivery(view, state)

    ws_panel = view.slots['lobby-banner']
    previous = view.screen.get_clip()
    view.screen.set_clip(ws_panel.inflate(-8, -8))
    view.text('WS 메시지', (ws_panel.x + 12, ws_panel.y + 10), ACCENT, view.small)
    ws_data = (
        json.dumps(state.ws_json, ensure_ascii=False)
        if state.ws_json is not None
        else '아직 WS 메시지가 없습니다.'
    )
    view.wrapped(
        ws_data,
        ws_panel.x + 12,
        ws_panel.y + 34,
        ws_panel.width - 24,
        color=INK,
    )
    view.screen.set_clip(previous)

    _draw_commands(view, state, analytics_panel)
    analytics_label = (
        '통계 닫기'
        if analytics_panel is not None and analytics_panel.visible
        else '통계 읽기'
    )
    analytics_disabled = analytics_panel is not None and analytics_panel.pending
    view.button(
        'analytics',
        analytics_label,
        analytics_disabled or state.busy or state.closing,
    )
    history_label = (
        '이력 닫기'
        if history_panel is not None and history_panel.visible
        else '수련 이력'
    )
    view.button(
        'history_panel',
        history_label,
        analytics_disabled or state.busy or state.closing,
    )
    _draw_command_status(view, state)
    draw_api_panel(view, state, analytics_panel, history_panel)
    draw_analytics_panel(view, analytics_panel)
    draw_history_panel(view, history_panel)
