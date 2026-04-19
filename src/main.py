from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.ai import AIClient, PromptRepository, Summarizer
from src.collectors import BilibiliCollector, DouyinCollector, WeiboCollector, XCollector, YouTubeCollector
from src.dedupe import EventCluster
from src.models import Event
from src.normalizers import EventNormalizer
from src.selectors import CommentSelector
from src.storage import CommentRepository, Database, RankingRepository, ReportFileManager
from src.utils import configure_logging, get_logger, normalize_title

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class PlatformCollectionResult:
    rankings: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    comments_by_seed: dict[str, list] = field(default_factory=dict)


def load_settings() -> dict:
    settings_path = Path("config/settings.yaml")
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_collectors(settings: dict) -> list:
    collector_settings = settings["collector"]
    platform_settings = collector_settings.get("platforms", {})
    registry = {
        "bilibili": BilibiliCollector({**collector_settings, **platform_settings.get("bilibili", {})}),
        "douyin": DouyinCollector({**collector_settings, **platform_settings.get("douyin", {})}),
        "weibo": WeiboCollector({**collector_settings, **platform_settings.get("weibo", {})}),
        "x": XCollector({**collector_settings, **platform_settings.get("x", {})}),
        "youtube": YouTubeCollector({**collector_settings, **platform_settings.get("youtube", {})}),
    }
    enabled_platforms: Iterable[str] = collector_settings.get("enabled_platforms") or list(registry.keys())
    return [registry[name] for name in enabled_platforms if name in registry]


def _collect_platform_data(collector, settings: dict) -> PlatformCollectionResult:
    normalizer = EventNormalizer()
    result = PlatformCollectionResult()
    LOGGER.info("collector %s started", collector.platform)
    try:
        rankings = [
            normalizer.normalize_ranking(item)
            for item in collector.fetch_top_rankings(settings["collector"]["top_limit"])
        ]
    except Exception as exc:
        LOGGER.warning("collector %s ranking failed: %s", collector.platform, exc)
        rankings = []

    result.rankings.extend(rankings)
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
        result.comments.extend(comments)
        result.comments_by_seed.setdefault(title_seed, []).extend(comments)

    LOGGER.info(
        "collector %s finished with %s rankings and %s comments",
        collector.platform,
        len(result.rankings),
        len(result.comments),
    )
    return result


async def _collect_all_platform_data(collectors: list, settings: dict) -> list[PlatformCollectionResult]:
    if not collectors:
        return []

    collector_settings = settings["collector"]
    if not collector_settings.get("concurrent_platforms", True):
        return [_collect_platform_data(collector, settings) for collector in collectors]

    max_platform_workers = max(int(collector_settings.get("max_platform_workers") or len(collectors)), 1)
    semaphore = asyncio.Semaphore(min(max_platform_workers, len(collectors)))
    LOGGER.info(
        "collectors running concurrently: %s (max_workers=%s)",
        ", ".join(collector.platform for collector in collectors),
        min(max_platform_workers, len(collectors)),
    )

    async def run_for_collector(collector) -> PlatformCollectionResult:
        async with semaphore:
            return await asyncio.to_thread(_collect_platform_data, collector, settings)

    return await asyncio.gather(*(run_for_collector(collector) for collector in collectors))


def _summarize_event_report(summarizer: Summarizer, event: Event):
    return summarizer.summarize_event_report(event)


async def _summarize_all_events(events: list[Event], summarizer: Summarizer, settings: dict) -> list:
    if not events:
        return []

    ai_settings = settings.get("ai", {})
    if not ai_settings.get("concurrent_event_summaries", True):
        return [_summarize_event_report(summarizer, event) for event in events]

    max_summary_workers = max(int(ai_settings.get("max_summary_workers") or len(events)), 1)
    worker_count = min(max_summary_workers, len(events))
    semaphore = asyncio.Semaphore(worker_count)
    LOGGER.info("event summaries running concurrently: %s (max_workers=%s)", len(events), worker_count)

    async def run_for_event(event: Event):
        async with semaphore:
            return await asyncio.to_thread(_summarize_event_report, summarizer, event)

    return await asyncio.gather(*(run_for_event(event) for event in events))


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

    collectors = build_collectors(settings)
    platform_results = asyncio.run(_collect_all_platform_data(collectors, settings))

    all_rankings = []
    all_comments = []
    comments_by_seed: dict[str, list] = {}
    for result in platform_results:
        all_rankings.extend(result.rankings)
        all_comments.extend(result.comments)
        for title_seed, comments in result.comments_by_seed.items():
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

    event_reports = asyncio.run(_summarize_all_events(events, summarizer, settings))

    markdown = summarizer.summarize_daily(event_reports, focus_limit=settings["report"].get("focus_limit", 10))
    markdown_path = report_manager.write_markdown(markdown, label=report_label)

    if settings["report"]["write_json"]:
        report_manager.write_json(
            {
                "events": [asdict(report) for report in event_reports],
                "event_count": len(event_reports),
                "source_item_count": len(all_rankings),
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
