# Bakery Commerce Platform 历史后台前端重构方案 v1

- 日期：2026-05-25
- 状态：方案已确认，待书面审阅
- 范围：后台前端整体重构，不借机做后端大重构
- 说明：这是后台前端重构的历史设计稿，反映的是当时的命名和阶段判断；当前产品与仓边界请以 `README.md` 和 `docs/architecture/project-boundaries.md` 为准。

## 1. 背景与目标

当前后台前端基于 `FastAPI + Jinja2 模板 + 原生 CSS + 原生 JS`，已经能支撑基础管理能力，但随着页面增加、交互复杂度提升和三端适配要求明确，现有形态开始出现以下问题：

1. 页面结构和交互复用能力弱，新页面容易继续堆叠模板、脚本和样式。
2. PC、Pad、Phone 三端体验难以统一，复杂页面越来越依赖页面级补丁。
3. 后台已经逐渐从“几张管理模板页”演变成“完整任务型应用”，现有技术路径不再适合继续扩张。
4. 新需求开始强调抽屉编辑、状态可视化、失败排查、筛选交互和移动端可操作性，现有前端组织方式维护成本偏高。

本次重构目标如下：

1. 在当前仓库内新增独立后台前端应用 `web/admin`。
2. 使用 `Vue 3 + Vite + TypeScript + Element Plus` 重做后台表现层。
3. 保持 `FastAPI` 继续负责业务真源和 `/api/v1/admin/*` 接口。
4. 第一阶段覆盖整个后台，而不是只迁一个局部页面。
5. 后台设计从一开始就按 `PC / Pad / Phone` 三端任务体验来做，而不是桌面版做完后再被动压缩。
6. 迁移期间旧 Jinja 后台冻结，不再承接复杂新功能。

### 1.1 前置决策

以下关键决策已在方案讨论阶段确认，本方案默认以这些前提为基础继续展开：

1. 在当前仓库内建设 `web/admin`，不新建独立前端仓库。
2. 新旧后台在工程层面短期并行，但最终由 `/admin` 一次性切换到新后台。
3. 新后台技术栈采用 `Vue 3 + Vite + TypeScript + Element Plus`。
4. 本次重构聚焦后台前端整体升级，不借机做后端大重构。

## 2. 页面信息架构与三端适配策略

### 2.1 信息架构

一级导航：

- 概览
- AI 测试
- 商品管理
- 知识配置
- 数据观察台
- 转人工
- 系统配置

二级结构建议如下：

```txt
商品管理
  - 商品列表
  - 主推款
  - 商品同步/来源状态

知识配置
  - 知识库条目
  - 问答配置
  - 意图/规则配置

数据观察台
  - 会话记录
  - AI 命中情况
  - 失败/转人工原因
  - 渠道状态

系统配置
  - 店铺配置
  - API/Token 配置
  - 渠道配置
```

其中，`主推款` 最终挂到 `商品管理` 下，但第一期可保留一级入口，以降低迁移期认知成本。

### 2.2 页面类型

后台页面分三类：

1. 工作台型
   - 商品管理
   - 主推款
   - 知识配置
   - 系统配置
2. 排查型
   - 数据观察台
   - 转人工
   - 会话记录
   - 失败原因
   - 渠道状态
3. 操作型
   - AI 测试
   - 概览

三类页面的标准结构如下：

```txt
工作台型：
筛选区
列表区
右侧抽屉 / 手机全屏面板
底部固定操作栏

排查型：
状态筛选
时间线 / 日志流
详情面板
异常原因
重试 / 复制 / 标记处理

操作型：
输入
反馈
状态
指标
快捷操作
```

### 2.3 三端适配策略

PC：

- 左侧固定导航
- 顶部工具栏
- 主内容最大宽度自适应
- 列表页默认表格
- 右侧 Drawer 编辑

Pad：

- 侧边栏可收起
- 表格减少列
- 筛选区可折叠
- 详情抽屉 70% 宽度

Phone：

- 底部主导航
- 顶部标题 + 更多菜单
- 列表全部卡片化
- 筛选进入弹层
- 编辑/详情全屏面板
- 保存按钮底部固定

Phone 底部导航最多保留 4 到 5 个主入口，推荐：

```txt
概览
AI 测试
商品
观察台
我的/更多
```

其余入口进入“更多”：

```txt
知识配置
转人工
系统配置
退出登录
```

核心原则：

> PC 是管理效率，Pad 是半管理半操作，Phone 是快速处理任务。

最终结论：

> 新后台不是桌面表格站，而是一套三端任务后台。

## 3. 前端技术落地方式

