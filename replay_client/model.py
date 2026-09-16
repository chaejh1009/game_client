"""Replay data loading, editing helpers, and the deterministic replay engine."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReplayDataError(ValueError):
    """Raised when a JSONL file cannot be used as replay data."""


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def event_value(event: dict[str, Any], key: str, default: Any = "") -> Any:
    if key in event:
        return event[key]
    return event_payload(event).get(key, default)


def validate_event(event: Any, line_number: int | None = None) -> list[str]:
    """Return human-readable validation errors without requiring extra metadata."""

    prefix = f"line {line_number}: " if line_number is not None else ""
    errors: list[str] = []
    if not isinstance(event, dict):
        return [prefix + "event must be a JSON object"]
    event_type = event.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        errors.append(prefix + "event_type is required")
    if type(event.get('player_id')) not in (int, str) or str(event.get('player_id', '')).strip() == '':
        errors.append(prefix + 'player_id must be an integer or nonempty string')
    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append(prefix + "payload must be an object")
        return errors
    for key in ("x", "y", "coins"):
        if key not in payload or isinstance(payload[key], bool):
            errors.append(prefix + f"payload.{key} must be an integer")
        else:
            try:
                int(payload[key])
            except (TypeError, ValueError):
                errors.append(prefix + f"payload.{key} must be an integer")
    return errors


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ReplayDataError(f"파일을 찾을 수 없습니다: {path}")

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ReplayDataError(f"파일을 읽을 수 없습니다: {exc}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: JSON 오류 ({exc.msg})")
            continue
        errors.extend(validate_event(event, line_number))
        if isinstance(event, dict):
            events.append(event)

    if errors:
        details = "; ".join(errors[:3])
        more = f" 외 {len(errors) - 3}개" if len(errors) > 3 else ""
        raise ReplayDataError(f"JSONL 형식 오류: {details}{more}")
    if not events:
        raise ReplayDataError("재생할 이벤트가 없습니다.")
    return events


def save_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for index, event in enumerate(events, start=1):
        errors.extend(validate_event(event, index))
    if errors:
        details = "; ".join(errors[:3])
        more = f" 외 {len(errors) - 3}개" if len(errors) > 3 else ""
        raise ReplayDataError(f"저장할 수 없는 이벤트: {details}{more}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = "\n".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            for event in events
        )
        path.write_text(serialized + "\n", encoding="utf-8")
    except OSError as exc:
        raise ReplayDataError(f"파일을 저장할 수 없습니다: {exc}") from exc


def duplicate_event(event: dict[str, Any]) -> dict[str, Any]:
    copy_event = copy.deepcopy(event)
    copy_event["event_id"] = str(uuid.uuid4())
    payload = event_payload(copy_event)
    if "command_id" in payload:
        payload["command_id"] = str(uuid.uuid4())
    return copy_event


def make_event(events: list[dict[str, Any]], player_id: Any = 1) -> dict[str, Any]:
    """Create an editable event using the latest known state as its starting point."""

    latest = next(
        (event for event in reversed(events) if event.get("player_id") == player_id),
        None,
    )
    latest_payload = event_payload(latest or {})
    if latest is not None:
        x = _as_int(latest_payload.get("x"))
        y = _as_int(latest_payload.get("y"))
        coins = _as_int(latest_payload.get("coins"))
        version = _as_int(latest_payload.get("version"), len(events)) + 1
        room_id = latest.get("room_id", "room-01")
    else:
        x, y, coins, version, room_id = 0, 0, 0, 1, "room-01"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "event_type": "player.moved",
        "player_id": player_id,
        "room_id": room_id,
        "event_time": now,
        "payload": {
            "x": x,
            "y": y,
            "coins": coins,
            "version": version,
            "command_id": str(uuid.uuid4()),
        },
        "kafka_topic": "game.events.v1",
        "kafka_partition": 0,
        "kafka_offset": len(events),
        "kafka_key": str(player_id),
    }


def short_time(value: Any) -> str:
    if not value:
        return "--/-- --:--:--"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%m/%d %H:%M:%S")
    except ValueError:
        return text.replace("T", " ")[:19]


def event_label(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "event"))
    if event_type == "player.moved":
        return "이동"
    if event_type == "player.gathered":
        return "채굴"
    if "." in event_type:
        return event_type.rsplit(".", 1)[-1]
    return event_type


@dataclass
class ReplayEngine:
    """Apply events in file order and expose the latest state of each player."""

    events: list[dict[str, Any]]
    cursor: int = -1
    playing: bool = False
    speed: float = 1.0
    accumulator: float = 0.0
    flash: float = 0.0

    def __post_init__(self) -> None:
        self.states: dict[Any, dict[str, Any]] = {}
        self.trails: dict[Any, list[tuple[int, int]]] = {}
        self.last_event: dict[str, Any] | None = None

    @property
    def total(self) -> int:
        return len(self.events)

    @property
    def progress(self) -> float:
        if not self.events:
            return 0.0
        return max(0.0, min(1.0, (self.cursor + 1) / len(self.events)))

    @property
    def interval(self) -> float:
        return max(0.035, 0.24 / max(0.25, self.speed))

    def replace_events(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.reset()

    def reset(self) -> None:
        self.playing = False
        self.cursor = -1
        self.accumulator = 0.0
        self.flash = 0.0
        self.states.clear()
        self.trails.clear()
        self.last_event = None

    def _apply(self, index: int) -> dict[str, Any] | None:
        if index < 0 or index >= len(self.events):
            return None
        event = self.events[index]
        payload = event_payload(event)
        player_id = event.get("player_id", "?")
        x = _as_int(payload.get("x"))
        y = _as_int(payload.get("y"))
        snapshot = {
            "player_id": player_id,
            "x": x,
            "y": y,
            "coins": _as_int(payload.get("coins")),
            "version": _as_int(payload.get("version"), index + 1),
            "room_id": event.get("room_id", "room-01"),
            "event_type": event.get("event_type", "event"),
            "event_time": event.get("event_time", ""),
            "event_index": index,
        }
        self.states[player_id] = snapshot
        trail = self.trails.setdefault(player_id, [])
        point = (x, y)
        if not trail or trail[-1] != point:
            trail.append(point)
        self.cursor = index
        self.last_event = event
        self.flash = 0.45
        return event

    def step_next(self) -> dict[str, Any] | None:
        if self.cursor + 1 >= len(self.events):
            self.playing = False
            return None
        return self._apply(self.cursor + 1)

    def step_previous(self) -> dict[str, Any] | None:
        if not self.events:
            return None
        if self.cursor <= 0:
            self.reset()
            return None
        target = self.cursor - 1
        self.seek(target)
        return self.last_event

    def seek(self, index: int) -> dict[str, Any] | None:
        if not self.events:
            self.reset()
            return None
        target = max(0, min(len(self.events) - 1, int(index)))
        self.playing = False
        self.cursor = -1
        self.accumulator = 0.0
        self.states.clear()
        self.trails.clear()
        self.last_event = None
        for current in range(target + 1):
            self._apply(current)
        self.flash = 0.45
        return self.last_event

    def toggle_play(self) -> bool:
        if not self.events:
            return False
        if self.playing:
            self.playing = False
            return False
        if self.cursor >= len(self.events) - 1:
            self.reset()
        self.playing = True
        if self.cursor < 0:
            self.step_next()
        return True

    def update(self, delta_seconds: float) -> dict[str, Any] | None:
        if self.flash > 0:
            self.flash = max(0.0, self.flash - delta_seconds)
        if not self.playing or not self.events:
            return None
        self.accumulator += max(0.0, delta_seconds)
        applied = None
        while self.accumulator >= self.interval and self.playing:
            self.accumulator -= self.interval
            next_event = self.step_next()
            if next_event is not None:
                applied = next_event
        return applied
