from __future__ import annotations

import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from skill_core.clustering import dbscan_cosine_vectors
from skill_core.ingredients import SLOTS, clean_ingredient_slots, update_ingredient_reference
from skill_core.skill_builder import SkillBuilder
from skill_core.trajectory_analyzer import TrajectoryAnalyzer


class ClusterBuilder:
    def __init__(self, builder: SkillBuilder, analyzer: TrajectoryAnalyzer, builder_workers: int = 1) -> None:
        self.builder = builder
        self.analyzer = analyzer
        self.builder_workers = max(1, int(builder_workers))

    def build(self, collected_samples: List[Dict[str, Any]], dbscan_eps: float, dbscan_min_samples: int) -> Dict[str, Any]:
        samples = [item for item in collected_samples if isinstance(item, dict)]
        eligible = [item for item in samples if bool(item.get("eligible", False))]
        valid_samples: List[Dict[str, Any]] = []
        vectors: List[List[float]] = []
        for item in eligible:
            vector = item.get("query_embedding", [])
            if isinstance(vector, list) and vector:
                vectors.append([float(value) for value in vector])
                valid_samples.append(item)
        payload: Dict[str, Any] = {
            "dbscan_eps": float(dbscan_eps),
            "dbscan_min_samples": int(dbscan_min_samples),
            "input_count": len(samples),
            "eligible_count": len(eligible),
            "ineligible_count": len(samples) - len(eligible),
            "clusters": [],
            "built_skills": [],
        }
        for item in samples:
            update_ingredient_reference(self.builder.manager.library_dir, item.get("ingredient_slots", {}))
        if not eligible:
            payload["reason"] = "no_eligible_sample"
            return payload
        if not valid_samples:
            payload["reason"] = "eligible_without_embedding"
            return payload

        labels = dbscan_cosine_vectors(vectors, eps=float(dbscan_eps), min_samples=max(1, int(dbscan_min_samples)))
        grouped_indices: Dict[str, List[int]] = {}
        noise_counter = 0
        for index, label in enumerate(labels):
            if label < 0:
                cluster_id = f"noise_{noise_counter:04d}"
                noise_counter += 1
            else:
                cluster_id = f"cluster_{label:04d}"
            grouped_indices.setdefault(cluster_id, []).append(index)
        cluster_items = [
            (cluster_id, [valid_samples[index] for index in grouped_indices[cluster_id]])
            for cluster_id in sorted(grouped_indices)
        ]

        def draft(cluster_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
            counts: Dict[str, Dict[str, int]] = {slot: {} for slot in SLOTS}
            for record in records:
                slots = clean_ingredient_slots(record.get("ingredient_slots", {}))
                for slot in SLOTS:
                    for token in slots[slot]:
                        counts[slot][token] = counts[slot].get(token, 0) + 1
            ingredients = {
                slot: [token for token, _ in sorted(counts[slot].items(), key=lambda item: (-item[1], item[0]))]
                for slot in SLOTS
            }
            candidates: List[Dict[str, Any]] = []
            for sample_index, record in enumerate(records, start=1):
                key = str(record.get("sample_key", "")).strip() or f"sample_{sample_index}"
                slug = re.sub(r"[^\w\-.]+", "_", key)
                rollout = record.get("rollout", {})
                raw_candidates = rollout.get("candidates", []) if isinstance(rollout, dict) else []
                for index, candidate in enumerate(raw_candidates if isinstance(raw_candidates, list) else [], start=1):
                    if not isinstance(candidate, dict):
                        continue
                    candidate_payload = copy.deepcopy(candidate)
                    candidate_id = str(candidate_payload.get("candidate_id", "")).strip() or f"candidate_{index}"
                    candidate_payload["candidate_id"] = f"{slug}__{candidate_id}"
                    candidates.append(candidate_payload)
            if not candidates:
                return {
                    "cluster_id": cluster_id,
                    "sample_count": len(records),
                    "candidate_count": 0,
                    "ingredients": ingredients,
                    "built": False,
                    "reason": "no_candidate",
                }
            analyses = self.analyzer.analyze_candidates(ingredients, candidates)
            raw_skill = self.builder.build_raw_skill(f"bootstrap_{cluster_id}", ingredients, analyses)
            return {
                "cluster_id": cluster_id,
                "sample_count": len(records),
                "candidate_count": len(candidates),
                "analysis_count": len(analyses),
                "ingredients": ingredients,
                "sample_keys": [str(item.get("sample_key", "")).strip() for item in records],
                "analyses": analyses,
                "raw_skill": raw_skill,
                "built": True,
            }

        drafts: Dict[str, Dict[str, Any]] = {}
        if self.builder_workers > 1 and len(cluster_items) > 1:
            with ThreadPoolExecutor(max_workers=min(self.builder_workers, len(cluster_items))) as pool:
                futures = {pool.submit(draft, cluster_id, records): cluster_id for cluster_id, records in cluster_items}
                for future in as_completed(futures):
                    drafts[futures[future]] = future.result()
        else:
            for cluster_id, records in cluster_items:
                drafts[cluster_id] = draft(cluster_id, records)

        for cluster_id in sorted(drafts):
            item = drafts[cluster_id]
            if not item.get("built", False):
                payload["clusters"].append(item)
                continue
            stored = self.builder.store_skill_content(
                f"bootstrap_{cluster_id}",
                item["analyses"],
                item["raw_skill"],
            )
            summary = {
                "cluster_id": cluster_id,
                "sample_count": item["sample_count"],
                "candidate_count": item["candidate_count"],
                "analysis_count": item["analysis_count"],
                "ingredients": item["ingredients"],
                "sample_keys": item["sample_keys"],
                "built": True,
                "record": stored["record"],
                "candidate_analyses": item["analyses"],
            }
            payload["clusters"].append(summary)
            payload["built_skills"].append(
                {
                    "cluster_id": cluster_id,
                    "record": stored["record"],
                    "analysis_count": item["analysis_count"],
                }
            )
        payload["labels"] = labels
        payload["noise_cluster_count"] = noise_counter
        return payload
