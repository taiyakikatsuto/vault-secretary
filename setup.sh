#!/usr/bin/env bash
# vault-secretary 初回セットアップスクリプト
#
# 対話形式で値を聞いて、`.claude/commands/*.md` のプレースホルダーを置換する。
# `secretary.config.yml` も同時に生成する。
#
# 使い方:
#   このリポを自分の vault に重ねた後、vault のルートで実行する:
#     bash setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS_DIR="$SCRIPT_DIR/.claude/commands"
CONFIG_FILE="$SCRIPT_DIR/secretary.config.yml"
CONFIG_EXAMPLE="$SCRIPT_DIR/secretary.config.example.yml"

# OS 別の sed -i オプション
if [[ "$(uname)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi

ask() {
    # ask "プロンプト" "デフォルト値（省略可）" → 標準出力に値を返す
    local prompt="$1"
    local default="${2:-}"
    local answer
    if [[ -n "$default" ]]; then
        read -r -p "$prompt [$default]: " answer
        answer="${answer:-$default}"
    else
        read -r -p "$prompt: " answer
    fi
    printf '%s' "$answer"
}

escape_sed() {
    # sed の置換右辺で安全に使えるようにエスケープ
    printf '%s' "$1" | sed -e 's/[\/&|]/\\&/g'
}

if [[ ! -d "$COMMANDS_DIR" ]]; then
    echo "ERROR: $COMMANDS_DIR が見つからない。vault のルートで実行している？" >&2
    exit 1
fi

echo "==== vault-secretary セットアップ ===="
echo ""

# ---- 1. システムプロンプト用の呼び名 ----
echo "[1/4] システムプロンプトの呼び名を設定する"
echo "      （日報に「太郎さんは〜した」のように使われる名前）"
USER_NAME=$(ask "あなたの呼び名" "ユーザー")
echo ""

# ---- 2. 論理日付の境界時刻 ----
echo "[2/4] 論理日付の境界時刻（0-23 のJST。深夜のメモを前日扱いにする境目）"
while :; do
    BOUNDARY_HOUR=$(ask "境界時刻" "5")
    if [[ "$BOUNDARY_HOUR" =~ ^[0-9]+$ ]] && (( BOUNDARY_HOUR >= 0 && BOUNDARY_HOUR <= 23 )); then
        break
    fi
    echo "  0〜23 の整数で入力してください"
done
echo ""

# ---- 3. Google Calendar 設定 ----
echo "[3/4] Google Calendar の設定"
echo "      使わない場合は全て空Enterでスキップ"
echo ""
echo "  (a) パートナーとの共有カレンダー"
PARTNER_NAME=$(ask "  パートナーの名前（空Enter=共有カレンダー使わない）" "")

if [[ -n "$PARTNER_NAME" ]]; then
    SHARED_CALENDAR_LABEL=$(ask "  共有カレンダーのラベル名（例: 家族）")
    CALENDAR_ID_SHARED=$(ask "  共有カレンダーの ID（xxxxx@group.calendar.google.com）")
else
    SHARED_CALENDAR_LABEL=""
    CALENDAR_ID_SHARED=""
fi

echo ""
echo "  (b) プライベート用カレンダー"
CALENDAR_ID_PRIVATE=$(ask "  プライベートカレンダーの ID（空Enter=使わない）" "")
echo ""

# ---- 4. 置換実行 ----
echo "[4/4] 置換実行"

if [[ -n "$PARTNER_NAME" ]]; then
    "${SED_INPLACE[@]}" \
        -e "s|{{PARTNER_NAME}}|$(escape_sed "$PARTNER_NAME")|g" \
        -e "s|{{SHARED_CALENDAR_LABEL}}|$(escape_sed "$SHARED_CALENDAR_LABEL")|g" \
        -e "s|{{CALENDAR_ID_SHARED}}|$(escape_sed "$CALENDAR_ID_SHARED")|g" \
        "$COMMANDS_DIR"/*.md
    echo "  共有カレンダーのプレースホルダーを置換した"
else
    # 共有カレンダー未使用 → 該当行を削除
    "${SED_INPLACE[@]}" \
        -e '/{{CALENDAR_ID_SHARED}}/d' \
        -e '/{{SHARED_CALENDAR_LABEL}}/d' \
        -e '/{{PARTNER_NAME}}/d' \
        "$COMMANDS_DIR"/*.md
    echo "  共有カレンダーは使わない設定にした（該当行を削除）"
fi

if [[ -n "$CALENDAR_ID_PRIVATE" ]]; then
    "${SED_INPLACE[@]}" \
        -e "s|{{CALENDAR_ID_PRIVATE}}|$(escape_sed "$CALENDAR_ID_PRIVATE")|g" \
        "$COMMANDS_DIR"/*.md
    echo "  プライベートカレンダーのプレースホルダーを置換した"
else
    "${SED_INPLACE[@]}" \
        -e '/{{CALENDAR_ID_PRIVATE}}/d' \
        "$COMMANDS_DIR"/*.md
    echo "  プライベートカレンダーは使わない設定にした（該当行を削除）"
fi

# カレンダー数の文言調整（テンプレは「3つのカレンダー」想定）
CAL_COUNT=1
[[ -n "$PARTNER_NAME" ]] && CAL_COUNT=$((CAL_COUNT + 1))
[[ -n "$CALENDAR_ID_PRIVATE" ]] && CAL_COUNT=$((CAL_COUNT + 1))
if [[ $CAL_COUNT -ne 3 ]]; then
    "${SED_INPLACE[@]}" \
        -e "s|3つのカレンダー|${CAL_COUNT}つのカレンダー|g" \
        "$COMMANDS_DIR"/*.md
    echo "  カレンダー数の文言を「${CAL_COUNT}つのカレンダー」に調整"
fi

# ---- 4. secretary.config.yml 生成 ----
if [[ -f "$CONFIG_FILE" ]]; then
    echo ""
    echo "  $CONFIG_FILE は既に存在しているのでスキップ"
else
    if [[ -f "$CONFIG_EXAMPLE" ]]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
    else
        echo "user_name: \"$USER_NAME\"" > "$CONFIG_FILE"
    fi
    "${SED_INPLACE[@]}" \
        -e "s|^user_name:.*|user_name: \"$(escape_sed "$USER_NAME")\"|" \
        "$CONFIG_FILE"
    echo "  $CONFIG_FILE を作成した"
fi

# secretary.config.yml の daily_boundary_hour を更新（既存ファイルでも上書き）
if grep -q '^daily_boundary_hour:' "$CONFIG_FILE" 2>/dev/null; then
    "${SED_INPLACE[@]}" \
        -e "s|^daily_boundary_hour:.*|daily_boundary_hour: ${BOUNDARY_HOUR}|" \
        "$CONFIG_FILE"
else
    echo "daily_boundary_hour: ${BOUNDARY_HOUR}" >> "$CONFIG_FILE"
fi
echo "  daily_boundary_hour を ${BOUNDARY_HOUR} に設定"

# ---- 5. workflow yaml の cron を config から同期 ----
if [[ -x "${SCRIPT_DIR}/.scripts/sync_cron.sh" ]]; then
    bash "${SCRIPT_DIR}/.scripts/sync_cron.sh" || echo "  (sync_cron.sh が失敗した)"
fi

# ---- 6. pre-commit hook を仕込むかどうか ----
HOOK_TARGET="${SCRIPT_DIR}/.git/hooks/pre-commit"
HOOK_SOURCE_REL=".scripts/git-hooks/pre-commit-sync-cron"
HOOK_SOURCE_ABS="${SCRIPT_DIR}/${HOOK_SOURCE_REL}"

if [[ -d "${SCRIPT_DIR}/.git" ]] && [[ -f "${HOOK_SOURCE_ABS}" ]]; then
    echo ""
    INSTALL_HOOK=$(ask "pre-commit hook を入れる？config.yml 編集時に cron が自動同期される (Y/n)" "Y")
    if [[ "${INSTALL_HOOK}" =~ ^[Yy]$ ]]; then
        if [[ -e "${HOOK_TARGET}" ]] && [[ ! -L "${HOOK_TARGET}" ]]; then
            BACKUP="${HOOK_TARGET}.bak.$(date +%Y%m%d%H%M%S)"
            mv "${HOOK_TARGET}" "${BACKUP}"
            echo "  既存の pre-commit を ${BACKUP} に退避した"
        fi
        ln -sf "../../${HOOK_SOURCE_REL}" "${HOOK_TARGET}"
        echo "  pre-commit hook を有効化した"
    else
        echo "  hook を入れない設定にした。境界時刻を変えたら 'bash .scripts/sync_cron.sh' を叩いてから commit してください"
    fi
fi

# ---- 残ったプレースホルダーがないか確認 ----
REMAINING=$(grep -l '{{[A-Z_]*}}' "$COMMANDS_DIR"/*.md 2>/dev/null || true)
if [[ -n "$REMAINING" ]]; then
    echo ""
    echo "⚠ 置換しきれなかったプレースホルダーがあります:"
    grep -n '{{[A-Z_]*}}' "$COMMANDS_DIR"/*.md || true
fi

echo ""
echo "==== セットアップ完了 ===="
echo ""
echo "次にやること:"
echo "  1. GitHub Actions の Secrets に ANTHROPIC_API_KEY を登録"
echo "     （Settings → Secrets and variables → Actions）"
echo "  2. ntfy.sh で通知を受け取るなら、.env に NTFY_TOPIC を書いて"
echo "     GitHub Secrets にも同じ値を登録"
echo "  3. git commit & push したら毎朝${BOUNDARY_HOUR}時(JST)に日報が自動生成される"
