from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .env_loader import load_project_dotenv


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required embedding env var: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class EmbeddingConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 120
    retries: int = 3

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        load_project_dotenv()
        return cls(
            base_url=_require_env("OPTSKILL_EMBED_BASE_URL"),
            api_key=_require_env("OPTSKILL_EMBED_API_KEY"),
            model=_require_env("OPTSKILL_EMBED_MODEL"),
            timeout=_env_int("OPTSKILL_EMBED_TIMEOUT", 120),
            retries=max(1, _env_int("OPTSKILL_EMBED_RETRIES", 3)),
        )


class EmbeddingCaller:
    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        self.config = config or EmbeddingConfig.from_env()

    def embed_text(self, text: str) -> List[float]:
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else []

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        payload = {
            "model": self.config.model,
            "input": [str(item) for item in texts],
        }
        response = self._post_embeddings(payload)
        data = response.get("data", [])
        if not isinstance(data, list) or len(data) != len(texts):
            raise RuntimeError(f"Unexpected embeddings response payload: {response}")
        vectors: List[List[float]] = []
        for item in data:
            if not isinstance(item, dict):
                raise RuntimeError(f"Invalid embedding item in response: {item}")
            embedding = item.get("embedding", [])
            if not isinstance(embedding, list):
                raise RuntimeError(f"Invalid embedding vector type: {type(embedding)}")
            vec = [float(v) for v in embedding]
            if not vec:
                raise RuntimeError("Received empty embedding vector.")
            vectors.append(vec)
        return vectors

    def _post_embeddings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self.config.base_url.rstrip("/") + "/embeddings"
        body = json.dumps(payload).encode("utf-8")
        last_error: Optional[Exception] = None

        for attempt in range(self.config.retries):
            req = urllib.request.Request(url=url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.config.api_key}")
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", errors="ignore")
                last_error = RuntimeError(f"Embedding HTTP error {err.code}: {detail}")
            except urllib.error.URLError as err:
                last_error = RuntimeError(f"Embedding connection error: {err}")
            except Exception as err:  # pragma: no cover - defensive
                last_error = err

            if attempt < self.config.retries - 1:
                time.sleep(1.5 * (attempt + 1))

        raise RuntimeError(f"Embedding call failed after retries: {last_error}")
