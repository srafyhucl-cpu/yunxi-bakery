"""构建包含精确 commit、版本和文件 SHA256 的发布 manifest。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def resolve_commit(root_dir: Path, explicit_commit: str = "") -> str:
    candidate = explicit_commit.strip() or os.environ.get("GITHUB_SHA", "").strip()
    if not candidate:
        completed = subprocess.run(
            ["git", "-C", str(root_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        candidate = completed.stdout.strip()
    if not SHA_PATTERN.fullmatch(candidate):
        raise ValueError("发布 commit 必须是 40 位完整 SHA")
    return candidate


def collect_tracked_files(root_dir: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(root_dir), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    relative_paths = [item for item in completed.stdout.decode().split("\0") if item]
    return [root_dir / relative_path for relative_path in relative_paths]


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release_manifest(
    root_dir: Path,
    *,
    commit: str,
    files: list[Path] | None = None,
) -> dict[str, object]:
    resolved_root = root_dir.resolve()
    resolved_commit = resolve_commit(resolved_root, commit)
    version_path = resolved_root / "VERSION"
    if not version_path.is_file():
        raise FileNotFoundError(f"VERSION 不存在: {version_path}")
    tracked_files = files if files is not None else collect_tracked_files(resolved_root)
    entries: list[dict[str, str]] = []
    for file_path in sorted(tracked_files):
        resolved_path = file_path.resolve()
        if not resolved_path.is_file() or resolved_root not in resolved_path.parents:
            raise ValueError(f"manifest 文件路径无效: {file_path}")
        entries.append(
            {
                "path": resolved_path.relative_to(resolved_root).as_posix(),
                "sha256": sha256_file(resolved_path),
            }
        )
    return {
        "manifest_version": 1,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "commit": resolved_commit,
        "version": version_path.read_text(encoding="utf-8").strip(),
        "files": entries,
    }


def write_manifest(output_path: Path, payload: dict[str, object]) -> None:
    if output_path.exists():
        raise FileExistsError(f"拒绝覆盖已有 manifest: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建精确发布 manifest")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", default="", help="40 位完整 commit SHA")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = build_release_manifest(ROOT_DIR, commit=args.commit)
        write_manifest(args.output, payload)
    except (
        FileExistsError,
        FileNotFoundError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.summary:
        print(
            f"release_manifest status=passed commit={payload['commit']} "
            f"version={payload['version']} files={len(payload['files'])}"
        )
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
