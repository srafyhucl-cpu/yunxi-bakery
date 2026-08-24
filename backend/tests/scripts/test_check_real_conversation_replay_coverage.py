"""脱敏真实会话 replay 覆盖率检查测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_real_conversation_replay_coverage


def test_real_conversation_replay_coverage_sample_passes() -> None:
    report = check_real_conversation_replay_coverage.build_real_replay_coverage_report(
        replay_fixture_path=Path(
            "tests/fixtures/customer_real_replay_coverage_sample.json"
        ),
    )

    assert report["status"] == "passed"
    assert report["total"] == 6
    assert report["failed"] == 0
    assert {
        item["scenario"]: item["total"] for item in report["scenario_coverage"]
    } == {
        "order": 6,
        "refund": 6,
        "after_sales": 8,
        "inventory": 5,
        "price": 6,
        "human_transfer": 16,
    }


def test_real_conversation_replay_coverage_fails_when_below_threshold() -> None:
    report = check_real_conversation_replay_coverage.build_real_replay_coverage_report(
        replay_fixture_path=Path("tests/fixtures/customer_real_replay_sample.json"),
        min_per_scenario=5,
    )

    assert report["status"] == "failed"
    assert report["failed"] == 6
    assert all(not item["passed"] for item in report["scenario_coverage"])


def test_real_conversation_replay_coverage_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "coverage.json"

    exit_code = check_real_conversation_replay_coverage.main(
        [
            "--fixture",
            "tests/fixtures/customer_real_replay_coverage_sample.json",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["min_per_scenario"] == 5
