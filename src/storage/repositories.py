from __future__ import annotations

from src.models import CommentItem, RankingItem
from src.storage.db import Database


class RankingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_many(self, items: list[RankingItem]) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO platform_rankings (
                    platform, rank_index, title, url,
                    heat_score_raw, heat_score_normalized, topic_hint, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.platform,
                        item.rank_index,
                        item.title,
                        item.url,
                        item.heat_score_raw,
                        item.heat_score_normalized,
                        item.topic_hint,
                        item.captured_at.isoformat(),
                    )
                    for item in items
                ],
            )
            connection.commit()


class CommentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_many(self, items: list[CommentItem]) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO comments (
                    platform, ranking_id, comment_id_on_platform, author_name,
                    content, like_count, reply_count, published_at, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.platform,
                        item.ranking_id,
                        item.comment_id_on_platform,
                        item.author_name,
                        item.content,
                        item.like_count,
                        item.reply_count,
                        item.published_at.isoformat() if item.published_at else None,
                        item.captured_at.isoformat(),
                    )
                    for item in items
                ],
            )
            connection.commit()
