from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class CommentItem:
    platform: str
    ranking_id: int | None
    content: str
    comment_id_on_platform: str | None = None
    author_name: str | None = None
    like_count: int | None = None
    reply_count: int | None = None
    published_at: datetime | None = None
    captured_at: datetime = field(default_factory=datetime.utcnow)
