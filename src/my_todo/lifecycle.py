"""ライフサイクル自動移行ロジック (design.md 第4節, F-5)。

常駐プロセスを持たないため、CLI実行時に遅延的 (lazy) に昇格させる。
昇格基準は created_at 固定。ユーザー操作で寿命がリセットされないようにする。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .db import now_iso, parse_iso

# lifecycle 段階の順序。
STAGES = ("short", "mid", "long")

# 各段階へ「昇格する」ために必要な、created_at からの経過日数しきい値。
# short→mid: 約7日 / mid→long: 約30日 (design.md 4.1)。
PROMOTE_THRESHOLDS_DAYS = {
    "mid": 7,
    "long": 30,
}


def target_stage(created_at: str, now: datetime | None = None) -> str:
    """created_at からの経過日数に応じて到達すべき lifecycle 段階を返す。

    1回のチェックで複数段階の昇格条件を満たす場合 (久しぶりの実行など) は
    最終的に到達すべき段階を返す (design.md 4.2-3)。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elapsed_days = (now - parse_iso(created_at)).days

    stage = "short"
    if elapsed_days >= PROMOTE_THRESHOLDS_DAYS["mid"]:
        stage = "mid"
    if elapsed_days >= PROMOTE_THRESHOLDS_DAYS["long"]:
        stage = "long"
    return stage


def run_promotions(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """open タスクの lifecycle を遅延昇格させる。昇格した件数を返す。

    status='open' のタスクのみ対象 (done は寿命を凍結)。
    昇格時に lifecycle / promoted_at / updated_at を更新する。
    """
    if now is None:
        now = datetime.now(timezone.utc)

    rows = conn.execute(
        "SELECT id, lifecycle, created_at FROM tasks WHERE status = 'open'"
    ).fetchall()

    promoted = 0
    ts = now_iso()
    for row in rows:
        target = target_stage(row["created_at"], now)
        if STAGES.index(target) > STAGES.index(row["lifecycle"]):
            conn.execute(
                "UPDATE tasks SET lifecycle = ?, promoted_at = ?, updated_at = ? WHERE id = ?",
                (target, ts, ts, row["id"]),
            )
            promoted += 1

    if promoted:
        conn.commit()
    return promoted
