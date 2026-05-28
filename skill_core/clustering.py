from __future__ import annotations

import math
from typing import List


def _cosine_distance(left: List[float], right: List[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    lnorm = math.sqrt(sum(a * a for a in left))
    rnorm = math.sqrt(sum(b * b for b in right))
    if lnorm <= 0.0 or rnorm <= 0.0:
        return 1.0
    return 1.0 - numerator / (lnorm * rnorm)


def dbscan_cosine_vectors(vectors: List[List[float]], eps: float, min_samples: int) -> List[int]:
    labels = [-99 for _ in vectors]

    def neighbors(index: int) -> List[int]:
        return [j for j, vec in enumerate(vectors) if _cosine_distance(vectors[index], vec) <= eps]

    cluster_id = 0
    for index in range(len(vectors)):
        if labels[index] != -99:
            continue
        nearby = neighbors(index)
        if len(nearby) < min_samples:
            labels[index] = -1
            continue
        labels[index] = cluster_id
        seeds = list(nearby)
        cursor = 0
        while cursor < len(seeds):
            point = seeds[cursor]
            cursor += 1
            if labels[point] == -1:
                labels[point] = cluster_id
            if labels[point] != -99:
                continue
            labels[point] = cluster_id
            expanded = neighbors(point)
            if len(expanded) >= min_samples:
                for other in expanded:
                    if other not in seeds:
                        seeds.append(other)
        cluster_id += 1
    return labels
