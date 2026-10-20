"""有赞 POINTS 死信核对脚本的测试。

数据库用真实 SQLite 临时库（不 mock DB），只有有赞 API 用假取数器替换：
本文件只验证核对口径与写库边界，不验证网络。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "reconcile_youzan_points_dead_letters.py"
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

MEMBER_BALANCE_DDL = """
CREATE TABLE IF NOT EXISTS member_balance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    is_member INTEGER NOT NULL DEFAULT 0,
    card_alias TEXT NOT NULL DEFAULT '',
    card_no TEXT NOT NULL DEFAULT '',
    card_status TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    stored_value_fen INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    youzan_points_base INTEGER NOT NULL DEFAULT 0
);
"""

POINTS_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS points_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def load_module() -> ModuleType:
    """按路径加载被测脚本模块。"""
    spec = importlib.util.spec_from_file_location(
        "reconcile_youzan_points_dead_letters", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_payload(
    *,
    event_type: str = "POINTS",
    mobile: str = "13800138000",
    total: int = 500,
    unique_id: str = "u-1",
    yz_open_id: str = "ozid-1",
) -> str:
    """构造一条与生产结构一致的有赞 webhook 载荷。

    生产把业务体放在 `body.msg`（URL 编码的 JSON 字符串）里。
    """
    raw_msg = json.dumps(
        {
            "mobile": mobile,
            "total": total,
            "unique_id": unique_id,
            "yz_open_id": yz_open_id,
            "event_type": event_type,
        },
        ensure_ascii=False,
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


class FakePointsFetcher:
    """假的有赞积分取数器：只回放预置结果，不触网。"""

    def __init__(
        self,
        points: dict[str, int] | None = None,
        *,
        errors: dict[str, Exception] | None = None,
        missing: set[str] | None = None,
    ) -> None:
        self.points = points or {}
        self.errors = errors or {}
        self.missing = missing or set()
        self.calls: list[str] = []
        self.closed = False

    def prepare(self) -> None:
        """假取数器无需准备。"""
        return None

    async def fetch(self, mobile: str) -> int | None:
        """返回预置的有赞当前积分。"""
        self.calls.append(mobile)
        if mobile in self.errors:
            raise self.errors[mobile]
        if mobile in self.missing:
            return None
        return self.points.get(mobile)

    async def aclose(self) -> None:
        """记录连接已释放，便于断言脚本没有泄漏客户端。"""
        self.closed = True


class SlowPointsFetcher(FakePointsFetcher):
    """永远超时的假取数器，用于验证超时不被静默吞掉。"""

    async def fetch(self, mobile: str) -> int | None:
        """模拟长时间无响应。"""
        await asyncio.sleep(5)
        return 0


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """建立只含目标表的真实 SQLite 临时库。"""
    path = tmp_path / "bot.db"
    with sqlite3.connect(path) as connection:
        connection.execute(INBOX_DDL)
        connection.execute(MEMBER_BALANCE_DDL)
        connection.execute(POINTS_LEDGER_DDL)
    return path


def insert_inbox(
    db_path: Path,
    *,
    message_key: str = "youzan_webhook:yzuser_1",
    payload_json: str | None = None,
    status: str = "dead_letter",
    queue_name: str = "youzan_webhook",
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


def insert_member(
    db_path: Path,
    *,
    mobile: str,
    points: int = 1000,
    youzan_points_base: int = 1000,
    yz_open_id: str = "ozid-1",
) -> int:
    """写入一条会员余额账户，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO member_balance "
            "(customer_id, mobile, yz_open_id, points, youzan_points_base) "
            "VALUES ('c-1', ?, ?, ?, ?)",
            (mobile, yz_open_id, points, youzan_points_base),
        )
        return int(cursor.lastrowid or 0)


def read_inbox(db_path: Path, row_id: int) -> dict[str, object]:
    """读取一条 inbox 记录的关键字段。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, message_key, payload_json, status, attempt_count, "
            "lease_until, last_error, created_at "
            "FROM inbox_events WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def read_member(db_path: Path, mobile: str) -> dict[str, object] | None:
    """读取会员余额账户。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, mobile, points, youzan_points_base FROM member_balance "
            "WHERE mobile = ?",
            (mobile,),
        ).fetchone()
    return dict(row) if row is not None else None


def read_ledger_count(db_path: Path) -> int:
    """统计积分流水条数。"""
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute("SELECT COUNT(*) FROM points_ledger").fetchone()[0]
        )


