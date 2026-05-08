#!/usr/bin/env bash
# secretary.config.yml の daily_boundary_hour から
# .github/workflows/daily-batch.yml の cron 行を再生成する。
#
# 使い方:
#   bash .scripts/sync_cron.sh           # 必要なら yaml を書き換える
#   bash .scripts/sync_cron.sh --check   # 書き換えずに乖離を exit code で返す（0=同期済み, 1=要同期）
#
# pre-commit hook（.scripts/git-hooks/pre-commit-sync-cron）からも呼ばれる。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$REPO_ROOT/secretary.config.yml"
WORKFLOW_FILE="$REPO_ROOT/.github/workflows/daily-batch.yml"

CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "WARN: ${CONFIG_FILE} が無いから同期スキップ〜" >&2
    exit 0
fi

if [[ ! -f "${WORKFLOW_FILE}" ]]; then
    echo "ERROR: ${WORKFLOW_FILE} が無い〜" >&2
    exit 2
fi

# config から daily_boundary_hour を読む（PyYAML 不要、grep + awk で十分）
BOUNDARY_HOUR=$(awk -F'[: \t]+' '/^daily_boundary_hour:/ {print $2; exit}' "${CONFIG_FILE}")
if [[ -z "${BOUNDARY_HOUR}" ]] || ! [[ "${BOUNDARY_HOUR}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: daily_boundary_hour が読めない〜（${CONFIG_FILE}）" >&2
    exit 2
fi
if (( BOUNDARY_HOUR < 0 || BOUNDARY_HOUR > 23 )); then
    echo "ERROR: daily_boundary_hour=${BOUNDARY_HOUR} は範囲外（0-23）〜" >&2
    exit 2
fi

# UTC = (JST - 9 + 24) % 24
CRON_HOUR=$(( (BOUNDARY_HOUR - 9 + 24) % 24 ))
EXPECTED_CRON="    - cron: '0 ${CRON_HOUR} * * *'"

# 現状の cron 行を取得（コメントは無視、`- cron:` で始まる行）
CURRENT_CRON=$(grep -E "^[[:space:]]*-[[:space:]]+cron:[[:space:]]+'[0-9]+ [0-9]+ \* \* \*'" "${WORKFLOW_FILE}" || true)

if [[ "${CURRENT_CRON}" == "${EXPECTED_CRON}" ]]; then
    # 既に同期済み、何もしない
    exit 0
fi

if [[ ${CHECK_ONLY} -eq 1 ]]; then
    echo "daily-batch.yml の cron が config と乖離（期待: '0 ${CRON_HOUR} * * *'）" >&2
    exit 1
fi

# OS 別 sed
if [[ "$(uname)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi

# `- cron: '<n> <n> * * *'` の行をまるごと書き換える
"${SED_INPLACE[@]}" \
    -e "s|^[[:space:]]*-[[:space:]]\{1,\}cron:[[:space:]]\{1,\}'[0-9]\{1,2\} [0-9]\{1,2\} \* \* \*'.*|${EXPECTED_CRON}|" \
    "${WORKFLOW_FILE}"

echo "daily-batch.yml の cron を '0 ${CRON_HOUR} * * *' に同期したよ〜（boundary=${BOUNDARY_HOUR} JST）"
