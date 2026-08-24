"""测量 LangChain / LangGraph 的本机导入和最小图运行成本。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _rss_mb() -> float | None:
    try:
        import psutil
    except Exception:
        return None
    process = psutil.Process(os.getpid())
    return round(process.memory_info().rss / 1024 / 1024, 2)


def _timed_import(module_name: str) -> dict[str, float | str | None]:
    rss_before = _rss_mb()
    started = time.perf_counter()
    module = importlib.import_module(module_name)
    elapsed = time.perf_counter() - started
    rss_after = _rss_mb()
    return {
        "module": module_name,
        "seconds": round(elapsed, 3),
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "version": getattr(module, "__version__", ""),
    }


class ProbeState(TypedDict):
    message: str
    result: str


def _run_minimal_graph() -> dict[str, object]:
    from langgraph.graph import END, START, StateGraph

    def answer(state: ProbeState) -> ProbeState:
        return {"message": state["message"], "result": "ok:" + state["message"]}

    rss_before = _rss_mb()
    started = time.perf_counter()
    builder = StateGraph(ProbeState)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile()
    compile_seconds = time.perf_counter() - started

    started = time.perf_counter()
    result = graph.invoke({"message": "ping", "result": ""})
    invoke_seconds = time.perf_counter() - started
    rss_after = _rss_mb()
    return {
        "compile_seconds": round(compile_seconds, 3),
        "invoke_seconds": round(invoke_seconds, 3),
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-app-import", action="store_true")
    args = parser.parse_args()

    tracemalloc.start()
    report: dict[str, object] = {
        "python": sys.version,
        "rss_start_mb": _rss_mb(),
        "imports": [],
    }

    imports: list[dict[str, float | str | None]] = []
    for module_name in [
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langgraph",
    ]:
        imports.append(_timed_import(module_name))
    report["imports"] = imports
    report["minimal_graph"] = _run_minimal_graph()

    if args.include_app_import:
        rss_before = _rss_mb()
        started = time.perf_counter()
        import app.main as app_main

        report["app_import"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "rss_before_mb": rss_before,
            "rss_after_mb": _rss_mb(),
            "app_loaded": bool(app_main.app),
        }

    current, peak = tracemalloc.get_traced_memory()
    report["tracemalloc_current_mb"] = round(current / 1024 / 1024, 2)
    report["tracemalloc_peak_mb"] = round(peak / 1024 / 1024, 2)
    report["rss_end_mb"] = _rss_mb()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
