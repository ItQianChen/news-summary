from __future__ import annotations

import os
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class DouyinCollector(BaseCollector):
    platform = "douyin"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        for url, params, headers in self._hot_endpoints():
            try:
                payload = self._request_json(url, params=params, headers=headers)
                rankings = self._parse_hot_payload(payload, limit)
                if rankings:
                    return rankings
            except Exception as exc:
                self.logger.info("douyin hot search fetch failed via %s: %s", url, exc)

        rankings = self._fetch_hot_from_jina(limit)
        if rankings:
            return rankings

        self.logger.warning("douyin hot search fetch failed: all network sources returned no usable content")
        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        comments = self._fetch_comments_from_search_api(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_search_html(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_jina_search(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_search_engine(item, limit)
        if comments:
            return comments

        self.logger.warning("douyin discussion fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _hot_endpoints(self) -> list[tuple[str, dict[str, object] | None, dict[str, str] | None]]:
        referer = os.getenv("DOUYIN_REFERER", "https://www.douyin.com/hot")
        web_url = self.settings.get("hot_web_url") or os.getenv(
            "DOUYIN_HOT_WEB_URL",
            "https://www.douyin.com/aweme/v1/web/hot/search/list/",
        )
        web_params: dict[str, object] = {
            "device_platform": "webapp",
            "aid": str(self.settings.get("aid") or os.getenv("DOUYIN_AID", "6383")),
            "channel": self.settings.get("channel") or os.getenv("DOUYIN_CHANNEL", "channel_pc_web"),
        }
        old_url = self.settings.get("hot_fallback_url") or os.getenv(
            "DOUYIN_HOT_FALLBACK_URL",
            "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/",
        )
        headers = {"Referer": referer}
        return [
            (str(web_url), web_params, headers),
            (str(old_url), None, headers),
        ]

    def _parse_hot_payload(self, payload: object, limit: int) -> list[RankingItem]:
        if not isinstance(payload, dict):
            return []

        raw_items = (
            payload.get("data", {}).get("word_list")
            if isinstance(payload.get("data"), dict)
            else None
        ) or payload.get("word_list") or payload.get("data") or []
        if not isinstance(raw_items, list):
            return []

        rankings: list[RankingItem] = []
        for index, row in enumerate(raw_items[:limit], start=1):
            if not isinstance(row, dict):
                continue
            title = self._clean_text(
                row.get("word")
                or row.get("sentence")
                or row.get("title")
                or row.get("desc")
                or ""
            )
            if not title:
                continue
            target_url = row.get("word_cover", {}).get("url") if isinstance(row.get("word_cover"), dict) else None
            target_url = target_url or f"https://www.douyin.com/search/{quote(title)}"
            rankings.append(
                RankingItem(
                    platform=self.platform,
                    rank_index=index,
                    title=title,
                    url=str(target_url),
                    heat_score_raw=str(
                        row.get("hot_value")
                        or row.get("event_time")
                        or row.get("view_count")
                        or row.get("aweme_cnt")
                        or ""
                    ),
                    topic_hint=self._clean_text(row.get("group_id") or row.get("sentence_tag") or ""),
                )
            )
        return rankings

    def _fetch_hot_from_jina(self, limit: int) -> list[RankingItem]:
        try:
            text = self._request_text("https://r.jina.ai/http://https://www.douyin.com/hot")
            rankings: list[RankingItem] = []
            seen: set[str] = set()
            for line in self._extract_meaningful_lines(text):
                title = self._normalize_hot_line(line)
                if not title or title in seen:
                    continue
                seen.add(title)
                rankings.append(
                    RankingItem(
                        platform=self.platform,
                        rank_index=len(rankings) + 1,
                        title=title,
                        url=f"https://www.douyin.com/search/{quote(title)}",
                        heat_score_raw="",
                    )
                )
                if len(rankings) >= limit:
                    return rankings
            return rankings
        except Exception as exc:
            self.logger.info("douyin hot search fetch failed via jina mirror: %s", exc)
            return []

    def _fetch_comments_from_search_api(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_api = self.settings.get("search_api") or os.getenv(
            "DOUYIN_SEARCH_API",
            "https://www.douyin.com/aweme/v1/web/general/search/single/",
        )
        params = {
            "device_platform": "webapp",
            "aid": str(self.settings.get("aid") or os.getenv("DOUYIN_AID", "6383")),
            "channel": self.settings.get("channel") or os.getenv("DOUYIN_CHANNEL", "channel_pc_web"),
            "keyword": item.title,
            "search_channel": "aweme_general",
            "offset": 0,
            "count": min(max(limit, 10), 20),
        }
        headers = {"Referer": f"https://www.douyin.com/search/{quote(item.title)}"}
        try:
            payload = self._request_json(str(search_api), params=params, headers=headers)
            return self._parse_search_payload(payload, limit)
        except Exception as exc:
            self.logger.info("douyin search api fetch failed for %s: %s", item.title, exc)
            return []

    def _parse_search_payload(self, payload: object, limit: int) -> list[CommentItem]:
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("data") or []
        if not isinstance(raw_items, list):
            return []

        comments: list[CommentItem] = []
        for index, row in enumerate(raw_items, start=1):
            if not isinstance(row, dict):
                continue
            aweme = row.get("aweme_info") or row.get("aweme_info_list") or row.get("aweme") or {}
            if isinstance(aweme, list):
                aweme = aweme[0] if aweme else {}
            if not isinstance(aweme, dict):
                continue
            author = aweme.get("author") or {}
            desc = self._clean_text(aweme.get("desc") or aweme.get("preview_title") or "")
            if len(desc) < 8:
                continue
            statistics = aweme.get("statistics") or {}
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=str(aweme.get("aweme_id") or aweme.get("group_id") or f"douyin-aweme-{index}"),
                    content=desc,
                    author_name=self._clean_text(author.get("nickname") or author.get("unique_id") or "") or None,
                    like_count=self._safe_int(statistics.get("digg_count") or statistics.get("admire_count")),
                    reply_count=self._safe_int(statistics.get("comment_count")),
                )
            )
            if len(comments) >= limit:
                return comments
        return comments

    def _fetch_comments_from_search_html(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_url = f"https://www.douyin.com/search/{quote(item.title)}"
        try:
            html = self._request_text(search_url, headers={"Referer": "https://www.douyin.com/"})
            soup = BeautifulSoup(html, "html.parser")
            comments: list[CommentItem] = []
            for index, node in enumerate(soup.select("script[type='application/ld+json'], p, h3")[: limit * 5], start=1):
                content = self._clean_text(node.get_text(" ", strip=True))
                if len(content) < 12:
                    continue
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"douyin-html-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="douyin-html",
                        like_count=max(limit - index, 0),
                        reply_count=0,
                    )
                )
                if len(comments) >= limit:
                    return comments
            return comments
        except Exception as exc:
            self.logger.info("douyin search html fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_jina_search(self, item: RankingItem, limit: int) -> list[CommentItem]:
        mirror_url = f"https://r.jina.ai/http://https://www.douyin.com/search/{quote(item.title)}"
        try:
            text = self._request_text(mirror_url)
            candidates = self._extract_meaningful_lines(text)
            comments: list[CommentItem] = []
            for index, content in enumerate(candidates[:limit], start=1):
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"jina-douyin-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="douyin-search-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("douyin jina search fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="douyin.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-douyin-{index}-{self._quote(item.title)}",
                    content=content,
                    author_name="search-snippet",
                    like_count=max(limit - index, 0),
                    reply_count=0,
                )
            )
        return comments

    @staticmethod
    def _normalize_hot_line(text: str) -> str:
        cleaned = re.sub(r"^\s*\d+[.、]\s*", "", text).strip()
        cleaned = re.sub(r"\s+(热度|上升|新晋).*$", "", cleaned).strip()
        return cleaned

    @staticmethod
    def _extract_meaningful_lines(text: str) -> list[str]:
        ignored_prefixes = (
            "title:",
            "url source:",
            "markdown content:",
            "warning:",
            "抖音",
            "下载",
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
