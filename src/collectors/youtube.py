from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class YouTubeCollector(BaseCollector):
    platform = "youtube"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        for base_url in self._candidate_base_urls():
            try:
                payload = self._request_json(f"{base_url}/api/v1/trending", params={"type": "default"})
                rankings: list[RankingItem] = []
                for index, row in enumerate(payload[:limit], start=1):
                    video_id = row.get("videoId") or row.get("video_id")
                    title = self._clean_text(row.get("title"))
                    if not video_id or not title:
                        continue
                    rankings.append(
                        RankingItem(
                            platform=self.platform,
                            rank_index=index,
                            title=title,
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            heat_score_raw=str(row.get("viewCount") or row.get("views") or ""),
                            topic_hint=self._clean_text(row.get("author") or ""),
                        )
                    )
                if rankings:
                    return rankings
            except Exception as exc:
                self.logger.info("youtube trending fetch failed via %s: %s", base_url, exc)

        rankings = self._fetch_trending_from_jina(limit)
        if rankings:
            return rankings

        self.logger.warning("youtube trending fetch failed: all invidious candidates and jina mirror returned no usable content")
        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        video_id = self._extract_video_id(item.url)

        if video_id:
            for base_url in self._candidate_base_urls():
                try:
                    payload = self._request_json(f"{base_url}/api/v1/comments/{video_id}", params={"sort_by": "top"})
                    raw_comments = payload.get("comments") or []
                    comments: list[CommentItem] = []
                    for row in raw_comments[:limit]:
                        content = self._clean_text(row.get("contentHtml") or row.get("content"))
                        if not content:
                            continue
                        comments.append(
                            CommentItem(
                                platform=self.platform,
                                ranking_id=None,
                                comment_id_on_platform=str(row.get("commentId") or row.get("comment_id") or ""),
                                content=content,
                                author_name=self._clean_text(row.get("author")),
                                like_count=self._safe_int(row.get("likeCount")),
                                reply_count=self._safe_int((row.get("replies") or {}).get("replyCount")),
                            )
                        )
                    if comments:
                        return comments
                except Exception as exc:
                    self.logger.info("youtube comments fetch failed via %s for %s: %s", base_url, item.title, exc)

        comments = self._fetch_comments_from_jina_watch(item, limit)
        if comments:
            return comments

        comments = self._fetch_comments_from_search_engine(item, limit)
        if comments:
            return comments

        self.logger.warning("youtube comments fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _candidate_base_urls(self) -> list[str]:
        configured = self.settings.get("invidious_base_url") or os.getenv("YOUTUBE_INVIDIOUS_BASE_URL", "")
        extra = os.getenv("YOUTUBE_INVIDIOUS_BASE_URLS", "")
        defaults = [
            "https://yewtu.be",
            "https://inv.nadeko.net",
            "https://inv.us.projectsegfau.lt",
            "https://invidious.privacyredirect.com",
        ]
        values = [configured, *extra.split(","), *defaults]
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = str(value or "").strip().rstrip("/")
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    def _fetch_trending_from_jina(self, limit: int) -> list[RankingItem]:
        try:
            text = self._request_text("https://r.jina.ai/http://https://www.youtube.com/feed/trending")
            pattern = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://(?:www\.)?youtube\.com/watch\?v=[^)]+)\)")
            rankings: list[RankingItem] = []
            seen: set[str] = set()
            for match in pattern.finditer(text):
                title = self._clean_text(match.group("title"))
                url = match.group("url")
                if not title or title in seen:
                    continue
                seen.add(title)
                rankings.append(
                    RankingItem(
                        platform=self.platform,
                        rank_index=len(rankings) + 1,
                        title=title,
                        url=url,
                        heat_score_raw="",
                    )
                )
                if len(rankings) >= limit:
                    return rankings
            return rankings
        except Exception as exc:
            self.logger.info("youtube trending fetch failed via jina mirror: %s", exc)
            return []

    def _fetch_comments_from_jina_watch(self, item: RankingItem, limit: int) -> list[CommentItem]:
        target_url = item.url or f"https://www.youtube.com/results?search_query={self._quote(item.title)}"
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
                        comment_id_on_platform=f"jina-youtube-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="youtube-watch-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("youtube comments fetch failed via jina mirror for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="youtube.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-youtube-{index}-{self._quote(item.title)}",
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
            "home",
            "shorts",
            "subscriptions",
            "you",
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
            if cleaned in seen:
                continue
            seen.add(cleaned)
            lines.append(cleaned)
        return lines

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.query:
            return parse_qs(parsed.query).get("v", [None])[0]
        return None
