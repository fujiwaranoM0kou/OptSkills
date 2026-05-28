from __future__ import annotations

import copy
import json
import os
import random
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from agents.agent_loop import AgentLoop
from pipeline.artifacts import RunLayout, load_json, save_learning_checkpoint, save_resume
from pipeline.datasets import select_entries
from skill_core.skill_manager import SkillManager
from utils.runtime_logger import RuntimeLogger


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _build_loop(args: Any, logger: RuntimeLogger, library: str) -> AgentLoop:
    return AgentLoop(
        skill_library_dir=library,
        archetype_fusion_alpha=args.archetype_fusion_alpha,
        agent_max_turns=args.agent_max_turns,
        analysis_workers=args.analysis_workers,
        builder_workers=args.builder_workers,
        logger=logger,
    )


def _record(phase: str, pending: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "phase": phase,
        "index": pending["row"].get("index", pending["idx"]),
        "sample_key": pending["sample_key"],
        "sample_id": pending["sample_id"],
        "question": pending["question"],
        "answer": pending["answer"],
    }
    payload.update(result)
    if isinstance(pending.get("fc_problem_context"), dict):
        payload["miplib_nl_context"] = pending["fc_problem_context"]
    return payload


def _pending(entries: List[Dict[str, Any]], state: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    processed = set(str(key) for key in state.get("processed_sample_keys", []))
    pending = [item for item in entries if str(item["sample_key"]) not in processed]
    return pending[: max(0, limit - len(processed))] if limit > 0 else pending


def _commit(layout: RunLayout, state: Dict[str, Any], record: Dict[str, Any]) -> None:
    _append_jsonl(layout.trajectories, record)
    state.setdefault("processed_sample_keys", []).append(record["sample_key"])
    state["written_count"] = int(state.get("written_count", 0)) + 1
    save_resume(layout, state)


def _commit_learning(layout: RunLayout, state: Dict[str, Any], record: Dict[str, Any]) -> None:
    _append_jsonl(layout.trajectories, record)
    next_state = copy.deepcopy(state)
    next_state.setdefault("processed_sample_keys", []).append(record["sample_key"])
    next_state["written_count"] = int(next_state.get("written_count", 0)) + 1
    # The checkpoint copies the updated library before making this sample
    # visible in resume.json, so resume never advances without its skill state.
    save_learning_checkpoint(layout, next_state)
    state.clear()
    state.update(next_state)


def run_cluster(args: Any, layout: RunLayout, state: Dict[str, Any], entries: List[Dict[str, Any]], logger: RuntimeLogger) -> None:
    if not isinstance(state.get("split"), dict):
        ordered = list(entries)
        if args.shuffle_data:
            random.Random(args.shuffle_seed).shuffle(ordered)
        keys = [str(item["sample_key"]) for item in ordered]
        state["split"] = {
            "ordered_sample_keys": keys,
            "cluster_sample_keys": keys[: args.cluster_size],
            "learning_sample_keys": keys[args.cluster_size :],
        }
        save_resume(layout, state)
    selected = select_entries(entries, state["split"]["cluster_sample_keys"])
    pending = _pending(selected, state, args.limit)
    SkillManager(layout.skill_library)
    write_lock = threading.Lock()
    local = threading.local()

    def collect(item: Dict[str, Any]) -> Dict[str, Any]:
        if not hasattr(local, "loop"):
            local.loop = _build_loop(args, logger, layout.skill_library)
        result = local.loop.cluster_collect(item["question"], item["answer"], args.top_k, args.timeout, item["sample_id"])
        return _record("cluster", item, result)

    with ThreadPoolExecutor(max_workers=args.cluster_workers) as pool:
        futures = [pool.submit(collect, item) for item in pending]
        for future in as_completed(futures):
            record = future.result()
            with write_lock:
                _commit(layout, state, record)

    if bool(state.get("cluster_build_complete", False)):
        return

    records: List[Dict[str, Any]] = []
    if os.path.exists(layout.trajectories):
        with open(layout.trajectories, "r", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
    staging_library = f"{layout.skill_library}.building"
    if os.path.isdir(staging_library):
        shutil.rmtree(staging_library)
    builder = _build_loop(args, logger, staging_library)
    build_summary = builder.cluster_build(records, args.cluster_eps, args.cluster_min_samples)
    if os.path.isdir(layout.skill_library):
        shutil.rmtree(layout.skill_library)
    os.replace(staging_library, layout.skill_library)
    state["cluster_build"] = build_summary
    state["cluster_build_complete"] = True
    save_resume(layout, state)


def run_learning_or_eval(args: Any, layout: RunLayout, state: Dict[str, Any], entries: List[Dict[str, Any]], logger: RuntimeLogger, active_library: str) -> None:
    if args.phase == "learning" and args.parent_run_dir:
        parent = load_json(os.path.join(os.path.abspath(args.parent_run_dir), "resume.json"))
        entries = select_entries(entries, parent.get("split", {}).get("learning_sample_keys", []))
    pending = _pending(entries, state, args.limit)

    if args.phase == "learning":
        loop = _build_loop(args, logger, active_library)
        for item in pending:
            result = loop.run(
                problem_description=item["question"],
                ground_truth=item["answer"],
                top_k=args.top_k,
                timeout=args.timeout,
                enable_self_learn=True,
                sample_id=item["sample_id"],
                fc_problem_context=item.get("fc_problem_context"),
            )
            _commit_learning(layout, state, _record("learning", item, result))
        return

    lock = threading.Lock()
    local = threading.local()

    def evaluate(item: Dict[str, Any]) -> Dict[str, Any]:
        if not hasattr(local, "loop"):
            local.loop = _build_loop(args, logger, active_library)
        result = local.loop.run(
            problem_description=item["question"],
            ground_truth=item["answer"],
            top_k=args.top_k,
            timeout=args.timeout,
            enable_self_learn=False,
            sample_id=item["sample_id"],
            use_eval_extractor_prompt=True,
            fc_problem_context=item.get("fc_problem_context"),
        )
        return _record("eval", item, result)

    with ThreadPoolExecutor(max_workers=args.eval_workers) as pool:
        futures = [pool.submit(evaluate, item) for item in pending]
        for future in as_completed(futures):
            with lock:
                _commit(layout, state, future.result())
