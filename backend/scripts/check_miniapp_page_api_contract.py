"""MiniApp 页面 API 覆盖合约静态验收。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = (
    ROOT_DIR / "docs" / "architecture" / "miniapp-page-api-coverage-contract.md"
)
REQUIRED_PAGES = (
    "pages/home/index",
    "pages/products/index",
    "pages/product-detail/index",
    "pages/cart/index",
    "pages/checkout/index",
    "pages/policy/index",
    "pages/address/index",
    "pages/orders/index",
    "pages/order-detail/index",
    "pages/group-registration/index",
    "pages/chat/index",
    "pages/profile/index",
)
REQUIRED_API_PREFIXES = (
    "/api/v1/miniapp/pages/home",
    "/api/v1/miniapp/products",
    "/api/v1/miniapp/product-categories",
    "/api/v1/miniapp/addresses",
    "/api/v1/miniapp/orders",
    "/api/v1/miniapp/chat/messages",
    "/api/v1/miniapp/chat/transfer",
    "/api/v1/miniapp/group-registrations",
    "/api/v1/miniapp/shop-settings",
)
REQUIRED_PENDING_PLATFORM_APIS = (
    "GET /api/v1/miniapp/member/benefits",
    "GET /api/v1/miniapp/member/points",
    "GET /api/v1/miniapp/member/balance",
    "GET /api/v1/miniapp/coupons",
    "配送费 / 满减 / 活动价",
)
REQUIRED_BOUNDARIES = (
    "MiniApp 不得新增客户主档模型",
    "MiniApp 不得新增商品定价、库存、分类真相",
    "MiniApp 不得实现订单状态流转规则",
    "MiniApp 不得本地计算会员权益、积分、储值、优惠券、配送费、满减或活动价",
    "MiniApp 不得把 `mock-pay` 当成正式支付能力",
    "MiniApp 不得把本地 mock 数据覆盖真实 API 响应",
    "缺 API 时先回 Platform 定义契约",
    "双仓联动功能必须使用同一个 `trace_id`",
)
REQUIRED_VALIDATION_ENTRIES = (
    "npm run check:miniapp",
    "npm run typecheck",
    "npm run release:readiness",
    "真机验收清单覆盖商品、购物车、结算、支付、客服入口",
)
FORBIDDEN_DIRECTIVES = (
    "在 MiniApp 写业务规则",
    "前端自行计算最终价格",
    "本地 mock 规则伪装成真实权益",
)


@dataclass(frozen=True)
class ContractCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def load_contract(path: Path = CONTRACT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def validate_contract(content: str) -> list[ContractCheck]:
    has_content = bool(content.strip())
    return [
        ContractCheck(
            "contract.exists",
            has_content,
            "" if has_content else "contract is empty",
        ),
        *_check_required_items("page", REQUIRED_PAGES, content),
        *_check_required_items("api", REQUIRED_API_PREFIXES, content),
        *_check_required_items(
            "pending_platform_api", REQUIRED_PENDING_PLATFORM_APIS, content
        ),
        *_check_required_items("boundary", REQUIRED_BOUNDARIES, content),
        *_check_required_items("validation", REQUIRED_VALIDATION_ENTRIES, content),
        *_check_forbidden_directives(content),
        _check_no_placeholders(content),
    ]


def _check_required_items(
    prefix: str,
    items: tuple[str, ...],
    content: str,
) -> list[ContractCheck]:
    return [
        ContractCheck(
            f"{prefix}.{item}",
            item in content,
            "" if item in content else f"required {prefix} missing",
        )
        for item in items
    ]


def _check_forbidden_directives(content: str) -> list[ContractCheck]:
    return [
        ContractCheck(
            f"forbidden.{item}",
            item not in content,
            "" if item not in content else "forbidden MiniApp directive found",
        )
        for item in FORBIDDEN_DIRECTIVES
    ]


def _check_no_placeholders(content: str) -> ContractCheck:
    placeholders = ("TBD", "TODO", "待定", "占位")
    found = [item for item in placeholders if item in content]
    return ContractCheck(
        "contract.no_placeholders",
        not found,
        "" if not found else f"placeholders found: {', '.join(found)}",
    )


def build_json_report(checks: list[ContractCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "contract": str(CONTRACT_PATH),
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check MiniApp page API coverage contract"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = validate_contract(load_contract())
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "miniapp_page_api_contract "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"miniapp_page_api_contract status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
