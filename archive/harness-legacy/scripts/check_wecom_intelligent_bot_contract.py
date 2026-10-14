"""企微智能机器人工具契约检查。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.api.integrations.wecom_intelligent_bot import (  # noqa: E402
    create_wecom_intelligent_bot_router,
)
from app.config import APP_VERSION  # noqa: E402

UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DOC_PATH = ROOT_DIR / "docs" / "architecture" / "wecom-intelligent-bot-tools.md"
ROUTE_PREFIX = "/api/v1/wecom/intelligent-bot"
EXPECTED_TOOLS = {
    "ping": "/plugins/ping",
    "order-lookup": "/tools/order-lookup",
    "product-lookup": "/tools/product-lookup",
    "knowledge-answer": "/tools/knowledge-answer",
    "customer-lookup": "/tools/customer-lookup",
    "group-campaign-summary": "/tools/group-campaign-summary",
    "handoff-pending": "/tools/handoff-pending",
    "ops-summary": "/tools/ops-summary",
    "integration-status": "/tools/integration-status",
    "offline-review-summary": "/tools/offline-review-summary",
}


@dataclass(frozen=True)
class ContractCheck:
    key: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "passed": self.passed,
            "detail": self.detail,
        }


def collect_router_paths() -> set[str]:
    router = create_wecom_intelligent_bot_router()
    return {
        route.path.removeprefix(ROUTE_PREFIX)
        for route in router.routes
        if hasattr(route, "path")
        and (
            route.path.removeprefix(ROUTE_PREFIX).startswith("/plugins/")
            or route.path.removeprefix(ROUTE_PREFIX).startswith("/tools/")
        )
    }


def collect_documented_tools() -> dict[str, str]:
    if not DOC_PATH.exists():
        return {}
    text = DOC_PATH.read_text(encoding="utf-8")
    tools: dict[str, str] = {}
    pattern = re.compile(r"\|\s*(?:P\d+)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")
    for name, path in pattern.findall(text):
        tools[name] = path
    return tools


def build_contract_checks() -> list[ContractCheck]:
    documented_tools = collect_documented_tools()
    router_paths = collect_router_paths()
    expected_paths = set(EXPECTED_TOOLS.values())
    documented_paths = set(documented_tools.values())
    missing_doc_names = sorted(set(EXPECTED_TOOLS) - set(documented_tools))
    extra_doc_names = sorted(set(documented_tools) - set(EXPECTED_TOOLS))
    missing_router_paths = sorted(expected_paths - router_paths)
    extra_router_paths = sorted(path for path in router_paths - expected_paths)
    path_mismatches = sorted(
        name
        for name, path in EXPECTED_TOOLS.items()
        if documented_tools.get(name) != path
    )
    return [
        ContractCheck(
            "document_exists",
            DOC_PATH.exists(),
            str(DOC_PATH) if DOC_PATH.exists() else "missing=" + str(DOC_PATH),
        ),
        ContractCheck(
            "documented_tool_names",
            not missing_doc_names and not extra_doc_names,
            _format_diff("missing", missing_doc_names, "extra", extra_doc_names),
        ),
        ContractCheck(
            "documented_tool_paths",
            not path_mismatches and expected_paths == documented_paths,
            _format_diff(
                "mismatch",
                path_mismatches,
                "documented_paths",
                sorted(documented_paths),
            ),
        ),
        ContractCheck(
            "router_paths",
            not missing_router_paths and not extra_router_paths,
            _format_diff("missing", missing_router_paths, "extra", extra_router_paths),
        ),
    ]


def _format_diff(
    first_label: str,
    first_values: list[str],
    second_label: str,
    second_values: list[str],
) -> str:
    if not first_values and not second_values:
        return "ready"
    return (
        f"{first_label}={', '.join(first_values) or 'none'}; "
        f"{second_label}={', '.join(second_values) or 'none'}"
    )


def build_report_metadata() -> dict[str, str]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "doc_path": str(DOC_PATH),
        "app_version": APP_VERSION,
    }


def build_json_report(checks: list[ContractCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": build_report_metadata(),
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "expected_tools": EXPECTED_TOOLS,
    }


def print_report(checks: list[ContractCheck]) -> None:
    payload = build_json_report(checks)
    print("WeCom intelligent bot contract")
    print(f"generated_at={payload['metadata']['generated_at']}")
    print(f"doc_path={DOC_PATH}")
    print(f"total={payload['total']} failed={payload['failed']}")
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status} {check.key}: {check.detail}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check WeCom intelligent bot tool contract"
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    return parser.parse_args(argv)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    output_path = expand_output_path(args.output) if args.output else None
    if output_path is not None and output_path.exists():
        print(f"报告文件已存在，拒绝覆盖: {output_path}", file=sys.stderr)
        return 2
    checks = build_contract_checks()
    if args.json:
        json_bytes = (
            json.dumps(build_json_report(checks), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is not None:
            try:
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        else:
            sys.stdout.buffer.write(json_bytes)
    else:
        print_report(checks)
    return 1 if any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
