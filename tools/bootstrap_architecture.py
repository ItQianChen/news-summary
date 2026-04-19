from pathlib import Path

FILES = {
    "requirements.txt": '''requests>=2.32.0
beautifulsoup4>=4.12.3
PyYAML>=6.0.1
APScheduler>=3.10.4
python-dotenv>=1.0.1
openai>=2.11.0
''',
    ".env.example": '''OPENAI_API_KEY=
OPENAI_BASE_URL=
MODEL_NAME=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_RETRIES=3
OPENAI_TEMPERATURE=0.2
EMBEDDING_MODEL=
DATABASE_URL=sqlite:///data/news_summary.db
REPORT_TIMEZONE=Asia/Shanghai
X_NITTER_BASE_URL=https://nitter.net
X_TRENDS_URL=https://trends24.in/united-states/
YOUTUBE_INVIDIOUS_BASE_URL=https://yewtu.be
WEIBO_HOT_URL=https://weibo.com/ajax/side/hotSearch
WEIBO_SEARCH_API=https://m.weibo.cn/api/container/getIndex
''',
    "config/settings.yaml": '''collector:
  top_limit: 10
  comment_limit: 20
  timeout_seconds: 15
  allow_fallback_on_error: true
  enabled_platforms:
    - weibo
    - x
    - youtube
  platforms:
    weibo:
      hot_url: https://weibo.com/ajax/side/hotSearch
      search_api: https://m.weibo.cn/api/container/getIndex
      referer: https://weibo.com/hot/search
    x:
      trends_url: https://trends24.in/united-states/
      nitter_base_url: https://nitter.net
    youtube:
      invidious_base_url: https://yewtu.be

selector:
  per_event_comment_limit: 10
  min_text_length: 8

dedupe:
  strong_similarity_threshold: 0.82
  weak_similarity_threshold: 0.68

scheduler:
  hourly_cron: "0 * * * *"
  report_crons:
    - "0 8 * * *"
    - "0 20 * * *"

report:
  output_dir: data/reports
  write_json: true
''',
    "config/prompts/event_summary.txt": '''你是一个新闻事件总结助手。

你会收到一个事件对象，里面包含：
- 统一事件标题
- 多个平台热榜条目
- 代表性评论/帖子样本

输出要求：
1. 只能基于输入信息总结，不得虚构事实。
2. 先区分事实，再概括观点分歧。
3. 评论只能作为“观点样本”，不能当成事实来源。
4. 结果必须输出为 JSON 对象。
5. JSON 必须包含以下键：
   - one_line_summary: string
   - background: string
   - controversy: string
   - viewpoints: string[]
   - tags: string[]
   - watchpoints: string[]
''',
    "config/prompts/daily_digest.txt": '''你是一个新闻日报编辑助手。

你会收到多个单事件总结，请输出结构化 Markdown 日报。

要求：
1. 先输出今日三大焦点。
2. 再输出每个事件的一句话摘要、背景、争议焦点、主要观点、标签、观察点。
3. 明确哪些是事实观察，哪些是舆论倾向。
4. 不得虚构输入中不存在的背景。
5. 输出必须是 Markdown，不要输出 JSON，不要加代码块。
''',
    "src/collectors/base.py": '''from __future__ import annotations

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
''',
    "src/collectors/weibo.py": '''from __future__ import annotations

import os

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
        search_api = self.settings.get("search_api") or os.getenv("WEIBO_SEARCH_API", "https://m.weibo.cn/api/container/getIndex")
        params = {
            "containerid": f"100103type=1&q={item.title}",
            "page_type": "searchall",
        }
        try:
            payload = self._request_json(search_api, params=params)
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
            if comments:
                return comments
        except Exception as exc:
            self.logger.warning("weibo discussion fetch failed for %s: %s", item.title, exc)

        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []
''',
    "src/collectors/x.py": '''from __future__ import annotations

import os
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
            if comments:
                return comments
        except Exception as exc:
            self.logger.warning("x discussion fetch failed for %s: %s", item.title, exc)

        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []
''',
    "src/collectors/youtube.py": '''from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

from src.collectors.base import BaseCollector
from src.models import CommentItem, RankingItem


class YouTubeCollector(BaseCollector):
    platform = "youtube"

    def fetch_top_rankings(self, limit: int = 10) -> list[RankingItem]:
        base_url = (self.settings.get("invidious_base_url") or os.getenv("YOUTUBE_INVIDIOUS_BASE_URL", "https://yewtu.be")).rstrip("/")
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
            self.logger.warning("youtube trending fetch failed: %s", exc)

        return self._fallback_rankings(limit) if self.allow_fallback_on_error else []

    def fetch_comments(self, item: RankingItem, limit: int = 30) -> list[CommentItem]:
        base_url = (self.settings.get("invidious_base_url") or os.getenv("YOUTUBE_INVIDIOUS_BASE_URL", "https://yewtu.be")).rstrip("/")
        video_id = self._extract_video_id(item.url)
        if not video_id:
            return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []
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
            self.logger.warning("youtube comments fetch failed for %s: %s", item.title, exc)

        return self._fallback_comments(item, limit) if self.allow_fallback_on_error else []

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.query:
            return parse_qs(parsed.query).get("v", [None])[0]
        return None
''',
    "src/ai/client.py": '''from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from src.utils import get_logger


class AIClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.model_name = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "").strip()
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        self.logger = get_logger(__name__)
        self._client: OpenAI | None = None

        if self.is_configured():
            client_kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout_seconds,
                "max_retries": self.max_retries,
            }
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model_name)

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float | None = None) -> str:
        if not self._client:
            return ""
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature if temperature is None else temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            self.logger.warning("AI completion failed: %s", exc)
            return ""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        text = self.complete(system_prompt, user_prompt)
        return self.extract_json(text)

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._client or not self.embedding_model or not texts:
            return None
        try:
            response = self._client.embeddings.create(model=self.embedding_model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as exc:
            self.logger.warning("embedding request failed: %s", exc)
            return None

    @staticmethod
    def extract_json(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        text = text.strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
''',
    "src/ai/summarizer.py": '''from __future__ import annotations

import json
from dataclasses import asdict

from src.ai.client import AIClient
from src.ai.prompts import PromptRepository
from src.models import Event, EventSummary
from src.utils import unique_preserve_order


class Summarizer:
    def __init__(self, client: AIClient, prompts: PromptRepository) -> None:
        self.client = client
        self.prompts = prompts

    def summarize_event(self, event: Event) -> EventSummary:
        system_prompt = self.prompts.load("event_summary.txt")
        payload = {
            "title": event.canonical_title,
            "platform_items": [
                {
                    "platform": item.platform,
                    "rank_index": item.rank_index,
                    "title": item.title,
                    "url": item.url,
                    "heat_score": item.heat_score_raw,
                }
                for item in event.items
            ],
            "comments": [
                {
                    "platform": comment.platform,
                    "author_name": comment.author_name,
                    "content": comment.content,
                    "like_count": comment.like_count,
                    "reply_count": comment.reply_count,
                }
                for comment in event.comments[:10]
            ],
        }
        ai_result = self.client.complete_json(system_prompt, json.dumps(payload, ensure_ascii=False, indent=2))
        if ai_result:
            return EventSummary(
                title=event.canonical_title,
                one_line_summary=str(ai_result.get("one_line_summary") or f"{event.canonical_title} 引发多平台讨论。"),
                background=str(ai_result.get("background") or "输入信息不足，暂无更多可靠背景。"),
                controversy=str(ai_result.get("controversy") or "暂无足够信息判断主要争议焦点。"),
                viewpoints=self._coerce_list(ai_result.get("viewpoints"), fallback=[comment.content for comment in event.comments[:3]]),
                tags=self._coerce_list(ai_result.get("tags"), fallback=[item.platform for item in event.items]),
                watchpoints=self._coerce_list(ai_result.get("watchpoints"), fallback=["继续跟踪事件演化"]),
            )
        return self._fallback_event_summary(event)

    def summarize_daily(self, summaries: list[EventSummary]) -> str:
        system_prompt = self.prompts.load("daily_digest.txt")
        payload = {"events": [asdict(summary) for summary in summaries]}
        ai_text = self.client.complete(system_prompt, json.dumps(payload, ensure_ascii=False, indent=2))
        if ai_text:
            return ai_text.strip()
        return self._fallback_daily_summary(summaries)

    def _fallback_event_summary(self, event: Event) -> EventSummary:
        viewpoints = [comment.content for comment in event.comments[:3]] or ["暂无足够评论样本"]
        tags = unique_preserve_order([item.platform for item in event.items])
        return EventSummary(
            title=event.canonical_title,
            one_line_summary=f"{event.canonical_title} 在多个平台进入热点讨论。",
            background=f"聚合自 {', '.join(tags)} 平台热榜，当前为规则摘要。",
            controversy="当前为基础规则总结，争议焦点基于代表性评论提取。",
            viewpoints=viewpoints,
            tags=tags,
            watchpoints=["补充更多原始评论", "对比后续热度变化"],
        )

    def _fallback_daily_summary(self, summaries: list[EventSummary]) -> str:
        if not summaries:
            return "# 今日热点摘要\n\n暂无事件。\n"
        sections: list[str] = ["# 今日热点摘要\n"]
        sections.append("## 今日三大焦点")
        for index, summary in enumerate(summaries[:3], start=1):
            sections.append(f"- 焦点 {index}：{summary.one_line_summary}")
        sections.append("")
        for index, summary in enumerate(summaries, start=1):
            sections.append(
                f"## {index}. {summary.title}\n"
                f"- 一句话摘要：{summary.one_line_summary}\n"
                f"- 背景：{summary.background}\n"
                f"- 争议焦点：{summary.controversy}\n"
                f"- 主要观点：{'；'.join(summary.viewpoints)}\n"
                f"- 标签：{' / '.join(summary.tags)}\n"
                f"- 观察点：{'；'.join(summary.watchpoints)}\n"
            )
        return "\n".join(sections)

    @staticmethod
    def _coerce_list(value: object, *, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            result = [str(item).strip() for item in value if str(item).strip()]
            if result:
                return result
        return [item for item in fallback if item]
''',
    "src/dedupe/event_cluster.py": '''from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from src.ai.client import AIClient
from src.models import Event, RankingItem
from src.utils import normalize_title


class EventCluster:
    SYNONYM_MAP = {
        "usa": "united states",
        "u.s": "united states",
        "us": "united states",
        "ai": "artificial intelligence",
        "a.i": "artificial intelligence",
    }

    def __init__(
        self,
        *,
        strong_threshold: float = 0.82,
        weak_threshold: float = 0.68,
        ai_client: AIClient | None = None,
    ) -> None:
        self.strong_threshold = strong_threshold
        self.weak_threshold = weak_threshold
        self.ai_client = ai_client

    def cluster(self, items: list[RankingItem]) -> list[Event]:
        if not items:
            return []

        normalized_items = [(item, self._normalize_phrase(item.title)) for item in items]
        embeddings = self._build_embedding_map([text for _, text in normalized_items])
        events: list[Event] = []
        event_vectors: list[list[float] | None] = []

        for item, normalized_title in normalized_items:
            candidate_vector = embeddings.get(normalized_title)
            best_index: int | None = None
            best_score = 0.0
            for index, event in enumerate(events):
                event_key = self._normalize_phrase(event.canonical_title)
                score = self._similarity(
                    normalized_title,
                    event_key,
                    candidate_vector,
                    event_vectors[index],
                )
                if score > best_score:
                    best_score = score
                    best_index = index

            if best_index is not None and best_score >= self.weak_threshold:
                target = events[best_index]
                target.items.append(item)
                target.importance_score += item.heat_score_normalized or 0.0
                if (item.heat_score_normalized or 0.0) > (target.items[0].heat_score_normalized or 0.0):
                    target.canonical_title = item.title
                event_vectors[best_index] = self._merge_vectors(event_vectors[best_index], candidate_vector)
                continue

            events.append(
                Event(
                    canonical_title=item.title,
                    summary_seed=normalized_title,
                    importance_score=item.heat_score_normalized or 0.0,
                    items=[item],
                )
            )
            event_vectors.append(candidate_vector)

        return sorted(events, key=lambda event: event.importance_score, reverse=True)

    def _normalize_phrase(self, text: str) -> str:
        normalized = normalize_title(text)
        for source, target in self.SYNONYM_MAP.items():
            normalized = normalized.replace(source, target)
        normalized = re.sub(r"\b(breaking|live|latest|update|news|video|shorts|official)\b", " ", normalized)
        normalized = re.sub(r"\b(20\d{2}|19\d{2})\b", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _similarity(
        self,
        left: str,
        right: str,
        left_vector: list[float] | None,
        right_vector: list[float] | None,
    ) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0

        token_similarity = self._jaccard(self._tokens(left), self._tokens(right))
        sequence_similarity = SequenceMatcher(None, left, right).ratio()
        bigram_similarity = self._jaccard(self._ngrams(left), self._ngrams(right))
        embedding_similarity = self._cosine_similarity(left_vector, right_vector)

        score = 0.35 * token_similarity + 0.30 * sequence_similarity + 0.20 * bigram_similarity + 0.15 * embedding_similarity
        if token_similarity >= self.strong_threshold:
            return max(score, token_similarity)
        return score

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in text.split() if len(token) > 1}

    @staticmethod
    def _ngrams(text: str, size: int = 2) -> set[str]:
        compact = text.replace(" ", "")
        if len(compact) < size:
            return {compact} if compact else set()
        return {compact[index : index + size] for index in range(len(compact) - size + 1)}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        return intersection / union if union else 0.0

    @staticmethod
    def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _build_embedding_map(self, texts: list[str]) -> dict[str, list[float] | None]:
        unique_texts = list(dict.fromkeys(texts))
        if not self.ai_client:
            return {text: None for text in unique_texts}
        vectors = self.ai_client.embed(unique_texts)
        if not vectors or len(vectors) != len(unique_texts):
            return {text: None for text in unique_texts}
        return {text: vector for text, vector in zip(unique_texts, vectors)}

    @staticmethod
    def _merge_vectors(left: list[float] | None, right: list[float] | None) -> list[float] | None:
        if left and right and len(left) == len(right):
            return [(a + b) / 2 for a, b in zip(left, right)]
        return left or right
''',
    "src/main.py": '''from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.ai import AIClient, PromptRepository, Summarizer
from src.collectors import WeiboCollector, XCollector, YouTubeCollector
from src.dedupe import EventCluster
from src.normalizers import EventNormalizer
from src.selectors import CommentSelector
from src.storage import CommentRepository, Database, RankingRepository, ReportFileManager
from src.utils import configure_logging, get_logger, normalize_title

LOGGER = get_logger(__name__)


def load_settings() -> dict:
    settings_path = Path("config/settings.yaml")
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_collectors(settings: dict) -> list:
    collector_settings = settings["collector"]
    platform_settings = collector_settings.get("platforms", {})
    registry = {
        "weibo": WeiboCollector({**collector_settings, **platform_settings.get("weibo", {})}),
        "x": XCollector({**collector_settings, **platform_settings.get("x", {})}),
        "youtube": YouTubeCollector({**collector_settings, **platform_settings.get("youtube", {})}),
    }
    enabled_platforms: Iterable[str] = collector_settings["enabled_platforms"]
    return [registry[name] for name in enabled_platforms if name in registry]


def run_pipeline(report_label: str = "manual") -> Path:
    load_dotenv()
    configure_logging()
    settings = load_settings()

    database = Database()
    database.initialize()
    ranking_repo = RankingRepository(database)
    comment_repo = CommentRepository(database)
    report_manager = ReportFileManager(settings["report"]["output_dir"])

    ai_client = AIClient()
    normalizer = EventNormalizer()
    cluster = EventCluster(
        strong_threshold=settings["dedupe"]["strong_similarity_threshold"],
        weak_threshold=settings["dedupe"]["weak_similarity_threshold"],
        ai_client=ai_client,
    )
    selector = CommentSelector(
        per_event_limit=settings["selector"]["per_event_comment_limit"],
        min_text_length=settings["selector"]["min_text_length"],
    )
    summarizer = Summarizer(ai_client, PromptRepository())

    all_rankings = []
    all_comments = []
    comments_by_seed: dict[str, list] = {}
    for collector in build_collectors(settings):
        try:
            rankings = [
                normalizer.normalize_ranking(item)
                for item in collector.fetch_top_rankings(settings["collector"]["top_limit"])
            ]
        except Exception as exc:
            LOGGER.warning("collector %s ranking failed: %s", collector.platform, exc)
            rankings = []

        all_rankings.extend(rankings)
        for ranking in rankings:
            title_seed = normalize_title(ranking.title)
            try:
                comments = [
                    normalizer.normalize_comment(comment)
                    for comment in collector.fetch_comments(ranking, settings["collector"]["comment_limit"])
                ]
            except Exception as exc:
                LOGGER.warning("collector %s comments failed for %s: %s", collector.platform, ranking.title, exc)
                comments = []
            all_comments.extend(comments)
            comments_by_seed.setdefault(title_seed, []).extend(comments)

    if all_rankings:
        ranking_repo.save_many(all_rankings)
    if all_comments:
        comment_repo.save_many(all_comments)

    events = cluster.cluster(all_rankings)
    for event in events:
        related_comments = []
        for item in event.items:
            related_comments.extend(comments_by_seed.get(normalize_title(item.title), []))
        event.comments = selector.select(related_comments)

    event_summaries = [summarizer.summarize_event(event) for event in events[:10]]
    markdown = summarizer.summarize_daily(event_summaries)
    markdown_path = report_manager.write_markdown(markdown, label=report_label)

    if settings["report"]["write_json"]:
        report_manager.write_json(
            {
                "events": [asdict(summary) for summary in event_summaries],
                "markdown_path": str(markdown_path),
                "ai_configured": ai_client.is_configured(),
            },
            label=report_label,
        )

    LOGGER.info("report generated: %s", markdown_path)
    return markdown_path


if __name__ == "__main__":
    output = run_pipeline()
    print(output)
''',
    "README.md": '''# News Summary MVP

一个用于聚合多平台新闻热榜、筛选代表评论并生成 Markdown 日报的 Python 基础架构。

## 目录结构

```text
NewsSummary/
├─ .env.example
├─ README.md
├─ requirements.txt
├─ config/
│  ├─ settings.yaml
│  └─ prompts/
│     ├─ daily_digest.txt
│     └─ event_summary.txt
├─ data/
│  ├─ processed/.gitkeep
│  ├─ raw/.gitkeep
│  └─ reports/.gitkeep
└─ src/
   ├─ main.py
   ├─ scheduler.py
   ├─ ai/
   │  ├─ __init__.py
   │  ├─ client.py
   │  ├─ prompts.py
   │  └─ summarizer.py
   ├─ collectors/
   │  ├─ __init__.py
   │  ├─ base.py
   │  ├─ weibo.py
   │  ├─ x.py
   │  └─ youtube.py
   ├─ dedupe/
   │  ├─ __init__.py
   │  └─ event_cluster.py
   ├─ models/
   │  ├─ __init__.py
   │  ├─ comment.py
   │  ├─ event.py
   │  └─ ranking.py
   ├─ normalizers/
   │  ├─ __init__.py
   │  └─ event_normalizer.py
   ├─ selectors/
   │  ├─ __init__.py
   │  └─ comment_selector.py
   ├─ storage/
   │  ├─ __init__.py
   │  ├─ db.py
   │  ├─ files.py
   │  └─ repositories.py
   └─ utils/
      ├─ __init__.py
      ├─ logger.py
      ├─ retry.py
      └─ text.py
```

## 当前实现范围

当前代码实现的是“基础架构 + 最小可用抓取链路”，不是完整商业级产品：

- 定义了统一的数据模型
- 定义了采集器抽象接口，并提供微博 / X / YouTube 的真实网络抓取方案
- 实现了标准化、规则+相似度去重、评论筛选、摘要拼装的基础流程
- 提供 SQLite 初始化与基础 Repository
- 提供可配置的 OpenAI 兼容客户端
- 提供手动运行入口和 APScheduler 定时入口
- 提供配置文件、Prompt 模板和环境变量样例

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 复制环境变量文件并按需修改

```bash
copy .env.example .env
```

3. 不配置 AI 也可以直接跑通基础流程

```bash
python -m src.main
```

4. 配置 AI 后再次执行，可得到模型生成的事件总结和日报

```bash
python -m src.main
```

5. 启动本地调度器

```bash
python -m src.scheduler
```

## 你需要配置的 AI 项

至少填写以下三个：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL_NAME`

可选增强：

- `EMBEDDING_MODEL`：用于更强的事件去重语义相似度
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`
- `OPENAI_TEMPERATURE`

## 说明

- 微博采集：使用公开热搜接口 + 搜索结果帖子作为评论观点样本。
- X 采集：使用 Trends24 获取趋势词，使用 Nitter RSS 获取讨论样本。
- YouTube 采集：使用 Invidious 公共接口获取趋势视频和评论样本。
- 如果第三方来源暂时不可访问，系统会自动降级为占位数据而不是直接崩溃。
''',
}

for relative_path, content in FILES.items():
    path = Path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

print(f"updated {len(FILES)} files")
