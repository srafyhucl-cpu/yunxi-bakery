"""有赞储值余额期初导入管线测试：dry-run / apply / 对账 / 幂等 / 回滚。

全部使用真实内存 SQLite 与真实仓储/服务，驱动 v041 批次表与存储过程。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import aiosqlite
import pytest

from app.models.stored_value import BalanceBizType, BalanceSource
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.stored_value.importing import (
    BATCH_STATUS_APPLIED,
    StoredValueImportError,
    StoredValueImportService,
    mask_mobile,
)
from app.service.stored_value.member import MemberBalanceService

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SYNTHETIC_CSV = FIXTURE_DIR / "youzan_stored_value_synthetic.csv"
HEADER = (
    "mobile,display_name,principal_fen,bonus_fen,reported_total_fen,"
    "yz_open_id,card_no,card_alias"
)
LEDGER_COUNT_SQL = "SELECT COUNT(id) AS c FROM balance_ledger"
BALANCE_COUNT_SQL = "SELECT COUNT(id) AS c FROM member_balance"


def write_csv(tmp_path: Path, rows: list[str], name: str = "import.csv") -> Path:
    """写入一份以英文规范表头为准的合成储值导入 CSV。"""
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def build_member_service(db) -> MemberBalanceService:
    """用真实仓储构建会员账务服务（与导入服务共享同一连接）。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )


async def _count_rows(db, sql: str) -> int:
    rows = await db.execute_fetchall(sql)
    return int(rows[0]["c"])


async def _balance_fen(db, mobile: str) -> int:
    rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ? LIMIT 1",
        (mobile,),
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


async def _column_names(db, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_table_info(?)", (table_name,)
    )
    return {row["name"] for row in rows}


def load_script_module() -> ModuleType:
    """按文件路径加载导入脚本模块，隔离其 CLI 入口。"""
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "import_youzan_stored_value.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_youzan_stored_value", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_dry_run_creates_batch_without_touching_accounting(
    db: aiosqlite.Connection,
) -> None:
    """dry-run 只创建/校验批次，绝不写入 member_balance 与 balance_ledger。"""
    columns = await _column_names(db, "youzan_stored_value_import_rows")
    assert {"batch_id", "row_no", "mobile", "status"}.issubset(columns)

    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(SYNTHETIC_CSV)
    report = await service.validate_batch(batch["id"])

    assert report["total_rows"] == 16
    assert report["valid_rows"] == 11
    assert report["invalid_rows"] == 5
    assert report["conflict_rows"] == 0
    assert report["status"] == "failed"
    assert report["variance_fen"] == 0
    assert await _count_rows(db, BALANCE_COUNT_SQL) == 0
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 0


