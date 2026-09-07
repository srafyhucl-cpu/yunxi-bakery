"""有赞商品 API 真实接口连通性与可行性测试。

凭证一律从环境变量读取，仓库内不得出现真实密钥字面量；
运行输出不得包含 secret、token、client_id 或带 token 的完整 URL；
失败返回非零退出码。
"""

import asyncio
import os
import tempfile


def _require_env(name: str) -> str:
    """读取必填环境变量，缺失直接失败并返回非零退出码。"""
    value = (os.environ.get(name) or "").strip()
    if not value:
        print(f"[ERROR] 缺少环境变量 {name}，拒绝使用内置凭证", flush=True)
        raise SystemExit(2)
    return value


def _redacted_host(url: str) -> str:
    """输出只保留接口路径，绝不输出带 token 的完整 URL。"""
    try:
        path = url.split("open.youzanyun.com", 1)[1]
    except IndexError:
        return "<youzan-api>"
    return "<youzan>" + path.split("?")[0]


async def test_youzan_product_feasibility() -> int:
    """执行连通性探测，返回进程退出码（0 成功，非零失败）。"""
    import httpx

    client_id = _require_env("YOUZAN_CLIENT_ID")
    client_secret = _require_env("YOUZAN_CLIENT_SECRET")
    kdt_id = _require_env("YOUZAN_KDT_ID")

    output_lines = ["=== [1. 启动有赞 API 真实连通性测试] ==="]
    auth_url = "https://open.youzanyun.com/auth/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            output_lines.append("正在请求 OAuth2 Token...")
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
            if (
                token_resp.status_code != 200
                or "data" not in token_data
                or "access_token" not in token_data["data"]
            ):
                output_lines.append(
                    f"[ERROR] 获取 Token 失败! HTTP 状态码: {token_resp.status_code}"
                )
                _write_file(output_lines)
                return 1

            access_token = token_data["data"]["access_token"]
            expires_in = token_data["data"].get("expires_in", 0)
            output_lines.append(f"[OK] 成功获取 Token! 授权有效期截止: {expires_in}")

        except Exception as exc:
            output_lines.append(f"[ERROR] 请求 Token 发生异常: {type(exc).__name__}")
            _write_file(output_lines)
            return 1

        api_url = (
            "https://open.youzanyun.com/api/youzan.items.onsale.get/3.0.0"
            f"?access_token={access_token}"
        )
        try:
            output_lines.append(f"正在请求在售商品列表 {_redacted_host(api_url)} ...")
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
            if "data" in api_data and "items" in api_data["data"]:
                data_obj = api_data["data"]
                count = data_obj.get("count", 0)
                items = data_obj.get("items", [])
                output_lines.append(
                    f"[OK] 商品列表拉取成功! 共找到 {count} 个在售商品。"
                )
                output_lines.append("=== [所有商品的别名(Alias)与详情链接精简列表] ===")
                for i, item in enumerate(items, 1):
                    title = item.get("title", "未知标题")
                    alias = item.get("alias", "无Alias")
                    detail_url = item.get("detail_url", "无原生链接")
                    output_lines.append(f"商品 {i}: {title}")
                    output_lines.append(f"    -> Alias: {alias}")
                    output_lines.append(f"    -> Detail URL: {detail_url}")
            else:
                output_lines.append("[ERROR] 有赞返回了异常结构或报错信息")
                _write_file(output_lines)
                return 1

        except Exception as exc:
            output_lines.append(
                f"[ERROR] 调用在售商品接口发生异常: {type(exc).__name__}"
            )
            _write_file(output_lines)
            return 1

    _write_file(output_lines)
    return 0


def _write_file(lines: list[str]) -> None:
    """写入系统临时目录，不污染仓库工作区，不含任何凭证。"""
    path = os.path.join(tempfile.gettempdir(), "youzan-feasibility-output.txt")
    content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    print("测试执行完毕，结果已写入系统临时目录 youzan-feasibility-output.txt")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(test_youzan_product_feasibility()))
