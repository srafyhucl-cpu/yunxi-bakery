# Bakery Commerce Platform — API 接口规范

> 版本：v0.2.0 | 最后更新：2026-06-04 | 在线文档：`http://<host>:7001/docs`
>
> 说明：本文件是早期人工整理的接口总览，适合快速扫读，不是当前唯一权威契约。当前真实接口以运行中的 FastAPI OpenAPI 文档和现网兼容路由为准；其中 `/api/v1/miniapp/*` 与 `/api/v1/admin/*` 仍作为对外稳定路径保留。

---

## 一、通用约定

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| 协议 | HTTP/1.1 + JSON |
| 编码 | UTF-8 |
| 认证 | 各渠道独立签名验证（见第二节） |
| 服务器端口 | 7001 |

### 1.2 标准响应格式

```json
// 成功
{"code": 0, "msg": "success"}

// 业务错误
{"code": <status_code * 100>, "message": "<错误描述>"}
```

### 1.3 HTTP 状态码速查

| 状态码 | 含义 | 触发场景 |
|--------|------|---------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求错误 | JSON 解析失败 / 缺少必填字段 |
| 403 | 禁止访问 | 签名验证失败 |
| 404 | 资源不存在 | 会话/知识条目未找到 |
| 500 | 服务器错误 | 未预期异常（全局兜底） |
| 502 | 网关错误 | LLM/外部 API 调用失败 |

### 1.4 错误码速查

| 错误码 | 说明 | 来源 |
|--------|------|------|
| 40000 | 请求参数错误 | API 层校验 |
| 40300 | 认证失败 | 签名验证 |
| 40400 | 资源不存在 | 业务逻辑 |
| 50000 | 服务器内部错误 | 全局兜底 |
| 50200 | 外部服务错误 | LLM / 有赞 API |

---

## 二、认证机制

### 2.1 有赞 Webhook — MD5 签名

```
签名算法：MD5(client_id + raw_body + client_secret)
请求头：event-sign: <签名值>
```

验证流程：
1. 从请求头获取 `event-sign`
2. 读取请求体原始字节 `raw_body`
3. 使用 `YOUZAN_CLIENT_ID` + `raw_body` + `YOUZAN_CLIENT_SECRET` 计算 MD5
4. 与 `event-sign` 常量时间比较（防时序攻击）

### 2.2 企微回调 — SHA1 签名

```python
# 签名算法（企微标准）
token + timestamp + nonce + encrypt_msg → SHA1
```

---

## 三、对外接口（第三方回调）

### 3.1 有赞 Webhook 回调

**端点**: `POST /api/v1/webhook/youzan`

**请求头**:
```
Content-Type: application/json
event-sign: <MD5 签名>
event-type: <事件类型，可选>
x-rontgen: traceId=<链路追踪ID>;...
```

**响应**: `{"code": 0, "msg": "success"}` （立即秒回，异步处理）

**支持的事件类型**:

| 事件类型 | 业务含义 | 去重策略 |
|---------|---------|---------|
| `trade_*` | 交易事件（下单/支付/退款等） | msg_id 内存锁 + DB |
| `item_*` | 商品事件（上下架/信息变更） | msg_id 内存锁 + DB |
| `youzan_item_skustockorsoldnumupdated` | 库存/销量变更 | msg_id 内存锁 + DB |
| 空（无 event-type） | 买家咨询客服消息 | msg_id 内存锁 + DB |

**去重机制**:
- 第一级：10 秒内存滑动窗口锁（高并发秒杀）
- 第二级：数据库 `msg_id` 已处理检查
- 清洗：30 秒 TTL 定时自愈

---

## 四、管理后台接口

### 4.1 系统健康

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 → `{"status":"ok","version":"0.2.0"}` |
| GET | `/docs` | OpenAPI Swagger UI |
| GET | `/redoc` | OpenAPI ReDoc 文档 |

### 4.2 前端入口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 管理后台前端 SPA（含向量构建进度页） |
| GET | `/admin/*` | 前端路由 fallback |
| GET | `/api/admin/vector-build-status` | 向量索引构建进度查询 |
| POST | `/api/admin/vector-build-retry` | 手动触发向量重建 |

