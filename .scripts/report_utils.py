"""週報・月報の生成ロジック・通知ユーティリティ"""

import calendar
import os
import sys
import urllib.request
from pathlib import Path
from datetime import date, datetime, timezone, timedelta

# .env ファイルからローカル環境変数を読み込む（NTFY_TOPIC 等）
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from secretary_config import user_name

VAULT_ROOT = Path(__file__).parent.parent
DAILY_DIR = VAULT_ROOT / "Diary" / "Daily"
WEEKLY_DIR = VAULT_ROOT / "Diary" / "Weekly"
MONTHLY_DIR = VAULT_ROOT / "Diary" / "Monthly"
JST = timezone(timedelta(hours=9))

client = anthropic.Anthropic()

MAX_NTFY_BYTES = 4000  # ntfy.sh の上限は約4096bytes、余裕を持たせる

_WEEKLY_SYSTEM_TEMPLATE = """\
あなたは本人を傍で観察していた秘書として、日次ノート群から週次振り返りを生成します。

# 出力フォーマット

1行目は `# YYYY-WNN 週次振り返り（YYYY-MM-DD 〜 YYYY-MM-DD）` 形式（入力で渡された週・日付範囲をそのまま使う）。

（その週の1〜2行サマリー — どんな週だったかを秘書視点で）

## 今週のハイライト
（7日分のできごとから特に印象的だったもの3〜5項目。事実とその規模感で選ぶ。
本人が悩んでいた・喜んでいたなどは、本人の発言や行動として観測された範囲でのみ書く）

## やったこと
（完了した取り組み・進捗のまとめ。カテゴリ分けしてよい。自然な文章で）

## 学び・気づき
（その週の重要な学び・発見・自己理解の更新。Daily に書かれている範囲で拾う）

## 今週の雰囲気
（週を通して観測された本人の発言・行動の傾向。
「『疲れた』とつぶやく日が多かった」「外出が3日続いた」など、観察された事実として書く。
内面の推測はしない。観測材料が薄ければ省略）

## sources
（元にした Daily ファイルをリスト）

# 視点と文体
- **秘書視点・三人称・常体**で書く。「{USER_NAME}さんは〜した」「本人は〜と言っていた」のような、外から観察した距離感
- 本人の内面・感情は**推測しない**。「〜と感じたのだろう」「〜が嬉しかったようだ」のような心の中を代弁する表現は禁止
- 本人の発言は**引用として残す**。「『〜』とつぶやいていた」「本人いわく『〜』」のように観測された事実として書く
- 多少の温かみはあってよいが、それは事実の選び方や言葉の柔らかさで出すこと

# 重要なルール
- AIっぽい定型（「今後の展開が注目されます」「〜が期待されます」等）は避ける
- Obsidianのwikiリンク [[]] は関連ノートがあるときだけ使う
- 該当する内容が薄いセクションは無理に膨らませず、丸ごと省略してよい
- Daily 全体を読んで週単位の動きとして抽象化する（事実の取捨選択や分類のための判断はしてよい。感情の創作だけが禁止）
- **出力は本文のみ**。全体を ```markdown ... ``` のコードブロックで囲んだり、先頭・末尾に `---` の区切り線を置いたりしない\
"""

_WEEKLY_SYSTEM = _WEEKLY_SYSTEM_TEMPLATE.replace("{USER_NAME}", user_name())

_MONTHLY_SYSTEM = """\
あなたは本人を傍で観察していた秘書として、週次振り返りノート群から月次振り返りを生成します。

# 出力フォーマット

1行目は `# YYYY-MM 月次振り返り（YYYY年M月）` 形式（入力で渡された年月をそのまま使う）。

（その月の2〜3行サマリー — どんな1ヶ月だったかを秘書視点で）

## 今月のハイライト
（月を通して特に印象的だったこと3〜5項目。事実とその規模感で選ぶ。
本人の発言や行動として観測された範囲でのみ感情に触れる）

## やったこと
（月間の成果・取り組みのまとめ。カテゴリ分けしてよい。自然な文章で）

## 学び・気づき
（月を通しての重要な学び・自己理解の更新・スキルの伸び。週報・日報に書かれている範囲で拾う）

## 今月の変化
（先月と比べて変わったこと。習慣、行動パターン、生活環境、人間関係など、観測された変化を書く。
本人発言で「変わった」と明言されているもの、または事実として観測できる行動の変化に限る。
内面の変化を推測で書かない。変化がなければ省略してよい）

## sources
（元にした Weekly ファイル・Daily ファイルをリスト）

# 視点と文体
- **秘書視点・三人称・常体**で書く
- 本人の内面・感情は**推測しない**。代弁する表現は禁止
- 本人の発言は**引用として残す**
- 多少の温かみはあってよいが、それは事実の選び方や言葉の柔らかさで出すこと

# 重要なルール
- 週報の内容を単にコピーするのではなく、月単位の視点で抽象度を上げる
- 「週報に含まれなかった日」の内容も同等に扱う。補足扱いにしない
- AIっぽい定型（「今後の展開が注目されます」「〜が期待されます」等）は避ける
- Obsidianのwikiリンク [[]] は関連ノートがあるときだけ使う
- 該当する内容が薄いセクションは丸ごと省略してよい
- 事実の取捨選択や分類のための判断はしてよい。感情の創作だけが禁止
- **出力は本文のみ**。全体を ```markdown ... ``` のコードブロックで囲んだり、先頭・末尾に `---` の区切り線を置いたりしない\
"""


