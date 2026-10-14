"""生成 LangChain 外部证据交接汇总包。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts import build_langchain_portfolio_evidence_packet as portfolio_packet  # noqa: E402
from scripts import build_rag_shadow_log_intake_packet as rag_packet  # noqa: E402
from scripts import build_real_conversation_replay_intake_packet as replay_packet  # noqa: E402

TRACE_ID = "20260709-langchain-ai-layer-production-enhancement"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "harness" / "langchain-external-evidence-handoff.json"
)
DEFAULT_HANDOFF_EVIDENCE_ID = "E-LANGCHAIN-EXTERNAL-EVIDENCE-HANDOFF"
LOCAL_EVIDENCE_ACTIONS = {
    "restore_portfolio_code_path_references",
    "refresh_current_version_agent_eval",
    "refresh_rag_shadow_observability_report",
    "refresh_langchain_observability_evidence",
    "refresh_strict_production_release_evidence",
}


def build_external_evidence_handoff_packet(
    *,
    operator: str = "manual_reviewer",
    handoff_evidence_id: str = DEFAULT_HANDOFF_EVIDENCE_ID,
    real_replay_evidence_id: str = "E-P17B-REAL-REPLAY-INTAKE",
    rag_shadow_log_evidence_id: str = "E-P19C-RAG-SHADOW-LOG-INTAKE",
    portfolio: dict[str, object] | None = None,
) -> dict[str, object]:
    real_replay = replay_packet.build_real_replay_intake_packet(
        operator=operator,
        evidence_id=real_replay_evidence_id,
    )
    rag_shadow_log = rag_packet.build_rag_shadow_log_intake_packet(
        operator=operator,
        evidence_id=rag_shadow_log_evidence_id,
    )
    portfolio_report = portfolio
    if portfolio_report is None:
        portfolio_report = portfolio_packet.build_portfolio_evidence_packet()

    stage_readiness = dict_value(portfolio_report, "stage_readiness")
    assertions = build_assertions(
        operator=operator,
        handoff_evidence_id=handoff_evidence_id,
        real_replay=real_replay,
        rag_shadow_log=rag_shadow_log,
        portfolio_report=portfolio_report,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    missing_actions = list(portfolio_report.get("missing_actions", []))
    pre_submission_checklist_summary = build_pre_submission_checklist_summary(
        real_replay=real_replay,
        rag_shadow_log=rag_shadow_log,
    )
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "trace_id": TRACE_ID,
        "app_version": APP_VERSION,
        "failed": failed,
        "operator": operator,
        "handoff_evidence_id": handoff_evidence_id,
        "external_evidence_complete": portfolio_report.get(
            "external_evidence_complete", False
        ),
        "portfolio_complete": portfolio_report.get("portfolio_complete", False),
        "assertions": assertions,
        "missing_actions": missing_actions,
        "action_groups": build_action_groups(missing_actions),
        "action_group_details": build_action_group_details(missing_actions),
        "required_external_inputs": build_required_external_inputs(stage_readiness),
        "pre_submission_checklist_summary": pre_submission_checklist_summary,
        "readiness_truth": build_readiness_truth(
            real_replay=real_replay,
            rag_shadow_log=rag_shadow_log,
            portfolio_report=portfolio_report,
            stage_readiness=stage_readiness,
        ),
        "handoff_packets": {
            "real_replay": summarize_real_replay_packet(real_replay),
            "rag_shadow_log": summarize_rag_shadow_log_packet(rag_shadow_log),
        },
        "handoff_sequence": build_handoff_sequence(
            real_replay=real_replay,
            rag_shadow_log=rag_shadow_log,
            portfolio_report=portfolio_report,
        ),
        "boundaries": build_boundaries(),
        "next_gate": (
            "python scripts\\build_langchain_portfolio_evidence_packet.py "
            "--require-complete --summary"
        ),
    }


def build_assertions(
    *,
    operator: str,
    handoff_evidence_id: str,
    real_replay: dict[str, object],
    rag_shadow_log: dict[str, object],
    portfolio_report: dict[str, object],
) -> dict[str, bool]:
    return {
        "operator.present": bool(operator.strip()),
        "handoff_evidence_id.present": bool(handoff_evidence_id.strip()),
        "real_replay_intake_packet.passed": real_replay.get("status") == "passed",
        "rag_shadow_log_intake_packet.passed": rag_shadow_log.get("status") == "passed",
        "portfolio_report_available": isinstance(
            portfolio_report.get("stage_readiness"), dict
        ),
        "external_missing_actions_visible": bool(
            portfolio_report.get("external_evidence_complete") is True
            or portfolio_report.get("missing_actions")
        ),
    }


def build_required_external_inputs(
    stage_readiness: dict[str, object],
) -> list[dict[str, object]]:
    external_inputs: list[dict[str, object]] = []
    for stage_name, stage in stage_readiness.items():
        stage_payload = dict_value_from_object(stage)
        if stage_payload.get("ready") is True:
            continue
        external_inputs.append(
            {
                "stage": stage_name,
                "ready": False,
                "action": stage_payload.get("action", ""),
                "human_input_required": True,
            }
        )
    return external_inputs


def build_action_groups(missing_actions: list[object]) -> dict[str, list[str]]:
    details = build_action_group_details(missing_actions)
    return {
        "local_evidence_refresh_actions": details["local_evidence_refresh"]["actions"],
        "external_handoff_actions": details["external_handoff"]["actions"],
    }


def build_action_group_details(
    missing_actions: list[object],
) -> dict[str, dict[str, object]]:
    local_refresh_actions: list[str] = []
    external_handoff_actions: list[str] = []
    for action in missing_actions:
        action_name = str(action)
        if action_name in LOCAL_EVIDENCE_ACTIONS:
            local_refresh_actions.append(action_name)
        else:
            external_handoff_actions.append(action_name)
    return {
        "local_evidence_refresh": {
            "owner": "repo_maintainer",
            "human_input_required": False,
            "actions": local_refresh_actions,
        },
        "external_handoff": {
            "owner": "external_record_holder_or_compliance_reviewer",
            "human_input_required": True,
            "actions": external_handoff_actions,
        },
    }


def build_pre_submission_checklist_summary(
    *,
    real_replay: dict[str, object],
    rag_shadow_log: dict[str, object],
) -> dict[str, object]:
    sources = [
        build_pre_submission_source_summary(
            "real_replay",
            list_value(real_replay, "pre_submission_checklist"),
        ),
        build_pre_submission_source_summary(
            "rag_shadow_log",
            list_value(rag_shadow_log, "pre_submission_checklist"),
        ),
    ]
    owners: list[str] = []
    human_input_required_items = 0
    for source in sources:
        for owner in list_value(source, "owners"):
            owner_name = str(owner)
            if owner_name not in owners:
                owners.append(owner_name)
        human_input_required_items += sum(
            1
            for item in list_value(source, "items")
            if isinstance(item, dict) and item.get("human_input_required") is True
        )
    total_items = sum(int(source["item_count"]) for source in sources)
    return {
        "total_items": total_items,
        "human_input_required_items": human_input_required_items,
        "automation_safe_items": total_items - human_input_required_items,
        "owners": owners,
        "sources": sources,
    }


def build_pre_submission_source_summary(
    source: str,
    checklist: list[object],
) -> dict[str, object]:
    items = [item for item in checklist if isinstance(item, dict)]
    owners: list[str] = []
    item_ids: list[str] = []
    for item in items:
        item_id = str(item.get("id", ""))
        if item_id:
            item_ids.append(item_id)
        owner = str(item.get("owner", ""))
        if owner and owner not in owners:
            owners.append(owner)
    return {
        "source": source,
        "item_count": len(items),
        "owners": owners,
        "item_ids": item_ids,
        "items": items,
    }


def build_readiness_truth(
    *,
    real_replay: dict[str, object],
    rag_shadow_log: dict[str, object],
    portfolio_report: dict[str, object],
    stage_readiness: dict[str, object],
) -> dict[str, object]:
    replay_readiness = dict_value(real_replay, "readiness")
    rag_readiness = dict_value(rag_shadow_log, "readiness")
    readiness_flags = {
        "candidate_ready": replay_readiness.get("candidate_ready") is True,
        "real_sample_ready": replay_readiness.get("real_sample_ready") is True,
        "shadow_log_ready": rag_readiness.get("shadow_log_ready") is True,
        "external_evidence_complete": portfolio_report.get("external_evidence_complete")
        is True,
        "portfolio_complete": portfolio_report.get("portfolio_complete") is True,
    }
    stage_snapshot = build_stage_readiness_snapshot(stage_readiness)
    return {
        **readiness_flags,
        "stage_readiness": stage_snapshot,
        "false_readiness_reasons": build_false_readiness_reasons(
            readiness_flags=readiness_flags,
            stage_snapshot=stage_snapshot,
        ),
        "readiness_changed": False,
    }


def build_stage_readiness_snapshot(
    stage_readiness: dict[str, object],
) -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for stage_name, stage in stage_readiness.items():
        stage_payload = dict_value_from_object(stage)
        snapshot[stage_name] = {
            "ready": stage_payload.get("ready") is True,
            "action": stage_payload.get("action", ""),
        }
    return snapshot


def build_false_readiness_reasons(
    *,
    readiness_flags: dict[str, bool],
    stage_snapshot: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    false_reasons: list[dict[str, object]] = []
    for name, is_ready in readiness_flags.items():
        if not is_ready:
            false_reasons.append(
                {
                    "name": name,
                    "ready": False,
                    "reason": "required_external_evidence_not_verified",
                }
            )
    for stage_name, stage in stage_snapshot.items():
        if stage.get("ready") is not True:
            false_reasons.append(
                {
                    "name": stage_name,
                    "ready": False,
                    "action": stage.get("action", ""),
                }
            )
    return false_reasons


def summarize_real_replay_packet(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "target_count": report.get("target_count", 0),
        "required_scenarios": report.get("required_scenarios", []),
        "handoff_template": report.get("handoff_template", {}),
        "pre_submission_checklist": report.get("pre_submission_checklist", []),
        "commands": report.get("commands", []),
        "boundaries": report.get("boundaries", {}),
        "next_gate": report.get("next_gate", ""),
        "readiness": {
            "candidate_ready": False,
            "real_sample_ready": False,
            "reason": "external_redacted_real_replay_input_not_provided_by_handoff",
        },
    }


def summarize_rag_shadow_log_packet(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "recommended_record_count": report.get("recommended_record_count", 0),
        "required_metadata_fields": report.get("required_metadata_fields", []),
        "required_record_fields": report.get("required_record_fields", []),
        "handoff_template": report.get("handoff_template", {}),
        "pre_submission_checklist": report.get("pre_submission_checklist", []),
        "commands": report.get("commands", []),
        "boundaries": report.get("boundaries", {}),
        "readiness": report.get("readiness", {}),
    }


def build_handoff_sequence(
    *,
    real_replay: dict[str, object],
    rag_shadow_log: dict[str, object],
    portfolio_report: dict[str, object],
) -> list[dict[str, object]]:
    return [
        {
            "step": "collect_real_replay_input_outside_repo",
            "source": "real_replay",
            "commands": real_replay.get("commands", []),
        },
        {
            "step": "collect_rag_shadow_log_input_outside_repo",
            "source": "rag_shadow_log",
            "commands": rag_shadow_log.get("commands", []),
        },
        {
            "step": "refresh_portfolio_completion_gate",
            "source": "portfolio",
            "commands": [
                {
                    "step": "verify_complete_portfolio_gate",
                    "command": (
                        "python scripts\\build_langchain_portfolio_evidence_packet.py "
                        "--require-complete --summary"
                    ),
                    "human_input_required": False,
                }
            ],
            "missing_actions": portfolio_report.get("missing_actions", []),
        },
    ]


def build_boundaries() -> dict[str, bool]:
    return {
        "raw_customer_conversation_read": False,
        "raw_rag_shadow_log_read": False,
        "real_customer_data_committed": False,
        "business_database_read": False,
        "business_database_written": False,
        "external_llm_called": False,
        "production_service_changed": False,
        "readiness_changed": False,
        "missing_external_evidence_treated_as_complete": False,
    }


def render_markdown_handoff(report: dict[str, object]) -> str:
    checklist_summary = dict_value(report, "pre_submission_checklist_summary")
    readiness_truth = dict_value(report, "readiness_truth")
    action_groups = dict_value(report, "action_groups")
    handoff_packets = dict_value(report, "handoff_packets")
    real_replay = dict_value(handoff_packets, "real_replay")
    rag_shadow_log = dict_value(handoff_packets, "rag_shadow_log")
    lines = [
        "# LangChain 外部证据交接包",
        "",
        f"- trace_id: `{report.get('trace_id', '')}`",
        f"- app_version: `{report.get('app_version', '')}`",
        f"- operator: `{report.get('operator', '')}`",
        f"- handoff_evidence_id: `{report.get('handoff_evidence_id', '')}`",
        f"- status: `{report.get('status', '')}`",
        "",
        "## 当前 readiness 真值",
        "",
        *_render_readiness_flags(readiness_truth),
        "",
        "## 待办动作分组",
        "",
        "### 本地维护动作",
        "",
        *_render_list_items(
            list_value(action_groups, "local_evidence_refresh_actions")
        ),
        "",
        "### 外部交接动作",
        "",
        *_render_list_items(list_value(action_groups, "external_handoff_actions")),
        "",
        "## 提交前自检摘要",
        "",
        f"- total_items: `{checklist_summary.get('total_items', 0)}`",
        "- human_input_required_items: "
        f"`{checklist_summary.get('human_input_required_items', 0)}`",
        "- automation_safe_items: "
        f"`{checklist_summary.get('automation_safe_items', 0)}`",
        "",
        "### 自检项",
        "",
        *_render_checklist_sources(list_value(checklist_summary, "sources")),
        "",
        "## 真实 replay 交接命令",
        "",
        *_render_commands(list_value(real_replay, "commands")),
        "",
        "## RAG shadow log 交接命令",
        "",
        *_render_commands(list_value(rag_shadow_log, "commands")),
        "",
        "## 边界声明",
        "",
        *_render_boundaries(dict_value(report, "boundaries")),
        "",
        "## 下一道门禁",
        "",
        f"```powershell\n{report.get('next_gate', '')}\n```",
        "",
    ]
    return "\n".join(lines)


def write_markdown_handoff(report: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_handoff(report), encoding="utf-8")


def _render_readiness_flags(readiness_truth: dict[str, object]) -> list[str]:
    flag_names = [
        "candidate_ready",
        "real_sample_ready",
        "shadow_log_ready",
        "external_evidence_complete",
        "portfolio_complete",
        "readiness_changed",
    ]
    return [
        f"- {name}: `{str(readiness_truth.get(name, False)).lower()}`"
        for name in flag_names
    ]


def _render_list_items(items: list[object]) -> list[str]:
    if not items:
        return ["- 无"]
    return [f"- `{item}`" for item in items]


def _render_checklist_sources(sources: list[object]) -> list[str]:
    lines: list[str] = []
    for source in sources:
        source_payload = dict_value_from_object(source)
        lines.append(f"#### {source_payload.get('source', '')}")
        lines.append("")
        for item in list_value(source_payload, "items"):
            item_payload = dict_value_from_object(item)
            lines.append(
                "- "
                f"`{item_payload.get('id', '')}` "
                f"owner=`{item_payload.get('owner', '')}` "
                "human_input_required="
                f"`{str(item_payload.get('human_input_required', False)).lower()}`"
            )
        lines.append("")
    return lines


def _render_commands(commands: list[object]) -> list[str]:
    lines: list[str] = []
    for command in commands:
        command_payload = dict_value_from_object(command)
        lines.append(f"### {command_payload.get('step', '')}")
        lines.append("")
        lines.append("```powershell")
        lines.append(str(command_payload.get("command", "")))
        lines.append("```")
        lines.append("")
    return lines or ["- 无"]


def _render_boundaries(boundaries: dict[str, object]) -> list[str]:
    return [f"- {key}: `{str(value).lower()}`" for key, value in boundaries.items()]


def dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def list_value(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def dict_value_from_object(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 LangChain 外部证据交接汇总包")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out", type=Path, default=DEFAULT_OUTPUT_PATH, help="交接汇总包路径"
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="额外写出可发给外部记录持有人的 Markdown 交接包",
    )
    parser.add_argument("--operator", default="manual_reviewer", help="交接审核人")
    parser.add_argument(
        "--handoff-evidence-id",
        default=DEFAULT_HANDOFF_EVIDENCE_ID,
        help="交接汇总证据 ID",
    )
    parser.add_argument(
        "--real-replay-evidence-id",
        default="E-P17B-REAL-REPLAY-INTAKE",
        help="真实 replay 接入证据 ID",
    )
    parser.add_argument(
        "--rag-shadow-log-evidence-id",
        default="E-P19C-RAG-SHADOW-LOG-INTAKE",
        help="真实 RAG shadow log 接入证据 ID",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_external_evidence_handoff_packet(
        operator=args.operator,
        handoff_evidence_id=args.handoff_evidence_id,
        real_replay_evidence_id=args.real_replay_evidence_id,
        rag_shadow_log_evidence_id=args.rag_shadow_log_evidence_id,
    )
    write_json_report(report, args.json_out)
    if args.markdown_out:
        write_markdown_handoff(report, args.markdown_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_summary(report: dict[str, object]) -> None:
    action_groups = dict_value(report, "action_groups")
    local_actions = list_value(action_groups, "local_evidence_refresh_actions")
    external_actions = list_value(action_groups, "external_handoff_actions")
    checklist_summary = dict_value(report, "pre_submission_checklist_summary")
    print(
        "langchain_external_evidence_handoff "
        f"status={report['status']} failed={report['failed']} "
        f"external_evidence_complete="
        f"{str(report['external_evidence_complete']).lower()} "
        f"portfolio_complete={str(report['portfolio_complete']).lower()} "
        f"local_refresh_actions={len(local_actions)} "
        f"external_handoff_actions={len(external_actions)} "
        f"precheck_items={checklist_summary.get('total_items', 0)}"
    )


def print_text_report(report: dict[str, object]) -> None:
    print_summary(report)
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


if __name__ == "__main__":
    raise SystemExit(main())
