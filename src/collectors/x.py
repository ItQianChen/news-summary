from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class XCollector(BaseCollector):
    platform = "x"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        trends_url = self.settings.get("trends_url") or os.getenv("X_TRENDS_URL", "https://trends24.in/united-states/")
        try:
            html = self._request_text(trends_url)
            soup = BeautifulSoup(html, "html.parser")
            containers = soup.select("ol.trend-card__list") or soup.select("ol")
            rankings: list[RankingItem] = []
            seen: set[str] = set()
            for container in containers:
                for li in container.select("li"):
                    anchor = li.select_one("a")
                    if anchor is None:
                        continue
                    title = self._clean_text(anchor.get_text(" ", strip=True))
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    heat_raw = self._clean_text((li.select_one("span") or li).get_text(" ", strip=True))
                    rankings.append(
                        RankingItem(
                            platform=self.platform,
                            rank_index=len(rankings) + 1,
                            title=title,
                            url=f"https://x.com/search?q={self._quote(title)}&src=trend_click&f=live",
                            heat_score_raw=heat_raw,
                        )
                    )
                    if len(rankings) >= limit:
                        return rankings
            if rankings:
                return rankings[:limit]
        except Exception as exc:
            self.logger.warning("x trends fetch failed: %s", exc)

        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        comments = self._fetch_comments_from_nitter_rss(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_jina_search(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_search_engine(item, limit)
        if comments:
            return comments

        self.logger.warning("x discussion fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _fetch_comments_from_nitter_rss(self, item: RankingItem, limit: int) -> list[CommentItem]:
        nitter_base_url = (self.settings.get("nitter_base_url") or os.getenv("X_NITTER_BASE_URL", "https://nitter.net")).rstrip("/")
        rss_url = f"{nitter_base_url}/search/rss"
        try:
            text = self._request_text(rss_url, params={"f": "tweets", "q": item.title})
            root = ET.fromstring(text)
            comments: list[CommentItem] = []
            for index, node in enumerate(root.findall("./channel/item")[:limit], start=1):
                title = self._clean_text(node.findtext("title"))
                description = self._clean_text(node.findtext("description"))
                creator = self._clean_text(node.findtext("{http://purl.org/dc/elements/1.1/}creator"))
                content = description or title
                if not content:
                    continue
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=node.findtext("guid") or node.findtext("link"),
                        content=content,
                        author_name=creator or None,
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 2, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("x nitter rss discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_jina_search(self, item: RankingItem, limit: int) -> list[CommentItem]:
        target_url = f"https://x.com/search?q={self._quote(item.title)}&src=typed_query&f=live"
        mirror_url = f"https://r.jina.ai/http://{target_url}"
        try:
            text = self._request_text(mirror_url)
            candidates = self._extract_meaningful_lines(text)
            comments: list[CommentItem] = []
            for index, content in enumerate(candidates[:limit], start=1):
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"jina-x-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="x-search-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("x jina mirror discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="x.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-x-{index}-{self._quote(item.title)}",
                    content=content,
                    author_name="search-snippet",
                    like_count=max(limit - index, 0),
                    reply_count=0,
                )
            )
        return comments

    @staticmethod
    def _extract_meaningful_lines(text: str) -> list[str]:
        ignored_prefixes = (
            "title:",
            "url source:",
            "markdown content:",
            "warning:",
            "sign in",
            "don’t miss",
            "don't miss",
            "search",
            "explore",
            "x",
        )
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            cleaned = " ".join(raw_line.split())
            lowered = cleaned.lower()
            if len(cleaned) < 20 or len(cleaned) > 320:
                continue
            if lowered.startswith(ignored_prefixes):
                continue
            if cleaned.count("http") >= 2:
                continue
            if re.fullmatch(r"[\W_]+", cleaned):
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            lines.append(cleaned)
        return lines
