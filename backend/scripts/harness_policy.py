"""Harness 策略即代码的读取、哈希和裁决工具。"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "harness-policy.json"
)
POLICY_HASH_LENGTH = 64


class PolicyError(ValueError):
    """策略文件不符合约定。"""


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    """读取并校验策略 JSON。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise PolicyError(f"策略文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"策略文件不是合法 JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PolicyError("策略根节点必须是对象")
    required = (
        "schema_version",
        "policy_id",
        "forbidden_path_patterns",
        "operations",
        "network",
        "production",
        "data_handling",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise PolicyError(f"策略缺少字段: {', '.join(missing)}")
    if not isinstance(payload["forbidden_path_patterns"], list):
        raise PolicyError("forbidden_path_patterns 必须是数组")
    if not isinstance(payload["operations"], dict):
        raise PolicyError("operations 必须是对象")
    return payload


def canonical_json(payload: dict[str, Any]) -> bytes:
    """生成不受空格和键顺序影响的策略表示。"""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def policy_hash(policy: dict[str, Any]) -> str:
    """计算策略内容 SHA-256。"""
    return hashlib.sha256(canonical_json(policy)).hexdigest()


def policy_hash_from_file(path: Path = DEFAULT_POLICY_PATH) -> str:
    return policy_hash(load_policy(path))


def _normalise_pattern(pattern: str) -> str:
    return pattern.replace("\\", "/").lstrip("./")


def normalise_repo_path(
    raw_path: str | os.PathLike[str], root_dir: Path = ROOT_DIR
) -> str:
    """把路径转换成仓库相对 POSIX 路径；仓库外路径保留绝对路径。"""
    raw = str(raw_path).strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    resolved_root = root_dir.resolve()
    try:
        return candidate.resolve().relative_to(resolved_root).as_posix()
    except ValueError:
        return candidate.resolve().as_posix()


def _matches(path: str, pattern: str) -> bool:
    normalised_path = _normalise_pattern(path)
    normalised_pattern = _normalise_pattern(pattern)
    if fnmatch.fnmatchcase(normalised_path, normalised_pattern):
        return True
    if fnmatch.fnmatchcase(normalised_path, normalised_pattern.rstrip("/") + "/**"):
        return True
    if "/" not in normalised_pattern and fnmatch.fnmatchcase(
        Path(normalised_path).name, normalised_pattern
    ):
        return True
    return False


def path_matches(
    path: str,
    patterns: list[str] | tuple[str, ...],
    exceptions: list[str] | tuple[str, ...] = (),
) -> bool:
    """判断路径是否命中模式，并优先应用例外。"""
    if any(_matches(path, exception) for exception in exceptions):
        return False
    return any(_matches(path, pattern) for pattern in patterns)


def forbidden_path_patterns(policy: dict[str, Any]) -> tuple[str, ...]:
    raw = policy.get("forbidden_path_patterns", [])
    return tuple(str(item) for item in raw if str(item).strip())


def forbidden_path_exceptions(policy: dict[str, Any]) -> tuple[str, ...]:
    raw = policy.get("forbidden_path_exceptions", [])
    return tuple(str(item) for item in raw if str(item).strip())


def check_paths(
    paths: list[str] | tuple[str, ...],
    policy: dict[str, Any],
    allowed_patterns: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """检查敏感路径和可选的任务级允许路径。"""
    issues: list[str] = []
    forbidden = forbidden_path_patterns(policy)
    exceptions = forbidden_path_exceptions(policy)
    allowed = tuple(allowed_patterns or ())
    for raw_path in paths:
        path = _normalise_pattern(str(raw_path))
        if not path:
            continue
        if path_matches(path, forbidden, exceptions):
            issues.append(f"路径命中禁止策略: {path}")
        if allowed and not path_matches(path, allowed):
            issues.append(f"路径超出任务允许范围: {path}")
    return issues


def operation_config(policy: dict[str, Any], operation: str) -> dict[str, Any]:
    operations = policy.get("operations", {})
    config = operations.get(operation)
    if not isinstance(config, dict):
        raise PolicyError(f"未定义的高风险操作: {operation}")
    return config


def check_operation(
    operation: str | None,
    policy: dict[str, Any],
    *,
    human_approved: bool = False,
) -> list[str]:
    """按策略裁决一次高风险操作。"""
    if not operation:
        return []
    try:
        config = operation_config(policy, operation)
    except PolicyError as exc:
        return [str(exc)]
    issues: list[str] = []
    title = str(config.get("human_title") or operation)
    if config.get("enabled") is not True:
        issues.append(f"高风险操作默认未启用: {title}")
    if config.get("requires_human_approval") is True and not human_approved:
        issues.append(f"高风险操作缺少人工批准: {title}")
    return issues


def build_policy_snapshot(path: Path = DEFAULT_POLICY_PATH) -> dict[str, str]:
    policy = load_policy(path)
    return {
        "policy_id": str(policy["policy_id"]),
        "schema_version": str(policy["schema_version"]),
        "sha256": policy_hash(policy),
    }
