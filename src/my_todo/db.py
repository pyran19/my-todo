"""ストレージ層: DBパス解決・接続・スキーマ作成 (design.md 第2,3節)。

実行ディレクトリに依存しない固定パスに SQLite DB を置くことで
「どのパスから実行しても同一ストレージ」(F-1) を満たす。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    """現在時刻を ISO8601 (UTC) 文字列で返す。日付はすべてアプリ側で自動設定 (F-2)。"""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """ISO8601 文字列を tz-aware な datetime へ。"""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def db_path() -> Path:
    """DBファイルのパスを解決する。

    優先順位 (design.md 第2節):
      1. 環境変数 MY_TODO_DB (テスト・上書き用)
      2. ${XDG_DATA_HOME:-~/.local/share}/my-todo/todo.db
    """
    override = os.environ.get("MY_TODO_DB")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "my-todo" / "todo.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    body            TEXT    NOT NULL,
    lifecycle       TEXT    NOT NULL DEFAULT 'short',
    status          TEXT    NOT NULL DEFAULT 'open',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    promoted_at     TEXT,
    lifecycle_locked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS think (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """既存DB向けの軽量マイグレーション。新カラムを冪等に追加する。

    `CREATE TABLE IF NOT EXISTS` は既存テーブルに新カラムを足さないため、
    ここで PRAGMA を見て不足分を ALTER TABLE する。
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "lifecycle_locked" not in cols:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN lifecycle_locked INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def connect() -> sqlite3.Connection:
    """DBへ接続する。ディレクトリ・DB・スキーマを冪等に初期化する。"""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn
