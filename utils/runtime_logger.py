from __future__ import annotations

import json
import os
import time
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class RuntimeLogger:
    def __init__(
        self,
        log_dir: str,
        run_name: str = "run",
        enabled: bool = True,
    ) -> None:
        self.enabled = bool(enabled)
        self.log_dir = os.path.abspath(log_dir)
        self.run_name = str(run_name).strip() or "run"
        self.run_id = f"{self.run_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self._start_ts = time.time()
        self._event_count = 0
        self._sample_count = 0
        self._error_count = 0
        self._lock = threading.Lock()

        os.makedirs(self.log_dir, exist_ok=True)
        self.events_path = os.path.join(self.log_dir, f"{self.run_id}.events.jsonl")
        self.summary_path = os.path.join(self.log_dir, f"{self.run_id}.summary.json")

    def log(
        self,
        *,
        component: str,
        event: str,
        message: str = "",
        sample_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
    ) -> None:
        if not self.enabled:
            return
        payload = {
            "ts": _utc_now(),
            "run_id": self.run_id,
            "level": str(level).upper(),
            "component": str(component).strip(),
            "event": str(event).strip(),
            "message": str(message),
            "sample_id": str(sample_id).strip(),
            "data": data if isinstance(data, dict) else {},
        }
        with self._lock:
            with open(self.events_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._event_count += 1
            if payload["event"] == "sample_start":
                self._sample_count += 1
            if payload["level"] == "ERROR":
                self._error_count += 1

    def close(self) -> None:
        if not self.enabled:
            return
        summary = {
            "run_id": self.run_id,
            "started_at": datetime.utcfromtimestamp(self._start_ts).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": _utc_now(),
            "duration_s": round(time.time() - self._start_ts, 3),
            "events": self._event_count,
            "samples": self._sample_count,
            "errors": self._error_count,
            "events_path": self.events_path,
        }
        with self._lock:
            with open(self.summary_path, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)