def run_cli(
    capsys: pytest.CaptureFixture[str],
    fetcher: FakePointsFetcher,
    *args: str,
) -> tuple[int, dict]:
    """执行脚本 CLI 并解析 stdout 上的 JSON 报告。"""
    module = load_module()
    exit_code = module.main(list(args), points_fetcher=fetcher)
    captured = capsys.readouterr()
    assert captured.out.strip(), "stdout 必须输出 JSON 报告"
    return exit_code, json.loads(captured.out)


def test_current_points_supersede_old_event_and_get_archived(
    db_path: Path, capsys
) -> None:
    """有赞当前积分不低于旧事件总额时判定为 superseded 并归档。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000", points=1000, youzan_points_base=1000)
    before = read_inbox(db_path, row_id)
    fetcher = FakePointsFetcher({"13800138000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["status"] == "ok"
    assert report["confirmed"] == 1
    assert report["blocked"] == 0
    assert report["archived"] == 1
    assert report["checked_members"] == 1
    assert fetcher.closed is True

    after = read_inbox(db_path, row_id)
    assert after["status"] == "processed"
    assert after["last_error"] == "superseded_by_youzan_current_points"
    # 载荷、幂等键、创建时间不得改动
    assert after["payload_json"] == before["payload_json"]
    assert after["message_key"] == before["message_key"]
    assert after["created_at"] == before["created_at"]
    # 会员余额与积分流水都不得被本脚本改动
    member = read_member(db_path, "13800138000")
    assert member is not None
    assert member["points"] == 1000
    assert member["youzan_points_base"] == 1000
    assert read_ledger_count(db_path) == 0


def test_current_points_below_old_event_is_blocked_and_not_written(
    db_path: Path, capsys
) -> None:
    """有赞当前积分低于旧事件总额时必须拦下且不写库。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000", points=1000, youzan_points_base=1000)
    before = read_inbox(db_path, row_id)
    fetcher = FakePointsFetcher({"13800138000": 100})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["status"] == "blocked"
    assert report["confirmed"] == 0
    assert report["blocked"] == 1
    assert report["archived"] == 0
    assert report["rows"][0]["reason"] == "youzan_points_below_event_total"
    after = read_inbox(db_path, row_id)
    assert after["status"] == "dead_letter"
    assert after["last_error"] == before["last_error"]
    assert read_member(db_path, "13800138000")["youzan_points_base"] == 1000


def test_one_blocked_row_blocks_the_whole_batch(db_path: Path, capsys) -> None:
    """只要有一条 blocked，整批都不写库，不做部分写入。"""
    good_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:good",
        payload_json=build_payload(total=500, unique_id="u-good"),
    )
    bad_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:bad",
        payload_json=build_payload(
            total=900, unique_id="u-bad", yz_open_id="ozid-2", mobile="13900139000"
        ),
    )
    insert_member(db_path, mobile="13800138000", yz_open_id="ozid-1")
    insert_member(db_path, mobile="13900139000", yz_open_id="ozid-2")
    fetcher = FakePointsFetcher({"13800138000": 900, "13900139000": 100})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["confirmed"] == 1
    assert report["blocked"] == 1
    assert report["archived"] == 0
    assert read_inbox(db_path, good_id)["status"] == "dead_letter"
    assert read_inbox(db_path, bad_id)["status"] == "dead_letter"


def test_empty_mobile_without_local_account_is_archived(db_path: Path, capsys) -> None:
    """空手机号且本地无可关联账户时只归档，不建档。"""
    row_id = insert_inbox(
        db_path, payload_json=build_payload(mobile="", total=178, yz_open_id="ozid-x")
    )
    fetcher = FakePointsFetcher()

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["confirmed"] == 1
    assert report["checked_members"] == 0
    assert report["by_category"] == {"archived_empty_mobile": 1}
    after = read_inbox(db_path, row_id)
    assert after["status"] == "processed"
    assert after["last_error"] == "archived_empty_mobile"
    # 不得凭空建出空手机号账户
    assert read_member(db_path, "") is None


