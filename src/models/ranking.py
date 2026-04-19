from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class RankingItem:
    platform: str
    rank_index: int
    title: str
    url: str
    heat_score_raw: str | None = None
    heat_score_normalized: float | None = None
    topic_hint: str | None = None
    captured_at: datetime = field(default_factory=datetime.utcnow)
