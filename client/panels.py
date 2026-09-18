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
    ingest_pending: bool = False
    ingest_available: bool | None = None
    ingest_source: str = ''
    ingest_generated_at: str = ''
    ingest_record_count: int | None = None
    ingest_event_count: int | None = None
    ingest_duplicate_record_count: int | None = None
    ingest_by_action: tuple = ()
    ingest_message: str = '통계 다시 읽기를 누르면 이미 게시된 결과를 읽습니다.'
    ingest_error: str = ''

    def begin(self, authenticated, closing):
        if not authenticated or closing or self.pending or self.ingest_pending:
            return False
        self.visible = True
        self.pending = True
        self.message = '집계 결과를 읽는 중…'
        self.error = ''
        return True

    def begin_ingest(self, authenticated, closing):
        if not authenticated or closing or self.pending or self.ingest_pending:
            return False
        self.visible = True
        self.ingest_pending = True
        self.ingest_message = '마지막 수집 통계를 읽는 중…'
        self.ingest_error = ''
        return True

    def hide(self):
        if not self.pending and not self.ingest_pending:
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
        self.ingest_pending = False
        self.ingest_available = None
        self.ingest_source = ''
        self.ingest_generated_at = ''
        self.ingest_record_count = None
        self.ingest_event_count = None
        self.ingest_duplicate_record_count = None
        self.ingest_by_action = ()
        self.ingest_message = '통계 다시 읽기를 누르면 이미 게시된 결과를 읽습니다.'
        self.ingest_error = ''

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
        if result.kind == 'ingest':
            data = result.player
            self.ingest_pending = False
            self.ingest_available = data['available']
            self.ingest_error = ''
            if not self.ingest_available:
                self.ingest_source = ''
                self.ingest_generated_at = ''
                self.ingest_record_count = None
                self.ingest_event_count = None
                self.ingest_duplicate_record_count = None
                self.ingest_by_action = ()
                reason_messages = {
                    'not_ready': '아직 수집 통계가 준비되지 않았습니다.',
                    'summary_not_created': '아직 수집 통계가 생성되지 않았습니다.',
                    'no_snapshot': '표시할 수집 통계 snapshot이 없습니다.',
                }
                reason = data.get('reason', '')
                self.ingest_message = reason_messages.get(
                    reason, '아직 수집 통계를 준비하고 있습니다.')
                return True
            self.ingest_source = data['source']
            self.ingest_generated_at = data['generated_at']
            self.ingest_record_count = data['record_count']
            self.ingest_event_count = data['event_count']
            self.ingest_duplicate_record_count = data['duplicate_record_count']
            self.ingest_by_action = tuple(data['by_action'])
            self.ingest_message = '고정 snapshot · 마지막 집계 기준'
            return True
        if result.kind == 'ingest_error':
            self.ingest_pending = False
            self.ingest_message = result.message
            self.ingest_error = result.message
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
