"""CLIからntfy.sh通知を送信するユーティリティ

使い方:
    python .scripts/notify.py "タイトル" path/to/file.md
    python .scripts/notify.py "タイトル" --message "本文テキスト"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_utils import _send_ntfy


def main():
    parser = argparse.ArgumentParser(description="Send ntfy.sh notification")
    parser.add_argument("title", help="Notification title")
    parser.add_argument("file", nargs="?", help="File to send as body")
    parser.add_argument("--message", "-m", help="Message body (used if file not specified)")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        body = path.read_text(encoding="utf-8").strip()
    elif args.message:
        body = args.message
    else:
        print("Either file or --message is required.")
        sys.exit(1)

    _send_ntfy(args.title, body)


if __name__ == "__main__":
    main()
