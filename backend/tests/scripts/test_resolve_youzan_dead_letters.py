"""死信回放与历史审计失败处置脚本的测试（真实 SQLite 临时库，不 mock 数据库）。"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "resolve_youzan_dead_letters.py"
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
)
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
)
"""

BEIJING_TZ = timezone(timedelta(hours=8))


def load_module() -> ModuleType:
    """按路径加载被测脚本模块。"""
    spec = importlib.util.spec_from_file_location(
        "resolve_youzan_dead_letters", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_payload(
    event_type: str = "POINTS", mobile: str = "13800138000", total: int = 100
) -> str:
    """构造一条与生产结构一致的有赞 webhook 载荷。

    生产把业务体放在 `body.msg`（URL 编码的 JSON 字符串）里。
    """
    raw_msg = json.dumps(
        {"mobile": mobile, "total": total, "unique_id": "u-1"}, ensure_ascii=False
    )
    return json.dumps(
        {
            "event_type": event_type,
            "msg_id": "yzuser_1537746756265271296",
            "buyer_id": "",
            "audit_id": None,
            "body": {"msg": urllib.parse.quote(raw_msg, safe="")},
        },
        ensure_ascii=False,
    )


def timestamp_days_ago(days: int) -> str:
    """生成相对当前时间的历史时间戳。"""
    moment = datetime.now(BEIJING_TZ) - timedelta(days=days)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """建立只含两张目标表的真实 SQLite 临时库。"""
    path = tmp_path / "bot.db"
    with sqlite3.connect(path) as connection:
        connection.execute(INBOX_DDL)
        connection.execute(AUDIT_DDL)
    return path


def insert_inbox(
    db_path: Path,
    *,
    queue_name: str = "youzan_webhook",
    status: str = "dead_letter",
    payload_json: str | None = None,
    message_key: str = "youzan_webhook:yzuser_1",
    last_error: str = "'NoneType' object has no attribute 'in_transaction'",
    created_at: str = "2026-08-14 00:47:50",
) -> int:
    """写入一条 inbox 记录，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO inbox_events "
            "(queue_name, message_key, payload_json, status, attempt_count, "
            "lease_until, next_attempt_at, last_error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 5, '2026-09-05 02:49:37', '2026-09-05 02:49:37', "
            "?, ?, '2026-09-05 02:49:37')",
            (
                queue_name,
                message_key,
                payload_json if payload_json is not None else build_payload(),
                status,
                last_error,
                created_at,
            ),
        )
        return int(cursor.lastrowid or 0)


def insert_audit_failed(
    db_path: Path,
    *,
    msg_id: str = "2026052515301182jHi",
    business_type: str = "item",
    business_key: str = "2026052515301182jHi",
    error_type: str = "ValueError",
    error_message: str = "invalid literal for int() with base 10: '2026052515301182jHi'",
    received_at: str | None = None,
) -> int:
    """写入一条 failed 审计记录，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO youzan_webhook_events "
            "(msg_id, event_type, business_type, business_key, status, http_status, "
            "process_stage, error_type, error_message, received_at) "
            "VALUES (?, 'ITEM_INFO', ?, ?, 'failed', 200, 'item_failed', ?, ?, ?)",
            (
                msg_id,
                business_type,
                business_key,
                error_type,
                error_message,
                received_at if received_at is not None else timestamp_days_ago(90),
            ),
        )
        return int(cursor.lastrowid or 0)


def read_inbox(db_path: Path, row_id: int) -> dict[str, object]:
    """读取一条 inbox 记录的关键字段。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, message_key, payload_json, status, attempt_count, "
            "lease_until, next_attempt_at, last_error, created_at "
            "FROM inbox_events WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def read_audit(db_path: Path, row_id: int) -> dict[str, object]:
    """读取一条审计记录的关键字段。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, msg_id, status, error_type, error_message, process_stage "
            "FROM youzan_webhook_events WHERE id = ?",
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
    """dry-run 只出报告，不改库。"""
    row_id = insert_inbox(db_path)

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    assert report["mode"] == "dry-run"
    assert report["inbox"]["eligible"] == 1
    assert report["inbox"]["replayed"] == 0
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_apply_replays_eligible_dead_letter_to_received(db_path: Path, capsys) -> None:
    """有效死信被回放成 received，并重置重试计数。"""
    row_id = insert_inbox(db_path)
    before = read_inbox(db_path, row_id)

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["inbox"]["eligible"] == 1
    assert report["inbox"]["replayed"] == 1
    assert report["summary"]["committed"] is True

    after = read_inbox(db_path, row_id)
    assert after["status"] == "received"
    assert after["attempt_count"] == 0
    assert after["last_error"] == ""
    assert after["lease_until"] is None
    # next_attempt_at 是 NOT NULL 列，复位为「立即可认领」的当前时间
    assert after["next_attempt_at"] is not None
    datetime.strptime(str(after["next_attempt_at"]), "%Y-%m-%d %H:%M:%S")
    # 幂等键与原始载荷、创建时间不得改动
    assert after["message_key"] == before["message_key"]
    assert after["payload_json"] == before["payload_json"]
    assert after["created_at"] == before["created_at"]


