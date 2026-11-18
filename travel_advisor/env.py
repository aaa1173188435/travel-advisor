"""极简 `.env` 加载器。

放在独立模块里，保证无论先导入哪个组件（天气、模型还是应用），
进程启动时都会读取一次项目根目录的 `.env`。
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILES = (
    Path(__file__).resolve().parent.parent / ".env",
    Path.cwd() / ".env",
)

_loaded = False


def load_env_files() -> None:
    """读取 .env；已存在的环境变量优先，不覆盖。"""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in _ENV_FILES:
        try:
            if not path.is_file():
                continue
            for raw in path.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
