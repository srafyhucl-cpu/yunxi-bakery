"""有赞审计终态回写脚本的测试（真实 SQLite 临时库，不 mock 数据库）。"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "reconcile_youzan_audit_status.py"
)

INBOX_DDL = """
CREATE TABLE IF NOT EXISTS inbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_name TEXT NOT NULL,
    message_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK(status IN ('received', 'processing', 'processed', 'failed', 'dead_letter')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS youzan_webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT NOT NULL UNIQUE,
    trace_id TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    business_type TEXT NOT NULL
        CHECK(business_type IN ('trade','item','chat','member','unknown')),
    business_key TEXT DEFAULT '',
    status TEXT NOT NULL
        CHECK(status IN ('received','processing','processed','skipped','failed','duplicate')),
    http_status INTEGER DEFAULT 200,
    process_stage TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    payload_hash TEXT DEFAULT '',
    payload_summary_json TEXT DEFAULT '{}',
    received_at TEXT NOT NULL,
    process_started_at TEXT,
    process_finished_at TEXT,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

MEMBER_BALANCE_DDL = """
CREATE TABLE IF NOT EXISTS member_balance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    stored_value_fen INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

POINTS_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS points_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'webhook',
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

YOUZAN_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS youzan_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL DEFAULT '',
    buyer_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    amount_fen INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

YOUZAN_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS youzan_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    price_fen INTEGER NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

BEIJING_TZ = timezone(timedelta(hours=8))


def load_module() -> ModuleType:
    """按路径加载被测脚本模块。"""
    spec = importlib.util.spec_from_file_location(
        "reconcile_youzan_audit_status", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def timestamp_hours_ago(hours: int) -> str:
    """生成相对当前北京时间的历史时间戳。"""
    moment = datetime.now(BEIJING_TZ) - timedelta(hours=hours)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """建立只含目标表的真实 SQLite 临时库。"""
    path = tmp_path / "bot.db"
    with sqlite3.connect(path) as connection:
        connection.execute(AUDIT_DDL)
        connection.execute(INBOX_DDL)
        connection.execute(MEMBER_BALANCE_DDL)
        connection.execute(POINTS_LEDGER_DDL)
        connection.execute(YOUZAN_ORDERS_DDL)
        connection.execute(YOUZAN_PRODUCTS_DDL)
    return path


def insert_order(db_path: Path, *, order_no: str) -> None:
    """写入一条订单落地记录。"""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO youzan_orders (order_no, status, updated_at) "
            "VALUES (?, 'TRADE_PAID', '2026-10-20 00:00:00')",
            (order_no,),
        )


def insert_audit(
    db_path: Path,
    *,
    msg_id: str = "yzuser_1",
    event_type: str = "trade_TradePaid",
    business_type: str = "trade",
    business_key: str = "E202610201200001",
    status: str = "received",
    received_at: str | None = None,
) -> int:
    """写入一条审计记录，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO youzan_webhook_events "
            "(msg_id, event_type, business_type, business_key, status, http_status, "
            "received_at) VALUES (?, ?, ?, ?, ?, 200, ?)",
            (
                msg_id,
                event_type,
                business_type,
                business_key,
                status,
                received_at if received_at is not None else timestamp_hours_ago(48),
            ),
        )
        return int(cursor.lastrowid or 0)


