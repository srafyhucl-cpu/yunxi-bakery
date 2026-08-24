"""轻量加载 LangGraph ToolNode，避免冷启动导入重依赖。"""

from functools import lru_cache
import importlib.util
import sys
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def load_tool_node_class() -> Any:
    """加载 langgraph.prebuilt.tool_node.ToolNode，绕开 prebuilt 包入口。

    ``langgraph.prebuilt.__init__`` 会急切导入 ``create_react_agent``，
    连带加载 transformers/torch，冷进程约 10 秒。这里按文件直接加载
    ``tool_node.py``，其本身不依赖这些重依赖，行为保持与官方导入一致。
    """
    langgraph_spec = importlib.util.find_spec("langgraph")
    if langgraph_spec is None or not langgraph_spec.submodule_search_locations:
        raise ImportError("未找到 langgraph 包路径")
    package_root = Path(next(iter(langgraph_spec.submodule_search_locations)))
    tool_node_path = package_root / "prebuilt" / "tool_node.py"
    if not tool_node_path.is_file():
        raise ImportError(f"找不到 LangGraph ToolNode 文件: {tool_node_path}")

    module_name = "_langgraph_tool_node_runtime"
    spec = importlib.util.spec_from_file_location(module_name, tool_node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 LangGraph ToolNode: {tool_node_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.ToolNode
