"""把出行建议官发布到魔搭（ModelScope）Docker 创空间。

前置条件：
  1. 已完成实名认证并绑定阿里云账号（魔搭 Docker 创空间的要求）；
  2. 已在 https://www.modelscope.cn/studios/create 创建 Docker 创空间；
  3. 已在 https://modelscope.cn/my/myaccesstoken 创建「写」权限令牌。

用法：
    python scripts/deploy_modelscope.py --user 你的魔搭用户名

令牌读取顺序：环境变量 MODELSCOPE_API_TOKEN → 项目根目录 .ms_token 文件。
推送完成后，还需要在创空间「设置 → 环境变量」里添加密钥，并点「上线」。
"""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".ms_token"
WORK = ROOT / "dist-ms"
SOURCE_FILES = ("travel_advisor", "web")
SOURCE_SINGLE = ("requirements.txt",)
DEPLOY_DIR = ROOT / "deploy" / "modelscope"


def _auth_header(token: str) -> str:
    return "http.extraHeader=Authorization: Basic " + base64.b64encode(f"oauth2:{token}".encode()).decode()


def read_token() -> str:
    token = os.getenv("MODELSCOPE_API_TOKEN", "").strip()
    if token:
        return token
    if TOKEN_FILE.is_file():
        return TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
    return ""


def run(args: list[str], cwd: Path) -> None:
    print("$", " ".join(args[:2]), "...")
    subprocess.run(args, cwd=cwd, check=True)


def check_sdk(user: str, space: str) -> None:
    """确认创空间是 Docker 类型，否则 Gradio 环境跑不了 FastAPI。"""
    import httpx

    try:
        response = httpx.get(
            f"https://www.modelscope.cn/api/v1/studio/{user}/{space}",
            headers={"User-Agent": "git/2.44.0.windows.1"},
            timeout=15,
        )
        data = response.json().get("Data") or {}
    except Exception:
        return
    sdk = str(data.get("SdkType") or "").lower()
    if sdk and sdk != "docker":
        print(
            f"当前创空间的 SDK 是 {sdk}，不是 docker。请在创建创空间时选择「Docker / 编程式创空间」，"
            "或删除后重建。",
            file=sys.stderr,
        )
        raise SystemExit(4)


def prepare_clone(user: str, space: str, token: str) -> None:
    url = f"https://www.modelscope.cn/studios/{user}/{space}.git"
    if (WORK / ".git").exists():
        print("复用已有克隆，先同步远端")
        subprocess.run(["git", "-c", _auth_header(token), "fetch", "origin"], cwd=WORK, check=False)
        subprocess.run(["git", "reset", "--hard", "origin/master"], cwd=WORK, check=False)
        return

    if WORK.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(WORK)], check=False)
        if WORK.exists():
            shutil.rmtree(WORK, ignore_errors=True)

    print(f"克隆创空间仓库：{user}/{space}")
    result = subprocess.run(
        ["git", "-c", _auth_header(token), "clone", url, str(WORK)],
        check=False,
    )
    if result.returncode != 0:
        print(
            "克隆失败：请确认创空间已创建（Docker SDK）、用户名/名称正确、令牌是「写」权限。",
            file=sys.stderr,
        )
        raise SystemExit(3)


def copy_project() -> None:
    for name in SOURCE_SINGLE:
        shutil.copy(ROOT / name, WORK / name)
    for name in SOURCE_FILES:
        target = WORK / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            ROOT / name,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copy(DEPLOY_DIR / "Dockerfile", WORK / "Dockerfile")
    shutil.copy(DEPLOY_DIR / "README.md", WORK / "README.md")
    (WORK / ".gitignore").write_text(".env\n__pycache__/\n*.pyc\n", encoding="utf-8")


def commit_and_push(user: str, space: str, token: str) -> None:
    run(["git", "config", "user.name", "travel-advisor"], WORK)
    run(["git", "config", "user.email", "travel-advisor@users.noreply.modelscope.cn"], WORK)
    run(["git", "add", "-A"], WORK)
    # 没有变更时 commit 会失败，这里允许它失败
    subprocess.run(["git", "commit", "-m", "deploy: travel advisor studio"], cwd=WORK)
    run(["git", "-c", _auth_header(token), "push", "origin", "HEAD:master"], WORK)
    run(["git", "remote", "set-url", "origin", f"https://www.modelscope.cn/studios/{user}/{space}.git"], WORK)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="魔搭用户名")
    parser.add_argument("--space", default="travel-advisor", help="创空间名称")
    parser.add_argument("--prepare-only", action="store_true", help="只生成 dist-ms/，不推送")
    args = parser.parse_args()

    if args.prepare_only:
        if WORK.exists():
            shutil.rmtree(WORK)
        WORK.mkdir(parents=True)
        copy_project()
        print(f"已生成 {WORK}，可手动上传到创空间。")
        return 0

    token = read_token()
    if not token:
        print("缺少令牌：设置 MODELSCOPE_API_TOKEN，或写入 .ms_token 文件。", file=sys.stderr)
        return 2

    prepare_clone(args.user, args.space, token)
    copy_project()
    check_sdk(args.user, args.space)
    commit_and_push(args.user, args.space, token)

    url = f"https://www.modelscope.cn/studios/{args.user}/{args.space}"
    print("\n代码已推送。接下来：")
    print(f"1. 打开 {url} → 设置 → 环境变量，添加（运行时）：")
    print("   TRAVEL_ADVISOR_WEATHER_KEY / TRAVEL_ADVISOR_WEATHER_BASE_URL / DEEPSEEK_API_KEY")
    print("2. 同一页面点「上线」，等待构建完成。")
    print(f"3. 访问地址：{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
