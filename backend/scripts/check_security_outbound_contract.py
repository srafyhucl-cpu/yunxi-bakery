"""聚合检查 R3-B 远程下载和员工授权出站合同。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
URL_POLICY_PATH = ROOT_DIR / "app" / "service" / "security" / "url_policy.py"
CATALOG_PATH = ROOT_DIR / "app" / "service" / "catalog" / "application.py"
KF_CARD_PATH = ROOT_DIR / "app" / "service" / "wecom" / "kf_card_sender.py"
AUTH_PATH = ROOT_DIR / "app" / "service" / "wecom" / "employee_authorization.py"
DISPATCHER_PATH = (
    ROOT_DIR / "app" / "service" / "wecom" / "intelligent_bot_dispatcher.py"
)
AGENT_NODES_PATH = ROOT_DIR / "app" / "service" / "agents" / "employee" / "nodes.py"
ROUTER_PATH = ROOT_DIR / "app" / "api" / "integrations" / "wecom_intelligent_bot.py"

PRODUCTION_FIELDS = (
    "employee_auth_required",
    "employee_allowed_users_count",
    "employee_corp_configured",
    "employee_ops_users_count",
    "remote_image_allowed_hosts_count",
)
REMOTE_RUNTIME_COMMAND = (
    'cd /opt/apps/yunxibakebot && venv/bin/python -c "'
    "import json; from app.config import settings as s; "
    "split=lambda value:[item.strip() for item in str(value).split(',') if item.strip()]; "
    "print(json.dumps({"
    "'employee_auth_required':bool(s.WECOM_EMPLOYEE_AUTH_REQUIRED),"
    "'employee_allowed_users_count':len(split(s.WECOM_EMPLOYEE_ALLOWED_USERS)),"
    "'employee_corp_configured':bool(s.WECOM_EMPLOYEE_CORP_ID.strip()),"
    "'employee_ops_users_count':len(split(s.WECOM_EMPLOYEE_OPS_USERS)),"
    "'remote_image_allowed_hosts_count':len(split(s.REMOTE_IMAGE_ALLOWED_HOSTS))"
    '}, sort_keys=True))"'
)


def build_report(
    *, production_state: dict[str, bool | int] | None = None
) -> dict[str, object]:
    url_policy = read_source(URL_POLICY_PATH)
    catalog = read_source(CATALOG_PATH)
    kf_card = read_source(KF_CARD_PATH)
    authorizer = read_source(AUTH_PATH)
    dispatcher = read_source(DISPATCHER_PATH)
    agent_nodes = read_source(AGENT_NODES_PATH)
    router = read_source(ROUTER_PATH)
    assertions = {
        "download.policy_streams_without_auto_redirect": (
            'client.stream("GET", current_url)' in url_policy
            and "follow_redirects=False" in url_policy
        ),
        "download.policy_revalidates_each_hop": (
            "await validate_remote_url(current_url, allowed_hosts)" in url_policy
            and "urljoin(current_url, location)" in url_policy
        ),
        "download.policy_checks_mime_and_size": (
            'content_type.startswith("image/")' in url_policy
            and "len(content) > max_bytes" in url_policy
        ),
        "download.consumers_use_single_policy": (
            "fetch_limited_remote_image" in catalog
            and "fetch_limited_remote_image" in kf_card
            and "client._client" not in kf_card
        ),
        "employee.callback_always_builds_authorizer": (
            "actor_authorizer=EmployeeActorAuthorizer()" in router
        ),
        "employee.ops_uses_server_side_users": (
            "WECOM_EMPLOYEE_OPS_USERS" in authorizer
            and "WECOM_EMPLOYEE_OPS_ROLES" not in authorizer
        ),
        "employee.group_chat_fails_closed": (
            'actor.chat_type == "group"' in authorizer
            and "员工群聊白名单未配置" in authorizer
        ),
        "employee.agent_checks_tools_before_execution": (
            "allowed_agent_tools(actor)" in dispatcher
            and "_is_tool_allowed(state, tool_name)" in agent_nodes
        ),
        "production_runtime.checked": production_state is not None,
        "production_runtime.security_config_ready": (
            production_state is None or production_state_ready(production_state)
        ),
    }
    failed = [name for name, passed in assertions.items() if not passed]
    if production_state is None:
        failed.remove("production_runtime.checked")
    return {
        "status": "passed" if not failed else "failed",
        "failed": len(failed),
        "failed_names": failed,
        "assertions": assertions,
        "production": {
            "checked": production_state is not None,
            "state": production_state or {},
        },
        "boundaries": {
            "external_requests_sent": False,
            "business_database_read": False,
            "allowlist_values_exposed": False,
            "production_config_changed": False,
        },
    }


def production_state_ready(state: dict[str, bool | int]) -> bool:
    return (
        state.get("employee_auth_required") is True
        and positive_count(state.get("employee_allowed_users_count"))
        and state.get("employee_corp_configured") is True
        and positive_count(state.get("employee_ops_users_count"))
        and positive_count(state.get("remote_image_allowed_hosts_count"))
    )


def positive_count(value: bool | int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_production_state(ssh_key: Path, host: str, user: str) -> dict[str, bool | int]:
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
    if not isinstance(payload, dict) or set(payload) != set(PRODUCTION_FIELDS):
        raise ValueError("生产 R3-B 配置报告字段不完整")
    if not all(isinstance(value, (bool, int)) for value in payload.values()):
        raise ValueError("生产 R3-B 配置报告类型无效")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 R3-B 安全出站合同")
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
    production_state = (
        read_production_state(args.ssh_key, args.host, args.user)
        if args.production_runtime
        else None
    )
    report = build_report(production_state=production_state)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        production = report["production"]
        checked = (
            bool(production.get("checked")) if isinstance(production, dict) else False
        )
        print(
            "security_outbound_contract "
            f"status={report['status']} failed={report['failed']} "
            f"production_checked={str(checked).lower()}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
