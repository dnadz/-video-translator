"""Cluster speaker embeddings. No sklearn."""

from __future__ import annotations

import numpy as np


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    left = np.asarray(a, dtype=np.float32).reshape(-1)
    right = np.asarray(b, dtype=np.float32).reshape(-1)
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / denom)


def cluster_embeddings(
    embeddings: list[np.ndarray],
    *,
    threshold: float = 0.55,
    max_speakers: int = 8,
) -> list[int]:
    """Online centroid clustering. Higher cosine similarity → same speaker."""
    if not embeddings:
        return []
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int] = []
    for vector in embeddings:
        item = np.asarray(vector, dtype=np.float32).reshape(-1)
        if not centroids:
            centroids.append(item.copy())
            counts.append(1)
            labels.append(0)
            continue
        scores = [cosine(item, center) for center in centroids]
        best = int(np.argmax(scores))
        if scores[best] >= threshold and len(centroids) <= max_speakers:
            labels.append(best)
            counts[best] += 1
            centroids[best] = (centroids[best] * (counts[best] - 1) + item) / counts[best]
            continue
        if len(centroids) >= max_speakers:
            labels.append(best)
            counts[best] += 1
            centroids[best] = (centroids[best] * (counts[best] - 1) + item) / counts[best]
            continue
        labels.append(len(centroids))
        centroids.append(item.copy())
        counts.append(1)
    return labels
