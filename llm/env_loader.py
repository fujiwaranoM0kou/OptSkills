from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Optional

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    _load_dotenv = None

_LOCK = Lock()
_LOADED_PATH: Optional[str] = None


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_project_dotenv(project_root: Optional[str] = None) -> str:
    global _LOADED_PATH
    with _LOCK:
        if _LOADED_PATH:
            return _LOADED_PATH

        root = Path(project_root).resolve() if project_root else _resolve_project_root()
        env_path = root / ".env"
        if env_path.exists():
            if _load_dotenv is not None:
                _load_dotenv(dotenv_path=str(env_path), override=False, encoding="utf-8")
            else:
                _manual_load_dotenv(env_path)

        _LOADED_PATH = str(env_path)
        return _LOADED_PATH


def _manual_load_dotenv(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if value and ((value[0] == value[-1]) and value[0] in {"'", '"'}):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value