def test_repeated_apply_is_idempotent(db_path: Path, capsys) -> None:
    """重复 apply 不会重复回放已 received 的记录。"""
    row_id = insert_inbox(db_path)

    first_code, first_report = run_cli(capsys, "--db", str(db_path), "--apply")
    second_code, second_report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert first_code == 0
    assert second_code == 0
    assert first_report["inbox"]["replayed"] == 1
    assert second_report["inbox"]["dead_letter_total"] == 0
    assert second_report["inbox"]["eligible"] == 0
    assert second_report["inbox"]["replayed"] == 0
    assert read_inbox(db_path, row_id)["status"] == "received"
    assert read_inbox(db_path, row_id)["attempt_count"] == 0


def test_invalid_payload_stays_dead_letter_and_counts_as_skipped(
    db_path: Path, capsys
) -> None:
    """载荷不可解析的死信保持 dead_letter 并计入 skipped_invalid。"""
    broken_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:broken",
        payload_json="{not-json",
    )
    missing_body_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:no-body",
        payload_json=json.dumps({"event_type": "POINTS"}),
    )

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["inbox"]["eligible"] == 0
    assert report["inbox"]["skipped_invalid"] == 2
    assert report["inbox"]["replayed"] == 0
    reasons = {item["id"]: item["reason"] for item in report["inbox"]["skipped"]}
    assert reasons[broken_id].startswith("invalid_json")
    assert reasons[missing_body_id] == "missing_body"
    assert read_inbox(db_path, broken_id)["status"] == "dead_letter"
    assert read_inbox(db_path, missing_body_id)["status"] == "dead_letter"


def test_other_queue_is_untouched(db_path: Path, capsys) -> None:
    """非 youzan_webhook 队列的死信不受影响。"""
    other_id = insert_inbox(
        db_path,
        queue_name="wecom",
        message_key="wecom:msg-1",
    )

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["inbox"]["dead_letter_total"] == 0
    assert report["inbox"]["replayed"] == 0
    assert read_inbox(db_path, other_id)["status"] == "dead_letter"
    assert read_inbox(db_path, other_id)["attempt_count"] == 5


def test_production_path_is_rejected_without_allow_production(
    db_path: Path, capsys
) -> None:
    """指向生产路径时必须显式传 --allow-production。"""
    module = load_module()
    assert module.looks_like_production_path("/opt/apps/yunxibakebot/data/bot.db")
    assert module.looks_like_production_path(
        "/opt/apps/yunxi-bakery/backend/data/bot.db"
    )
    assert not module.looks_like_production_path(str(db_path))

    exit_code, report = run_cli(
        capsys, "--db", "/opt/apps/yunxibakebot/data/bot.db", "--apply"
    )

    assert exit_code == module.EXIT_REJECTED
    assert report["status"] == "rejected"
    assert "--allow-production" in report["error"]


def test_allow_production_passes_guard_for_existing_file(db_path: Path, capsys) -> None:
    """带 --allow-production 时防呆放行，但仍需目标文件真实存在。"""
    module = load_module()
    guard = module.evaluate_target_guard(db_path, allow_production=True)
    assert guard["production_like"] is False
    assert guard["allow_production"] is True

    exit_code, report = run_cli(
        capsys,
        "--db",
        "/opt/apps/yunxi-bakery/backend/data/bot.db",
        "--apply",
        "--allow-production",
    )
    assert exit_code == module.EXIT_REJECTED
    assert "不存在" in report["error"]


