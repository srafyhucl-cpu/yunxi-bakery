from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from app.database import close_db, init_db
from app.models.customer_master import CustomerMasterCreate
from app.repository.customer_master_repo import CustomerMasterRepo

SCRIPT_NAME = "preimport_youzan_customer_openids"


def load_script_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / f"{SCRIPT_NAME}.py"
    spec = importlib.util.spec_from_file_location(SCRIPT_NAME, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _seed_database(db_path: Path) -> None:
    conn = await init_db(str(db_path))
    try:
        repo = CustomerMasterRepo(conn)
        for phone in ("13800138000", "13900139000", "13700137000"):
            await repo.create_master(
                CustomerMasterCreate(
                    tenant_id="yunxi",
                    primary_phone=phone,
                    display_name="测试客户",
                    phone_verified=1,
                )
            )
        await repo.create_master(
            CustomerMasterCreate(
                tenant_id="yunxi", primary_phone="", display_name="弱身份"
            )
        )
    finally:
        await close_db(conn)


async def _count_openid_links(db_path: Path) -> int:
    conn = await init_db(str(db_path))
    try:
        repo = CustomerMasterRepo(conn)
        masters = await repo.list_masters_with_primary_phone("yunxi")
        total = 0
        for master in masters:
            links = await repo.list_identity_links(master.id)
            total += sum(1 for link in links if link.identity_type == "miniapp_openid")
        return total
    finally:
        await close_db(conn)


async def test_dry_run_queries_without_writing(tmp_path: Path, monkeypatch) -> None:
    script = load_script_module()
    monkeypatch.setattr(script.settings, "YOUZAN_MOCK_MODE", True)
    db_path = tmp_path / "bot.db"
    await _seed_database(db_path)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi", "--json"]
    )

    assert exit_code == 0
    assert await _count_openid_links(db_path) == 0


async def test_dry_run_report_stats(tmp_path: Path, monkeypatch, capsys) -> None:
    script = load_script_module()
    monkeypatch.setattr(script.settings, "YOUZAN_MOCK_MODE", True)
    db_path = tmp_path / "bot.db"
    await _seed_database(db_path)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "total_phones=3" in output
    assert "queried=3" in output
    assert "matched_openid=3" in output
    assert "created=3" in output
    assert "hit_rate=1.0" in output


async def test_limit_controls_queried_count(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    script = load_script_module()
    monkeypatch.setattr(script.settings, "YOUZAN_MOCK_MODE", True)
    db_path = tmp_path / "bot.db"
    await _seed_database(db_path)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi", "--limit", "1"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "total_phones=3" in output
    assert "queried=1" in output
    assert "matched_openid=1" in output


async def test_apply_writes_links_and_rerun_is_idempotent(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    script = load_script_module()
    monkeypatch.setattr(script.settings, "YOUZAN_MOCK_MODE", True)
    db_path = tmp_path / "bot.db"
    await _seed_database(db_path)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi", "--apply"]
    )
    assert exit_code == 0
    assert await _count_openid_links(db_path) == 3

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi", "--apply"]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "already_linked=3" in output
    assert "created=0" in output


async def test_skip_linked_skips_existing(tmp_path: Path, monkeypatch, capsys) -> None:
    script = load_script_module()
    monkeypatch.setattr(script.settings, "YOUZAN_MOCK_MODE", True)
    db_path = tmp_path / "bot.db"
    await _seed_database(db_path)

    exit_code = await script.async_main(
        ["--db-path", str(db_path), "--tenant-id", "yunxi", "--apply"]
    )
    assert exit_code == 0

    exit_code = await script.async_main(
        [
            "--db-path",
            str(db_path),
            "--tenant-id",
            "yunxi",
            "--skip-linked",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "skipped_linked=3" in output
    assert "queried=0" in output
