"""核对有赞 POINTS 死信与有赞当前积分，并把已确认失效的历史事件标记为已处理。

背景
----
生产 `inbox_events` 里还留着 53 条 `youzan_webhook` + `POINTS` 死信
（2026-08-14 ~ 2026-08-21）。这些事件携带的是 2026-08 的有赞积分权威快照，
而 `member_balance.youzan_points_base` 已经是 10 月的新锚点。直接回放会用
旧 `total` 覆盖新锚点：`backend/scripts/resolve_youzan_dead_letters.py` 实测
28 条会让 26 个会员合计减少约 1.09 万分（2026-10-20 复核为 10,935 分，
该数字随会员积分实时变动）。

本脚本只做两件事：

1. **只读核对**——把每条死信里的旧 `total` 与有赞**当前**积分逐户比对；
2. **可选归档**——`--apply` 时把核对通过的死信标记为 `processed`，
   并在 `last_error` 写入稳定原因码。

判定口径
--------
- 有赞当前积分 >= 旧事件 total：旧事件已被有赞现状覆盖（superseded），
  可归档，`last_error = superseded_by_youzan_current_points`；
- 有赞当前积分 < 旧事件 total：无法证明旧事件已被覆盖，列入 blocked，
  **禁止归档**（`--stale-policy sync-ok` 可在「本地锚点已等于有赞当前积分」
  这一条证据下按过期快照归档，理由码 `stale_youzan_points_decreased`）；
- 空手机号且本地查不到任何可关联账户：回放也改不动任何余额，
  归入 `archived_empty_mobile`，原因码 `archived_empty_mobile`；
- 本地无账户但有手机号：仍要查有赞当前积分，且必须与旧事件比对；
  查询失败、查不到数据或低于旧事件 total 一律 blocked，不猜、不伪造；
  只有「有赞当前积分 >= 旧事件 total」才归入 `archived_no_account`，
  只归档、不建档，原因码 `archived_no_account`。

`last_error` 里只会出现四个稳定原因码，便于后续审计直接比对：
`superseded_by_youzan_current_points`（有赞现状已覆盖旧事件）、
`archived_no_account`（有赞现状已覆盖，但本地无账户，只归档不建档）、
`archived_empty_mobile`（空手机号且无可关联账户，回放改不动余额）、
`stale_youzan_points_decreased`（有赞积分事后被花掉，本地锚点已同步）。

安全约束
--------
- 必须显式传 `--db`，脚本不猜测任何默认库路径；
- 默认 dry-run，只有 `--apply` 才写库；
- 路径疑似生产部署目录时必须额外传 `--allow-production`；
- dry-run 以 SQLite `mode=ro` 打开数据库，全程只读，不需要写权限；
- 任何一条 blocked 时 `--apply` 整体拒绝，不做部分写入，退出码非 0；
- 写库只有一种：把死信标记为 `processed` 并写原因码。不改 `payload_json`、
  不改 `member_balance`、不改 `points_ledger`。

有赞积分接口说明
----------------
本脚本经 `YouzanClient` 直接调用
`youzan.crm.customer.points.get/1.0.0`（`user.account_type=2` 即手机号，
响应取 `data.point`）。**没有**走
`app/service/youzan/member_api.py` 的 `YouzanMemberApi.query_points`：
本脚本需要原始响应体与网关错误明细，service 层只透出业务数据。
service 层的 `POINTS_QUERY_API_VERSION` 曾写成 `3.0.0`，会被有赞网关以
4005「非法的API」拒绝（2026-10-20 生产实测），返回值恒为空字典，
进而让 `scripts/import_member_loyalty.py` 把每个会员的积分锚点写成 0；
该版本已按本脚本的实测口径修正为 `1.0.0`。

用法
----
    # 只读核对（不写库）
    python scripts/reconcile_youzan_points_dead_letters.py --db /path/to/bot.db

    # 核对通过后归档
    python scripts/reconcile_youzan_points_dead_letters.py \
        --db /path/to/bot.db --apply

    # 指向生产路径时必须显式声明
    python scripts/reconcile_youzan_points_dead_letters.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import urllib.parse
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# 复用既有回放工具的生产路径判定与手机号脱敏口径，避免两套安全规则漂移。
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from resolve_youzan_dead_letters import (  # noqa: E402
    looks_like_production_path,
    mask_sensitive,
)

QUEUE_NAME = "youzan_webhook"
DEAD_LETTER_STATUS = "dead_letter"
ARCHIVE_TARGET_STATUS = "processed"
POINTS_EVENT_TYPE = "POINTS"
BUSINESS_TIMEOUT_MS = 15000
DEFAULT_API_TIMEOUT_SECONDS = 20.0
SAMPLE_LIMIT = 20
MAX_REASON_LENGTH = 500

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2

# ── 稳定原因码（写进 inbox_events.last_error，可被后续审计直接比对）──────
REASON_SUPERSEDED = "superseded_by_youzan_current_points"
REASON_NO_ACCOUNT = "archived_no_account"
REASON_EMPTY_MOBILE = "archived_empty_mobile"
REASON_STALE = "stale_youzan_points_decreased"

# ── 判定原因码（只出现在报告里，不写库）────────────────────────────────
REASON_YOUZAN_API_ERROR = "youzan_api_error"
REASON_YOUZAN_API_UNAVAILABLE = "youzan_api_unavailable"
REASON_YOUZAN_POINTS_UNKNOWN = "youzan_points_unknown"
REASON_YOUZAN_BELOW_EVENT_TOTAL = "youzan_points_below_event_total"
REASON_EMPTY_MOBILE_HAS_ACCOUNT = "empty_mobile_but_local_account_exists"
REASON_PAYLOAD_INVALID = "payload_invalid"
REASON_EVENT_TYPE_NOT_POINTS = "event_type_not_points"

# 归档分类
CATEGORY_SUPERSEDED = "superseded"
CATEGORY_STALE = "stale"
CATEGORY_EMPTY_MOBILE = "archived_empty_mobile"
CATEGORY_NO_ACCOUNT = "archived_no_account"
CATEGORY_BLOCKED = "blocked"

# 有赞「查询客户当前积分」API。
# 版本必须是 1.0.0：3.0.0 会被网关以 4005「非法的API」拒绝
# （2026-10-20 生产实测），调用结果恒为空字典。
# `app/service/youzan/member_api.py` 的同名常量原先正是 3.0.0，现已按本
# 脚本的实测口径修正为 1.0.0（取数请求体同为 user.account_type=2）。
# 本脚本按有赞开放平台 API 文档（doc 0/884）直接经 YouzanClient 调用，
# 以便拿到原始响应体与网关错误明细。
POINTS_QUERY_API_NAME = "youzan.crm.customer.points.get"
POINTS_QUERY_API_VERSION = "1.0.0"
# account_type：2=手机号（同上文档）
POINTS_ACCOUNT_TYPE_MOBILE = 2

# 有赞当前积分响应里可能出现的字段名，按可信度排序。
POINTS_FIELD_CANDIDATES = (
    "point",
    "points",
    "total_points",
    "total",
    "balance",
    "current_points",
    "points_total",
    "available_points",
)

# 日志统一走 stderr，保证 stdout 只有一份可被机器解析的 JSON 报告。
logger = logging.getLogger("yunxi_bot.reconcile_youzan_points_dead_letters")
logger.propagate = False


class TargetRejected(Exception):
    """目标库路径不满足安全前提。"""


class PointsFetcher(Protocol):
    """按手机号查询有赞当前积分的取数器。"""

    def prepare(self) -> None:
        """准备取数器（构造客户端、检查凭证）；失败时抛异常。"""

    async def fetch(self, mobile: str) -> int | None:
        """返回有赞当前积分；None 表示有赞侧查不到该会员的积分数据。"""

    async def aclose(self) -> None:
        """释放取数器占用的连接资源。"""


@dataclass(frozen=True)
class ParsedPointsPayload:
    """从死信载荷里解析出的 POINTS 关键字段。"""

    event_type: str
    mobile: str
    event_total: int | None
    unique_id: str
    yz_open_id: str
    reason: str


@dataclass(frozen=True)
class PointsDeadLetter:
    """一条 POINTS 死信 inbox 记录及其解析结果。"""

    row_id: int
    message_key: str
    payload_json: str
    last_error: str
    created_at: str
    event_type: str
    mobile: str
    event_total: int | None
    unique_id: str
    yz_open_id: str
    parse_reason: str


@dataclass(frozen=True)
class MemberAccount:
    """本地会员余额账户快照（只读）。"""

    account_id: int
    mobile: str
    points: int
    youzan_points_base: int
    yz_open_id: str


@dataclass(frozen=True)
class RowDecision:
    """单条死信的核对结论。"""

    row: PointsDeadLetter
    category: str
    confirmed: bool
    reason: str
    reason_detail: str
    account: MemberAccount | None
    account_source: str
    youzan_current: int | None

    @property
    def write_reason(self) -> str:
        """写进 last_error 的稳定原因码。"""
        if self.category == CATEGORY_SUPERSEDED:
            return REASON_SUPERSEDED
        if self.category == CATEGORY_STALE:
            return REASON_STALE
        if self.category == CATEGORY_EMPTY_MOBILE:
            return REASON_EMPTY_MOBILE
        return REASON_NO_ACCOUNT


@dataclass
class ReconciliationPlan:
    """整批死信的核对计划。"""

    dead_letter_total: int = 0
    points_total: int = 0
    decisions: list[RowDecision] = field(default_factory=list)
    out_of_scope: list[dict[str, object]] = field(default_factory=list)
    checked_mobiles: list[str] = field(default_factory=list)
    api_errors: list[dict[str, object]] = field(default_factory=list)
    api_unavailable: str = ""
    # 与 resolve_youzan_dead_letters.py 的 points_impact 同口径：
    # 重放旧事件会把本地锚点改小多少（只读预估，用于证明「不回放」的必要性）。
    backward_rows: int = 0
    backward_members: int = 0
    backward_points: int = 0

    @property
    def confirmed(self) -> list[RowDecision]:
        """核对通过、可归档的死信。"""
        return [item for item in self.decisions if item.confirmed]

    @property
    def blocked(self) -> list[RowDecision]:
        """被拦下、禁止归档的死信。"""
        return [item for item in self.decisions if not item.confirmed]


@dataclass
class ApplyOutcome:
    """一次写库执行的结果。"""

    archived: int = 0
    failures: list[dict[str, object]] = field(default_factory=list)
    committed: bool = False
    error: str = ""


def _configure_logging() -> None:
    """初始化脚本日志器，输出到 stderr。"""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def evaluate_target_guard(
    db_path: Path, *, allow_production: bool
) -> dict[str, object]:
    """校验目标库路径，返回防呆结论；不满足前提时抛 TargetRejected。"""
    production_like = looks_like_production_path(str(db_path))
    if production_like and not allow_production:
        raise TargetRejected(
            f"目标库路径疑似生产部署目录（{db_path}），"
            "必须显式传 --allow-production 才能继续"
        )
    if not db_path.is_file():
        raise TargetRejected(f"目标库文件不存在: {db_path}（本脚本不会创建数据库）")
    return {
        "production_like": production_like,
        "allow_production": allow_production,
    }


def _coerce_int(value: object) -> int | None:
    """严格解析整数；不可用时返回 None（区分「真 0」与「未知」）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def parse_points_payload(payload_json: str) -> ParsedPointsPayload:
    """解析死信载荷，取出事件类型、手机号、旧积分总额等字段。

    有赞把业务体放在 `body.msg`（URL 编码的 JSON 字符串）里，解析口径与
    `app/service/youzan/event_handler.py` 保持一致。
    """
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError) as exc:
        return ParsedPointsPayload("", "", None, "", "", f"invalid_json: {exc}")
    if not isinstance(payload, dict):
        return ParsedPointsPayload(
            "", "", None, "", "", f"payload_not_object: {type(payload).__name__}"
        )
    event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
    if not event_type:
        return ParsedPointsPayload("", "", None, "", "", "missing_event_type")
    body = payload.get("body")
    if isinstance(body, dict):
        raw_msg = body.get("msg")
    elif "msg" in payload:
        # 原始推送体直接放在载荷顶层时，载荷本身即业务体
        raw_msg = payload.get("msg")
    else:
        return ParsedPointsPayload(event_type, "", None, "", "", "missing_body")
    if isinstance(raw_msg, dict):
        msg = raw_msg
    else:
        try:
            msg = json.loads(urllib.parse.unquote(str(raw_msg or "")))
        except (TypeError, ValueError) as exc:
            return ParsedPointsPayload(
                event_type, "", None, "", "", f"msg_unparsable: {exc}"
            )
    if not isinstance(msg, dict):
        return ParsedPointsPayload(
            event_type, "", None, "", "", f"msg_not_object: {type(msg).__name__}"
        )
    mobile = str(msg.get("mobile") or "").strip()
    unique_id = str(msg.get("unique_id") or "").strip()
    yz_open_id = str(msg.get("yz_open_id") or msg.get("yzOpenId") or "").strip()
    event_total = _coerce_int(msg.get("total"))
    reason = "" if event_total is not None else "event_total_invalid"
    return ParsedPointsPayload(
        event_type, mobile, event_total, unique_id, yz_open_id, reason
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """判断目标库是否具备指定表。"""
    row = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _anchor_column(connection: sqlite3.Connection) -> str:
    """返回可用的外部权威锚点列名。

    `youzan_points_base` 是 v038 才加的列；老库没有该列时退回 `points`，
    保证脚本在老 schema 上也能只读运行而不报错。
    """
    # PRAGMA 不支持参数绑定，这里的表名/列名都是脚本内常量。
    for row in connection.execute("PRAGMA table_info(member_balance)"):
        if str(row[1]) == "youzan_points_base":
            return "youzan_points_base"
    return "points"


def fetch_dead_letters(connection: sqlite3.Connection) -> list[PointsDeadLetter]:
    """读取指定队列的全部死信，并解析出 POINTS 关键字段。"""
    rows = connection.execute(
        "SELECT id, message_key, payload_json, last_error, created_at "
        "FROM inbox_events "
        "WHERE queue_name = ? AND status = ? "
        "ORDER BY id",
        (QUEUE_NAME, DEAD_LETTER_STATUS),
    ).fetchall()
    result: list[PointsDeadLetter] = []
    for row in rows:
        parsed = parse_points_payload(str(row[2]))
        result.append(
            PointsDeadLetter(
                row_id=int(row[0]),
                message_key=str(row[1]),
                payload_json=str(row[2]),
                last_error=str(row[3] or ""),
                created_at=str(row[4] or ""),
                event_type=parsed.event_type,
                mobile=parsed.mobile,
                event_total=parsed.event_total,
                unique_id=parsed.unique_id,
                yz_open_id=parsed.yz_open_id,
                parse_reason=parsed.reason,
            )
        )
    return result


ACCOUNT_BY_MOBILE_SQL = (
    "SELECT id, mobile, points, youzan_points_base, yz_open_id "
    "FROM member_balance WHERE mobile = ? LIMIT 1"
)
ACCOUNT_BY_MOBILE_LEGACY_SQL = (
    "SELECT id, mobile, points, points, yz_open_id "
    "FROM member_balance WHERE mobile = ? LIMIT 1"
)
ACCOUNT_BY_OPENID_SQL = (
    "SELECT id, mobile, points, youzan_points_base, yz_open_id "
    "FROM member_balance WHERE yz_open_id = ? LIMIT 1"
)
ACCOUNT_BY_OPENID_LEGACY_SQL = (
    "SELECT id, mobile, points, points, yz_open_id "
    "FROM member_balance WHERE yz_open_id = ? LIMIT 1"
)


def _account_from_row(row: sqlite3.Row) -> MemberAccount:
    """把 member_balance 查询结果转成只读账户快照。"""
    return MemberAccount(
        account_id=int(row[0]),
        mobile=str(row[1] or ""),
        points=int(row[2] or 0),
        youzan_points_base=int(row[3] or 0),
        yz_open_id=str(row[4] or ""),
    )


def fetch_account_by_mobile(
    connection: sqlite3.Connection, mobile: str, anchor_column: str
) -> MemberAccount | None:
    """按手机号查本地会员余额账户。"""
    if not mobile:
        return None
    sql = (
        ACCOUNT_BY_MOBILE_SQL
        if anchor_column == "youzan_points_base"
        else ACCOUNT_BY_MOBILE_LEGACY_SQL
    )
    row = connection.execute(sql, (mobile,)).fetchone()
    return _account_from_row(row) if row is not None else None


def fetch_account_by_openid(
    connection: sqlite3.Connection, yz_open_id: str, anchor_column: str
) -> MemberAccount | None:
    """按有赞 openid 查本地会员余额账户。

    `mirror_youzan_points` 在手机号查不到账户时会按 openid 回退，
    因此「无账户」必须同时按手机号和 openid 两个口径确认。
    """
    if not yz_open_id:
        return None
    sql = (
        ACCOUNT_BY_OPENID_SQL
        if anchor_column == "youzan_points_base"
        else ACCOUNT_BY_OPENID_LEGACY_SQL
    )
    row = connection.execute(sql, (yz_open_id,)).fetchone()
    return _account_from_row(row) if row is not None else None


def detect_youzan_error(payload: object) -> str:
    """识别有赞响应里的错误，返回错误文案；正常时返回空串。

    有赞网关级错误（`gw_err_resp`）与业务错误（`success=false` /
    `code != 200`）都必须显式暴露：把它们当成「查不到数据」会让核对
    结论看起来像是「该会员没有积分」，属于伪造。
    """
    if not isinstance(payload, dict):
        return "response_not_object"
    gateway = payload.get("gw_err_resp") or payload.get("error_response")
    if isinstance(gateway, dict) and gateway:
        return (
            f"gateway_error: err_code={gateway.get('err_code')} "
            f"err_msg={gateway.get('err_msg')}"
        )
    if payload.get("success") is False:
        return f"api_error: code={payload.get('code')} message={payload.get('message')}"
    code = payload.get("code")
    if code is not None:
        try:
            if int(code) != 200:
                return f"api_error: code={code} message={payload.get('message')}"
        except (TypeError, ValueError):
            return f"api_error: unparsable_code={code!r}"
    return ""


def extract_youzan_points(payload: dict) -> int | None:
    """从有赞积分查询响应中提取当前积分；查不到时返回 None。

    兼容多种字段名与一层嵌套（`data.point` 是官方响应形状）；返回 None
    表示「有赞侧没有该会员的积分数据」，调用方必须据此判定为 blocked，
    不允许当作 0 处理。
    """
    if not isinstance(payload, dict) or not payload:
        return None
    for key in POINTS_FIELD_CANDIDATES:
        if key in payload:
            value = _coerce_int(payload.get(key))
            if value is not None:
                return value
    for nested in payload.values():
        if isinstance(nested, dict):
            found = extract_youzan_points(nested)
            if found is not None:
                return found
    return None


class YouzanPointsFetcher:
    """基于 `YouzanClient` 的有赞当前积分取数器。"""

    def __init__(self, app_root: Path, timeout_seconds: float) -> None:
        self._app_root = app_root
        self._timeout_seconds = timeout_seconds
        self._client = None

    def prepare(self) -> None:
        """构造有赞客户端并校验凭证；不可用时抛出明确异常。"""
        if self._client is not None:
            return
        if str(self._app_root) not in sys.path:
            sys.path.insert(0, str(self._app_root))
        from app.config import settings
        from app.service.youzan.client import YouzanClient

        if settings.YOUZAN_MOCK_MODE:
            raise RuntimeError(
                "有赞处于 Mock 模式（YOUZAN_MOCK_MODE=True），无法核对真实积分"
            )
        missing = [
            name
            for name in (
                "YOUZAN_CLIENT_ID",
                "YOUZAN_CLIENT_SECRET",
                "YOUZAN_KDT_ID",
            )
            if not str(getattr(settings, name, "") or "").strip()
        ]
        if missing:
            raise RuntimeError(f"有赞凭证未配置: {', '.join(missing)}")
        self._client = YouzanClient()
        logger.info(
            "有赞积分核对客户端就绪 api=%s/%s timeout=%ss",
            POINTS_QUERY_API_NAME,
            POINTS_QUERY_API_VERSION,
            self._timeout_seconds,
        )

    async def fetch(self, mobile: str) -> int | None:
        """查询单个会员的有赞当前积分。

        响应里的网关错误/业务错误一律抛异常，由调用方记为 api_error，
        绝不把「查询失败」当成「积分是 0」。
        """
        self.prepare()
        payload = await self._client.call_api(
            POINTS_QUERY_API_NAME,
            POINTS_QUERY_API_VERSION,
            {
                "user": {
                    "account_type": POINTS_ACCOUNT_TYPE_MOBILE,
                    "account_id": mobile,
                },
                "is_do_extpoint": False,
                "is_query_points_account_version": False,
                "need_expired_but_not_executed": False,
            },
        )
        error = detect_youzan_error(payload)
        if error:
            raise RuntimeError(f"有赞积分查询返回错误: {error}")
        logger.info(
            "有赞积分响应 mobile=%s keys=%s",
            mask_sensitive(mobile),
            sorted(payload.keys()) if isinstance(payload, dict) else "not_object",
        )
        return extract_youzan_points(payload)

    async def aclose(self) -> None:
        """关闭有赞客户端连接池。"""
        if self._client is not None:
            await self._client.close()
            self._client = None


async def collect_youzan_points(
    mobiles: list[str],
    fetcher: PointsFetcher,
    timeout_seconds: float,
) -> tuple[dict[str, int], list[dict[str, object]], set[str]]:
    """逐个手机号查询有赞当前积分。

    返回 (成功结果, 失败明细, 查询失败的原始手机号集合)。失败明细里的手机号
    已脱敏；原始手机号只用于把「查询失败」和「查不到数据」区分开，不得外泄。
    """
    results: dict[str, int] = {}
    failures: list[dict[str, object]] = []
    failed_mobiles: set[str] = set()
    for mobile in mobiles:
        try:
            value = await asyncio.wait_for(
                fetcher.fetch(mobile), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(
                "有赞积分查询超时 mobile=%s timeout=%ss",
                mask_sensitive(mobile),
                timeout_seconds,
            )
            failures.append(
                {
                    "mobile": mask_sensitive(mobile),
                    "error": f"timeout_after_{timeout_seconds}s",
                }
            )
            failed_mobiles.add(mobile)
            continue
        except Exception as exc:
            logger.error(
                "有赞积分查询失败 mobile=%s err=%s", mask_sensitive(mobile), exc
            )
            failures.append(
                {
                    "mobile": mask_sensitive(mobile),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            failed_mobiles.add(mobile)
            continue
        if value is None:
            logger.error(
                "有赞侧查不到该会员的积分数据 mobile=%s", mask_sensitive(mobile)
            )
            failures.append(
                {"mobile": mask_sensitive(mobile), "error": "no_points_data"}
            )
            continue
        results[mobile] = value
    return results, failures, failed_mobiles


async def collect_and_close(
    mobiles: list[str],
    fetcher: PointsFetcher,
    timeout_seconds: float,
) -> tuple[dict[str, int], list[dict[str, object]], set[str]]:
    """查询完毕后关闭取数器连接，避免连接池泄漏。"""
    try:
        return await collect_youzan_points(mobiles, fetcher, timeout_seconds)
    finally:
        try:
            await fetcher.aclose()
        except Exception as exc:
            logger.error("关闭有赞积分取数器失败: %s", exc)


def build_reconciliation_plan(
    connection: sqlite3.Connection,
    rows: list[PointsDeadLetter],
    youzan_points: dict[str, int],
    failed_mobiles: set[str],
    *,
    stale_policy: str = "strict",
) -> ReconciliationPlan:
    """逐条判定死信能否归档。

    - 有本地账户：有赞当前积分必须 >= 旧事件 total，否则 blocked；
    - 无本地账户：同样要求有赞当前积分 >= 旧事件 total，满足时只归档不建档；
    - 空手机号：必须查不到任何可关联账户，否则 blocked；
    - `stale_policy=sync-ok`：有赞当前积分低于旧事件 total、但本地锚点已经
      等于有赞当前积分时允许归档——本地状态已与有赞一致，旧事件只是过期
      快照，回放它反而会凭空造出幽灵积分。
    """
    plan = ReconciliationPlan(dead_letter_total=len(rows), points_total=len(rows))
    anchor_column = _anchor_column(connection)
    for row in rows:
        if row.parse_reason:
            plan.decisions.append(
                RowDecision(
                    row=row,
                    category=CATEGORY_BLOCKED,
                    confirmed=False,
                    reason=REASON_PAYLOAD_INVALID,
                    reason_detail=row.parse_reason,
                    account=None,
                    account_source="none",
                    youzan_current=None,
                )
            )
            continue
        if row.event_type != POINTS_EVENT_TYPE:
            plan.decisions.append(
                RowDecision(
                    row=row,
                    category=CATEGORY_BLOCKED,
                    confirmed=False,
                    reason=REASON_EVENT_TYPE_NOT_POINTS,
                    reason_detail=f"event_type={row.event_type}",
                    account=None,
                    account_source="none",
                    youzan_current=None,
                )
            )
            continue
        account = fetch_account_by_mobile(connection, row.mobile, anchor_column)
        account_source = "mobile"
        if account is None:
            account = fetch_account_by_openid(connection, row.yz_open_id, anchor_column)
            account_source = "openid"
        if account is None:
            account_source = "none"
        current = youzan_points.get(row.mobile) if row.mobile else None
        plan.decisions.append(
            _decide_row(
                row,
                account,
                account_source,
                current,
                stale_policy,
                row.mobile in failed_mobiles,
            )
        )
    _collect_replay_impact(plan)
    return plan


def _collect_replay_impact(plan: ReconciliationPlan) -> None:
    """统计「若回放旧事件会减少多少本地积分」，与既有回放工具同口径。"""
    backward_accounts: set[int] = set()
    for decision in plan.decisions:
        account = decision.account
        if account is None or decision.row.event_total is None:
            continue
        if decision.row.event_total >= account.youzan_points_base:
            continue
        plan.backward_rows += 1
        plan.backward_points += account.youzan_points_base - decision.row.event_total
        backward_accounts.add(account.account_id)
    plan.backward_members = len(backward_accounts)


def _decide_row(
    row: PointsDeadLetter,
    account: MemberAccount | None,
    account_source: str,
    current: int | None,
    stale_policy: str,
    api_failed: bool,
) -> RowDecision:
    """给出单条死信的核对结论。"""
    if not row.mobile:
        if account is not None:
            return RowDecision(
                row=row,
                category=CATEGORY_BLOCKED,
                confirmed=False,
                reason=REASON_EMPTY_MOBILE_HAS_ACCOUNT,
                reason_detail=(
                    "空手机号但本地存在可关联账户（按 openid 命中），"
                    "回放可能改写该账户余额"
                ),
                account=account,
                account_source=account_source,
                youzan_current=None,
            )
        return RowDecision(
            row=row,
            category=CATEGORY_EMPTY_MOBILE,
            confirmed=True,
            reason=REASON_EMPTY_MOBILE,
            reason_detail="空手机号且本地无任何可关联账户，回放改不动余额",
            account=None,
            account_source="none",
            youzan_current=None,
        )
    if current is None:
        reason = REASON_YOUZAN_API_ERROR if api_failed else REASON_YOUZAN_POINTS_UNKNOWN
        detail = (
            "有赞积分查询失败，无法核对"
            if api_failed
            else "有赞侧查不到该会员的积分数据"
        )
        return RowDecision(
            row=row,
            category=CATEGORY_BLOCKED,
            confirmed=False,
            reason=reason,
            reason_detail=f"{detail}，不做假设",
            account=account,
            account_source=account_source,
            youzan_current=None,
        )
    if row.event_total is None:
        return RowDecision(
            row=row,
            category=CATEGORY_BLOCKED,
            confirmed=False,
            reason=REASON_PAYLOAD_INVALID,
            reason_detail="事件总额不可用",
            account=account,
            account_source=account_source,
            youzan_current=current,
        )
    if current < row.event_total:
        if (
            stale_policy == "sync-ok"
            and account is not None
            and account.youzan_points_base == current
        ):
            # 本地锚点已等于有赞当前积分：本地状态与有赞一致，旧事件只是过期
            # 快照（会员在 8 月之后把积分花掉了）。归档是安全的，回放反而会
            # 凭空造出幽灵积分。
            return RowDecision(
                row=row,
                category=CATEGORY_STALE,
                confirmed=True,
                reason=REASON_STALE,
                reason_detail=(
                    f"有赞当前积分 {current} 低于旧事件总额 {row.event_total}，"
                    f"但本地锚点已等于有赞当前积分（{account.youzan_points_base}），"
                    "旧事件为过期快照，回放会虚增积分"
                ),
                account=account,
                account_source=account_source,
                youzan_current=current,
            )
        return RowDecision(
            row=row,
            category=CATEGORY_BLOCKED,
            confirmed=False,
            reason=REASON_YOUZAN_BELOW_EVENT_TOTAL,
            reason_detail=(
                f"有赞当前积分 {current} 低于旧事件总额 {row.event_total}，"
                "无法证明旧事件已被覆盖"
            ),
            account=account,
            account_source=account_source,
            youzan_current=current,
        )
    if account is None:
        return RowDecision(
            row=row,
            category=CATEGORY_NO_ACCOUNT,
            confirmed=True,
            reason=REASON_NO_ACCOUNT,
            reason_detail=(
                f"本地无账户，只归档不建档（有赞当前积分 {current} >= 旧事件总额 "
                f"{row.event_total}）"
            ),
            account=None,
            account_source="none",
            youzan_current=current,
        )
    return RowDecision(
        row=row,
        category=CATEGORY_SUPERSEDED,
        confirmed=True,
        reason=REASON_SUPERSEDED,
        reason_detail=(
            f"有赞当前积分 {current} >= 旧事件总额 {row.event_total}，旧事件已被覆盖"
        ),
        account=account,
        account_source=account_source,
        youzan_current=current,
    )


ARCHIVE_SQL = (
    "UPDATE inbox_events SET status = ?, lease_until = NULL, last_error = ?, "
    "updated_at = datetime('now') WHERE id = ? AND status = ?"
)


def archive_confirmed_rows(
    connection: sqlite3.Connection, plan: ReconciliationPlan
) -> ApplyOutcome:
    """在单个事务内把核对通过的死信标记为 processed。

    任一行更新失败整体回滚，绝不部分写入。
    """
    outcome = ApplyOutcome()
    connection.execute("BEGIN IMMEDIATE")
    try:
        for decision in plan.confirmed:
            try:
                cursor = connection.execute(
                    ARCHIVE_SQL,
                    (
                        ARCHIVE_TARGET_STATUS,
                        decision.write_reason[:MAX_REASON_LENGTH],
                        decision.row.row_id,
                        DEAD_LETTER_STATUS,
                    ),
                )
            except sqlite3.Error as exc:
                logger.error("归档死信失败 id=%s err=%s", decision.row.row_id, exc)
                outcome.failures.append(
                    {
                        "id": decision.row.row_id,
                        "reason": f"update_error: {exc}",
                    }
                )
                continue
            if int(cursor.rowcount or 0) != 1:
                outcome.failures.append(
                    {
                        "id": decision.row.row_id,
                        "reason": "status_changed_concurrently",
                    }
                )
                continue
            outcome.archived += 1
        if outcome.failures:
            connection.execute("ROLLBACK")
            outcome.archived = 0
            outcome.error = "存在更新失败行，本次归档已整体回滚"
        else:
            connection.execute("COMMIT")
            outcome.committed = True
    except sqlite3.Error as exc:
        connection.execute("ROLLBACK")
        outcome.archived = 0
        outcome.error = f"写库失败已回滚: {exc}"
        logger.error("写库失败，已整体回滚: %s", exc)
    return outcome


def _connect(db_path: Path, *, read_only: bool) -> sqlite3.Connection:
    """打开目标库；dry-run 一律只读打开，避免任何意外写入。"""
    timeout_seconds = BUSINESS_TIMEOUT_MS / 1000
    if read_only:
        connection = sqlite3.connect(
            f"{db_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=timeout_seconds,
            isolation_level=None,
        )
    else:
        connection = sqlite3.connect(
            str(db_path), timeout=timeout_seconds, isolation_level=None
        )
    return connection


def _decision_row(decision: RowDecision) -> dict[str, object]:
    """把单条核对结论转成脱敏后的报告条目。"""
    row = decision.row
    account = decision.account
    return {
        "id": row.row_id,
        "message_key": mask_sensitive(row.message_key),
        "created_at": row.created_at,
        "unique_id": row.unique_id,
        "mobile": mask_sensitive(row.mobile),
        "event_total": row.event_total,
        "youzan_current_points": decision.youzan_current,
        "local_account": bool(account),
        "local_account_source": decision.account_source,
        "local_points": account.points if account else None,
        "local_youzan_points_base": account.youzan_points_base if account else None,
        "category": decision.category,
        "confirmed": decision.confirmed,
        "reason": decision.reason,
        "reason_detail": decision.reason_detail,
    }


def _sample_rows(decisions: list[RowDecision]) -> list[dict[str, object]]:
    """挑样本行：先给被拦下的行，再补核对通过的行。"""
    blocked = [item for item in decisions if not item.confirmed]
    confirmed = [item for item in decisions if item.confirmed]
    picked = blocked[:SAMPLE_LIMIT]
    if len(picked) < SAMPLE_LIMIT:
        picked.extend(confirmed[: SAMPLE_LIMIT - len(picked)])
    return [_decision_row(item) for item in picked]


def build_report(
    plan: ReconciliationPlan,
    outcome: ApplyOutcome,
    *,
    mode: str,
    db_path: str,
    guard: dict[str, object],
    stale_policy: str,
) -> dict[str, object]:
    """生成稳定结构的核对报告。"""
    by_category: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for decision in plan.decisions:
        by_category[decision.category] = by_category.get(decision.category, 0) + 1
        by_reason[decision.reason] = by_reason.get(decision.reason, 0) + 1
    by_category = dict(sorted(by_category.items()))
    by_reason = dict(sorted(by_reason.items()))
    confirmed = len(plan.confirmed)
    blocked = len(plan.blocked)
    status = "ok"
    if outcome.failures or outcome.error:
        status = "failed"
    elif blocked:
        status = "blocked"
    report: dict[str, object] = {
        "status": status,
        "mode": mode,
        "db": db_path,
        "production_guard": guard,
        "stale_policy": stale_policy,
        "dead_letter_total": plan.dead_letter_total,
        "points_dead_letter_total": plan.points_total,
        "checked_members": len(plan.checked_mobiles),
        "confirmed": confirmed,
        "blocked": blocked,
        "archived": outcome.archived,
        "would_archive": confirmed,
        "by_category": by_category,
        "by_reason": by_reason,
        "replay_impact": {
            "backward_rows": plan.backward_rows,
            "backward_members": plan.backward_members,
            "backward_points_total": plan.backward_points,
            "note": "与 resolve_youzan_dead_letters.py 的 points_impact 同口径："
            "若回放这些旧事件，本地锚点合计会被改小的分数",
        },
        "youzan_api": {
            "name": POINTS_QUERY_API_NAME,
            "version": POINTS_QUERY_API_VERSION,
            "account_type": POINTS_ACCOUNT_TYPE_MOBILE,
        },
        "api_unavailable": plan.api_unavailable,
        "api_errors": plan.api_errors,
        "out_of_scope": plan.out_of_scope,
        "samples": _sample_rows(plan.decisions),
        "rows": [_decision_row(item) for item in plan.decisions],
        "summary": {
            "dead_letter_total": plan.dead_letter_total,
            "points_dead_letter_total": plan.points_total,
            "checked_members": len(plan.checked_mobiles),
            "confirmed": confirmed,
            "blocked": blocked,
            "archived": outcome.archived,
            "would_archive": confirmed,
            "api_error_count": len(plan.api_errors),
            "committed": outcome.committed,
        },
    }
    if outcome.error:
        report["error"] = outcome.error
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(
        description="核对有赞 POINTS 死信与有赞当前积分，并把已确认失效的历史事件标记为已处理"
    )
    parser.add_argument("--db", required=True, help="目标 SQLite 数据库路径（必填）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库（标记为 processed）；不加该参数时只做只读核对。",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="允许对疑似生产路径的数据库执行操作。",
    )
    parser.add_argument(
        "--app-root",
        default="",
        help="后端代码根目录（用于导入 app.* 有赞客户端），缺省取脚本上级目录。",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=DEFAULT_API_TIMEOUT_SECONDS,
        help="单个会员的有赞积分查询超时秒数。",
    )
    parser.add_argument(
        "--stale-policy",
        choices=("strict", "sync-ok"),
        default="strict",
        help=(
            "有赞当前积分低于旧事件总额时的口径：strict=一律拦下；"
            "sync-ok=本地锚点已等于有赞当前积分时按过期快照归档（回放会虚增积分）。"
        ),
    )
    parser.add_argument("--output", default="", help="把 JSON 报告额外写入指定文件")
    return parser.parse_args(argv)


def emit_report(report: dict[str, object], output_path: str) -> None:
    """把报告写到 stdout，并按需额外落盘。"""
    text = json.dumps(report, ensure_ascii=False, indent=2)
    sys.stdout.write(text + "\n")
    if not output_path:
        return
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    logger.info("报告已写入 %s", path)


def resolve_app_root(raw: str) -> Path:
    """定位后端代码根目录：显式参数 > 当前目录 > 脚本上级目录。

    脚本被复制到临时目录执行时，仅按脚本位置推断会找不到 `app` 包；
    此时只要工作目录是后端根目录，仍能正确导入有赞客户端。
    """
    if raw:
        return Path(raw).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "app" / "service" / "youzan" / "client.py").is_file():
        return cwd.resolve()
    return SCRIPTS_DIR.parent.resolve()


def main(
    argv: list[str] | None = None,
    *,
    points_fetcher: PointsFetcher | None = None,
) -> int:
    """脚本入口，返回进程退出码。"""
    _configure_logging()
    args = parse_args(argv)
    report: dict[str, object] = {
        "status": "ok",
        "mode": "apply" if args.apply else "dry-run",
        "db": str(args.db),
    }
    try:
        db_path = Path(args.db).expanduser()
        guard = evaluate_target_guard(
            db_path, allow_production=bool(args.allow_production)
        )
    except TargetRejected as exc:
        report["status"] = "rejected"
        report["error"] = str(exc)
        report["summary"] = {"rejected": True}
        emit_report(report, args.output)
        logger.error("目标库被拒绝: %s", exc)
        return EXIT_REJECTED

    report["production_guard"] = guard
    try:
        with closing(_connect(db_path, read_only=not args.apply)) as connection:
            return _run_on_database(connection, args, report, points_fetcher)
    except sqlite3.Error as exc:
        logger.error("数据库操作失败: %s", exc)
        report["status"] = "failed"
        report["error"] = f"数据库操作失败: {exc}"
        emit_report(report, args.output)
        return EXIT_FAILED


def _run_on_database(
    connection: sqlite3.Connection,
    args: argparse.Namespace,
    report: dict[str, object],
    points_fetcher: PointsFetcher | None,
) -> int:
    """在目标库上完成核对、归档与报告输出。"""
    missing_tables = [
        name
        for name in ("inbox_events", "member_balance")
        if not _table_exists(connection, name)
    ]
    if missing_tables:
        report["status"] = "failed"
        report["error"] = f"目标库缺少必要的表: {', '.join(missing_tables)}"
        report["summary"] = {"missing_tables": missing_tables}
        emit_report(report, args.output)
        logger.error("目标库缺少必要的表: %s", ", ".join(missing_tables))
        return EXIT_FAILED

    rows = fetch_dead_letters(connection)
    # 事件类型不可解析的死信无法判定是否属于本次范围，一律按「拦下」处理，
    # 不得当成范围外而静默跳过。
    in_scope_ids = {
        row.row_id
        for row in rows
        if row.event_type == POINTS_EVENT_TYPE or not row.event_type
    }
    points_rows = [row for row in rows if row.row_id in in_scope_ids]
    out_of_scope = [
        {
            "id": row.row_id,
            "message_key": mask_sensitive(row.message_key),
            "event_type": row.event_type or "unknown",
            "reason": REASON_EVENT_TYPE_NOT_POINTS,
        }
        for row in rows
        if row.row_id not in in_scope_ids
    ]

    mobiles: list[str] = []
    for row in points_rows:
        if row.mobile and row.mobile not in mobiles:
            mobiles.append(row.mobile)

    fetcher = points_fetcher or YouzanPointsFetcher(
        resolve_app_root(str(args.app_root)), float(args.api_timeout)
    )
    youzan_points: dict[str, int] = {}
    api_failures: list[dict[str, object]] = []
    failed_mobiles: set[str] = set()
    api_unavailable = ""
    try:
        fetcher.prepare()
        youzan_points, api_failures, failed_mobiles = asyncio.run(
            collect_and_close(mobiles, fetcher, float(args.api_timeout))
        )
    except Exception as exc:
        api_unavailable = f"{type(exc).__name__}: {exc}"
        logger.error("有赞积分核对不可用: %s", api_unavailable)
        api_failures = [
            {"mobile": mask_sensitive(mobile), "error": api_unavailable}
            for mobile in mobiles
        ]
        failed_mobiles = set(mobiles)

    plan = build_reconciliation_plan(
        connection,
        points_rows,
        youzan_points,
        failed_mobiles,
        stale_policy=str(args.stale_policy),
    )
    plan.dead_letter_total = len(rows)
    plan.checked_mobiles = list(mobiles)
    plan.api_errors = api_failures
    plan.api_unavailable = api_unavailable
    plan.out_of_scope = out_of_scope

    blocked = plan.blocked
    outcome = ApplyOutcome()
    if args.apply and not blocked:
        outcome = archive_confirmed_rows(connection, plan)
    elif args.apply and blocked:
        logger.error("存在 %d 条 blocked 死信，拒绝整体归档，本次不写库", len(blocked))
    elif blocked:
        logger.warning("存在 %d 条 blocked 死信", len(blocked))

    report.update(
        build_report(
            plan,
            outcome,
            mode="apply" if args.apply else "dry-run",
            db_path=str(args.db),
            guard=report.get("production_guard", {}),
            stale_policy=str(args.stale_policy),
        )
    )
    emit_report(report, args.output)
    logger.info(
        "核对完成 mode=%s dead_letter=%s checked=%s confirmed=%s blocked=%s "
        "archived=%s",
        report["mode"],
        plan.dead_letter_total,
        len(plan.checked_mobiles),
        len(plan.confirmed),
        len(blocked),
        outcome.archived,
    )
    if outcome.error:
        logger.error("归档未完成: %s", outcome.error)
        return EXIT_FAILED
    if blocked:
        return EXIT_REJECTED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
