# vault-secretary

Obsidian vault に住み込みで働く秘書。朝晩あなたと対話して、1日の計画と振り返りをやってくれる。日中の Thino メモや作業ログは Claude API が日報・週報・月報にまとめる。

Claude Code の slash command と GitHub Actions で動く。

## できること

- **`/goodmorning`**：今朝のあいさつから始まり、Google Calendar の予定 + Tasks Kanban を読んで「今日やること」を一緒に決める。日中の時間ブロックも雛形として組む。
- **`/goodnight`**：1日の Thino メモと作業レポートを拾い、計画 vs 実績で振り返る。タスクの完了/延期/新規追加もここで反映。明日やることまで仕込む。
- **Daily/Weekly/Monthly ノート自動生成**：GitHub Actions が毎朝7時に Inbox と Thino を Claude に渡し、日報を `Diary/Daily/` に書く。週報・月報も同じ仕組みで生成。本人の発言は引用、内面の創作は禁止という秘書視点で書かれる。
- **ntfy.sh プッシュ通知**：日報・週報の中身がそのままスマホに飛んでくる。

## 仕組み

```
┌──────────────────────────┐
│  Obsidian vault          │
│  ├─ Inbox/ ← Thino       │
│  ├─ Tasks/ ← Kanban      │
│  └─ Diary/ ← 自動生成     │
└──────────────────────────┘
        ↑ git push           ↑ /goodmorning /goodnight
        │                    │
┌──────────────────────────┐ ┌─────────────────┐
│  GitHub Actions (cron)   │ │  Claude Code     │
│  └─ Claude API でまとめ   │ │  (対話 + MCP)    │
└──────────────────────────┘ └─────────────────┘
```

vault は Obsidian で開きつつ、git リポにもしておく。日中の Thino メモは git に乗って GitHub に上がり、毎朝の cron で Claude が日報を書いて push し戻してくる。Obsidian Sync の代わりに git でいい。

## 前提

- Obsidian で vault を git 管理している（Obsidian Git プラグインなど）
- GitHub にその vault リポがある（private 推奨）
- Anthropic API のキーを持っている
- Claude Code がインストール済み（`/goodmorning` などを使う場合）
- Google Calendar 連携は任意。使うなら Claude.ai 側の Google Calendar コネクタを認証しておく
- ntfy.sh の通知は任意。トピック名を決めるだけ

## セットアップ

### 1. 自分の vault リポにこのテンプレを重ねる

```bash
cd path/to/your-vault
git clone --depth 1 https://github.com/taiyakikatsuto/vault-secretary.git /tmp/vault-secretary
cp -r /tmp/vault-secretary/.scripts ./
cp -r /tmp/vault-secretary/.github ./
cp -r /tmp/vault-secretary/.claude ./
cp /tmp/vault-secretary/secretary.config.example.yml ./
cp /tmp/vault-secretary/setup.sh ./
cp /tmp/vault-secretary/.gitignore ./.gitignore.secretary  # 既存と統合
cp /tmp/vault-secretary/requirements.txt ./
```

### 2. setup.sh で対話的に初期化（おすすめ）

```bash
bash setup.sh
```

呼び名・パートナー名・Google Calendar ID を順番に聞かれるので入力する。空Enter で「使わない」を選べる（共有カレンダーやプライベートカレンダーがない構成にも対応）。

スクリプトは以下をやってくれる：

- `.claude/commands/*.md` のプレースホルダーを入力値で sed 置換
- 共有・プライベートカレンダーをスキップした場合は該当行を削除
- 「3つのカレンダー」のような件数表記を実構成に合わせて調整
- `secretary.config.yml` を生成して `user_name` を埋める

#### 手動でやる場合

setup.sh を使わず手で置換するなら、`.claude/commands/` 内の以下のプレースホルダーを sed なりエディタなりで自分の値に変える：

| プレースホルダー | 何を入れる |
|---|---|
| `{{PARTNER_NAME}}` | 共有カレンダーを使う相手の名前 |
| `{{SHARED_CALENDAR_LABEL}}` | 共有カレンダーのラベル名（例: 家族） |
| `{{CALENDAR_ID_SHARED}}` | 共有カレンダーの Google Calendar ID |
| `{{CALENDAR_ID_PRIVATE}}` | プライベート用カレンダーの Google Calendar ID |

呼び名は `secretary.config.yml` の `user_name` で設定する（`secretary.config.example.yml` をコピーして書き換える）。

カレンダーは1つしか使わないなら、`.claude/commands/goodmorning.md` `goodnight.md` の該当する行（共有・プライベートのカレンダー定義）をまるごと削除すればいい。

### 3. 環境変数（任意）

ntfy.sh で通知を受け取りたいなら `.env` を作る。

```
NTFY_TOPIC=your-secret-topic-name
```

### 4. GitHub Actions の secrets

vault リポの Settings → Secrets and variables → Actions に以下を登録。

- `ANTHROPIC_API_KEY`：Anthropic Console で発行したキー
- `NTFY_TOPIC`：通知を受け取るならトピック名（任意）

これで毎朝7時(JST) に日報、毎週月曜7:30に週報・月報が生成される。

### 5. ディレクトリの前提

vault 直下に以下のディレクトリが必要（無ければ作る）。

```
your-vault/
├── Inbox/                # Thino + 作業レポート + Obsidianデイリー
├── Diary/
│   ├── Daily/            # 自動生成
│   ├── Weekly/           # 自動生成
│   └── Monthly/          # 自動生成
├── Tasks/
│   ├── _index.md         # Kanban
│   └── Waiting/          # タスクカード
├── .scripts/             # このリポからコピー
├── .github/workflows/    # このリポからコピー
└── .claude/commands/     # このリポからコピー
```

Inbox の Thino メモは `YYYY-MM-DD.md` 形式（[Thino プラグイン](https://github.com/Quorafind/Obsidian-Thino) のデフォルト）を想定。

## 論理日付（LOGICAL_DATE）

「今日」の境界時間は環境変数 `DAILY_BOUNDARY_HOUR` で変えられる（デフォルト 7時 JST）。深夜2時に書いたメモは「昨日のメモ」として扱いたい、という前提。

## カスタマイズ

- システムプロンプトは `.scripts/daily_batch.py` の `_DAILY_SYSTEM_TEMPLATE` と `.scripts/report_utils.py` の `_WEEKLY_SYSTEM_TEMPLATE` / `_MONTHLY_SYSTEM` に直接書かれている。文体ルールや視点（秘書視点・三人称）は好みで書き換え可能
- `/goodmorning` と `/goodnight` の手順は `.claude/commands/*.md` に Markdown で書かれている。Claude Code がそのまま読んで実行するので、ステップを足したり消したりするのも編集だけで済む
- ntfy.sh が嫌なら `.scripts/report_utils.py` の `_send_ntfy` を別の通知サービスに差し替えればいい

## ライセンス

[MIT](LICENSE)
