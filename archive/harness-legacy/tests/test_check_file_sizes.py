"""文件体量责任优先治理测试。"""

from pathlib import Path

from scripts import check_file_sizes

ROOT_DIR = Path(__file__).resolve().parents[2]
FILE_SIZE_SKILL_PATH = (
    ROOT_DIR / ".agents" / "skills" / "yunxi-file-size-guard" / "SKILL.md"
)
FILE_SIZE_ADR_PATH = (
    ROOT_DIR
    / "docs"
    / "harness-engineering"
    / "adr"
    / "0004-responsibility-first-file-size-governance.md"
)
CHECK_PROJECT_PATH = ROOT_DIR / "scripts" / "check_project.py"
PRECOMMIT_PATH = ROOT_DIR / ".pre-commit-config.yaml"


def test_oversize_review_notes_explain_responsibility() -> None:
    assert check_file_sizes.OVERSIZE_REVIEW_NOTES
    for path, review_note in check_file_sizes.OVERSIZE_REVIEW_NOTES.items():
        assert path.startswith("app/")
        assert "职责" in review_note
        assert len(review_note.strip()) >= 20


def test_unreviewed_oversize_guidance_rejects_mechanical_splitting() -> None:
    guidance = check_file_sizes.UNREVIEWED_OVERSIZE_GUIDANCE

    assert "职责评审" in guidance
    assert "职责混杂" in guidance
    assert "职责高度内聚" in guidance
    assert "禁止为了压行数机械切文件" in guidance


def test_file_size_skill_and_adr_use_responsibility_first_contract() -> None:
    skill_content = FILE_SIZE_SKILL_PATH.read_text(encoding="utf-8")
    adr_content = FILE_SIZE_ADR_PATH.read_text(encoding="utf-8")
    project_check_content = CHECK_PROJECT_PATH.read_text(encoding="utf-8")
    precommit_content = PRECOMMIT_PATH.read_text(encoding="utf-8")

    required_phrases = (
        "行数阈值是评审触发器，不是拆分目标",
        "禁止为了让门禁变绿",
        "split_by_responsibility",
        "keep_cohesive_with_review",
        "defer_with_boundary_plan",
    )
    for phrase in required_phrases:
        assert phrase in skill_content
        assert phrase in adr_content

    assert "函数职责评审信号" in project_check_content
    assert "不因行数自动要求拆分" in project_check_content
    assert "文件体量职责评审门禁" in precommit_content
    assert "职责混杂才拆" in precommit_content
