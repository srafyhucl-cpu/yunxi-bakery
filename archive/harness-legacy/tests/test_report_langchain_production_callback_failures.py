"""生产 callback 失败定位报告测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts import report_langchain_production_callback_failures as report_script


def test_blocks_when_runtime_version_is_not_current(tmp_path: Path) -> None:
    callback_path = tmp_path / "callback.json"
    handoff_path = tmp_path / "handoff.json"
    callback_path.write_text(
        report_script.json.dumps(build_callback_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    handoff_path.write_text(
        report_script.json.dumps(build_handoff_payload("failed"), ensure_ascii=False),
        encoding="utf-8",
    )

    report = report_script.build_callback_failure_report(
        callback_report_path=callback_path,
        handoff_report_path=handoff_path,
        today=date(2026, 7, 10),
    )

    assert report["status"] == "blocked"
    assert report["runtime"]["status"] == "failed"
    assert report["callback"]["failed"] == 2
    assert {failure["diagnosis_code"] for failure in report["failures"]} == {
        "runtime_version_not_current"
    }
    assert "先完成 P14c" in report["next_actions"][0]


def test_classifies_callback_failures_after_runtime_passes(tmp_path: Path) -> None:
    callback_path = tmp_path / "callback.json"
    handoff_path = tmp_path / "handoff.json"
    callback_path.write_text(
        report_script.json.dumps(build_callback_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    handoff_path.write_text(
        report_script.json.dumps(build_handoff_payload("passed"), ensure_ascii=False),
        encoding="utf-8",
    )

    report = report_script.build_callback_failure_report(
        callback_report_path=callback_path,
        handoff_report_path=handoff_path,
        today=date(2026, 7, 10),
    )
    failures = {failure["name"]: failure for failure in report["failures"]}

    assert report["status"] == "failed"
    assert failures["p2c-today-wait-buyer-confirm-list"]["diagnosis_code"] == (
        "data_dependent_empty_result"
    )
    assert failures["p2c-refund-policy-knowledge"]["diagnosis_code"] == (
        "production_knowledge_missing_or_old_retrieval"
    )
    assert failures["p2c-refund-policy-knowledge"]["expected"]["expected_intent"] == (
        "knowledge_answer"
    )


def test_main_writes_json_and_summary(tmp_path: Path, capsys) -> None:
    callback_path = tmp_path / "callback.json"
    handoff_path = tmp_path / "handoff.json"
    output_path = tmp_path / "diagnosis.json"
    callback_path.write_text(
        report_script.json.dumps(
            build_callback_payload(failed=False), ensure_ascii=False
        ),
        encoding="utf-8",
    )
    handoff_path.write_text(
        report_script.json.dumps(build_handoff_payload("passed"), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = report_script.main(
        [
            "--callback-report",
            str(callback_path),
            "--handoff-report",
            str(handoff_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert "langchain_production_callback_failures status=passed" in (
        capsys.readouterr().out
    )


def build_callback_payload(*, failed: bool = True) -> dict[str, object]:
    results: list[dict[str, object]] = []
    if failed:
        results.extend(
            [
                {
                    "name": "p2c-today-wait-buyer-confirm-list",
                    "query": "今天待收货订单有哪些",
                    "status_code": 200,
                    "passed": False,
                    "reply_valid": True,
                    "privacy_safe": True,
                    "semantic_safe": False,
                    "content_preview": "没有查到下单日期 2026-07-10、待收货的订单。",
                    "detail": "semantic rule mismatch",
                },
                {
                    "name": "p2c-refund-policy-knowledge",
                    "query": "退款规则是什么",
                    "status_code": 200,
                    "passed": False,
                    "reply_valid": True,
                    "privacy_safe": True,
                    "semantic_safe": False,
                    "content_preview": "未找到匹配知识。",
                    "detail": "semantic rule mismatch",
                },
            ]
        )
    return {
        "status": "failed" if failed else "passed",
        "metadata": {
            "base_url": "https://yunxifood.cn",
            "app_version": "0.98.0",
        },
        "total": len(results),
        "failed": len(results),
        "results": results,
        "failed_names": [result["name"] for result in results],
    }


def build_handoff_payload(runtime_status: str) -> dict[str, object]:
    return {
        "runtime_check": {
            "status": runtime_status,
            "expected_version": "0.100.0",
            "endpoint_versions": {
                "health": "0.100.0" if runtime_status == "passed" else "0.85.2",
                "ready": "0.100.0" if runtime_status == "passed" else "0.85.2",
            },
            "failed_names": [] if runtime_status == "passed" else ["health", "ready"],
        }
    }