def test_empty_mobile_with_local_account_is_blocked(db_path: Path, capsys) -> None:
    """空手机号但本地按 openid 存在账户时必须拦下。"""
    row_id = insert_inbox(
        db_path, payload_json=build_payload(mobile="", total=178, yz_open_id="ozid-1")
    )
    insert_member(
        db_path, mobile="", points=300, youzan_points_base=300, yz_open_id="ozid-1"
    )
    fetcher = FakePointsFetcher()

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["blocked"] == 1
    assert report["rows"][0]["reason"] == "empty_mobile_but_local_account_exists"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_member_without_local_account_is_archived_without_creating_account(
    db_path: Path, capsys
) -> None:
    """本地无账户的会员只归档，不建档也不改积分。"""
    row_id = insert_inbox(
        db_path,
        payload_json=build_payload(
            mobile="13700137000", total=831, unique_id="u-2", yz_open_id="ozid-2"
        ),
    )
    fetcher = FakePointsFetcher({"13700137000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["confirmed"] == 1
    assert report["by_category"] == {"archived_no_account": 1}
    after = read_inbox(db_path, row_id)
    assert after["status"] == "processed"
    assert after["last_error"] == "archived_no_account"
    # 绝不能因为归档而建出本地账户
    assert read_member(db_path, "13700137000") is None


def test_strict_policy_blocks_no_account_member_below_event_total(
    db_path: Path, capsys
) -> None:
    """strict 口径下本地无账户且有赞当前积分更低时拦下。"""
    row_id = insert_inbox(
        db_path,
        payload_json=build_payload(
            mobile="13700137000", total=831, unique_id="u-3", yz_open_id="ozid-3"
        ),
    )
    fetcher = FakePointsFetcher({"13700137000": 100})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["blocked"] == 1
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_replay_impact_matches_dead_letter_replay_tool(db_path: Path, capsys) -> None:
    """报告要能量化「回放旧事件会让会员少多少分」，口径与回放工具一致。"""
    insert_inbox(
        db_path,
        message_key="youzan_webhook:a",
        payload_json=build_payload(total=500, unique_id="u-a"),
    )
    insert_inbox(
        db_path,
        message_key="youzan_webhook:b",
        payload_json=build_payload(
            total=800, unique_id="u-b", mobile="13900139000", yz_open_id="ozid-2"
        ),
    )
    insert_member(db_path, mobile="13800138000", points=1200, youzan_points_base=1200)
    insert_member(
        db_path,
        mobile="13900139000",
        points=900,
        youzan_points_base=900,
        yz_open_id="ozid-2",
    )
    fetcher = FakePointsFetcher({"13800138000": 1200, "13900139000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path))

    assert exit_code == 0
    assert report["replay_impact"]["backward_rows"] == 2
    assert report["replay_impact"]["backward_members"] == 2
    assert report["replay_impact"]["backward_points_total"] == 800
    # 只读核对不得改动任何账户
    assert read_member(db_path, "13800138000")["points"] == 1200


def test_api_failure_is_reported_and_not_silently_ignored(
    db_path: Path, capsys
) -> None:
    """有赞查询失败必须显式出现在报告里，并把相关死信拦下。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher(
        {}, errors={"13800138000": RuntimeError("有赞网关调用失败")}
    )

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["api_errors"]
    assert "有赞网关调用失败" in report["api_errors"][0]["error"]
    assert report["blocked"] == 1
    assert report["rows"][0]["reason"] == "youzan_api_error"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_api_timeout_is_reported_and_blocks(db_path: Path, capsys) -> None:
    """有赞查询超时必须被记录为失败，而不是当成 0 分处理。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = SlowPointsFetcher()

    exit_code, report = run_cli(
        capsys,
        fetcher,
        "--db",
        str(db_path),
        "--apply",
        "--api-timeout",
        "0.05",
    )

    assert exit_code != 0
    assert report["api_errors"]
    assert "timeout_after" in report["api_errors"][0]["error"]
    assert report["blocked"] == 1
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_missing_youzan_data_is_blocked_not_treated_as_zero(
    db_path: Path, capsys
) -> None:
    """有赞侧查不到积分数据时按未知处理，不得当成 0 分放行。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({}, missing={"13800138000"})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["blocked"] == 1
    assert report["rows"][0]["reason"] == "youzan_points_unknown"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_dry_run_does_not_write_database(db_path: Path, capsys) -> None:
    """dry-run 只出报告，不改库。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({"13800138000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path))

    assert exit_code == 0
    assert report["mode"] == "dry-run"
    assert report["confirmed"] == 1
    assert report["archived"] == 0
    assert report["would_archive"] == 1
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_repeated_apply_is_idempotent(db_path: Path, capsys) -> None:
    """重复 apply 不会重复归档，也不会改动已归档行。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({"13800138000": 900})

    first_code, first_report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")
    second_code, second_report = run_cli(
        capsys, fetcher, "--db", str(db_path), "--apply"
    )

    assert first_code == 0
    assert second_code == 0
    assert first_report["archived"] == 1
    assert second_report["dead_letter_total"] == 0
    assert second_report["archived"] == 0
    assert second_report["confirmed"] == 0
    after = read_inbox(db_path, row_id)
    assert after["status"] == "processed"
    assert after["last_error"] == "superseded_by_youzan_current_points"


def test_report_masks_phone_numbers(db_path: Path, capsys) -> None:
    """报告里的手机号必须脱敏。"""
    insert_inbox(db_path, payload_json=build_payload(mobile="13800138000", total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({"13800138000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path))

    assert exit_code == 0
    text = json.dumps(report, ensure_ascii=False)
    assert "13800138000" not in text
    assert "138****8000" in text


def test_report_structure_is_stable(db_path: Path, capsys) -> None:
    """同一份数据两次 dry-run 的报告内容一致（结构稳定）。"""
    insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({"13800138000": 900})

    _, first = run_cli(capsys, fetcher, "--db", str(db_path))
    _, second = run_cli(capsys, fetcher, "--db", str(db_path))

    assert first["rows"] == second["rows"]
    assert first["summary"] == second["summary"]
    assert first["by_category"] == second["by_category"]
    assert first["by_reason"] == second["by_reason"]


def test_non_points_dead_letter_is_out_of_scope(db_path: Path, capsys) -> None:
    """非 POINTS 死信不在本次范围内，不写库也不拦截。"""
    row_id = insert_inbox(
        db_path,
        message_key="youzan_webhook:scrm",
        payload_json=build_payload(event_type="SCRM_CUSTOMER_EVENT"),
    )
    fetcher = FakePointsFetcher()

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["dead_letter_total"] == 1
    assert report["points_dead_letter_total"] == 0
    assert report["out_of_scope"][0]["event_type"] == "SCRM_CUSTOMER_EVENT"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_broken_payload_is_blocked(db_path: Path, capsys) -> None:
    """载荷不可解析的死信必须拦下，不得静默跳过。"""
    row_id = insert_inbox(db_path, payload_json="{not-json")
    fetcher = FakePointsFetcher()

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["blocked"] == 1
    assert report["rows"][0]["reason"] == "payload_invalid"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_other_queue_is_untouched(db_path: Path, capsys) -> None:
    """非 youzan_webhook 队列的死信不受影响。"""
    row_id = insert_inbox(db_path, queue_name="wecom", message_key="wecom:msg-1")
    fetcher = FakePointsFetcher()

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code == 0
    assert report["dead_letter_total"] == 0
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_production_path_is_rejected_without_allow_production(
    db_path: Path, capsys
) -> None:
    """指向生产路径时必须显式传 --allow-production。"""
    module = load_module()
    assert module.looks_like_production_path(
        "/opt/apps/yunxi-bakery/backend/data/bot.db"
    )
    assert not module.looks_like_production_path(str(db_path))

    exit_code, report = run_cli(
        capsys,
        FakePointsFetcher(),
        "--db",
        "/opt/apps/yunxi-bakery/backend/data/bot.db",
        "--apply",
    )

    assert exit_code == module.EXIT_REJECTED
    assert report["status"] == "rejected"
    assert "--allow-production" in report["error"]


def test_allow_production_still_requires_existing_file(db_path: Path, capsys) -> None:
    """带 --allow-production 时防呆放行，但仍需目标文件真实存在。"""
    module = load_module()
    guard = module.evaluate_target_guard(db_path, allow_production=True)
    assert guard["production_like"] is False
    assert guard["allow_production"] is True

    exit_code, report = run_cli(
        capsys,
        FakePointsFetcher(),
        "--db",
        "/opt/apps/yunxi-bakery/backend/data/bot.db",
        "--apply",
        "--allow-production",
    )

    assert exit_code == module.EXIT_REJECTED
    assert "不存在" in report["error"]


def test_app_root_falls_back_to_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脚本被复制到临时目录时，应能从工作目录找到后端代码根目录。"""
    module = load_module()
    client_path = tmp_path / "app" / "service" / "youzan" / "client.py"
    client_path.parent.mkdir(parents=True)
    client_path.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert module.resolve_app_root("") == tmp_path.resolve()
    assert module.resolve_app_root(str(tmp_path)) == tmp_path.resolve()


def test_strict_policy_blocks_member_whose_youzan_points_decreased(
    db_path: Path, capsys
) -> None:
    """默认 strict 口径：有赞当前积分低于旧事件总额时必须拦下。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=1891))
    insert_member(db_path, mobile="13800138000", points=941, youzan_points_base=941)
    fetcher = FakePointsFetcher({"13800138000": 941})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["blocked"] == 1
    assert report["rows"][0]["reason"] == "youzan_points_below_event_total"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_sync_ok_policy_archives_stale_event_when_local_anchor_matches(
    db_path: Path, capsys
) -> None:
    """本地锚点已等于有赞当前积分时，过期事件可按 stale 归档。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=1891))
    insert_member(db_path, mobile="13800138000", points=941, youzan_points_base=941)
    fetcher = FakePointsFetcher({"13800138000": 941})

    exit_code, report = run_cli(
        capsys,
        fetcher,
        "--db",
        str(db_path),
        "--apply",
        "--stale-policy",
        "sync-ok",
    )

    assert exit_code == 0
    assert report["confirmed"] == 1
    assert report["by_category"] == {"stale": 1}
    after = read_inbox(db_path, row_id)
    assert after["status"] == "processed"
    assert after["last_error"] == "stale_youzan_points_decreased"
    # 会员余额与流水都不得被改动
    member = read_member(db_path, "13800138000")
    assert member is not None
    assert member["points"] == 941
    assert member["youzan_points_base"] == 941
    assert read_ledger_count(db_path) == 0


def test_sync_ok_policy_still_blocks_when_local_anchor_is_out_of_sync(
    db_path: Path, capsys
) -> None:
    """本地锚点与有赞不一致时，sync-ok 口径也不得放行。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=1891))
    insert_member(db_path, mobile="13800138000", points=500, youzan_points_base=500)
    fetcher = FakePointsFetcher({"13800138000": 941})

    exit_code, report = run_cli(
        capsys,
        fetcher,
        "--db",
        str(db_path),
        "--apply",
        "--stale-policy",
        "sync-ok",
    )

    assert exit_code != 0
    assert report["blocked"] == 1
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"


def test_missing_table_is_reported(db_path: Path, capsys) -> None:
    """目标库缺少必要表时必须报错退出，不得静默通过。"""
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE member_balance")
    module = load_module()

    exit_code, report = run_cli(capsys, FakePointsFetcher(), "--db", str(db_path))

    assert exit_code == module.EXIT_FAILED
    assert "member_balance" in report["error"]


def test_extract_youzan_points_reads_official_response_shape() -> None:
    """官方响应形状 `data.point` 必须能解析出当前积分。"""
    module = load_module()
    payload = {
        "trace_id": "yz7-xxx",
        "code": 200,
        "data": {"point": 16376},
        "success": True,
        "message": "successful",
    }
    assert module.extract_youzan_points(payload) == 16376
    # 真实积分为 0 时也必须读成 0，而不是「查不到」
    zero_payload = {"code": 200, "data": {"point": 0}, "success": True}
    assert module.extract_youzan_points(zero_payload) == 0
    assert module.extract_youzan_points({}) is None
    assert module.extract_youzan_points({"data": {}}) is None


def test_detect_youzan_error_exposes_gateway_and_business_errors() -> None:
    """网关错误与业务错误都必须被识别出来，不得当成「查不到数据」。"""
    module = load_module()
    assert module.detect_youzan_error(
        {"gw_err_resp": {"err_code": 4005, "err_msg": "非法的API"}}
    ).startswith("gateway_error")
    assert module.detect_youzan_error(
        {"code": 141500101, "success": False, "message": "invalid params"}
    ).startswith("api_error")
    assert (
        module.detect_youzan_error({"code": 200, "data": {"point": 1}, "success": True})
        == ""
    )


def test_youzan_api_identity_is_recorded_in_report(db_path: Path, capsys) -> None:
    """报告必须记录所用的有赞积分接口，便于审计复现。"""
    insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher({"13800138000": 900})

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path))

    assert exit_code == 0
    assert report["youzan_api"] == {
        "name": "youzan.crm.customer.points.get",
        "version": "1.0.0",
        "account_type": 2,
    }


def test_api_error_from_youzan_is_not_treated_as_zero_points(
    db_path: Path, capsys
) -> None:
    """有赞返回业务错误时必须记为 api_error 并拦下，不得当成 0 分。"""
    row_id = insert_inbox(db_path, payload_json=build_payload(total=500))
    insert_member(db_path, mobile="13800138000")
    fetcher = FakePointsFetcher(
        {}, errors={"13800138000": RuntimeError("api_error: code=141500101")}
    )

    exit_code, report = run_cli(capsys, fetcher, "--db", str(db_path), "--apply")

    assert exit_code != 0
    assert report["rows"][0]["youzan_current_points"] is None
    assert report["rows"][0]["reason"] == "youzan_api_error"
    assert read_inbox(db_path, row_id)["status"] == "dead_letter"
