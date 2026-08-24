"""检查生产运行时 /health 与 /ready 是否已切到目标版本。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_PATH = ROOT_DIR / "VERSION"
DEFAULT_BASE_URL = "https://yunxifood.cn"
REQUEST_TIMEOUT_SECONDS = 5
HEALTH_PATH = "/health"
READY_PATH = "/ready"
EXPECTED_HEALTH_STATUS = "ok"
EXPECTED_READY_STATUS = "ready"


@dataclass(frozen=True)
class RuntimeEndpointResult:
    name: str
    url: str
    status: str
    expected_status: str
    version: str
    expected_version: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "expected_status": self.expected_status,
            "version": self.version,
            "expected_version": self.expected_version,
            "passed": self.passed,
            "detail": self.detail,
        }


async def build_runtime_version_report(
    *,
    base_url: str = DEFAULT_BASE_URL,
    expected_version: str | None = None,
) -> dict[str, object]:
    target_version = expected_version or read_expected_version()
    normalized_base_url = normalize_base_url(base_url)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        results = [
            await check_runtime_endpoint(
                client,
                base_url=normalized_base_url,
                path=HEALTH_PATH,
                name="health",
                expected_status=EXPECTED_HEALTH_STATUS,
                expected_version=target_version,
            ),
            await check_runtime_endpoint(
                client,
                base_url=normalized_base_url,
                path=READY_PATH,
                name="ready",
                expected_status=EXPECTED_READY_STATUS,
                expected_version=target_version,
            ),
        ]
    failed_results = [result for result in results if not result.passed]
    endpoint_versions = {
        result.name: result.version for result in results if result.version
    }
    return {
        "status": "passed" if not failed_results else "failed",
        "generated_at": utc_now(),
        "base_url": normalized_base_url,
        "expected_version": target_version,
        "endpoint_versions": endpoint_versions,
        "total": len(results),
        "failed": len(failed_results),
        "results": [result.to_dict() for result in results],
        "failed_names": [result.name for result in failed_results],
    }


async def check_runtime_endpoint(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    path: str,
    name: str,
    expected_status: str,
    expected_version: str,
) -> RuntimeEndpointResult:
    url = urljoin(base_url + "/", path.lstrip("/"))
    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return RuntimeEndpointResult(
            name=name,
            url=url,
            status="request_failed",
            expected_status=expected_status,
            version="",
            expected_version=expected_version,
            passed=False,
            detail=str(exc) or exc.__class__.__name__,
        )
    if not isinstance(payload, dict):
        return RuntimeEndpointResult(
            name=name,
            url=url,
            status="invalid_payload",
            expected_status=expected_status,
            version="",
            expected_version=expected_version,
            passed=False,
            detail="response JSON is not an object",
        )
    actual_status = str(payload.get("status", ""))
    actual_version = str(payload.get("version", ""))
    passed = actual_status == expected_status and actual_version == expected_version
    return RuntimeEndpointResult(
        name=name,
        url=url,
        status=actual_status,
        expected_status=expected_status,
        version=actual_version,
        expected_version=expected_version,
        passed=passed,
        detail="" if passed else build_mismatch_detail(payload),
    )


def build_mismatch_detail(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def read_expected_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check production /health and /ready runtime version"
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="生产服务根地址",
    )
    parser.add_argument(
        "--expected-version",
        help="期望生产接口返回的 VERSION；默认读取 VERSION 文件",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    return parser.parse_args(argv)


async def main_async(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = await build_runtime_version_report(
        base_url=args.base_url,
        expected_version=args.expected_version,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_summary(report: dict[str, object]) -> None:
    versions = sorted(set(str(value) for value in report["endpoint_versions"].values()))
    print(
        "langchain_production_runtime_version "
        f"status={report['status']} failed={report['failed']} "
        f"expected_version={report['expected_version']} "
        f"runtime_versions={','.join(versions) or 'missing'}"
    )
    for result in report["results"]:
        if isinstance(result, dict) and result.get("passed") is not True:
            print(
                f"FAIL {result.get('name')}: "
                f"status={result.get('status')} version={result.get('version')}"
            )


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_production_runtime_version")
    print(f"status={report['status']} failed={report['failed']}")
    print(f"expected_version={report['expected_version']}")
    for result in report["results"]:
        if isinstance(result, dict):
            mark = "PASS" if result.get("passed") else "FAIL"
            print(
                f"{mark} {result.get('name')} "
                f"status={result.get('status')} version={result.get('version')}"
            )


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
