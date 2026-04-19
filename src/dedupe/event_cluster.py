from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from src.ai.client import AIClient
from src.models import Event, RankingItem
from src.utils import normalize_title


class EventCluster:
    SYNONYM_MAP = {
        "usa": "united states",
        "u.s": "united states",
        "us": "united states",
        "ai": "artificial intelligence",
        "a.i": "artificial intelligence",
    }

    def __init__(
        self,
        *,
        strong_threshold: float = 0.82,
        weak_threshold: float = 0.68,
        ai_client: AIClient | None = None,
    ) -> None:
        self.strong_threshold = strong_threshold
        self.weak_threshold = weak_threshold
        self.ai_client = ai_client

    def cluster(self, items: list[RankingItem]) -> list[Event]:
        if not items:
            return []

        normalized_items = [(item, self._normalize_phrase(item.title)) for item in items]
        embeddings = self._build_embedding_map([text for _, text in normalized_items])
        events: list[Event] = []
        event_vectors: list[list[float] | None] = []

        for item, normalized_title in normalized_items:
            candidate_vector = embeddings.get(normalized_title)
            best_index: int | None = None
            best_score = 0.0
            for index, event in enumerate(events):
                event_key = self._normalize_phrase(event.canonical_title)
                score = self._similarity(
                    normalized_title,
                    event_key,
                    candidate_vector,
                    event_vectors[index],
                )
                if score > best_score:
                    best_score = score
                    best_index = index

            if best_index is not None and best_score >= self.weak_threshold:
                target = events[best_index]
                target.items.append(item)
                target.importance_score += item.heat_score_normalized or 0.0
                if (item.heat_score_normalized or 0.0) > (target.items[0].heat_score_normalized or 0.0):
                    target.canonical_title = item.title
                event_vectors[best_index] = self._merge_vectors(event_vectors[best_index], candidate_vector)
                continue

            events.append(
                Event(
                    canonical_title=item.title,
                    summary_seed=normalized_title,
                    importance_score=item.heat_score_normalized or 0.0,
                    items=[item],
                )
            )
            event_vectors.append(candidate_vector)

        return sorted(events, key=lambda event: event.importance_score, reverse=True)

    def _normalize_phrase(self, text: str) -> str:
        normalized = normalize_title(text)
        for source, target in self.SYNONYM_MAP.items():
            normalized = normalized.replace(source, target)
        normalized = re.sub(r"(breaking|live|latest|update|news|video|shorts|official)", " ", normalized)
        normalized = re.sub(r"(20\d{2}|19\d{2})", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _similarity(
        self,
        left: str,
        right: str,
        left_vector: list[float] | None,
        right_vector: list[float] | None,
    ) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0

        token_similarity = self._jaccard(self._tokens(left), self._tokens(right))
        sequence_similarity = SequenceMatcher(None, left, right).ratio()
        bigram_similarity = self._jaccard(self._ngrams(left), self._ngrams(right))
        embedding_similarity = self._cosine_similarity(left_vector, right_vector)

        score = 0.35 * token_similarity + 0.30 * sequence_similarity + 0.20 * bigram_similarity + 0.15 * embedding_similarity
        if token_similarity >= self.strong_threshold:
            return max(score, token_similarity)
        return score

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in text.split() if len(token) > 1}

    @staticmethod
    def _ngrams(text: str, size: int = 2) -> set[str]:
        compact = text.replace(" ", "")
        if len(compact) < size:
            return {compact} if compact else set()
        return {compact[index : index + size] for index in range(len(compact) - size + 1)}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        return intersection / union if union else 0.0

    @staticmethod
    def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _build_embedding_map(self, texts: list[str]) -> dict[str, list[float] | None]:
        unique_texts = list(dict.fromkeys(texts))
        if not self.ai_client:
            return {text: None for text in unique_texts}
        vectors = self.ai_client.embed(unique_texts)
        if not vectors or len(vectors) != len(unique_texts):
            return {text: None for text in unique_texts}
        return {text: vector for text, vector in zip(unique_texts, vectors)}

    @staticmethod
    def _merge_vectors(left: list[float] | None, right: list[float] | None) -> list[float] | None:
        if left and right and len(left) == len(right):
            return [(a + b) / 2 for a, b in zip(left, right)]
        return left or right
