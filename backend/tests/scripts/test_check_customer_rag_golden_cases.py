import json

from scripts import check_customer_rag_golden_cases as golden_check


def test_customer_rag_golden_fixture_passes_structure_check() -> None:
    checks = golden_check.validate_fixture(golden_check.load_fixture())
    report = golden_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert {f"group.{group}" for group in golden_check.REQUIRED_GROUPS}.issubset(
        {check.name for check in checks}
    )
    assert {
        f"sensitive_output_policy.{scenario}"
        for scenario in golden_check.REQUIRED_SENSITIVE_SCENARIOS
    }.issubset({check.name for check in checks})


def test_customer_rag_golden_fixture_requires_all_groups() -> None:
    payload = {
        "meta": {"version": "1", "purpose": "test"},
        "cases": [
            {
                "id": "only-product",
                "group": "product_consultation",
                "query": "生日蛋糕",
                "intent": "product_consultation",
                "relevant": [["生日"]],
                "guardrails": ["不能编造商品"],
            }
        ],
    }

    checks = golden_check.validate_fixture(payload)
    report = golden_check.build_json_report(checks)

    assert report["status"] == "failed"
    missing_group_checks = [
        check
        for check in checks
        if check.name.startswith("group.") and not check.passed
    ]
    assert {check.name for check in missing_group_checks} == {
        "group.inventory",
        "group.delivery",
        "group.refund_after_sales",
        "group.human_transfer",
        "group.knowledge_no_match",
    }


def test_customer_rag_golden_fixture_requires_sensitive_scenario_coverage() -> None:
    payload = {
        "meta": {"version": "1", "purpose": "test"},
        "cases": [
            {
                "id": f"order-{index}",
                "group": "human_transfer",
                "query": "查订单",
                "intent": "human_transfer",
                "relevant": [["订单"]],
                "guardrails": ["不能编造订单"],
                "sensitive_scenarios": ["order"],
            }
            for index in range(5)
        ],
    }

    checks = golden_check.validate_fixture(payload)
    report = golden_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert any(check.name == "sensitive.order" and check.passed for check in checks)
    assert any(
        check.name == "sensitive.refund" and not check.passed for check in checks
    )


def test_customer_rag_golden_fixture_requires_sensitive_policy_keywords() -> None:
    case = {
        "id": "order-risk",
        "group": "human_transfer",
        "query": "查订单",
        "intent": "human_transfer",
        "relevant": [["订单"]],
        "guardrails": ["回答要谨慎"],
        "sensitive_scenarios": ["order"],
    }

    checks = golden_check.build_sensitive_policy_checks(case)

    assert checks == [
        golden_check.GoldenCaseCheck(
            "order-risk.sensitive_policy.order",
            False,
            "missing policy keywords: ['订单', '不能编造 / 工具 / 人工 / 订单状态 / 确认 / 转人工']",
        )
    ]


def test_customer_rag_golden_derives_forbidden_reply_patterns() -> None:
    patterns = golden_check.build_forbidden_reply_patterns(
        {"sensitive_scenarios": ["order", "refund", "order"]}
    )

    assert "已为您查到订单" in patterns
    assert "可以全额退款" in patterns
    assert patterns.count("已为您查到订单") == 1


def test_customer_rag_golden_main_outputs_json(capsys) -> None:
    exit_code = golden_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_customer_rag_golden_main_outputs_summary(capsys) -> None:
    exit_code = golden_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "customer_rag_golden_cases status=passed" in output
    assert "failed=0" in output
