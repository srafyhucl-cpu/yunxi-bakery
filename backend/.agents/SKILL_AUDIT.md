# Skill 死亡风险审计

> 审计日期：2026-05-22（更新：2026-07-10）
> 范围：全局 `c:\Users\srafy\.agents\skills\` + 项目 `.agents\skills\`
> 操作建议仅供参考，**不自动删除任何文件**

---

## 标记说明

- DELETE **删除候选**：永久无关，建议删除
- FIX **修复候选**：触发逻辑有问题，建议修复
- KEEP **保留**：存活且触发可靠
- LOW **保留（低频）**：有明确场景但不常用
- PROJECT_SKIP **本项目不引入**：全局可保留，但不纳入 YunxiBakeBot 默认 Harness

---

## 一、项目级 Skill（本项目 `.agents/skills/`）

| 状态 | Skill | 功能说明 | 问题 |
|------|-------|---------|------|
| KEEP | `芸熙Harness工程守卫` | 较大任务、追溯、复盘、防重犯、证据留档、交接和 Skill 审计的统一入口 | 2026-06-11 新增，已联动 AGENTS、skill-reference、traceability-model、verification-matrix 和交接模板 |
| KEEP | `芸熙LLM守卫` | DeepSeek 调用、Function Calling、意图识别、对话循环的专项规范 | 已补充 Harness 联动 |
| KEEP | `芸熙架构守卫` | api/service/repository/models 分层边界、Webhook 幂等约束 | 已补充 Harness 联动 |
| KEEP | `芸熙文件体量守卫` | 用体量信号触发职责评审，防止上帝类和职责漂移 | 2026-07-10 升级为责任优先治理：职责混杂才拆，高度内聚可记录理由保留，禁止为压行数机械切分 |
| KEEP | `芸熙洁净代码守卫` | 零硬编码、函数设计、命名质量、可复用性 | 已修复：重定位为深度核查手册，与 AGENT.md 差异化；已补充 Harness 联动 |

---

## 二、全局 Skill（`c:\Users\srafy\.agents\skills\`）

### 通用工具类（非飞书）

| 状态 | Skill | 功能说明 | 本项目引入状态 |
|------|-------|---------|--------------|
| KEEP | `using-superpowers` | **元技能**：建立 skill 检索习惯，任务开始前强制检查可用 skill。核心原则"1% 概率就调用"已写入 `AGENTS.md` 零号章节 | 已引入 AGENTS.md |
| KEEP | `brainstorming` | **设计前探索**：新功能 / 新需求开发前必须调用，探索需求、提 2-3 方案、用户确认后才动代码 | 已引入 AGENTS.md Step 1，强制调用 |
| KEEP | `defuddle` | **网页转 Markdown**：查阅有赞 API 文档、DeepSeek 文档、微信开放平台文档时使用，比 WebFetch 省 token | 已引入 AGENTS.md / docs/AGENTS/quick-reference.md |
| KEEP | `skill-creator` | **Skill 工厂**：Guard Skill 需要迭代改进时使用，提供草稿→测试→迭代→description 优化全流程 | 已引入 AGENTS.md / sync-skills.md 联动 |
| LOW | `markitdown` | **本地文件转 Markdown**：用微软 markitdown 工具把 PDF/Word/Excel/PPT/图片/音频/YouTube 链接转成 markdown | 低频，保留备用 |
| PROJECT_SKIP | `json-canvas` | **Obsidian Canvas 文件编辑**：本项目无 Obsidian vault，不适用 | 不引入；全局可保留 |
| PROJECT_SKIP | `playwright-skill` | **E2E 自动化测试**：本项目用 pytest，不使用 Playwright | 不引入；全局可保留 |

### Obsidian 类（LOW 已归档/不活跃，保留备用）

| Skill | 功能说明 |
|-------|---------|
| `obsidian-cli` | 用命令行操作 Obsidian vault（读写笔记、任务、属性，支持插件开发调试）。本项目无 vault，暂不适用 |
| `obsidian-markdown` | 创建/编辑 Obsidian Flavored Markdown（wikilinks、callouts、frontmatter）。本项目暂不适用 |
| `obsidian-bases` | 创建/编辑 Obsidian Bases（`.base` 文件，类似数据库视图）。本项目暂不适用 |

### 飞书工具类

| 状态 | Skill | 功能说明 | 本项目引入状态 |
|------|-------|---------|--------------|
| KEEP | `lark-im` | 飞书即时消息：发消息/回复/搜索聊天记录/群管理/文件收发 | 已引入：生产部署结果通知、告警推送 |
| KEEP | `lark-calendar` | 飞书日历：查看日程、创建会议、管理参会人、查忙闲、预定会议室 |
| KEEP | `lark-doc` | 飞书文档（docx）+ 知识库 Wiki：创建/读取/编辑/翻译文档，支持嵌入表格/画板 |
| KEEP | `lark-drive` | 飞书云空间：上传下载文件、管理文件夹、复制移动、权限管理、导入 Word/Excel |
| KEEP | `lark-base` | 飞书多维表格（Base）：建表、字段管理、读写记录、视图配置、工作流 |
| KEEP | `lark-sheets` | 飞书电子表格：创建/读写单元格、追加行、查找内容、导出 |
| KEEP | `lark-task` | 飞书任务：创建/更新任务、子任务、清单、分配成员、任务智能体 |
| KEEP | `lark-contact` | 飞书通讯录：按姓名/邮箱查 open_id，反查员工姓名/部门/联系方式 |
| KEEP | `lark-wiki` | 飞书知识库：管理知识空间、节点层级、文档组织 |
| LOW | `lark-slides` | 飞书幻灯片：创建/编辑幻灯片，读写页面内容（XML 协议） |
| KEEP | `lark-whiteboard` | 飞书画板：导出预览图、编辑节点、支持 PlantUML/Mermaid 导入 |
| KEEP | `lark-mail` | 飞书邮箱：收发/回复/转发邮件、管理草稿/标签/联系人/规则 |
| KEEP | `lark-markdown` | 飞书 Markdown 文件：创建/读取/局部编辑/差异比较 |
| KEEP | `lark-minutes` | 飞书妙记：查询妙记列表、获取 AI 总结/待办/章节、上传音视频生成妙记 |
| KEEP | `lark-approval` | 飞书审批：查询和管理审批实例、审批任务 |
| KEEP | `lark-attendance` | 飞书考勤：查询个人考勤打卡记录 |
| KEEP | `lark-okr` | 飞书 OKR：管理目标/关键结果/对齐关系/进展记录 |
| KEEP | `lark-vc` | 飞书视频会议（历史）：搜索已结束会议、获取纪要/逐字稿/参会人快照 |
| LOW | `lark-vc-agent` | **AI bot 入会**：让机器人代用户加入/离开**正在进行中**的会议，读取实时事件（发言/共享屏幕等）。极低频 |
| LOW | `lark-event` | 飞书实时事件监听：用 NDJSON 流式接收 IM 消息/群成员变更等事件，适合长连接 bot。低频 |
| LOW | `lark-openapi-explorer` | **飞书原生 API 探索**：当其他 lark-* skill 都无法满足需求时，从官方文档查找原始 OpenAPI 接口。定位是兜底，触发时机模糊 |
| LOW | `lark-shared` | 飞书 CLI 基础：首次初始化、登录认证、切换用户/bot 身份、处理权限错误 |
| LOW | `lark-skill-maker` | 创建 lark-cli 自定义 Skill：封装飞书 API 为可复用命令 |
| LOW | `lark-workflow-meeting-summary` | **工作流**：汇总指定时间范围内多次会议纪要，生成结构化报告 |
| LOW | `lark-workflow-standup-report` | **工作流**：组合日历日程 + 未完成任务，生成今日/本周行程摘要 |

---

## 三、功能重叠分析

### 重叠组 1：内容转 Markdown（互补，不重叠）

| Skill | 输入 | 备注 |
|-------|------|------|
| `defuddle` | 网页 URL | 去噪提取正文 |
| `markitdown` | 本地文件（PDF/Word/图片/音频） | 格式转换 |

**结论**：输入来源不同，共存合理。

### 重叠组 2：飞书会议内容（有覆盖关系）

| Skill | 职责 |
|-------|------|
| `lark-vc` | 查**历史**会议记录、纪要、参会人 |
| `lark-vc-agent` | AI 真实入会，读**进行中**会议的实时事件 |
| `lark-minutes` | 处理**单次**音视频文件，生成妙记/逐字稿 |
| `lark-workflow-meeting-summary` | **聚合**多次会议纪要，依赖 lark-vc + lark-minutes 的数据 |

**结论**：有覆盖关系但分工明确，`lark-workflow-meeting-summary` 是前两者的上层组合。

### 重叠组 3：飞书日程/任务（工作流是组合封装）

| Skill | 职责 |
|-------|------|
| `lark-calendar` | 日历/日程原子操作 |
| `lark-task` | 任务原子操作 |
| `lark-workflow-standup-report` | 封装 calendar + task，快速生成日报摘要 |

**结论**：工作流是便利层，不是重复。

### 重叠组 4：飞书文档体系（分工明确）

| Skill | 职责 |
|-------|------|
| `lark-doc` | 富文本 docx / 知识库 Wiki |
| `lark-markdown` | Markdown `.md` 文件 |
| `lark-drive` | 云空间文件系统（上传/下载/权限） |

**结论**：三者均有独立职责，无实质重叠。

### 重叠组 5：brainstorming vs using-superpowers vs skill-creator（均不重叠）

- `using-superpowers`：教 AI **如何找到并调用** skill（元层面）
- `brainstorming`：功能设计前**探索需求**（过程层面）
- `skill-creator`：**创建/改进 skill** 本身（工具层面）

**结论**：无功能重叠，但 `using-superpowers` 本身存在平台兼容问题（见修复候选）。

---

## 四、行动清单（2026-05-22 已完成）

### 保留决策

- [x] 保留 `json-canvas` — 归档/不活跃，暂不适用本项目
- [x] 保留 `obsidian-cli` — 归档/不活跃，暂不适用本项目
- [x] 保留 `obsidian-markdown` — 归档/不活跃，暂不适用本项目
- [x] 保留 `obsidian-bases` — 归档/不活跃，暂不适用本项目
- [x] 保留 `playwright-skill` — 归档/不活跃，暂不适用本项目

### 已完成的修复

- [x] `using-superpowers` — 已补充 Windsurf 中文触发词到 description
- [x] `芸熙文件体量守卫` — 已加入主动检查，并升级为“体量触发职责评审、禁止机械拆分”的责任优先治理
- [x] `芸熙洁净代码守卫` — 已重定位为深度核查手册，与 AGENT.md 基础规则差异化
- [x] `lark-vc-agent` — 保留，极低频但有效（AI 代入飞书会议场景）
- [x] `lark-openapi-explorer` — 保留，已作为其他 lark-* skill 的兜底方案

### 新增调用路径

- [x] `/check` 工作流 — 步骤 0 明确调用四大守卫，添加联动表
- [x] `/review` 工作流 — 步骤 0 明确调用守卫，添加联动表
- [x] `/commit` 工作流 — 步骤 4.5 触发 `/sync-skills`
- [x] `/large-file-refactor-review` 工作流 — 联动升级为明确调用指令
- [x] `/design` 工作流（新建）— 步骤 1 强制调用 `brainstorming`
- [x] `/update-knowledge` 工作流（新建）— 步骤 1 调用 `markitdown`
- [x] `/sync-skills` 工作流 — 步骤 4 新建 skill 时调用 `skill-creator`
