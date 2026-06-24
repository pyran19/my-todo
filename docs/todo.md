# 開発TODO

実装の進め方をチェックリスト形式でまとめる。仕様は [`specification.md`](./specification.md)、設計は [`design.md`](./design.md) を参照。

## セットアップ
- [x] `pyproject.toml` に依存 `typer` を追加
- [x] `pyproject.toml` の `[project.scripts]` に `todo = "main:app"`（相当）を登録し、グローバルコマンド化
- [x] `uv tool install`（または `uv run`）でローカル動作確認できる状態にする

## ストレージ層
- [x] DBパス解決: `MY_TODO_DB` → `${XDG_DATA_HOME:-~/.local/share}/my-todo/todo.db` の順で決定
- [x] ディレクトリ・DBの初回自動作成
- [x] スキーマ作成（`tasks` / `think`）を `CREATE TABLE IF NOT EXISTS` で冪等に

## タスクCRUD
- [x] `todo add` … 短期タスク追加（`created_at`/`updated_at` 自動設定、本文省略時は `$EDITOR`）
- [x] `todo ls` … タスクを lifecycle 段階ごとにグループ表示（既定は short のみ、`--stage/-s` で段階指定・`all` で全段階、`--all` で done 含む）
- [x] `todo promote <id>` … 一つ長寿命側へ手動移動（`created_at` を移動先段階の入口へ書き換え）
- [x] `todo demote <id>` … 一つ短寿命側へ手動移動（同上）
- [x] `todo edit <id>` … `$EDITOR` で本文編集、`updated_at` 更新
- [x] `todo done <id>` … `status = 'done'` へ
- [x] `todo rm <id>` … 削除

## `$EDITOR`(vim) 連携
- [x] 一時ファイル経由で本文を編集（新規＝空ファイル、編集＝既存本文を投入）
- [x] `os.environ.get("EDITOR", "vim")` をサブプロセス起動 → 終了後に読み戻して保存

## ライフサイクル自動移行
- [x] 昇格ロジック: `open` かつ `created_at` 経過日数がしきい値超のものを昇格（short→mid: 約3日 / mid→long: 約14日）
- [x] 1回のチェックで複数段階の昇格にも対応
- [x] 昇格時に `lifecycle` / `promoted_at` / `updated_at` を更新
- [x] 各コマンド実行時にこのチェックを自動フック（lazy migration）
- [x] 手動移動（`promote`/`demote`）は `created_at` を移動先段階の入口へ書き換え、自動移行と整合させる

## to think リスト
- [x] `todo think add` / `ls` / `edit` / `rm` を実装（`think` テーブル操作）

## 表示整形
- [x] `todo ls` の段階別グループ表示（id・本文・作成からの経過日数など、寿命がひと目で分かる形式）

## 動作確認
- [x] 別ディレクトリから実行しても同一DBを参照することを確認（F-1）
- [x] 追加→一覧→編集→完了/削除の一連を確認
- [x] 日付を過去に設定したレコードで昇格が走ることを確認（しきい値や `created_at` を一時的に操作してテスト）

## 将来検討（今回スコープ外）
- [ ] タグ用テーブル（`tags` / `task_tags`）と「分解→タグ変換」ワークフロー
- [ ] `config.toml`（昇格しきい値・既定エディタの上書き）
