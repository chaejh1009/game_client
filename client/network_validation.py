"""Pure validation and safe projections for HTTP and WebSocket data."""
import json

import aiohttp

from messages import DELIVERY_FIELDS, PLAYER_FIELDS
from network_errors import Failure


class ResponseValidator:
    def decode_ws_message(self, message, close_code: int | None) -> dict:
        if message.type != aiohttp.WSMsgType.TEXT:
            raise Failure('게임 연결이 종료되었습니다.', close_code == 4401)
        if len(message.data) > 65536:
            raise Failure('게임 응답이 너무 큽니다.')
        try:
            data = json.loads(message.data)
        except (ValueError, UnicodeError):
            raise Failure('게임 응답 형식이 올바르지 않습니다.') from None
        if not isinstance(data, dict):
            raise Failure('게임 응답은 객체여야 합니다.')
        return data

    def validate_snapshot(self, data: dict) -> tuple[dict, ...]:
        raw_players = data.get('players')
        if not isinstance(raw_players, list) or len(raw_players) > 100:
            raise Failure('게임 snapshot의 players 형식을 확인하세요.')
        players = tuple(self.validate_player(player) for player in raw_players)
        ids = [player['player_id'] for player in players]
        if len(ids) != len(set(ids)):
            raise Failure('게임 snapshot에 중복 player가 있습니다.')
        return players

    def safe_state_message(self, player: dict,
                           command_id: str | None = None) -> dict:
        safe = {'type': 'state', **player}
        if isinstance(command_id, str) and len(command_id) <= 80:
            safe['command_id'] = command_id
        return safe

    def safe_error_message(self, data: dict) -> dict:
        safe = {'type': 'error', 'code': str(data.get('code', 'unknown'))[:80]}
        command_id = data.get('command_id')
        if isinstance(command_id, str) and len(command_id) <= 80:
            safe['command_id'] = command_id
        return safe

    def command_failure(self, data: dict) -> Failure:
        messages = {
            'too_fast': '게임 명령은 모두 합쳐 초당 최대 5개입니다.',
            'outside_map': '맵 바깥으로 이동할 수 없습니다.',
            'invalid_direction': '올바르지 않은 이동 방향입니다.',
            'not_at_gather_tile': '코인은 채굴 지점 (2, 2)에서만 채굴할 수 있습니다.',
            'not_at_train_tile': '개인 수련은 수련 타일 (3, 2)에서만 가능합니다.',
            'unknown_action': '올바르지 않은 게임 명령입니다.',
        }
        return Failure(messages.get(data.get('code'), '게임 명령을 처리하지 못했습니다.'))

    def validate_player(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise Failure('player 응답은 객체여야 합니다.')
        validated = {}
        for key in PLAYER_FIELDS:
            value = data.get(key)
            if key in ('player_id', 'room_id'):
                valid = type(value) is int or (isinstance(value, str) and len(value) <= 80)
            else:
                valid = type(value) is int
            if not valid:
                raise Failure('player 응답의 필수 필드 또는 자료형을 확인하세요.')
            validated[key] = value
        return validated

    def validate_delivery(self, data: dict) -> dict:
        source = data.get('source')
        if not isinstance(source, str) or not source or len(source) > 80:
            raise Failure('delivery 응답의 source를 확인하세요.')
        validated = {'source': source}
        for key in DELIVERY_FIELDS[1:]:
            value = data.get(key)
            if type(value) is not int or value < 0:
                raise Failure('delivery 응답의 카운트 필드를 확인하세요.')
            validated[key] = value
        return validated

    def _validate_analytics_rows(self, rows, label_key: str,
                                 field_name: str) -> tuple:
        if not isinstance(rows, list) or len(rows) > 100:
            raise Failure(f'analytics 응답의 {field_name} 형식을 확인하세요.')
        validated = []
        for row in rows:
            if not isinstance(row, dict):
                raise Failure(f'analytics 응답의 {field_name} 행을 확인하세요.')
            label = row.get(label_key)
            count = row.get('count')
            label_ok = isinstance(label, str) and bool(label) and len(label) <= 80
            if label_key == 'room_id':
                label_ok = label_ok or type(label) is int
            if not label_ok or type(count) is not int or count < 0:
                raise Failure(f'analytics 응답의 {field_name} 행을 확인하세요.')
            validated.append({label_key: label, 'count': count})
        return tuple(validated)

    def validate_analytics(self, data: dict) -> dict:
        available = data.get('available')
        if type(available) is not bool:
            raise Failure('analytics 응답의 available을 확인하세요.')
        if not available:
            return {'available': False}

        source_topic = data.get('source_topic')
        source_kind = data.get('source_kind')
        raw_record_count = data.get('raw_record_count')
        summary = data.get('summary')
        for field_name, value in (
                ('source_topic', source_topic), ('source_kind', source_kind)):
            if not isinstance(value, str) or not value or len(value) > 160:
                raise Failure(f'analytics 응답의 {field_name}을 확인하세요.')
        if type(raw_record_count) is not int or raw_record_count < 0:
            raise Failure('analytics 응답의 raw_record_count를 확인하세요.')
        if not isinstance(summary, dict):
            raise Failure('analytics 응답의 summary를 확인하세요.')

        generated_at = summary.get('generated_at')
        event_count = summary.get('event_count')
        if not isinstance(generated_at, str) or not generated_at or len(generated_at) > 120:
            raise Failure('analytics summary의 generated_at을 확인하세요.')
        if type(event_count) is not int or event_count < 0:
            raise Failure('analytics summary의 event_count를 확인하세요.')
        by_action = self._validate_analytics_rows(
            summary.get('by_action'), 'action_label', 'summary.by_action')
        by_room = self._validate_analytics_rows(
            summary.get('by_room'), 'room_id', 'summary.by_room')
        return {
            'available': True,
            'source_topic': source_topic,
            'source_kind': source_kind,
            'raw_record_count': raw_record_count,
            'summary': {
                'generated_at': generated_at,
                'event_count': event_count,
                'by_action': list(by_action),
                'by_room': list(by_room),
            },
        }

    def validate_ingest(self, data: dict) -> dict:
        """Project the published Kafka-ingest snapshot into display-safe fields."""
        available = data.get('available')
        if type(available) is not bool:
            raise Failure('ingest 응답의 available을 확인하세요.')
        if not available:
            reason = data.get('reason', '')
            if not isinstance(reason, str) or len(reason) > 160:
                raise Failure('ingest 응답의 reason을 확인하세요.')
            return {'available': False, 'reason': reason}

        source = data.get('source')
        generated_at = data.get('generated_at')
        if not isinstance(source, str) or not source or len(source) > 160:
            raise Failure('ingest 응답의 source를 확인하세요.')
        if (not isinstance(generated_at, str) or not generated_at
                or len(generated_at) > 120):
            raise Failure('ingest 응답의 generated_at을 확인하세요.')
        counts = {}
        for field_name in ('record_count', 'event_count', 'duplicate_record_count'):
            value = data.get(field_name)
            if type(value) is not int or value < 0:
                raise Failure(f'ingest 응답의 {field_name}을 확인하세요.')
            counts[field_name] = value
        rows = data.get('by_action')
        if not isinstance(rows, list) or len(rows) > 100:
            raise Failure('ingest 응답의 by_action 형식을 확인하세요.')
        by_action = []
        for row in rows:
            if not isinstance(row, dict):
                raise Failure('ingest 응답의 by_action 행을 확인하세요.')
            event_type = row.get('event_type')
            count = row.get('count')
            if (not isinstance(event_type, str) or not event_type
                    or len(event_type) > 80 or type(count) is not int or count < 0):
                raise Failure('ingest 응답의 by_action 행을 확인하세요.')
            by_action.append({'event_type': event_type, 'count': count})
        return {
            'available': True,
            'source': source,
            'generated_at': generated_at,
            **counts,
            'by_action': by_action,
        }

    def validate_ingest_analytics(self, data: dict) -> dict:
        return self.validate_ingest(data)

    def validate_history(self, data: dict) -> dict:
        scope = data.get('scope')
        limit = data.get('limit')
        events = data.get('events')
        if scope != 'current-player':
            raise Failure('history 응답의 scope를 확인하세요.')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Failure('history 응답의 limit을 확인하세요.')
        if not isinstance(events, list) or len(events) > limit:
            raise Failure('history 응답의 events 형식을 확인하세요.')
        validated_events = []
        for event in events:
            if not isinstance(event, dict):
                raise Failure('history 응답의 event 형식을 확인하세요.')
            schema_version = event.get('schema_version')
            event_id = event.get('event_id')
            event_type = event.get('event_type')
            player_id = event.get('player_id')
            room_id = event.get('room_id')
            event_time = event.get('event_time')
            payload = event.get('payload')
            if type(schema_version) is not int or schema_version < 1:
                raise Failure('history event의 schema_version을 확인하세요.')
            if not isinstance(event_id, str) or not event_id or len(event_id) > 80:
                raise Failure('history event의 event_id를 확인하세요.')
            if not isinstance(event_type, str) or not event_type or len(event_type) > 80:
                raise Failure('history event의 event_type을 확인하세요.')
            for name, value in (('player_id', player_id), ('room_id', room_id)):
                valid = type(value) is int or (
                    isinstance(value, str) and bool(value) and len(value) <= 80)
                if not valid:
                    raise Failure(f'history event의 {name}를 확인하세요.')
            if not isinstance(event_time, str) or not event_time or len(event_time) > 120:
                raise Failure('history event의 event_time을 확인하세요.')
            if not isinstance(payload, dict):
                raise Failure('history event의 payload를 확인하세요.')
            safe_payload = {}
            for key in ('x', 'y', 'coins', 'version'):
                value = payload.get(key)
                if type(value) is not int:
                    raise Failure(f'history event payload의 {key}를 확인하세요.')
                safe_payload[key] = value
            transition = payload.get('transition')
            safe_transition = None
            if transition is not None:
                if not isinstance(transition, dict):
                    raise Failure('history event payload의 transition을 확인하세요.')
                step = transition.get('step')
                reward = transition.get('reward')
                if type(step) is not int or step < 1:
                    raise Failure('history transition의 step을 확인하세요.')
                if isinstance(reward, bool) or not isinstance(reward, (int, float)):
                    raise Failure('history transition의 reward를 확인하세요.')
                safe_transition = {'step': step, 'reward': reward}
            safe_payload['transition'] = safe_transition
            validated_events.append({
                'schema_version': schema_version,
                'event_id': event_id,
                'event_type': event_type,
                'player_id': player_id,
                'room_id': room_id,
                'event_time': event_time,
                'payload': safe_payload,
            })
        return {'scope': scope, 'limit': limit, 'events': validated_events}
