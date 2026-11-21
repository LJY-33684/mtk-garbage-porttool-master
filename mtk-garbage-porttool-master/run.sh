#!/bin/sh
set -eu

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未检测到 python3。" >&2
    echo "        请安装 Python 3.10 或更高版本，并确保 python3 在 PATH 中。" >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "[错误] 当前 Python 版本低于 3.10，本工具需要 Python 3.10+。" >&2
    python3 --version >&2 || true
    exit 1
fi

exec python3 main.py
