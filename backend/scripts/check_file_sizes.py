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
    ),
    "app/repository/youzan_order_repo.py": (
        "本轮职责评审：有赞订单读取、订单事件幂等和履约字段回写共享订单数据所有权与事务连接；拆分会重复状态映射和唯一性约束。保留当前内聚边界，后续按稳定的订单读取/事件写入合同拆分。"
    ),
    "app/repository/order_repo.py": (
        "本轮职责评审：订单仓储保持原子条件更新内聚，新增组合支付中间态条件写入（partial/unpaid 双态流转）与既有 unpaid 单态写入共享同一 PAYMENT_STATUS_SQL 合同；按支付状态拆方法只会复制 WHERE 条件与回读胶水，保留当前内聚边界。"
    ),
    "app/service/points/payment.py": (
        "本轮职责评审（B3.4）：积分支付联动保持单一事实域内聚——围栏与快照写入、结算发分/扣减（含扣减失败阻断）、退款两命令分流（未结算释放 / 已结算核验原流水并按原账户入账）共享同一 ledger/reconcile 仓储与快照生命周期（pointsSettledAt 标记、_clear_awarded）；拆分会把核验-入账原子性分散到多文件并复制幂等键与对账胶水，保留当前内聚边界，后续按 D1 统一支付应用服务职责拆分。"
    ),
    "app/main.py": (
        "存量职责评审：应用入口集中管理 lifespan、repository/service 装配和运行时路由，"
        "本轮仅增加 readiness Response 注入，不新增独立业务职责；禁止为单行超线机械拆分。"
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
