"""客户回复回放探针脚本测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scripts import check_customer_reply_replay, probe_customer_reply_replay


def test_probe_customer_reply_replay_writes_sensitive_replies(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "customer-replies.json"

    result_path = asyncio.run(probe_customer_reply_replay.main_async(output_path))
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert result_path == output_path
    assert payload["metadata"]["source"] == "probe_customer_reply_replay"
    assert len(payload["replies"]) == 30
    assert {record["source"] for record in payload["replies"]} == {
        "customer_graph_fake_model"
    }


def test_probe_customer_reply_replay_output_passes_replay_check(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "customer-replies.json"

    asyncio.run(
        probe_customer_reply_replay.main_async(
            output_path,
            case_ids=("customer-order-sensitive-001",),
        )
    )
    result = check_customer_reply_replay.build_customer_reply_replay_result(
        reply_json_path=output_path,
    )

    assert result.status == "passed"
    assert result.total == 30
    checked_case = next(
        case for case in result.cases if case.case_id == "customer-order-sensitive-001"
    )
    assert checked_case.metadata["reply_source"] == "input"
