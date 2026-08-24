"""有赞商品 API 真实接口连通性与可行性测试。"""

import asyncio
import httpx


async def test_youzan_product_feasibility() -> None:
    # 1. 真实配置信息
    client_id = "889f26abda62ebffe0"
    client_secret = "34ac2d72b65537e210f6f9e81b5eb1c7"
    kdt_id = "131707202"

    # 用来收集所有输出文本
    output_lines = []
    output_lines.append("=== [1. 启动有赞 API 真实连通性测试] ===")
    output_lines.append(f"kdt_id: {kdt_id}")
    output_lines.append(f"client_id: {client_id}")

    # 2. 获取 Access Token (OAuth2 silent grant)
    auth_url = "https://open.youzanyun.com/auth/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            output_lines.append("\n正在请求 OAuth2 Token...")
            token_resp = await client.post(
                auth_url,
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "authorize_type": "silent",
                    "grant_id": kdt_id,
                },
            )
            token_data = token_resp.json()
            # 判断是否成功获取 Token
            if (
                token_resp.status_code != 200
                or "data" not in token_data
                or "access_token" not in token_data["data"]
            ):
                output_lines.append(
                    f"[ERROR] 获取 Token 失败! HTTP 状态码: {token_resp.status_code}"
                )
                output_lines.append(f"响应内容: {token_data}")
                _write_file(output_lines)
                return

            access_token = token_data["data"]["access_token"]
            expires_in = token_data["data"].get("expires", 0)
            output_lines.append(f"[OK] 成功获取 Token! 授权有效期截止: {expires_in}")

        except Exception as exc:
            output_lines.append(f"[ERROR] 请求 Token 发生异常: {exc}")
            _write_file(output_lines)
            return

        # 3. 调用商品列表 API (youzan.items.onsale.get)
        api_url = f"https://open.youzanyun.com/api/youzan.items.onsale.get/3.0.0?access_token={access_token}"
        try:
            output_lines.append(
                "\n正在请求有赞在售商品列表 (youzan.items.onsale.get/3.0.0)..."
            )
            api_resp = await client.post(
                api_url,
                json={
                    "kdt_id": kdt_id,
                    "page_no": 1,
                    "page_size": 10,
                },
            )
            api_data = api_resp.json()

            output_lines.append(f"HTTP 状态码: {api_resp.status_code}")
            # 最新版的商品接口直接返回 code = 200 以及 data
            if "data" in api_data and "items" in api_data["data"]:
                data_obj = api_data["data"]
                count = data_obj.get("count", 0)
                items = data_obj.get("items", [])
                output_lines.append(
                    f"[OK] 商品列表拉取成功! 共找到 {count} 个在售商品。"
                )

                output_lines.append(
                    "\n=== [所有商品的别名(Alias)与详情链接(Detail URL)精简列表] ==="
                )
                for i, item in enumerate(items, 1):
                    title = item.get("title", "未知标题")
                    alias = item.get("alias", "无Alias")
                    detail_url = item.get("detail_url", "无原生链接")
                    output_lines.append(f"商品 {i}: {title}")
                    output_lines.append(f"    -> Alias: {alias}")
                    output_lines.append(f"    -> Detail URL: {detail_url}")

            else:
                output_lines.append("[ERROR] 有赞返回了异常结构或报错信息:")
                output_lines.append(str(api_data))

        except Exception as exc:
            output_lines.append(f"[ERROR] 调用在售商品接口发生异常: {exc}")

    _write_file(output_lines)


def _write_file(lines: list[str]) -> None:
    """以 UTF-8 编码安全地写入本地 output.txt 中，绝不发生 GBK 编码报错。"""
    content = "\n".join(lines)
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ 测试执行完毕，结果已安全写入本地 output.txt 文件！")


if __name__ == "__main__":
    asyncio.run(test_youzan_product_feasibility())
