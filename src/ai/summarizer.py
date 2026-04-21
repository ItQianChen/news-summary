from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict

from src.ai.client import AIClient
from src.ai.prompts import PromptRepository
from src.models import Event, EventPlatformItem, EventReport, EventSummary
from src.utils import format_markdown_link, unique_preserve_order


class Summarizer:
    def __init__(self, client: AIClient, prompts: PromptRepository) -> None:
        self.client = client
        self.prompts = prompts

    def summarize_event_report(self, event: Event) -> EventReport:
        try:
            summary = self.summarize_event(event)
        except Exception:
            summary = self._fallback_event_summary(event)
        return self.build_event_report(event, summary)

    def summarize_event(self, event: Event) -> EventSummary:
        system_prompt = self.prompts.load("event_summary.txt")
        viewpoint_limit = 10
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
                for comment in event.comments[:viewpoint_limit]
            ],
        }
        ai_result = self.client.complete_json(system_prompt, json.dumps(payload, ensure_ascii=False, indent=2))
        if ai_result:
            return EventSummary(
                title=event.canonical_title,
                one_line_summary=str(ai_result.get("one_line_summary") or f"{event.canonical_title} 引发多平台讨论。"),
                background=str(ai_result.get("background") or "输入信息不足，暂无更多可靠背景。"),
                controversy=str(ai_result.get("controversy") or "暂无足够信息判断主要争议焦点。"),
                viewpoints=self._coerce_list(
                    ai_result.get("viewpoints"),
                    fallback=[comment.content for comment in event.comments[:10]],
                ),
                tags=self._coerce_list(ai_result.get("tags"), fallback=[item.platform for item in event.items]),
                watchpoints=self._coerce_list(ai_result.get("watchpoints"), fallback=["继续跟踪事件演化"]),
            )
        return self._fallback_event_summary(event)

    def build_event_report(self, event: Event, summary: EventSummary) -> EventReport:
        platform_items = [
            EventPlatformItem(
                platform=item.platform,
                rank_index=item.rank_index,
                title=item.title,
                url=item.url,
                heat_score=item.heat_score_raw,
            )
            for item in sorted(event.items, key=lambda item: (item.platform, item.rank_index, item.title))
        ]
        return EventReport(summary=summary, platform_items=platform_items)

    def summarize_daily(self, reports: list[EventReport], focus_limit: int = 10, mode: str = "rule") -> str:
        normalized_mode = (mode or "rule").strip().lower()
        if normalized_mode == "ai":
            return self._ai_daily_summary(reports, focus_limit=focus_limit)
        return self._fallback_daily_summary(reports, focus_limit=focus_limit)

    def summarize_daily_variants(self, reports: list[EventReport], focus_limit: int = 10, mode: str = "rule") -> dict[str, str]:
        normalized_mode = (mode or "rule").strip().lower()
        if normalized_mode == "all":
            return {
                "rule": self._fallback_daily_summary(reports, focus_limit=focus_limit),
                "ai": self._ai_daily_summary(reports, focus_limit=focus_limit),
            }
        if normalized_mode == "ai":
            return {"ai": self._ai_daily_summary(reports, focus_limit=focus_limit)}
        return {"rule": self._fallback_daily_summary(reports, focus_limit=focus_limit)}

    def _fallback_event_summary(self, event: Event) -> EventSummary:
        viewpoints = [comment.content for comment in event.comments[:10]] or ["暂无足够评论样本"]
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

    def _ai_daily_summary(self, reports: list[EventReport], *, focus_limit: int) -> str:
        fallback_markdown = self._fallback_daily_summary(reports, focus_limit=focus_limit)
        if not reports:
            return fallback_markdown

        system_prompt = self.prompts.load("daily_digest.txt")
        payload = {
            "focus_limit": max(focus_limit, 0),
            "platforms": self._build_daily_payload(reports, focus_limit=focus_limit),
        }
        markdown = self.client.complete(system_prompt, json.dumps(payload, ensure_ascii=False, indent=2))
        if markdown.strip():
            return markdown.strip()
        return fallback_markdown

    def _build_daily_payload(self, reports: list[EventReport], *, focus_limit: int) -> list[dict[str, object]]:
        platform_groups = self._build_platform_groups(reports)
        payload: list[dict[str, object]] = []
        normalized_focus_limit = max(focus_limit, 0)

        for platform, entries in platform_groups.items():
            sorted_entries = self._sort_platform_entries(entries)
            focus_entries = sorted_entries[:normalized_focus_limit] if normalized_focus_limit else []
            payload.append(
                {
                    "platform": platform,
                    "focus_limit": normalized_focus_limit,
                    "focus_count": len(focus_entries),
                    "focuses": [
                        {
                            "title": entry["summary"].title,
                            "one_line_summary": entry["summary"].one_line_summary,
                            "rank_index": entry["platform_item"].rank_index,
                            "heat_score": entry["platform_item"].heat_score,
                        }
                        for entry in focus_entries
                    ],
                    "items": [
                        {
                            "title": entry["summary"].title,
                            "one_line_summary": entry["summary"].one_line_summary,
                            "background": entry["summary"].background,
                            "controversy": entry["summary"].controversy,
                            "viewpoints": entry["summary"].viewpoints,
                            "tags": entry["summary"].tags,
                            "watchpoints": entry["summary"].watchpoints,
                            "rank_index": entry["platform_item"].rank_index,
                            "heat_score": entry["platform_item"].heat_score,
                            "url": entry["platform_item"].url,
                        }
                        for entry in sorted_entries
                    ],
                }
            )
        return payload

    def _fallback_daily_summary(self, reports: list[EventReport], *, focus_limit: int) -> str:
        if not reports:
            return "# 今日热点摘要\n\n暂无事件。\n"

        platform_groups = self._build_platform_groups(reports)
        if not platform_groups:
            return "# 今日热点摘要\n\n暂无事件。\n"

        normalized_focus_limit = max(focus_limit, 0)
        sections: list[str] = ["# 今日热点摘要", ""]

        for platform, entries in platform_groups.items():
            sorted_entries = self._sort_platform_entries(entries)
            focus_entries = sorted_entries[:normalized_focus_limit] if normalized_focus_limit else []

            sections.append(f"## 渠道：{platform}")
            if focus_entries:
                sections.append(f"### 今日{len(focus_entries)}大焦点")
                for index, entry in enumerate(focus_entries, start=1):
                    summary = entry["summary"]
                    sections.append(f"- 焦点 {index}：{summary.one_line_summary}")
            else:
                sections.append("### 今日焦点")
                sections.append("- 未配置焦点数量，跳过焦点导读。")
            sections.append("")

            for index, entry in enumerate(sorted_entries, start=1):
                summary = entry["summary"]
                item = entry["platform_item"]
                sections.append(f"### {index}. {summary.title}")
                sections.append(f"- 一句话摘要：{summary.one_line_summary}")
                sections.append(f"- 渠道：{item.platform}")
                sections.append(f"- 排名：#{item.rank_index}")
                sections.append(f"- 热度：{item.heat_score or '暂无'}")
                sections.append(f"- 链接：{format_markdown_link(item.url, item.title)}")
                sections.append(f"- 背景：{summary.background}")
                sections.append(f"- 争议焦点：{summary.controversy}")
                sections.append(f"- 主要观点：{'；'.join(summary.viewpoints)}")
                sections.append(f"- 标签：{' / '.join(summary.tags)}")
                sections.append(f"- 观察点：{'；'.join(summary.watchpoints)}")
                sections.append("")

        return "\n".join(sections)

    @staticmethod
    def _build_platform_groups(reports: list[EventReport]) -> OrderedDict[str, list[dict[str, object]]]:
        platform_groups: OrderedDict[str, list[dict[str, object]]] = OrderedDict()
        for report in reports:
            for item in report.platform_items:
                platform_groups.setdefault(item.platform, []).append(
                    {
                        "summary": report.summary,
                        "platform_item": item,
                    }
                )
        return platform_groups

    @staticmethod
    def _sort_platform_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
        return sorted(
            entries,
            key=lambda entry: (
                int(entry["platform_item"].rank_index),
                str(entry["summary"].title),
            ),
        )

    @staticmethod
    def _coerce_list(value: object, *, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            result = [str(item).strip() for item in value if str(item).strip()]
            if result:
                return result
        return [item for item in fallback if item]
