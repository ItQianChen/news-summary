from __future__ import annotations

import os
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class ToutiaoCollector(BaseCollector):
    platform = "toutiao"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        hot_url = self.settings.get("hot_url") or os.getenv("TOUTIAO_HOT_URL", "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
        try:
            payload = self._request_json(hot_url)
            rankings = self._parse_hot_payload(payload, limit)
            if rankings:
                return rankings
        except Exception as exc:
            self.logger.warning("toutiao hot search fetch failed: %s", exc)

        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        comments = self._fetch_comments_from_search_html(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_jina_search(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_search_engine(item, limit)
        if comments:
            return comments

        self.logger.warning("toutiao discussion fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _parse_hot_payload(self, payload: object, limit: int) -> list[RankingItem]:
        if not isinstance(payload, dict):
            return []

        raw_items = payload.get("data") or []
        if not isinstance(raw_items, list):
            return []

        rankings: list[RankingItem] = []
        for index, row in enumerate(raw_items[:limit], start=1):
            if not isinstance(row, dict):
                continue
            title = self._clean_text(row.get("Title") or "")
            if not title:
                continue
            
            target_url = row.get("Url") or f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(title)}"
            
            # HotValue
            heat_score = str(row.get("HotValue") or "")
            
            # topic_hint: use InterestCategory if available
            interest_cat = row.get("InterestCategory")
            topic_hint = ",".join(interest_cat) if isinstance(interest_cat, list) else ""
            topic_hint = self._clean_text(topic_hint)

            rankings.append(
                RankingItem(
                    platform=self.platform,
                    rank_index=index,
                    title=title,
                    url=str(target_url),
                    heat_score_raw=heat_score,
                    topic_hint=topic_hint,
                )
            )
        return rankings

    def _fetch_comments_from_search_html(self, item: RankingItem, limit: int) -> list[CommentItem]:
        # Implementation for directly scraping Toutiao search html
        search_url = f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(item.title)}"
        try:
            html = self._request_text(search_url)
            soup = BeautifulSoup(html, "html.parser")
            comments: list[CommentItem] = []
            
            # This is a generic approach to find text blocks in search results
            for index, node in enumerate(soup.select("p, h3, .s-result-item, .text-truncate")[: limit * 5], start=1):
                content = self._clean_text(node.get_text(" ", strip=True))
                if len(content) < 12:
                    continue
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"toutiao-html-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="toutiao-html",
                        like_count=max(limit - index, 0),
                        reply_count=0,
                    )
                )
                if len(comments) >= limit:
                    return comments
            return comments
        except Exception as exc:
            self.logger.info("toutiao search html fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_jina_search(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_url = f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(item.title)}"
        # Remove https:// prefix if needed but let's keep it as is
        mirror_url = f"https://r.jina.ai/http://{search_url}"
        try:
            text = self._request_text(mirror_url)
            candidates = self._extract_meaningful_lines(text)
            comments: list[CommentItem] = []
            for index, content in enumerate(candidates[:limit], start=1):
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"jina-toutiao-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="toutiao-search-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("toutiao jina search fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="toutiao.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-toutiao-{index}-{self._quote(item.title)}",
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
            "今日头条",
            "头条",
            "登录",
            "注册",
            "首页",
        )
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            cleaned = " ".join(raw_line.split())
            lowered = cleaned.lower()
            if len(cleaned) < 10 or len(cleaned) > 320:
                continue
            if lowered.startswith(("title:", "url source:", "markdown content:", "warning:")):
                continue
            if cleaned.startswith(ignored_prefixes):
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
