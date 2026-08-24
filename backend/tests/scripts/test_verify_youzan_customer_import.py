from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType


def load_import_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "import_youzan_customers.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_youzan_customers_for_verify", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_verify_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_youzan_customer_import.py"
    )
    spec = importlib.util.spec_from_file_location(
        "verify_youzan_customer_import", script_path
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
        return cls(2026, 6, 20, 12, 20, 0, tzinfo=tz)


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


async def _apply_import(
    import_script: ModuleType,
    *,
    monkeypatch,
    customer_csv: Path,
    orders_csv: Path,
    database_path: Path,
    report_path: Path,
    source_batch_id: str,
) -> Path:
    monkeypatch.setattr(import_script, "datetime", _FrozenDateTime)
    exit_code = await import_script.async_main(
        [
            "--customer-csv",
            str(customer_csv),
            "--orders-csv",
            str(orders_csv),
            "--db-path",
            str(database_path),
            "--tenant-id",
            "tenant-yunxi",
            "--source-batch-id",
            source_batch_id,
            "--apply",
            "--allow-create",
            "--json",
            "--output",
            str(report_path),
        ]
    )
    assert exit_code == 0
    return report_path.parent / report_path.name.replace(
        "{timestamp}",
        "20260620-122000",
    )


def test_main_requires_batch_or_import_report(capsys) -> None:
    verify_script = load_verify_module()

    exit_code = verify_script.main([])

    assert exit_code == 2
    assert (
        "--source-batch-id 与 --import-report 至少提供一个" in capsys.readouterr().err
    )


async def test_main_verifies_batch_summary_from_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import_script = load_import_module()
    verify_script = load_verify_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    database_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "import-{timestamp}.json"
    output_path = tmp_path / "reports" / "verify-{timestamp}.json"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)

    await _apply_import(
        import_script,
        monkeypatch=monkeypatch,
        customer_csv=customer_csv,
        orders_csv=orders_csv,
        database_path=database_path,
        report_path=report_path,
        source_batch_id="batch-20260620",
    )
    monkeypatch.setattr(verify_script, "datetime", _FrozenDateTime)

    exit_code = verify_script.main(
        [
            "--db-path",
            str(database_path),
            "--tenant-id",
            "tenant-yunxi",
            "--source-batch-id",
            "batch-20260620",
            "--json",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    expected_path = tmp_path / "reports" / "verify-20260620-122000.json"
    payload = json.loads(expected_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "ready"
    assert payload["report"]["snapshot_count"] == 5
    assert payload["report"]["distinct_customer_count"] == 5
    assert payload["report"]["source_identity_count"] == 5
    assert payload["report"]["linked_phone_identity_count"] == 2
    assert payload["report"]["merge_review_count"] == 2
    assert payload["report"]["bucket_summary"] == {
        "auto_merge": 1,
        "new_master": 2,
        "pending_review": 2,
    }


async def test_main_compares_apply_report_successfully(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import_script = load_import_module()
    verify_script = load_verify_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    database_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "import-{timestamp}.json"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)

    import_report_path = await _apply_import(
        import_script,
        monkeypatch=monkeypatch,
        customer_csv=customer_csv,
        orders_csv=orders_csv,
        database_path=database_path,
        report_path=report_path,
        source_batch_id="batch-20260620",
    )
    monkeypatch.setattr(verify_script, "datetime", _FrozenDateTime)

    exit_code = verify_script.main(
        [
            "--db-path",
            str(database_path),
            "--import-report",
            str(import_report_path),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = (
        json.loads(sys.stdout.getvalue()) if hasattr(sys.stdout, "getvalue") else None
    )
    if payload is None:
        payload = verify_script.build_json_report(
            verify_script.verify_customer_import(
                db_path_value=str(database_path),
                tenant_id="tenant-yunxi",
                source_batch_id="batch-20260620",
                import_report_path=str(import_report_path),
                import_report_payload=json.loads(
                    import_report_path.read_text(encoding="utf-8-sig")
                ),
            )
        )
    assert payload["report"]["compared_report_mode"] == "applied"
    assert payload["report"]["expected_total_records"] == 5
    assert payload["report"]["mismatches"] == []
    assert "actions_summary" in payload["report"]["unverifiable_checks"][0]


async def test_main_detects_import_report_mismatch(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import_script = load_import_module()
    verify_script = load_verify_module()
    customer_csv = tmp_path / "customers.csv"
    orders_csv = tmp_path / "orders.csv"
    database_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "import-{timestamp}.json"
    _write_customer_csv(customer_csv)
    _write_orders_csv(orders_csv)

    import_report_path = await _apply_import(
        import_script,
        monkeypatch=monkeypatch,
        customer_csv=customer_csv,
        orders_csv=orders_csv,
        database_path=database_path,
        report_path=report_path,
        source_batch_id="batch-20260620",
    )
    broken_payload = json.loads(import_report_path.read_text(encoding="utf-8-sig"))
    broken_payload["report"]["applied_bucket_summary"]["pending_review"] = 1
    broken_report_path = tmp_path / "reports" / "import-broken.json"
    broken_report_path.write_text(
        json.dumps(broken_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script, "datetime", _FrozenDateTime)

    exit_code = verify_script.main(
        [
            "--db-path",
            str(database_path),
            "--import-report",
            str(broken_report_path),
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "verified=False" in output
    assert "bucket_summary 与批次实际分流不一致" in output
