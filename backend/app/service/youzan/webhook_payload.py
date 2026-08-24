"""有赞 Webhook 负载中的商品字段提取。"""

import json


def parse_item_id(payload: dict, msg_obj: dict | None = None) -> str | None:
    """按固定优先级从 Webhook 负载提取商品 ID。"""
    if msg_obj is None:
        msg_obj = {}

    item_id = msg_obj.get("item_id")
    if item_id:
        return str(item_id)

    msg_data = msg_obj.get("data", {})
    if isinstance(msg_data, str):
        try:
            msg_data = json.loads(msg_data)
        except Exception:
            msg_data = {}
    if isinstance(msg_data, dict):
        item_id = msg_data.get("item_id")
        if item_id:
            return str(item_id)

    payload_data = payload.get("data", {})
    if isinstance(payload_data, dict):
        item_id = payload_data.get("item_id")
        if item_id:
            return str(item_id)

    item_id = payload.get("item_id")
    if item_id:
        return str(item_id)

    raw_id = payload.get("id")
    if raw_id is not None:
        raw_id_str = str(raw_id)
        if raw_id_str.isdigit():
            return raw_id_str

    return None
