---
name: 芸熙文件体量守卫
version: 1.1.0
description: "【必须在动代码前调用】芸熙烘焙 AI 客服文件体量与职责守卫。新增或修改任意 .py 文件前，用行数、公开类/方法和依赖数量触发职责评审；目标是防止上帝类，不是把文件机械切到阈值以内。超线后先判断职责是否混杂，只有存在稳定、可独立测试的职责边界时才拆分；高度内聚的单一职责可记录评审理由后保留。"
---

# 芸熙烘焙文件体量与职责守卫

## 核心目标

本守卫要阻止的是上帝类、职责漂移和难以测试的耦合，不是大文件本身。

必须坚持以下判断：

1. 行数阈值是评审触发器，不是拆分目标。
2. 不能仅凭“超过 N 行”判定上帝类；要看模块有多少独立变化原因、依赖方向和业务职责。
3. 只有抽出单元具备清晰接口、独立测试价值和稳定所有权时才拆分。
4. 如果拆分只会产生转发壳、碎片 helper、callback 穿透或循环依赖，应保留内聚实现并记录评审理由。
5. 禁止为了让门禁变绿而按行数、函数数量或代码块位置机械切文件。

长期决策见 `docs/harness-engineering/adr/0004-responsibility-first-file-size-governance.md`。

## Harness 联动

如果出现“继续往超线文件追加新职责”“拆分后职责又回流”“阈值或存量清单过时”或“为压行数硬拆”等情况，先联动 `yunxi-harness-engineering`：

- 将本次文件体量风险绑定到 trace。
- 把职责评审结论和验证命令写入 ADR、LOGBOOK 或 verification matrix。
- 若属于重复错误，写入 `docs/harness-engineering/core/mistake-ledger.md` 并补机械防线。

## 单文件体量阈值

> 阈值是“职责可能过载”的早期信号。阻断线的含义是“未经职责评审不能继续”，不是“必须把行数拆到线下”。

| 层级 | 警戒线 | 未评审阻断线 |
|------|--------|--------------|
| `app/api/*.py` | 250 行 | 350 行 |
| `app/service/*.py` | 220 行 | 320 行 |
| `app/service/llm/*.py` | 120 行 | 180 行 |
| `app/service/wecom/*.py` / `youzan/*.py` | 150 行 | 250 行 |
| `app/repository/*.py` | 150 行 | 250 行 |
| `app/models/*.py` | 80 行 | 120 行 |

**附加评审触发器：**

- 单文件公开类（非 `_` 前缀）数量超过 3 个。
- 单类公开方法数量超过 20 个。
- 单个函数/方法体超过 50 行（不含注释和空行）。
- 禁止在大文件上继续追加新职责（无论是否超线）

`scripts/check_file_sizes.py` 对超过阻断线且没有评审记录的新文件阻断提交。评审后有三种合法结果：

- `split_by_responsibility`：职责混杂，按稳定边界拆分并补独立测试。
- `keep_cohesive_with_review`：职责高度内聚，在 `OVERSIZE_REVIEW_NOTES` 写明保留理由。
- `defer_with_boundary_plan`：暂时无法安全拆分，记录候选边界并禁止继续追加无关职责。

不得把评审记录当成永久白名单；每次修改超线文件仍要确认本次改动是否引入新的变化原因。

## 上帝类判定

出现以下多个证据时，才把模块判定为上帝类并进入拆分设计：

- 单类/单模块同时承担 **≥ 4 类职责**（如：路由解析 + 业务逻辑 + DB 操作 + 外部 API 同时存在）
- 不同业务需求经常修改同一文件的不同区域，存在多个独立变化原因。
- 单元测试无法隔离某项职责，必须装配大量无关依赖。
- 依赖方向跨越 `api → service → repository → models` 边界或出现循环依赖。
- 某个子能力已有稳定输入输出合同，可以被独立 mock、替换和复用。

以下情况不应仅因行数偏长而拆分：

- 声明式映射、协议字段表、有限状态转换或单一领域规则集中表达更清晰。
- 拆分后每个文件只剩薄转发，阅读一条调用链需要跨越多个文件。
- 抽取会迫使调用方传递大量内部状态或增加 callback/闭包耦合。
- 代码虽长，但只有一个业务所有者、一个变化原因和一套可独立测试的输入输出。

## 存量文件来源

存量超线文件和评审说明以 `scripts/check_file_sizes.py` 的 `OVERSIZE_REVIEW_NOTES` 为唯一来源。不要在 Skill 中复制易过期的行数表。

修改超线文件前先读评审说明，并验证本次改动没有新增无关职责。只有职责评审结论为 `split_by_responsibility` 时，才进入 `large-file-refactor-review` 工作流。

## 职责评审流程

1. 列出文件当前职责、公开入口、主要依赖和最近三类变化原因。
2. 区分“同一职责的多个步骤”和“可独立变化的多个职责”，不要把步骤数量当职责数量。
3. 为每个候选拆分回答：能否独立测试、接口是否稳定、是否减少依赖、是否避免循环。
4. 比较保留与拆分后的认知成本；跨文件跳转、胶水代码和状态传递都计入成本。
5. 输出明确结论：`split_by_responsibility`、`keep_cohesive_with_review` 或 `defer_with_boundary_plan`。

## 好的拆分标准

- 新单元有可命名的业务职责，而不是 `part1.py`、`helpers2.py` 或按行号分段。
- 新单元能用少量参数调用，能独立 mock 和测试。
- 原模块对新单元只通过稳定接口依赖，不泄漏大量内部可变状态。
- 拆分减少变化耦合、依赖数量或测试装配成本，至少改善一项可说明的工程指标。
- 不引入循环依赖，不穿透项目分层。

## 检查方法（PowerShell）

```powershell
# 运行机器门禁并读取存量职责评审说明
python scripts/check_file_sizes.py
python scripts/check_project.py --skip-tests

# 查看所有 .py 文件行数排序
Get-ChildItem -Recurse -Filter "*.py" -Path "app" |
  ForEach-Object { [PSCustomObject]@{File=$_.Name; Lines=@(Get-Content $_.FullName).Count} } |
  Sort-Object Lines -Descending | Format-Table -AutoSize

# 单文件行数
@(Get-Content -LiteralPath "app/service/chat.py").Count

# 单文件公开类数量（不以 _ 开头的 class 定义）
Select-String -LiteralPath "app/service/chat.py" -Pattern "^class [A-Z]" | Measure-Object | Select-Object -ExpandProperty Count

# 函数行数超 50 行检测
$content = Get-Content "app/service/chat.py"
# 人工结合 IDE 展开查看各函数体行数
```

## 评审记录模板

```text
file:
size_signal:
current_responsibilities:
independent_change_reasons:
candidate_boundary:
testability_after_split:
coupling_cost:
decision: split_by_responsibility | keep_cohesive_with_review | defer_with_boundary_plan
rationale:
verification:
```

## 验收清单

- [ ] 已说明职责和变化原因，而不是只报告行数。
- [ ] 若拆分，新文件具有稳定职责、独立测试价值和清晰依赖方向。
- [ ] 若保留超线文件，已记录内聚性理由和禁止追加的新职责范围。
- [ ] 未产生薄转发壳、碎片 helper、循环依赖或大量状态穿透。
- [ ] 相关测试、`check_file_sizes.py` 和项目门禁通过。
- [ ] 长期决策或存量风险已同步 LOGBOOK、ADR 或评审说明。
