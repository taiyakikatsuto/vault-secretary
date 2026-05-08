import os
import re
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from kanban_utils import archive_done_tasks, ensure_task_cards_for_unlinked
from report_utils import _send_ntfy
from secretary_config import user_name

# 設定
VAULT_ROOT = Path(__file__).parent.parent
INBOX_DIR = VAULT_ROOT / "Inbox"
DAILY_DIR = VAULT_ROOT / "Diary" / "Daily"
ARCHIVE_BASE = INBOX_DIR / "archived"
JST = timezone(timedelta(hours=9))

# Thinoファイル判定: YYYY-MM-DD.md 形式
THINO_FILENAME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\.md$')
# Thinoエントリの開始行: "- HH:MM:SS" or "- HH:MM" or "- [x] HH:MM:SS"
THINO_ENTRY_RE = re.compile(r'^- (?:\[.\] )?(\d{2}):(\d{2})(?::(\d{2}))?')
BOUNDARY_HOUR = int(os.environ.get("DAILY_BOUNDARY_HOUR", "7"))


def get_todays_inbox_files(date_str):
    """指定日付のInboxファイルをgit履歴から取得（Thinoファイルは除外）"""
    window_end = datetime.fromisoformat(date_str).replace(
        hour=BOUNDARY_HOUR, minute=0, second=0, microsecond=0, tzinfo=JST
    )
    window_start = window_end - timedelta(days=1)

    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "log", "--format=%ai",
         "--diff-filter=A", "--name-only", "--", "Inbox/*.md"],
        capture_output=True, text=True, cwd=VAULT_ROOT
    )

    files = []
    current_date = None

    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("20"):
            try:
                current_date = datetime.fromisoformat(line).astimezone(JST)
            except ValueError:
                current_date = None
        elif line.startswith("Inbox/") and current_date is not None:
            if window_start <= current_date < window_end:
                filepath = VAULT_ROOT / line
                if filepath.exists() and filepath.suffix == ".md":
                    # Thinoファイルは別処理するので除外
                    if THINO_FILENAME_RE.match(filepath.name):
                        continue
                    files.append(filepath)

    return files


def get_thino_entries_in_window(date_str):
    """Thinoファイルからwindow内のエントリだけ抽出する（ファイルは移動しない）

    window: 前日7:00 〜 当日7:00
    - 前日ファイル（daily_date_str.md）の 7:00〜23:59 のエントリ
    - 当日ファイル（date_str.md）の 0:00〜6:59 のエントリ
    """
    window_end = datetime.fromisoformat(date_str).replace(
        hour=BOUNDARY_HOUR, minute=0, second=0, microsecond=0, tzinfo=JST
    )
    window_start = window_end - timedelta(days=1)
    daily_date_str = window_start.strftime("%Y-%m-%d")

    entries = []

    # 前日ファイル: 7:00〜23:59 のエントリ
    prev_file = INBOX_DIR / f"{daily_date_str}.md"
    if prev_file.exists():
        for hour, text in _parse_thino_entries(prev_file):
            if hour >= BOUNDARY_HOUR:
                entries.append(text)

    # 当日ファイル: 0:00〜6:59 のエントリ
    next_file = INBOX_DIR / f"{date_str}.md"
    if next_file.exists():
        for hour, text in _parse_thino_entries(next_file):
            if hour < BOUNDARY_HOUR:
                entries.append(text)

    return entries, daily_date_str


def _parse_thino_entries(filepath):
    """Thinoファイルをエントリ単位でパースする。
    Returns: list of (hour, entry_text) タプル
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    result = []
    current_hour = None
    current_lines = []

    for line in lines:
        match = THINO_ENTRY_RE.match(line)
        if match:
            if current_hour is not None:
                result.append((current_hour, "\n".join(current_lines)))
            current_hour = int(match.group(1))
            current_lines = [line]
        elif current_hour is not None:
            current_lines.append(line)

    if current_hour is not None:
        result.append((current_hour, "\n".join(current_lines)))

    return result


def read_files(files):
    """ファイル内容を結合して読み込む"""
    contents = []
    for f in files:
        text = f.read_text(encoding="utf-8").strip()
        if text:
            contents.append(f"=== {f.name} ===\n{text}")
    return "\n\n".join(contents)


_DAILY_SYSTEM_TEMPLATE = """\
あなたは本人を傍で観察していた秘書として、Inboxのメモ群を元に日次ノートを生成します。
Thinoのつぶやき（自然言語の日記的メモ）と、Claudeとユーザーが共同作業した際の作業レポート（技術的な改修記録など）の両方が含まれます。

# 出力フォーマット

1行目は `# YYYY-MM-DD` 形式のMarkdown見出し（入力で渡された日付をそのまま使う）。

## 概要

（秘書視点・三人称・常体で、本人の1日を記録する文章。
時系列に縛らず、話題ごとに段落でまとめてよい。
重要なことは段落を厚く、些末なことは軽く流すか省略する。
情報の強弱は段落の厚みと配置で表現する）

## sources

（元ファイル名をリスト）

# 視点と文体
- **秘書視点・三人称・常体**で書く。「{USER_NAME}さんは〜した」「本人は〜と言っていた」のような、外から観察した距離感
- 本人の内面・感情は**絶対に推測しない**。「〜と感じたのだろう」「〜が嬉しかったようだ」「〜に違和感があった様子」など、心の中を代弁する表現は禁止
- 本人の発言・つぶやきは**引用として残す**。「『〜』とつぶやいていた」「本人いわく『〜』」のように、観測された事実として書く
- 多少の温かみはあってよいが、それは**事実の選び方や言葉の柔らかさ**で出すこと。内面に踏み込んで温かみを演出してはいけない

