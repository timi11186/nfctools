#!/usr/bin/env python3
"""
NFC 烧录工具打包脚本（跨平台）

用法：
    python build_client.py            # 用 config.json 现有的 host 打包
    python build_client.py --host=https://nurafamily.com  # 指定 host

产物：
    macOS:   dist/NFC烧录系统.app
    Windows: dist/NFC烧录系统/NFC烧录系统.exe
    Linux:   dist/NFC烧录系统/NFC烧录系统
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "NFC烧录系统"
ENTRY = "run.py"

DEFAULT_HOST = "https://nurafamily.com"
DEFAULT_API_PREFIX = "/factory/legacy"


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("→ 安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])


def write_config(host: str):
    """写入 config.json（这个文件会被打包到 app 内部，但运行时也可被外部 config.json 覆盖）"""
    config_path = ROOT / "config.json"
    cfg = {
        "host": host.rstrip("/"),
        "api_prefix": DEFAULT_API_PREFIX,
    }
    config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"→ 写入 config.json: {cfg}")


def clean_build_artifacts():
    """清理旧产物"""
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            print(f"→ 清理 {p}")
            shutil.rmtree(p)
    for f in ROOT.glob("*.spec"):
        print(f"→ 删除 {f}")
        f.unlink()


def build_executable():
    system = platform.system()
    print(f"→ 当前平台: {system}")

    # PyInstaller 跨平台打包参数
    sep = ";" if system == "Windows" else ":"

    args = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--name", APP_NAME,
        "--windowed",                     # 不显示控制台窗口（GUI 应用）
        "--add-data", f"assets{sep}assets",
        "--add-data", f"config.json{sep}.",
        # 隐式依赖（PyInstaller 探测不到的）
        "--hidden-import", "smartcard.scard",
        "--hidden-import", "PyQt6.QtMultimedia",
        # 排除不必要的大体积依赖
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
    ]

    # macOS 需要 .icns；Windows/Linux 可用 .ico
    if system == "Darwin":
        icns = ROOT / "assets" / "icon.icns"
        if icns.exists():
            args += ["--icon", str(icns)]
        else:
            print("→ macOS 平台无 icon.icns，跳过自定义图标（使用默认）")
    else:
        ico = ROOT / "assets" / "icon.ico"
        if ico.exists():
            args += ["--icon", str(ico)]

    args.append(str(ROOT / ENTRY))

    print(f"→ 运行 PyInstaller...")
    print("  " + " ".join(args))
    subprocess.check_call(args, cwd=str(ROOT))


def make_release_package():
    """额外打包一个分发用的目录，方便分发"""
    dist = ROOT / "dist"
    if not dist.exists():
        return

    # 复制 README + 新的 config.json 模板
    readme_path = dist / "README.txt"
    readme_path.write_text(
        f"""# NFC 烧录系统使用说明

## 服务器地址配置

如果服务器地址变更，无需重新打包。
编辑同目录的 config.json，修改 host 字段后重启程序即可：

{{
    "host": "https://nurafamily.com",
    "api_prefix": "/factory/legacy"
}}

## 运行

- macOS: 双击 {APP_NAME}.app
- Windows: 进入 {APP_NAME} 文件夹，双击 {APP_NAME}.exe

## 登录账号

请联系 Nurplay 管理员获取工厂账号。

## 卡片管理

主窗口的「卡片管理」按钮可以查询/取消已烧录的卡片，
用于烧错卡后重烧的场景。

## 数据目录

程序运行时会在同目录下生成：
- data/        — 离线记录、缓存
- config/      — 登录信息

请勿删除这些目录。
""",
        encoding="utf-8"
    )

    # 把外部版本的 config.json 也放一份（方便修改）
    external_cfg = dist / "config.json"
    shutil.copy(ROOT / "config.json", external_cfg)

    print(f"→ 已生成发布包，位于: {dist}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"后端服务器地址，默认 {DEFAULT_HOST}")
    parser.add_argument("--keep-config", action="store_true",
                        help="保留现有 config.json 不覆盖")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  打包 {APP_NAME}")
    print("=" * 60)

    if not args.keep_config:
        write_config(args.host)

    ensure_pyinstaller()
    clean_build_artifacts()
    build_executable()
    make_release_package()

    print()
    print("=" * 60)
    print("  ✓ 打包完成")
    print("=" * 60)
    print(f"  产物目录: {ROOT / 'dist'}")
    if platform.system() == "Darwin":
        print(f"  macOS 应用: {ROOT / 'dist' / f'{APP_NAME}.app'}")
        print(f"  双击运行 或 cd dist && open '{APP_NAME}.app'")
    elif platform.system() == "Windows":
        print(f"  Windows 可执行: {ROOT / 'dist' / APP_NAME / f'{APP_NAME}.exe'}")
    print()


if __name__ == "__main__":
    main()