### 3.1 工程位置与总体方向

新后台位于当前仓库：

```txt
yunxibakebot/
  app/
  web/
    admin/
```

其定位为：

- `web/admin` 是当前仓库内的独立 Vue 管理后台应用
- `FastAPI` 继续负责业务能力和 `/api/v1/admin/*`
- `Vue` 只接管后台表现层
- 旧 Jinja 后台进入迁移期，不再新增复杂功能

### 3.2 第一阶段路由范围

第一阶段优先落以下路由：

```txt
/admin
/admin/overview
/admin/chat-test
/admin/products
/admin/products/featured
/admin/knowledge
/admin/observability
/admin/observability/sessions
/admin/observability/failures
/admin/transfers
/admin/settings
/admin/settings/shop
/admin/settings/channel
/admin/settings/api
```

这些路径后置，不作为第一阶段必须项：

```txt
/admin/products/sync-status
/admin/knowledge/qa
/admin/knowledge/rules
/admin/observability/hit-analysis
```

路由约束：

- `path` 表达业务位置
- `query` 表达筛选状态
- 临时 UI 状态不进入 URL

允许进入 URL 的例子：

```txt
/admin/products?keyword=蛋糕&status=active&page=2
/admin/observability/failures?channel=wecom&level=error
```

不进入 URL 的例子：

- 抽屉是否打开
- 当前展开了哪个卡片
- 移动端筛选弹层是否显示

### 3.3 状态管理

使用 `Pinia`，但只管理真正全局的状态：

```txt
stores/
  auth.ts
  app.ts
  settings.ts
```

约定如下：

- `auth.ts`：token、登录状态、管理员信息
- `app.ts`：sidebar、device、theme、全局 loading
- `settings.ts`：少量跨页共享的店铺/渠道配置缓存

明确规则：

> 列表筛选、分页、当前选中项、抽屉开关，默认不进入 Pinia。

这些状态优先保留在页面内部或 composable 中，例如：

```txt
pages/products/useProductsPage.ts
pages/knowledge/useKnowledgePage.ts
pages/transfers/useTransfersPage.ts
```

### 3.4 API 封装

前端 API 结构建议如下：

```txt
services/
  http.ts
  auth.ts
  products.ts
  knowledge.ts
  observability.ts
  transfers.ts
  settings.ts

types/
  product.ts
  knowledge.ts
  session.ts
  transfer.ts
  settings.ts

schemas/
  product.ts
  knowledge.ts
  observability.ts
```

约束：

- 页面不直接 `fetch`
- 页面不拼裸 URL
- service 不写 UI 提示
- `http.ts` 统一处理 token、401、timeout、基础错误
- 业务错误由页面决定如何展示

`schemas/` 用于接口返回校验，建议使用 `Zod`。

### 3.5 组件分层

建议结构：

```txt
components/
  ui/
  layout/
  feedback/

features/
  products/
  knowledge/
  observability/
  transfers/
  chat-test/
```

边界：

- `components/ui/`：通用基础组件
- `components/layout/`：壳子、导航、顶部栏等布局组件
- `components/feedback/`：空态、错误态、加载态等反馈组件
- `features/`：按业务域组织的组合组件

例如：

```txt
components/ui/StatusTag.vue
features/products/ProductStatusTag.vue
features/transfers/TransferTimeline.vue
```

### 3.6 三端适配沉入组件层

响应式能力不依赖页面补丁，而作为组件能力沉下去。建议准备：

```txt
ResponsiveList
ResponsiveFilterBar
ResponsiveDrawer
ResponsiveDescription
StickyActionBar
PageContainer
```

示例：

```vue
<ResponsiveList
  :items="products"
  desktop-mode="table"
  mobile-mode="card"
/>
```

```vue
<ResponsiveDrawer
  v-model="visible"
  title="编辑商品"
>
  ...
</ResponsiveDrawer>
```

行为要求：

- PC：右侧抽屉
- Pad：70% 宽抽屉
- Phone：全屏面板

### 3.7 设备判断规范

统一提供：

```txt
composables/
  useDevice.ts
```

输出：

- `isPhone`
- `isPad`
- `isPC`
- `deviceType`

断点固定：

```txt
phone: < 768
pad: 768 - 1199
pc: >= 1200
```

禁止在页面和组件中直接散写 `window.innerWidth` 判断。

### 3.8 目录定稿

