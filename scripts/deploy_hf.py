"""把出行建议官发布到 Hugging Face Spaces（免费 Docker Space）。

用法：
    1. 在 https://huggingface.co/settings/tokens 创建一个 Write 权限的 token
    2. 把 token 写进本目录的 .hf_token 文件（一行，不要提交）
    3. python scripts/deploy_hf.py

可选参数：
    --name my-space        指定 Space 名称，默认 travel-advisor
    --prepare-only         只生成 dist-hf/ 目录，不创建仓库、不推送
    --private              创建私有 Space（默认公开）
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist-hf"
TOKEN_FILE = ROOT / ".hf_token"

SPACE_README = """---
title: 出行建议官
emoji: 🧳
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8010
pinned: false
license: mit
short_description: 输入日期、城市与出行模式，返回可执行的出行建议
---

# 出行建议官 · Travel Advisor

输入 **日期 + 城市 + 出行模式**，返回一份可解释、能直接照做的出行建议。

- 规则引擎负责事实：气候、法定节假日与调休、节气、通勤高峰、旅游人流
- 可选接入和风天气预报与 DeepSeek 润色，未配置时自动使用纯规则
- 代码与完整说明见：https://github.com/aaa1173188435/travel-advisor

## 这个 Space 的密钥

在 **Settings → Variables and secrets** 里添加（不要写进代码）：

| 名称 | 说明 |
| --- | --- |
| `TRAVEL_ADVISOR_WEATHER_KEY` | 和风天气 Key |
| `TRAVEL_ADVISOR_WEATHER_BASE_URL` | 和风 API Host |
| `DEEPSEEK_API_KEY` | DeepSeek Key（可选） |
"""


def read_token() -> str:
    token = os.getenv("HF_TOKEN", "").strip()
    if token:
        return token
    if TOKEN_FILE.is_file():
        return TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
    return ""


def whoami(token: str) -> str:
    response = httpx.get(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["name"]


def create_space(token: str, name: str, private: bool) -> None:
    response = httpx.post(
        "https://huggingface.co/api/repos/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "space", "name": name, "private": private, "sdk": "docker"},
        timeout=30,
    )
    if response.status_code == 409:
        print(f"Space 已存在，直接更新代码：{name}")
        return
    response.raise_for_status()
    print(f"已创建 Space：{name}")


def prepare() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copy(ROOT / "Dockerfile", DIST / "Dockerfile")
    shutil.copy(ROOT / "requirements.txt", DIST / "requirements.txt")
    shutil.copytree(
        ROOT / "travel_advisor",
        DIST / "travel_advisor",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT / "web", DIST / "web")
    (DIST / "README.md").write_text(SPACE_README, encoding="utf-8")
    (DIST / ".gitignore").write_text(".env\n__pycache__/\n*.pyc\n", encoding="utf-8")
    print(f"已生成 {DIST}")


def push(token: str, user: str, name: str) -> str:
    remote = f"https://{user}:{token}@huggingface.co/spaces/{user}/{name}"
    clean_remote = f"https://huggingface.co/spaces/{user}/{name}"
    repo = DIST / "spaces"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(DIST, repo, ignore=shutil.ignore_patterns("spaces"))

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, check=True)

    run("git", "init", "-b", "main")
    run("git", "config", "user.name", "travel-advisor")
    run("git", "config", "user.email", "travel-advisor@users.noreply.huggingface.co")
    run("git", "add", "-A")
    run("git", "commit", "-m", "deploy: travel advisor space")
    run("git", "remote", "add", "origin", remote)
    run("git", "push", "-f", "origin", "main")
    run("git", "remote", "set-url", "origin", clean_remote)
    return f"https://{user}-{name}.hf.space"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="travel-advisor")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    prepare()
    if args.prepare_only:
        print("仅生成目录，未创建/推送 Space。")
        return 0

    token = read_token()
    if not token:
        print("缺少 token：请设置 HF_TOKEN 环境变量，或写入 .hf_token 文件。", file=sys.stderr)
        return 2

    user = whoami(token)
    print(f"已登录 Hugging Face：{user}")
    create_space(token, args.name, args.private)
    url = push(token, user, args.name)
    print("\n部署完成，Space 正在构建（首次约 3—5 分钟）。")
    print(f"地址：{url}")
    print("\n下一步：打开 Space → Settings → Variables and secrets，添加：")
    print("  TRAVEL_ADVISOR_WEATHER_KEY")
    print("  TRAVEL_ADVISOR_WEATHER_BASE_URL")
    print("  DEEPSEEK_API_KEY（可选）")
    print("添加后 Space 会自动重启，即可使用真实天气与润色。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
