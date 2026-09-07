"""边缘防护共享 Redis 后端：限流窗口与登录失败计数。

SQLite 后端只覆盖明确的本地/单机模式；多机生产必须使用本共享后端。
全部状态变更使用 Lua 脚本保证原子性（含 TTL）。redis 客户端按需引入，
缺依赖或缺地址时实例化即抛配置错误，调用方 fail-closed。
"""

from app.exceptions import ConfigError

RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

LOGIN_ATTEMPT_LUA = """
local row = redis.call('HMGET', KEYS[1], 'fail_count', 'window_until')
local fails = tonumber(row[1]) or 0
local until_ts = tonumber(row[2]) or 0
local now_ts = tonumber(ARGV[1])
local max_attempts = tonumber(ARGV[2])
if until_ts > now_ts and fails >= max_attempts then
  return {0, fails}
end
local new_fails = 1
if until_ts > now_ts then
  new_fails = fails + 1
end
redis.call('HSET', KEYS[1], 'fail_count', new_fails, 'window_until', ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return {1, new_fails}
"""


class RedisEdgeProtectionRepo:
    """基于共享 Redis 的限流与登录保护读写。"""

    def __init__(self, redis_url: str) -> None:
        if not (redis_url or "").strip():
            raise ConfigError("共享边缘防护缺少 EDGE_REDIS_URL，拒绝启动")
        try:
            import redis.asyncio as redis_asyncio  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigError("共享边缘防护缺少 redis 依赖，拒绝启动") from exc
        self._client = redis_asyncio.from_url(redis_url.strip(), decode_responses=True)

    async def check_request_allowed(
        self, client_key: str, now_seconds: int, window_seconds: int, limit: int
    ) -> bool:
        """固定窗口计数，原子递增，超限返回假。"""
        _ = now_seconds
        count = await self._client.eval(
            RATE_LIMIT_LUA, 1, f"edge:{client_key}", window_seconds
        )
        return int(count) <= int(limit)

    async def admin_login_allowed(
        self, client_key: str, now_seconds: int, max_attempts: int
    ) -> bool:
        """失败未超阈或窗口过期则放行。"""
        data = await self._client.hgetall(f"edge:login:{client_key}")
        if not data:
            return True
        if int(now_seconds) >= int(data.get("window_until", 0) or 0):
            return True
        return int(data.get("fail_count", 0) or 0) < int(max_attempts)

    async def record_admin_login_failure(
        self, client_key: str, now_seconds: int, window_seconds: int
    ) -> None:
        """记录一次登录失败，窗口过期则重置计数（兼容旧两步调用）。"""
        await self.check_and_record_login_attempt(
            client_key, now_seconds, window_seconds, 2**31
        )

    async def check_and_record_login_attempt(
        self, client_key: str, now_seconds: int, window_seconds: int, max_attempts: int
    ) -> bool:
        """单 Lua 脚本原子完成窗口判断、占用与 TTL，返回是否放行。"""
        allowed, _ = await self._client.eval(
            LOGIN_ATTEMPT_LUA,
            1,
            f"edge:login:{client_key}",
            now_seconds,
            max_attempts,
            now_seconds + window_seconds,
            window_seconds,
        )
        return bool(int(allowed) == 1)

    async def clear_admin_login_failures(self, client_key: str) -> None:
        """成功登录后清理失败计数。"""
        await self._client.delete(f"edge:login:{client_key}")
