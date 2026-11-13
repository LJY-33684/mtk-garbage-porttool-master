@echo off
chcp 65001 >nul
cd /d %~dp0

rem 1) 实际执行一次 --version：可同时识破 PATH 缺失与 WindowsApps 空存根
python --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到可用的 Python 环境。
    echo        请安装 Python 3.10 或更高版本，安装时勾选 "Add python.exe to PATH"。
    echo        若已安装仍报错，请检查 PATH，或改用 py -3 启动。
    pause
    exit /b 1
)

rem 2) 版本门槛：低于 3.10 直接给出可读提示
python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [错误] 当前 Python 版本低于 3.10，本工具需要 Python 3.10+。
    python --version
    pause
    exit /b 1
)

python main.py
if errorlevel 1 pause
