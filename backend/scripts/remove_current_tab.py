import re

file_path = "web/admin/src/features/observability/useObservabilityWorkbench.ts"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. normalizeTab: remove 'current'
content = content.replace(
    'mode === "failures" ? ["history", "webhooks"] : ["current", "history", "webhooks"]',
    '["history", "webhooks"]',
)

# 2. remove currentItems, currentCategoryDraft, currentKeywordDraft
content = re.sub(
    r"\s*const currentItems = ref<ObservabilityCurrentItem\[\]>\(\[\]\);", "", content
)
content = re.sub(r"\s*const currentCategoryDraft = ref\(\"\"\);", "", content)
content = re.sub(r"\s*const currentKeywordDraft = ref\(\"\"\);", "", content)

# 3. remove queryView, queryCategory, queryProductStatus, queryCurrentKeyword
content = re.sub(
    r"\s*const queryView = computed.*?;\n\s*const queryCategory = computed.*?;",
    "",
    content,
    flags=re.DOTALL,
)
content = re.sub(r"\s*const queryProductStatus = computed.*?;", "", content)
content = re.sub(r"\s*const queryCurrentKeyword = computed.*?;", "", content)

# 4. listCount, issueCount, summaryLabel: remove activeTab === 'current'
content = re.sub(
    r"\s*if \(activeTab\.value === \"current\"\)\s*\{\s*return currentItems\.value\.length;\s*\}",
    "",
    content,
)
content = re.sub(
    r"\s*if \(activeTab\.value === \"current\"\)\s*\{\s*return currentItems\.value\.filter\(\(item\) => !item\.isActive\)\.length;\s*\}",
    "",
    content,
)
content = re.sub(
    r"\s*if \(activeTab\.value === \"current\"\)\s*\{\s*return \"当前内容总数\";\s*\}",
    "",
    content,
)

# 5. remove currentRows
content = re.sub(
    r"\s*const currentRows = computed\(\(\) =>[\s\S]*?\}\)\);\n", "", content
)

# 6. remove handleCurrentFilter, handleCurrentReset
content = re.sub(r"\s*function handleCurrentFilter\(\) \{[\s\S]*?\}\n", "", content)
content = re.sub(r"\s*function handleCurrentReset\(\) \{[\s\S]*?\}\n", "", content)

# 7. remove fetchCurrentList
content = re.sub(r"\s*async function fetchCurrentList\(\) \{[\s\S]*?\}\n", "", content)

# 8. remove viewCurrentDetail
content = re.sub(
    r"\s*function viewCurrentDetail\(item: ObservabilityCurrentItem\) \{[\s\S]*?\}\n",
    "",
    content,
)

# 9. fetchCurrentList inside watch -> remove
content = re.sub(
    r"\s*else if \(activeTab\.value === \"current\"\)\s*\{\s*fetchCurrentList\(\);\s*\}",
    "",
    content,
)
content = re.sub(
    r"\s*if \(activeTab\.value === \"current\"\)\s*\{\s*fetchCurrentList\(\);\s*\} else ",
    "",
    content,
)

# 10. export names
content = re.sub(r"\s*currentItems,\n", "\n", content)
content = re.sub(r"\s*currentCategoryDraft,\n", "\n", content)
content = re.sub(r"\s*currentKeywordDraft,\n", "\n", content)
content = re.sub(r"\s*currentRows,\n", "\n", content)
content = re.sub(r"\s*handleCurrentFilter,\n", "\n", content)
content = re.sub(r"\s*handleCurrentReset,\n", "\n", content)
content = re.sub(r"\s*viewCurrentDetail,\n", "\n", content)
content = re.sub(r"\s*queryView,\n", "\n", content)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
