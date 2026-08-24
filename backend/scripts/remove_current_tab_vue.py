import re

file_path = "web/admin/src/features/observability/ObservabilityWorkbench.vue"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove `{ key: "current", label: "当前知识" },`
content = re.sub(
    r"\s*\{\s*key:\s*\"current\",\s*label:\s*\"当前知识\"\s*\},", "", content
)

# 2. Change `v-if="page.activeTab === 'current'"` block (Toolbar) to remove it.
# First, remove the whole `<div v-if="page.activeTab === 'current'" class="observability-page__toolbar"> ... </div>`
toolbar_pattern = r'\s*<!-- 紧凑单行筛选工具栏：当前知识 -->\s*<div v-if="page\.activeTab === \'current\'" class="observability-page__toolbar">.*?</div>\s*</div>\s*</div>'
content = re.sub(toolbar_pattern, "", content, flags=re.DOTALL)

# Change `v-else-if="page.activeTab === 'history'"` to `v-if="page.activeTab === 'history'"` for Toolbar
content = content.replace(
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__toolbar">',
    '<div v-if="page.activeTab === \'history\'" class="observability-page__toolbar">',
)

# 3. Desktop Table
table_pattern = r'\s*<!-- 当前内容表格 -->\s*<el-table\s*v-if="page\.activeTab === \'current\'".*?</el-table>'
content = re.sub(table_pattern, "", content, flags=re.DOTALL)

# Change `v-else-if="page.activeTab === 'history'"` to `v-if="page.activeTab === 'history'"` for Table
content = content.replace(
    "<el-table\n          v-else-if=\"page.activeTab === 'history'\"",
    "<el-table\n          v-if=\"page.activeTab === 'history'\"",
)

# 4. Mobile List
mobile_list_pattern = r'\s*<div v-else-if="page\.activeTab === \'current\'" class="observability-page__cards">.*?</div>\s*</button>\s*</div>'
content = re.sub(mobile_list_pattern, "", content, flags=re.DOTALL)

# Change `v-else-if="page.activeTab === 'history'"` to `v-if`
content = content.replace(
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__cards">',
    '<div v-else-if="page.activeTab === \'history\'" class="observability-page__cards">',
)
# wait! the skeleton is `v-if="page.loading"`, so `history` should stay `v-else-if`

# 5. DetailDrawer track-btn
content = content.replace(
    ":show-track-btn=\"page.activeTab === 'current'\"", ':show-track-btn="false"'
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
