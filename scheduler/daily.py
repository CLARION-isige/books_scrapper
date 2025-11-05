import json
import os
from datetime import datetime, timezone
import subprocess
from apscheduler.schedulers.blocking import BlockingScheduler
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
CHANGES_COL = os.getenv("MONGO_CHANGES_COLLECTION")

REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")


def run_crawl():
    # Run Scrapy spider with resume support and info logs
    subprocess.run(
        [
            "scrapy",
            "crawl",
            "books",
            "-s",
            "JOBDIR=.job/books_daily",
            "-s",
            "LOG_LEVEL=INFO",
        ],
        cwd=os.path.join(os.path.dirname(__file__), "..", "web_crawler"),
        check=True,
    )


def generate_daily_report():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    today = datetime.now(timezone.utc).date()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    # find changes since start of day
    changes = list(
        db[CHANGES_COL]
        .find({"changed_at": {"$gte": start}}, {"_id": 0})
        .sort("changed_at", 1)
    )
    report_path = os.path.join(REPORTS_DIR, f"changes_{today.isoformat()}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": today.isoformat(),
                "count": len(changes),
                "changes": changes,
            },
            f,
            ensure_ascii=False,
            indent=2,
            default=lambda o: o.isoformat() if isinstance(o, datetime) else o,  # ✅ key fix
        )
    client.close()
    return report_path


def job():
    run_crawl()
    path = generate_daily_report()
    print(f"Daily crawl completed. Report: {path}")


if __name__ == "__main__":
    sched = BlockingScheduler(timezone="UTC")
    # schedule once a day at 02:00 UTC
    sched.add_job(job, "cron", hour=2, minute=0)
    print("Scheduler started. Next run at 02:00 UTC")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
