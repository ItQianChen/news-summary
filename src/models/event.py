from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.models.comment import CommentItem
from src.models.ranking import RankingItem


@dataclass(slots=True)
class Event:
    canonical_title: str
    summary_seed: str
    category: str | None = None
    importance_score: float = 0.0
    items: list[RankingItem] = field(default_factory=list)
    comments: list[CommentItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class EventSummary:
    title: str
    one_line_summary: str
    background: str
    controversy: str
    viewpoints: list[str]
    tags: list[str]
    watchpoints: list[str]


@dataclass(slots=True)
class EventPlatformItem:
    platform: str
    rank_index: int
    title: str
    url: str
    heat_score: str | None = None


@dataclass(slots=True)
class EventReport:
    summary: EventSummary
    platform_items: list[EventPlatformItem] = field(default_factory=list)
