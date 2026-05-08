"""過去の Daily ノートから週報・月報をバックフィル生成するスクリプト

使い方:
    # 週報を指定して生成
    python .scripts/backfill_reports.py --weeks 2026-W11 2026-W12 2026-W13

    # 月報を指定して生成
    python .scripts/backfill_reports.py --months 2026-03 2026-04

    # 両方まとめて指定
    python .scripts/backfill_reports.py --weeks 2026-W11 --months 2026-03
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_utils import generate_weekly_report, generate_monthly_report

WEEK_RE = re.compile(r'^(\d{4})-W(\d{1,2})$')
MONTH_RE = re.compile(r'^(\d{4})-(\d{2})$')


def parse_week(s):
    m = WEEK_RE.match(s)
    if not m:
        raise argparse.ArgumentTypeError(f"週は YYYY-WNN 形式で指定してください（例: 2026-W11）: {s!r}")
    return int(m.group(1)), int(m.group(2))


def parse_month(s):
    m = MONTH_RE.match(s)
    if not m:
        raise argparse.ArgumentTypeError(f"月は YYYY-MM 形式で指定してください（例: 2026-03）: {s!r}")
    return int(m.group(1)), int(m.group(2))


def main():
    parser = argparse.ArgumentParser(
        description="Daily ノートから週報・月報をバックフィル生成する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--weeks", nargs="+", type=parse_week, metavar="YYYY-WNN",
        help="生成する週報（例: 2026-W11 2026-W12）",
    )
    parser.add_argument(
        "--months", nargs="+", type=parse_month, metavar="YYYY-MM",
        help="生成する月報（例: 2026-03 2026-04）",
    )
    args = parser.parse_args()

    if not args.weeks and not args.months:
        parser.print_help()
        sys.exit(1)

    if args.weeks:
        print("=== Backfill weekly reports ===")
        for year, week in args.weeks:
            generate_weekly_report(year, week)

    if args.months:
        print("\n=== Backfill monthly reports ===")
        for year, month in args.months:
            generate_monthly_report(year, month)

    print("\nBackfill complete!")


if __name__ == "__main__":
    main()
