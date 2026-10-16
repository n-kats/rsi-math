"""数学問題用のフィードバック退避操作。"""

import fcntl
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field


mcp = FastMCP("workflow_mcp")


def reject_feedback_turn(project_root: Path, turn: int) -> dict[str, str | int]:
    """指定ターンを退避し、既存の退避記録は上書きしない。"""
    if type(turn) is not int or turn < 1:
        raise ValueError("turnには1以上の整数を指定してください。")

    project_root = project_root.resolve(strict=True)
    feedbacks = project_root / "feedbacks"
    rejected = project_root / "rejected_feedbacks"
    for directory in (feedbacks, rejected):
        if directory.is_symlink():
            raise ValueError("保存先にシンボリックリンクは使えません。")
        directory.mkdir(exist_ok=True)

    turn_name = f"turn_{turn:03d}"
    source = feedbacks / turn_name
    destination = rejected / turn_name

    with (rejected / ".reject.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            raise ValueError("このターンは既に退避されています。上書きは行いません。")
        if source.is_symlink():
            raise ValueError("対象ターンにシンボリックリンクは使えません。")
        if not source.is_dir():
            raise ValueError("対象ターンのフィードバックディレクトリがありません。")

        for entry in source.rglob("*"):
            mode = entry.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("対象ターンには通常ファイルとディレクトリだけを置いてください。")

        # 別々のbind mount間ではrenameできないため、退避を完了してから元を除去する。
        staging = Path(tempfile.mkdtemp(prefix=".reject-", dir=rejected))
        try:
            shutil.copytree(source, staging / "feedback", symlinks=True)
            for entry in (staging / "feedback").rglob("*"):
                if entry.is_symlink():
                    raise ValueError("退避中にシンボリックリンクが検出されました。")
            (staging / "feedback").rename(destination)
        finally:
            shutil.rmtree(staging)

        # 除去に失敗しても、退避先の完全なコピーは保持する。
        shutil.rmtree(source)

    return {"status": "rejected", "turn": turn, "feedback_path": f"feedbacks/{turn_name}"}


@mcp.tool
def reject_feedback(turn: Annotated[int, Field(strict=True, ge=1)]) -> dict[str, str | int]:
    """指定ターンのフィードバック全体を通常の参照範囲から退避する。

    turnには1以上のターン番号を指定する。採否の判断と
    feedbacks/README.mdからの該当参照・要約の除去は呼び出すエージェントが行う。
    """
    root = Path(os.environ.get("WORKFLOW_MCP_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
    try:
        return reject_feedback_turn(root, turn)
    except ValueError as error:
        raise ToolError(str(error)) from None
    except OSError:
        raise ToolError("退避操作を完了できませんでした。管理者が保存先と権限を確認してください。") from None


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("WORKFLOW_MCP_PORT", "8765")),
    )
