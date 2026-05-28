from __future__ import annotations

import argparse
import os
import random

from pipeline.artifacts import (
    build_layout,
    load_or_start_resume,
    prepare_trajectories,
    prepare_library,
    save_resume,
    signature,
)
from pipeline.datasets import load_entries
from pipeline.runner import run_cluster, run_learning_or_eval
from utils.runtime_logger import RuntimeLogger


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RELEASED_LIBRARY = os.path.join(BASE_DIR, "skill_library", "skill_library_learned")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OptSkills pipeline runner")
    parser.add_argument("--phase", choices=["cluster", "learning", "eval"], default="eval")
    parser.add_argument("--run-dir", type=str, default="", help="Output directory for one stage run.")
    parser.add_argument("--parent-run-dir", type=str, default="", help="Completed cluster run used to initialize learning.")
    parser.add_argument("--source-skill-library", type=str, default="", help="Input skill library for learning or eval.")
    parser.add_argument("--question", type=str, default="", help="Single problem description.")
    parser.add_argument("--answer", type=str, default="", help="Optional ground truth for a single problem.")
    parser.add_argument("--data", type=str, default="", help="Dataset JSONL path, or MIPLIB-NL directory with --miplib-nl-bench.")
    parser.add_argument("--miplib-nl-bench", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--shuffle-data", action="store_true")
    parser.add_argument("--shuffle-seed", type=int, default=42)
    parser.add_argument("--cluster-size", type=int, default=150)
    parser.add_argument("--cluster-eps", type=float, default=0.05)
    parser.add_argument("--cluster-min-samples", type=int, default=1)
    parser.add_argument("--cluster-workers", type=int, default=1)
    parser.add_argument("--analysis-workers", type=int, default=8)
    parser.add_argument("--builder-workers", type=int, default=1)
    parser.add_argument("--disable-runtime-log", action="store_true")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--agent-max-turns", type=int, default=12)
    parser.add_argument("--eval-workers", type=int, default=1)
    parser.add_argument("--archetype-fusion-alpha", type=float, default=0.55)
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.cluster_size < 0 or args.cluster_min_samples < 1:
        raise SystemExit("Cluster size must be non-negative and cluster min samples must be positive.")
    if args.cluster_workers < 1 or args.analysis_workers < 1 or args.builder_workers < 1 or args.eval_workers < 1:
        raise SystemExit("Worker counts must be positive.")
    if args.miplib_nl_bench and args.phase != "eval":
        raise SystemExit("--miplib-nl-bench supports eval only.")
    if args.phase == "cluster" and args.question:
        raise SystemExit("Cluster phase requires --data.")


def main() -> None:
    args = _build_parser().parse_args()
    _validate_args(args)

    run_dir = args.run_dir or os.path.join(BASE_DIR, "outputs", args.phase)
    layout = build_layout(run_dir)
    os.makedirs(layout.root, exist_ok=True)
    os.environ["OPTSKILL_TOOL_ARTIFACT_DIR"] = os.path.join(layout.logs, "tool_outputs")
    os.environ["OPTSKILL_RUN_CODE_CWD_BASE"] = os.path.join(layout.logs, "tool_workspaces")

    preliminary_library = (
        layout.skill_library if args.phase in {"cluster", "learning"}
        else os.path.abspath(args.source_skill_library or DEFAULT_RELEASED_LIBRARY)
    )
    run_signature = signature(args, preliminary_library)
    state = load_or_start_resume(args, layout, run_signature)
    prepare_trajectories(args, layout, state)
    active_library = prepare_library(args, layout, state, DEFAULT_RELEASED_LIBRARY)

    logger = RuntimeLogger(log_dir=layout.logs, run_name=f"optskill_{args.phase}", enabled=not args.disable_runtime_log)
    logger.log(component="main", event="run_start", message="run start", data={"argv": vars(args), "layout": layout.__dict__})
    try:
        entries = load_entries(args.question, args.answer, args.data, args.miplib_nl_bench)
        if args.phase == "cluster":
            run_cluster(args, layout, state, entries, logger)
        else:
            if args.shuffle_data and args.phase == "eval":
                random.Random(args.shuffle_seed).shuffle(entries)
            run_learning_or_eval(args, layout, state, entries, logger, active_library)
        state["status"] = "completed"
        save_resume(layout, state)
        print(f"[main] completed phase={args.phase} trajectories={layout.trajectories}", flush=True)
        logger.log(component="main", event="run_done", message="run completed", data={"records": state["written_count"]})
    except Exception as err:
        state["status"] = "failed"
        state["error"] = {"type": type(err).__name__, "message": str(err)}
        save_resume(layout, state)
        logger.log(component="main", event="run_error", message=str(err), level="ERROR")
        raise
    finally:
        logger.close()


if __name__ == "__main__":
    main()