def insert_inbox(
    db_path: Path,
    *,
    msg_id: str = "yzuser_1",
    status: str = "processed",
    queue_name: str = "youzan_webhook",
    payload_json: str = '{"audit_id": null}',
) -> int:
    """写入一条 inbox 记录，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO inbox_events "
            "(queue_name, message_key, payload_json, status, attempt_count, "
            "lease_until, next_attempt_at, last_error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, '2026-10-05 02:49:37', '2026-10-05 02:49:37', "
            "'', '2026-10-05 02:49:36', '2026-10-05 02:49:37')",
            (queue_name, f"youzan_webhook:{msg_id}", payload_json, status),
        )
        return int(cursor.lastrowid or 0)


def read_audit(db_path: Path, row_id: int) -> dict[str, object]:
    """读取一条审计记录的关键字段。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, msg_id, status, process_stage, error_type, error_message, "
            "process_finished_at, updated_at, received_at "
            "FROM youzan_webhook_events WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def read_inbox(db_path: Path, row_id: int) -> dict[str, object]:
    """读取一条 inbox 记录的关键字段。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, message_key, status, attempt_count, last_error "
            "FROM inbox_events WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def run_cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict]:
    """执行脚本 CLI 并解析 stdout 上的 JSON 报告。"""
    module = load_module()
    exit_code = module.main(list(args))
    captured = capsys.readouterr()
    assert captured.out.strip(), "stdout 必须输出 JSON 报告"
    return exit_code, json.loads(captured.out)


def test_dry_run_does_not_write_database(db_path: Path, capsys) -> None:
    """dry-run 只出报告，不改审计状态。"""
    audit_id = insert_audit(db_path)
    insert_inbox(db_path)

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    assert report["mode"] == "dry-run"
    assert report["summary"]["would_processed"] == 1
    assert report["summary"]["processed_written"] == 0
    assert read_audit(db_path, audit_id)["status"] == "received"


def test_processed_backfill_marks_audit_processed(db_path: Path, capsys) -> None:
    """inbox 已 processed 时把审计回写为 processed 并记录稳定阶段码。"""
    audit_id = insert_audit(db_path)
    insert_inbox(db_path, status="processed")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["summary"]["would_processed"] == 1
    assert report["summary"]["processed_written"] == 1
    assert report["summary"]["committed"] is True

    row = read_audit(db_path, audit_id)
    assert row["status"] == "processed"
    assert row["process_stage"] == "audit_backfilled"
    assert row["process_finished_at"]
    assert row["updated_at"]


def test_audit_without_inbox_is_kept(db_path: Path, capsys) -> None:
    """没有对应 inbox 记录的行默认原样保留，不做任何猜测。"""
    audit_id = insert_audit(db_path, msg_id="no-inbox-1")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["summary"]["would_processed"] == 0
    assert report["summary"]["kept"] == 1
    assert report["stats"]["by_reason"]["no_inbox_record"] == 1
    assert read_audit(db_path, audit_id)["status"] == "received"


def test_inbox_not_processed_is_kept(db_path: Path, capsys) -> None:
    """inbox 未 processed 时不得回写 processed。"""
    audit_id = insert_audit(db_path, msg_id="dead-1")
    insert_inbox(db_path, msg_id="dead-1", status="dead_letter")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["summary"]["would_processed"] == 0
    assert report["stats"]["by_reason"]["inbox_dead_letter"] == 1
    assert read_audit(db_path, audit_id)["status"] == "received"


def test_mark_unmatched_skipped_marks_kept_rows(db_path: Path, capsys) -> None:
    """显式开启 --mark-unmatched-skipped 后才把无法确认的行标成 skipped。"""
    audit_id = insert_audit(db_path, msg_id="no-inbox-2")

    exit_code, report = run_cli(
        capsys, "--db", str(db_path), "--apply", "--mark-unmatched-skipped"
    )

    assert exit_code == 0
    assert report["summary"]["would_skipped"] == 1
    assert report["summary"]["skipped_written"] == 1

    row = read_audit(db_path, audit_id)
    assert row["status"] == "skipped"
    assert row["error_type"] == "audit_no_inbox_record"


def test_recent_rows_are_guarded(db_path: Path, capsys) -> None:
    """早于阈值之外的近期行不处理，防呆避免动到新事件。"""
    audit_id = insert_audit(db_path, received_at=timestamp_hours_ago(1))
    insert_inbox(db_path, status="processed")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["scope"]["recent_kept_total"] == 1
    assert report["summary"]["candidate_total"] == 0
    assert report["summary"]["would_processed"] == 0
    assert read_audit(db_path, audit_id)["status"] == "received"


def test_apply_is_idempotent(db_path: Path, capsys) -> None:
    """重复执行 --apply 不会二次改写，第二次没有可写行。"""
    audit_id = insert_audit(db_path)
    insert_inbox(db_path, status="processed")

    first_code, first_report = run_cli(capsys, "--db", str(db_path), "--apply")
    assert first_code == 0
    assert first_report["summary"]["processed_written"] == 1

    second_code, second_report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert second_code == 0
    assert second_report["summary"]["candidate_total"] == 0
    assert second_report["summary"]["processed_written"] == 0
    assert read_audit(db_path, audit_id)["status"] == "processed"


def test_production_path_requires_allow_production(tmp_path: Path, capsys) -> None:
    """路径疑似生产部署目录时必须显式声明 --allow-production。"""
    production_dir = tmp_path / "opt" / "apps" / "yunxi-bakery"
    production_dir.mkdir(parents=True)
    db_file = production_dir / "bot.db"
    with sqlite3.connect(db_file) as connection:
        connection.execute(AUDIT_DDL)
        connection.execute(INBOX_DDL)

    exit_code, report = run_cli(capsys, "--db", str(db_file))

    assert exit_code == 2
    assert report["status"] == "rejected"
    assert report["summary"]["rejected"] is True


def test_missing_database_is_rejected(tmp_path: Path, capsys) -> None:
    """目标库不存在时拒绝执行，不创建数据库。"""
    missing = tmp_path / "not-exists.db"

    exit_code, report = run_cli(capsys, "--db", str(missing))

    assert exit_code == 2
    assert report["status"] == "rejected"
    assert not missing.exists()


def test_report_masks_phone_numbers(db_path: Path, capsys) -> None:
    """报告里的手机号必须脱敏。"""
    insert_audit(
        db_path,
        msg_id="yzuser_2",
        event_type="POINTS",
        business_type="member",
        business_key="13800138000",
    )
    insert_inbox(db_path, msg_id="yzuser_2", status="processed")

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    text = json.dumps(report, ensure_ascii=False)
    assert "13800138000" not in text
    assert "138****8000" in text
    assert report["samples"][0]["business_key"] == "138****8000"


def test_report_structure_is_stable(db_path: Path, capsys) -> None:
    """同一份数据两次 dry-run 的报告核心结构一致。"""
    insert_audit(db_path)
    insert_inbox(db_path, status="processed")
    insert_audit(db_path, msg_id="no-inbox-3")

    _, first = run_cli(capsys, "--db", str(db_path))
    _, second = run_cli(capsys, "--db", str(db_path))

    assert first["stats"] == second["stats"]
    assert first["scope"] == second["scope"]
    assert first["plan"] == second["plan"]
    assert first["summary"] == second["summary"]


def test_apply_does_not_touch_inbox_or_ledger(db_path: Path, capsys) -> None:
    """回写只改审计表，不动 inbox、member_balance 与 points_ledger。"""
    audit_id = insert_audit(db_path)
    inbox_id = insert_inbox(db_path, status="processed")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO member_balance (mobile, points) VALUES ('13800138000', 100)"
        )
        connection.execute(
            "INSERT INTO points_ledger (unique_id, mobile, amount) "
            "VALUES ('u-1', '13800138000', 10)"
        )

    exit_code, _ = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert read_audit(db_path, audit_id)["status"] == "processed"
    assert read_inbox(db_path, inbox_id)["status"] == "processed"
    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM member_balance").fetchone()[0] == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM points_ledger").fetchone()[0] == 1
        )


def test_inbox_of_other_queue_is_not_matched(db_path: Path, capsys) -> None:
    """非有赞队列的 inbox 行不得被当成处理证据。"""
    audit_id = insert_audit(db_path, msg_id="other-queue-1")
    insert_inbox(
        db_path, msg_id="other-queue-1", status="processed", queue_name="wecom"
    )

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["summary"]["would_processed"] == 0
    assert report["stats"]["by_reason"]["no_inbox_record"] == 1
    assert read_audit(db_path, audit_id)["status"] == "received"


def test_business_evidence_is_reported_but_does_not_change_decision(
    db_path: Path, capsys
) -> None:
    """业务落地佐证只进报告，不参与判定，也不改写审计状态。"""
    audit_id = insert_audit(
        db_path,
        msg_id="trade-1",
        business_key="E202610201200001",
    )
    insert_inbox(db_path, msg_id="trade-1", status="processed")
    insert_order(db_path, order_no="E202610201200001")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    evidence = report["stats"]["business_evidence"]
    assert evidence["available"] is True
    assert evidence["by_business_type"]["trade"]["total"] == 1
    assert evidence["by_business_type"]["trade"]["with_business_evidence"] == 1
    assert report["summary"]["processed_written"] == 1
    assert read_audit(db_path, audit_id)["status"] == "processed"


def test_business_evidence_missing_still_backfills_when_inbox_processed(
    db_path: Path, capsys
) -> None:
    """落地表查不到时证据维度记 0，但判定仍以 inbox 为准。"""
    audit_id = insert_audit(db_path, msg_id="trade-2", business_key="E-MISSING")
    insert_inbox(db_path, msg_id="trade-2", status="processed")

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    evidence = report["stats"]["business_evidence"]
    assert evidence["by_business_type"]["trade"]["with_business_evidence"] == 0
    assert report["summary"]["processed_written"] == 1
    assert read_audit(db_path, audit_id)["status"] == "processed"


def test_empty_business_key_is_not_counted_as_evidence(db_path: Path, capsys) -> None:
    """business_key 为空的行不得被算成「有业务落地佐证」。"""
    insert_audit(
        db_path,
        msg_id="scrm-1",
        event_type="SCRM_CUSTOMER_EVENT",
        business_type="member",
        business_key="",
    )
    insert_inbox(db_path, msg_id="scrm-1", status="processed")

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    evidence = report["stats"]["business_evidence"]
    assert evidence["by_business_type"]["member"]["total"] == 0
    assert evidence["by_business_type"]["member"]["with_business_evidence"] == 0


def test_apply_rolls_back_when_a_row_fails(db_path: Path, capsys) -> None:
    """任一行写失败时整体回滚，绝不部分写入。"""
    good_id = insert_audit(db_path, msg_id="good-1")
    bad_id = insert_audit(db_path, msg_id="bad-1")
    insert_inbox(db_path, msg_id="good-1", status="processed")
    insert_inbox(db_path, msg_id="bad-1", status="processed")
    # 用真实触发器制造单行写入失败，验证事务整体回滚
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_on_bad BEFORE UPDATE ON youzan_webhook_events "
            "WHEN OLD.msg_id = 'bad-1' BEGIN "
            "SELECT RAISE(ABORT, '模拟写入失败'); END"
        )

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 1
    assert report["result"]["committed"] is False
    assert report["result"]["failures"]
    assert report["result"]["error"]
    assert read_audit(db_path, good_id)["status"] == "received"
    assert read_audit(db_path, bad_id)["status"] == "received"


def test_run_in_transaction_rolls_back_on_unexpected_error(db_path: Path) -> None:
    """事务包装器遇到意外异常时必须回滚，不得留下部分写入。

    断言点选在**同一条连接**上、异常抛出之后、连接关闭之前：
    若 ROLLBACK 真的执行了，本连接读到的就是回滚后的旧值；
    若没执行，读到的会是那条未提交的 'skipped'。
    （不能等到连接关闭后再断言——sqlite3 关闭连接时会隐式回滚，
    会把「没写 ROLLBACK」的缺陷掩盖掉。）
    """
    module = load_module()
    audit_id = insert_audit(db_path, msg_id="tx-1")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE youzan_webhook_events SET status = 'processed' WHERE id = ?",
            (audit_id,),
        )

    connection = sqlite3.connect(db_path, isolation_level=None)

    def boom() -> None:
        """先写一行再抛错，验证异常路径整体回滚。"""
        connection.execute(
            "UPDATE youzan_webhook_events SET status = 'skipped' WHERE id = ?",
            (audit_id,),
        )
        raise RuntimeError("模拟意外异常")

    with pytest.raises(RuntimeError):
        module.run_in_transaction(connection, boom)

    in_transaction = connection.execute(
        "SELECT status FROM youzan_webhook_events WHERE id = ?", (audit_id,)
    ).fetchone()[0]
    connection.close()

    assert in_transaction == "processed"
    assert read_audit(db_path, audit_id)["status"] == "processed"