### 4.3 对话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/sessions` | 会话列表查询 |
| GET | `/api/admin/sessions/{session_id}` | 会话详情（含消息历史） |
| POST | `/api/admin/sessions/{session_id}/transfer` | 手动转人工 |
| GET | `/api/admin/dialogs` | 对话检索 |

### 4.4 知识管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/knowledge` | 知识条目列表 |
| POST | `/api/admin/knowledge` | 新增知识条目 |
| PUT | `/api/admin/knowledge/{id}` | 编辑知识条目 |
| DELETE | `/api/admin/knowledge/{id}` | 下架知识条目 |
| POST | `/api/admin/knowledge/sync` | 触发知识同步 |
| GET | `/api/admin/knowledge/categories` | 知识分类列表 |

### 4.5 店铺配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/shop/config` | 获取店铺配置 |
| PUT | `/api/admin/shop/config` | 更新店铺配置 |

### 4.6 数据观察台

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/observability/overview` | 数据概览 |
| GET | `/api/admin/observability/content-changes` | 内容变更历史 |
| GET | `/api/admin/observability/webhook-events` | Webhook 审计事件 |

### 4.7 商品管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/products` | 商品列表 |
| POST | `/api/admin/products/reconcile` | 触发商品对账 |

---

## 五、企微集成

### 5.1 企微消息回调

**端点**: `GET/POST /api/v1/webhook/wecom`

当前状态：生产已接入微信客服回调、验签解密、消息队列、AI 回复和人工接手同步。

### 5.2 企微智能机器人插件

**基础端点**: `/api/v1/wecom/intelligent-bot`

鉴权：

- Header：`X-Yunxi-Bot-Key`
- 值：生产环境 `WECOM_BOT_PLUGIN_API_KEY`
- 不支持 URL query 参数传密钥，避免密钥进入访问日志。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/plugins/ping` | 连通性验证 |
| POST | `/tools/order-lookup` | 查订单摘要 |
| POST | `/tools/product-lookup` | 查商品价格、库存、分类 |
| POST | `/tools/knowledge-answer` | 查知识库答案 |
| POST | `/tools/customer-lookup` | 查客户地址簿线索，返回脱敏结果 |
| POST | `/tools/group-campaign-summary` | 查客户群批次汇总 |
| POST | `/tools/handoff-pending` | 查待人工列表 |
| POST | `/tools/ops-summary` | 查观察台值守摘要 |
| POST | `/tools/integration-status` | 查同步排障摘要 |
| POST | `/tools/offline-review-summary` | 查离线复盘摘要 |

所有工具均为只读；订单、客户地址、客户群待跟进、转人工摘要和 webhook 错误细节只返回脱敏或白名单字段。

---

## 六、系统架构速查

```
有赞/企微 客户端
    │
    ▼
┌─────────────────┐
│  API 层 (webhook)│  ← 签名验证 + 消息解析 + 去重
└────────┬────────┘
         │
    ┌────▼────┐
    │ Service │  ← 对话循环 + 系统事件分发 + 知识检索
    └────┬────┘
         │
    ┌────▼──────┐
    │ Repository│  ← SQLite CRUD + 参数化绑定
    └────┬──────┘
         │
    ┌────▼──┐
    │ Models │  ← Pydantic 数据模型（纯类型定义）
    └────────┘
```

**关键原则**：
- API 层穿透访问 Repository → ❌ 阻断（pre-commit 检查）
- SQL f-string 拼接 → ❌ 阻断（必须使用 `?` 占位符）
- `SELECT *` → ❌ 阻断（必须明确列出字段）

---

## 七、部署速查

```bash
# 本地开发
uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload

# Docker 部署
docker-compose up -d

# 健康检查
curl http://127.0.0.1:7001/health

# 知识种子导入
python scripts/seed_baseline_knowledge.py
python scripts/seed_baseline_knowledge.py --apply

# 锁文件更新（依赖变更后）
pip-compile requirements.in --output-file requirements.txt
pip-compile requirements-dev.in --output-file requirements-dev.txt
```