```txt
web/admin/
  public/
  src/
    main.ts
    App.vue

    router/
      index.ts
      routes.ts

    stores/
      auth.ts
      app.ts
      settings.ts

    services/
      http.ts
      auth.ts
      products.ts
      knowledge.ts
      observability.ts
      transfers.ts
      settings.ts

    types/
      product.ts
      knowledge.ts
      session.ts
      transfer.ts
      settings.ts

    schemas/
      product.ts
      knowledge.ts
      observability.ts

    layouts/
      AdminLayout.vue
      AuthLayout.vue

    pages/
      overview/
      chat-test/
      products/
      knowledge/
      observability/
      transfers/
      settings/

    features/
      products/
      knowledge/
      observability/
      transfers/
      chat-test/

    components/
      ui/
      layout/
      feedback/

    composables/
      useDevice.ts
      useQueryState.ts
      useResponsiveDrawer.ts

    utils/
      format.ts
      date.ts

    styles/
      variables.css
      global.css
      responsive.css
```

## 4. 迁移与部署策略

### 4.1 生命周期与入口策略

`/admin-v2`：

- 只用于联调、验收、灰度验证
- 正式切换后删除或隐藏

`/admin-legacy`：

- 只用于上线后短期回滚
- 稳定 1 到 2 周后移除

结论：

> `/admin-v2` 和 `/admin-legacy` 都是迁移工具，不是长期产品结构。

### 4.2 分阶段入口接管

开发期：

- `web/admin` 使用 Vite 独立开发
- Vite 代理 `/api` 到 FastAPI
- 旧 `/admin` 不受影响

联调期：

- 新后台挂 `/admin-v2`
- 旧后台继续保留 `/admin`
- `/admin-v2` 只用于验收，不作为长期入口

切换期：

- `/admin` 切到新 Vue 后台
- 旧 Jinja 后台退到 `/admin-legacy`
- `/admin-legacy` 只作为短期回滚兜底

部署期：

- 不新增 Node 服务
- Vue 构建产物由 FastAPI 或 Nginx 托管
- `/api/v1/admin/*` 继续由 FastAPI 处理
- `/admin/*` 做 SPA fallback

### 4.3 SPA 路由规则

生产路由规则：

```txt
/api/v1/admin/*   -> FastAPI API
/admin/assets/*   -> 静态资源
/admin/*          -> Vue index.html
```

要求：

- API 路由优先
- 静态资源其次
- SPA fallback 最后兜底

否则以下刷新场景会 404：

```txt
/admin/products
/admin/knowledge
/admin/settings/shop
```

### 4.4 缓存策略

缓存规则：

- `index.html`：`no-cache`
- `assets/*.js`：带 hash，长缓存
- `assets/*.css`：带 hash，长缓存

这样可以避免旧入口文件阻挡新版本发布，同时保留静态资源缓存收益。

### 4.5 环境变量与构建配置

建议准备：

```txt
.env.development
.env.staging
.env.production
```

基础变量：

```txt
VITE_API_BASE=/api/v1/admin
VITE_ROUTER_BASE=/admin
```

开发期：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:7001`
- `/api` -> `http://127.0.0.1:7001`

验收期：

```txt
VITE_ROUTER_BASE=/admin-v2
```

正式期：

```txt
VITE_ROUTER_BASE=/admin
```

禁止把 `/admin-v2` 的临时逻辑写死进代码。

### 4.6 迁移原则

旧 Jinja 后台：

- 只修阻断性 bug
- 不新增复杂功能
- 不做结构级改造

新 Vue 后台：

- 承接所有新功能
- 承接所有体验优化
- 承接三端适配

### 4.7 回滚策略

回滚必须具备两层兜底：

1. 保留上一版前端构建产物
2. 保留短期 `/admin-legacy`

并且需要在正式切换前完成一次回滚演练：

```txt
/admin 指向新后台
模拟发现问题
/admin 切回旧后台或上一版构建产物
确认登录、核心页面可用
```

> 没有演练过的回滚方案，不算上线保障。

## 5. 接口与后端配合改造边界

### 5.1 总原则

```txt
Vue 后台只重做表现层
后端继续作为业务真源
不借前端迁移做后端大重构
```

### 5.2 先承认现状

当前后台接口已经“能用”，但形态不统一，例如：

```txt
AI 测试：
{ code, reply, intent, session_id }

转人工列表：
{ code, data: [...] }

商品列表：
{ code, total, data: [...] }

主推款：
{ code, data }

商品启停：
{ code, is_active, title }
```

因此本次策略不是立刻重写全部接口，而是：

```txt
旧接口保留
新前端 service 层先做适配
确实影响体验或复用的接口，再补标准化版本
```

### 5.3 可直接复用与最小补齐

可优先复用的能力域：

- AI 测试
- 商品管理
- 主推款
- 知识配置
- 数据观察台
- 转人工
- 系统配置

