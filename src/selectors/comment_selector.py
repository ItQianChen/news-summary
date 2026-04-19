from __future__ import annotations

from src.models import CommentItem


class CommentSelector:
    def __init__(self, per_event_limit: int = 10, min_text_length: int = 8) -> None:
        self.per_event_limit = per_event_limit
        self.min_text_length = min_text_length

    def select(self, comments: list[CommentItem]) -> list[CommentItem]:
        filtered = [comment for comment in comments if self._is_valid(comment)]
        ranked = sorted(filtered, key=self._score, reverse=True)
        return ranked[: self.per_event_limit]

    def _is_valid(self, comment: CommentItem) -> bool:
        content = comment.content.strip()
        if len(content) < self.min_text_length:
            return False
        if content.count("😀") > 2:
            return False
        return True

    @staticmethod
    def _score(comment: CommentItem) -> float:
        like_score = float(comment.like_count or 0)
        reply_score = float(comment.reply_count or 0)
        text_quality_score = min(len(comment.content.strip()) / 50, 1.0)
        diversity_bonus = 0.1 if len(set(comment.content.strip().split())) > 5 else 0.0
        return 0.45 * like_score + 0.25 * reply_score + 0.20 * text_quality_score + 0.10 * diversity_bonus
