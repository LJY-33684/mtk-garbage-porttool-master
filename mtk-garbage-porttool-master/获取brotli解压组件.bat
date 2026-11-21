@echo off
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%SystemRoot%\System32\chcp.com" 65001 >nul 2>nul
setlocal enabledelayedexpansion
title 获取 brotli 解压组件

set "ROOT=%~dp0"
set "DST=%ROOT%bin\win\x86_64"
set "ZIP=%TEMP%\brotli_porttool.zip"
set "EX=%TEMP%\brotli_porttool_ex"

rem 下载源：GitHub 官方 release 为主，ghproxy 加速镜像兜底（直连失败时自动切换）
set CAND0=https://github.com/google/brotli/releases/download/v1.2.0/brotli-x64-windows-static.zip
set CAND1=https://ghfast.top/https://github.com/google/brotli/releases/download/v1.2.0/brotli-x64-windows-static.zip
set CAND2=https://mirror.ghproxy.com/https://github.com/google/brotli/releases/download/v1.2.0/brotli-x64-windows-static.zip
set SHA256=3208AB82D4F08E062A25660CF38092DB4E8415792AA1E579956D37740F8D8924

if exist "%DST%\brotli.exe" goto installed


:not_installed
echo ===============================================================
echo   brotli 解压组件（可选，推荐安装）
echo ---------------------------------------------------------------
echo   用于在「img 镜像」输出下解压 Android 9+ 固件的 new.dat.br
echo   （OPPO/Realme/OnePlus 固件解密后转换 system/vendor 分区镜像）
echo   未安装时该转换会明确报错并保留 .br 源文件（不静默降级）
echo   zip 卡刷包输出与 Android 8 以下老固件无需此组件
echo   安装后工具自动启用，无需重启
echo ===============================================================
echo.
echo 请选择操作（输入数字后回车）：
echo   0 - 退出
echo   1 - 安装该组件
set /p CHOICE=请选择:
if "%CHOICE%"=="1" goto download
exit /b 0


:download
for %%U in (%CAND0% %CAND1% %CAND2%) do (
  echo [下载] 正在下载官方 brotli 1.2.0（Windows 静态版）...
  echo        来源：%%U
  del /q "%ZIP%" 2>nul
  "%SystemRoot%\System32\curl.exe" -fL --retry 2 --retry-delay 2 --connect-timeout 15 --max-time 300 -o "%ZIP%" "%%U"
  if exist "%ZIP%" (
    set "GOT="
    for /f "skip=1 tokens=*" %%H in ('%SystemRoot%\System32\certutil.exe -hashfile "%ZIP%" SHA256 2^>nul') do if not defined GOT set "GOT=%%H"
    set "GOT=!GOT: =!"
    if /i not "!GOT!"=="%SHA256%" (
      echo [失败] SHA256 校验不匹配，已拒绝解压。
      del /q "%ZIP%" 2>nul
      goto fail
    )
    if exist "%EX%" rmdir /s /q "%EX%"
    echo [解压] 正在解压...
    "%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%EX%' } catch { }" 2>nul
    if exist "%EX%\brotli.exe" goto install
  )
  echo [提示] 该源失败，尝试下一个源...
)

goto fail


:install
if not exist "%DST%" mkdir "%DST%"
set "SRC="
for /r "%EX%" %%F in (brotli.exe) do if not defined SRC set "SRC=%%~dpF"
if not defined SRC goto fail
copy /y "%SRC%brotli.exe" "%DST%\" >nul

echo [验证]
"%DST%\brotli.exe" --version 2>nul
if errorlevel 1 goto fail

echo.
echo [完成] brotli 解压组件已安装到 bin\win\x86_64
echo        此后 OPPO 固件 img 输出将自动使用该组件解压 new.dat.br。
del /q "%ZIP%" 2>nul
rmdir /s /q "%EX%" 2>nul
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 0


:fail
echo.
echo [失败] 下载或解压失败（网络不通或被拦截），可稍后重试本脚本。
echo 未安装时工具会明确报错并保留 .br 源文件，不影响 zip 输出。
del /q "%ZIP%" 2>nul
rmdir /s /q "%EX%" 2>nul
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 1


:installed
echo [已安装] 检测到 brotli，当前版本：
"%DST%\brotli.exe" --version 2>nul
echo.
echo 请选择操作（输入数字后回车）：
echo   0 - 退出
echo   1 - 重新安装该组件
echo   2 - 卸载该组件
set /p CHOICE=请选择:
if "%CHOICE%"=="2" goto uninstall
if "%CHOICE%"=="1" goto reinstall
exit /b 0


:reinstall
echo [安装] 正在删除现有 brotli 并重新下载...
del /q "%DST%\brotli.exe" 2>nul
if exist "%DST%\brotli.exe" (
  echo [失败] 文件被占用无法删除，请关闭占用程序后重试。
  echo.
  echo 按任意键退出本窗口...
  pause >nul
  exit /b 1
)
goto download


:uninstall
echo [卸载] 正在删除 brotli 组件...
del /q "%DST%\brotli.exe" 2>nul
if exist "%DST%\brotli.exe" (
  echo [提示] 文件被占用未删除，请关闭占用程序后再试。
) else (
  echo [完成] brotli 解压组件已卸载。
)
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 0
