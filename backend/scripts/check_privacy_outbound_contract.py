"""聚合检查模型外发脱敏、trace 过滤和生产关闭态。"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICE_DIR = ROOT_DIR / "app" / "service"
sys.path.insert(0, str(ROOT_DIR))

from app.service.agents.observability import safe_trace_payload  # noqa: E402
from app.service.privacy_redaction import redact_external_messages  # noqa: E402

MODEL_FACTORY_NAME = "get_langchain_chat_model"
REDACTION_CALL_NAMES = frozenset(
    {
        "redact_external_text",
        "redact_external_messages",
        "redact_external_langchain_messages",
    }
)
ALLOWED_CHAT_MODEL_FACTORY = Path("app/service/agents/llm.py")
ALLOWED_OPENAI_SDK_ADAPTER = Path("app/service/llm/client.py")
PRODUCTION_SAFE_FLAGS = (
    "ENABLE_OFFLINE_QA",
    "ENABLE_OFFLINE_KNOWLEDGE_GAP",
    "ENABLE_OFFLINE_MEMORY",
    "LANGCHAIN_TRACING_ENABLED",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY_CONFIGURED",
)
SENSITIVE_VALUES = (
    "not-a-phone-format",
    "望京SOHO T3 1201",
    "short-open-id",
    "short-order",
    "没有格式特征的原始消息",
    "sample-secret-token",
)
REMOTE_RUNTIME_COMMAND = (
    'cd /opt/apps/yunxibakebot && venv/bin/python -c "'
    "import json, os; from app.config import settings as s; "
    "truth=lambda v: str(v).strip().lower() in ('1','true','yes','on'); "
    "print(json.dumps({"
    "'ENABLE_OFFLINE_QA': bool(s.ENABLE_OFFLINE_QA),"
    "'ENABLE_OFFLINE_KNOWLEDGE_GAP': bool(s.ENABLE_OFFLINE_KNOWLEDGE_GAP),"
    "'ENABLE_OFFLINE_MEMORY': bool(s.ENABLE_OFFLINE_MEMORY),"
    "'LANGCHAIN_TRACING_ENABLED': bool(s.LANGCHAIN_TRACING_ENABLED),"
    "'LANGCHAIN_TRACING_V2': truth(os.getenv('LANGCHAIN_TRACING_V2','')),"
    "'LANGSMITH_TRACING': truth(os.getenv('LANGSMITH_TRACING','')),"
    "'LANGSMITH_API_KEY_CONFIGURED': bool(s.LANGSMITH_API_KEY)"
    '}, sort_keys=True))"'
)


def build_report(
    *, production_flags: dict[str, bool] | None = None
) -> dict[str, object]:
    model_call_files = discover_call_files(MODEL_FACTORY_NAME)
    redaction_call_files = discover_redaction_call_files()
    direct_chat_model_files = discover_symbol_files("ChatOpenAI")
    direct_openai_files = discover_symbol_files("AsyncOpenAI")
    redaction_markers = dynamic_redaction_markers()
    trace_markers = dynamic_trace_markers()
    assertions = {
        "model_calls.discovered": bool(model_call_files),
        "model_calls.all_use_redaction": model_call_files <= redaction_call_files,
        "chat_model.single_factory": direct_chat_model_files
        <= {ALLOWED_CHAT_MODEL_FACTORY},
        "openai_sdk.asr_only": direct_openai_files <= {ALLOWED_OPENAI_SDK_ADAPTER},
        "dynamic_payload.no_sensitive_values": not redaction_markers,
        "trace_metadata.no_sensitive_values": not trace_markers,
        "production_runtime.checked": production_flags is not None,
        "production_runtime.external_paths_disabled": production_flags is None
        or all(not production_flags.get(flag, True) for flag in PRODUCTION_SAFE_FLAGS),
    }
    failed = [name for name, passed in assertions.items() if not passed]
    if production_flags is None:
        failed.remove("production_runtime.checked")
    return {
        "status": "passed" if not failed else "failed",
        "failed": len(failed),
        "failed_names": failed,
        "assertions": assertions,
        "static": {
            "model_call_files": sorted(map(str, model_call_files)),
            "redaction_call_files": sorted(map(str, redaction_call_files)),
            "direct_chat_model_files": sorted(map(str, direct_chat_model_files)),
            "direct_openai_files": sorted(map(str, direct_openai_files)),
        },
        "dynamic": {
            "redaction_sensitive_markers": redaction_markers,
            "trace_sensitive_markers": trace_markers,
        },
        "production": {
            "checked": production_flags is not None,
            "flags": production_flags or {},
        },
        "boundaries": {
            "external_llm_called": False,
            "langsmith_external_export": False,
            "business_database_read": False,
            "contains_sensitive_data": False,
        },
    }


def discover_call_files(function_name: str) -> set[Path]:
    return {
        relative_path
        for relative_path, tree in iter_service_trees()
        if any(
            isinstance(node, ast.Call) and call_name(node.func) == function_name
            for node in ast.walk(tree)
        )
    }


def discover_redaction_call_files() -> set[Path]:
    return {
        relative_path
        for relative_path, tree in iter_service_trees()
        if any(
            isinstance(node, ast.Call) and call_name(node.func) in REDACTION_CALL_NAMES
            for node in ast.walk(tree)
        )
    }


def discover_symbol_files(symbol_name: str) -> set[Path]:
    return {
        relative_path
        for relative_path, tree in iter_service_trees()
        if any(
            isinstance(node, (ast.Name, ast.Attribute))
            and call_name(node) == symbol_name
            for node in ast.walk(tree)
        )
    }


def iter_service_trees() -> list[tuple[Path, ast.AST]]:
    return [
        (
            path.relative_to(ROOT_DIR),
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
        )
        for path in sorted(SERVICE_DIR.rglob("*.py"))
    ]


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def dynamic_redaction_markers() -> list[str]:
    payload = redact_external_messages(
        [
            {
                "role": "tool",
                "content": {
                    "receiver_phone": SENSITIVE_VALUES[0],
                    "delivery_address": SENSITIVE_VALUES[1],
                    "open_id": SENSITIVE_VALUES[2],
                    "order_no": SENSITIVE_VALUES[3],
                    "history_text": SENSITIVE_VALUES[4],
                },
            }
        ]
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return [marker for marker in SENSITIVE_VALUES if marker in serialized]


def dynamic_trace_markers() -> list[str]:
    payload = safe_trace_payload(
        {
            "case_id": "privacy-outbound",
            "access_token": SENSITIVE_VALUES[5],
            "customer_profile": {"phone": SENSITIVE_VALUES[0]},
            "tool_result": {"order_no": SENSITIVE_VALUES[3]},
        }
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return [marker for marker in SENSITIVE_VALUES if marker in serialized]


def read_production_flags(ssh_key: Path, host: str, user: str) -> dict[str, bool]:
    completed = subprocess.run(
        [
            "ssh.exe",
            "-i",
            str(ssh_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{user}@{host}",
            REMOTE_RUNTIME_COMMAND,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload: Any = json.loads(completed.stdout)
    if not isinstance(payload, dict) or set(payload) != set(PRODUCTION_SAFE_FLAGS):
        raise ValueError("生产隐私开关报告字段不完整")
    if not all(isinstance(value, bool) for value in payload.values()):
        raise ValueError("生产隐私开关必须全部是布尔值")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查完整隐私出站合同")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--production-runtime", action="store_true")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--host", default="47.94.102.250")
    parser.add_argument("--user", default="root")
    args = parser.parse_args()
    if args.production_runtime and args.ssh_key is None:
        parser.error("--production-runtime 必须提供 --ssh-key")
    return args


def main() -> int:
    args = parse_args()
    production_flags = (
        read_production_flags(args.ssh_key, args.host, args.user)
        if args.production_runtime
        else None
    )
    report = build_report(production_flags=production_flags)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        production = report["production"]
        production_checked = (
            bool(production.get("checked")) if isinstance(production, dict) else False
        )
        print(
            "privacy_outbound_contract "
            f"status={report['status']} failed={report['failed']} "
            f"production_checked={str(production_checked).lower()}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
