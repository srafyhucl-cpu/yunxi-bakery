"""版本号与项目进度表头同步测试。"""

from pathlib import Path

from scripts import sync_version

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_inject_version_updates_current_progress_header(
    monkeypatch,
    tmp_path: Path,
) -> None:
    progress_path = tmp_path / "progress.md"
    progress_path.write_text(
        "# 项目进度\n\n"
        "> 最后更新 2026-07-09 - 当前本地代码版本为 `0.105.13`。后续说明。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_version, "PROGRESS_FILE", progress_path)

    matched = sync_version.inject_version_to_progress("0.105.14")
    content = progress_path.read_text(encoding="utf-8")

    assert matched is True
    assert "当前本地代码版本为 `0.105.14`。后续说明。" in content


def test_inject_version_keeps_legacy_progress_header_compatible(
    monkeypatch,
    tmp_path: Path,
) -> None:
    progress_path = tmp_path / "legacy-progress.md"
    progress_path.write_text(
        "> 最后更新: 2026-07-09（第十次）— v0.105.13 历史说明。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_version, "PROGRESS_FILE", progress_path)

    matched = sync_version.inject_version_to_progress("0.105.14")
    content = progress_path.read_text(encoding="utf-8")

    assert matched is True
    assert "v0.105.14 历史说明。" in content


def test_inject_version_rejects_unknown_progress_header(
    monkeypatch,
    tmp_path: Path,
) -> None:
    progress_path = tmp_path / "unknown-progress.md"
    original_content = "# 没有版本标记的项目进度\n"
    progress_path.write_text(original_content, encoding="utf-8")
    monkeypatch.setattr(sync_version, "PROGRESS_FILE", progress_path)

    matched = sync_version.inject_version_to_progress("0.105.14")

    assert matched is False
    assert progress_path.read_text(encoding="utf-8") == original_content


def test_repository_progress_header_matches_version_file() -> None:
    version = (ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip()
    progress_header = "\n".join(
        (ROOT_DIR / "项目进度与配置清单.md")
        .read_text(encoding="utf-8")
        .splitlines()[:5]
    )

    assert f"当前本地代码版本为 `{version}`" in progress_header
