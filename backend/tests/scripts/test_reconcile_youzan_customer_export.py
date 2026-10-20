"""有赞客户导出迁移/对账工具测试：解析口径、dry-run、apply/verify、幂等与脱敏。

全部使用真实 SQLite staging 文件与真实仓储/服务，不 mock 数据库。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

# 与真实有赞客户导出一致的列名（UTF-8 BOM CSV）
SOURCE_HEADER = (
    "客户姓名,客户昵称,客户手机号,客户生日,客户性别,标签,是否会员,成长值,"
    "免费等级,付费等级,权益卡,客户积分,客户储值余额,消费次数,消费金额"
)

# 合成数据覆盖：有效/空/非法手机号、零余额、非零余额、积分、金额精度与负余额
SYNTHETIC_ROWS: list[dict[str, str]] = [
    {
        "客户姓名": "张三",
        "客户昵称": "zhangsan",
        "客户手机号": "13800000001",
        "权益卡": "金卡",
        "客户积分": "120",
        "客户储值余额": "89.90",
    },
    {
        "客户姓名": "李四",
        "客户昵称": "lisi",
        "客户手机号": "13800000002",
        "权益卡": "",
        "客户积分": "0",
        "客户储值余额": "0",
    },
    {
        "客户姓名": "王五",
        "客户昵称": "wangwu",
        "客户手机号": "13800000003",
        "权益卡": "银卡",
        "客户积分": "50",
        "客户储值余额": "0.01",
    },
    {
        "客户姓名": "",
        "客户昵称": "赵六",
        "客户手机号": "13800000004",
        "权益卡": "",
        "客户积分": "10",
        "客户储值余额": "100",
    },
    {
        "客户姓名": "空号客户",
        "客户昵称": "",
        "客户手机号": "",
        "权益卡": "",
        "客户积分": "0",
        "客户储值余额": "0",
    },
    {
        "客户姓名": "非法号客户",
        "客户昵称": "",
        "客户手机号": "12345",
        "权益卡": "",
        "客户积分": "0",
        "客户储值余额": "0",
    },
    {
        "客户姓名": "精度异常客户",
        "客户昵称": "",
        "客户手机号": "13800000005",
        "权益卡": "",
        "客户积分": "7",
        "客户储值余额": "12.345",
    },
    {
        "客户姓名": "负余额客户",
        "客户昵称": "",
        "客户手机号": "13800000006",
        "权益卡": "",
        "客户积分": "0",
        "客户储值余额": "-5.00",
    },
]

# 源侧预期口径（与 SYNTHETIC_ROWS 对应）
EXPECTED_TOTAL_ROWS = 8
EXPECTED_VALID_MOBILE_ROWS = 6
EXPECTED_EMPTY_MOBILE_ROWS = 1
EXPECTED_INVALID_MOBILE_ROWS = 1
EXPECTED_NONZERO_BALANCE_ACCOUNTS = 3
EXPECTED_NONZERO_BALANCE_TOTAL_FEN = 8990 + 1 + 10000
EXPECTED_POINTS_ACCOUNTS = 4
EXPECTED_POINTS_TOTAL = 120 + 50 + 10 + 7
EXPECTED_ANOMALY_COUNTS = {
    "empty_mobile": 1,
    "invalid_mobile": 1,
    "balance_precision": 1,
    "negative_balance": 1,
}


def write_source_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    """写入一份与真实导出同构的合成客户 CSV（UTF-8 BOM）。"""
    fieldnames = SOURCE_HEADER.split(",")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return path


def load_script_module() -> ModuleType:
    """按文件路径加载对账脚本模块，隔离其 CLI 入口。"""
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "reconcile_youzan_customer_export.py"
    )
    spec = importlib.util.spec_from_file_location(
        "reconcile_youzan_customer_export", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    """读取脚本产出的 JSON 报告。"""
    return json.loads(path.read_text(encoding="utf-8"))


def query_staging(db_path: Path, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """只读查询 staging 库。"""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_amount_parsing_converts_yuan_to_fen_exactly() -> None:
    """元转分必须精确：89.90 -> 8990，0.01 -> 1；超 2 位小数与负数被拒。"""
    script = load_script_module()

    assert script.parse_amount_yuan_to_fen("89.90") == (8990, "")
    assert script.parse_amount_yuan_to_fen("0.01") == (1, "")
    assert script.parse_amount_yuan_to_fen("100") == (10000, "")
    assert script.parse_amount_yuan_to_fen("") == (0, "")

    fen, reason = script.parse_amount_yuan_to_fen("12.345")
    assert fen is None
    assert reason == script.ANOMALY_BALANCE_PRECISION

    fen, reason = script.parse_amount_yuan_to_fen("-5.00")
    assert fen is None
    assert reason == script.ANOMALY_NEGATIVE_BALANCE

    assert script.parse_points("120") == (120, "")
    assert script.parse_points("") == (0, "")
    assert script.parse_points("-1") == (None, script.ANOMALY_NEGATIVE_POINTS)
    assert script.parse_points("1.5") == (None, script.ANOMALY_POINTS_INVALID)


async def test_dry_run_reports_source_stats_without_creating_staging(
    tmp_path: Path,
) -> None:
    """dry-run 只解析源文件：不建库、不写库，源侧统计口径正确。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"
    report_path = tmp_path / "dry-run.json"

    exit_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--dry-run",
            "--json",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert not staging_db.exists()

    payload = read_json(report_path)
    source = payload["source"]
    assert payload["mode"] == "dry-run"
    assert source["total_rows"] == EXPECTED_TOTAL_ROWS
    assert source["valid_mobile_rows"] == EXPECTED_VALID_MOBILE_ROWS
    assert source["empty_mobile_rows"] == EXPECTED_EMPTY_MOBILE_ROWS
    assert source["invalid_mobile_rows"] == EXPECTED_INVALID_MOBILE_ROWS
    assert source["duplicate_mobile_rows"] == 0
    assert source["nonzero_balance_accounts"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert source["nonzero_balance_total_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert source["nonzero_balance_total_yuan"] == "189.91"
    assert source["points_accounts"] == EXPECTED_POINTS_ACCOUNTS
    assert source["points_total"] == EXPECTED_POINTS_TOTAL
    assert source["anomaly_counts"] == EXPECTED_ANOMALY_COUNTS
    assert payload["import"] is None
    assert payload["verify"] is None


async def test_apply_then_verify_matches_source_balances_and_points(
    tmp_path: Path,
) -> None:
    """apply 后逐会员对账：非零余额数、总额与积分全部一致，流水 source=import。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"
    apply_report = tmp_path / "apply.json"
    verify_report = tmp_path / "verify.json"

    apply_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--apply",
            "--json",
            "--output",
            str(apply_report),
        ]
    )
    assert apply_code == 0
    apply_payload = read_json(apply_report)
    import_report = apply_payload["import"]
    assert import_report["applied"] is True
    assert import_report["batch_status"] == "applied"
    assert import_report["balance_rows"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert import_report["balance_total_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert import_report["balance_applied_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert import_report["balance_variance_fen"] == 0
    assert import_report["failed_count"] == 0
    assert import_report["points_mirrored"] == EXPECTED_POINTS_ACCOUNTS

    verify_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--verify",
            "--json",
            "--output",
            str(verify_report),
        ]
    )
    assert verify_code == 0
    verify = read_json(verify_report)["verify"]
    assert verify["source_nonzero_accounts"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert verify["target_nonzero_accounts"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert verify["source_balance_total_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert verify["target_balance_total_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert verify["source_balance_total_yuan"] == "189.91"
    assert verify["balance_variance_fen"] == 0
    assert verify["variance_count"] == 0
    assert verify["points_source_accounts"] == EXPECTED_POINTS_ACCOUNTS
    assert verify["points_target_accounts"] == EXPECTED_POINTS_ACCOUNTS
    assert verify["points_source_total"] == EXPECTED_POINTS_TOTAL
    assert verify["points_target_total"] == EXPECTED_POINTS_TOTAL
    assert verify["points_variance"] == 0
    assert verify["failed_mobiles"] == []

    balances = query_staging(
        staging_db,
        "SELECT mobile, stored_value_fen, principal_fen, bonus_fen, points "
        "FROM member_balance ORDER BY mobile",
    )
    rows = {row["mobile"]: dict(row) for row in balances}
    assert rows["13800000001"]["stored_value_fen"] == 8990
    assert rows["13800000001"]["principal_fen"] == 8990
    assert rows["13800000001"]["bonus_fen"] == 0
    assert rows["13800000001"]["points"] == 120
    assert rows["13800000003"]["stored_value_fen"] == 1
    assert rows["13800000004"]["stored_value_fen"] == 10000
    # 余额被拒的客户不导储值，但积分仍然镜像
    assert rows["13800000005"]["stored_value_fen"] == 0
    assert rows["13800000005"]["points"] == 7
    # 空号与非法号完全不建档
    assert "13800000006" not in rows

    ledger = query_staging(
        staging_db,
        "SELECT unique_id, amount_fen, source, biz_type FROM balance_ledger "
        "ORDER BY id",
    )
    assert len(ledger) == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert all(row["source"] == "import" for row in ledger)
    assert all(row["biz_type"] == "recharge" for row in ledger)
    assert (
        sum(row["amount_fen"] for row in ledger) == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    )


async def test_repeat_apply_and_verify_are_idempotent(tmp_path: Path) -> None:
    """重复 apply 不得重复加款：余额、流水条数与对账结果保持不变。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"

    first = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--apply",
            "--json",
            "--output",
            str(tmp_path / "apply-1.json"),
        ]
    )
    assert first == 0
    first_batch = read_json(tmp_path / "apply-1.json")["import"]["batch_id"]

    second = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--apply",
            "--json",
            "--output",
            str(tmp_path / "apply-2.json"),
        ]
    )
    assert second == 0
    second_import = read_json(tmp_path / "apply-2.json")["import"]
    # 同一份归一化 CSV 复用同一批次，绝不新建批次重复入账
    assert second_import["batch_id"] == first_batch
    assert second_import["balance_rows"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert second_import["balance_applied_fen"] == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    assert second_import["failed_count"] == 0

    ledger_rows = query_staging(
        staging_db, "SELECT id, amount_fen FROM balance_ledger ORDER BY id"
    )
    assert len(ledger_rows) == EXPECTED_NONZERO_BALANCE_ACCOUNTS
    assert (
        sum(row["amount_fen"] for row in ledger_rows)
        == EXPECTED_NONZERO_BALANCE_TOTAL_FEN
    )

    verify_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--verify",
            "--json",
            "--output",
            str(tmp_path / "verify.json"),
        ]
    )
    assert verify_code == 0
    verify = read_json(tmp_path / "verify.json")["verify"]
    assert verify["variance_count"] == 0
    assert verify["balance_variance_fen"] == 0
    assert verify["points_variance"] == 0
    assert verify["target_nonzero_accounts"] == EXPECTED_NONZERO_BALANCE_ACCOUNTS


