from __future__ import annotations

import time

from apscheduler.schedulers.blocking import BlockingScheduler

from src.main import run_pipeline
from src.utils import configure_logging, get_logger

LOGGER = get_logger(__name__)


def start_scheduler() -> None:
    configure_logging()
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(run_pipeline, "cron", minute=0, id="hourly-cache")
    scheduler.add_job(run_pipeline, "cron", hour=8, minute=0, kwargs={"report_label": "morning"}, id="morning-report")
    scheduler.add_job(run_pipeline, "cron", hour=20, minute=0, kwargs={"report_label": "evening"}, id="evening-report")
    LOGGER.info("scheduler started")
    scheduler.start()


if __name__ == "__main__":
    try:
        start_scheduler()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("scheduler stopped")
        time.sleep(0.1)
