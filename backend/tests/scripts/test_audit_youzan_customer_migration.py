from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType


def load_audit_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "audit_youzan_customer_migration.py"
    )
    spec = importlib.util.spec_from_file_location(
        "audit_youzan_customer_migration",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 20, 10, 30, 0, tzinfo=tz)


def _write_customer_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "客户姓名,客户昵称,客户手机号,客户生日,客户性别,标签,是否会员,成长值,免费等级,付费等级,权益卡,客户积分,客户储值余额,消费次数,消费金额,累计退款金额,累计退款订单数,笔单价,上次消费时间,分销员,导购员,企微好友,来源渠道,来源方式,成为客户时间,成为会员时间,成为会员店铺,公众号,公众号关注时间,最近浏览时间,微信地域,所属区域,指定时间消费次数,指定时间消费金额,",
                "Alice,Alice,13800138000,1990-01-01,女,生日蛋糕,是,12,,, ,200,10.00,2,300.00,0.00,0,150.00,2026-06-18 10:00:00,,,否,有赞后台,外部导入,2024-01-01 10:00:00,,,,,北京,朝阳区,,",
                ",沙拉,, ,其他,,否,2,,, ,10,0.00,0,0.00,0.00,0,0.00,,,,否,微信小程序,登录创建客户,2026-04-15 12:21:29,,,,,北京,朝阳区,,",
                "张三,张三,13900139000,,男,,是,20,,, ,0,0.00,1,100.00,0.00,0,100.00,2026-06-17 09:00:00,,,否,有赞后台,外部导入,2023-09-21 21:09:25,,,,,北京,海淀区,,",
                "李四,李四,13900139000,,女,,否,1,,, ,0,0.00,0,0.00,0.00,0,0.00,,,,否,微信小程序,登录创建客户,2026-04-15 12:21:29,,,,,上海,浦东新区,,",
                "Foo,Foo,186******05,,其他,,否,1,,, ,0,0.00,0,0.00,0.00,0,0.00,,,,否,有赞后台,外部导入,2023-09-21 21:09:35,,,,,广州,天河区,,",
            ]
        ),
        encoding="utf-8",
    )


def _write_orders_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "订单号,销售渠道,归属店铺,订单类型,订单状态,推广方式,订单来源,订单创建时间,买家付款时间,交易成功时间,付款方式,支付流水号,商品金额合计,运费,店铺优惠合计,应收订单金额,订单实付金额,支付优惠合计,订单实收金额,订单抵用积分数,店铺优惠方式,支付优惠方式,全部商品名称,商品种类数,订单配送方式,同城送达时间/提货时间,收货人省份,收货人城市,收货人地区,详细收货地址/提货地址,收货人/提货人,收货人手机号/提货人手机号,买家备注,订单星级,买家昵称,买家是否会员,买家手机号,下单网点,收银员,分销员,销售导购,专属导购,订单退款状态,订单已退款金额,商家订单备注,桌号,挂账主体,挂账手机号,团长订单,订单风险标签,分销员,分销员手机号,分销员所属店铺,分销员所属团队,分销员所属分组,分销员等级,订单佣金类型,订单佣金金额,订单下级卖货提成类型,订单下级卖货提成金额",
                "O-1,网店,芸熙烘焙,普通订单,交易完成,,商家小程序,2026-06-19 10:00:00,2026-06-19 10:01:00,2026-06-19 10:02:00,微信支付,,100.00,0.00,0,100.00,100.00,0.00,100.00,0,,,草莓蛋糕,1,同城送,2026-06-20 11:00 - 2026-06-20 12:00,北京,北京,朝阳区,地址,Alice,13800138000,, ,Alice,是,13800138000,,,,,,,0.00,,,,,否,——,,,,,,,,,,",
                "O-2,网店,芸熙烘焙,普通订单,交易完成,,商家小程序,2026-06-19 11:00:00,2026-06-19 11:01:00,2026-06-19 11:02:00,微信支付,,200.00,0.00,0,200.00,200.00,0.00,200.00,0,,,蓝莓蛋糕,1,同城送,2026-06-20 13:00 - 2026-06-20 14:00,北京,北京,朝阳区,地址,沙拉,13200000000,, ,沙拉,否,13200000000,,,,,,,0.00,,,,,否,——,,,,,,,,,,",
                "O-3,网店,芸熙烘焙,普通订单,交易完成,,商家小程序,2026-06-19 12:00:00,2026-06-19 12:01:00,2026-06-19 12:02:00,微信支付,,300.00,0.00,0,300.00,300.00,0.00,300.00,0,,,巧克力蛋糕,1,同城送,2026-06-20 15:00 - 2026-06-20 16:00,北京,北京,朝阳区,地址,张三,13900139000,, ,张三,是,13900139000,,,,,,,0.00,,,,,否,——,,,,,,,,,,",
            ]
        ),
        encoding="utf-8",
    )


