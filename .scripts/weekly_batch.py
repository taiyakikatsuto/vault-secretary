import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from report_utils import generate_weekly_report, generate_monthly_report, _send_ntfy

VAULT_ROOT = Path(__file__).parent.parent
INBOX_DIR = VAULT_ROOT / "Inbox"
JST = timezone(timedelta(hours=9))


def archive_old_thino_files(days_threshold=14):
    """2週間以上前のThinoファイルをarchiveに移動"""
    today = datetime.now(JST).date()
    thino_re = re.compile(r'^(\d{4}-\d{2}-\d{2})\.md$')

    for f in INBOX_DIR.glob("*.md"):
        match = thino_re.match(f.name)
        if not match:
            continue
        file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        if (today - file_date).days >= days_threshold:
            year_month = match.group(1)[:7]
            archive_dir = INBOX_DIR / "archived" / year_month
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / f.name
            f.rename(dest)
            print(f"  Archived old Thino: {f.name} → {dest}")


def notify_reports(year, week, weekly_result, monthly_result):
    """ntfy.sh で週報・月報の生成を通知"""
    if weekly_result:
        content = weekly_result.read_text(encoding="utf-8").strip()
        _send_ntfy(f"Vault 週報 {year}-W{week:02d}", content)

    if monthly_result:
        content = monthly_result.read_text(encoding="utf-8").strip()
        _send_ntfy(f"Vault 月報 {monthly_result.stem}", content)


def main():
    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    print(f"Weekly batch start: {today}")

    archive_old_thino_files()

    last_week = now - timedelta(weeks=1)
    year, week, _ = last_week.isocalendar()
    print(f"Generating weekly report for {year}-W{week:02d}...")
    weekly_result = generate_weekly_report(year, week)

    monthly_result = None
    last_week_date = last_week.date()
    if last_week_date.month != now.date().month:
        prev_year = last_week_date.year
        prev_month = last_week_date.month
        print(f"Generating monthly report for {prev_year}-{prev_month:02d}...")
        monthly_result = generate_monthly_report(prev_year, prev_month)

    notify_reports(year, week, weekly_result, monthly_result)

    print("Weekly batch complete!")


if __name__ == "__main__":
    main()
