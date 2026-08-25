"""P0.5 资产迁移：旧库业务知识选择性迁入新库。

范围：仅 faq/policy/after_sales 三类目（24 条人工沉淀），禁触客户数据与商品快照。
幂等：按 (category, title) 查重，重跑安全。
默认 dry-run 只打印计划；--apply 才实际写入。
"""

from __future__ import annotations

import argparse
import sqlite3

OLD_DB_PATH = r"D:\Project\YunxiBakeBot\data\bot.db"
NEW_DB_PATH = r"D:\Project\YunxiBakery\backend\data\bot.db"

TARGET_CATEGORIES = ("faq", "policy", "after_sales")

# 明确列出字段（禁止 SELECT *），不含客户数据相关列
SELECT_FIELDS = (
    "category, title, content, keywords, priority, is_active, "
    "content_type, created_at, updated_at"
)


def fetch_source_rows() -> list[sqlite3.Row]:
    conn = sqlite3.connect(OLD_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT {SELECT_FIELDS} FROM knowledge_base "
            "WHERE category IN (?, ?, ?) AND is_active = 1 "
            "ORDER BY category, priority DESC, id",
            TARGET_CATEGORIES,
        ).fetchall()
    finally:
        conn.close()
    return rows


def existing_titles(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT category, title FROM knowledge_base WHERE category IN (?, ?, ?)",
        TARGET_CATEGORIES,
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = parser.parse_args()

    source_rows = fetch_source_rows()
    new_conn = sqlite3.connect(NEW_DB_PATH)
    try:
        existing = existing_titles(new_conn)
        to_insert = [
            r for r in source_rows if (r["category"], r["title"]) not in existing
        ]
        skipped = len(source_rows) - len(to_insert)
        before_total = new_conn.execute(
            "SELECT COUNT(*) FROM knowledge_base WHERE category IN (?, ?, ?)",
            TARGET_CATEGORIES,
        ).fetchone()[0]

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(
            f"[{mode}] 源条数={len(source_rows)} 将插入={len(to_insert)} 已存在跳过={skipped}"
        )

        for row in to_insert:
            print(f"  - [{row['category']}] p{row['priority']} {row['title']}")

        if not args.apply:
            print("\n[dry-run] 未写入任何数据；确认后加 --apply 执行")
            return

        inserted = 0
        for row in to_insert:
            cur = new_conn.execute(
                "INSERT INTO knowledge_base "
                "(category, title, content, keywords, priority, is_active, "
                " content_type, content_origin, last_sync_source, last_sync_ref, "
                " created_by, updated_by, audience, review_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["category"],
                    row["title"],
                    row["content"],
                    row["keywords"],
                    row["priority"],
                    row["is_active"],
                    row["content_type"] or "text",
                    "legacy_migration",
                    "legacy_bot_db_20260824",
                    "p05_asset_migration",
                    "ai_migration",
                    "ai_migration",
                    "all",
                    "published",
                ),
            )
            inserted += cur.rowcount
        new_conn.commit()
        print(f"\n[apply] 已插入 {inserted} 条")

        total = new_conn.execute(
            "SELECT COUNT(*) FROM knowledge_base WHERE category IN (?, ?, ?)",
            TARGET_CATEGORIES,
        ).fetchone()[0]
        # 目标类目内可能存在种子等其他来源条目，以插入前基数校验增量
        expected = before_total + inserted
        print(
            f"\n[verify] 新库目标类目现有 {total} 条（预期 {expected} = 迁移前 {before_total} + 插入 {inserted}）"
        )
        assert total == expected, "迁移后总数与预期不符"
        print("[PASS] 迁移总数校验通过")
    finally:
        new_conn.close()


if __name__ == "__main__":
    main()
