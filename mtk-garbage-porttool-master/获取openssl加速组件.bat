@echo off
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%SystemRoot%\System32\chcp.com" 65001 >nul 2>nul
setlocal enabledelayedexpansion
title 获取 OpenSSL 加速组件

set "ROOT=%~dp0"
set "DST=%ROOT%bin\win\x86_64"
set "ZIP=%TEMP%\openssl_porttool.zip"
set "EX=%TEMP%\openssl_porttool_ex"

rem 官方推荐：OpenSSL 3.5 LTS（FireDaemon 预编译 Windows 便携包）
rem 固定单一可信源，禁止第三方代理；下载后必须通过 SHA256 校验
set CAND0=https://download.firedaemon.com/FireDaemon-OpenSSL/openssl-3.5.9.zip
set SHA256=76DA391395BE029B44794857B9FF380255E02A0960A98314CD3F6A6816D82696

if exist "%DST%\openssl.exe" goto installed


:not_installed
echo ===============================================================
echo   OpenSSL 加速组件（可选，推荐安装）
echo ---------------------------------------------------------------
echo   该组件用于加速 OPPO / Realme / OnePlus 固件解密。
echo   未安装时工具使用内置 pyaes 纯 Python 后端，
echo   功能不受影响，仅解密速度稍慢。
echo   安装后会自动启用更快的 OpenSSL 后端，
echo   尤其在 PK 型大固件上提速可达数十倍。
echo ===============================================================
echo.
echo 请选择操作（输入数字后回车）：
echo   0 - 退出
echo   1 - 安装该组件
set /p CHOICE=你的选择：
if "%CHOICE%"=="1" goto download
exit /b 0


:download
if not exist "%SystemRoot%\System32\curl.exe" (
  echo [提示] 未找到 curl.exe（需 Windows 10 1803 及以上系统）。
  echo 不影响使用：工具将使用内置 pyaes 纯 Python 后端，仅解密速度稍慢。
  echo.
  echo 按任意键退出本窗口...
  pause >nul
  exit /b 1
)

for %%U in (%CAND0%) do (
  echo [下载] 正在下载 OpenSSL 3.5.9 LTS（免安装）...
  echo        来源：%%U
  del /q "%ZIP%" 2>nul
  "%SystemRoot%\System32\curl.exe" -fL --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 900 -o "%ZIP%" "%%U"
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
    echo [解压] 正在展开...
    "%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%EX%' } catch { }" 2>nul
    if exist "%EX%\x64\bin\openssl.exe" goto install
    if exist "%EX%\openssl.exe" goto install
    if exist "%EX%\openssl-1.1\x64\bin\openssl.exe" goto install
  )
  echo [重试] 该来源失败，请检查网络后重试。
)

goto fail

:install
if not exist "%DST%" mkdir "%DST%"
set "SRC="
if exist "%EX%\x64\bin\openssl.exe" set "SRC=%EX%\x64\bin\"
if not defined SRC if exist "%EX%\openssl.exe" set "SRC=%EX%\"
if exist "%EX%\openssl-1.1\x64\bin\openssl.exe" set "SRC=%EX%\openssl-1.1\x64\bin\"
if not defined SRC for /r "%EX%" %%F in (openssl.exe) do if not defined SRC set "SRC=%%~dpF"
if not defined SRC goto fail
copy /y "%SRC%openssl.exe" "%DST%\" >nul
for /f "delims=" %%D in ('dir /b /a-d "%SRC%*.dll" 2^>nul') do copy /y "%SRC%%%D" "%DST%\" >nul

echo [验证]
"%DST%\openssl.exe" version 2>nul
if errorlevel 1 goto fail

echo.
echo [完成] OpenSSL 加速组件已安装到 bin\win\x86_64
echo        此后 OPPO 固件解密将自动使用更快的 OpenSSL 后端。
del /q "%ZIP%" 2>nul
rmdir /s /q "%EX%" 2>nul
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 0

:fail
echo.
echo [失败] 下载或解压失败（可能当前网络无法访问分发站点）。
echo 不影响使用：工具将使用内置 pyaes 纯 Python 后端，仅解密速度稍慢。
echo 你也可以稍后网络正常时重新运行本脚本。
del /q "%ZIP%" 2>nul
rmdir /s /q "%EX%" 2>nul
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 1
:installed
echo [已安装] 检测到 OpenSSL，当前版本：
"%DST%\openssl.exe" version 2>nul
echo.
echo 请选择操作（输入数字后回车）：
echo   0 - 退出
echo   1 - 重新安装该组件
echo   2 - 卸载该组件
set /p CHOICE=你的选择：
if "%CHOICE%"=="2" goto uninstall
if "%CHOICE%"=="1" goto reinstall
exit /b 0

:reinstall
echo [重装] 正在删除现有 OpenSSL 组件...
del /q "%DST%\openssl.exe" "%DST%\libeay32.dll" "%DST%\ssleay32.dll" "%DST%\libcrypto-1_1-x64.dll" "%DST%\libssl-1_1-x64.dll" "%DST%\libcrypto-3-x64.dll" "%DST%\libssl-3-x64.dll" 2>nul
if exist "%DST%\openssl.exe" (
  echo [失败] 组件文件被占用无法删除，请关闭占用程序后重试。
  echo.
  echo 按任意键退出本窗口...
  pause >nul
  exit /b 1
)
goto download

:uninstall
echo [卸载] 正在删除 OpenSSL 组件...
del /q "%DST%\openssl.exe" "%DST%\libeay32.dll" "%DST%\ssleay32.dll" "%DST%\libcrypto-1_1-x64.dll" "%DST%\libssl-1_1-x64.dll" "%DST%\libcrypto-3-x64.dll" "%DST%\libssl-3-x64.dll" 2>nul
if exist "%DST%\openssl.exe" (
  echo [提示] 部分文件被占用未能删除，请关闭占用程序后重新运行。
) else (
  echo [完成] OpenSSL 加速组件已卸载。
)
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 0
