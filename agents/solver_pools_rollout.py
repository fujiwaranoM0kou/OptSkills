from __future__ import annotations

import json
import os
import re
import copy
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from agents.base import BaseAgent
from prompts.solver_prompts import SOLVER_POOL_SELECTION_PROMPT
from utils.extract_json import extract_json
from utils.runtime_logger import RuntimeLogger


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read().strip()


def _read_title(markdown: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def _candidate_sort_key(item: Dict[str, Any]) -> int:
    candidate_id = str(item.get("candidate_id", "")).strip()
    match = re.search(r"(\d+)$", candidate_id)
    if not match:
        return 10_000
    return int(match.group(1))


class SolverPoolsRolloutAgent(BaseAgent):
    def __init__(
        self,
        solvers_root: Optional[str] = None,
        logger: Optional[RuntimeLogger] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(system_prompt="You are a practical optimization backend selector.", **kwargs)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.solvers_root = solvers_root or os.path.join(base_dir, "lists", "solvers")
        self.logger = logger
        self._catalog_cache: Optional[List[Dict[str, Any]]] = None
        self._doc_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    def _log(
        self,
        event: str,
        message: str = "",
        *,
        sample_id: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.logger is None:
            return
        self.logger.log(
            component="solver_pool",
            event=event,
            message=message,
            sample_id=sample_id,
            data=data or {},
        )

    def discover_solver_catalog(self) -> List[Dict[str, Any]]:
        with self._cache_lock:
            if self._catalog_cache is not None:
                return copy.deepcopy(self._catalog_cache)

        catalog: List[Dict[str, Any]] = []
        if not os.path.isdir(self.solvers_root):
            return catalog

        for framework in sorted(os.listdir(self.solvers_root)):
            framework_path = os.path.join(self.solvers_root, framework)
            if not os.path.isdir(framework_path):
                continue

            for backend in sorted(os.listdir(framework_path)):
                backend_path = os.path.join(framework_path, backend)
                if not os.path.isdir(backend_path):
                    continue
                readme_path = os.path.join(backend_path, "README.md")
                if not os.path.exists(readme_path):
                    continue

                readme_text = _read_text(readme_path)
                solver_id = f"{framework}_{backend}".lower()
                catalog.append(
                    {
                        "solver_id": solver_id,
                        "framework": framework,
                        "backend": backend,
                        "title": _read_title(readme_text),
                        "readme_path": readme_path,
                    }
                )

        with self._cache_lock:
            self._catalog_cache = copy.deepcopy(catalog)
        return catalog

    def _read_doc_cached(self, readme_path: str) -> str:
        path = str(readme_path).strip()
        if not path or not os.path.exists(path):
            return ""
        mtime = os.path.getmtime(path)
        with self._cache_lock:
            entry = self._doc_cache.get(path)
            if isinstance(entry, dict) and float(entry.get("mtime", -1.0)) == float(mtime):
                return str(entry.get("text", ""))
        text = _read_text(path)
        with self._cache_lock:
            self._doc_cache[path] = {"mtime": float(mtime), "text": text}
        return text

    def _enrich_selected_with_docs(self, selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for item in selected:
            payload = dict(item)
            readme_path = str(payload.get("readme_path", "")).strip()
            payload["backend_doc"] = self._read_doc_cached(readme_path) if readme_path else ""
            enriched.append(payload)
        return enriched

    def select_solver_pool(
        self,
        problem_description: str,
        ingredient_slots: Dict[str, List[str]],
        top_k: int,
        catalog: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        llm_catalog = [
            {
                "solver_id": str(item.get("solver_id", "")),
                "framework": str(item.get("framework", "")),
                "backend": str(item.get("backend", "")),
            }
            for item in catalog
        ]
        prompt = SOLVER_POOL_SELECTION_PROMPT.format(
            problem_description=problem_description,
            keywords=json.dumps(ingredient_slots, ensure_ascii=False, indent=2),
            top_k=top_k,
            solver_catalog=json.dumps(llm_catalog, ensure_ascii=False, indent=2),
        )
        raw = self.call_llm(prompt)
        parsed = extract_json(raw, default={})

        by_id: Dict[str, Dict[str, Any]] = {
            str(item.get("solver_id", "")).strip(): item for item in catalog
        }
        selected: List[Dict[str, Any]] = []
        seen = set()

        if isinstance(parsed, dict):
            for item in parsed.get("selected", []):
                if not isinstance(item, dict):
                    continue
                solver_id = str(item.get("solver_id", "")).strip()
                if not solver_id or solver_id in seen or solver_id not in by_id:
                    continue
                payload = dict(by_id[solver_id])
                payload["reason"] = str(item.get("reason", "")).strip()
                selected.append(payload)
                seen.add(solver_id)
                if len(selected) >= top_k:
                    break

        return {
            "prompt": prompt,
            "raw": raw,
            "parsed": parsed if isinstance(parsed, dict) else {},
            "selected": selected,
        }

    def rollout(
        self,
        problem_description: str,
        ingredient_slots: Dict[str, List[str]],
        run_candidate: Callable[[Dict[str, Any]], Dict[str, Any]],
        top_k: int = 3,
        sample_id: str = "",
    ) -> Dict[str, Any]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        print("[solver_pool] discover solver catalog start", flush=True)
        self._log("catalog_start", sample_id=sample_id)
        catalog = self.discover_solver_catalog()
        print(f"[solver_pool] discover solver catalog done count={len(catalog)}", flush=True)
        self._log("catalog_done", sample_id=sample_id, data={"count": len(catalog)})
        print("[solver_pool] LLM selection start", flush=True)
        self._log("selection_start", sample_id=sample_id, data={"top_k": top_k})
        selection = self.select_solver_pool(
            problem_description=problem_description,
            ingredient_slots=ingredient_slots,
            top_k=top_k,
            catalog=catalog,
        )
        print(
            f"[solver_pool] LLM selection done selected={len(selection.get('selected', [])) if isinstance(selection, dict) else 0}",
            flush=True,
        )
        self._log(
            "selection_done",
            sample_id=sample_id,
            data={"selected": len(selection.get("selected", [])) if isinstance(selection, dict) else 0},
        )
        selected = self._enrich_selected_with_docs(selection.get("selected", []))
        if not isinstance(selected, list):
            selected = []

        candidates: List[Dict[str, Any]] = []
        if selected:
            with ThreadPoolExecutor(max_workers=min(len(selected), top_k)) as executor:
                futures = {}
                for idx, item in enumerate(selected, start=1):
                    payload = dict(item)
                    payload["candidate_rank"] = idx
                    print(
                        f"[solver_pool] submit candidate rank={idx} solver_id={payload.get('solver_id', '')}",
                        flush=True,
                    )
                    self._log(
                        "candidate_submitted",
                        sample_id=sample_id,
                        data={"rank": idx, "solver_id": payload.get("solver_id", "")},
                    )
                    future = executor.submit(run_candidate, payload)
                    futures[future] = payload

                for future in as_completed(futures):
                    selected_item = futures[future]
                    try:
                        result = future.result()
                    except Exception as err:  # pragma: no cover - defensive
                        raise RuntimeError(
                            f"rollout worker failed for {selected_item.get('solver_id', '')}: {err}"
                        ) from err
                    if not isinstance(result, dict):
                        raise TypeError("run_candidate must return dict")

                    if not result.get("candidate_id"):
                        result["candidate_id"] = (
                            f"candidate_{selected_item.get('candidate_rank', len(candidates) + 1)}"
                        )
                    if not result.get("solver_id"):
                        result["solver_id"] = str(selected_item.get("solver_id", ""))
                    result["framework"] = str(selected_item.get("framework", ""))
                    result["backend"] = str(selected_item.get("backend", ""))
                    result["backend_doc"] = str(selected_item.get("backend_doc", ""))
                    result["selection_reason"] = str(selected_item.get("reason", ""))
                    candidates.append(result)
                    print(
                        f"[solver_pool] candidate completed rank={selected_item.get('candidate_rank', '')} "
                        f"solver_id={selected_item.get('solver_id', '')}",
                        flush=True,
                    )
                    self._log(
                        "candidate_completed",
                        sample_id=sample_id,
                        data={
                            "rank": selected_item.get("candidate_rank", ""),
                            "solver_id": selected_item.get("solver_id", ""),
                        },
                    )

        candidates = sorted(candidates, key=_candidate_sort_key)
        stored_selection = dict(selection)
        stored_selection.pop("prompt", None)
        return {
            "selection": stored_selection,
            "candidates": candidates,
        }
