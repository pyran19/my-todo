"""ライフサイクル昇格ロジックのテスト (design.md 第4節, F-5)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from my_todo import db
from my_todo.lifecycle import run_promotions, target_stage


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TODO_DB", str(tmp_path / "todo.db"))
    c = db.connect()
    yield c
    c.close()


def _insert(conn, created_at, lifecycle="short", status="open"):
    cur = conn.execute(
        "INSERT INTO tasks (body, lifecycle, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("body", lifecycle, status, created_at, created_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.mark.parametrize(
    "days,expected",
    [(0, "short"), (6, "short"), (7, "mid"), (29, "mid"), (30, "long"), (100, "long")],
)
def test_target_stage_thresholds(days, expected):
    assert target_stage(_ago(days)) == expected


def test_promotion_updates_open_task(conn):
    tid = _insert(conn, _ago(10))
    assert run_promotions(conn) == 1
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    assert row["lifecycle"] == "mid"
    assert row["promoted_at"] is not None


def test_multistage_jump_in_one_run(conn):
    tid = _insert(conn, _ago(45))  # short -> long を一度に
    run_promotions(conn)
    row = conn.execute("SELECT lifecycle FROM tasks WHERE id = ?", (tid,)).fetchone()
    assert row["lifecycle"] == "long"


def test_done_tasks_are_not_promoted(conn):
    tid = _insert(conn, _ago(100), status="done")
    assert run_promotions(conn) == 0
    row = conn.execute("SELECT lifecycle FROM tasks WHERE id = ?", (tid,)).fetchone()
    assert row["lifecycle"] == "short"


def test_no_double_promotion_is_idempotent(conn):
    _insert(conn, _ago(10))
    assert run_promotions(conn) == 1
    assert run_promotions(conn) == 0  # 既に mid なので再昇格しない


def test_fresh_task_not_promoted(conn):
    _insert(conn, _ago(1))
    assert run_promotions(conn) == 0
