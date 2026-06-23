"""CLIエントリポイント (design.md 第5節)。Typer アプリ `app` を定義する。

各コマンド実行時にライフサイクル昇格チェックを自動フックする (lazy migration)。
サブコマンドを省略した場合は `ls` を実行する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer

from . import db
from .editor import edit_text
from .lifecycle import (
    STAGES,
    created_at_for_stage,
    next_stage,
    prev_stage,
    run_promotions,
)

app = typer.Typer(
    help="個人用TODO CLI。自分の欲しい機能だけを備えた最小TODO。",
    no_args_is_help=False,
    add_completion=False,
)
think_app = typer.Typer(help="to think リスト (思考が長くなりそうな項目の別立て置き場)。")
app.add_typer(think_app, name="think")


def _resolve_body(body: str | None, initial: str = "") -> str:
    """本文を決定する。引数があればそれを、無ければ $EDITOR を開いて取得する。"""
    if body is not None:
        return body.strip()
    return edit_text(initial)


def _elapsed_days(created_at: str) -> int:
    return (datetime.now(timezone.utc) - db.parse_iso(created_at)).days


def _first_line(body: str) -> str:
    """本文の1行目を返す。続きがある場合は末尾に … を付ける (ls 用)。"""
    lines = body.splitlines() or [""]
    head = lines[0]
    if len(lines) > 1:
        head = f"{head}…"
    return head


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """全コマンド共通の前処理: 昇格チェックを走らせる。引数なしなら ls。"""
    conn = db.connect()
    try:
        run_promotions(conn)
    finally:
        conn.close()

    if ctx.invoked_subcommand is None:
        _render_ls(["short"], show_all=False)


@app.command()
def add(
    body: str = typer.Argument(None, help="タスク本文。省略すると $EDITOR で入力。"),
) -> None:
    """短期タスクとして追加する (created_at を自動記録)。"""
    text = _resolve_body(body)
    if not text:
        typer.echo("本文が空のため中止しました。")
        raise typer.Exit(code=1)

    ts = db.now_iso()
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (body, created_at, updated_at) VALUES (?, ?, ?)",
            (text, ts, ts),
        )
        conn.commit()
        typer.echo(f"added #{cur.lastrowid}")
    finally:
        conn.close()


def _resolve_stages(stage: list[str] | None) -> list[str]:
    """--stage オプションを表示対象段階のリストへ正規化する。

    無指定なら short のみ。"all" 指定で全段階。STAGES の順序を保つ。
    """
    if not stage:
        return ["short"]
    if "all" in stage:
        return list(STAGES)
    invalid = [s for s in stage if s not in STAGES]
    if invalid:
        valid = ", ".join((*STAGES, "all"))
        typer.echo(f"不明な段階: {', '.join(invalid)} (有効: {valid})")
        raise typer.Exit(code=1)
    return [s for s in STAGES if s in stage]


def _render_ls(stages: list[str], show_all: bool) -> None:
    """指定段階のタスクを lifecycle 段階ごとにグループ化して一覧表示する。"""
    conn = db.connect()
    try:
        if show_all:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'open' ORDER BY created_at"
            ).fetchall()
    finally:
        conn.close()

    by_stage: dict[str, list] = {s: [] for s in stages}
    for row in rows:
        if row["lifecycle"] in by_stage:
            by_stage[row["lifecycle"]].append(row)

    if not any(by_stage.values()):
        typer.echo("(タスクはありません)")
        return

    first = True
    for stage in stages:
        items = by_stage[stage]
        if not items:
            continue  # 空グループは見出しごと非表示。
        if not first:
            typer.echo("")
        first = False
        typer.echo(f"## {stage}")
        for row in items:
            mark = " ✓" if row["status"] == "done" else ""
            typer.echo(
                f"{row['id']:>4}  [{_elapsed_days(row['created_at'])}d]{mark} "
                f"{_first_line(row['body'])}"
            )


@app.command()
def ls(
    stage: list[str] = typer.Option(
        None,
        "--stage",
        "-s",
        help="表示する段階 (short/mid/long, 複数指定可。all で全段階)。"
        "無指定なら short のみ。",
    ),
    show_all: bool = typer.Option(
        False, "--all", "-a", help="done タスクも含めて表示する。"
    ),
) -> None:
    """タスクを lifecycle 段階ごとにグループ化して一覧表示する (既定では short のみ)。"""
    _render_ls(_resolve_stages(stage), show_all)


def _move_stage(id: int, direction: int) -> None:
    """タスクの lifecycle 段階を手動で1段階移動する。

    direction > 0 で長寿命側 (short→mid→long)、< 0 で短寿命側へ。
    移動は created_at を「移動先段階の入口」に書き換えて行う。これにより
    自動移行ロジックと矛盾せず (直後に昇格も降格もされない)、降格しても
    次回実行で巻き戻らない。経過日数表示は移動先段階相当に変わる。
    """
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT lifecycle FROM tasks WHERE id = ?", (id,)
        ).fetchone()
        if row is None:
            typer.echo(f"task #{id} が見つかりません。")
            raise typer.Exit(code=1)

        current = row["lifecycle"]
        dest = next_stage(current) if direction > 0 else prev_stage(current)
        if dest is None:
            edge = "long (最長)" if direction > 0 else "short (最短)"
            typer.echo(f"task #{id} は既に {edge} 段階のため移動できません。")
            raise typer.Exit(code=1)

        ts = db.now_iso()
        conn.execute(
            "UPDATE tasks SET lifecycle = ?, created_at = ?, "
            "promoted_at = ?, updated_at = ? WHERE id = ?",
            (dest, created_at_for_stage(dest), ts, ts, id),
        )
        conn.commit()
        typer.echo(f"moved #{id}: {current} -> {dest}")
    finally:
        conn.close()


@app.command()
def promote(id: int = typer.Argument(..., help="移動するタスクID。")) -> None:
    """タスクを一つ長いライフサイクル段階へ移動する (short→mid→long)。"""
    _move_stage(id, direction=1)


@app.command()
def demote(id: int = typer.Argument(..., help="移動するタスクID。")) -> None:
    """タスクを一つ短いライフサイクル段階へ移動する (long→mid→short)。"""
    _move_stage(id, direction=-1)


@app.command()
def edit(id: int = typer.Argument(..., help="編集するタスクID。")) -> None:
    """タスク本文を $EDITOR で開いて編集する (保存時に updated_at 更新)。"""
    conn = db.connect()
    try:
        row = conn.execute("SELECT body FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            typer.echo(f"task #{id} が見つかりません。")
            raise typer.Exit(code=1)

        text = edit_text(row["body"])
        if not text:
            typer.echo("本文が空のため変更しませんでした。")
            raise typer.Exit(code=1)

        conn.execute(
            "UPDATE tasks SET body = ?, updated_at = ? WHERE id = ?",
            (text, db.now_iso(), id),
        )
        conn.commit()
        typer.echo(f"updated #{id}")
    finally:
        conn.close()


@app.command()
def done(id: int = typer.Argument(..., help="完了にするタスクID。")) -> None:
    """タスクを完了 (status='done') にする。"""
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?",
            (db.now_iso(), id),
        )
        conn.commit()
        if cur.rowcount == 0:
            typer.echo(f"task #{id} が見つかりません。")
            raise typer.Exit(code=1)
        typer.echo(f"done #{id}")
    finally:
        conn.close()


@app.command()
def rm(id: int = typer.Argument(..., help="削除するタスクID。")) -> None:
    """タスクを削除する (確認なし)。"""
    conn = db.connect()
    try:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (id,))
        conn.commit()
        if cur.rowcount == 0:
            typer.echo(f"task #{id} が見つかりません。")
            raise typer.Exit(code=1)
        typer.echo(f"removed #{id}")
    finally:
        conn.close()


# --- to think リスト (F-4) -------------------------------------------------


@think_app.command("add")
def think_add(
    body: str = typer.Argument(None, help="本文。省略すると $EDITOR で入力。"),
) -> None:
    """to think リストへ追加する。"""
    text = _resolve_body(body)
    if not text:
        typer.echo("本文が空のため中止しました。")
        raise typer.Exit(code=1)

    ts = db.now_iso()
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO think (body, created_at, updated_at) VALUES (?, ?, ?)",
            (text, ts, ts),
        )
        conn.commit()
        typer.echo(f"added think #{cur.lastrowid}")
    finally:
        conn.close()


@think_app.command("ls")
def think_ls() -> None:
    """to think リストを一覧表示する。"""
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM think ORDER BY created_at").fetchall()
    finally:
        conn.close()

    if not rows:
        typer.echo("(to think はありません)")
        return
    for row in rows:
        typer.echo(
            f"{row['id']:>4}  [{_elapsed_days(row['created_at'])}d] "
            f"{_first_line(row['body'])}"
        )


@think_app.command("edit")
def think_edit(id: int = typer.Argument(..., help="編集する think 項目ID。")) -> None:
    """to think 項目を $EDITOR で編集する。"""
    conn = db.connect()
    try:
        row = conn.execute("SELECT body FROM think WHERE id = ?", (id,)).fetchone()
        if row is None:
            typer.echo(f"think #{id} が見つかりません。")
            raise typer.Exit(code=1)

        text = edit_text(row["body"])
        if not text:
            typer.echo("本文が空のため変更しませんでした。")
            raise typer.Exit(code=1)

        conn.execute(
            "UPDATE think SET body = ?, updated_at = ? WHERE id = ?",
            (text, db.now_iso(), id),
        )
        conn.commit()
        typer.echo(f"updated think #{id}")
    finally:
        conn.close()


@think_app.command("rm")
def think_rm(id: int = typer.Argument(..., help="削除する think 項目ID。")) -> None:
    """to think 項目を削除する (確認なし)。"""
    conn = db.connect()
    try:
        cur = conn.execute("DELETE FROM think WHERE id = ?", (id,))
        conn.commit()
        if cur.rowcount == 0:
            typer.echo(f"think #{id} が見つかりません。")
            raise typer.Exit(code=1)
        typer.echo(f"removed think #{id}")
    finally:
        conn.close()


if __name__ == "__main__":
    app()
