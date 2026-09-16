"""Configuration for the local replay client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    base_dir: Path
    data_path: Path
    save_path: Path
    asset_dir: Path
    window_width: int = 1440
    window_height: int = 900
    tile_size: int = 34
    map_columns: int = 20
    map_rows: int = 15

    @classmethod
    def load(cls) -> "Config":
        config_path = BASE_DIR / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))

        def resolve(value: str, default: str) -> Path:
            raw = value if isinstance(value, str) and value else default
            path = Path(raw).expanduser()
            return path.resolve() if path.is_absolute() else (BASE_DIR / path).resolve()

        width = int(data.get("window_width", 1440))
        height = int(data.get("window_height", 900))
        tile_size = int(data.get("tile_size", 34))
        if width < 1280 or height < 820 or tile_size < 24:
            raise ValueError("replay_client 창은 최소 1280×820, 타일은 24px 이상이어야 합니다.")
        return cls(
            base_dir=BASE_DIR,
            data_path=resolve(data.get("data_path", ""), "../../data-replay/raw/game-events.jsonl"),
            save_path=resolve(data.get("save_path", ""), "replay-edited.jsonl"),
            asset_dir=resolve(data.get("asset_dir", ""), "../client/assets"),
            window_width=width,
            window_height=height,
            tile_size=tile_size,
            map_columns=int(data.get("map_columns", 20)),
            map_rows=int(data.get("map_rows", 15)),
        )

