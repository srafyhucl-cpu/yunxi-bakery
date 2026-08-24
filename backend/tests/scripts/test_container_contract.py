"""容器运行时边界合同测试。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_runtime_is_non_root_and_single_worker() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    digest = "sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff"
    assert f"FROM python:3.11-slim-trixie@{digest} AS builder" in dockerfile
    assert f"FROM python:3.11-slim-trixie@{digest} AS runtime" in dockerfile
    assert "pip install --no-cache-dir -r requirements-dev.txt" not in dockerfile
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert "torch==2.12.0+cpu" in dockerfile
    assert "build-essential" not in dockerfile
    assert "apt-get" not in dockerfile
    assert dockerfile.count("--only-binary=:all:") == 2
    assert "--mount=type=cache,target=/root/.cache/pip,sharing=locked" in dockerfile
    assert "pip wheel --no-cache-dir" not in dockerfile
    assert "--no-index --find-links /wheels" in dockerfile
    assert "pip uninstall --yes pip setuptools wheel jaraco.context" in dockerfile
    assert "EMBEDDING_INDEX_DIR=/app/data/embeddings" in dockerfile
    assert "USER yunxi" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "SentenceTransformer" not in dockerfile
    assert "DB_PATH=/app/data/bot.db" in compose
    assert "EMBEDDING_INDEX_DIR=/app/data/embeddings" in compose
    assert "/ready" in dockerfile
    assert "/ready" in compose
    assert "reports/" in dockerignore
    assert "web/admin/node_modules/" in dockerignore
    assert "web/admin/dist/" not in dockerignore
