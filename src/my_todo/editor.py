"""$EDITOR (vim) 連携 (design.md 5.1, F-3)。

一時ファイル経由で本文を編集する。新規追加時は空、編集時は既存本文を投入。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import typer


def edit_text(initial: str = "") -> str:
    """$EDITOR を開いて本文を編集し、結果の文字列を返す。

    1. 一時ファイルに initial を書き込む。
    2. os.environ.get("EDITOR", "vim") を subprocess で起動。
    3. 終了後に読み戻して返す (末尾の余分な改行は除去)。

    エディタが見つからない / 異常終了した場合は、トレースバックではなく
    クリーンなメッセージを表示して中止する。
    """
    editor = os.environ.get("EDITOR", "vim")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as tf:
        tf.write(initial)
        tmp_path = Path(tf.name)

    try:
        subprocess.run([*editor.split(), str(tmp_path)], check=True)
        return tmp_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        typer.echo(f"エディタ '{editor}' が見つかりません ($EDITOR を確認してください)。")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError:
        typer.echo("エディタが異常終了したため中止しました。")
        raise typer.Exit(code=1)
    finally:
        tmp_path.unlink(missing_ok=True)
