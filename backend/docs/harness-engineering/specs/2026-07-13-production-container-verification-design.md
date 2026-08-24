# 生产容器真实验证设计

## 目标

在不替换当前 systemd 服务、不挂载生产数据库的前提下，完成精确 HEAD 镜像的真实 build、镜像元数据、非 root/单 worker、health/ready/version、数据隔离和漏洞扫描验证。

## 隔离运行方式

- 镜像使用 `yunxibakebot:<version>-<short-sha>` 精确标签。
- smoke 容器只绑定 `127.0.0.1:17001`，不占用生产 `7001`。
- `/app/data` 使用 UID/GID 10001 的 tmpfs，不挂载 `/opt/yunxibakebot/data`。
- 容器继承生产配置用于启动必需布尔门禁，但不执行 callback、模型调用或外部业务请求。
- smoke 预置合成空 SQLite schema和位于`/app/data/embeddings.npy/.json`的合法空向量索引，验证容器打包与运行合同，而不是复制生产数据。
- 容器使用 memory、swap、CPU 和 pids上限，结束后按明确名称删除单个容器。

## 构建边界

- Python base image固定 digest。
- PyTorch从官方CPU wheel索引获取，保留真实SentenceTransformer能力但不携带CUDA运行库。
- builder通过BuildKit cache mount保留pip HTTP缓存，慢链路中断后可复用已完成下载；缓存不复制到runtime镜像。
- runtime阶段只从wheelhouse离线安装锁定生产依赖。
- runtime安装完成后移除pip、setuptools、wheel和jaraco.context等构建/安装工具，避免未使用的vendor代码进入生产层。
- `.dockerignore` 排除 `.env`、数据库、密钥、reports和前端node_modules；已编译 `web/admin/dist` 必须进入镜像，满足readiness。
- `DB_PATH`固定为`/app/data/bot.db`，`EMBEDDING_INDEX_DIR`固定为`/app/data/embeddings`；索引基名必须位于持久化数据目录内。
- 记录镜像ID、实际大小和最大层；真实构建不得再次把根盘推到不可运行状态。

## 漏洞门禁

使用真实scanner检查最终镜像OS和Python依赖。报告只保留按严重级别计数、scanner版本、镜像ID和阻断结论；不保存生产环境变量。CRITICAL/HIGH结果必须区分有修复和无修复项，存在可修复CRITICAL时阻断完成。

## 清理约束

不运行 `docker system prune`、`docker builder prune` 或批量删除。只允许删除本轮明确命名的单个smoke容器、单个scanner容器和明确标签镜像；构建缓存保留并在证据中记录。