最小必要改造只做以下几类：

1. 补列表标准结构
2. 补详情聚合接口
3. 补统计摘要接口
4. 补枚举/配置接口
5. 补 `auth/me` 状态接口
6. 抽公共 admin 鉴权依赖

明确不做：

- 不重写 repository
- 不重写 service
- 不重做业务模型
- 不大面积改历史业务逻辑

### 5.4 列表、详情、写操作约束

列表接口标准结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

补充原则：

- 后端只返回数据和分页结果
- 前端负责保存 query/filter 状态
- 接口不返回当前 UI 选项状态

写操作标准结构：

```json
{
  "ok": true,
  "message": "已保存",
  "data": {}
}
```

`data` 可选，但结构保留，方便前端局部更新而不是每次整页重拉。

详情接口可采用两种形式之一：

```json
{
  "item": {}
}
```

或直接返回完整详情对象，但必须稳定、清晰、可直接驱动页面。

### 5.5 鉴权与认证边界

当前后台主要依赖 `admin_token` cookie 和 Bearer token。为了兼容迁移期，建议：

1. 继续兼容当前管理员 cookie/token 方案
2. 前端 `http.ts` 同时兼容旧结构
3. 401 统一视为未登录或登录过期
4. 403 统一视为 token 无效或无权限

补一个最小状态接口：

```txt
GET /api/v1/admin/auth/me
```

返回：

```json
{
  "ok": true,
  "data": {
    "role": "admin",
    "name": "管理员"
  }
}
```

即使当前没有完整管理员体系，也建议返回稳定的基础身份信息，供前端刷新后判断登录态。

### 5.6 公共鉴权依赖

建议新增：

```txt
app/api/deps.py
  verify_admin_token()
  check_admin_cookie()
```

目标是统一 admin 鉴权入口，避免 `admin.py`、`admin_config.py` 和后续新接口继续复制粘贴校验逻辑。

### 5.7 前端 http 兼容策略

前端 `http.ts` 迁移期兼容规则：

```txt
code === 0 视为成功
ok === true 视为成功
HTTP 401 统一跳登录
HTTP 403 显示无权限
```

### 5.8 最终接口规范

```txt
列表：
items + total + page + page_size

写操作：
ok + message + data

错误：
detail

时间：
统一 ISO 字符串

布尔：
统一 true / false

枚举：
后端给稳定值，前端负责中文展示
```

## 6. 实施分期与验收标准

### 6.1 预备动作

在阶段 A 前先完成盘点：

1. 旧后台现有页面
2. 旧后台现有 API
3. 每个页面主任务路径
4. 每个页面是否必须首期迁移
5. 每个接口是直接复用、service 层适配还是后端补接口

这份结果形成 API 适配地图。

### 6.2 阶段 A：前端基础设施

内容：

- `web/admin` 工程初始化
- 路由、布局、登录态、API 封装完成
- 三端基础壳子完成
- 响应式基础组件完成
- 本地代理和构建流程跑通

验收标准：

- 能正常登录
- 能跑通空白演示页
- 三端都能进入后台且布局不崩
- 本地开发、构建和代理链路全部正常

### 6.3 阶段 B：核心业务页迁移

迁移页面：

- 概览
- AI 测试
- 商品管理
- 主推款
- 知识配置
- 数据观察台
- 转人工
- 系统配置

每页按 `P0 / P1 / P2` 拆分：

- `P0`：切 `/admin` 前必须完整可用
- `P1`：可上线后补强，但不能阻断主任务
- `P2`：体验增强，不影响切换

### 6.4 阶段 C：/admin-v2 联调验收

内容：

- 对照旧后台逐页验收
- 修接口适配问题
- 修三端响应式问题
- 完成切换验收表
- P0 阻断缺陷清零

必须产出一张切换验收表：

```txt
页面
主任务
PC 是否通过
Pad 是否通过
Phone 是否通过
接口是否稳定
是否允许切换
备注
```

### 6.5 阶段 D：正式切换

动作：

- `/admin` 切新 Vue 后台
- 旧后台退到 `/admin-legacy`
- 保留上一版静态资源
- 回滚方案已演练
- 观察 1 到 2 周后移除旧入口

### 6.6 切换门槛

切 `/admin` 前必须满足：

1. 一期 P0 功能全部完成
2. 主任务路径全部通过
3. PC / Pad / Phone 三端验收通过
4. 关键 API 稳定
5. `/admin-v2` 验收通过
6. P0 阻断缺陷为 0
7. 回滚方案已验证可执行

### 6.7 缺陷分级

