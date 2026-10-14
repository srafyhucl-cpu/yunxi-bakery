"""Harness P2 文档园艺扫描合同测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import check_doc_garden


def test_current_document_garden_has_no_error_findings() -> None:
    report = check_doc_garden.build_report()

    assert report["status"] == "passed", report["findings"]
    assert report["summary"]["errors"] == 0


def test_broken_link_is_detected(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("[失效](missing.md)\n", encoding="utf-8")
    (tmp_path / "PROJECT-STATE.md").write_text(
        "| task_id | status |\n", encoding="utf-8"
    )

    findings = check_doc_garden.scan_links(docs / "README.md", tmp_path)

    assert findings
    assert findings[0].rule == "broken_link"
