import re

file_path = "web/admin/src/features/observability/ObservabilityWorkbench.vue"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove `{ key: "current", label: "当前知识" },`
content = re.sub(
    r"\s*\{\s*key:\s*\"current\",\s*label:\s*\"当前知识\"\s*\},", "", content
)

# 2. 移除工具栏中的 `v-if="page.activeTab === 'current'"` 区块。
# 先移除完整的 `<div v-if="page.activeTab === 'current'" class="observability-page__toolbar"> ... </div>`。
toolbar_pattern = r'\s*<!-- 紧凑单行筛选工具栏：当前知识 -->\s*<div v-if="page\.activeTab === \'current\'" class="observability-page__toolbar">.*?</div>\s*</div>\s*</div>'
content = re.sub(toolbar_pattern, "", content, flags=re.DOTALL)

# 工具栏中的 `v-else-if="page.activeTab === 'history'"` 改为 `v-if="page.activeTab === 'history'"`
content = content.replace(
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__toolbar">',
    '<div v-if="page.activeTab === \'history\'" class="observability-page__toolbar">',
)

# 3. 桌面表格
table_pattern = r'\s*<!-- 当前内容表格 -->\s*<el-table\s*v-if="page\.activeTab === \'current\'".*?</el-table>'
content = re.sub(table_pattern, "", content, flags=re.DOTALL)

# 表格中的 `v-else-if="page.activeTab === 'history'"` 改为 `v-if="page.activeTab === 'history'"`
content = content.replace(
    "<el-table\n          v-else-if=\"page.activeTab === 'history'\"",
    "<el-table\n          v-if=\"page.activeTab === 'history'\"",
)

# 4. 移动端列表
mobile_list_pattern = r'\s*<div v-else-if="page\.activeTab === \'current\'" class="observability-page__cards">.*?</div>\s*</button>\s*</div>'
content = re.sub(mobile_list_pattern, "", content, flags=re.DOTALL)

# 移动端列表保留历史页的 `v-else-if`
content = content.replace(
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__cards">',
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__cards">',
)
# 注意：骨架屏使用 `v-if="page.loading"`，因此 history 仍应使用 `v-else-if`

# 5. 详情抽屉的 track-btn
content = content.replace(
    ":show-track-btn=\"page.activeTab === 'current'\"", ':show-track-btn="false"'
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
