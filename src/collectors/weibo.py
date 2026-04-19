from __future__ import annotations

import os
import re

from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class WeiboCollector(BaseCollector):
    platform = "weibo"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        hot_url = self.settings.get("hot_url") or os.getenv("WEIBO_HOT_URL", "https://weibo.com/ajax/side/hotSearch")
        referer = self.settings.get("referer", "https://weibo.com/hot/search")
        try:
            payload = self._request_json(hot_url, headers={"Referer": referer})
            realtime = payload.get("data", {}).get("realtime") or payload.get("realtime") or []
            rankings: list[RankingItem] = []
            for index, row in enumerate(realtime[:limit], start=1):
                title = self._clean_text(row.get("note") or row.get("word") or "")
                if not title:
                    continue
                target_url = row.get("scheme") or f"https://s.weibo.com/weibo?q={self._quote(title)}"
                if isinstance(target_url, str) and target_url.startswith("//"):
                    target_url = f"https:{target_url}"
                rankings.append(
                    RankingItem(
                        platform=self.platform,
                        rank_index=index,
                        title=title,
                        url=target_url,
                        heat_score_raw=str(row.get("num") or row.get("raw_hot") or row.get("hot") or ""),
                        topic_hint=self._clean_text(row.get("label_name") or row.get("category") or ""),
                    )
                )
            if rankings:
                return rankings
        except Exception as exc:
            self.logger.warning("weibo hot search fetch failed: %s", exc)

        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        comments = self._fetch_comments_from_mobile_api(item, limit)
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

        self.logger.warning("weibo discussion fetch failed for %s: all network sources returned no usable content", item.title)
        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    def _fetch_comments_from_mobile_api(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_api = self.settings.get("search_api") or os.getenv("WEIBO_SEARCH_API", "https://m.weibo.cn/api/container/getIndex")
        referer = self.settings.get("referer", "https://weibo.com/hot/search")
        params = {
            "containerid": f"100103type=1&q={item.title}",
            "page_type": "searchall",
        }
        try:
            payload = self._request_json(
                search_api,
                params=params,
                headers={
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            cards = payload.get("data", {}).get("cards") or []
            comments: list[CommentItem] = []
            for card in cards:
                for group in card.get("card_group") or [card]:
                    mblog = group.get("mblog") or {}
                    content = self._clean_text(mblog.get("text"))
                    if not content:
                        continue
                    user = mblog.get("user") or {}
                    comments.append(
                        CommentItem(
                            platform=self.platform,
                            ranking_id=None,
                            comment_id_on_platform=str(mblog.get("id") or mblog.get("bid") or ""),
                            content=content,
                            author_name=user.get("screen_name"),
                            like_count=self._safe_int(mblog.get("attitudes_count")),
                            reply_count=self._safe_int(mblog.get("comments_count")),
                        )
                    )
                    if len(comments) >= limit:
                        return comments
            return comments
        except Exception as exc:
            self.logger.info("weibo mobile api discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_html(self, item: RankingItem, limit: int) -> list[CommentItem]:
        referer = self.settings.get("referer", "https://weibo.com/hot/search")
        search_url = f"https://s.weibo.com/weibo?q={self._quote(item.title)}"
        try:
            html = self._request_text(search_url, headers={"Referer": referer})
            soup = BeautifulSoup(html, "html.parser")
            comments: list[CommentItem] = []
            cards = soup.select(".card-wrap")
            for index, card in enumerate(cards, start=1):
                text_node = card.select_one(".txt") or card.select_one("[node-type='feed_list_content']")
                if text_node is None:
                    continue
                content = self._clean_text(text_node.get_text(" ", strip=True))
                if len(content) < 8:
                    continue
                author_node = card.select_one(".name") or card.select_one(".from a")
                action_texts = [self._clean_text(node.get_text(" ", strip=True)) for node in card.select(".card-act li")]
                comments.append(
                    CommentItem(
                        platform=self.platform,
                        ranking_id=None,
                        comment_id_on_platform=str(card.get("mid") or card.get("action-type") or f"weibo-html-{index}"),
                        content=content,
                        author_name=self._clean_text(author_node.get_text(" ", strip=True)) if author_node else None,
                        like_count=self._extract_first_int(action_texts[2]) if len(action_texts) > 2 else None,
                        reply_count=self._extract_first_int(action_texts[1]) if len(action_texts) > 1 else None,
                    )
                )
                if len(comments) >= limit:
                    return comments
            return comments
        except Exception as exc:
            self.logger.info("weibo search html discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_jina_search(self, item: RankingItem, limit: int) -> list[CommentItem]:
        search_url = f"https://s.weibo.com/weibo?q={self._quote(item.title)}"
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
                        comment_id_on_platform=f"jina-weibo-{index}-{self._quote(item.title)}",
                        content=content,
                        author_name="weibo-search-mirror",
                        like_count=max(limit - index, 0),
                        reply_count=max((limit - index) // 3, 0),
                    )
                )
            return comments
        except Exception as exc:
            self.logger.info("weibo jina discussion fetch failed for %s: %s", item.title, exc)
            return []

    def _fetch_comments_from_search_engine(self, item: RankingItem, limit: int) -> list[CommentItem]:
        snippets = self._fetch_search_snippets(item.title, limit, site_hint="weibo.com")
        comments: list[CommentItem] = []
        for index, content in enumerate(snippets[:limit], start=1):
            comments.append(
                CommentItem(
                    platform=self.platform,
                    ranking_id=None,
                    comment_id_on_platform=f"search-weibo-{index}-{self._quote(item.title)}",
                    content=content,
                    author_name="search-snippet",
                    like_count=max(limit - index, 0),
                    reply_count=0,
                )
            )
        return comments

    @staticmethod
    def _extract_first_int(text: str) -> int | None:
        match = re.search(r"(\d+)", text or "")
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _extract_meaningful_lines(text: str) -> list[str]:
        ignored_prefixes = (
            "title:",
            "url source:",
            "markdown content:",
            "warning:",
            "微博",
            "热搜",
            "登录",
            "注册",
            "还没有",
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