def _send_ntfy(title, message):
    """ntfy.sh でプッシュ通知を送信"""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC not set. Skipping notification.")
        return

    suffix = "\n\n（...続きはObsidianで）"
    suffix_bytes = suffix.encode("utf-8")
    if len(message.encode("utf-8")) > MAX_NTFY_BYTES:
        limit = MAX_NTFY_BYTES - len(suffix_bytes)
        truncated = message.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        body = (truncated + suffix).encode("utf-8")
    else:
        body = message.encode("utf-8")

    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body,
        headers={
            "Title": title.encode("utf-8"),
            "Tags": "notebook",
            "Priority": "high",
        },
    )
    try:
        urllib.request.urlopen(req)
        print(f"  Notification sent to ntfy.sh/{topic}")
    except Exception as e:
        print(f"  Notification failed: {e}")


def _read_file(path):
    return path.read_text(encoding="utf-8").strip()


def _iso_week_range(year, week):
    """ISO週番号から月曜〜日曜の日付範囲を返す"""
    monday = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u").date()
    sunday = monday + timedelta(days=6)
    return monday, sunday


def get_weekly_daily_files(year, week):
    """指定ISO週の月曜〜日曜に対応する Daily ファイルを取得"""
    monday, sunday = _iso_week_range(year, week)
    files = []
    for i in range(7):
        date = monday + timedelta(days=i)
        path = DAILY_DIR / date.strftime("%Y-%m") / f"{date.isoformat()}.md"
        if path.exists():
            files.append(path)
    return files


def generate_weekly_report(year, week):
    """週報を生成して Diary/Weekly/ に保存"""
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    output_path = WEEKLY_DIR / f"{year}-W{week:02d}.md"
    if output_path.exists():
        print(f"  Weekly report already exists: {output_path.name}")
        return None

    daily_files = get_weekly_daily_files(year, week)
    if not daily_files:
        print(f"  No daily files for {year}-W{week:02d}. Skipping weekly report.")
        return None

    monday, sunday = _iso_week_range(year, week)
    daily_contents = []
    for f in daily_files:
        daily_contents.append(f"=== {f.stem} ===\n{_read_file(f)}")

    raw = "\n\n".join(daily_contents)

    user_message = (
        f"週: {year}-W{week:02d}（{monday} 〜 {sunday}）\n\n"
        f"# 日次ノート\n{raw}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[{"type": "text", "text": _WEEKLY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )

    content = message.content[0].text
    output_path.write_text(content, encoding="utf-8")
    print(f"  Weekly report saved: {output_path.name}")
    return output_path


def get_monthly_weekly_files(year, month):
    """指定月に属する週報ファイルを取得"""
    files = []
    for f in sorted(WEEKLY_DIR.glob(f"{year}-W*.md")):
        # 週番号からその週の月曜日を求め、月曜 or 日曜がその月に属するか判定
        week_str = f.stem  # e.g. "2026-W16"
        week_num = int(week_str.split("-W")[1])
        monday, sunday = _iso_week_range(year, week_num)
        # 週の過半数がその月に含まれるかで判定（木曜日が属する月）
        thursday = monday + timedelta(days=3)
        if thursday.month == month:
            files.append(f)
    return files


def _get_gap_daily_files(year, month, weekly_files):
    """週報でカバーされていない月初・月末の Daily ファイルを取得"""
    # 週報がカバーする日付の集合を作る
    covered_dates = set()
    for f in weekly_files:
        week_num = int(f.stem.split("-W")[1])
        monday, sunday = _iso_week_range(year, week_num)
        for i in range(7):
            covered_dates.add(monday + timedelta(days=i))

    # 月の全日からカバー済みを引いてギャップを特定
    _, last_day = calendar.monthrange(year, month)
    gap_files = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if d not in covered_dates:
            path = DAILY_DIR / d.strftime("%Y-%m") / f"{d.isoformat()}.md"
            if path.exists():
                gap_files.append(path)

    return gap_files


def generate_monthly_report(year, month):
    """月報を生成して Diary/Monthly/ に保存"""
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)

    output_path = MONTHLY_DIR / f"{year}-{month:02d}.md"
    if output_path.exists():
        print(f"  Monthly report already exists: {output_path.name}")
        return None

    weekly_files = get_monthly_weekly_files(year, month)
    if not weekly_files:
        print(f"  No weekly reports for {year}-{month:02d}. Skipping monthly report.")
        return None

    weekly_contents = []
    for f in weekly_files:
        weekly_contents.append(f"=== {f.stem} ===\n{_read_file(f)}")

    # 週報でカバーされていない月初・月末の Daily を補完
    gap_files = _get_gap_daily_files(year, month, weekly_files)
    gap_contents = []
    for f in gap_files:
        gap_contents.append(f"=== {f.stem}（週報に未含） ===\n{_read_file(f)}")

    if gap_files:
        print(f"  {len(gap_files)} gap daily files found for {year}-{month:02d}: {[f.stem for f in gap_files]}")

    raw_parts = []
    raw_parts.append("# 週次振り返りノート\n" + "\n\n".join(weekly_contents))
    if gap_contents:
        raw_parts.append("# 週報に含まれなかった日の日次まとめ\n" + "\n\n".join(gap_contents))

    raw = "\n\n".join(raw_parts)
    month_label = f"{year}年{month}月"

    user_message = (
        f"月: {year}-{month:02d}（{month_label}）\n\n"
        f"# ソースデータ\n{raw}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[{"type": "text", "text": _MONTHLY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )

    content = message.content[0].text
    output_path.write_text(content, encoding="utf-8")
    print(f"  Monthly report saved: {output_path.name}")
    return output_path