def test_normalize_phone_handles_valid_masked_and_invalid_values() -> None:
    audit = load_audit_module()

    assert audit.normalize_phone(" 138 0013 8000 ") == "13800138000"
    assert audit.normalize_phone("186******05") == ""
    assert audit.normalize_phone("abc") == ""
    assert audit.normalize_phone("") == ""


def test_run_audit_builds_expected_summary_and_buckets(tmp_path: Path) -> None:
    audit = load_audit_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)

    artifacts = audit.run_audit(customer_csv, orders_csv)

    assert artifacts.summary["total_customers"] == 5
    assert artifacts.summary["customers_with_phone"] == 3
    assert artifacts.summary["customers_without_phone"] == 2
    assert artifacts.summary["unique_phone_count"] == 2
    assert artifacts.summary["duplicate_phone_customer_count"] == 2
    assert artifacts.summary["duplicate_phone_group_count"] == 1
    assert artifacts.summary["invalid_phone_count"] == 1
    assert artifacts.summary["auto_merge_customer_count"] == 1
    assert artifacts.summary["new_master_customer_count"] == 2
    assert artifacts.summary["pending_review_customer_count"] == 2
    assert artifacts.summary["orders_with_buyer_phone"] == 3
    assert artifacts.summary["orders_phone_match_customer"] == 2
    assert artifacts.summary["customers_missing_phone_but_order_matchable"] == 1
    assert artifacts.summary["same_phone_name_conflict_count"] == 2
    assert artifacts.summary["same_phone_membership_conflict_count"] == 2
    assert artifacts.summary["same_phone_source_conflict_count"] == 2

    issue_types = {row.issue_type for row in artifacts.issues}
    assert "missing_phone" in issue_types
    assert "invalid_phone" in issue_types
    assert "duplicate_phone" in issue_types

    bucket_map = {
        row.source_record_id: row.proposed_bucket for row in artifacts.buckets
    }
    assert bucket_map["customer-row-1"] == "auto_merge"
    assert bucket_map["customer-row-2"] == "new_master"
    assert bucket_map["customer-row-3"] == "pending_review"
    assert bucket_map["customer-row-4"] == "pending_review"
    assert bucket_map["customer-row-5"] == "new_master"


def test_main_output_requires_json_flag(capsys) -> None:
    audit = load_audit_module()

    exit_code = audit.main(["--output", "report.json"])

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err


