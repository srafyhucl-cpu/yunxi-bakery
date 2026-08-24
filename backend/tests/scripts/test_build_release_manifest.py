"""发布 manifest 构建合同测试。"""

from pathlib import Path

import pytest

from scripts import build_release_manifest


def _write_fixture(root_dir: Path) -> list[Path]:
    (root_dir / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    source_path = root_dir / "app.py"
    source_path.write_text("print('fixture')\n", encoding="utf-8")
    return [root_dir / "VERSION", source_path]


def test_manifest_contains_exact_commit_version_and_hashes(tmp_path: Path) -> None:
    files = _write_fixture(tmp_path)

    payload = build_release_manifest.build_release_manifest(
        tmp_path,
        commit="a" * 40,
        files=files,
    )

    assert payload["commit"] == "a" * 40
    assert payload["version"] == "1.2.3"
    assert {entry["path"] for entry in payload["files"]} == {"VERSION", "app.py"}
    assert all(len(entry["sha256"]) == 64 for entry in payload["files"])


def test_manifest_rejects_short_commit(tmp_path: Path) -> None:
    files = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="40 位完整 SHA"):
        build_release_manifest.build_release_manifest(
            tmp_path,
            commit="short",
            files=files,
        )


def test_manifest_refuses_overwrite(tmp_path: Path) -> None:
    files = _write_fixture(tmp_path)
    output_path = tmp_path / "manifest.json"
    output_path.write_text("existing", encoding="utf-8")
    payload = build_release_manifest.build_release_manifest(
        tmp_path,
        commit="b" * 40,
        files=files,
    )

    with pytest.raises(FileExistsError):
        build_release_manifest.write_manifest(output_path, payload)
    assert output_path.read_text(encoding="utf-8") == "existing"
