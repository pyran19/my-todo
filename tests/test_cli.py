"""CLIコマンドのテスト (promote/demote と ls の段階フィルタ)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from my_todo import db
from my_todo.cli import app

runner = CliRunner()


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TODO_DB", str(tmp_path / "todo.db"))
    yield


def _insert(created_at, lifecycle="short", status="open"):
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (body, lifecycle, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("body", lifecycle, status, created_at, created_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _lifecycle(tid):
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT lifecycle FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        return row["lifecycle"]
    finally:
        conn.close()


def test_promote_moves_one_stage_up():
    tid = _insert(_ago(0))
    result = runner.invoke(app, ["promote", str(tid)])
    assert result.exit_code == 0
    assert _lifecycle(tid) == "mid"


def test_demote_moves_one_stage_down():
    tid = _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["demote", str(tid)])
    assert result.exit_code == 0
    assert _lifecycle(tid) == "mid"


def test_promote_at_top_stage_errors():
    tid = _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["promote", str(tid)])
    assert result.exit_code == 1
    assert _lifecycle(tid) == "long"


def test_demote_at_bottom_stage_errors():
    tid = _insert(_ago(0), lifecycle="short")
    result = runner.invoke(app, ["demote", str(tid)])
    assert result.exit_code == 1
    assert _lifecycle(tid) == "short"


def test_demote_survives_auto_promotion():
    # 45日経過 (本来 long) のタスクを mid へ手動 demote すると created_at が
    # mid 相当へ書き換わり、次回コマンドの自動移行で long へ戻らない。
    tid = _insert(_ago(45), lifecycle="long")
    runner.invoke(app, ["demote", str(tid)])
    assert _lifecycle(tid) == "mid"
    runner.invoke(app, ["ls"])  # 自動移行フックが走る
    assert _lifecycle(tid) == "mid"


def test_promote_then_aging_continues():
    # 手動 promote 後も「その段階に入ったばかり」の created_at になるだけで、
    # さらに時間が経てば自動移行は通常どおり進む (ロックされない)。
    tid = _insert(_ago(0), lifecycle="short")
    runner.invoke(app, ["promote", str(tid)])  # short -> mid (created_at: 7日前)
    assert _lifecycle(tid) == "mid"
    # mid の入口(7日)に置かれるので、long(30日)へは即時昇格しない。
    runner.invoke(app, ["ls"])
    assert _lifecycle(tid) == "mid"


def test_missing_task_errors():
    result = runner.invoke(app, ["promote", "999"])
    assert result.exit_code == 1


def test_ls_default_shows_only_short():
    _insert(_ago(0), lifecycle="short")
    _insert(_ago(0), lifecycle="mid")
    _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "## short" in result.stdout
    assert "## mid" not in result.stdout
    assert "## long" not in result.stdout


def test_ls_stage_option_selects_table():
    _insert(_ago(0), lifecycle="short")
    _insert(_ago(0), lifecycle="mid")
    result = runner.invoke(app, ["ls", "-s", "mid"])
    assert result.exit_code == 0
    assert "## mid" in result.stdout
    assert "## short" not in result.stdout


def test_ls_stage_all_shows_every_table():
    _insert(_ago(0), lifecycle="short")
    _insert(_ago(0), lifecycle="mid")
    _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["ls", "-s", "all"])
    assert result.exit_code == 0
    assert "## short" in result.stdout
    assert "## mid" in result.stdout
    assert "## long" in result.stdout


def test_ls_invalid_stage_errors():
    result = runner.invoke(app, ["ls", "-s", "bogus"])
    assert result.exit_code == 1


def test_stage_shortcut_shows_only_that_stage():
    _insert(_ago(0), lifecycle="short")
    _insert(_ago(0), lifecycle="mid")
    _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["mid"])
    assert result.exit_code == 0
    assert "## mid" in result.stdout
    assert "## short" not in result.stdout
    assert "## long" not in result.stdout


def test_stage_shortcut_long():
    _insert(_ago(0), lifecycle="long")
    result = runner.invoke(app, ["long"])
    assert result.exit_code == 0
    assert "## long" in result.stdout


def test_stage_shortcut_all_flag_includes_done():
    _insert(_ago(0), lifecycle="mid", status="done")
    without_all = runner.invoke(app, ["mid"])
    assert "## mid" not in without_all.stdout
    with_all = runner.invoke(app, ["mid", "-a"])
    assert "## mid" in with_all.stdout