P0 阻断缺陷示例：

- 无法登录
- 核心页面白屏
- 主任务按钮无响应
- 保存失败但无提示
- 手机端无法完成关键操作
- 刷新路由 404
- 401 后不能回登录

规则：

- `P0` 阻断缺陷：0 个
- `P1` 严重缺陷：可接受极少量，但必须有替代路径
- `P2` 体验问题：允许记录到切换后优化

### 6.8 三端验收方式

不能只靠桌面浏览器缩放，必须包含真设备与响应式双验收。

最低验收矩阵：

- PC：Chrome / Edge，完整管理流
- Pad：iPad 或等效尺寸，验证侧栏、抽屉、表格压缩
- Phone：iPhone 或 Android 至少一种真机，验证底部导航、卡片列表、全屏面板、固定操作栏

Phone 端验收重点：

- 能看懂状态
- 能快速处理
- 能保存
- 能返回
- 不误触

## 7. 第一期页面范围与任务清单

### 7.1 第一期页面范围

- 概览
- AI 测试
- 商品管理
- 主推款
- 知识配置
- 数据观察台
- 转人工
- 系统配置

交付原则：

- 所有页面都迁移
- 以 `P0` 作为切 `/admin` 的最低交付标准
- `P1 / P2` 可在切换后继续增强
- 页面能打开不算完成，主任务路径完整才算完成

### 7.2 页面 P0 最低交付标准

#### 概览

- 展示核心运营摘要
- 提供关键指标卡片
- 提供近期异常或待处理入口
- 可跳转到商品、观察台、转人工等关键页

#### AI 测试

- 新建测试会话
- 发送消息
- 展示 AI 回复
- 展示意图识别结果或关键调试信息
- 查看当前会话消息流

说明：P0 必须表现为聊天工作台，而不是表格页。

#### 商品管理

- 商品列表
- 关键词搜索
- 上下架 / 启停
- 商品详情查看
- 来源状态查看
- 最近同步信息可见

#### 主推款

- 查看主推款列表
- 调整主推状态或主推内容
- 保存配置
- 查看当前生效状态

#### 知识配置

- 知识条目列表
- 搜索 / 分类筛选
- 新建
- 编辑
- 停用
- 查看 AI 可读状态
- 查看失败原因
- 手动重试同步
- 查看最近历史

特别说明：

> 知识配置是 P0 页面，但其中“新建 / 编辑 / 重试同步”可能需要后端补最小接口。

#### 数据观察台

P0 先只保证“查问题”：

- 会话记录
- 失败记录
- 详情查看
- 原因排查
- 基础筛选

特别说明：

> 数据观察台 P0 先保证查问题，不追求 BI 图表。

#### 转人工

- 转人工列表可看
- 查看会话详情
- 接受 / 处理 / 关闭
- 人工回复
- 查看基础状态流转

#### 系统配置

P0 先区分：

- 可安全展示的配置：可查看
- 允许后台修改的配置：可保存
- 敏感配置：脱敏展示，修改需明确确认

### 7.3 开发顺序建议

建议开发顺序按切换风险排序：

```txt
1. 登录 / 布局 / 三端壳子
2. AI 测试
3. 商品管理
4. 主推款
5. 转人工
6. 数据观察台
7. 知识配置
8. 系统配置
9. 概览
```

理由：

- `AI 测试`、`商品管理`、`主推款`、`转人工` 与现有能力贴得更近
- 更容易形成可联调、可验收闭环
- `知识配置` 和 `系统配置` 更可能涉及补接口、权限和敏感字段处理

### 7.4 优先级说明

高优先级核心页：

- AI 测试
- 商品管理
- 主推款
- 知识配置
- 数据观察台
- 转人工

中优先级支撑页：

- 概览
- 系统配置

## 8. 风险与待确认事项

1. 知识配置 P0 接口缺口
   - 新建、编辑、重试同步能力可能需要后端补最小接口。
2. 系统配置敏感字段处理方式
   - 需明确哪些配置可见、可改、需脱敏和需二次确认。
3. `/admin-v2` 和 `/admin-legacy` 生命周期
   - 需在实施时写入实际下线路径和时间点。
4. 三端真设备验收清单
   - 需落实为具体设备与浏览器组合。
5. 回滚演练步骤
   - 需形成可执行步骤文档，而不是只有原则描述。
6. 旧后台冻结范围
   - 需明确哪些问题算阻断性 bug，哪些变更必须转入新前端实现。
7. 旧接口适配地图缺失
   - 若未先盘点旧页面与旧 API，可能导致 Vue 页面开发过程中反复返工。
