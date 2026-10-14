"""企微员工助手 URL 回调端到端验收。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION, settings  # noqa: E402
from app.service.wecom.crypto import (  # noqa: E402
    decrypt,
    encrypt,
    generate_signature,
    verify_signature,
)
from scripts.wecom_employee_agent_callback_semantics import (  # noqa: E402
    CallbackSemanticRule,
    has_plain_text_violation,
    is_semantic_safe,
)
from scripts.wecom_employee_agent_probe_cases import default_probe_cases  # noqa: E402

HTTP_OK = 200
REQUEST_TIMEOUT_SECONDS = 20
UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_BASE_URL = "http://127.0.0.1:7001"
CALLBACK_PATH = "/api/v1/wecom/intelligent-bot/callback"
TEST_TOKEN = "callback-token"
TEST_AES_KEY = "MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTE"
REPLY_PREVIEW_LIMIT = 80
SENSITIVE_MARKERS = (
    "WECOM_INTELLIGENT_BOT_TOKEN",
    "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY",
    "WECOM_TOKEN",
    "WECOM_ENCODING_AES_KEY",
    "encrypt",
    "msgsignature",
)
PRIVACY_PATTERNS = (
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"\b[A-Z]?\d{14,}\b"),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    re.compile(r"(buyer|mobile|phone|address|receiver|tid|oid)", re.IGNORECASE),
    re.compile(r"\bID\s*:", re.IGNORECASE),
    re.compile(r"(手机号|电话|完整订单号|收货地址|买家ID|买家 id)", re.IGNORECASE),
)


@dataclass(frozen=True)
class CallbackCredentials:
    token: str
    encoding_aes_key: str

    @property
    def is_ready(self) -> bool:
        return bool(self.token.strip() and self.encoding_aes_key.strip())


@dataclass(frozen=True)
class CallbackProbe:
    name: str
    query: str
    required_any_terms: tuple[str, ...] = ()
    required_all_terms: tuple[str, ...] = ()
    required_all_term_groups: tuple[tuple[str, ...], ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allow_empty_result: bool = False
    allow_handoff: bool = True


@dataclass(frozen=True)
class CallbackProbeResult:
    name: str
    query: str
    status_code: int
    passed: bool
    reply_valid: bool
    privacy_safe: bool
    semantic_safe: bool
    elapsed_ms: int
    content_preview: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "query": self.query,
            "status_code": self.status_code,
            "passed": self.passed,
            "reply_valid": self.reply_valid,
            "privacy_safe": self.privacy_safe,
            "semantic_safe": self.semantic_safe,
            "elapsed_ms": self.elapsed_ms,
            "content_preview": self.content_preview,
            "detail": self.detail,
        }


def default_probes() -> tuple[CallbackProbe, ...]:
    return tuple(
        CallbackProbe(
            case.name,
            case.query,
            case.required_any_terms,
            case.required_all_terms,
            case.required_all_term_groups,
            case.forbidden_terms,
            case.allow_empty_result,
            case.allow_handoff,
        )
        for case in default_probe_cases(date.today())
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


def resolve_callback_credentials() -> CallbackCredentials | None:
    token = (
        os.getenv("WECOM_INTELLIGENT_BOT_TOKEN", "").strip()
        or settings.WECOM_INTELLIGENT_BOT_TOKEN.strip()
        or os.getenv("WECOM_TOKEN", "").strip()
        or settings.WECOM_TOKEN.strip()
    )
    aes_key = (
        os.getenv("WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY", "").strip()
        or settings.WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY.strip()
        or os.getenv("WECOM_ENCODING_AES_KEY", "").strip()
        or settings.WECOM_ENCODING_AES_KEY.strip()
    )
    credentials = CallbackCredentials(token, aes_key)
    return credentials if credentials.is_ready else None


async def run_callback_checks(
    base_url: str,
    credentials: CallbackCredentials,
) -> list[CallbackProbeResult]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        results = [
            await request_callback_probe(client, base_url, credentials, probe, index)
            for index, probe in enumerate(default_probes(), start=1)
        ]
    return results


async def request_callback_probe(
    client: httpx.AsyncClient,
    base_url: str,
    credentials: CallbackCredentials,
    probe: CallbackProbe,
    index: int,
) -> CallbackProbeResult:
    started_at = perf_counter()
    nonce = f"employee-agent-{index}"
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    try:
        msg_encrypt = encrypt(
            credentials.encoding_aes_key,
            json.dumps(build_callback_message(probe, index), ensure_ascii=False),
            "",
        )
        response = await client.post(
            base_url + CALLBACK_PATH,
            params={
                "msg_signature": generate_signature(
                    credentials.token,
                    timestamp,
                    nonce,
                    msg_encrypt,
                ),
                "timestamp": timestamp,
                "nonce": nonce,
            },
            json={"encrypt": msg_encrypt},
        )
        payload = response.json()
        reply_payload = decrypt_reply(credentials, payload)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return CallbackProbeResult(
            probe.name,
            probe.query,
            0,
            False,
            False,
            False,
            False,
            elapsed_ms,
            detail=str(exc) or exc.__class__.__name__,
        )
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    return evaluate_reply(probe, response.status_code, reply_payload, elapsed_ms)


def build_callback_message(probe: CallbackProbe, index: int) -> dict[str, object]:
    allowed_user = _first_allowlist_value(settings.WECOM_EMPLOYEE_ALLOWED_USERS)
    allowed_chat = _first_allowlist_value(settings.WECOM_EMPLOYEE_ALLOWED_CHATS)
    message: dict[str, object] = {
        "msgid": f"employee-agent-smoke-{index}",
        "aibotid": "yunxi-employee-agent",
        "chattype": "group" if allowed_chat else "single",
        "msgtype": "text",
        "from": {
            "userid": (
                allowed_user
                or settings.WECOM_STAFF_ID.strip()
                or settings.WECOM_KF_SERVICER_USERID.strip()
            )
        },
        "corpid": (
            settings.WECOM_EMPLOYEE_CORP_ID.strip() or settings.WECOM_CORP_ID.strip()
        ),
        "text": {"content": probe.query},
    }
    if allowed_chat:
        message["chatid"] = allowed_chat
    return message


def _first_allowlist_value(raw_value: str) -> str:
    return next(
        (item.strip() for item in raw_value.split(",") if item.strip()),
        "",
    )


def decrypt_reply(
    credentials: CallbackCredentials,
    payload: dict[str, object],
) -> dict[str, object]:
    msg_encrypt = str(payload["encrypt"])
    timestamp = str(payload["timestamp"])
    nonce = str(payload["nonce"])
    msg_signature = str(payload["msgsignature"])
    if not verify_signature(
        credentials.token,
        timestamp,
        nonce,
        msg_encrypt,
        msg_signature,
    ):
        raise ValueError("回复签名验证失败")
    reply_text = decrypt(credentials.encoding_aes_key, msg_encrypt)
    reply_payload = json.loads(reply_text)
    if not isinstance(reply_payload, dict):
        raise ValueError("回复明文不是 JSON 对象")
    return reply_payload


def evaluate_reply(
    probe: CallbackProbe,
    status_code: int,
    reply_payload: dict[str, object],
    elapsed_ms: int,
) -> CallbackProbeResult:
    content = extract_stream_content(reply_payload)
    reply_valid = is_valid_stream_reply(reply_payload, content)
    privacy_safe = is_privacy_safe(content)
    semantic_safe = is_semantic_safe(content, semantic_rule(probe))
    plain_text_safe = not has_plain_text_violation(content)
    detail_parts = []
    if status_code != HTTP_OK:
        detail_parts.append(f"status={status_code}")
    if not reply_valid:
        detail_parts.append("invalid stream reply")
    if not privacy_safe:
        detail_parts.append("privacy leak pattern matched")
    if not semantic_safe or not plain_text_safe:
        detail_parts.append("semantic rule mismatch")
    return CallbackProbeResult(
        name=probe.name,
        query=probe.query,
        status_code=status_code,
        passed=status_code == HTTP_OK
        and reply_valid
        and privacy_safe
        and semantic_safe
        and plain_text_safe,
        reply_valid=reply_valid,
        privacy_safe=privacy_safe,
        semantic_safe=semantic_safe and plain_text_safe,
        elapsed_ms=elapsed_ms,
        content_preview=content[:REPLY_PREVIEW_LIMIT],
        detail="; ".join(detail_parts),
    )


def semantic_rule(probe: CallbackProbe) -> CallbackSemanticRule:
    return CallbackSemanticRule(
        probe.required_any_terms,
        probe.required_all_terms,
        probe.required_all_term_groups,
        probe.forbidden_terms,
        probe.allow_empty_result,
        probe.allow_handoff,
    )


def extract_stream_content(reply_payload: dict[str, object]) -> str:
    stream = reply_payload.get("stream")
    if not isinstance(stream, dict):
        return ""
    content = stream.get("content")
    return content.strip() if isinstance(content, str) else ""


def is_valid_stream_reply(reply_payload: dict[str, object], content: str) -> bool:
    stream = reply_payload.get("stream")
    return (
        reply_payload.get("msgtype") == "stream"
        and isinstance(stream, dict)
        and stream.get("finish") is True
        and bool(content)
    )


def is_privacy_safe(content: str) -> bool:
    return not any(pattern.search(content) for pattern in PRIVACY_PATTERNS)


def build_report_metadata(base_url: str) -> dict[str, str]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "base_url": base_url,
        "app_version": APP_VERSION,
        "sensitive_data": "redacted; callback token, AES key and ciphertext are not recorded",
    }


def build_json_report(
    base_url: str,
    results: list[CallbackProbeResult],
) -> dict[str, object]:
    failed_results = [result for result in results if not result.passed]
    payload: dict[str, object] = {
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


def print_results(base_url: str, results: list[CallbackProbeResult]) -> None:
    payload = build_json_report(base_url, results)
    metadata = payload["metadata"]
    generated_at = (
        metadata.get("generated_at", "") if isinstance(metadata, dict) else ""
    )
    print("WeCom employee agent callback checks")
    print(f"generated_at={generated_at}")
    print(f"base_url={base_url}")
    print(f"app_version={APP_VERSION}")
    print(f"total={payload['total']} failed={payload['failed']}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}: status={result.status_code} {result.detail}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check WeCom employee agent URL callback replies"
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
    credentials = resolve_callback_credentials()
    if credentials is None:
        print(
            "WECOM_INTELLIGENT_BOT_TOKEN / WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY 未配置。",
            file=sys.stderr,
        )
        return 2
    output_path = expand_output_path(args.output) if args.output else None
    if output_path is not None and output_path.exists():
        print(f"报告文件已存在，拒绝覆盖: {output_path}", file=sys.stderr)
        return 2
    results = await run_callback_checks(base_url, credentials)
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
