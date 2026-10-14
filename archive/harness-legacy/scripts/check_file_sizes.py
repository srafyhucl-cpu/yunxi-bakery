"""文件体量职责评审门禁。

行数只负责触发评审。超过阻断线且没有评审记录时阻断提交，
避免未经设计继续膨胀；是否拆分仍由职责内聚性和稳定边界决定。
"""

import sys
from pathlib import Path

# 强制 stdout 使用 UTF-8，避免 Windows GBK 编码下 pre-commit 管道卡死
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except AttributeError:
    pass  # Python < 3.7 或某些环境不支持 reconfigure，忽略即可

# blocking 阈值（行数）：各层模块上限
BLOCKING_RULES: list[tuple[str, int]] = [
    ("app/repository/", 250),
    ("app/service/llm/", 180),
    ("app/service/youzan/", 250),
    ("app/service/", 320),
    ("app/api/", 350),
    ("app/", 400),
]

# 忽略目录（不参与检查）
IGNORE_DIRS = {"__pycache__", ".git", "venv", "node_modules", "migrations"}

# 存量超线文件的职责评审说明。这里不是永久白名单；修改时仍需复核是否新增职责。
OVERSIZE_REVIEW_NOTES: dict[str, str] = {
    "app/repository/knowledge_repo.py": (
        "存量职责评审：知识读写与治理查询仍有多个变化原因，后续按可独立测试的查询/写入边界评估；禁止按行数机械切分。"
    ),
    "app/repository/knowledge_product_repo.py": (
        "存量职责评审：商城目录查询与分类序列化是候选边界，拆分前需先稳定返回合同；禁止按行数机械切分。"
    ),
    "app/repository/youzan_repo.py": (
        "存量职责评审：有赞商品宽表与分类回写存在独立变化原因，后续按数据所有权拆分；禁止按行数机械切分。"
    ),
    "app/repository/customer_master_queries.py": (
        "本轮职责评审：客户主档查询集合保持读模型内聚，统一维护 customer_master / customer_identity_links 的行映射合同；拆分会把同一张表的查询与映射分散到多个文件。保留当前内聚边界。"
    ),
    "app/service/chat.py": (
        "存量职责评审：客户对话入口保持编排内聚，新职责应落入已有 agent/tool 边界；禁止为缩短入口文件制造薄转发层。"
    ),
    "app/service/knowledge_admin.py": (
        "存量职责评审：后台知识管理编排含分页与同步候选边界，只有接口可独立测试时才拆分。"
    ),
    "app/service/observability.py": (
        "存量职责评审：观测查询与报表聚合存在不同变化原因，后续按读模型合同评估；禁止按行数机械切分。"
    ),
    "app/service/catalog/application.py": (
        "存量职责评审：商品目录应用服务集中维护商城在售商品分页、分类分组、详情展示与关键词检索的读模型编排；各方法共享统一的展示态转换与上架过滤逻辑，拆分会分散商品目录合同并增加薄转发层。保留当前内聚边界，后续按独立读模型拆分。"
    ),
    "app/service/llm/function_tool_order.py": (
        "存量职责评审：订单与物流工具同属履约事实查询，先保持领域内聚；新增其他工具职责时再拆。"
    ),
    "app/service/llm/function_tool_product.py": (
        "存量职责评审：商品事实查询与 RAG 辅助存在候选边界，需避免拆分后泄漏会话和检索内部状态。"
    ),
    "app/service/llm/function_tool_product_live.py": (
        "本轮职责评审：商品缓存、实时 API 刷新、宽表/RAG/向量同步和变更历史记录共享同一条刷新事务语义；继续拆分会分散失败记录与写入结果关联，保留当前内聚边界并由独立入口调用。"
    ),
    "app/service/llm/intent.py": (
        "存量职责评审：意图入口已把词表和 prompt 外置，当前保留解析编排内聚；不得回流词表职责。"
    ),
    "app/service/offline/agent_memory.py": (
        "本轮职责评审：画像抽取、LLM 修复重试、规则信号合并、consent 校验和画像写入共同维护同一份长期记忆事实合同；Runnable 仅替换模型调用边界，拆分会增加事实状态穿透，保留当前内聚边界。"
    ),
    "app/service/youzan/event_member.py": (
        "本轮职责评审：四类会员事件（客户/积分/优惠券/会员卡）共享同一账务域写入合同、幂等去重与审计标记；解析助手已外置 member_helpers，按事件类型拆分只会复制去重与审计胶水，保留当前内聚边界。"
    ),
    "app/service/youzan/client.py": (
        "存量职责评审：有赞开放接口客户端可按 API 领域形成稳定子客户端，拆分不得复制鉴权和重试逻辑。"
    ),
    "app/service/youzan/event_item.py": (
        "存量职责评审：商品事件解析、构建和 RAG 同步存在候选边界，需按事件数据流拆分而非按函数数量切分。"
    ),
    "app/service/youzan/product_reconciler.py": (
        "存量职责评审：商品对账与分类回填存在独立变化原因，候选单元必须能独立 dry-run 和测试。"
    ),
    "app/service/wecom/client_kf.py": (
        "存量职责评审：企微客服客户端按协议能力聚合，候选拆分需复用统一鉴权并避免 mixin 状态穿透。"
    ),
    "app/service/wecom/kf_message_queue.py": (
        "本轮职责评审：已将商品卡片发送独立为 kf_card_sender.py；队列仍集中持久化拉取、非文本预处理、会话状态同步和 AI 回复编排，需先冻结队列状态合同再拆分剩余边界。"
    ),
    "app/service/agents/employee/nodes.py": (
        "本轮职责评审：员工 graph 节点、ToolNode 缓存、领域订单查询例外、确定性 finalizer 和 trace 记录共同维护同一 graph state 合同；拆分会增加状态穿透和工具装配重复。保留当前内聚边界，待 graph 生命周期与工具上下文进一步解耦后再按职责拆分。"
    ),
    "app/repository/privacy_repo.py": (
        "本轮职责评审：主体导出、删除和保留期清理共享同一份个人数据表覆盖清单，"
        "拆分会复制或漂移删除范围；保持一个隐私数据所有权仓库，service 负责事务编排。"
        "r73/r74 新增的两条查询同属该所有权边界（分别定位储值占用腿与在途微信尾款腿），"
        "留在本仓库可与删除范围同源核对；结清与拒绝逻辑一律放 service，不下沉到仓储。"
        "r75 新增的 `_purge_orders` 与 `delete_subject` 的子表清理同属该所有权边界："
        "两张硬外键子表的清理范围必须与订单删除范围同源判定，拆到别处会重新引入"
        "「删了父表却漏清子表」的外键缺口。"
        "r76 修正的 `_customer_ids` 主体标识归一与 `_delete_customer_records` "
        "子表先于身份链接的删除顺序，同样属于「哪些个人数据归本主体」这一份所有权："
        "身份匹配口径与客户主档层删除范围必须同源判定，拆开就会出现「导出得到、"
        "删不掉」或「先删父表撞外键」的口径漂移。openid 归一函数本身是全仓唯一的"
        "纯函数，落在 app/utils.py 而非本仓库，避免仓储反向依赖 service 层。"
    ),
    "app/repository/youzan_order_repo.py": (
        "本轮职责评审：有赞订单读取、订单事件幂等和履约字段回写共享订单数据所有权与事务连接；拆分会重复状态映射和唯一性约束。保留当前内聚边界，后续按稳定的订单读取/事件写入合同拆分。"
    ),
    "app/repository/order_repo.py": (
        "本轮职责评审：订单仓储保持原子条件更新内聚，新增组合支付中间态条件写入（partial/unpaid 双态流转）与既有 unpaid 单态写入共享同一 PAYMENT_STATUS_SQL 合同；按支付状态拆方法只会复制 WHERE 条件与回读胶水，保留当前内聚边界。"
    ),
    "app/repository/member_balance_repo.py": (
        "本轮职责评审（r79）：`member_balance` 是单表单行投影，十个方法全部是对同一行的原子读写——"
        "身份/卡片合并（`upsert_identity`，同时写 `stored_value_fen`）、外部积分镜像"
        "（`mirror_youzan_points`）、积分与储值各自的读取/加款/余额充足条件扣减。"
        "积分与储值是同一行的不同列，`credit_points` 与 `credit_stored_value` 结构同构；"
        "`get_by_mobile`/`get_by_openid` 是身份写入与积分镜像共用的行定位原语。"
        "按「身份 / 余额」两半拆分需要跨类共享行定位、并把 `upsert_identity` 已持有的"
        "储值列写入搬到另一半，会把「同一行、同一原子写」这一事实域切开。"
        "r79 新增的 `mirror_youzan_points` 属该事实域内的第三条写路径而非新职责："
        "「余额 = 外部锚点 + 本地账本净额」这条不变量要求镜像与本地增量写同处一个仓储才可同源核对，"
        "拆开正是 r79 缺陷（`M-20260926-030`）的成因形态。"
        "保留当前内聚边界，禁止新增与单行余额投影无关的职责。"
    ),
    "app/repository/coupon_inventory_repo.py": (
        "本轮职责评审：`coupon_inventory` 是单表优惠券生命周期账本，方法全部围绕同一份去重键空间"
        "（`coupon_id+status+mobile+cycle_no`）与同一套「最新状态」排序口径（`authority` 下的 "
        "`source` 权重 + `cycle_no` 因果序 + 时间序）展开。"
        "r64/r78 引入的 `cycle_no` 周期维度横穿 `insert`、`list_by_mobile`、`get_latest_state`、"
        "`consume`、`refund`、`list_all` 每一个方法——它是这张表的排序键而非某个方法的局部需求；"
        "按「查询 / 写入」或按「有赞权威 / 本地权威」拆分都会把该口径复制成两份，"
        "一旦漂移即等于把券的最新状态判错（错判已消耗会再次核销同一张券）。"
        "r78 在 `refund` 补写新周期 `TAKE` 与 r64 在 `consume` 的有效期复核豁免说明属状态机正确性论证，"
        "行数增长来自论证而非职责扩张。保留当前内聚边界。"
    ),
    "app/service/order/payment_runtime.py": (
        "本轮职责评审：支付运行时服务集中维护支付会话准备、mock/微信支付确认、通知与查询恢复的统一状态入口；r15 增加的 intake 租约、业务事务和失败重试编排仍属于同一支付回调恢复边界，拆分会把认领、支付事实和完成标记分散到薄转发层。保留当前内聚边界，后续若引入独立支付尝试模型再按稳定状态边界评估。"
    ),
    "app/service/order/refund_notification.py": (
        "本轮职责评审：退款通知服务集中维护同一微信退款事实的金额与交易校验、交易归属确认、资产补偿、退款快照记账和对账案件；这些步骤共享同一订单快照与事务提交边界，抽离只会增加状态穿透和补偿时序漂移。保留当前内聚边界，禁止继续加入与退款事实无关的支付或履约职责。"
    ),
    "app/service/points/payment.py": (
        "本轮职责评审（B3.4）：积分支付联动保持单一事实域内聚——围栏与快照写入、结算发分/扣减（含扣减失败阻断）、退款两命令分流（未结算释放 / 已结算核验原流水并按原账户入账）共享同一 ledger/reconcile 仓储与快照生命周期（pointsSettledAt 标记、_clear_awarded）；拆分会把核验-入账原子性分散到多文件并复制幂等键与对账胶水，保留当前内聚边界，后续按 D1 统一支付应用服务职责拆分。"
    ),
    "app/main.py": (
        "存量职责评审：应用入口集中管理 lifespan、repository/service 装配和运行时路由，"
        "本轮仅增加 readiness Response 注入，不新增独立业务职责；禁止为单行超线机械拆分。"
    ),
    "app/service/wecom/kf_callback_processor.py": (
        "本轮职责评审：回调处理保持单同步命令编排内聚——拉取、分类、账本、人工落库、收件箱暂存、游标推进共享同一事务边界；"
        "持久化原语已拆至 kf_sync_persist.py，继续拆分只会把事务顺序分散到多文件并增加游标超前风险。保留当前内聚边界，禁止新增无关职责。"
    ),
}