async def test_rejected_amounts_are_listed_as_anomalies_and_not_imported(
    tmp_path: Path,
) -> None:
    """超过 2 位小数与负余额必须列为异常，且不得进入储值批次。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"
    report_path = tmp_path / "apply.json"

    exit_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--apply",
            "--json",
            "--output",
            str(report_path),
        ]
    )
    assert exit_code == 0
    payload = read_json(report_path)
    reasons = {item["reason"] for item in payload["source"]["anomalies"]}
    assert "balance_precision" in reasons
    assert "negative_balance" in reasons

    ledger_rows = query_staging(
        staging_db, "SELECT mobile FROM balance_ledger ORDER BY id"
    )
    imported_mobiles = {row["mobile"] for row in ledger_rows}
    assert "13800000005" not in imported_mobiles
    assert "13800000006" not in imported_mobiles
    assert imported_mobiles == {
        "13800000001",
        "13800000003",
        "13800000004",
    }


async def test_report_masks_mobile_numbers(tmp_path: Path) -> None:
    """报告中的手机号必须脱敏（前 3 后 4），不得出现完整手机号。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"
    apply_report = tmp_path / "apply.json"
    verify_report = tmp_path / "verify.json"

    apply_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--apply",
            "--json",
            "--output",
            str(apply_report),
        ]
    )
    assert apply_code == 0
    verify_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--verify",
            "--json",
            "--output",
            str(verify_report),
        ]
    )
    assert verify_code == 0

    for raw in (
        apply_report.read_text(encoding="utf-8"),
        verify_report.read_text(encoding="utf-8"),
    ):
        for mobile in (
            "13800000001",
            "13800000002",
            "13800000003",
            "13800000004",
            "13800000005",
            "13800000006",
        ):
            assert mobile not in raw

    samples = read_json(verify_report)["verify"]["samples"]
    assert samples
    assert all(sample["mobile"].count("*") == 4 for sample in samples)
    assert "138****0001" in verify_report.read_text(encoding="utf-8")


async def test_output_file_refuses_overwrite(tmp_path: Path) -> None:
    """报告文件已存在时拒绝覆盖，避免验收证据被静默改写。"""
    script = load_script_module()
    source_path = write_source_csv(tmp_path / "customers.csv", SYNTHETIC_ROWS)
    staging_db = tmp_path / "staging" / "youzan_staging.db"
    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")

    exit_code = await script.async_main(
        [
            "--source",
            str(source_path),
            "--staging-db",
            str(staging_db),
            "--dry-run",
            "--json",
            "--output",
            str(report_path),
        ]
    )
    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "{}"


def test_staging_path_guard_refuses_production_data_dir(tmp_path: Path) -> None:
    """staging 库落在生产目录时必须拒绝执行。"""
    script = load_script_module()
    with pytest.raises(ValueError):
        script.assert_staging_path_allowed(script.ROOT_DIR / "data" / "bot.db")
    # 临时目录允许
    allowed = script.assert_staging_path_allowed(tmp_path / "staging.db")
    assert allowed.name == "staging.db"
