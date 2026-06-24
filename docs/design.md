# 設計書 (Design)

[`specification.md`](./specification.md) の機能仕様を実装レベルへ落とし込む。スキーマ・コマンド体系・自動移行ロジックは、本書だけを見れば実装に着手できる粒度を目指す。

## 1. 技術スタック

| 項目 | 選定 | 理由 |
|------|------|------|
| 言語 | Python 3.12（`.python-version` / `requires-python` 準拠） | 既存プロジェクト設定 |
| CLIフレームワーク | [Typer](https://typer.tiangolo.com/) | サブコマンド・引数定義が宣言的。依存はこの1つのみ追加 |
| ストレージ | 標準ライブラリ `sqlite3` | 追加依存なし。単一ファイルDBで取り回しが容易 |
| 配布 | `uv tool install` | グローバルコマンド `todo` として提供（F-1） |

依存は Typer のみに抑え、ストレージは標準ライブラリで賄う方針。

## 2. データ保存場所（F-1）

「どのパスから実行しても同一ストレージ」を満たすため、実行ディレクトリに依存しない固定パスにDBを置く。XDG Base Directory 準拠とする。

- DBファイル: `${XDG_DATA_HOME:-~/.local/share}/my-todo/todo.db`
- 環境変数 `MY_TODO_DB`（任意）が設定されていればそちらを優先（テスト・上書き用）。
- ディレクトリ・DBは初回実行時に存在しなければ自動作成する。

> README の「ホーム下にアプリ用ディレクトリ」を、XDG準拠の `~/.local/share/my-todo/` として具体化したもの。

## 3. データモデル（SQLiteスキーマ）

README の「寿命ごとに複数テーブルを用意して移していく」という表現は、**単一 `tasks` テーブル + `lifecycle` カラム**に整理する。段階の移行＝カラム値の更新となり、テーブル間のレコード移動より単純で、同じ意図（寿命分類と移行）を満たせるため。

### 3.1 `tasks` テーブル

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    body        TEXT    NOT NULL,
    lifecycle   TEXT    NOT NULL DEFAULT 'short',  -- 'short' | 'mid' | 'long'
    status      TEXT    NOT NULL DEFAULT 'open',   -- 'open'  | 'done'
    created_at  TEXT    NOT NULL,                  -- ISO8601 (UTC)
    updated_at  TEXT    NOT NULL,                  -- ISO8601 (UTC)
    promoted_at TEXT                               -- 最後に lifecycle 移動した日時 (nullable)
);
```

- `lifecycle`: 短期=`short` / 中期=`mid` / 長期=`long`。
- `status`: `open`（未完了） / `done`（完了）。
- 日付はすべてアプリ側で自動設定（F-2）。ユーザーは入力しない。ただし手動移動（4.3）では `created_at` を意図的に書き換える。

### 3.2 `think` テーブル（F-4）

to think は通常タスクと別立てにするため、専用テーブルとする。寿命分類・status は持たない（純粋な思考メモの置き場）。

```sql
CREATE TABLE IF NOT EXISTS think (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 3.3 タグ（将来用・今回未実装）

将来の「分解→タグ変換」ワークフロー（仕様書 2.3）に備えたスキーマ案のみ記載。今回は作成しない。

```sql
-- 将来検討。今回は未実装。
-- CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
-- CREATE TABLE task_tags (task_id INTEGER, tag_id INTEGER, PRIMARY KEY (task_id, tag_id));
```

## 4. ライフサイクル自動移行ロジック（F-5）

### 4.1 しきい値

経過日数で昇格する。初期値は以下。将来 `config.toml`（第6節）で変更可能とする想定。

| 移行 | 条件（経過日数の目安） |
|------|------------------------|
| `short` → `mid` | 作成から約 **3日** 経過 |
| `mid` → `long`  | 作成から約 **14日** 経過 |

経過日数は `created_at` を基準に算出する（昇格基準を作成日に固定し、ユーザー操作で寿命がリセットされないようにする）。

### 4.2 移行の実行タイミング（lazy migration）

常駐プロセスや通知（仕様書 2.2 で除外）を持たないため、**CLI実行時に遅延的に**移行を行う。

1. 任意の `todo` コマンド実行直後、最初にDBへ接続したタイミングで昇格チェックを走らせる。
2. `status = 'open'` のタスクのうち、`created_at` からの経過日数がしきい値を超えるものについて `lifecycle` を1段階昇格し、`promoted_at` と `updated_at` を更新する。
3. 1回のチェックで複数段階の昇格条件を満たす場合（例: 久しぶりの実行で14日以上経過）、最終的に到達すべき段階まで一度に昇格させる。

これにより、ユーザーが何もしなくても古いタスクが中期→長期へ移り、一覧から「おおまかな寿命」が把握できる。

### 4.3 手動移動（`promote` / `demote`）

自動移行とは別に、ユーザーが任意のタスクを明示的に1段階ずつ移動できる。

- `promote`: 一つ長寿命側へ（`short`→`mid`→`long`）。`long` で頭打ち。
- `demote`: 一つ短寿命側へ（`long`→`mid`→`short`）。`short` で頭打ち。

移動は **`created_at` を「移動先段階の入口」に書き換える**方式で行う。具体的には `lifecycle` を移動先段階に更新すると同時に、`created_at` を `now - 移動先段階の下限日数`（`short`=0日 / `mid`=3日 / `long`=14日）へ書き換える。

- 経過日数を正確に保つことは本アプリの目的ではない（おおまかな寿命把握のみ）ため、`created_at` の書き換えを許容する。
- この方式なら専用フラグを持たずに自動移行（4.2）と整合する。移動直後は `target_stage()` がちょうど移動先段階を返すため、即座に再昇格・降格されない。特に `demote` が次回実行の自動昇格で巻き戻ることもない。
- 一方で「その段階に入ったばかり」の状態になるため、さらに時間が経てば自動移行は通常どおり進む（移動でロックはされない）。

## 5. CLIコマンド体系（Typer）

エントリポイントは `todo`。各コマンド実行時に第4節の昇格チェックを自動実行する。

| コマンド | 説明 |
|----------|------|
| `todo add "<本文>"` | 短期タスクとして追加。`created_at` を自動記録。本文を省略した場合は `$EDITOR` を開いて入力 |
| `todo ls` | タスクを **lifecycle 段階ごとにグループ化**して一覧表示。既定では `short` 段階のみ。`--stage/-s <段階>` で表示段階を指定（複数指定可、`all` で全段階）。`--all` で done も含める |
| `todo promote <id>` | タスクを一つ長寿命側の段階へ手動移動（`short`→`mid`→`long`）。`created_at` を移動先段階の入口へ書き換える |
| `todo demote <id>` | タスクを一つ短寿命側の段階へ手動移動（`long`→`mid`→`short`）。`created_at` を移動先段階の入口へ書き換える |
| `todo edit <id>` | 該当タスクの本文を `$EDITOR`（vim）で開いて編集。保存時に `updated_at` 更新 |
| `todo done <id>` | タスクを完了（`status = 'done'`）にする |
| `todo rm <id>` | タスクを削除する |
| `todo think add ["<本文>"]` | to think リストへ追加（本文省略時は `$EDITOR`） |
| `todo think ls` | to think リスト一覧 |
| `todo think edit <id>` | to think 項目を `$EDITOR` で編集 |
| `todo think rm <id>` | to think 項目を削除 |

### 5.1 `$EDITOR`（vim）連携（F-3）

1. 一時ファイルを作成し、編集対象の本文を書き込む（新規追加時は空）。
2. `os.environ.get("EDITOR", "vim")` で得たエディタを `subprocess` で起動し、一時ファイルを開く。
3. エディタ終了後に一時ファイルを読み戻し、本文としてDBへ保存。

### 5.2 一覧表示の整形（F-6）

`todo ls` は `short` / `mid` / `long` の見出しごとにタスクをまとめて表示する。各行に `id`・本文・（任意で）作成からの経過日数を示し、寿命がひと目で分かるようにする。

既定では `short` 段階のみ表示し、`--stage/-s` で表示対象段階を選べる（例: `-s mid`、`-s mid -s long`、`-s all`）。短期タスクに集中しやすくしつつ、長寿命側は必要なときに明示的に確認する運用を想定。

## 6. 設定ファイル（任意・将来）

`${XDG_CONFIG_HOME:-~/.config}/my-todo/config.toml` を将来の拡張点として用意する想定。
昇格しきい値・既定エディタなどを上書きできるようにする。今回は未実装で、第4.1節のデフォルト値をハードコードしてよい。

## 7. 既存資産との関係

- `src/main.py`: 現状はスタブ（`Hello from my-todo!`）。本設計の実装起点とする。
- `pyproject.toml`: `dependencies = []`。実装フェーズで Typer 追加と `[project.scripts]` への `todo` エントリポイント登録を行う。
