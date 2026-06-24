# 使い方（コマンド一覧）

エントリポイントは `todo` です。引数なしで実行すると、短期タスクの一覧（`todo ls` 相当）を表示します。

各コマンドの実行時には、古くなったタスクを自動的に長寿命側へ移すチェックが走ります
（[ライフサイクルの考え方](./concepts.md) を参照）。

## タスク

| コマンド | 説明 |
|----------|------|
| `todo add "<本文>"` | 短期タスクとして追加。作成日時は自動記録。本文を省略すると `$EDITOR` が開く |
| `todo ls` | タスクを寿命の段階ごとにまとめて一覧表示（既定は `short` 段階のみ） |
| `todo ls -s <段階>` | 表示する段階を指定（`short`/`mid`/`long`、複数指定可、`all` で全段階） |
| `todo ls -a` | 完了（done）タスクも含めて表示 |
| `todo edit <id>` | タスク本文を `$EDITOR` で開いて編集 |
| `todo done <id>` | タスクを完了にする |
| `todo rm <id>` | タスクを削除する（確認なし） |
| `todo promote <id>` | タスクを一つ長寿命側の段階へ手動で移動（`short`→`mid`→`long`） |
| `todo demote <id>` | タスクを一つ短寿命側の段階へ手動で移動（`long`→`mid`→`short`） |

## to think リスト

すぐ片付くタスクではなく、「ちょっと考える必要がある」項目を別立てで置いておくためのリストです。

| コマンド | 説明 |
|----------|------|
| `todo think add "<本文>"` | to think リストへ追加（本文省略時は `$EDITOR`） |
| `todo think ls` | to think リストを一覧表示 |
| `todo think edit <id>` | to think 項目を `$EDITOR` で編集 |
| `todo think rm <id>` | to think 項目を削除 |

## 使用例

```sh
# 追加
todo add "請求書を送る"

# 本文を省略して vim で書く（複数行も可）
todo add

# 一覧（既定は short のみ）
todo

# 中期・長期も含めて確認
todo ls -s all

# 編集・完了・削除
todo edit 3
todo done 3
todo rm 3

# 考えごとは to think へ
todo think add "来期の方針をどう整理するか"
todo think ls
```

## エディタ連携

本文の入力・編集は `$EDITOR` 環境変数で指定したエディタで行います。
未設定の場合は `vim` が使われます。一時ファイルを開き、保存して終了すると本文として取り込まれます。
