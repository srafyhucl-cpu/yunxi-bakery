"""有赞云 API/Webhook 异步仿真器。

提供完全解耦、不依赖线上真实实名认证的有赞 API 与 Webhook 仿真数据生成、签名计算和客户端 Mock 拦截。
"""

import hashlib
import json
import time


class YouzanMockEmulator:
    """有赞异步仿真器。"""

    @staticmethod
    def calculate_signature(client_id: str, client_secret: str, raw_body: bytes) -> str:
        """根据有赞 Webhook 规范计算签名：MD5(client_id + raw_body + client_secret)。"""
        return hashlib.md5(
            (
                client_id + raw_body.decode("utf-8", errors="replace") + client_secret
            ).encode()
        ).hexdigest()

    @staticmethod
    def generate_webhook_message(
        buyer_id: str,
        content_text: str,
        msg_type: str = "text",
        msg_id: str | None = None,
        client_id: str = "mock_client_id",
        client_secret: str = "mock_secret",
    ) -> tuple[bytes, str]:
        """生成有赞买家端客服消息推送 Webhook Payload 及对应的 event-sign 签名。"""
        actual_msg_id = msg_id or f"msg_{int(time.time() * 1000)}"
        payload = {
            "msg_id": actual_msg_id,
            "buyer_id": buyer_id,
            "msg_type": msg_type,
            "content": {"text": content_text} if msg_type == "text" else content_text,
            "timestamp": int(time.time()),
        }
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        signature = YouzanMockEmulator.calculate_signature(
            client_id, client_secret, raw_body
        )
        return raw_body, signature

    @staticmethod
    def get_mock_order_response(order_no: str) -> dict:
        """生成仿真有赞订单详情数据（结构与 youzan.trade.get 4.0.0 真实响应对齐）。"""
        return {
            "gw_err_resp": None,
            "data": {
                "full_order_info": {
                    "order_info": {
                        "tid": order_no,
                        "status": "WAIT_SELLER_SEND_GOODS",
                        "status_str": "待发货",
                        "pay_time": "2026-05-19 12:00:00",
                        "consign_time": "",
                        "created": "2026-05-19 11:58:00",
                        "pay_type_str": "微信支付",
                        "express_type": 1,
                        "refund_state": 0,
                    },
                    "pay_info": {
                        "payment": "188.00",
                        "total_fee": "188.00",
                        "post_fee": "0.00",
                    },
                    "buyer_info": {
                        "buyer_id": "63889",
                        "outer_user_id": "wx_mock_user_001",
                    },
                    "address_info": {
                        "delivery_province": "上海",
                        "delivery_city": "上海市",
                        "delivery_district": "浦东新区",
                        "delivery_address": "碧波路 888 号",
                        "delivery_start_time": "",
                    },
                    "orders": [
                        {
                            "oid": "mock_oid_001",
                            "item_id": 5836487486,
                            "alias": "mock5836487486",
                            "title": "皇家草莓双层奶油蛋糕 (6寸)",
                            "num": 1,
                            "price": "188.00",
                            "payment": "188.00",
                            "sku_properties_name": "6寸",
                            "buyer_messages": "",
                        }
                    ],
                }
            },
        }

    @staticmethod
    def get_mock_logistics_response(order_no: str) -> dict:
        """生成仿真有赞物流跟踪数据。"""
        return {
            "gw_err_resp": None,
            "response": {
                "express_id": "SF1234567890",
                "express_name": "顺丰速运",
                "transit_step_infos": [
                    {
                        "status_time": "2026-05-19 14:00:00",
                        "status_desc": "【上海市】已揽收，正发往投递站",
                    },
                    {
                        "status_time": "2026-05-19 18:00:00",
                        "status_desc": "【上海市】快件已到达浦东张江分拨中心",
                    },
                ],
            },
        }

    @staticmethod
    def get_mock_user_info_response(mobile: str) -> dict:
        """生成仿真有赞用户信息查询响应（结构对齐 youzan.users.info.query 1.0.0）。"""
        return {
            "success": True,
            "code": 200,
            "data": {
                "user_list": [
                    {
                        "mobile_info": {"countryCode": "+86", "mobile": mobile},
                        "platform_info": {"weixin_open_id": f"oMock{mobile[-6:]}"},
                        "wechat_info": {
                            "wechat_type": 2,
                            "union_id": f"oUnion{mobile[-6:]}",
                            "is_fans": 1,
                        },
                        "primitive_info": {"yz_open_id": f"mock_yz_{mobile[-6:]}"},
                    }
                ]
            },
        }

    @staticmethod
    def get_mock_product_response(item_id: int, alias: str) -> dict:
        """生成高保真的有赞单品规格与实时库存仿真响应。"""
        actual_item_id = item_id or 5836487486
        actual_alias = alias or f"mock{actual_item_id}"
        return {
            "gw_err_resp": None,
            "response": {
                "item": {
                    "item_id": actual_item_id,
                    "title": "小山园抹茶千层（有蜜豆）",
                    "alias": actual_alias,
                    "price": 28800,
                    "quantity": 150,
                    "sold_num": 88,
                    "image": "https://img.yzcdn.cn/upload_files/2026/05/14/FqQM5g15ANOfnStSH3eNgGmTc0Mw.jpg",
                    "desc": "<p>选用京都宇治若竹抹茶粉，层层细腻手作千层皮，搭配手熬软糯蜜红豆夹心。进口安佳淡奶油调配，抹茶微苦奶油清甜，绝妙交融。建议0-4℃冷藏，保质期3天，四寸、六寸均可现场预定制作。</p>",
                    "tags": "抹茶千层, 蜜红豆夹心, 下午茶爆款",
                    "skus": [
                        {
                            "sku_id": 999111,
                            "price": 28800,
                            "quantity": 150,
                            "properties_name_json": '[{"k":"规格","v":"6寸"}]',
                        }
                    ],
                }
            },
        }
