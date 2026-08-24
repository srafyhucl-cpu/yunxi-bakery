"""轻量 ToolNode 加载器回归测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_tool_node_loader_avoids_heavy_prebuilt_imports() -> None:
    project_root = Path(__file__).resolve().parents[3]
    command = (
        "import sys; "
        "from app.service.agents.tool_node import load_tool_node_class; "
        "cls = load_tool_node_class(); "
        "print(cls.__name__); "
        "raise SystemExit(1 if 'transformers' in sys.modules or 'torch' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ToolNode"
