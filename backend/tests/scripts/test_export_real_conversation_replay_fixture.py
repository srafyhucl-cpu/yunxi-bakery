"""脱敏真实会话 replay 导出脚本测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import (
    check_real_conversation_replay,
    export_real_conversation_replay_fixture,
)


def test_export_real_conversation_replay_fixture_redacts_and_validates(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "records.json"
    output_path = tmp_path / "fixture.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "case_id": "conv-13800138000",
                        "golden_case_id": "customer-refund-sensitive-001",
                        "source": "support_export",
                        "group": "refund_after_sales",
                        "intent": "faq_after_sales",
                        "user_message": (
                            "用户手机号 13800138000，完整订单号 202607100000001，"
                            "收货地址 上海市浦东新区测试路88号，问退款多久到。"
                        ),
                        "final_reply": (
                            "退款需要按订单状态和制作进度确认，我先帮您记录诉求并转人工核对。"
                        ),
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = export_real_conversation_replay_fixture.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    result = check_real_conversation_replay.build_real_conversation_replay_result(
        replay_fixture_path=output_path,
    )
    exported_case = payload["cases"][0]

    assert exit_code == 0
    assert payload["metadata"]["contains_sensitive_data"] is False
    assert payload["metadata"]["input_record_count"] == 1
    assert exported_case["case_id"] == "conv"
    assert "13800138000" not in exported_case["user_message"]
    assert "202607100000001" not in exported_case["user_message"]
    assert "完整订单号" not in exported_case["user_message"]
    assert "收货地址" not in exported_case["user_message"]
    assert result.status == "passed"


def test_export_real_conversation_replay_fixture_supports_jsonl(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "golden_case_id": "customer-inventory-sensitive-001",
                "query": "用户问库存，平台ID open_id=abc123 已出现。",
                "reply": "库存会随门店销售变化，建议以下单页面和门店确认为准。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = export_real_conversation_replay_fixture.build_replay_fixture_payload(
        input_path,
        source="jsonl_export",
    )

    assert payload["metadata"]["source"] == "jsonl_export"
    assert payload["cases"][0]["case_id"] == "real-export-001"
    assert "open_id" not in payload["cases"][0]["user_message"]
    assert "abc123" not in payload["cases"][0]["user_message"]


def test_export_real_conversation_replay_fixture_requires_golden_case_id(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "user_message": "用户问退款，内容已脱敏。",
                    "final_reply": "需要人工核对。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="golden_case_id"):
        export_real_conversation_replay_fixture.build_replay_fixture_payload(input_path)
