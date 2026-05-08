"""
kanban_utils.py
Kanbanボードとタスクカードの共通ユーティリティ
"""
import re
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

VAULT_ROOT = Path(__file__).parent.parent
TASKS_DIR = VAULT_ROOT / "Tasks"
WAITING_DIR = TASKS_DIR / "Waiting"
DONE_DIR = TASKS_DIR / "Done"
KANBAN_PATH = TASKS_DIR / "_index.md"
JST = timezone(timedelta(hours=9))

KANBAN_COLUMNS = ["Inbox", "Todo", "Done"]

# ファイル名に使えない文字を置換
_SANITIZE_RE = re.compile(r'[\\/:*?"<>|]')


def clean_task_name(name):
    """タスク名からwikilink・markdownリンク・バッククォートを除去してファイル名向けに整形"""
    # [[text|alias]] → alias, [[text]] → text
    cleaned = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', name)
    cleaned = re.sub(r'\[\[([^\]]+)\]\]', r'\1', cleaned)
    # [text](url) → text
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cleaned)
    # バッククォート除去
    cleaned = cleaned.replace('`', '')
    return cleaned.strip()


def sanitize_filename(name):
    """タスク名をファイル名として安全な文字列に変換"""
    cleaned = clean_task_name(name)
    return _SANITIZE_RE.sub("_", cleaned).strip()


def get_existing_task_names():
    """Waiting/ のカードファイル名一覧を取得（拡張子なし）"""
    if not WAITING_DIR.exists():
        return []
    return [f.stem for f in WAITING_DIR.glob("*.md")]


def create_task_card(name, metadata):
    """タスクカードファイルを Tasks/Waiting/ に作成

    ファイル名はwikilink等を除去した安全な名前。
    元のタスク名（wikilink付き）は本文に保持する。

    Returns: True if created, False if already exists
    """
    WAITING_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(name)
    filepath = WAITING_DIR / f"{safe_name}.md"
    if filepath.exists():
        return False

    lines = ["---"]
    for key in ["estimated", "priority", "urgency", "context", "due", "source", "created"]:
        if key == "created":
            lines.append(f"created: {datetime.now(JST).strftime('%Y-%m-%d')}")
        elif key == "source":
            lines.append(f'source: "{metadata.get(key, "")}"')
        elif key in metadata:
            lines.append(f"{key}: {metadata[key]}")
    lines.append("---")

    # 元の名前にwikilink等が含まれていれば本文に保存
    if name != safe_name:
        lines.append(f"\n{name}")
    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return True


def parse_kanban_sections(content):
    """Kanbanファイルの内容をセクションごとにパースする

    Returns: dict[section_name, list[str]]
    """
    sections = {}
    current_section = None

    for line in content.split("\n"):
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
        elif current_section and line.strip().startswith("- ["):
            sections[current_section].append(line.strip())
        elif line.startswith("%% kanban:settings"):
            break

    return sections


