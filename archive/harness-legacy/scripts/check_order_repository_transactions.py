"""检查订单域 repository 不自行提交事务。"""

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("app/repository/order_repo.py", ("OrderRepo",)),
    ("app/repository/youzan_inventory_repo.py", ("YouzanInventoryRepo",)),
    ("app/repository/order_event_repo.py", ("OrderEventRepo",)),
    ("app/repository/session_repo.py", ("SessionRepo.get_or_create",)),
)


def _target_functions(tree: ast.AST, target: str) -> list[ast.AsyncFunctionDef]:
    if "." in target:
        class_name, function_name = target.split(".", 1)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            return [
                item
                for item in node.body
                if isinstance(item, ast.AsyncFunctionDef) and item.name == function_name
            ]
        return []
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == target
        for item in node.body
        if isinstance(item, ast.AsyncFunctionDef)
    ]


def check() -> list[str]:
    failures: list[str] = []
    for relative_path, targets in CHECKS:
        path = ROOT_DIR / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for target in targets:
            for function in _target_functions(tree, target):
                start = function.lineno - 1
                end = function.end_lineno or function.lineno
                if any(".commit(" in line for line in lines[start:end]):
                    failures.append(
                        f"{relative_path}:{function.lineno} {target} 包含 commit"
                    )
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("[order-repository-transactions] failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[order-repository-transactions] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
