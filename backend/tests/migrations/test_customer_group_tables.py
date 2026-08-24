"""客户群运营表结构测试。"""

import aiosqlite


async def test_customer_group_tables_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含客户群运营三张表和关键字段。"""
    group_columns = await _column_names(db, "customer_groups")
    campaign_columns = await _column_names(db, "group_campaigns")
    registration_columns = await _column_names(db, "group_registrations")

    assert {"chat_id", "opengid", "owner_userid", "status"}.issubset(group_columns)
    assert {"group_id", "title", "status", "summary_note"}.issubset(campaign_columns)
    assert {
        "campaign_id",
        "group_id",
        "user_id",
        "product_name",
        "quantity",
        "fulfillment_method",
        "status",
    }.issubset(registration_columns)


async def test_customer_group_indexes_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含客户群运营关键索引。"""
    group_indexes = await _index_names(db, "customer_groups")
    campaign_indexes = await _index_names(db, "group_campaigns")
    registration_indexes = await _index_names(db, "group_registrations")

    assert "idx_cg_opengid" in group_indexes
    assert "idx_gc_group_status" in campaign_indexes
    assert "idx_gr_campaign_status" in registration_indexes
    assert "idx_gr_user" in registration_indexes


async def _column_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_table_info(?)",
        (table_name,),
    )
    return {row["name"] for row in rows}


async def _index_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_index_list(?)",
        (table_name,),
    )
    return {row["name"] for row in rows}
