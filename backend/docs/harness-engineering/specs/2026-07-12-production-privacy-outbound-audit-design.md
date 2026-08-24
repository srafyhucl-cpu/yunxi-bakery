# 生产隐私出站聚合审计设计

> trace_id: `20260711-global-risk-remediation`
> 约束来源: 全局风险整改计划 R3-A、ADR 0005

## 目标

把模型调用、离线 Agent、LangSmith、trace 元数据和结构化敏感字段纳入一个可重复执行的隐私出站门禁，替代分散测试和人工搜索形成的弱证据。

## 方案

1. 使用 AST 自动发现 `app/service` 内所有 `get_langchain_chat_model` 调用模块，要求同模块调用统一 `privacy_redaction` helper。
2. 限制 `ChatOpenAI` 只能出现在共享模型工厂，`AsyncOpenAI` 只能出现在 ASR 窄适配器。
3. 使用无真实数据的嵌套 payload 验证手机号、地址、open_id、订单号和原始消息按结构化键替换；同时验证 trace 敏感字段过滤。
4. 默认模式只做本地静态和动态检查，并接入 `check_project.py`；生产模式通过 SSH 只回传离线任务、LangSmith tracing 和 key 是否配置的布尔值。
5. 报告不调用外部模型、不读取业务数据库、不启用 LangSmith，也不输出任何密钥值。

## 代码边界

- 脱敏规则继续由 `app/service/privacy_redaction.py` 单一拥有，模型入口不重复维护规则。
- 聚合门禁只检查生产路径合同，不成为运行时代理或第二条外发路径。
- 真实生产主体删除仍是独立证据缺口，本专项不替代该验证。

## 验收

- 自动发现的模型调用模块全部经过统一脱敏。
- 结构化和非结构化合成敏感值在外发 payload 中零残留。
- trace metadata 中密钥、画像和工具结果零残留。
- 生产离线 QA、知识缺口、memory 和 LangSmith 三类 tracing 开关全部关闭，LangSmith key 未配置。
- 聚合门禁加入统一项目质量检查，后续新增未脱敏模型入口会阻断提交。
