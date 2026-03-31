"""Evidence Sentence Alignment Score (ESAS).

Measures inter-model agreement on evidence sentences using token-level
Jaccard similarity. Provides one-way confidence modulation (boost only).
"""

from __future__ import annotations

from metascreener.core.models_base import ModelOutput


def token_jaccard(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def compute_esas(
    model_outputs: list[ModelOutput],
    elements: list[str],
) -> tuple[float, dict[str, float]]:
    per_element: dict[str, float] = {}

    for elem in elements:
        evidence_sentences: list[str] = []
        for output in model_outputs:
            if output.error is not None:
                continue
            ea = output.element_assessment.get(elem)
            if ea is not None and ea.evidence:
                evidence_sentences.append(ea.evidence)

        if len(evidence_sentences) < 2:
            per_element[elem] = 0.0
            continue

        n = len(evidence_sentences)
        total_sim = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_sim += token_jaccard(evidence_sentences[i], evidence_sentences[j])
                count += 1

        per_element[elem] = total_sim / count if count > 0 else 0.0

    mean_esas = sum(per_element.values()) / len(per_element) if per_element else 0.0
    return mean_esas, per_element


def esas_modulation(
    confidence: float,
    mean_esas: float,
    gamma: float = 0.3,
    tau: float = 0.5,
) -> float:
    boost = gamma * max(0.0, mean_esas - tau)
    return confidence * (1.0 + boost)
