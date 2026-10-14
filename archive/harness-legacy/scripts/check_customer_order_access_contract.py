"""检查客户订单与物流工具始终携带可信身份范围。"""

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CUSTOMER_TOOLS_PATH = ROOT_DIR / "app/service/agents/tools/customer.py"
ORDER_TOOL_NAMES = frozenset({"get_order_info", "get_logistics_info"})
IDENTITY_KEYWORDS = frozenset({"buyer_id", "outer_user_id"})


def check_source(source: str, relative_path: str) -> list[str]:
    """检查客户工具源码中的订单范围合同。"""
    tree = ast.parse(source, filename=relative_path)
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = _call_name(node)
        if function_name in ORDER_TOOL_NAMES:
            keyword_names = {keyword.arg for keyword in node.keywords}
            missing = sorted(IDENTITY_KEYWORDS - keyword_names)
            if missing:
                failures.append(
                    f"{relative_path}:{node.lineno} {function_name} "
                    f"缺少身份参数: {','.join(missing)}"
                )
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get_by_order_no":
            failures.append(
                f"{relative_path}:{node.lineno} 禁止客户工具调用无范围 get_by_order"
            )
    return failures


def check() -> list[str]:
    """检查当前客户工具实现。"""
    return check_source(
        CUSTOMER_TOOLS_PATH.read_text(encoding="utf-8"),
        "app/service/agents/tools/customer.py",
    )


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def main() -> int:
    failures = check()
    if failures:
        print("[customer-order-access-contract] failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[customer-order-access-contract] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
