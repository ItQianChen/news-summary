from __future__ import annotations

from src.models import CommentItem, RankingItem
from src.utils import normalize_title


class EventNormalizer:
    def normalize_ranking(self, item: RankingItem) -> RankingItem:
        normalized_score = self._normalize_heat(item.heat_score_raw)
        topic_hint = normalize_title(item.title)[:32]
        return RankingItem(
            platform=item.platform,
            rank_index=item.rank_index,
            title=item.title.strip(),
            url=item.url,
            heat_score_raw=item.heat_score_raw,
            heat_score_normalized=normalized_score,
            topic_hint=topic_hint,
            captured_at=item.captured_at,
        )

    def normalize_comment(self, item: CommentItem) -> CommentItem:
        content = " ".join(item.content.split())
        return CommentItem(
            platform=item.platform,
            ranking_id=item.ranking_id,
            comment_id_on_platform=item.comment_id_on_platform,
            author_name=item.author_name,
            content=content,
            like_count=item.like_count,
            reply_count=item.reply_count,
            published_at=item.published_at,
            captured_at=item.captured_at,
        )

    @staticmethod
    def _normalize_heat(value: str | None) -> float | None:
        if not value:
            return None
        digits = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        if not digits:
            return None
        try:
            return float(digits)
        except ValueError:
            return None
