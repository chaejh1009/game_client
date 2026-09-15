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
