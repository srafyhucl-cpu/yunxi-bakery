from app.service.wecom.processed_message_cache import ProcessedMessageCache


def test_cache_rejects_duplicate_message_id() -> None:
    cache = ProcessedMessageCache(max_size=2)

    assert cache.add_if_new("msg-1") is True
    assert cache.add_if_new("msg-1") is False
    assert len(cache) == 1


def test_cache_evicts_least_recent_message_id() -> None:
    cache = ProcessedMessageCache(max_size=2)

    assert cache.add_if_new("msg-1") is True
    assert cache.add_if_new("msg-2") is True
    assert cache.add_if_new("msg-1") is False
    assert cache.add_if_new("msg-3") is True

    assert "msg-1" in cache
    assert "msg-2" not in cache
    assert "msg-3" in cache
    assert len(cache) == 2


def test_cache_rejects_invalid_capacity() -> None:
    try:
        ProcessedMessageCache(max_size=0)
    except ValueError as exc:
        assert "max_size" in str(exc)
    else:
        raise AssertionError("容量为 0 时应抛出 ValueError")