# 重要なルール
- 時系列の流れに無理やり乗せない。話題ごとにまとめたほうが読みやすければそうする
- タグ分類・タスク抽出・Knowledge抽出は**一切しない**（それは goodnight で対話しながらやる）
- `#task` `#knowledge` `#experience` `#ideas` のようなタグ付きセクションは**作らない**
- AIっぽい定型（「今後の展開が注目されます」「〜が期待されます」等）は避ける
- Obsidianのwikiリンク [[]] は関連ノートがあるときだけ使う。無理に張らない
- **Claude作業レポートの扱い**: 技術的な詳細（コード、設定値、実装手順など）は Daily に書かない。「Claudeとこういう改修をした」「〜という方針が決まった」くらいの粒度に留める。細かい技術情報は goodnight が Knowledge ノートに育成する役割なので、Daily では省略する
- **出力は本文のみ**。全体を ```markdown ... ``` のコードブロックで囲んだり、先頭・末尾に `---` の区切り線を置いたりしない（Obsidianでそのままマークダウンとして読みたいので）\
"""

_DAILY_SYSTEM = _DAILY_SYSTEM_TEMPLATE.replace("{USER_NAME}", user_name())


def generate_daily(raw_content, date_str):
    """Claude APIでDailyノートを生成"""
    client = anthropic.Anthropic()

    user_message = f"日付: {date_str}\n\n# Inboxの内容\n{raw_content}"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[{"type": "text", "text": _DAILY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


def archive_files(files, date_str):
    """処理済みファイルをarchiveに移動（Thinoファイルは含まれない）"""
    year_month = date_str[:7]  # YYYY-MM
    archive_dir = ARCHIVE_BASE / year_month
    archive_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        dest = archive_dir / f.name
        if dest.exists():
            dest = archive_dir / \
                f"{f.stem}_{datetime.now().strftime('%H%M%S')}{f.suffix}"
        f.rename(dest)
        print(f"Archived: {f.name} → {dest}")


def archive_old_thino_files(date_str):
    """Thinoファイルのうち、当日・前日以外をarchiveに移動"""
    today = datetime.fromisoformat(date_str).date()
    yesterday = today - timedelta(days=1)
    keep = {today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")}

    for f in INBOX_DIR.glob("*.md"):
        if not THINO_FILENAME_RE.match(f.name):
            continue
        stem = f.stem
        if stem in keep:
            continue
        year_month = stem[:7]
        archive_dir = ARCHIVE_BASE / year_month
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / f.name
        if dest.exists():
            dest = archive_dir / \
                f"{f.stem}_{datetime.now().strftime('%H%M%S')}{f.suffix}"
        f.rename(dest)
        print(f"Archived Thino: {f.name} → {dest}")


def main():
    now = datetime.now(JST)
    if now.hour >= 12:
        date_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_str = now.strftime("%Y-%m-%d")

    window_start = datetime.fromisoformat(date_str).replace(
        hour=BOUNDARY_HOUR, minute=0, second=0, microsecond=0, tzinfo=JST
    ) - timedelta(days=1)
    daily_date_str = window_start.strftime("%Y-%m-%d")

    print(f"Daily batch start: {daily_date_str}")

    # 通常のInboxファイル収集（Thinoファイルは除外済み）
    files = get_todays_inbox_files(date_str)

    # Thinoエントリをタイムスタンプベースで収集（ファイルは移動しない）
    thino_entries, _ = get_thino_entries_in_window(date_str)

    # 内容を結合
    raw_parts = []

    # 通常ファイルの内容
    file_content = read_files(files)
    if file_content:
        raw_parts.append(file_content)

    # Thinoエントリの内容
    if thino_entries:
        thino_content = f"=== Thino ({daily_date_str}) ===\n" + "\n".join(thino_entries)
        raw_parts.append(thino_content)
        print(f"Found {len(thino_entries)} Thino entries in window.")

    raw_content = "\n\n".join(raw_parts)

    if not raw_content:
        print("No inbox files or Thino entries today. Skipping.")
        sys.exit(0)

    print(f"Found {len(files)} inbox files + {len(thino_entries)} Thino entries.")

    # Daily生成
    print("Generating daily note...")
    daily_content = generate_daily(raw_content, daily_date_str)

    # Daily保存（YYYY-MM/YYYY-MM-DD.md）
    month_dir = DAILY_DIR / daily_date_str[:7]
    month_dir.mkdir(parents=True, exist_ok=True)
    daily_path = month_dir / f"{daily_date_str}.md"
    daily_path.write_text(daily_content, encoding="utf-8")
    print(f"Saved: {daily_path}")

    # 通常ファイルだけarchive（Thinoファイルはそのまま残る）
    archive_files(files, daily_date_str)

    # Thinoファイルは当日・前日分だけ残して、それ以外をarchive
    archive_old_thino_files(date_str)

    # Kanban上のリンクなしタスクにカードを作成してwikilink化
    linked_tasks = ensure_task_cards_for_unlinked()
    if linked_tasks:
        print(f"Linked {len(linked_tasks)} unlinked tasks.")

    # KanbanのDone列を整理（完了タスクをTasks/Done/へ移動）
    archived_tasks = archive_done_tasks()
    if archived_tasks:
        print(f"Archived {len(archived_tasks)} done tasks.")

    # ntfy.sh 通知（日報の内容をまるごと送信）
    _send_ntfy(f"Vault 日報 {daily_date_str}", daily_content)

    print("Daily batch complete!")


if __name__ == "__main__":
    main()
