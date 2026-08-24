"""测试新的 8 意图分类"""

import sys
import asyncio
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def test():
    url = "http://127.0.0.1:7001/api/v1/admin/chat-test"
    headers = {"Authorization": "Bearer 100200"}

    tests = [
        ("🍰 商品咨询", {"content": "提拉米苏多少钱", "user_id": "t_product"}),
        ("📜 规则咨询", {"content": "可以开发票吗", "user_id": "t_policy"}),
        ("💰 运费费用", {"content": "运费多少钱", "user_id": "t_fee"}),
        ("🚚 配送履约", {"content": "明天下午能送到吗", "user_id": "t_delivery"}),
        ("🧾 订单办理", {"content": "给我开发票", "user_id": "t_order_service"}),
        ("😡 售后异常", {"content": "蛋糕塌了我要退款", "user_id": "t_after_sales"}),
        ("🙋 人工服务", {"content": "转人工", "user_id": "t_human"}),
        ("👋 闲聊其他", {"content": "你好呀", "user_id": "t_greeting"}),
        ("⚠️ 极端噪声(过滤)", {"content": "!!!🎂🍰???", "user_id": "t_noise"}),
        (
            "🙋 多意图交织(高优提升)",
            {
                "content": "你们蛋糕送过来全碎了，赶紧退款，叫你们真人客服出来解决！",
                "user_id": "t_complex",
            },
        ),
    ]

    async with httpx.AsyncClient() as c:
        for label, payload in tests:
            try:
                r = await c.post(url, json=payload, headers=headers, timeout=30)
                data = r.json()
                intent = {
                    1: "商品咨询",
                    2: "规则咨询",
                    3: "运费费用",
                    4: "配送履约",
                    5: "订单办理",
                    6: "售后异常",
                    7: "人工服务",
                    8: "闲聊其他",
                }.get(data.get("intent"), "?")
                reply = (data.get("reply") or "(无回复)")[:120]
                print(f"[{intent}] {label}")
                print(f"  -> {reply}")
                print()
            except Exception as exc:
                print(f"请求失败 {label}: {exc}")


asyncio.run(test())
