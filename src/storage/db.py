from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS platform_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    rank_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    heat_score_raw TEXT,
    heat_score_normalized REAL,
    topic_hint TEXT,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    ranking_id INTEGER,
    comment_id_on_platform TEXT,
    author_name TEXT,
    content TEXT NOT NULL,
    like_count INTEGER,
    reply_count INTEGER,
    published_at TEXT,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_title TEXT NOT NULL,
    summary_seed TEXT NOT NULL,
    category TEXT,
    importance_score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    ranking_id INTEGER NOT NULL,
    platform TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str = "data/news_summary.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def clear(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM platform_rankings")
            connection.execute("DELETE FROM comments")
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM event_items")
            connection.commit()
