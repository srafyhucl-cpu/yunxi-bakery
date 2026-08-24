"""微信客服入队前消息去重缓存。"""

from collections import OrderedDict


class ProcessedMessageCache:
    """固定容量的消息 ID 缓存，用于拦截短时间内的重复推送。"""

    def __init__(self, max_size: int) -> None:
        if max_size <= 0:
            raise ValueError("max_size 必须大于 0")
        self._max_size = max_size
        self._message_ids: OrderedDict[str, None] = OrderedDict()

    def add_if_new(self, message_id: str) -> bool:
        """返回 True 表示首次出现，False 表示已存在。"""
        if not message_id:
            return True
        if message_id in self._message_ids:
            self._message_ids.move_to_end(message_id)
            return False

        self._message_ids[message_id] = None
        while len(self._message_ids) > self._max_size:
            self._message_ids.popitem(last=False)
        return True

    def __contains__(self, message_id: str) -> bool:
        return message_id in self._message_ids

    def __len__(self) -> int:
        return len(self._message_ids)
