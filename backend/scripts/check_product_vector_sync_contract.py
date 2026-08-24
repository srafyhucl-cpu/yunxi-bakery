"""检查商品知识向量状态机的关键结构合同。"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE_PATHS = (
    ROOT_DIR / "app/repository/knowledge_product_repo.py",
    ROOT_DIR / "app/repository/knowledge_repo.py",
    ROOT_DIR / "app/service/youzan/product_sync.py",
    ROOT_DIR / "app/service/youzan/product_reconciler.py",
    ROOT_DIR / "app/service/youzan/event_item.py",
)


def check() -> list[str]:
    """检查当前商品向量同步实现。"""
    failures: list[str] = []
    for path in SOURCE_PATHS:
        failures.extend(
            check_source(
                path.read_text(encoding="utf-8"),
                str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
            )
        )
    return failures


def check_source(source: str, relative_path: str) -> list[str]:
    """检查单个源码文件，便于测试构造违规 fixture。"""
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as exc:
        return [f"{relative_path}:{exc.lineno} 语法解析失败"]

    if relative_path.endswith("knowledge_product_repo.py"):
        return _check_product_repo(source, tree, relative_path)
    if relative_path.endswith("knowledge_repo.py"):
        return _check_generic_repo(source, relative_path)
    if relative_path.endswith("product_sync.py"):
        return _check_product_sync(tree, relative_path)
    if relative_path.endswith("product_reconciler.py"):
        return _check_reconciler(source, tree, relative_path)
    if relative_path.endswith("event_item.py"):
        return _check_event_item(tree, relative_path)
    return []


def _check_product_repo(
    source: str,
    tree: ast.Module,
    relative_path: str,
) -> list[str]:
    failures: list[str] = []
    required_methods = {
        "claim_product_vector_sync",
        "mark_product_vector_sync_success",
        "mark_product_vector_sync_failed",
        "list_product_vector_sync_candidates",
    }
    method_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for node in node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(required_methods - method_names)
    if missing:
        failures.append(f"{relative_path} 缺少商品向量状态方法: {','.join(missing)}")

    upsert_node = _find_method(tree, "upsert_product_knowledge")
    if upsert_node is None:
        failures.append(f"{relative_path} 缺少 upsert_product_knowledge")
    else:
        upsert_text = ast.get_source_segment(source, upsert_node) or ""
        if "'pending'" not in upsert_text:
            failures.append(f"{relative_path} 商品知识 upsert 未从 pending 开始")
        if "success" in upsert_text:
            failures.append(f"{relative_path} 商品知识 upsert 不得提前写入 success")

    for method_name in (
        "claim_product_vector_sync",
        "mark_product_vector_sync_success",
        "mark_product_vector_sync_failed",
    ):
        method = _find_method(tree, method_name)
        method_text = ast.get_source_segment(source, method) if method else ""
        if "updated_at = ?" not in (method_text or ""):
            failures.append(f"{relative_path} {method_name} 缺少 revision 条件")
        if "vector_sync_status = ?" not in (method_text or ""):
            failures.append(f"{relative_path} {method_name} 缺少状态条件更新")

    failed_method = _find_method(tree, "mark_product_vector_sync_failed")
    failed_text = ast.get_source_segment(source, failed_method) if failed_method else ""
    if "vector_sync_retry_count + 1" not in (failed_text or ""):
        failures.append(f"{relative_path} 失败状态未原子递增 retry_count")
    if "substr(?, 1, ?" not in (failed_text or ""):
        failures.append(f"{relative_path} 失败错误文本未限制长度")

    candidate_method = _find_method(tree, "list_product_vector_sync_candidates")
    candidate_text = (
        ast.get_source_segment(source, candidate_method) if candidate_method else ""
    )
    if "vector_synced_at <= ?" not in (candidate_text or ""):
        failures.append(f"{relative_path} 对账候选未筛选过期 syncing 租约")
    return failures


def _check_generic_repo(source: str, relative_path: str) -> list[str]:
    if (
        "get_pending_sync_entries" in source
        and "WHERE category != ? AND vector_sync_status IN" not in source
    ):
        return [f"{relative_path} 通用知识同步可能重新认领商品向量"]
    return []


def _check_product_sync(tree: ast.Module, relative_path: str) -> list[str]:
    failures: list[str] = []
    method = _find_method(tree, "sync_product_to_rag")
    if method is None:
        return [f"{relative_path} 缺少 sync_product_to_rag"]

    calls: dict[str, list[int]] = {}
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in {
            "upsert_product_knowledge",
            "claim_product_vector_sync",
            "upsert_one",
            "mark_product_vector_sync_success",
            "mark_product_vector_sync_failed",
        }:
            calls.setdefault(name, []).append(node.lineno)

    required = {
        "upsert_product_knowledge",
        "claim_product_vector_sync",
        "upsert_one",
        "mark_product_vector_sync_success",
        "mark_product_vector_sync_failed",
    }
    missing = sorted(required - calls.keys())
    if missing:
        failures.append(f"{relative_path} 缺少向量状态机调用: {','.join(missing)}")
        return failures

    sequence = [
        min(calls["upsert_product_knowledge"]),
        min(calls["claim_product_vector_sync"]),
        min(calls["upsert_one"]),
        min(calls["mark_product_vector_sync_success"]),
    ]
    if sequence != sorted(sequence):
        failures.append(
            f"{relative_path} 向量状态机顺序必须为 upsert -> claim -> vector -> success"
        )
    if min(calls["mark_product_vector_sync_failed"]) < min(calls["upsert_one"]):
        failures.append(f"{relative_path} vector 写入前不得标记商品向量 failed")
    return failures


def _check_reconciler(
    source: str,
    tree: ast.Module,
    relative_path: str,
) -> list[str]:
    failures: list[str] = []
    if "VECTOR_SYNC_RETRY_CEILING" not in source:
        failures.append(f"{relative_path} 缺少向量重试上限")
    method = _find_method(tree, "reconcile_product_vectors")
    if method is None:
        failures.append(f"{relative_path} 缺少 reconcile_product_vectors")
        return failures
    method_text = ast.get_source_segment(source, method) or ""
    for token, message in (
        ("list_product_vector_sync_candidates", "读取对账候选"),
        ("claim_product_vector_sync", "条件认领向量任务"),
        ("mark_product_vector_sync_failed", "记录向量失败"),
        ("mark_product_vector_sync_success", "记录向量成功"),
    ):
        if token not in method_text:
            failures.append(f"{relative_path} 对账服务缺少{message}")
    return failures


def _check_event_item(tree: ast.Module, relative_path: str) -> list[str]:
    failures: list[str] = []
    event_method = _find_method(tree, "handle_item_event")
    if event_method is None:
        return [f"{relative_path} 缺少 handle_item_event"]
    has_failure_guard = False
    for node in ast.walk(event_method):
        if not isinstance(node, ast.If):
            continue
        if (
            isinstance(node.test, ast.Compare)
            and "knowledge_result" in ast.unparse(node.test)
            and "WriteResult.FAILED" in ast.unparse(node.test)
        ):
            has_failure_guard = any(
                isinstance(child, ast.Raise) for child in ast.walk(node)
            )
    if not has_failure_guard:
        failures.append(f"{relative_path} 商品向量失败未阻止 Webhook 标记 processed")
    return failures


def _find_method(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    parser.parse_args()
    failures = check()
    if failures:
        print("[product-vector-sync-contract] failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[product-vector-sync-contract] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
