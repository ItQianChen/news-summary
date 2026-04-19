from __future__ import annotations

import math
import re

from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class BilibiliCollector(BaseCollector):
    platform = "bilibili"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        rankings = self._fetch_popular_rankings(limit)
        if rankings:
            return rankings

        rankings = self._fetch_rankings_from_jina(limit)
        if rankings:
            return rankings

        self.logger.warning("bilibili popular fetch failed: all network sources returned no usable content")
        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        comments = self._fetch_comments_from_reply_api(item, limit)
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

        self.logger.warning("bilibili discussion fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _fetch_popular_rankings(self, limit: int) -> list[RankingItem]:
        popular_url = str(self.settings.get("popular_url") or "https://api.bilibili.com/x/web-interface/popular")
        page_size = min(max(int(self.settings.get("page_size", 20)), 1), 20)
        total_pages = max(1, math.ceil(limit / page_size))
        rankings: list[RankingItem] = []
        seen: set[str] = set()

        for page in range(1, total_pages + 1):
            try:
                payload = self._request_json(popular_url, params={"pn": page, "ps": page_size})
            except Exception as exc:
                self.logger.info("bilibili popular fetch failed via page %s: %s", page, exc)
                continue

            rows = payload.get("data", {}).get("list") or []
            for row in rows:
                title = self._clean_text(row.get("title"))
                if not title or title in seen:
                    continue
                seen.add(title)
                bvid = str(row.get("bvid") or "").strip()
                target_url = f"https://www.bilibili.com/video/{bvid}" if bvid else (row.get("short_link_v2") or row.get("short_link") or "")
                rankings.append(
                    RankingItem(
                        platform=self.platform,
                        rank_index=len(rankings) + 1,
                        title=title,
                        url=str(target_url),
                        heat_score_raw=str((row.get("stat") or {}).get("view") or row.get("view") or ""),
                        topic_hint=self._clean_text((row.get("owner") or {}).get("name") or row.get("author") or ""),
                    )
                )
                if len(rankings) >= limit:
                    return rankings

        return rankings

    def _fetch_rankings_from_jina(self, limit: int) -> list[RankingItem]:
        try:
            text = self._request_text("https://r.jina.ai/http://https://www.bilibili.com/v/popular/all/")
            pattern = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://(?:www\.)?bilibili\.com/video/[^)]+)\)")
            rankings: list[RankingItem] = []
            seen: set[str] = set()
            for match in pattern.finditer(text):
                title = self._clean_text(match.group("title"))
                if not title or title in seen:
                    continue
                seen.add(title)
                rankings.append(
                    RankingItem(
                        platform=self.platform,
                        rank_index=len(rankings) + 1,
                        title=title,
                        url=match.group("url"),
                        heat_score_raw="",
                    )
                )
                if len(rankings) >= limit:
                    return rankings
            return rankings
        except Exception as exc:
            self.logger.info("bilibili popular fetch failed via jina mirror: %s", exc)
            return []

    def _fetch_comments_from_reply_api(self, item: RankingItem, limit: int) -> list[CommentItem]:
        bvid_match = re.search(r"bilibili\.com/video/(BV[a-zA-Z0-9]+)", str(item.url))
        if not bvid_match:
            return []
        bvid = bvid_match.group(1)
        
        try:
            view_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            view_data = self._request_json(view_url)
            aid = (view_data.get("data") or {}).get("aid")
            if not aid:
                return []
                
            reply_url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&sort=2"
            reply_data = self._request_json(reply_url)
            replies = (reply_data.get("data") or {}).get("replies") or []
            
            comments: list[CommentItem] = []
            for reply in replies[:limit]:
                content = self._clean_text((reply.get("content") or {}).get("message") or "")
                if not content:
                    continue
                author = self._clean_text((reply.get("member") or {}).get("uname") or "bilibili_user")
                
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=str(reply.get("rpid") or f"bilibili-{len(comments)}"),
                        content=content,
                        author_name=author,
                        like_count=int(reply.get("like", 0)),
                        reply_count=int(reply.get("rcount", 0)),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("bilibili reply api fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_html(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_url = f"https://search.bilibili.com/all?keyword={self._quote(item.title)}"
        try:
            html = self._request_text(search_url)
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(
                ".bili-video-card, .video-item, .search-all-list .video-list-item, .bili-video-card__wrap, li.video-item"
            )
            comments: list[CommentItem] = []
            for index, card in enumerate(cards, start=1):
                title_node = card.select_one(
                    ".bili-video-card__info--tit, .title, .video-item-title, .bili-video-card__info--title"
                )
                desc_node = card.select_one(
                    ".bili-video-card__info--desc, .des, .description, .desc, .bili-video-card__info--bottom"
                )
                author_node = card.select_one(
                    ".bili-video-card__info--author, .up-name, .so-icon .up-name, .bili-video-card__info--owner"
                )
                content_parts = [
                    self._clean_text(title_node.get_text(" ", strip=True)) if title_node else "",
                    self._clean_text(desc_node.get_text(" ", strip=True)) if desc_node else "",
                ]
                content = "；".join(part for part in content_parts if part)
                if len(content) < 8:
                    continue
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=f"search-bilibili-html-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name=self._clean_text(author_node.get_text(" ", strip=True)) if author_node else "bilibili-search",
                        like_count=max(limit - index, 0),
                        reply_count=0,
                    )
                )
                if len(comments) >= limit:
                    return comments
            return comments
        except Exception as exc:
            self.logger.info("bilibili search html discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_jina_search(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_url = f"https://search.bilibili.com/all?keyword={self._quote(item.title)}"
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
                        comment_id_on_platform=f"jina-bilibili-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="bilibili-search-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("bilibili jina discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="bilibili.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-bilibili-{index}-{self._quote(item.title)}",
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
            "bilibili",
            "首页",
            "番剧",
            "直播",
            "游戏中心",
            "下载客户端",
        )
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            cleaned = " ".join(raw_line.split())
            lowered = cleaned.lower()
            if len(cleaned) < 12 or len(cleaned) > 320:
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
