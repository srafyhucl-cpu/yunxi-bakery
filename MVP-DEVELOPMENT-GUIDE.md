# MVP 开发指导文档

> ⚠️ **范围修正警示（2026-08-24，计划书附录D v1.2）**
>
> 本文档基于 v1.0 的"三大功能 MVP"框架编写，**该范围定义已部分作废**：
> - 小程序及会员/积分/储值/券模块**不可砍、不可推迟**——它们是替代有赞的核心，已全部建成于基线中
> - "开发三大功能"已改为"**迁移资产 + 全模块承接验证**"
> - Week 1 已完成任务（基线冒烟、BM25 落地、FAQ 模板作废改用旧库迁移）仍然有效
> - **Week 2 及之后的任务清单待架构师重新下达，执行本文件 Week 2+ 内容前必须先确认新任务包**
> - 当前唯一活跃任务：P0.5 资产迁移（见 PROJECT-STATE.md）

**目标受众**：AI 开发助手  
**开发周期**：2026年8月-10月（8周）  
**核心目标**：~~实现3个核心功能~~ → 全模块承接验证，让店家能试用

---

## 🎯 一、MVP 范围定义

### 1.1 必须做的功能（MVP三大功能）

#### 功能1：AI客服对话

**需求描述**：
- 企微客户发消息，AI自动回答
- 支持FAQ（营业时间、配送范围、退换货政策）
- 支持产品咨询（"有什么面包"、"价格多少"）
- 复杂问题能转人工

**验收标准**：
- [ ] 能回答至少10个常见FAQ
- [ ] 能查询产品列表
- [ ] 回答准确率>80%
- [ ] 响应时间<3秒

#### 功能2：订单查询

**需求描述**：
- 客户说订单号，能查到订单状态
- 自动同步有赞订单状态
- 物流信息展示

**验收标准**：
- [ ] 能查询有赞订单
- [ ] 订单状态实时同步
- [ ] 测试10个真实订单通过

#### 功能3：企微消息接入

**需求描述**：
- 接收企微客户消息
- AI自动回复
- 人工接管功能

**验收标准**：
- [ ] Webhook能收到消息
- [ ] 消息去重和幂等性保证
- [ ] 人工接管流程跑通

### 1.2 不做的功能（推迟到v2.0）

**明确禁止**：
- ❌ 会员积分系统
- ❌ 储值余额系统
- ❌ 优惠券系统
- ❌ 客户群运营
- ❌ 小程序端（先只做企微）
- ❌ 微信支付集成（用有赞自带的）
- ❌ D1账务核心一致性

---

## 📅 二、8周开发计划

### Week 1-2：核心对话流程（2026年8月19日-9月1日）

#### 任务清单

**任务1.1：验证 master 基线能力**

> 依据架构评审 R1 修正：MVP 分支从 master（b30b2066，B3.5 冻结基线）拉出，
> 天然不含 D1 账务代码（D1 只存在于审阅分支 codex/r4c-ci-evidence，从未合入 master）。
> 因此无需删除任何代码——只需验证基线既有能力可用。

```powershell
# 在 mvp-2027-june 分支上启动服务并冒烟测试
git checkout mvp-2027-june
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
```

- [ ] 服务能启动，/health 返回 200
- [ ] FAQ 检索能力可用（营业时间/配送范围/退换货）
- [ ] 商品查询能力可用（列表/详情）
- [ ] 企微回调链路配置可加载
- [ ] 订单查询能力可用（有赞对接）

> D1 探索成果保留在审阅分支原样存档，不删除、不合并、不改写。

**任务1.2：简化LangChain调用**
```python
# 目标：最简单的对话流程
# app/service/llm/conversation.py

async def handle_message(user_message: str) -> str:
    """处理用户消息，返回AI回复"""
    # 1. 检查是否是FAQ（优先）
    faq_answer = check_faq(user_message)
    if faq_answer:
        return faq_answer
    
    # 2. 检查是否是产品查询
    if is_product_query(user_message):
        return query_products(user_message)
    
    # 3. 调用LangChain生成回复
    return await call_langchain(user_message)
```

