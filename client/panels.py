"""Main-thread state for optional information panels."""
from dataclasses import dataclass


@dataclass
class AnalyticsPanelState:
    visible: bool = False
    pending: bool = False
    available: bool | None = None
    source_topic: str = ''
    source_kind: str = ''
    generated_at: str = ''
    event_count: int | None = None
    raw_record_count: int | None = None
    by_action: tuple = ()
    by_room: tuple = ()
    message: str = ''
    error: str = ''

    def begin(self, authenticated, closing):
        if not authenticated or closing or self.pending:
            return False
        self.visible = True
        self.pending = True
        self.message = '집계 결과를 읽는 중…'
        self.error = ''
        return True

    def hide(self):
        if not self.pending:
            self.visible = False

    def clear(self):
        self.visible = False
        self.pending = False
        self.available = None
        self.source_topic = ''
        self.source_kind = ''
        self.generated_at = ''
        self.event_count = None
        self.raw_record_count = None
        self.by_action = ()
        self.by_room = ()
        self.message = ''
        self.error = ''

    def apply(self, result):
        if result.kind == 'analytics':
            data = result.player
            self.pending = False
            self.available = data['available']
            self.error = ''
            if not self.available:
                self.source_topic = ''
                self.source_kind = ''
                self.generated_at = ''
                self.event_count = None
                self.raw_record_count = None
                self.by_action = ()
                self.by_room = ()
                self.message = '행동 집계가 아직 없습니다'
                return True
            summary = data['summary']
            self.source_topic = data['source_topic']
            self.source_kind = data['source_kind']
            self.generated_at = summary['generated_at']
            self.event_count = summary['event_count']
            self.raw_record_count = data['raw_record_count']
            self.by_action = tuple(summary['by_action'])
            self.by_room = tuple(summary['by_room'])
            self.message = '고정 snapshot · 마지막 집계 기준'
            return True
        if result.kind == 'analytics_error':
            self.pending = False
            self.message = result.message
            self.error = result.message
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
