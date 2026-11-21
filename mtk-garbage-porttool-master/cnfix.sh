#!/system/bin/sh
# MTK 移植工具注入：国内网络连通性检测 + NTP 时间服务器（独立模板，可自定义）
# 开机由 init 的 cnfix 服务自动执行（root 权限，无需 ADB/手动操作）；脚本保留不删除，恢复出厂后自动重写，持续生效
# 幂等：逐个键检测，已设置的键跳过（恢复出厂/清空 settings 表后自动补齐）
# 等待系统完全启动、settings 服务可用（最多 120s，init 触发时通常已就绪，双保险）
i=0
while [ "$(getprop sys.boot_completed)" != "1" ] && [ $i -lt 60 ]; do
  sleep 2; i=$((i+1))
done
if [ "$(settings get global captive_portal_http_url 2>/dev/null)" != "http://connect.rom.miui.com/generate_204" ]; then
  settings put global captive_portal_http_url http://connect.rom.miui.com/generate_204
  settings put global captive_portal_https_url https://connect.rom.miui.com/generate_204
  settings put global captive_portal_use_https 0
fi
if [ "$(settings get global ntp_server 2>/dev/null)" != "ntp.aliyun.com" ]; then
  settings put global ntp_server ntp.aliyun.com
fi

# ============================================================
# 自定义开机指令区（可自行编辑本文件，插入你自己的命令）
# 以下命令会在系统完全启动后以 root 执行；每条一行，例如：
#   setprop persist.sys.usb.config mtp,adb
#   settings put global wifi_scan_always_enabled 1
# 不需要自定义时，保留下方为空即可；修改后重新运行工具移植即生效
# ============================================================