- [ ] 实现FAQ匹配逻辑
- [ ] 实现产品查询逻辑
- [ ] 简化LangChain配置

**任务1.3：准备10个FAQ**
```python
# app/data/faq.py
FAQ_DATABASE = {
    "营业时间": "我们的营业时间是周一至周日 8:00-20:00",
    "配送范围": "目前配送范围覆盖市区内10公里",
    "退换货政策": "请在收到商品24小时内联系客服，我们支持无理由退换货",
    # ... 添加更多FAQ
}
```

- [ ] 编写10个常见FAQ
- [ ] 实现关键词匹配
- [ ] 测试FAQ准确率

**任务1.4：本地测试**
```bash
# 启动服务
python -m uvicorn app.main:app --reload

# 测试FAQ
curl -X POST http://127.0.0.1:7001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你们营业时间"}'
```

- [ ] 所有FAQ能正确回答
- [ ] 产品查询返回结果
- [ ] 响应时间<3秒

**Week 1-2 验收标准**：
- ✅ 系统能启动（master 基线 v0.132.9）
- ✅ FAQ能正确回答
- ✅ 产品查询能用
- ✅ 基线冒烟测试全部通过（无回归）

---

### Week 3-4：企微接入（2026年9月2日-9月15日）

#### 任务清单

**任务2.1：配置企微Webhook**
```python
# app/api/wecom.py

@router.post("/webhook")
async def wecom_webhook(request: Request):
    """接收企微消息"""
    # 1. 验证签名
    # 2. 解析消息
    # 3. 调用对话服务
    # 4. 返回回复
```

- [ ] 配置企微应用
- [ ] 实现签名验证
- [ ] 测试消息接收

**任务2.2：消息去重**
```python
# app/service/message_handler.py

async def handle_wecom_message(msg_id: str, content: str):
    """处理企微消息，保证幂等性"""
    # 1. 检查消息是否已处理
    if await is_message_processed(msg_id):
        return "already_processed"
    
    # 2. 处理消息
    reply = await handle_message(content)
    
    # 3. 记录已处理
    await mark_message_processed(msg_id)
    
    return reply
```

- [ ] 实现消息去重表
- [ ] 测试重复消息不会重复处理

**任务2.3：人工接管**
```python
# 关键词触发人工
MANUAL_KEYWORDS = ["人工", "客服", "投诉"]

async def should_transfer_to_manual(message: str) -> bool:
    """判断是否需要转人工"""
    return any(kw in message for kw in MANUAL_KEYWORDS)
```

- [ ] 实现人工接管判断逻辑
- [ ] 测试转人工流程

**任务2.4：集成测试**
```bash
# 用企微客户端发送测试消息
# 验证能收到AI回复
```

- [ ] 企微能收到消息
- [ ] AI能自动回复
- [ ] 人工接管能触发

**Week 3-4 验收标准**：
- ✅ 企微Webhook正常工作
- ✅ 消息不会重复处理
- ✅ 人工接管流程跑通
- ✅ 响应时间<3秒

---

### Week 5-6：订单查询（2026年9月16日-9月29日）

#### 任务清单

**任务3.1：对接有赞API**
```python
# app/service/youzan/order.py

async def query_order(order_no: str) -> dict:
    """查询有赞订单"""
    # 1. 调用有赞API
    # 2. 解析订单状态
    # 3. 返回格式化结果
```

- [ ] 申请有赞API权限
- [ ] 实现订单查询接口
- [ ] 测试API调用

**任务3.2：订单状态映射**
```python
# 有赞订单状态 -> 客户友好描述
ORDER_STATUS_MAP = {
    "WAIT_BUYER_PAY": "待支付",
    "WAIT_SELLER_SEND_GOODS": "待发货",
    "WAIT_BUYER_CONFIRM_GOODS": "已发货",
    "TRADE_SUCCESS": "已完成",
}
```

- [ ] 实现状态映射
- [ ] 测试所有状态

**任务3.3：集成到对话流程**
```python
# 识别订单查询意图
if is_order_query(message):
    order_no = extract_order_no(message)
    order_info = await query_order(order_no)
    return format_order_reply(order_info)
```

