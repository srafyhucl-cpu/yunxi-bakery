"""生成和校验 Harness 运行 manifest 与最小 episode。"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from harness_policy import (
        DEFAULT_POLICY_PATH,
        build_policy_snapshot,
        policy_hash,
    )
except ModuleNotFoundError:
    from scripts.harness_policy import (  # type: ignore[no-redef]
        DEFAULT_POLICY_PATH,
        build_policy_snapshot,
        policy_hash,
    )

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
SCHEMA_PATH = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "run-manifest.schema.json"
)
SCHEMA_VERSION = "1.0"
MANIFEST_TYPE = "harness_run"
STATUS_LABELS = {
    "active": "进行中（active）",
    "completed": "已完成（completed）",
    "blocked": "已阻塞（blocked）",
    "failed": "失败（failed）",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
TASK_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
RFC3339_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def resolve_commit(root_dir: Path = ROOT_DIR) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or not COMMIT_RE.fullmatch(commit):
        raise ValueError(
            f"无法解析当前完整 commit: {commit or completed.stderr.strip()}"
        )
    return commit


def read_version(root_dir: Path = ROOT_DIR) -> str:
    version_path = root_dir / "backend" / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise ValueError(f"无法读取版本文件: {version_path}: {exc}") from exc
    if not version:
        raise ValueError(f"版本文件为空: {version_path}")
    return version


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hash(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.is_file():
        raise ValueError(f"工件路径不存在或不是文件: {path}")
    return sha256_file(path)


def _normalise_items(
    items: list[str | dict[str, Any]] | tuple[str | dict[str, Any], ...] | None,
) -> list[str | dict[str, Any]]:
    result: list[str | dict[str, Any]] = []
    for item in items or ():
        if isinstance(item, str):
            value = item.strip()
            if value:
                result.append(value)
        elif isinstance(item, dict):
            result.append(dict(item))
        else:
            raise ValueError("verification/evidence 只允许字符串或对象")
    return result


def _normalise_paths(paths: list[str] | tuple[str, ...] | None) -> list[str]:
    return [
        str(item).replace("\\", "/").strip()
        for item in paths or ()
        if str(item).strip()
    ]


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:12]}"


def build_manifest(
    *,
    task_id: str,
    trace_id: str,
    goal: str,
    source: str = "用户请求",
    status: str = "active",
    model_id: str = "unknown",
    run_id: str | None = None,
    parent_run_id: str | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
    operation: str | None = None,
    allowed_paths: list[str] | tuple[str, ...] | None = None,
    forbidden_paths: list[str] | tuple[str, ...] | None = None,
    changed_files: list[str] | tuple[str, ...] | None = None,
    verification: list[str | dict[str, Any]]
    | tuple[str | dict[str, Any], ...]
    | None = None,
    evidence: list[str | dict[str, Any]]
    | tuple[str | dict[str, Any], ...]
    | None = None,
    failure_class: str | None = "none",
    latency_ms: int | None = None,
    cost: str | float | int | None = "unknown",
    human_intervention: bool = False,
    human_intervention_count: int | None = None,
    replayable: bool = False,
    result_correct: bool | None = None,
    policy_compliant: bool | None = None,
    evidence_complete: bool | None = None,
    input_artifact: Path | None = None,
    output_artifact: Path | None = None,
    input_artifact_hash: str | None = None,
    output_artifact_hash: str | None = None,
    plan_summary: str = "",
    tool_call_count: int = 0,
    tool_calls: list[dict[str, Any]] | None = None,
    verification_commands: list[str] | None = None,
    recovery_point: str = "",
    events: list[dict[str, Any]] | None = None,
    decision_refs: list[str] | None = None,
    residual_risks: list[str] | None = None,
    root_dir: Path = ROOT_DIR,
) -> dict[str, Any]:
    """构建一次不可覆盖的运行记录。"""
    if not TASK_ID_RE.fullmatch(task_id):
        raise ValueError(f"task_id 格式无效: {task_id}")
    if not ID_RE.fullmatch(trace_id):
        raise ValueError(f"trace_id 格式无效: {trace_id}")
    resolved_run_id = run_id or new_run_id()
    if not ID_RE.fullmatch(resolved_run_id):
        raise ValueError(f"run_id 格式无效: {resolved_run_id}")
    if parent_run_id and parent_run_id == resolved_run_id:
        raise ValueError("parent_run_id 不能等于 run_id")
    if status not in STATUS_LABELS:
        raise ValueError(f"运行 status 无效: {status}")
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms 不能为负数")
    if tool_call_count < 0:
        raise ValueError("tool_call_count 不能为负数")
    if human_intervention_count is None:
        human_intervention_count = 1 if human_intervention else 0
    if human_intervention_count < 0:
        raise ValueError("human_intervention_count 不能为负数")

    snapshot = build_policy_snapshot(policy_path)
    expected_policy_hash = snapshot["sha256"]
    if policy_hash(load_policy_for_hash(policy_path)) != expected_policy_hash:
        raise ValueError("策略哈希计算不稳定")
    if input_artifact_hash is None:
        input_artifact_hash = _artifact_hash(input_artifact)
    if output_artifact_hash is None:
        output_artifact_hash = _artifact_hash(output_artifact)
    for label, value in (
        ("input_artifact_hash", input_artifact_hash),
        ("output_artifact_hash", output_artifact_hash),
    ):
        if value is not None and not SHA256_RE.fullmatch(value):
            raise ValueError(f"{label} 必须是 64 位 SHA-256")

    assertions = {
        "result_correct": result_correct,
        "policy_compliant": policy_compliant,
        "evidence_complete": evidence_complete,
        "replayable": replayable,
    }
    if status == "completed" and any(
        value is not True for value in assertions.values()
    ):
        raise ValueError("完成态必须明确通过结果、策略、证据和回放四项断言")

    resolved_verification = _normalise_items(verification)
    resolved_evidence = _normalise_items(evidence)
    resolved_verification_commands = list(verification_commands or [])
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": MANIFEST_TYPE,
        "run_id": resolved_run_id,
        "parent_run_id": parent_run_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "source": source.strip(),
        "goal": goal.strip(),
        "status": status,
        "status_label": STATUS_LABELS[status],
        "generated_at": utc_now(),
        "as_of_commit": resolve_commit(root_dir),
        "version": read_version(root_dir),
        "model_id": model_id.strip() or "unknown",
        "tool_policy_hash": expected_policy_hash,
        "policy_snapshot": snapshot,
        "operation": operation,
        "allowed_paths": _normalise_paths(allowed_paths),
        "forbidden_paths": _normalise_paths(forbidden_paths),
        "changed_files": _normalise_paths(changed_files),
        "verification": resolved_verification,
        "evidence": resolved_evidence,
        "failure_class": failure_class,
        "latency_ms": latency_ms,
        "cost": cost,
        "human_intervention": human_intervention,
        "human_intervention_count": human_intervention_count,
        "replayable": replayable,
        "input_artifact_hash": input_artifact_hash,
        "output_artifact_hash": output_artifact_hash,
        "decision_refs": list(decision_refs or []),
        "residual_risks": list(residual_risks or []),
        "assertions": assertions,
        "episode": {
            "plan_summary": plan_summary,
            "tool_call_count": tool_call_count,
            "tool_calls": [dict(item) for item in tool_calls or []],
            "verification_commands": resolved_verification_commands,
            "recovery_point": recovery_point,
            "events": [dict(item) for item in events or []],
        },
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    issues = validate_manifest(manifest)
    if issues:
        raise ValueError("运行 manifest 校验失败: " + "；".join(issues))
    return manifest


def load_policy_for_hash(path: Path) -> dict[str, Any]:
    """延迟读取策略，避免循环导入。"""
    try:
        from harness_policy import load_policy
    except ModuleNotFoundError:
        from scripts.harness_policy import load_policy  # type: ignore[no-redef]
    return load_policy(path)


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_json_schema(
    value: Any, schema: dict[str, Any], path: str = "$"
) -> list[str]:
    """执行本项目 manifest schema 使用到的 JSON Schema 约束。"""
    issues: list[str] = []
    expected_type = schema.get("type")
    type_options = expected_type if isinstance(expected_type, list) else [expected_type]
    if expected_type is not None and not any(
        _json_type_matches(value, item)
        for item in type_options
        if isinstance(item, str)
    ):
        return [f"{path}: 类型不符合 schema.type={expected_type}"]
    if "const" in schema and value != schema["const"]:
        issues.append(f"{path}: 不符合 schema.const")
    if "enum" in schema and value not in schema["enum"]:
        issues.append(f"{path}: 不符合 schema.enum")
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            issues.append(f"{path}: 长度小于 schema.minLength={minimum}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            issues.append(f"{path}: 不符合 schema.pattern")
        if schema.get("format") == "date-time":
            if not RFC3339_DATETIME_RE.fullmatch(value):
                issues.append(f"{path}: 不符合 schema.format=date-time")
            else:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    issues.append(f"{path}: 不符合 schema.format=date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            issues.append(f"{path}: 小于 schema.minimum={minimum}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for field in required:
                if field not in value:
                    issues.append(f"{path}: 缺少 schema.required 字段 {field}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for field, child_schema in properties.items():
                if field in value and isinstance(child_schema, dict):
                    issues.extend(
                        _validate_json_schema(
                            value[field], child_schema, f"{path}.{field}"
                        )
                    )
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            issues.extend(
                _validate_json_schema(item, schema["items"], f"{path}[{index}]")
            )
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for candidate in one_of:
            if isinstance(candidate, dict) and not _validate_json_schema(
                value, candidate, path
            ):
                matches += 1
        if matches != 1:
            issues.append(f"{path}: oneOf 匹配数量为 {matches}")
    return issues


def validate_manifest(
    manifest: dict[str, Any],
    *,
    schema_path: Path = SCHEMA_PATH,
) -> list[str]:
    """执行不依赖第三方库的关键 schema 和业务约束校验。"""
    issues: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest 根节点必须是对象"]
    required = (
        "schema_version",
        "manifest_type",
        "run_id",
        "trace_id",
        "task_id",
        "source",
        "goal",
        "status",
        "status_label",
        "generated_at",
        "as_of_commit",
        "version",
        "model_id",
        "tool_policy_hash",
        "policy_snapshot",
        "allowed_paths",
        "forbidden_paths",
        "changed_files",
        "verification",
        "evidence",
        "failure_class",
        "latency_ms",
        "cost",
        "human_intervention",
        "human_intervention_count",
        "replayable",
        "input_artifact_hash",
        "output_artifact_hash",
        "assertions",
        "episode",
        "environment",
    )
    issues.extend(f"缺少字段 {key}" for key in required if key not in manifest)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append("schema_version 必须为 1.0")
    if manifest.get("manifest_type") != MANIFEST_TYPE:
        issues.append("manifest_type 必须为 harness_run")
    run_id = manifest.get("run_id")
    trace_id = manifest.get("trace_id")
    task_id = manifest.get("task_id")
    if not isinstance(run_id, str) or not ID_RE.fullmatch(run_id):
        issues.append("run_id 格式无效")
    if not isinstance(trace_id, str) or not ID_RE.fullmatch(trace_id):
        issues.append("trace_id 格式无效")
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        issues.append("task_id 格式无效")
    status = manifest.get("status")
    if status not in STATUS_LABELS:
        issues.append("status 必须是 active/completed/blocked/failed")
    elif manifest.get("status_label") != STATUS_LABELS[status]:
        issues.append("status_label 与 status 不一致")
    commit = manifest.get("as_of_commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        issues.append("as_of_commit 必须是 40 位小写 SHA")
    policy_hash_value = manifest.get("tool_policy_hash")
    if not isinstance(policy_hash_value, str) or not SHA256_RE.fullmatch(
        policy_hash_value
    ):
        issues.append("tool_policy_hash 必须是 64 位 SHA-256")
    snapshot = manifest.get("policy_snapshot")
    if not isinstance(snapshot, dict):
        issues.append("policy_snapshot 必须是对象")
    elif snapshot.get("sha256") != policy_hash_value:
        issues.append("policy_snapshot.sha256 与 tool_policy_hash 不一致")
    for field in (
        "allowed_paths",
        "forbidden_paths",
        "changed_files",
        "verification",
        "evidence",
    ):
        if not isinstance(manifest.get(field), list):
            issues.append(f"{field} 必须是数组")
    for field in ("human_intervention", "replayable"):
        if not isinstance(manifest.get(field), bool):
            issues.append(f"{field} 必须是布尔值")
    if (
        not isinstance(manifest.get("human_intervention_count"), int)
        or manifest.get("human_intervention_count", -1) < 0
    ):
        issues.append("human_intervention_count 必须是非负整数")
    latency = manifest.get("latency_ms")
    if latency is not None and (not isinstance(latency, int) or latency < 0):
        issues.append("latency_ms 必须是非负整数或 null")
    for field in ("input_artifact_hash", "output_artifact_hash"):
        value = manifest.get(field)
        if value is not None and (
            not isinstance(value, str) or not SHA256_RE.fullmatch(value)
        ):
            issues.append(f"{field} 必须是 64 位 SHA-256 或 null")
    assertions = manifest.get("assertions")
    if not isinstance(assertions, dict):
        issues.append("assertions 必须是对象")
    else:
        for field in (
            "result_correct",
            "policy_compliant",
            "evidence_complete",
        ):
            if assertions.get(field) not in (True, False, None):
                issues.append(f"assertions.{field} 必须是布尔值或 null")
        if assertions.get("replayable") is not manifest.get("replayable"):
            issues.append("assertions.replayable 必须与 replayable 一致")
        if status == "completed" and any(
            assertions.get(field) is not True
            for field in (
                "result_correct",
                "policy_compliant",
                "evidence_complete",
                "replayable",
            )
        ):
            issues.append("完成态四项断言必须全部为 true")
    episode = manifest.get("episode")
    if not isinstance(episode, dict):
        issues.append("episode 必须是对象")
    else:
        for field in (
            "plan_summary",
            "tool_call_count",
            "tool_calls",
            "verification_commands",
            "recovery_point",
            "events",
        ):
            if field not in episode:
                issues.append(f"episode 缺少字段 {field}")
        if (
            not isinstance(episode.get("tool_call_count"), int)
            or episode.get("tool_call_count", -1) < 0
        ):
            issues.append("episode.tool_call_count 必须是非负整数")
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        issues.append("environment 必须是对象")
    else:
        for field in ("python_version", "platform"):
            if not str(environment.get(field) or "").strip():
                issues.append(f"environment.{field} 不能为空")
    if not schema_path.is_file():
        issues.append(f"schema 文件不存在或不是文件: {schema_path}")
        return issues
    try:
        schema_payload = json.loads(schema_path.read_text(encoding="utf-8-sig"))
        if not isinstance(schema_payload, dict):
            issues.append("schema 根节点必须是对象")
        elif schema_payload.get("$id") is None:
            issues.append("schema 文件缺少 $id")
        else:
            issues.extend(_validate_json_schema(manifest, schema_payload))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"schema 文件不可读取: {exc}")
    return issues


def format_markdown(manifest: dict[str, Any]) -> str:
    """输出中文摘要，机器字段保持原样。"""
    lines = [
        "# Harness 运行摘要",
        "",
        f"- run_id: {manifest['run_id']}",
        f"- parent_run_id: {manifest.get('parent_run_id') or 'none'}",
        f"- trace_id: {manifest['trace_id']}",
        f"- task_id: {manifest['task_id']}",
        f"- status: {manifest['status_label']}",
        f"- goal: {manifest['goal']}",
        f"- as_of_commit: {manifest['as_of_commit']}",
        f"- version: {manifest['version']}",
        f"- model_id: {manifest['model_id']}",
        f"- tool_policy_hash: {manifest['tool_policy_hash']}",
        "",
        "## 四项断言",
        "",
    ]
    assertions = manifest["assertions"]
    for key, label in (
        ("result_correct", "结果正确"),
        ("policy_compliant", "策略合规"),
        ("evidence_complete", "证据完整"),
        ("replayable", "可回放"),
    ):
        value = assertions.get(key)
        lines.append(f"- {label}: {value}")
    lines.extend(
        [
            "",
            "## 验证与证据",
            "",
            "- verification:",
        ]
    )
    lines.extend(f"  - {item}" for item in manifest.get("verification", []) or ["none"])
    lines.append("- evidence:")
    lines.extend(f"  - {item}" for item in manifest.get("evidence", []) or ["none"])
    lines.extend(
        [
            "",
            "## Episode",
            "",
            f"- plan_summary: {manifest['episode']['plan_summary'] or 'none'}",
            f"- tool_call_count: {manifest['episode']['tool_call_count']}",
            f"- recovery_point: {manifest['episode']['recovery_point'] or 'none'}",
            "",
            "## 未验证与风险",
            "",
        ]
    )
    risks = manifest.get("residual_risks") or ["none"]
    lines.extend(f"- {risk}" for risk in risks)
    lines.append("")
    return "\n".join(lines)


def write_artifact(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有运行工件: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 manifest: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"manifest 根节点不是对象: {path}")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成或校验 Harness 运行 manifest")
    parser.add_argument("--validate", type=Path, help="校验已有 manifest")
    parser.add_argument("--output", type=Path, help="JSON manifest 输出路径")
    parser.add_argument("--markdown-output", type=Path, help="Markdown 摘要输出路径")
    parser.add_argument("--task-id")
    parser.add_argument("--trace-id")
    parser.add_argument("--parent-run-id")
    parser.add_argument("--run-id")
    parser.add_argument("--source", default="用户请求")
    parser.add_argument("--goal")
    parser.add_argument(
        "--status",
        choices=tuple(STATUS_LABELS),
        default="active",
    )
    parser.add_argument("--model-id", default="unknown")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--operation")
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--forbidden-path", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--verification", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--failure-class", default="none")
    parser.add_argument("--latency-ms", type=int)
    parser.add_argument("--cost", default="unknown")
    parser.add_argument("--human-intervention", action="store_true")
    parser.add_argument("--human-intervention-count", type=int)
    parser.add_argument("--replayable", action="store_true")
    parser.add_argument("--result-correct", action="store_true", default=None)
    parser.add_argument("--policy-compliant", action="store_true", default=None)
    parser.add_argument("--evidence-complete", action="store_true", default=None)
    parser.add_argument("--input-artifact", type=Path)
    parser.add_argument("--output-artifact", type=Path)
    parser.add_argument("--plan-summary", default="")
    parser.add_argument("--tool-call-count", type=int, default=0)
    parser.add_argument("--recovery-point", default="")
    parser.add_argument("--decision-ref", action="append", default=[])
    parser.add_argument("--residual-risk", action="append", default=[])
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.validate:
            manifest = _load_manifest(args.validate)
            issues = validate_manifest(manifest)
            report = {
                "status": "passed" if not issues else "failed",
                "manifest": str(args.validate),
                "run_id": manifest.get("run_id", ""),
                "issues": issues,
            }
        else:
            if not args.task_id or not args.trace_id or not args.goal:
                raise ValueError("生成 manifest 必须提供 --task-id、--trace-id、--goal")
            manifest = build_manifest(
                task_id=args.task_id,
                trace_id=args.trace_id,
                goal=args.goal,
                source=args.source,
                status=args.status,
                model_id=args.model_id,
                run_id=args.run_id,
                parent_run_id=args.parent_run_id,
                policy_path=args.policy,
                operation=args.operation,
                allowed_paths=args.allowed_path,
                forbidden_paths=args.forbidden_path,
                changed_files=args.changed_file,
                verification=args.verification,
                evidence=args.evidence,
                failure_class=args.failure_class,
                latency_ms=args.latency_ms,
                cost=args.cost,
                human_intervention=args.human_intervention,
                human_intervention_count=args.human_intervention_count,
                replayable=args.replayable,
                result_correct=args.result_correct,
                policy_compliant=args.policy_compliant,
                evidence_complete=args.evidence_complete,
                input_artifact=args.input_artifact,
                output_artifact=args.output_artifact,
                plan_summary=args.plan_summary,
                tool_call_count=args.tool_call_count,
                recovery_point=args.recovery_point,
                decision_refs=args.decision_ref,
                residual_risks=args.residual_risk,
            )
            issues = []
            report = {
                "status": "passed",
                "manifest": manifest,
                "issues": issues,
            }
            if args.output:
                write_artifact(
                    args.output,
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
            if args.markdown_output:
                write_artifact(args.markdown_output, format_markdown(manifest))
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"[Harness 运行契约] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "harness_run_manifest "
            f"status={report['status']} "
            f"run_id={report.get('run_id') or report.get('manifest', {}).get('run_id', '')} "
            f"failed={len(report['issues'])}"
        )
    elif report["status"] == "failed":
        print("[Harness 运行契约] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(
            "[Harness 运行契约] PASS "
            f"run_id={report.get('run_id') or report.get('manifest', {}).get('run_id', '')}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
