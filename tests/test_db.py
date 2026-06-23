"""DBパス解決とスキーマ初期化のテスト (design.md 第2,3節)。"""

from __future__ import annotations

from pathlib import Path

from my_todo import db


def test_my_todo_db_takes_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TODO_DB", str(tmp_path / "custom.db"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert db.db_path() == tmp_path / "custom.db"


def test_xdg_data_home_used_when_no_override(monkeypatch, tmp_path):
    monkeypatch.delenv("MY_TODO_DB", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert db.db_path() == tmp_path / "xdg" / "my-todo" / "todo.db"


def test_default_path_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv("MY_TODO_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert db.db_path() == tmp_path / ".local" / "share" / "my-todo" / "todo.db"


def test_connect_creates_dir_and_schema(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "todo.db"
    monkeypatch.setenv("MY_TODO_DB", str(target))
    conn = db.connect()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"tasks", "think"} <= tables
        assert target.exists()
    finally:
        conn.close()