- [ ] 实现订单号提取
- [ ] 集成到对话服务
- [ ] 测试端到端流程

**任务3.4：真实订单测试**
```bash
# 用10个真实订单号测试
# 验证查询结果准确
```

- [ ] 测试10个真实订单
- [ ] 所有查询结果正确
- [ ] 无订单时提示友好

**Week 5-6 验收标准**：
- ✅ 能查询有赞订单
- ✅ 订单状态准确
- ✅ 客户体验友好
- ✅ 响应时间<3秒

---

### Week 7-8：部署试运行（2026年9月30日-10月13日）

#### 任务清单

**任务4.1：部署到服务器**
```bash
# 1. 推送代码到生产服务器
git push server mvp-branch:main

# 2. SSH登录服务器
ssh root@47.94.102.250

# 3. 重启服务
cd /opt/apps/yunxibakebot
systemctl restart yunxibakebot
```

- [ ] 代码推送到服务器
- [ ] 服务重启成功
- [ ] 健康检查通过

**任务4.2：配置生产环境**
```bash
# 检查.env配置
# - 有赞API密钥
# - 企微应用配置
# - LangChain API密钥
```

- [ ] 所有配置正确
- [ ] 服务能正常启动

**任务4.3：店家试用**
```
让店家客服团队试用1周，收集反馈：
1. AI回答是否准确
2. 订单查询是否方便
3. 有哪些常见问题没覆盖
4. 响应速度是否满意
```

- [ ] 店家团队开始试用
- [ ] 每天收集反馈
- [ ] 记录所有问题

**任务4.4：修复明显bug**
```
根据反馈快速修复：
- FAQ答案不准确 -> 调整
- 订单查询报错 -> 修复
- 响应太慢 -> 优化
```

- [ ] 修复所有阻塞性bug
- [ ] 调整FAQ内容
- [ ] 优化响应速度

**Week 7-8 验收标准**：
- ✅ 部署到生产环境
- ✅ 店家试用1周
- ✅ 收集至少20条反馈
- ✅ 修复所有阻塞性bug

---

## 🛠️ 三、技术实现指南

### 3.1 简化原则

**禁止过度设计**：
- ❌ 不要引入缓存（Redis）
- ❌ 不要引入消息队列（RabbitMQ）
- ❌ 不要引入事件溯源
- ❌ 不要引入微服务架构

**推荐做法**：
- ✅ 一张表搞定的不要拆成三张
- ✅ 一个函数搞定的不要拆成三个类
- ✅ 能用if-else的不要用策略模式
- ✅ 能用SQLite的不要换PostgreSQL

### 3.2 代码组织

**推荐结构**：
```
backend/app/
├── api/
│   ├── wecom.py          # 企微Webhook
│   └── chat.py           # 对话API（测试用）
├── service/
│   ├── conversation.py   # 核心对话逻辑
│   ├── faq.py           # FAQ匹配
│   └── youzan.py        # 有赞订单查询
├── models/
│   ├── message.py       # 消息模型
│   └── order.py         # 订单模型
└── data/
    └── faq.py           # FAQ数据库
```

**每个文件不超过300行**

### 3.3 测试策略

**只测试核心路径**：
```python
# tests/test_conversation.py

async def test_faq_matching():
    """测试FAQ匹配"""
    reply = await handle_message("你们营业时间")
    assert "8:00-20:00" in reply

async def test_order_query():
    """测试订单查询"""
    reply = await handle_message("查询订单 12345")
    assert "订单状态" in reply
```

**不追求100%覆盖率**，只测试：
- ✅ FAQ匹配
- ✅ 订单查询
- ✅ 人工接管触发

### 3.4 错误处理

**简单但够用**：
```python
async def handle_message(message: str) -> str:
    try:
        # 处理逻辑
        return reply
    except Exception as e:
        logger.error(f"处理消息失败: {e}")
        return "抱歉，我遇到了一些问题，请稍后再试或联系人工客服"
```

**不要**：
- ❌ 复杂的异常层次结构
- ❌ 自定义异常类（除非真的需要）
- ❌ 完美的错误分类

---

## 🚫 四、禁止事项清单

### 4.1 禁止引入的技术

