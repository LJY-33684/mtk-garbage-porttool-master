@echo off
setlocal enabledelayedexpansion
title 获取 OpenSSL 加速组件

set "ROOT=%~dp0"
set "DST=%ROOT%bin\win\x86_64"
set "ZIP=%TEMP%\openssl_porttool.zip"
set "EX=%TEMP%\openssl_porttool_ex"

rem 下载候选（按顺序尝试，fulgan 为 OpenSSL 官方 wiki 收录的免安装构建）
rem 备选源：FireDaemon 便携版（fulgan 源被 Cloudflare 拦截时自动切换）
set CAND0=https://indy.fulgan.com/SSL/openssl-1.0.2u-x64_86-win64.zip
set CAND1=https://download.firedaemon.com/FireDaemon-OpenSSL/openssl-1.1.1w.zip

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
where curl.exe >nul 2>nul
if errorlevel 1 (
  echo [提示] 未找到 curl.exe（需 Windows 10 1803 及以上系统）。
  echo 不影响使用：工具将使用内置 pyaes 纯 Python 后端，仅解密速度稍慢。
  echo.
  echo 按任意键退出本窗口...
  pause >nul
  exit /b 1
)

for %%U in (%CAND0% %CAND1%) do (
  echo [下载] 正在下载 OpenSSL 1.0.2u（免安装）...
  echo        来源：%%U
  del /q "%ZIP%" 2>nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $ProgressPreference='SilentlyContinue'; try { $src='%%U'; $dst='%ZIP%'; $req=[System.Net.HttpWebRequest]::Create($src); $req.Timeout=180000; $resp=$req.GetResponse(); $total=[long]$resp.ContentLength; $fs=[IO.File]::Create($dst); $buf=New-Object byte[] 65536; $stream=$resp.GetResponseStream(); $got=[long]0; $last=-1; while(($n=$stream.Read($buf,0,$buf.Length)) -gt 0){ $fs.Write($buf,0,$n); $got+=$n; if($total -gt 0){ $pct=[int](100*$got/$total); if($pct -ne $last){ $last=$pct; $full=[int]($pct/5); $bar=('█'*$full)+('-'*(20-$full)); Write-Host -NoNewline ([string][char]13 + '[' + $bar + '] ' + $pct + '%  ') } } }; $fs.Close(); $stream.Close(); $resp.Close(); Write-Host '' } catch { Write-Host '下载失败' } }" 2>nul
  if exist "%ZIP%" (
    if exist "%EX%" rmdir /s /q "%EX%"
    echo [解压] 正在展开...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%EX%' } catch { }" 2>nul
    if exist "%EX%\openssl.exe" goto install
    if exist "%EX%\openssl-1.1\x64\bin\openssl.exe" goto install
  )
  echo %%U | findstr /i "fulgan" >nul
  if errorlevel 1 (
    echo [重试] 该来源失败，尝试下一候选...
  ) else (
    echo [提示] fulgan 源被 Cloudflare 拦截(403)，需代理才能访问
    echo        不用担心，正在自动切换国内可直连的备用源...
  )
)

goto fail

:install
if not exist "%DST%" mkdir "%DST%"
set "SRC="
if exist "%EX%\openssl.exe" set "SRC=%EX%\"
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
del /q "%DST%\openssl.exe" "%DST%\libeay32.dll" "%DST%\ssleay32.dll" "%DST%\libcrypto-1_1-x64.dll" "%DST%\libssl-1_1-x64.dll" 2>nul
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
del /q "%DST%\openssl.exe" "%DST%\libeay32.dll" "%DST%\ssleay32.dll" "%DST%\libcrypto-1_1-x64.dll" "%DST%\libssl-1_1-x64.dll" 2>nul
if exist "%DST%\openssl.exe" (
  echo [提示] 部分文件被占用未能删除，请关闭占用程序后重新运行。
) else (
  echo [完成] OpenSSL 加速组件已卸载。
)
echo.
echo 按任意键退出本窗口...
pause >nul
exit /b 0