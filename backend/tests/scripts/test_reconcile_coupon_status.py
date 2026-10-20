"""券状态冲突对账脚本的测试（真实 SQLite 临时库 + 假有赞 API，不 mock 数据库）。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import aiosqlite
import pytest

from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.service.coupon.rules import apply_row_validity, is_coupon_available

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "reconcile_coupon_status.py"
)

COUPON_INVENTORY_DDL = """
CREATE TABLE IF NOT EXISTS coupon_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL DEFAULT '',
    coupon_group_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    order_no TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    value_fen INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'webhook'
        CHECK(source IN ('webhook', 'import', 'local', 'order')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    template_id TEXT NOT NULL DEFAULT '',
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    deducted_fen INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT NOT NULL DEFAULT '',
    refunded_at TEXT NOT NULL DEFAULT '',
    cycle_no INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_inventory_cycle
    ON coupon_inventory (coupon_id, status, mobile, cycle_no);
"""

MOBILE = "18911163140"
OTHER_MOBILE = "13167327393"
COUPON_ID = "38863608300"
EXPIRED_COUPON_ID = "66865484667"
GROUP_ID = "32035241"
EXPIRED_GROUP_ID = "32035222"
TAKE_AT = 1727341443000
USED_AT = 1727427843000
EXPIRE_AT = 1728000000000
TEMPLATE_VALID_END = 4102444800000
USED_ORDER_NO = "E20261012184512057906211"
NOW_TEXT = "2026-10-20 12:00:00"


def load_module() -> ModuleType:
    """按路径加载被测脚本模块。"""
    spec = importlib.util.spec_from_file_location(
        "reconcile_coupon_status", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module() -> ModuleType:
    """被测脚本模块（模块级复用，避免重复导入）。"""
    return load_module()


class FakeMemberApi:
    """假的有赞会员账务域客户端：只回放测试预置的券与券模板。"""

    def __init__(
        self,
        coupons_by_mobile: dict[str, list[dict]] | None = None,
        details_by_group: dict[str, dict] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._coupons = coupons_by_mobile or {}
        self._details = details_by_group or {}
        self._error = error
        self.coupon_calls: list[str] = []
        self.detail_calls: list[str] = []

    async def list_customer_coupons(self, mobile: str) -> list[dict]:
        """按手机号返回预置买家券（合并态）。"""
        self.coupon_calls.append(mobile)
        if self._error is not None:
            raise self._error
        return list(self._coupons.get(mobile, []))

    async def get_coupon_group_detail(self, coupon_group_id: str) -> dict:
        """按券模板 ID 返回预置模板详情。"""
        self.detail_calls.append(coupon_group_id)
        return dict(self._details.get(coupon_group_id, {}))


class FakeYouzanClient:
    """假的有赞云客户端：只回放按状态查询的原始返回集。"""

    def __init__(self, invalid_by_mobile: dict[str, list[dict]] | None = None) -> None:
        self._invalid = invalid_by_mobile or {}
        self.calls: list[tuple[str, str, dict]] = []

    async def call_api(self, api_name: str, version: str, params: dict) -> dict:
        """按请求体里的 status 返回预置券数组。"""
        self.calls.append((api_name, version, params))
        if str(params.get("status", "")) == "INVALID":
            return {"data": list(self._invalid.get(str(params.get("mobile", "")), []))}
        return {"data": []}


def build_probe(
    module: ModuleType,
    member_api: FakeMemberApi,
    client: FakeYouzanClient,
):
    """用真实探针类 + 假客户端组装被测探针。"""
    return module.YouzanCouponProbe(member_api, client)


def build_used_coupon(
    coupon_id: str = COUPON_ID,
    group_id: str = GROUP_ID,
) -> dict:
    """构造一条「有赞已使用」的券。"""
    return {
        "id": coupon_id,
        "coupon_id": coupon_id,
        "coupon_group_id": group_id,
        "title": "20元优惠券",
        "youzan_coupon_status": "USED",
        "is_used": 1,
        "take_at": TAKE_AT,
        "used_at": USED_AT,
        "used_in_order_no": USED_ORDER_NO,
        "valid_start_at": TAKE_AT,
        "expire_at": EXPIRE_AT,
        "value": 2000,
    }


def build_valid_coupon(
    coupon_id: str = COUPON_ID,
    group_id: str = GROUP_ID,
) -> dict:
    """构造一条「有赞当前有效」的券。"""
    return {
        "id": coupon_id,
        "coupon_id": coupon_id,
        "coupon_group_id": group_id,
        "title": "20元优惠券",
        "youzan_coupon_status": "VALID",
        "is_used": 0,
        "take_at": TAKE_AT,
        "valid_start_at": TAKE_AT,
        "expire_at": EXPIRE_AT,
        "value": 2000,
    }


def build_expired_coupon(
    coupon_id: str = EXPIRED_COUPON_ID,
    group_id: str = EXPIRED_GROUP_ID,
    *,
    with_expire_at: bool = True,
) -> dict:
    """构造一条「有赞已失效未使用」的券（只出现在 INVALID 原始返回集里）。"""
    coupon = {
        "id": coupon_id,
        "coupon_id": coupon_id,
        "coupon_group_id": group_id,
        "title": "10元优惠券",
        "is_used": 0,
        "take_at": TAKE_AT,
        "value": 1000,
    }
    if with_expire_at:
        coupon["expire_at"] = EXPIRE_AT
    return coupon


def build_template_detail(
    group_id: str = GROUP_ID,
    *,
    value_fen: int = 2000,
    threshold_fen: int = 5000,
) -> dict:
    """构造一份与有赞券模板详情一致形状的模板。"""
    return {
        "coupon_group_id": group_id,
        "title": "20元优惠卷" if value_fen >= 2000 else "10元优惠卷",
        "denominations": value_fen,
        "condition": threshold_fen,
        "preferential_type": 1,
        "valid_start_time": TAKE_AT,
        "valid_end_time": TEMPLATE_VALID_END,
    }


def build_details() -> dict[str, dict]:
    """两个券模板的详情（20 元券与 10 元券）。"""
    return {
        GROUP_ID: build_template_detail(GROUP_ID),
        EXPIRED_GROUP_ID: build_template_detail(
            EXPIRED_GROUP_ID, value_fen=1000, threshold_fen=3000
        ),
    }


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """建立只含券库存表的真实 SQLite 临时库。"""
    path = tmp_path / "bot.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(COUPON_INVENTORY_DDL)
    return path


def insert_coupon(
    db_path: Path,
    *,
    coupon_id: str = COUPON_ID,
    group_id: str = GROUP_ID,
    mobile: str = MOBILE,
    status: str = "TAKE",
    source: str = "webhook",
    occurred_at: str = "2024-09-26 17:04:03",
    created_at: str = "2024-09-26 17:04:03",
    cycle_no: int = 0,
) -> int:
    """写入一条骨架券库存行，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO coupon_inventory (coupon_id, coupon_group_id, customer_id, "
            "mobile, status, order_no, title, value_fen, detail_json, source, "
            "occurred_at, created_at, template_id, valid_from, valid_until, cycle_no) "
            "VALUES (?, ?, '', ?, ?, '', '', 0, '{}', ?, ?, ?, '', '', '', ?)",
            (
                coupon_id,
                group_id,
                mobile,
                status,
                source,
                occurred_at,
                created_at,
                cycle_no,
            ),
        )
        return int(cursor.lastrowid or 0)


def read_coupon(db_path: Path, row_id: int) -> dict:
    """按 id 读取券库存行的全部业务列。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, coupon_id, coupon_group_id, mobile, status, order_no, title, "
            "value_fen, detail_json, source, occurred_at, created_at, template_id, "
            "valid_from, valid_until, consumed_at, cycle_no "
            "FROM coupon_inventory WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def read_rows(db_path: Path) -> list[dict]:
    """按 id 升序读取全部券库存行。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, coupon_id, mobile, status, order_no, title, value_fen, "
            "source, occurred_at, template_id, valid_from, valid_until, consumed_at, "
            "cycle_no FROM coupon_inventory ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


async def read_latest_state(db_path: Path, coupon_id: str, mobile: str) -> dict | None:
    """按仓储口径读取券的最新状态行。"""
    async with aiosqlite.connect(db_path) as connection:
        connection.row_factory = aiosqlite.Row
        repo = CouponInventoryRepo(connection)
        return await repo.get_latest_state(coupon_id, mobile, authority="youzan")


def production_like_db_path(tmp_path: Path) -> Path:
    """构造一个「长得像生产部署目录」的真实数据库路径。"""
    path = tmp_path / "opt" / "apps" / "yunxi-bakery" / "backend" / "data" / "bot.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path):
        pass
    return path


def run_script(
    module: ModuleType,
    db_path: Path,
    probe,
    *,
    apply: bool = True,
    extra_args: list[str] | None = None,
) -> tuple[int, dict]:
    """执行脚本并返回 (退出码, 报告)。"""
    output_path = db_path.parent / "report.json"
    argv = ["--db", str(db_path), "--output", str(output_path)]
    if apply:
        argv.append("--apply")
    argv.extend(extra_args or [])
    exit_code = asyncio.run(module.async_main(argv, probe=probe))
    report = json.loads(output_path.read_text(encoding="utf-8"))
    return exit_code, report


def test_used_coupon_gets_local_consume_fact(module, db_path: Path) -> None:
    """有赞已使用 + 本地记持有：新增本地 CONSUME 事实，历史 TAKE 行不动。"""
    row_id = insert_coupon(db_path)
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    client = FakeYouzanClient()
    probe = build_probe(module, member_api, client)

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["consume_fact_inserted"] == 1
    assert report["summary"]["inserted"] == 1
    rows = read_rows(db_path)
    assert len(rows) == 2
    # 历史 TAKE 行原样保留：状态、来源、券名都不动
    take_row = read_coupon(db_path, row_id)
    assert take_row["status"] == "TAKE"
    assert take_row["source"] == "webhook"
    assert take_row["title"] == ""
    # 新增的 CONSUME 事实行
    consume_row = next(row for row in rows if row["status"] == "CONSUME")
    assert consume_row["coupon_id"] == COUPON_ID
    assert consume_row["order_no"] == USED_ORDER_NO
    assert consume_row["title"] == "20元优惠券"
    assert consume_row["value_fen"] == 2000
    assert consume_row["template_id"] == GROUP_ID
    assert consume_row["valid_from"] == "2024-09-26"
    assert consume_row["valid_until"] == "2024-10-04"
    assert consume_row["occurred_at"] == "2024-09-27 17:04:03"
    assert consume_row["consumed_at"] == "2024-09-27 17:04:03"
    assert consume_row["source"] == "import"
    assert consume_row["cycle_no"] == 0


def test_used_coupon_latest_state_becomes_consume(module, db_path: Path) -> None:
    """落库后「最新状态」必须落在 CONSUME，否则券仍会被当成可用券。"""
    insert_coupon(db_path)
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, _report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    latest = asyncio.run(read_latest_state(db_path, COUPON_ID, MOBILE))
    assert latest is not None
    assert latest["status"] == "CONSUME"
    assert latest["order_no"] == USED_ORDER_NO


def test_invalid_unused_coupon_is_filled_as_expired(module, db_path: Path) -> None:
    """有赞已失效未使用：补全元数据并按券自身过期时间落库，状态仍是 TAKE。"""
    row_id = insert_coupon(
        db_path, coupon_id=EXPIRED_COUPON_ID, group_id=EXPIRED_GROUP_ID
    )
    member_api = FakeMemberApi({}, build_details())
    client = FakeYouzanClient({MOBILE: [build_expired_coupon()]})
    probe = build_probe(module, member_api, client)

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["expired_filled"] == 1
    row = read_coupon(db_path, row_id)
    assert row["status"] == "TAKE"
    assert row["title"] == "10元优惠券"
    assert row["value_fen"] == 1000
    assert row["template_id"] == EXPIRED_GROUP_ID
    assert row["valid_until"] == "2024-10-04"
    # 过期券必须被本地券引擎拒绝
    template = {
        "id": row["template_id"],
        "coupon_type": "FULL_REDUCTION",
        "threshold_fen": 5000,
        "value_fen": row["value_fen"],
        "discount_bp": 0,
        "cap_fen": 0,
        "valid_from": row["valid_from"],
        "valid_until": row["valid_until"],
        "status": "active",
    }
    apply_row_validity(template, row)
    assert is_coupon_available(template, 10000, NOW_TEXT) is False


def test_invalid_unused_coupon_needs_separate_query(module, db_path: Path) -> None:
    """过期券不在合并查询结果里，必须靠单独的 INVALID 查询才查得到。"""
    insert_coupon(db_path, coupon_id=EXPIRED_COUPON_ID, group_id=EXPIRED_GROUP_ID)
    member_api = FakeMemberApi({}, build_details())
    client = FakeYouzanClient({MOBILE: [build_expired_coupon()]})
    probe = build_probe(module, member_api, client)

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["expired_filled"] == 1
    invalid_calls = [
        call for call in client.calls if str(call[2].get("status", "")) == "INVALID"
    ]
    assert invalid_calls, "必须单独按 INVALID 状态查询一次"


def test_invalid_coupon_without_expiry_is_kept(module, db_path: Path) -> None:
    """证明不了券已过期时保留原行：只补面额会让过期券重新变成可用券。"""
    row_id = insert_coupon(
        db_path, coupon_id=EXPIRED_COUPON_ID, group_id=EXPIRED_GROUP_ID
    )
    member_api = FakeMemberApi({}, build_details())
    client = FakeYouzanClient({MOBILE: [build_expired_coupon(with_expire_at=False)]})
    probe = build_probe(module, member_api, client)

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["expired_filled"] == 0
    assert report["stats"]["by_reason"]["expiry_not_provable"] == 1
    row = read_coupon(db_path, row_id)
    assert row["title"] == ""
    assert row["value_fen"] == 0
    assert row["template_id"] == ""
    assert row["status"] == "TAKE"


def test_consume_fact_time_is_not_earlier_than_local_take_row(
    module, db_path: Path
) -> None:
    """本地 TAKE 行的事件时间晚于核销时间时，事实行时间取较晚者。

    生产实况：有赞 Webhook 落库时 `occurred_at` 记的是事件到达时间，往往晚于券
    的真实核销时间。最新状态解析按 `occurred_at` 倒序取行，照搬核销时间会让
    最新状态退回 TAKE，券重新变成可用券。
    """
    row_id = insert_coupon(
        db_path, occurred_at="2026-10-20 13:14:25", created_at="2026-10-20 13:14:25"
    )
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    rows = read_rows(db_path)
    consume_row = next(row for row in rows if row["status"] == "CONSUME")
    take_row = read_coupon(db_path, row_id)
    assert consume_row["occurred_at"] == "2026-10-20 13:14:25"
    assert consume_row["occurred_at"] >= take_row["occurred_at"]
    # 真实核销时间保留在 consumed_at / youzan_used_at
    assert consume_row["consumed_at"] == "2024-09-27 17:04:03"
    assert report["rows"][0]["youzan_used_at"] == "2024-09-27 17:04:03"
    latest = asyncio.run(read_latest_state(db_path, COUPON_ID, MOBILE))
    assert latest is not None
    assert latest["status"] == "CONSUME"


def test_local_consume_row_is_not_duplicated(module, db_path: Path) -> None:
    """本地已是 CONSUME：只补全元数据，绝不重复插入。"""
    row_id = insert_coupon(db_path, status="CONSUME")
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["consume_metadata_filled"] == 1
    assert report["summary"]["inserted"] == 0
    rows = read_rows(db_path)
    assert len(rows) == 1
    row = read_coupon(db_path, row_id)
    assert row["status"] == "CONSUME"
    assert row["title"] == "20元优惠券"
    assert row["value_fen"] == 2000
    assert row["template_id"] == GROUP_ID
    assert row["valid_until"] == "2024-10-04"


def test_apply_is_idempotent(module, db_path: Path) -> None:
    """重复执行不会重复插入 CONSUME 行。"""
    insert_coupon(db_path)
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    first_code, first_report = run_script(module, db_path, probe)
    after_first = read_rows(db_path)
    second_code, second_report = run_script(module, db_path, probe)
    after_second = read_rows(db_path)

    assert first_code == module.EXIT_OK
    assert second_code == module.EXIT_OK
    assert first_report["summary"]["inserted"] == 1
    assert second_report["summary"]["inserted"] == 0
    assert second_report["summary"]["consume_fact_aligned"] == 1
    # 第二次执行是真正的空操作：不新增行，也不改写已有行
    assert second_report["result"]["updated"] == 0
    assert second_report["result"]["aligned"] == 1
    assert len(after_first) == len(after_second) == 2
    assert after_first == after_second


def test_coupon_not_found_is_kept(module, db_path: Path) -> None:
    """有赞查不到该券时保留原行，不删除、不改写。"""
    row_id = insert_coupon(db_path)
    member_api = FakeMemberApi({}, {GROUP_ID: build_template_detail()})
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["kept"] == 1
    assert report["stats"]["by_reason"]["coupon_not_found_in_youzan"] == 1
    rows = read_rows(db_path)
    assert len(rows) == 1
    row = read_coupon(db_path, row_id)
    assert row["status"] == "TAKE"
    assert row["title"] == ""
    assert row["value_fen"] == 0


def test_valid_coupon_is_aligned(module, db_path: Path) -> None:
    """有赞当前有效 + 本地记持有：两侧一致，只补全元数据。"""
    row_id = insert_coupon(db_path)
    member_api = FakeMemberApi(
        {MOBILE: [build_valid_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["valid_aligned"] == 1
    row = read_coupon(db_path, row_id)
    assert row["status"] == "TAKE"
    assert row["title"] == "20元优惠券"
    assert row["value_fen"] == 2000
    assert row["template_id"] == GROUP_ID


def test_youzan_query_failure_keeps_row(module, db_path: Path) -> None:
    """有赞接口失败时结论未知，保留原行并报告。"""
    row_id = insert_coupon(db_path)
    member_api = FakeMemberApi(
        {}, {GROUP_ID: build_template_detail()}, error=RuntimeError("gateway 4005")
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["kept"] == 1
    assert report["stats"]["by_reason"]["youzan_query_failed"] == 1
    row = read_coupon(db_path, row_id)
    assert row["status"] == "TAKE"
    assert row["title"] == ""


def test_dry_run_does_not_write(module, db_path: Path) -> None:
    """默认 dry-run：只出报告，库内一行都不动。"""
    row_id = insert_coupon(db_path)
    before = read_coupon(db_path, row_id)
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe, apply=False)

    assert exit_code == module.EXIT_OK
    assert report["mode"] == "dry-run"
    assert report["summary"]["consume_fact_inserted"] == 1
    assert report["summary"]["inserted"] == 0
    assert report["result"]["committed"] is False
    assert read_coupon(db_path, row_id) == before
    assert len(read_rows(db_path)) == 1


def test_transaction_rolls_back_on_row_failure(module, db_path: Path) -> None:
    """任一行写库失败时整体回滚：先写的 CONSUME 事实也不能留下。"""
    first_id = insert_coupon(db_path, coupon_id=COUPON_ID, mobile=MOBILE)
    second_id = insert_coupon(
        db_path,
        coupon_id=EXPIRED_COUPON_ID,
        group_id=EXPIRED_GROUP_ID,
        mobile=MOBILE,
    )
    with sqlite3.connect(db_path) as connection:
        # 用真实触发器制造单行写入失败，验证事务整体回滚
        # （条件是静态的：任何把券名写成非空的 UPDATE 都会失败）
        connection.execute(
            "CREATE TRIGGER boom BEFORE UPDATE ON coupon_inventory "
            "WHEN NEW.title <> '' BEGIN "
            "SELECT RAISE(ABORT, '模拟写入失败'); END"
        )
    member_api = FakeMemberApi({MOBILE: [build_used_coupon()]}, build_details())
    client = FakeYouzanClient({MOBILE: [build_expired_coupon()]})
    probe = build_probe(module, member_api, client)

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_FAILED
    assert report["result"]["committed"] is False
    assert report["result"]["error"]
    rows = read_rows(db_path)
    # 整体回滚：一行都不该留下
    assert len(rows) == 2
    assert all(row["status"] == "TAKE" for row in rows)
    assert read_coupon(db_path, first_id)["title"] == ""
    assert read_coupon(db_path, second_id)["title"] == ""


def test_report_masks_mobile(module, db_path: Path) -> None:
    """报告里的手机号必须脱敏，原始手机号不得出现。"""
    insert_coupon(db_path)
    member_api = FakeMemberApi(
        {MOBILE: [build_used_coupon()]}, {GROUP_ID: build_template_detail()}
    )
    probe = build_probe(module, member_api, FakeYouzanClient())

    exit_code, report = run_script(module, db_path, probe)

    assert exit_code == module.EXIT_OK
    row = report["rows"][0]
    assert row["mobile"] == "189****3140"
    assert MOBILE not in json.dumps(report, ensure_ascii=False)


def test_production_path_requires_allow_production(module, tmp_path: Path) -> None:
    """指向生产路径时必须显式传 --allow-production。"""
    production_path = production_like_db_path(tmp_path)

    with pytest.raises(module.TargetRejected):
        module.evaluate_target_guard(production_path, allow_production=False)

    guard = module.evaluate_target_guard(production_path, allow_production=True)
    assert guard["production_like"] is True
    assert guard["allow_production"] is True


def test_production_path_is_rejected_by_cli(module, capsys) -> None:
    """生产路径且未声明 --allow-production 时脚本拒绝执行。"""
    production_path = "/opt/apps/yunxi-bakery/backend/data/bot.db"

    exit_code = module.main(["--db", production_path, "--apply"])

    assert exit_code == module.EXIT_REJECTED
    captured = capsys.readouterr()
    assert "--allow-production" in captured.out


def test_missing_database_is_rejected(module, db_path: Path) -> None:
    """目标库不存在时拒绝执行，脚本不会创建数据库。"""
    missing = db_path.parent / "not-exist.db"

    with pytest.raises(module.TargetRejected):
        module.evaluate_target_guard(missing, allow_production=True)
