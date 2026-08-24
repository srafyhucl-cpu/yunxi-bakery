"""脱敏真实会话回复回放脚本测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_customer_reply_replay, check_real_conversation_replay


def test_real_conversation_replay_sample_passes() -> None:
    result = check_real_conversation_replay.build_real_conversation_replay_result()

    assert result.status == "passed"
    assert result.total == 2
    assert result.metadata["contains_sensitive_data"] is False
    assert result.cases[0].metadata["golden_case_id"] == "customer-refund-sensitive-001"


def test_real_conversation_replay_rejects_privacy_patterns(
    tmp_path: Path,
) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        [
            {
                "case_id": "real-privacy-leak",
                "golden_case_id": "customer-inventory-sensitive-001",
                "user_message": "用户手机号 13800138000 想确认库存。",
                "final_reply": "库存需要以门店实时确认为准。",
            }
        ],
    )

    result = check_real_conversation_replay.build_real_conversation_replay_result(
        replay_fixture_path=fixture_path,
    )

    assert result.status == "failed"
    assert result.cases[0].metadata["privacy_hits"]


def test_real_conversation_replay_requires_sensitive_data_false(
    tmp_path: Path,
) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        [
            {
                "case_id": "real-sensitive-flag",
                "golden_case_id": "customer-inventory-sensitive-001",
                "user_message": "用户询问库存，内容已脱敏。",
                "final_reply": "库存需要以门店实时确认为准。",
            }
        ],
        contains_sensitive_data=True,
    )

    result = check_real_conversation_replay.build_real_conversation_replay_result(
        replay_fixture_path=fixture_path,
    )

    assert result.status == "failed"
    assert result.cases[0].assertions[0].name == "fixture.contains_sensitive_data_false"
    assert result.cases[0].assertions[0].passed is False


def test_real_conversation_replay_rejects_forbidden_reply(
    tmp_path: Path,
) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        [
            {
                "case_id": "real-forbidden-reply",
                "golden_case_id": "customer-order-sensitive-001",
                "user_message": "用户问订单状态，内容已脱敏。",
                "final_reply": "已为您查到订单，订单正在制作，不需要人工。",
            }
        ],
    )

    result = check_real_conversation_replay.build_real_conversation_replay_result(
        replay_fixture_path=fixture_path,
    )

    assert result.status == "failed"
    assert result.cases[0].metadata["matched_forbidden_patterns"] == [
        "已为您查到订单",
        "订单正在制作",
        "不需要人工",
    ]


def test_real_conversation_replay_exports_reply_replay_json(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "real-replay.json"
    replies_path = tmp_path / "replies.json"

    exit_code = check_real_conversation_replay.main(
        [
            "--json-out",
            str(output_path),
            "--replies-json-out",
            str(replies_path),
            "--summary",
        ]
    )
    reply_result = check_customer_reply_replay.build_customer_reply_replay_result(
        reply_json_path=replies_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    replies_payload = json.loads(replies_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert replies_payload["metadata"]["contains_sensitive_data"] is False
    assert {reply["case_id"] for reply in replies_payload["replies"]} == {
        "customer-refund-sensitive-001",
        "customer-inventory-sensitive-001",
    }
    assert reply_result.status == "passed"


def _write_fixture(
    tmp_path: Path,
    cases: list[dict[str, object]],
    *,
    contains_sensitive_data: bool = False,
) -> Path:
    fixture_path = tmp_path / "real-replay.json"
    fixture_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "source": "test",
                    "redaction": "unit_test",
                    "contains_sensitive_data": contains_sensitive_data,
                },
                "cases": cases,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture_path
