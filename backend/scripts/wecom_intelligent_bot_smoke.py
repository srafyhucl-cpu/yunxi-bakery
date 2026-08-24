"""企微智能机器人工具只读冒烟报告。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION, settings  # noqa: E402

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
REQUEST_TIMEOUT_SECONDS = 10
UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_BASE_URL = "http://127.0.0.1:7001"
SENSITIVE_MARKERS = (
    "X-Yunxi-Bot-Key",
    "Authorization",
    "WECOM_BOT_PLUGIN_API_KEY",
)
REQUIRED_RESULT_FIELDS = ("result", "resultText")


@dataclass(frozen=True)
class ToolProbe:
    name: str
    path: str
    payload: dict[str, Any]
    expected_ok: bool | None = True


@dataclass(frozen=True)
class ProbeResult:
    name: str
    path: str
    status_code: int
    passed: bool
    ok: bool | None
    tool: str
    summary: str
    elapsed_ms: int
    result_present: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "status_code": self.status_code,
            "passed": self.passed,
            "ok": self.ok,
            "tool": self.tool,
            "summary": self.summary,
            "elapsed_ms": self.elapsed_ms,
            "result_present": self.result_present,
            "detail": self.detail,
        }


TOOL_PROBES: tuple[ToolProbe, ...] = (
    ToolProbe("ping", "/api/v1/wecom/intelligent-bot/plugins/ping", {"text": "ping"}),
    ToolProbe(
        "order-lookup",
        "/api/v1/wecom/intelligent-bot/tools/order-lookup",
        {"query": "测试", "limit": 1},
    ),
    ToolProbe(
        "product-lookup",
        "/api/v1/wecom/intelligent-bot/tools/product-lookup",
        {"query": "蛋糕", "limit": 1},
    ),
    ToolProbe(
        "knowledge-answer",
        "/api/v1/wecom/intelligent-bot/tools/knowledge-answer",
        {"question": "配送范围怎么说", "limit": 1},
    ),
    ToolProbe(
        "customer-lookup",
        "/api/v1/wecom/intelligent-bot/tools/customer-lookup",
        {"query": "测试"},
    ),
    ToolProbe(
        "group-campaign-summary",
        "/api/v1/wecom/intelligent-bot/tools/group-campaign-summary",
        {"campaignId": "smoke-campaign-not-exist"},
        expected_ok=False,
    ),
    ToolProbe(
        "handoff-pending",
        "/api/v1/wecom/intelligent-bot/tools/handoff-pending",
        {"limit": 1},
    ),
    ToolProbe(
        "ops-summary",
        "/api/v1/wecom/intelligent-bot/tools/ops-summary",
        {},
    ),
    ToolProbe(
        "integration-status",
        "/api/v1/wecom/intelligent-bot/tools/integration-status",
        {"query": "", "limit": 1},
    ),
    ToolProbe(
        "offline-review-summary",
        "/api/v1/wecom/intelligent-bot/tools/offline-review-summary",
        {},
    ),
)


def parse_base_url(base_url: str) -> str:
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("--base-url 仅支持 http 或 https。")
    if not parsed_url.hostname:
        raise ValueError("--base-url 必须包含主机名。")
    if parsed_url.path not in {"", "/"} or parsed_url.params or parsed_url.query:
        raise ValueError("--base-url 只接受根地址，不要包含路径、参数或查询串。")
    return base_url.rstrip("/")


def resolve_plugin_key() -> str:
    env_value = os.getenv("WECOM_BOT_PLUGIN_API_KEY", "").strip()
    config_value = settings.WECOM_BOT_PLUGIN_API_KEY.strip()
    return env_value or config_value


def build_report_metadata(base_url: str) -> dict[str, str]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "base_url": base_url,
        "app_version": APP_VERSION,
        "sensitive_data": "redacted; plugin key and headers are not recorded",
    }


async def request_probe(
    client: httpx.AsyncClient,
    base_url: str,
    probe: ToolProbe,
    plugin_key: str,
) -> ProbeResult:
    started_at = perf_counter()
    try:
        response = await client.post(
            base_url + probe.path,
            headers={"X-Yunxi-Bot-Key": plugin_key},
            json=probe.payload,
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return ProbeResult(
            probe.name,
            probe.path,
            0,
            False,
            None,
            "",
            "",
            elapsed_ms,
            str(exc) or exc.__class__.__name__,
        )
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    ok_value = payload.get("ok") if isinstance(payload, dict) else None
    passed = response.status_code == HTTP_OK
    if probe.expected_ok is not None:
        passed = passed and ok_value is probe.expected_ok
    result_present = has_required_result_fields(payload)
    passed = passed and result_present
    return ProbeResult(
        probe.name,
        probe.path,
        response.status_code,
        passed,
        ok_value if isinstance(ok_value, bool) else None,
        str(payload.get("tool") or payload.get("plugin") or ""),
        safe_summary(payload),
        elapsed_ms,
        result_present,
        "" if result_present else "missing result/resultText",
    )


async def request_auth_check(
    client: httpx.AsyncClient,
    base_url: str,
    name: str,
    headers: dict[str, str] | None = None,
    query: str = "",
) -> ProbeResult:
    path = "/api/v1/wecom/intelligent-bot/tools/order-lookup"
    started_at = perf_counter()
    try:
        response = await client.post(
            base_url + path + query,
            headers=headers,
            json={"query": "测试"},
        )
        detail = "" if response.status_code == HTTP_UNAUTHORIZED else response.text[:80]
    except httpx.HTTPError as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return ProbeResult(name, path, 0, False, None, "", "", elapsed_ms, str(exc))
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    return ProbeResult(
        name,
        path,
        response.status_code,
        response.status_code == HTTP_UNAUTHORIZED,
        None,
        "",
        "鉴权拒绝符合预期" if response.status_code == HTTP_UNAUTHORIZED else "",
        elapsed_ms,
        False,
        detail,
    )


def safe_summary(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    summary = (
        payload.get("summary")
        or payload.get("message")
        or payload.get("answer")
        or payload.get("status")
        or ""
    )
    text = str(summary)
    return text[:120]


def has_required_result_fields(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(
        isinstance(payload.get(field_name), str) and payload[field_name].strip()
        for field_name in REQUIRED_RESULT_FIELDS
    )


async def run_smoke(base_url: str, plugin_key: str) -> list[ProbeResult]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        results = [
            await request_probe(client, base_url, probe, plugin_key)
            for probe in TOOL_PROBES
        ]
        results.append(
            await request_auth_check(
                client,
                base_url,
                "wrong-key-rejected",
                {"X-Yunxi-Bot-Key": "wrong-secret"},
            )
        )
        results.append(
            await request_auth_check(client, base_url, "missing-key-rejected")
        )
        results.append(
            await request_auth_check(
                client,
                base_url,
                "query-key-rejected",
                query="?api_key=wrong-secret",
            )
        )
    return results


def build_json_report(base_url: str, results: list[ProbeResult]) -> dict[str, object]:
    failed_results = [result for result in results if not result.passed]
    payload = {
        "status": "passed" if not failed_results else "failed",
        "metadata": build_report_metadata(base_url),
        "total": len(results),
        "failed": len(failed_results),
        "results": [result.to_dict() for result in results],
        "failed_names": [result.name for result in failed_results],
    }
    ensure_report_is_sanitized(payload)
    return payload


def ensure_report_is_sanitized(payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    leaked_markers = [marker for marker in SENSITIVE_MARKERS if marker in serialized]
    if leaked_markers:
        raise ValueError("报告包含敏感字段标记: " + ", ".join(leaked_markers))


def print_results(base_url: str, results: list[ProbeResult]) -> None:
    payload = build_json_report(base_url, results)
    print("WeCom intelligent bot smoke")
    print(f"generated_at={payload['metadata']['generated_at']}")
    print(f"base_url={base_url}")
    print(f"app_version={APP_VERSION}")
    print(f"total={payload['total']} failed={payload['failed']}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}: status={result.status_code} {result.summary}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WeCom intelligent bot smoke test")
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，报告不会包含插件密钥或请求头。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="目标服务根地址，例如 https://yunxifood.cn。",
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


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        base_url = parse_base_url(args.base_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    plugin_key = resolve_plugin_key()
    if not plugin_key:
        print("WECOM_BOT_PLUGIN_API_KEY 未配置。", file=sys.stderr)
        return 2
    output_path = expand_output_path(args.output) if args.output else None
    if output_path is not None and output_path.exists():
        print(f"报告文件已存在，拒绝覆盖: {output_path}", file=sys.stderr)
        return 2
    results = await run_smoke(base_url, plugin_key)
    if args.json:
        report = build_json_report(base_url, results)
        json_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if output_path is not None:
            try:
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        else:
            sys.stdout.buffer.write(json_bytes)
    else:
        print_results(base_url, results)
    return 1 if any(not result.passed for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
