"""Append-only local audit records for commands that create or restore files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import default_data_dir


class AuditLog:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or default_data_dir() / "audit.jsonl"

    def record(self, event: str, details: Dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def records(self, limit: int = 50) -> List[Dict[str, object]]:
        if not self.path.exists():
            return []
        records: List[Dict[str, object]] = []
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
        return records[-max(0, limit) :]
