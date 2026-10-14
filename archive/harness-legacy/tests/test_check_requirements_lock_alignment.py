"""生产与开发依赖锁一致性测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import check_requirements_lock_alignment


def test_current_requirement_locks_are_aligned() -> None:
    report = check_requirements_lock_alignment.build_report()

    assert report["status"] == "passed", report["issues"]


def test_conflicting_shared_pin_is_rejected(tmp_path: Path) -> None:
    production = tmp_path / "requirements.txt"
    development = tmp_path / "requirements-dev.txt"
    development_input = tmp_path / "requirements-dev.in"
    production.write_text("Example_Package==1.0\n", encoding="utf-8")
    development.write_text("example-package==2.0\n", encoding="utf-8")
    development_input.write_text(
        "-c requirements.txt\n-r requirements.in\n", encoding="utf-8"
    )

    report = check_requirements_lock_alignment.build_report(
        production,
        development,
        development_input,
    )

    assert report["status"] == "failed"
    assert any("共享依赖版本不一致" in issue for issue in report["issues"])


def test_development_input_requires_production_constraint(tmp_path: Path) -> None:
    production = tmp_path / "requirements.txt"
    development = tmp_path / "requirements-dev.txt"
    development_input = tmp_path / "requirements-dev.in"
    production.write_text("example==1.0\n", encoding="utf-8")
    development.write_text("example==1.0\n", encoding="utf-8")
    development_input.write_text("-r requirements.in\n", encoding="utf-8")

    report = check_requirements_lock_alignment.build_report(
        production,
        development,
        development_input,
    )

    assert report["status"] == "failed"
    assert any("缺少生产锁约束" in issue for issue in report["issues"])
