"""打印作业仓库测试。"""

import aiosqlite

from app.models.print_job import OrderPrintJob
from app.repository.print_job_repo import PrintJobRepo

ORDER_ID = "order_print_repo_001"


def _job(
    job_id: str,
    *,
    key: str,
    status: str = "PENDING",
    ticket_type: str = "CAKE_KITCHEN",
) -> OrderPrintJob:
    return OrderPrintJob(
        id=job_id,
        order_id=ORDER_ID,
        ticket_type=ticket_type,
        status=status,
        provider="mock",
        printer_id="",
        attempts=0,
        last_error="",
        provider_job_id="",
        idempotency_key=key,
        payload_snapshot='{"content": "test"}',
        operator="tester",
        created_at="2026-10-19 10:00:00",
        updated_at="2026-10-19 10:00:00",
    )


async def test_create_job_is_idempotent_by_key(db: aiosqlite.Connection) -> None:
    """同一幂等键只新建一条作业。"""
    repo = PrintJobRepo(db)

    assert await repo.create_job(_job("job_1", key="order:o1:CAKE_KITCHEN:v1")) is True
    assert await repo.create_job(_job("job_2", key="order:o1:CAKE_KITCHEN:v1")) is False

    jobs = await repo.list_for_order(ORDER_ID)
    assert [job.id for job in jobs] == ["job_1"]


async def test_mark_claimed_uses_cas(db: aiosqlite.Connection) -> None:
    """只有 PENDING/FAILED 能被领取，重复领取失败。"""
    repo = PrintJobRepo(db)
    await repo.create_job(_job("job_1", key="key_1"))

    assert await repo.mark_claimed("job_1", "2026-10-19 10:01:00") is True
    assert await repo.mark_claimed("job_1", "2026-10-19 10:02:00") is False
    job = await repo.get_job("job_1")
    assert job is not None
    assert job.status == "CLAIMED"

    await repo.mark_failed("job_1", "网络超时")
    assert await repo.mark_claimed("job_1", "2026-10-19 10:03:00") is True


async def test_mark_result_and_printed_record_explicit_fields(
    db: aiosqlite.Connection,
) -> None:
    """结果写回显式记录状态、云端作业号、尝试次数与出纸时间。"""
    repo = PrintJobRepo(db)
    await repo.create_job(_job("job_1", key="key_1"))

    assert (
        await repo.mark_result(
            "job_1",
            "SUBMITTED",
            "feieyun-001",
            "",
            1,
            updated_at="2026-10-19 10:01:00",
        )
        is True
    )
    job = await repo.get_job("job_1")
    assert job is not None
    assert job.status == "SUBMITTED"
    assert job.provider_job_id == "feieyun-001"
    assert job.attempts == 1

    assert await repo.mark_printed("job_1", "feieyun-001", "2026-10-19 10:02:00")
    job = await repo.get_job("job_1")
    assert job is not None
    assert job.status == "PRINTED"
    assert job.printed_at == "2026-10-19 10:02:00"


async def test_reprint_creates_new_job_without_touching_original(
    db: aiosqlite.Connection,
) -> None:
    """补打使用新幂等键新建作业，原作业状态保持不变。"""
    repo = PrintJobRepo(db)
    await repo.create_job(_job("job_1", key="order:o1:CAKE_KITCHEN:v1"))
    await repo.mark_mocked("job_1", "mock-001")

    assert await repo.create_job(_job("job_2", key="order:o1:CAKE_KITCHEN:reprint:x"))
    jobs = await repo.list_for_order(ORDER_ID)
    assert {job.id for job in jobs} == {"job_1", "job_2"}
    original = await repo.get_job("job_1")
    assert original is not None
    assert original.status == "MOCKED"


async def test_list_pending_and_failed_limit(db: aiosqlite.Connection) -> None:
    """待处理与失败列表按状态过滤并支持上限。"""
    repo = PrintJobRepo(db)
    for index in range(3):
        await repo.create_job(_job(f"pending_{index}", key=f"pending_{index}"))
    await repo.create_job(_job("failed_1", key="failed_1", status="FAILED"))

    assert len(await repo.list_pending(2)) == 2
    failed = await repo.list_failed(10)
    assert [job.id for job in failed] == ["failed_1"]