def extract_wikilinks(entries):
    """カードエントリから [[ファイル名]] を抽出"""
    names = []
    for entry in entries:
        match = re.search(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', entry)
        if match:
            names.append(match.group(1))
    return names


def rebuild_kanban(sections):
    """セクション辞書からKanbanファイルを再構築"""
    lines = [
        "---",
        "kanban-plugin: board",
        "---",
        "",
    ]

    for col in KANBAN_COLUMNS:
        lines.append(f"## {col}")
        lines.append("")
        for entry in sections.get(col, []):
            lines.append(entry)
        lines.append("")
        lines.append("")

    collapse = [col == "Done" for col in KANBAN_COLUMNS]
    settings = {"kanban-plugin": "board", "list-collapse": collapse}
    lines.append("%% kanban:settings")
    lines.append("```")
    lines.append(json.dumps(settings))
    lines.append("```")
    lines.append("%%")

    KANBAN_PATH.write_text("\n".join(lines), encoding="utf-8")


def add_to_kanban_inbox(task_names):
    """Kanban の Inbox セクションにタスクを追記"""
    if not KANBAN_PATH.exists():
        sections = {col: [] for col in KANBAN_COLUMNS}
    else:
        content = KANBAN_PATH.read_text(encoding="utf-8")
        sections = parse_kanban_sections(content)

    existing_links = set()
    for col in KANBAN_COLUMNS:
        existing_links.update(extract_wikilinks(sections.get(col, [])))

    for name in task_names:
        safe_name = sanitize_filename(name)
        if safe_name not in existing_links:
            sections.setdefault("Inbox", []).append(f"- [ ] [[{safe_name}]]")

    rebuild_kanban(sections)


def ensure_task_cards_for_unlinked():
    """Kanban上にwikilinkなしで書かれたタスクを検出し、カードを作成してwikilinkに変換する

    Returns: list of task names that were converted
    """
    if not KANBAN_PATH.exists():
        return []

    content = KANBAN_PATH.read_text(encoding="utf-8")
    sections = parse_kanban_sections(content)

    converted = []
    wikilink_re = re.compile(r'\[\[.+?\]\]')
    # チェックボックス後のタスク名を取得: "- [ ] タスク名" or "- [x] タスク名"
    task_text_re = re.compile(r'^- \[.\] (.+)$')

    for col in KANBAN_COLUMNS:
        entries = sections.get(col, [])
        new_entries = []
        for entry in entries:
            if wikilink_re.search(entry):
                # 既にwikilink付き → そのまま
                new_entries.append(entry)
                continue

            match = task_text_re.match(entry)
            if not match:
                new_entries.append(entry)
                continue

            task_name = match.group(1).strip()
            safe_name = sanitize_filename(task_name)

            # 列に応じて保存先を決定
            target_dir = DONE_DIR if col == "Done" else WAITING_DIR
            target_dir.mkdir(parents=True, exist_ok=True)

            # どちらのディレクトリにも存在しなければ作成
            waiting_path = WAITING_DIR / f"{safe_name}.md"
            done_path = DONE_DIR / f"{safe_name}.md"
            if not waiting_path.exists() and not done_path.exists():
                filepath = target_dir / f"{safe_name}.md"
                lines = [
                    "---",
                    "estimated: ",
                    "priority: ",
                    "urgency: ",
                    "context: ",
                    "due: ",
                    f'source: "Kanban直接作成"',
                    f"created: {datetime.now(JST).strftime('%Y-%m-%d')}",
                    "---",
                    "",
                ]
                filepath.write_text("\n".join(lines), encoding="utf-8")
                print(f"  Created card for unlinked task: {safe_name} → {target_dir.name}/")

            # チェック状態を保持してwikilink形式に変換
            check_char = entry[3]  # "- [x]" の x部分
            new_entries.append(f"- [{check_char}] [[{safe_name}]]")
            converted.append(safe_name)

        sections[col] = new_entries

    if converted:
        rebuild_kanban(sections)

    return converted


def archive_done_tasks():
    """Done列のカードをTasks/Done/に移動し、Done列をクリア"""
    if not KANBAN_PATH.exists():
        return []

    content = KANBAN_PATH.read_text(encoding="utf-8")
    sections = parse_kanban_sections(content)

    done_entries = sections.get("Done", [])
    if not done_entries:
        return []

    done_names = extract_wikilinks(done_entries)
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    archived = []
    for name in done_names:
        src = WAITING_DIR / f"{name}.md"
        dst = DONE_DIR / f"{name}.md"
        if src.exists():
            src.rename(dst)
            archived.append(name)
            print(f"  Archived: {name}")
        elif not dst.exists():
            print(f"  Warning: card not found for {name}")

    sections["Done"] = []
    rebuild_kanban(sections)

    return archived


def add_tasks_to_kanban(tasks):
    """タスクリスト（dict配列）からカード作成 + Kanban追記

    Args:
        tasks: [{"name": "...", "estimated": "...", ...}, ...]
    Returns:
        list of newly created task names
    """
    existing = set(get_existing_task_names())
    new_names = []

    for task in tasks:
        name = task["name"]
        safe_name = sanitize_filename(name)
        if safe_name in existing:
            continue

        metadata = {k: v for k, v in task.items() if k != "name"}
        if create_task_card(name, metadata):
            new_names.append(safe_name)
            print(f"  Created card: {safe_name}")

    if new_names:
        add_to_kanban_inbox(new_names)
        print(f"  {len(new_names)} tasks added to Kanban Inbox.")

    return new_names
