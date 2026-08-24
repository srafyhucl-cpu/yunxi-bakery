import aiosqlite

from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo


async def test_wecom_kf_sync_state_success_and_failure(
    db: aiosqlite.Connection,
) -> None:
    repo = WecomKfSyncRepo(db)

    empty_state = await repo.get_state("kf-1")
    await repo.mark_syncing("kf-1")
    await repo.mark_failed("kf-1", "temporary error")
    failed_state = await repo.get_state("kf-1")
    await repo.mark_success("kf-1", "cursor-2")
    success_state = await repo.get_state("kf-1")

    assert empty_state.last_cursor == ""
    assert failed_state.status == "failed"
    assert failed_state.retry_count == 1
    assert failed_state.last_error == "temporary error"
    assert success_state.status == "idle"
    assert success_state.last_cursor == "cursor-2"
    assert success_state.retry_count == 0


async def test_wecom_kf_message_ledger_is_idempotent(
    db: aiosqlite.Connection,
) -> None:
    repo = WecomKfSyncRepo(db)

    first = await repo.add_message_if_new(
        msg_id="msg-1",
        open_kfid="kf-1",
        external_userid="user-1",
        origin=3,
        msgtype="text",
        event_type="",
        process_action="route_customer",
    )
    second = await repo.add_message_if_new(
        msg_id="msg-1",
        open_kfid="kf-1",
        external_userid="user-1",
        origin=3,
        msgtype="text",
        event_type="",
        process_action="route_customer",
    )

    assert first is True
    assert second is False
