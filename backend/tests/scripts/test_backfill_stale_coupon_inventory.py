"""旧券库存定向回填脚本的测试（真实 SQLite 临时库 + 假有赞 API，不 mock 数据库）。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "backfill_stale_coupon_inventory.py"
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

COUPON_TEMPLATES_DDL = """
CREATE TABLE IF NOT EXISTS coupon_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    coupon_type TEXT NOT NULL DEFAULT '',
    threshold_fen INTEGER NOT NULL DEFAULT 0,
    value_fen INTEGER NOT NULL DEFAULT 0,
    discount_bp INTEGER NOT NULL DEFAULT 0,
    cap_fen INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    scope_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL DEFAULT 'youzan',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MOBILE = "18911163140"
OTHER_MOBILE = "13167327393"
COUPON_ID = "38863608300"
OTHER_COUPON_ID = "66865484667"
GROUP_ID = "32035241"
TAKE_AT = 1727341443000
EXPIRE_AT = 1728000000000
TEMPLATE_VALID_END = 4102444800000


def load_module() -> ModuleType:
    """按路径加载被测脚本模块。"""
    spec = importlib.util.spec_from_file_location(
        "backfill_stale_coupon_inventory", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
        """按手机号返回预置买家券。"""
        self.coupon_calls.append(mobile)
        if self._error is not None:
            raise self._error
        return list(self._coupons.get(mobile, []))

    async def get_coupon_group_detail(self, coupon_group_id: str) -> dict:
        """按券模板 ID 返回预置模板详情。"""
        self.detail_calls.append(coupon_group_id)
        return dict(self._details.get(coupon_group_id, {}))


def build_coupon(
    coupon_id: str = COUPON_ID,
    group_id: str = GROUP_ID,
    status: str = "VALID",
) -> dict:
    """构造一条与有赞买家券查询一致形状的券。"""
    return {
        "id": coupon_id,
        "coupon_id": coupon_id,
        "coupon_group_id": group_id,
        "title": "20元优惠券",
        "status": status,
        "youzan_coupon_status": status,
        "is_used": 0,
        "take_at": TAKE_AT,
        "valid_start_at": TAKE_AT,
        "expire_at": EXPIRE_AT,
        "value": 2000,
    }


def build_template_detail(group_id: str = GROUP_ID) -> dict:
    """构造一份与有赞券模板详情一致形状的模板。"""
    return {
        "coupon_group_id": group_id,
        "title": "20元优惠卷",
        "denominations": 2000,
        "condition": 5000,
        "preferential_type": 1,
        "valid_start_time": TAKE_AT,
        "valid_end_time": TEMPLATE_VALID_END,
    }


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """建立只含券库存与券模板两张表的真实 SQLite 临时库。"""
    path = tmp_path / "bot.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(COUPON_INVENTORY_DDL)
        connection.executescript(COUPON_TEMPLATES_DDL)
    return path


def insert_coupon(
    db_path: Path,
    *,
    coupon_id: str = COUPON_ID,
    group_id: str = GROUP_ID,
    mobile: str = MOBILE,
    status: str = "TAKE",
    title: str = "",
    value_fen: int = 0,
    template_id: str = "",
    source: str = "webhook",
    occurred_at: str = "2026-10-20 13:14:25",
    created_at: str = "2026-10-20 13:14:25",
) -> int:
    """写入一条券库存行，返回自增 id。"""
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO coupon_inventory (coupon_id, coupon_group_id, customer_id, "
            "mobile, status, order_no, title, value_fen, detail_json, source, "
            "occurred_at, created_at, template_id, valid_from, valid_until, cycle_no) "
            "VALUES (?, ?, '', ?, ?, '', ?, ?, '{}', ?, ?, ?, ?, '', '', 0)",
            (
                coupon_id,
                group_id,
                mobile,
                status,
                title,
                value_fen,
                source,
                occurred_at,
                created_at,
                template_id,
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
            "valid_from, valid_until, cycle_no FROM coupon_inventory WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def production_like_db_path(tmp_path: Path) -> Path:
    """构造一个「长得像生产部署目录」的真实数据库路径。"""
    path = tmp_path / "opt" / "apps" / "yunxi-bakery" / "backend" / "data" / "bot.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path):
        pass
    return path


def read_template(db_path: Path, template_id: str) -> dict | None:
    """按模板 ID 读取券模板行。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, name, coupon_type, threshold_fen, value_fen, valid_from, "
            "valid_until, status, source FROM coupon_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def run_script(
    module: ModuleType,
    db_path: Path,
    member_api: FakeMemberApi,
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
    exit_code = asyncio.run(module.async_main(argv, member_api=member_api))
    report = json.loads(output_path.read_text(encoding="utf-8"))
    return exit_code, report


def test_backfills_coupon_found_in_youzan(db_path: Path) -> None:
    """命中当前券时回填券名/面额/模板/有效期，且不改动状态与来源。"""
    module = load_module()
    row_id = insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["backfilled"] == 1
    assert report["summary"]["expired"] == 0
    row = read_coupon(db_path, row_id)
    assert row["title"] == "20元优惠券"
    assert row["value_fen"] == 2000
    assert row["template_id"] == GROUP_ID
    assert row["coupon_group_id"] == GROUP_ID
    assert row["valid_from"] == "2024-09-26"
    assert row["valid_until"] == "2024-10-04"
    assert row["occurred_at"] == "2024-09-26 17:04:03"
    assert json.loads(row["detail_json"])["coupon_id"] == COUPON_ID
    # 状态、来源与创建时间不得被回填改动
    assert row["status"] == "TAKE"
    assert row["source"] == "webhook"
    assert row["created_at"] == "2026-10-20 13:14:25"


def test_keeps_row_when_coupon_not_found(db_path: Path) -> None:
    """有赞查不到该券时保留原行，不删除、不改写。"""
    module = load_module()
    row_id = insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: []}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["backfilled"] == 0
    assert report["summary"]["expired"] == 1
    row = read_coupon(db_path, row_id)
    assert row["title"] == ""
    assert row["value_fen"] == 0
    assert row["template_id"] == ""
    assert row["status"] == "TAKE"


def test_only_updates_same_coupon_id_and_mobile(db_path: Path) -> None:
    """只更新同 coupon_id + 同 mobile 的那一行，其他券行不受影响。"""
    module = load_module()
    target_id = insert_coupon(db_path)
    # 同手机号的另一张券（非骨架行，本就带券名）
    other_coupon_id = insert_coupon(
        db_path,
        coupon_id=OTHER_COUPON_ID,
        title="10元优惠券",
        value_fen=1000,
        template_id=GROUP_ID,
    )
    # 同 coupon_id 但不同手机号的骨架行
    other_mobile_id = insert_coupon(db_path, mobile=OTHER_MOBILE)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["backfilled"] == 1
    assert read_coupon(db_path, target_id)["title"] == "20元优惠券"
    # 其他券行必须原样保留
    other_row = read_coupon(db_path, other_coupon_id)
    assert other_row["title"] == "10元优惠券"
    assert other_row["value_fen"] == 1000
    untouched = read_coupon(db_path, other_mobile_id)
    assert untouched["title"] == ""
    assert untouched["value_fen"] == 0
    assert untouched["template_id"] == ""


def test_apply_is_idempotent(db_path: Path) -> None:
    """重复执行不会二次改写：第二次没有骨架行可处理。"""
    module = load_module()
    row_id = insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    first_code, first_report = run_script(module, db_path, api)
    after_first = read_coupon(db_path, row_id)
    second_code, second_report = run_script(module, db_path, api)
    after_second = read_coupon(db_path, row_id)

    assert first_code == module.EXIT_OK
    assert second_code == module.EXIT_OK
    assert first_report["summary"]["backfilled"] == 1
    assert second_report["summary"]["stale_total"] == 0
    assert second_report["summary"]["updated"] == 0
    assert after_first == after_second


def test_dry_run_does_not_write(db_path: Path) -> None:
    """默认 dry-run：只出报告，库内一行都不动。"""
    module = load_module()
    row_id = insert_coupon(db_path)
    before = read_coupon(db_path, row_id)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(module, db_path, api, apply=False)

    assert exit_code == module.EXIT_OK
    assert report["mode"] == "dry-run"
    assert report["summary"]["backfilled"] == 1
    assert report["summary"]["updated"] == 0
    assert read_coupon(db_path, row_id) == before


def test_status_conflict_is_not_overwritten(db_path: Path) -> None:
    """有赞状态与本地状态冲突时不改写该行。"""
    module = load_module()
    row_id = insert_coupon(db_path, status="TAKE")
    api = FakeMemberApi(
        {MOBILE: [build_coupon(status="USED")]}, {GROUP_ID: build_template_detail()}
    )

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["ambiguous"] == 1
    assert report["stats"]["by_reason"]["status_conflict_with_local_row"] == 1
    row = read_coupon(db_path, row_id)
    assert row["title"] == ""
    assert row["status"] == "TAKE"


def test_missing_template_keeps_row(db_path: Path) -> None:
    """券模板缺失时保留原行并归入 missing。"""
    module = load_module()
    row_id = insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {})

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    assert report["summary"]["missing"] == 1
    assert report["stats"]["by_reason"]["coupon_template_missing"] == 1
    row = read_coupon(db_path, row_id)
    assert row["title"] == ""
    assert row["value_fen"] == 0


def test_upsert_templates_writes_coupon_templates(db_path: Path) -> None:
    """开启 --upsert-templates 时把用到的券模板幂等写进 coupon_templates。"""
    module = load_module()
    insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(
        module, db_path, api, extra_args=["--upsert-templates"]
    )

    assert exit_code == module.EXIT_OK
    assert report["options"]["upsert_templates"] is True
    assert report["result"]["templates_upserted"] == [GROUP_ID]
    template = read_template(db_path, GROUP_ID)
    assert template is not None
    assert template["name"] == "20元优惠卷"
    assert template["coupon_type"] == "FULL_REDUCTION"
    assert template["threshold_fen"] == 5000
    assert template["value_fen"] == 2000
    assert template["source"] == "youzan"


def test_report_masks_mobile(db_path: Path) -> None:
    """报告里的手机号必须脱敏，原始手机号不得出现。"""
    module = load_module()
    insert_coupon(db_path)
    api = FakeMemberApi({MOBILE: [build_coupon()]}, {GROUP_ID: build_template_detail()})

    exit_code, report = run_script(module, db_path, api)

    assert exit_code == module.EXIT_OK
    row = report["rows"][0]
    assert row["mobile"] == "189****3140"
    assert MOBILE not in json.dumps(report, ensure_ascii=False)


def test_production_path_requires_allow_production(tmp_path: Path) -> None:
    """指向生产路径时必须显式传 --allow-production。"""
    module = load_module()
    production_path = production_like_db_path(tmp_path)

    with pytest.raises(module.TargetRejected):
        module.evaluate_target_guard(production_path, allow_production=False)

    guard = module.evaluate_target_guard(production_path, allow_production=True)
    assert guard["production_like"] is True
    assert guard["allow_production"] is True


def test_production_path_is_rejected_by_cli(capsys) -> None:
    """生产路径且未声明 --allow-production 时脚本拒绝执行。"""
    module = load_module()
    production_path = "/opt/apps/yunxi-bakery/backend/data/bot.db"

    exit_code = module.main(["--db", production_path, "--apply"])

    assert exit_code == module.EXIT_REJECTED
    captured = capsys.readouterr()
    assert "--allow-production" in captured.out


def test_missing_database_is_rejected(db_path: Path) -> None:
    """目标库不存在时拒绝执行，脚本不会创建数据库。"""
    module = load_module()
    missing = db_path.parent / "not-exist.db"

    with pytest.raises(module.TargetRejected):
        module.evaluate_target_guard(missing, allow_production=True)