- ❌ Redis（缓存可以后续加）
- ❌ RabbitMQ / Kafka（消息队列）
- ❌ PostgreSQL（SQLite够用）
- ❌ Docker Compose（单机部署就行）
- ❌ Kubernetes（过度）
- ❌ 微服务架构
- ❌ GraphQL

### 4.2 禁止的架构模式

- ❌ 事件溯源（Event Sourcing）
- ❌ CQRS
- ❌ 六边形架构
- ❌ DDD（领域驱动设计）
- ❌ 策略模式（除非真的有5个以上策略）

### 4.3 禁止的治理机制

- ❌ 新的pre-commit钩子
- ❌ 证据索引生成
- ❌ 交接快照自动化
- ❌ 完美的测试覆盖率
- ❌ 复杂的CI/CD流程

---

## ✅ 五、每周验收标准

### Week 1-2 验收
```bash
# 1. 启动系统
cd backend
python -m uvicorn app.main:app --reload

# 2. 测试FAQ
curl -X POST http://127.0.0.1:7001/api/chat \
  -d '{"message":"营业时间"}'

# 3. 检查响应时间
# 应该 < 3秒
```

**通过标准**：
- [ ] 系统正常启动
- [ ] 10个FAQ全部正确
- [ ] 响应时间<3秒

---

### Week 3-4 验收
```bash
# 1. 企微发送测试消息
# 2. 检查是否收到AI回复
# 3. 发送"人工"测试转人工
```

**通过标准**：
- [ ] 企微消息能收到
- [ ] AI能自动回复
- [ ] 人工接管能触发
- [ ] 重复消息不会重复处理

---

### Week 5-6 验收
```bash
# 1. 测试订单查询
curl -X POST http://127.0.0.1:7001/api/chat \
  -d '{"message":"查询订单 E20240817001"}'

# 2. 验证10个真实订单
```

**通过标准**：
- [ ] 能查询有赞订单
- [ ] 10个真实订单全部正确
- [ ] 无订单时提示友好

---

### Week 7-8 验收
```bash
# 1. 生产环境健康检查
curl https://bot.yunxibakery.com/health

# 2. 店家试用反馈收集
# 3. Bug修复确认
```

**通过标准**：
- [ ] 生产环境稳定运行
- [ ] 店家试用1周
- [ ] 收集至少20条反馈
- [ ] 所有阻塞性bug已修复

---

## 📝 六、开发日志模板

**每周填写**：

```markdown
## Week X 开发日志（YYYY-MM-DD）

### 本周目标
- [ ] 任务1
- [ ] 任务2

### 实际完成
- [x] 任务1
- [ ] 任务2（未完成，原因：XXX）

### 遇到的问题
1. 问题描述
   - 解决方法：XXX
   - 耗时：X小时

### 下周计划
- [ ] 继续任务2
- [ ] 开始任务3

### 需要决策的问题
（需要项目负责人确认的问题）
```

---

## 🎯 七、最终交付物

### 7.1 代码交付

- [ ] `backend/` 代码推送到 `mvp-2027-june` 分支
- [ ] 所有核心功能实现
- [ ] 核心路径测试通过
- [ ] 部署到生产环境

### 7.2 文档交付

- [ ] API文档（自动生成）
- [ ] FAQ列表
- [ ] 部署说明
- [ ] 店家试用反馈总结

### 7.3 运行环境

- [ ] 生产服务器正常运行
- [ ] 企微Webhook配置完成
- [ ] 有赞API集成完成
- [ ] 所有配置正确

---

## 📞 八、需要帮助时

**遇到问题立即报告**：

1. **技术问题**
   - 描述问题
   - 已尝试的解决方法
   - 需要的帮助

2. **需求不清晰**
   - 描述不清晰的地方
   - 可能的理解
   - 需要确认的选项

3. **时间不够**
   - 当前进度
   - 预计完成时间
   - 建议调整的范围

---

**开始开发前，请确认**：
- [x] 已阅读本文档
- [ ] 已理解MVP范围
- [ ] 已理解禁止事项
- [ ] 已理解验收标准

**现在开始 Week 1 任务！** 🚀
