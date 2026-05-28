from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class RunLayout:
    root: str
    trajectories: str
    resume: str
    logs: str
    skill_library: str
    checkpoints: str


def build_layout(run_dir: str) -> RunLayout:
    root = os.path.abspath(run_dir)
    return RunLayout(
        root=root,
        trajectories=os.path.join(root, "trajectories.jsonl"),
        resume=os.path.join(root, "resume.json"),
        logs=os.path.join(root, "runtime_logs"),
        skill_library=os.path.join(root, "skill_library"),
        checkpoints=os.path.join(root, "checkpoints"),
    )


def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _atomic_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def save_resume(layout: RunLayout, state: Dict[str, Any]) -> None:
    _atomic_json(layout.resume, state)


def prepare_trajectories(args: Any, layout: RunLayout, state: Dict[str, Any]) -> None:
    has_resume_state = bool(args.resume and os.path.exists(layout.resume))
    if not has_resume_state:
        if os.path.exists(layout.trajectories):
            os.remove(layout.trajectories)
        return
    if not os.path.exists(layout.trajectories):
        if state.get("processed_sample_keys"):
            raise RuntimeError("Resume file records completed samples but trajectories.jsonl is missing.")
        return
    committed = set(str(item) for item in state.get("processed_sample_keys", []))
    kept = []
    seen = set()
    with open(layout.trajectories, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                break
            key = str(row.get("sample_key", ""))
            if key in committed and key not in seen:
                kept.append(row)
                seen.add(key)
    missing = committed - seen
    if missing:
        raise RuntimeError("Resume state refers to trajectory records that cannot be recovered.")
    tmp = f"{layout.trajectories}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, layout.trajectories)


def signature(args: Any, library: str) -> Dict[str, Any]:
    return {
        "phase": args.phase,
        "data_path": os.path.abspath(args.data) if args.data else "",
        "skill_library": os.path.abspath(library),
        "parent_run_dir": os.path.abspath(args.parent_run_dir) if args.parent_run_dir else "",
        "source_skill_library": os.path.abspath(args.source_skill_library) if args.source_skill_library else "",
        "cluster_size": int(args.cluster_size),
        "cluster_eps": float(args.cluster_eps),
        "cluster_min_samples": int(args.cluster_min_samples),
        "cluster_workers": int(args.cluster_workers),
        "analysis_workers": int(args.analysis_workers),
        "builder_workers": int(args.builder_workers),
        "eval_workers": int(args.eval_workers),
        "top_k": int(args.top_k),
        "timeout": int(args.timeout),
        "agent_max_turns": int(args.agent_max_turns),
        "archetype_fusion_alpha": float(args.archetype_fusion_alpha),
    }


def load_or_start_resume(args: Any, layout: RunLayout, run_signature: Dict[str, Any]) -> Dict[str, Any]:
    if args.resume and os.path.exists(layout.resume):
        state = load_json(layout.resume)
        if state.get("signature") != run_signature:
            raise RuntimeError("Resume state does not match the requested run configuration.")
        state["status"] = "running"
        state.pop("error", None)
        return state
    return {
        "phase": args.phase,
        "status": "running",
        "signature": run_signature,
        "data_path": os.path.abspath(args.data) if args.data else "",
        "processed_sample_keys": [],
        "written_count": 0,
    }


def _replace_tree(source: str, destination: str) -> None:
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def prepare_library(args: Any, layout: RunLayout, state: Dict[str, Any], default_library: str) -> str:
    has_resume_state = bool(args.resume and os.path.exists(layout.resume))
    if args.phase == "eval":
        source = os.path.abspath(args.source_skill_library or default_library)
        if not os.path.isdir(source):
            raise RuntimeError(f"Missing evaluation skill library: {source}")
        return source
    os.makedirs(layout.root, exist_ok=True)
    if args.phase == "cluster":
        if not has_resume_state and os.path.isdir(layout.skill_library):
            shutil.rmtree(layout.skill_library)
        os.makedirs(layout.skill_library, exist_ok=True)
        return layout.skill_library
    if has_resume_state and state.get("last_checkpoint"):
        checkpoint_library = os.path.join(str(state["last_checkpoint"]), "skill_library")
        if os.path.isdir(checkpoint_library):
            _replace_tree(checkpoint_library, layout.skill_library)
            return layout.skill_library
    no_committed_learning_checkpoint = (
        has_resume_state
        and int(state.get("written_count", 0)) == 0
        and not state.get("last_checkpoint")
    )
    if not os.path.isdir(layout.skill_library) or not has_resume_state or no_committed_learning_checkpoint:
        source = ""
        if args.parent_run_dir:
            source = os.path.join(os.path.abspath(args.parent_run_dir), "skill_library")
        elif args.source_skill_library:
            source = os.path.abspath(args.source_skill_library)
        else:
            source = default_library
        if not os.path.isdir(source):
            raise RuntimeError(f"Missing learning source skill library: {source}")
        _replace_tree(source, layout.skill_library)
    return layout.skill_library


def save_learning_checkpoint(layout: RunLayout, state: Dict[str, Any]) -> str:
    checkpoint = os.path.join(layout.checkpoints, f"checkpoint_{int(state['written_count']):05d}")
    os.makedirs(layout.checkpoints, exist_ok=True)
    _replace_tree(layout.skill_library, os.path.join(checkpoint, "skill_library"))
    state["last_checkpoint"] = checkpoint
    save_resume(layout, state)
    return checkpoint
