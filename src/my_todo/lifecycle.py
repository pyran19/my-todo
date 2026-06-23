"""ライフサイクル自動移行ロジック (design.md 第4節, F-5)。

常駐プロセスを持たないため、CLI実行時に遅延的 (lazy) に昇格させる。
昇格基準は created_at 固定。ユーザー操作で寿命がリセットされないようにする。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .db import now_iso, parse_iso

# lifecycle 段階の順序。
STAGES = ("short", "mid", "long")

# 各段階へ「昇格する」ために必要な、created_at からの経過日数しきい値。
# short→mid: 約7日 / mid→long: 約30日 (design.md 4.1)。
PROMOTE_THRESHOLDS_DAYS = {
    "mid": 7,
    "long": 30,
}

# 各段階の「入口」に相当する経過日数 (= その段階の下限しきい値)。
# 手動移動 (promote/demote) 時に created_at をこの日数ぶん過去へずらすことで、
# 自動移行ロジックと矛盾しない形で段階を移す (design.md 4.3)。
STAGE_ENTRY_DAYS = {
    "short": 0,
    "mid": PROMOTE_THRESHOLDS_DAYS["mid"],
    "long": PROMOTE_THRESHOLDS_DAYS["long"],
}


def created_at_for_stage(stage: str, now: datetime | None = None) -> str:
    """指定段階の入口に相当する created_at (ISO8601 文字列) を返す。

    `now - 段階の下限日数` を created_at とすることで、
    その段階に「入ったばかり」の状態を再現する。target_stage() がちょうど
    その段階を返すため、直後の自動移行で昇格も降格もされない。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return (now - timedelta(days=STAGE_ENTRY_DAYS[stage])).isoformat()


def next_stage(stage: str) -> str | None:
    """一つ長いライフサイクル段階を返す。最長 (long) なら None。"""
    i = STAGES.index(stage)
    return STAGES[i + 1] if i + 1 < len(STAGES) else None


def prev_stage(stage: str) -> str | None:
    """一つ短いライフサイクル段階を返す。最短 (short) なら None。"""
    i = STAGES.index(stage)
    return STAGES[i - 1] if i > 0 else None


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
