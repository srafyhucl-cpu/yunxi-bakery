"""生成 Harness CI 证据包的 artifact 索引。

索引列出报告目录内全部证据文件（含 SHA-256 哈希），并校验必需文件集合；
缺少必需文件时仍输出索引报告，但 status=failed，最终由 CI 汇总显式失败。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

try:
    from harness_run_manifest import resolve_commit
except ModuleNotFoundError:
    from scripts.harness_run_manifest import resolve_commit  # type: ignore[no-redef]

ROOT_DIR = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "1.0"
ARTIFACT_INDEX_TYPE = "harness_artifact_index"

# P1/P2 质量循环的必需证据集合；artifact-index 自身由索引生成时计入。
DEFAULT_REQUIRED_PATTERNS = (
    "harness-eval-*.json",
    "harness-observation-*.json",
    "doc-garden-*.json",
    "ci-quality-loop*.run.json",
    "artifact-index*.json",
    "failure-candidates/*.json",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    """对实际文件计算 SHA-256，与 manifest 哈希模式保持一致。"""
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_pattern(pattern: str, report_dir: Path) -> None:
    """拒绝绝对路径和目录穿越，所有匹配必须限制在 report_dir 内。"""
    if not pattern.strip():
        raise ValueError("必需文件模式不能为空")
    candidate = Path(pattern)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"必需文件模式越界，必须位于报告目录内: {pattern}")
    del report_dir


def _ensure_within_report_dir(report_dir: Path, file_path: Path) -> None:
    resolved_base = report_dir.resolve()
    resolved_file = file_path.resolve()
    if resolved_file != resolved_base and resolved_base not in resolved_file.parents:
        raise ValueError(f"证据文件越界，拒绝收录: {file_path}")


def _build_file_entry(
    report_dir: Path,
    file_path: Path,
    *,
    index_filename: str | None,
) -> dict[str, Any]:
    relative = file_path.relative_to(report_dir).as_posix()
    if index_filename is not None and relative == index_filename:
        # 索引文件自身无法在写出前计算哈希（自引用），以存在性标记计入。
        return {
            "path": relative,
            "size_bytes": 0,
            "sha256": "",
            "exists": True,
            "self_reference": True,
        }
    return {
        "path": relative,
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
        "exists": True,
    }


def build_artifact_index(
    report_dir: Path,
    *,
    run_id: str,
    required_patterns: tuple[str, ...],
    index_filename: str | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """扫描报告目录并生成带哈希的索引；缺少必需文件时 status=failed。"""
    if not run_id.strip():
        raise ValueError("run_id 不能为空")
    for pattern in required_patterns:
        _validate_pattern(pattern, report_dir)
    if not report_dir.is_dir():
        raise ValueError(f"报告目录不存在或不是目录: {report_dir}")

    files: list[dict[str, Any]] = []
    for file_path in sorted(report_dir.rglob("*")):
        if not file_path.is_file():
            continue
        _ensure_within_report_dir(report_dir, file_path)
        files.append(
            _build_file_entry(report_dir, file_path, index_filename=index_filename)
        )

    # 索引文件在写出前不存在，需主动补入自引用条目以满足 artifact-index* 模式。
    if index_filename is not None and not any(
        entry["path"] == index_filename for entry in files
    ):
        files.append(
            {
                "path": index_filename,
                "size_bytes": 0,
                "sha256": "",
                "exists": True,
                "self_reference": True,
            }
        )

    required_files = list(required_patterns)
    missing_files: list[str] = []
    for pattern in required_patterns:
        matched = any(fnmatch.fnmatch(entry["path"], pattern) for entry in files)
        if not matched and index_filename is not None:
            matched = fnmatch.fnmatch(index_filename, pattern)
        if not matched:
            missing_files.append(pattern)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_index_type": ARTIFACT_INDEX_TYPE,
        "generated_at": utc_now(),
        "run_id": run_id,
        "commit_sha": commit_sha
        if commit_sha is not None
        else resolve_commit(ROOT_DIR),
        "files": files,
        "required_files": required_files,
        "missing_files": missing_files,
        "status": "passed" if not missing_files else "failed",
    }


def write_artifact_index(path: Path, payload: dict[str, Any]) -> None:
    """写出索引报告；已存在路径拒绝覆盖，保护旧证据。"""
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有 artifact 索引: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 Harness CI artifact 索引")
    parser.add_argument(
        "--report-dir", type=Path, default=ROOT_DIR / "backend" / "reports" / "harness"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--required",
        action="append",
        default=[],
        help="追加必需文件模式（可多次）；缺省使用 P1/P2 完整证据集合",
    )
    parser.add_argument(
        "--index-name", help="索引文件自身文件名，用于满足 artifact-index* 模式"
    )
    parser.add_argument("--commit-sha", help="显式指定 commit SHA，缺省从 Git 解析")
    parser.add_argument("--output", type=Path, help="索引 JSON 输出路径")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = build_artifact_index(
            args.report_dir,
            run_id=args.run_id,
            required_patterns=tuple(args.required)
            if args.required
            else DEFAULT_REQUIRED_PATTERNS,
            index_filename=args.index_name,
            commit_sha=args.commit_sha,
        )
        if args.output is not None:
            write_artifact_index(args.output, payload)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"[artifact-index] FAIL {exc}", file=sys.stderr)
        return 1
    if args.summary:
        print(
            f"artifact_index status={payload['status']} "
            f"files={len(payload['files'])} "
            f"missing={len(payload['missing_files'])} "
            f"run_id={payload['run_id']}"
        )
    elif payload["status"] == "failed":
        print("[artifact-index] FAIL 缺少必需证据文件")
        for pattern in payload["missing_files"]:
            print(f"  - {pattern}")
    else:
        print(f"[artifact-index] PASS files={len(payload['files'])}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