def test_audit_failed_not_modified_by_default(db_path: Path, capsys) -> None:
    """默认不改动 failed 审计记录，只读统计。"""
    row_id = insert_audit_failed(db_path)

    exit_code, report = run_cli(capsys, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["audit_failed"]["total"] == 1
    assert report["audit_failed"]["resolved"] == 0
    assert report["audit_failed"]["would_resolve"] == 0
    assert report["audit_failed"]["items"][0]["action"] == "report_only"
    row = read_audit(db_path, row_id)
    assert row["status"] == "failed"
    assert row["error_type"] == "ValueError"
    assert row["error_message"].startswith("invalid literal for int()")


def test_audit_failed_marked_skipped_only_with_flag(db_path: Path, capsys) -> None:
    """带 --resolve-audit-failed 才把历史失败审计标记为 skipped。"""
    row_id = insert_audit_failed(db_path)

    exit_code, report = run_cli(
        capsys, "--db", str(db_path), "--resolve-audit-failed", "--apply"
    )

    assert exit_code == 0
    assert report["audit_failed"]["resolved"] == 1
    assert report["audit_failed"]["items"][0]["action"] == "resolved"
    row = read_audit(db_path, row_id)
    assert row["status"] == "skipped"
    assert row["error_type"] == "historical_invalid_payload"
    assert row["error_message"].startswith("[historical_invalid_payload] ")
    # 原始错误信息必须保留，不得删除
    assert "invalid literal for int()" in row["error_message"]
    # 原始处置阶段保留，不覆盖历史事实
    assert row["process_stage"] == "item_failed"


def test_audit_resolution_can_skip_inbox_replay(db_path: Path, capsys) -> None:
    """审计-only 模式不得误回放 inbox 死信。"""
    inbox_id = insert_inbox(db_path)
    audit_id = insert_audit_failed(db_path)

    exit_code, report = run_cli(
        capsys,
        "--db",
        str(db_path),
        "--resolve-audit-failed",
        "--skip-inbox",
        "--apply",
    )

    assert exit_code == 0
    assert report["inbox"]["replayed"] == 0
    assert report["inbox"]["skipped_by_inbox_flag"] is True
    assert read_inbox(db_path, inbox_id)["status"] == "dead_letter"
    assert read_audit(db_path, audit_id)["status"] == "skipped"


def test_skip_inbox_requires_audit_resolution(db_path: Path) -> None:
    """单独 --skip-inbox 没有可处理对象，应拒绝而不是静默成功。"""
    module = load_module()
    exit_code = module.main(["--db", str(db_path), "--skip-inbox", "--apply"])
    assert exit_code == 2


def test_audit_failed_recent_row_is_guarded(db_path: Path, capsys) -> None:
    """非历史失败记录被防呆拦下，不做处置。"""
    row_id = insert_audit_failed(
        db_path, msg_id="recent-1", received_at=timestamp_days_ago(1)
    )

    exit_code, report = run_cli(
        capsys, "--db", str(db_path), "--resolve-audit-failed", "--apply"
    )

    assert exit_code == 0
    assert report["audit_failed"]["eligible"] == 0
    assert report["audit_failed"]["skipped_by_guard"] == 1
    assert report["audit_failed"]["items"][0]["action"] == "skipped_by_guard"
    assert read_audit(db_path, row_id)["status"] == "failed"


def test_report_masks_phone_numbers(db_path: Path, capsys) -> None:
    """报告中的手机号必须脱敏。"""
    insert_inbox(
        db_path,
        message_key="youzan_webhook:yzuser_1",
        payload_json=build_payload(mobile="13800138000"),
        last_error="member 13800138000 mirror failed",
    )
    insert_audit_failed(
        db_path,
        msg_id="mask-1",
        business_key="13800138000",
        error_message="mobile 13800138000 unknown",
    )

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    text = json.dumps(report, ensure_ascii=False)
    assert "13800138000" not in text
    assert "138****8000" in text
    assert report["inbox"]["by_last_error"] == {"member 138****8000 mirror failed": 1}
    assert report["audit_failed"]["items"][0]["business_key"] == "138****8000"


def test_report_structure_is_stable(db_path: Path, capsys) -> None:
    """同一份数据两次 dry-run 的报告内容一致（结构稳定）。"""
    insert_inbox(db_path)
    insert_audit_failed(db_path)

    _, first = run_cli(capsys, "--db", str(db_path))
    _, second = run_cli(capsys, "--db", str(db_path))

    assert first["inbox"] == second["inbox"]
    assert first["audit_failed"] == second["audit_failed"]
    assert first["summary"] == second["summary"]


def test_event_type_scope_limits_replay(db_path: Path, capsys) -> None:
    """--event-type 只回放列出的事件类型，其余进入 out_of_scope。"""
    points_id = insert_inbox(
        db_path, message_key="youzan_webhook:points-1", payload_json=build_payload()
    )
    scrm_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:scrm-1",
        payload_json=build_payload(event_type="SCRM_CUSTOMER_EVENT"),
    )

    exit_code, report = run_cli(
        capsys,
        "--db",
        str(db_path),
        "--event-type",
        "SCRM_CUSTOMER_EVENT",
        "--apply",
    )

    assert exit_code == 0
    assert report["inbox"]["eligible"] == 1
    assert report["inbox"]["out_of_scope"] == 1
    assert report["inbox"]["replayed"] == 1
    assert read_inbox(db_path, scrm_id)["status"] == "received"
    assert read_inbox(db_path, points_id)["status"] == "dead_letter"


def test_points_impact_reports_backward_balance_movement(db_path: Path, capsys) -> None:
    """只读预估：旧 POINTS 事件会把会员积分余额改小。"""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS member_balance ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, mobile TEXT, "
            "points INTEGER DEFAULT 0, youzan_points_base INTEGER DEFAULT 0)"
        )
        connection.execute(
            "INSERT INTO member_balance (mobile, points, youzan_points_base) "
            "VALUES ('13800138000', 500, 500)"
        )
    insert_inbox(db_path, payload_json=build_payload(mobile="13800138000"))

    exit_code, report = run_cli(capsys, "--db", str(db_path))

    assert exit_code == 0
    impact = report["points_impact"]
    assert impact["available"] is True
    assert impact["checked_points_events"] == 1
    assert impact["backward"] == 1
    assert impact["backward_points_total"] == 400
    assert impact["samples"][0]["delta"] == -400
    assert impact["samples"][0]["mobile"] == "138****8000"