def test_main_writes_json_and_csv_reports(monkeypatch, tmp_path: Path) -> None:
    audit = load_audit_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)
    monkeypatch.setattr(audit, "datetime", _FrozenDateTime)

    json_path = tmp_path / "reports" / "audit-{timestamp}.json"
    metrics_path = tmp_path / "reports" / "metrics-{timestamp}.csv"
    issues_path = tmp_path / "reports" / "issues-{timestamp}.csv"
    buckets_path = tmp_path / "reports" / "buckets-{timestamp}.csv"

    exit_code = audit.main(
        [
            "--customer-csv",
            str(customer_csv),
            "--orders-csv",
            str(orders_csv),
            "--json",
            "--output",
            str(json_path),
            "--metrics-output",
            str(metrics_path),
            "--issues-output",
            str(issues_path),
            "--buckets-output",
            str(buckets_path),
        ]
    )

    assert exit_code == 0
    expected_json_path = tmp_path / "reports" / "audit-20260620-103000.json"
    expected_metrics_path = tmp_path / "reports" / "metrics-20260620-103000.csv"
    expected_issues_path = tmp_path / "reports" / "issues-20260620-103000.csv"
    expected_buckets_path = tmp_path / "reports" / "buckets-20260620-103000.csv"
    assert expected_json_path.read_bytes().startswith(audit.UTF8_BOM)
    assert expected_metrics_path.read_bytes().startswith(audit.UTF8_BOM)
    assert expected_issues_path.read_bytes().startswith(audit.UTF8_BOM)
    assert expected_buckets_path.read_bytes().startswith(audit.UTF8_BOM)

    payload = json.loads(expected_json_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "ready"
    assert payload["metadata"]["generated_at"] == "2026-06-20T10:30:00Z"
    assert payload["summary"]["pending_review_customer_count"] == 2


def test_main_apply_import_writes_import_report(monkeypatch, tmp_path: Path) -> None:
    audit = load_audit_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    database_path = tmp_path / "bot.db"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)
    monkeypatch.setattr(audit, "datetime", _FrozenDateTime)

    import_path = tmp_path / "reports" / "import-{timestamp}.json"

    exit_code = audit.main(
        [
            "--customer-csv",
            str(customer_csv),
            "--orders-csv",
            str(orders_csv),
            "--apply-import",
            "--db-path",
            str(database_path),
            "--tenant-id",
            "tenant-yunxi",
            "--source-batch-id",
            "batch-20260620",
            "--import-output",
            str(import_path),
        ]
    )

    assert exit_code == 0
    expected_import_path = tmp_path / "reports" / "import-20260620-103000.json"
    payload = json.loads(expected_import_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "ready"
    assert payload["metadata"]["tenant_id"] == "tenant-yunxi"
    assert payload["metadata"]["source_batch_id"] == "batch-20260620"
    assert payload["summary"]["total_records"] == 5
    assert payload["summary"]["bucket_summary"]["pending_review"] == 2


def test_main_apply_import_is_idempotent_for_same_file_db_batch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    database_path = tmp_path / "bot.db"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)
    monkeypatch.setattr(audit, "datetime", _FrozenDateTime)

    first_import_path = tmp_path / "reports" / "import-first-{timestamp}.json"
    second_import_path = tmp_path / "reports" / "import-second-{timestamp}.json"
    common_args = [
        "--customer-csv",
        str(customer_csv),
        "--orders-csv",
        str(orders_csv),
        "--apply-import",
        "--db-path",
        str(database_path),
        "--tenant-id",
        "tenant-yunxi",
        "--source-batch-id",
        "batch-20260620",
    ]

    first_exit_code = audit.main(
        [
            *common_args,
            "--import-output",
            str(first_import_path),
        ]
    )
    second_exit_code = audit.main(
        [
            *common_args,
            "--import-output",
            str(second_import_path),
        ]
    )

    assert first_exit_code == 0
    assert second_exit_code == 0

    first_payload = json.loads(
        (tmp_path / "reports" / "import-first-20260620-103000.json").read_text(
            encoding="utf-8-sig"
        )
    )
    second_payload = json.loads(
        (tmp_path / "reports" / "import-second-20260620-103000.json").read_text(
            encoding="utf-8-sig"
        )
    )

    assert first_payload["summary"]["actions_summary"] == {
        "create_master": 1,
        "create_review_queue": 2,
        "create_weak_master": 2,
    }
    assert second_payload["summary"]["actions_summary"] == {
        "skip_existing_batch_row": 5,
    }
