"""Main-thread state for optional information panels."""
from dataclasses import dataclass


@dataclass
class AnalyticsPanelState:
    visible: bool = False
    pending: bool = False
    available: bool | None = None
    schema_version: int | None = None
    generated_at: str = ''
    event_count: int | None = None
    by_action: tuple = ()
    by_room: tuple = ()
    message: str = ''

    def begin(self, authenticated, closing):
        if not authenticated or closing or self.pending:
            return False
        self.visible = True
        self.pending = True
        self.message = '집계 결과를 읽는 중…'
        return True

    def hide(self):
        if not self.pending:
            self.visible = False

    def clear(self):
        self.visible = False
        self.pending = False
        self.available = None
        self.schema_version = None
        self.generated_at = ''
        self.event_count = None
        self.by_action = ()
        self.by_room = ()
        self.message = ''

    def apply(self, result):
        if result.kind == 'analytics':
            data = result.player
            self.pending = False
            self.available = data['available']
            if not self.available:
                self.schema_version = None
                self.generated_at = ''
                self.event_count = None
                self.by_action = ()
                self.by_room = ()
                self.message = '아직 첫 집계가 없습니다'
                return True
            self.schema_version = data['schema_version']
            self.generated_at = data['generated_at']
            self.event_count = data['event_count']
            self.by_action = tuple(data['by_action'])
            self.by_room = tuple(data['by_room'])
            self.message = '저장된 집계 결과'
            return True
        if result.kind == 'analytics_error':
            self.pending = False
            self.message = result.message
            return True
        return False


@dataclass
class HistoryPanelState:
    visible: bool = False
    pending: bool = False
    scope: str = ''
    limit: int | None = None
    events: tuple = ()
    message: str = '수련을 완료하면 최근 행동 이력을 표시합니다.'

    def begin(self):
        if self.pending:
            return False
        self.visible = True
        self.pending = True
        self.message = '최근 행동 이력을 읽는 중…'
        return True

    def wait_for_train(self):
        self.pending = True
        self.message = '수련 결과를 기다리는 중…'

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def clear(self):
        self.visible = False
        self.pending = False
        self.scope = ''
        self.limit = None
        self.events = ()
        self.message = '수련을 완료하면 최근 행동 이력을 표시합니다.'

    def apply(self, result):
        if result.kind == 'command' and result.action == 'train':
            self.pending = True
            self.message = '수련 완료 · 최근 행동 이력을 읽는 중…'
            return False
        if result.kind == 'command_error' and result.action == 'train':
            self.pending = False
            self.message = result.message
            return False
        if result.kind == 'history':
            data = result.player
            self.pending = False
            self.scope = data['scope']
            self.limit = data['limit']
            self.events = tuple(data['events'])
            self.message = '최근 행동 이력'
            return False
        if result.kind == 'history_error':
            self.pending = False
            self.message = result.message
            return False
        return False
