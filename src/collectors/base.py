from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from src.models import CommentItem, RankingItem
from src.utils import get_logger


class BaseCollector(ABC):
    platform: str = "unknown"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}
        self.timeout = float(self.settings.get("timeout_seconds", 15))
        self.allow_fallback_on_error = bool(self.settings.get("allow_fallback_on_error", True))
        self.logger = get_logger(f"collector.{self.platform}")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )

    @abstractmethod
    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        raise NotImplementedError

    @abstractmethod
    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        raise NotImplementedError

    def _request_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _request_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if not value:
            return ""
        text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
        return " ".join(text.split())

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _quote(value: str) -> str:
        return quote_plus(value)

    def _fetch_search_snippets(self, query: str, limit: int, *, site_hint: str | None = None) -> list[str]:
        search_query = f"site:{site_hint} {query}" if site_hint else query
        engines = [
            ("https://www.bing.com/search", {"q": search_query}),
            ("https://www.sogou.com/web", {"query": search_query}),
        ]
        for url, params in engines:
            try:
                html = self._request_text(url, params=params)
                snippets = self._extract_search_snippets(html, limit)
                if snippets:
                    return snippets[:limit]
            except Exception as exc:
                self.logger.info("search snippet fetch failed via %s for %s: %s", url, query, exc)
        return []

    def _extract_search_snippets(self, html: str, limit: int) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select("li.b_algo, div.vrwrap, div.rb, .results .result")
        snippets: list[str] = []
        seen: set[str] = set()
        for block in blocks:
            candidates = block.select("p, .b_caption, .c-abstract, .str-text-info, .text-layout") or [block]
            for node in candidates:
                cleaned = self._clean_text(node.get_text(" ", strip=True))
                if len(cleaned) < 16 or len(cleaned) > 320:
                    continue
                if cleaned.count("http") >= 2:
                    continue
                if cleaned in seen:
                    continue
                seen.add(cleaned)
                snippets.append(cleaned)
                if len(snippets) >= limit:
                    return snippets
        return snippets

    def _fallback_rankings(self, limit: int) -> list[RankingItem]:
        return [
            RankingItem(
                platform=self.platform,
                rank_index=index,
                title=f"{self.platform} 热点抓取失败，占位 #{index}",
                url="",
                heat_score_raw=None,
            )
            for index in range(1, limit + 1)
        ]

    def _fallback_comments(self, item: RankingItem, limit: int) -> list[CommentItem]:
        return [
            CommentItem(
                platform=self.platform,
                ranking_id=None,
                content=f"{self.platform} 未能获取真实讨论内容，当前仅保留事件标题：{item.title}",
                author_name="system-fallback",
                like_count=max(limit - index, 0),
                reply_count=0,
            )
            for index in range(1, min(limit, 3) + 1)
        ]
