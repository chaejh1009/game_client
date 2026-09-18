"""Application use cases connecting main-thread state to the network worker."""
import time

from messages import Request, Result
from ports import AnalyticsPanelPort, HistoryPanelPort, NetworkPort, StatePort


class ClientController:
    def __init__(self, state: StatePort, analytics_panel: AnalyticsPanelPort,
                 history_panel: HistoryPanelPort, worker: NetworkPort):
        self.state = state
        self.analytics_panel = analytics_panel
        self.history_panel = history_panel
        self.worker = worker

    def submit(self, kind: str) -> bool:
        state = self.state
        if state.busy or state.closing or state.command_pending:
            return False
        if kind in ('player', 'history', 'logout') and (
                state.delivery_pending
                or self.analytics_panel.pending
                or self.analytics_panel.ingest_pending
                or self.history_panel.pending):
            return False
        if kind == 'login':
            if not state.username.strip() or not state.password:
                state.message = '사용자명과 비밀번호를 입력하세요.'
                return False
            request = Request(kind, state.username.strip(), state.password)
            self.analytics_panel.clear()
            self.history_panel.clear()
            state.password = ''  # Drop the input field immediately; never persist it.
        else:
            request = Request(kind)
        state.busy = True
        state.message = '서버에 요청 중…'
        self.worker.submit(request)
        return True

    def request_command(self, action: str, direction: str = '') -> bool:
        # Keyboard and mouse deliberately share this gate and request path.
        if not self.state.begin_command(action, time.monotonic(), direction):
            return False
        if action == 'train':
            self.history_panel.wait_for_train()
        self.worker.submit(Request('command', direction=direction, action=action))
        return True

    def request_delivery(self) -> bool:
        if not self.state.begin_delivery(time.monotonic()):
            return False
        self.worker.submit(Request('delivery'))
        return True

    def request_analytics(self) -> bool:
        if not self.analytics_panel.begin(
                self.state.authenticated, self.state.closing):
            return False
        self.history_panel.hide()
        self.worker.submit(Request('analytics'))
        return True

    def request_ingest(self) -> bool:
        if not self.analytics_panel.begin_ingest(
                self.state.authenticated, self.state.closing):
            return False
        self.history_panel.hide()
        self.worker.submit(Request('ingest'))
        return True

    def toggle_analytics(self) -> None:
        if self.analytics_panel.visible:
            self.analytics_panel.hide()
        else:
            self.request_analytics()

    def toggle_history(self) -> None:
        if self.history_panel.visible:
            self.history_panel.hide()
        elif (not self.analytics_panel.pending
              and not self.analytics_panel.ingest_pending):
            self.analytics_panel.hide()
            self.history_panel.show()

    def request_history(self) -> None:
        if not self.history_panel.pending and self.submit('history'):
            self.history_panel.begin()
            self.analytics_panel.hide()

    def begin_shutdown(self) -> bool:
        if self.state.closing:
            return False
        self.state.closing = True
        self.state.password = ''
        self.state.message = '연결을 정리하고 종료하는 중…'
        self.worker.stop()
        return True

    def apply_result(self, result: Result) -> None:
        handled = self.analytics_panel.apply(result)
        history_handled = self.history_panel.apply(result)
        if not (handled or history_handled) or result.needs_login:
            self.state.apply(result)
        if result.kind == 'logged_out' or result.needs_login:
            self.analytics_panel.clear()
            self.history_panel.clear()