async def test_apply_batch_credits_balance_ledger_and_identity(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """apply 正常批次：身份/余额/流水正确，拆分正确，对账差异为 0。"""
    csv_path = write_csv(
        tmp_path,
        [
            "13800000021,甲,10000,0,10000,o_a,CARD_A,金卡",
            "13800000022,乙,20000,2000,22000,o_b,CARD_B,银卡",
        ],
    )
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    validated = await service.validate_batch(batch["id"])
    assert validated["invalid_rows"] == 0

    report = await service.apply_batch(batch["id"])
    assert report["status"] == BATCH_STATUS_APPLIED
    assert report["applied_rows"] == 2
    assert report["expected_total_fen"] == 32000
    assert report["applied_total_fen"] == 32000
    assert report["variance_fen"] == 0
    assert report["expected_principal_fen"] == 30000
    assert report["expected_bonus_fen"] == 2000
    assert report["applied_principal_fen"] == 30000
    assert report["applied_bonus_fen"] == 2000
    assert report["principal_variance_fen"] == 0
    assert report["bonus_variance_fen"] == 0

    masters = await db.execute_fetchall(
        "SELECT id, primary_phone FROM customer_master "
        "WHERE primary_phone IN ('13800000021','13800000022') "
        "ORDER BY primary_phone"
    )
    assert [row["primary_phone"] for row in masters] == [
        "13800000021",
        "13800000022",
    ]
    assert (
        await _count_rows(
            db,
            "SELECT COUNT(id) AS c FROM customer_identity_links "
            "WHERE identity_type = 'phone'",
        )
        == 2
    )

    balances = await db.execute_fetchall(
        "SELECT mobile, stored_value_fen, principal_fen, bonus_fen, customer_id, "
        "yz_open_id, card_alias, card_no, is_member FROM member_balance "
        "WHERE mobile IN ('13800000021','13800000022') ORDER BY mobile"
    )
    first, second = balances
    assert (first["stored_value_fen"], first["principal_fen"], first["bonus_fen"]) == (
        10000,
        10000,
        0,
    )
    assert (
        second["stored_value_fen"],
        second["principal_fen"],
        second["bonus_fen"],
    ) == (
        22000,
        20000,
        2000,
    )
    assert first["customer_id"] == masters[0]["id"]
    assert first["is_member"] == 1
    assert second["yz_open_id"] == "o_b"
    assert second["card_alias"] == "银卡"

    ledger = await db.execute_fetchall(
        "SELECT unique_id, amount_fen, biz_type, biz_id, source, "
        "principal_delta_fen, bonus_delta_fen, balance_after_fen FROM balance_ledger "
        "ORDER BY id"
    )
    assert len(ledger) == 2
    assert all(row["source"] == "import" for row in ledger)
    assert all(row["biz_type"] == "recharge" for row in ledger)
    assert all(row["biz_id"] == batch["id"] for row in ledger)
    assert ledger[0]["unique_id"] == f"import:{batch['id']}:13800000021"
    assert (
        ledger[1]["amount_fen"],
        ledger[1]["principal_delta_fen"],
        ledger[1]["bonus_delta_fen"],
    ) == (22000, 20000, 2000)
    assert ledger[1]["balance_after_fen"] == 22000


async def test_repeat_apply_same_source_does_not_double_credit(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """同一 source_sha256 重复 apply 复用批次且不重复加款。"""
    csv_path = write_csv(tmp_path, ["13800000031,甲,12000,0,12000,,,"])
    service = StoredValueImportService(db)
    first_batch = await service.create_batch_from_csv(csv_path)
    await service.validate_batch(first_batch["id"])
    await service.apply_batch(first_batch["id"])
    balance_after_first = await _balance_fen(db, "13800000031")
    ledger_after_first = await _count_rows(db, LEDGER_COUNT_SQL)

    reused = await service.create_batch_from_csv(csv_path)
    assert reused["id"] == first_batch["id"]
    report = await service.apply_batch(reused["id"])

    assert report["status"] == BATCH_STATUS_APPLIED
    assert await _balance_fen(db, "13800000031") == balance_after_first
    assert await _count_rows(db, LEDGER_COUNT_SQL) == ledger_after_first


async def test_apply_refuses_when_invalid_rows_present(
    db: aiosqlite.Connection,
) -> None:
    """存在非法行时整批拒绝入账，一行都不落账。"""
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(SYNTHETIC_CSV)
    report = await service.validate_batch(batch["id"])
    assert report["invalid_rows"] == 5

    with pytest.raises(StoredValueImportError):
        await service.apply_batch(batch["id"])
    assert await _count_rows(db, BALANCE_COUNT_SQL) == 0
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 0


async def test_apply_refuses_existing_non_zero_balance(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """本地已有非零余额（等额或不等额）时拒绝入账，绝不覆盖/叠加。"""
    for mobile, existing_fen in (("13800000041", 5000), ("13800000042", 9999)):
        await db.execute(
            "INSERT INTO member_balance (mobile, stored_value_fen, principal_fen) "
            "VALUES (?, ?, ?)",
            (mobile, existing_fen, existing_fen),
        )
    await db.commit()
    csv_path = write_csv(
        tmp_path,
        [
            "13800000041,等额冲突,5000,0,5000,,,",
            "13800000042,不等额冲突,8000,0,8000,,,",
        ],
    )
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    report = await service.validate_batch(batch["id"])
    assert report["conflict_rows"] == 2
    assert report["invalid_rows"] == 2

    with pytest.raises(StoredValueImportError):
        await service.apply_batch(batch["id"])
    assert await _balance_fen(db, "13800000041") == 5000
    assert await _balance_fen(db, "13800000042") == 9999
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 0


async def test_rollback_clean_batch_restores_and_is_idempotent(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """干净批次回滚恢复余额与流水，重复回滚幂等；客户主档保留。"""
    csv_path = write_csv(
        tmp_path,
        [
            "13800000051,甲,10000,1000,11000,o_a,CARD_A,金卡",
            "13800000052,乙,20000,0,20000,,,",
        ],
    )
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    await service.validate_batch(batch["id"])
    await service.apply_batch(batch["id"])
    assert await _balance_fen(db, "13800000051") == 11000

    report = await service.rollback_batch(batch["id"])
    assert report["status"] == "rolled_back"
    assert await _balance_fen(db, "13800000051") == 0
    assert await _balance_fen(db, "13800000052") == 0
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 0
    assert await _count_rows(db, BALANCE_COUNT_SQL) == 2
    assert await _count_rows(db, "SELECT COUNT(id) AS c FROM customer_master") == 2

    again = await service.rollback_batch(batch["id"])
    assert again["status"] == "rolled_back"
    assert await _balance_fen(db, "13800000051") == 0


async def test_rollback_refuses_when_later_ledger_exists(
    db: aiosqlite.Connection, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """导入后已产生后续流水的批次拒绝回滚，并在日志中脱敏手机号。"""
    csv_path = write_csv(tmp_path, ["13800000061,甲,10000,0,10000,,,"])
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    await service.validate_batch(batch["id"])
    await service.apply_batch(batch["id"])

    await build_member_service(db).deduct(
        user_id="customer-61",
        mobile="13800000061",
        amount_fen=1000,
        biz_type=BalanceBizType.ORDER_PAY,
        biz_id="order-61",
        unique_id="order_pay:order-61",
        source=BalanceSource.ORDER,
    )
    assert await _balance_fen(db, "13800000061") == 9000

    with caplog.at_level("ERROR"):
        with pytest.raises(StoredValueImportError) as excinfo:
            await service.rollback_batch(batch["id"])

    message = str(excinfo.value)
    assert "138****0061" in message
    assert "13800000061" not in message
    assert "13800000061" not in caplog.text
    assert await _balance_fen(db, "13800000061") == 9000
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 2


async def test_reimport_after_rollback_creates_new_batch_audit_chain(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """回滚后同一 CSV 重导入必须新建批次，旧批次保持 rolled_back。"""
    csv_path = write_csv(tmp_path, ["13800000101,甲,10000,0,10000,,,"])
    service = StoredValueImportService(db)
    first = await service.create_batch_from_csv(csv_path)
    await service.validate_batch(first["id"])
    await service.apply_batch(first["id"])
    await service.rollback_batch(first["id"])

    second = await service.create_batch_from_csv(csv_path)
    assert second["id"] != first["id"]
    assert (await service.report(first["id"]))["status"] == "rolled_back"

    retried = await service.validate_batch(second["id"])
    assert retried["invalid_rows"] == 0
    report = await service.apply_batch(second["id"])
    assert report["status"] == BATCH_STATUS_APPLIED
    assert await _balance_fen(db, "13800000101") == 10000
    assert await _count_rows(db, LEDGER_COUNT_SQL) == 1


async def test_failed_batch_is_not_reused(db: aiosqlite.Connection) -> None:
    """校验失败批次不得复用，重试必须新建批次留痕。"""
    service = StoredValueImportService(db)
    first = await service.create_batch_from_csv(SYNTHETIC_CSV)
    await service.validate_batch(first["id"])
    assert (await service.report(first["id"]))["status"] == "failed"

    second = await service.create_batch_from_csv(SYNTHETIC_CSV)
    assert second["id"] != first["id"]


async def test_report_reconciles_principal_and_bonus_split(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """拆分被篡改（总额不变）时本金/赠送金差异必须暴露；恢复后为 0。"""
    csv_path = write_csv(tmp_path, ["13800000111,甲,10000,0,10000,,,"])
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    await service.validate_batch(batch["id"])
    report = await service.apply_batch(batch["id"])

    assert report["principal_variance_fen"] == 0
    assert report["bonus_variance_fen"] == 0
    assert report["variance_fen"] == 0
    assert report["applied_principal_fen"] == 10000
    assert report["applied_bonus_fen"] == 0

    # 仅在临时库内篡改拆分：总额不变，本金/赠送金结构被破坏
    await db.execute(
        "UPDATE balance_ledger SET principal_delta_fen = 9000, bonus_delta_fen = 1000 "
        "WHERE unique_id = ?",
        (f"import:{batch['id']}:13800000111",),
    )
    await db.commit()
    tampered = await service.report(batch["id"])
    assert tampered["variance_fen"] == 0
    assert tampered["principal_variance_fen"] == 1000
    assert tampered["bonus_variance_fen"] == -1000

    await db.execute(
        "UPDATE balance_ledger SET principal_delta_fen = 10000, bonus_delta_fen = 0 "
        "WHERE unique_id = ?",
        (f"import:{batch['id']}:13800000111",),
    )
    await db.commit()
    restored = await service.report(batch["id"])
    assert restored["principal_variance_fen"] == 0
    assert restored["bonus_variance_fen"] == 0
    assert restored["variance_fen"] == 0


async def test_report_masks_mobile_in_details(
    db: aiosqlite.Connection, tmp_path: Path
) -> None:
    """报告中的冲突明细只输出脱敏手机号。"""
    await db.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, principal_fen) "
        "VALUES (?, ?, ?)",
        ("13800000071", 1234, 1234),
    )
    await db.commit()
    csv_path = write_csv(tmp_path, ["13800000071,冲突,1234,0,1234,,,"])
    service = StoredValueImportService(db)
    batch = await service.create_batch_from_csv(csv_path)
    report = await service.validate_batch(batch["id"])

    assert "13800000071" not in json.dumps(report, ensure_ascii=False)
    assert mask_mobile("13800000071") == "138****0071"
    assert report["conflict_details"][0]["mobile"] == "138****0071"


async def test_script_dry_run_apply_and_rollback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """脚本 dry-run -> apply -> rollback 全链路退出码与报告正确。"""
    script = load_script_module()
    csv_path = write_csv(tmp_path, ["13800000081,甲,15000,500,15500,o_a,CARD_A,金卡"])
    db_path = tmp_path / "bot.db"

    dry_code = await script.async_main(
        ["--source", str(csv_path), "--db-path", str(db_path), "--json"]
    )
    assert dry_code == 0
    dry_report = json.loads(capsys.readouterr().out)["report"]
    assert dry_report["invalid_rows"] == 0
    assert dry_report["status"] == "validated"

    apply_code = await script.async_main(
        ["--source", str(csv_path), "--db-path", str(db_path), "--apply", "--json"]
    )
    assert apply_code == 0
    apply_report = json.loads(capsys.readouterr().out)["report"]
    assert apply_report["status"] == "applied"
    assert apply_report["variance_fen"] == 0
    # 干跑已把批次推进到 validated，apply 复用同一批次而非新建
    assert apply_report["batch_id"] == dry_report["batch_id"]

    rollback_code = await script.async_main(
        [
            "--db-path",
            str(db_path),
            "--rollback-batch",
            apply_report["batch_id"],
            "--json",
        ]
    )
    assert rollback_code == 0
    rollback_report = json.loads(capsys.readouterr().out)["report"]
    assert rollback_report["status"] == "rolled_back"


async def test_script_exits_nonzero_on_invalid_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """校验失败时脚本以非 0 退出并给出 failed 报告。"""
    script = load_script_module()
    db_path = tmp_path / "bot.db"

    exit_code = await script.async_main(
        ["--source", str(SYNTHETIC_CSV), "--db-path", str(db_path), "--json"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["report"]["invalid_rows"] == 5


async def test_script_rollback_refusal_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """存在后续流水时脚本回滚以非 0 退出，并输出脱敏手机号。"""
    from app.database import close_db, init_db

    script = load_script_module()
    csv_path = write_csv(tmp_path, ["13800000091,甲,10000,0,10000,,,"])
    db_path = tmp_path / "bot.db"
    await script.async_main(
        ["--source", str(csv_path), "--db-path", str(db_path), "--apply", "--json"]
    )
    batch_id = json.loads(capsys.readouterr().out)["report"]["batch_id"]

    conn = await init_db(str(db_path))
    try:
        await build_member_service(conn).deduct(
            user_id="customer-91",
            mobile="13800000091",
            amount_fen=1000,
            biz_type=BalanceBizType.ORDER_PAY,
            biz_id="order-91",
            unique_id="order_pay:order-91",
            source=BalanceSource.ORDER,
        )
    finally:
        await close_db(conn)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--rollback-batch", batch_id, "--json"]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "138****0091" in stderr
    assert "13800000091" not in stderr
