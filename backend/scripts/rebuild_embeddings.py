"""显式重建知识库向量索引缓存。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import db_session_scope  # noqa: E402
from app.readiness import embedding_index_files_exist  # noqa: E402
from app.repository.knowledge_repo import KnowledgeRepo  # noqa: E402
from app.service.embedding_search import EmbeddingSearcher  # noqa: E402
from scripts.preflight_production import (  # noqa: E402
    get_missing_database_columns,
    get_missing_database_tables,
    resolve_project_path,
)

MIGRATION_REQUIRED_ACTION = (
    "run scripts/preflight_production.py or scripts/apply_migrations.py dry-run first; "
    "confirm target database path, then rerun migrations with --apply"
)


@dataclass(frozen=True)
class EmbeddingRebuildReport:
    database_path: Path
    index_path: Path
    applied: bool
    schema_ready: bool
    active_docs: int
    files_ready_before: bool
    files_ready_after: bool


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Platform embeddings")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--index-path",
        default=settings.EMBEDDING_INDEX_DIR,
        help="向量索引基路径，默认读取 EMBEDDING_INDEX_DIR。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际重建并写入 .npy/.json；不加该参数时只做 dry-run。",
    )
    return parser.parse_args(argv)


def build_data_hash(docs: list[tuple[str, str, str]]) -> str:
    sorted_docs = sorted(docs, key=lambda item: item[0])
    concat_text = "".join(f"{title}{content}" for _, title, content in sorted_docs)
    return hashlib.md5(concat_text.encode("utf-8")).hexdigest()


async def load_active_docs(db_path: Path) -> list[tuple[str, str, str]]:
    async with db_session_scope(str(db_path)):
        return await KnowledgeRepo(None).get_all_titles_with_keys()


async def rebuild_embeddings(
    db_path_value: str,
    index_path_value: str,
    *,
    should_apply: bool,
) -> EmbeddingRebuildReport:
    database_path = resolve_project_path(db_path_value)
    index_path = resolve_project_path(index_path_value)
    files_ready_before = embedding_index_files_exist(index_path)
    schema_ready = (
        database_path.exists()
        and "knowledge_base" not in get_missing_database_tables(database_path)
        and not get_missing_database_columns(database_path)
    )
    docs = await load_active_docs(database_path) if schema_ready else []
    files_ready_after = files_ready_before

    if should_apply and docs:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        searcher = EmbeddingSearcher()
        await asyncio.to_thread(searcher.build, docs, build_data_hash(docs))
        await searcher.save(index_path)
        files_ready_after = embedding_index_files_exist(index_path)

    return EmbeddingRebuildReport(
        database_path=database_path,
        index_path=index_path,
        applied=should_apply,
        schema_ready=schema_ready,
        active_docs=len(docs),
        files_ready_before=files_ready_before,
        files_ready_after=files_ready_after,
    )


def print_report(report: EmbeddingRebuildReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Platform embedding rebuild")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"index_path={report.index_path}")
    print(
        f"expected_files={report.index_path.with_suffix('.npy')}, {report.index_path.with_suffix('.json')}"
    )
    print(f"schema_ready={report.schema_ready}")
    print(f"active_docs={report.active_docs}")
    print(f"files_ready_before={report.files_ready_before}")
    print(f"files_ready_after={report.files_ready_after}")
    if report.files_ready_after and report.applied:
        print("action=embedding cache ready")
    elif report.files_ready_after:
        print("action=embedding cache already ready")
    elif not report.schema_ready:
        print(f"action={MIGRATION_REQUIRED_ACTION}")
    elif report.active_docs == 0:
        print("action=import knowledge rows before rebuilding embeddings")
    elif not report.applied:
        print(
            "action=review dry-run output, confirm database and index paths, then rerun with --apply"
        )
    else:
        print("action=inspect embedding rebuild errors")


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = await rebuild_embeddings(
        args.db_path,
        args.index_path,
        should_apply=args.apply,
    )
    print_report(report)
    return 0 if report.files_ready_after else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