UNREVIEWED_OVERSIZE_GUIDANCE = (
    "请先做职责评审：职责混杂时按稳定、可独立测试的边界拆分；职责高度内聚时记录保留理由。"
    "禁止为了压行数机械切文件。"
)


def get_limit(rel: str) -> int:
    """按最精确路径前缀返回 blocking 阈值。"""
    for prefix, limit in BLOCKING_RULES:
        if rel.replace("\\", "/").startswith(prefix):
            return limit
    return 400


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations: list[str] = []

    app_root = root / "app"
    reviewed_findings: list[tuple[str, str]] = []
    for py_file in sorted(app_root.rglob("*.py")):
        parts = py_file.relative_to(root).parts
        if any(d in IGNORE_DIRS for d in parts):
            continue
        rel = str(py_file.relative_to(root))
        rel_unix = rel.replace("\\", "/")
        limit = get_limit(rel_unix)
        lines = count_lines(py_file)
        if lines > limit:
            msg = (
                f"  {rel_unix}: {lines} 行（未评审阻断线 {limit} 行，"
                f"超出 {lines - limit} 行）"
            )
            review_note = OVERSIZE_REVIEW_NOTES.get(rel_unix)
            if review_note is not None:
                reviewed_findings.append((msg, review_note))
            else:
                violations.append(msg)

    if reviewed_findings:
        print("\n[WARN] 已有职责评审记录的存量超线文件（不因行数自动要求拆分）：")
        for finding, review_note in reviewed_findings:
            print(finding)
            print(f"    评审：{review_note}")

    if violations:
        print("\n[ERROR] 文件体量超过阻断线且缺少职责评审，提交被阻断：")
        for v in violations:
            print(v)
        print(f"\n{UNREVIEWED_OVERSIZE_GUIDANCE}")
        return 1

    print(
        f"[OK] 文件体量检查通过（共检查 {sum(1 for _ in app_root.rglob('*.py'))} 个文件）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
