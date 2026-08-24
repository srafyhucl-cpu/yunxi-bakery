"""消息历史重复报告脚本测试。"""

import sqlite3

from scripts.check_message_idempotency import find_duplicate_message_keys, main


def _create_messages_db(path, duplicate: bool) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE messages (id TEXT, channel_msg_id TEXT NOT NULL)"
        )
        rows = [("1", "msg-1")]
        if duplicate:
            rows.append(("2", "msg-1"))
        connection.executemany("INSERT INTO messages VALUES (?, ?)", rows)


def test_duplicate_report_is_ready_without_historical_duplicates(tmp_path) -> None:
    db_path = tmp_path / "clean.db"
    _create_messages_db(db_path, duplicate=False)

    assert find_duplicate_message_keys(db_path) == []
    assert main(["--db-path", str(db_path), "--json"]) == 0


def test_duplicate_report_fails_closed_with_historical_duplicates(tmp_path) -> None:
    db_path = tmp_path / "duplicate.db"
    _create_messages_db(db_path, duplicate=True)

    duplicates = find_duplicate_message_keys(db_path)
    assert duplicates == [{"channel_msg_id": "msg-1", "row_count": 2}]
    assert main(["--db-path", str(db_path)]) == 1
