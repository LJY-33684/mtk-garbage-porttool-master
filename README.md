# MTK低端机ROM移植工具 / MTK Low-End Device ROM Porting Tool

> 当前版本 / Current version：**1.2-beta5**

## 项目介绍 / Project Introduction

这是一个针对 **MTK低端芯片系列（如MT65xx、MT67xx入门款）** 的ROM移植辅助工具，旨在简化“底包（当前设备官方ROM）”与“移植源（目标ROM）”之间的boot/system镜像适配流程，自动完成文件替换、配置同步、镜像打包等繁琐步骤，降低低端机ROM移植的技术门槛。

This is a ROM porting assistance tool specifically designed for MTK low-end chip series (such as MT65xx, MT67xx entry-level models). It aims to simplify the adaptation process of boot/system images between the "base package (official ROM of the current device)" and the "donor source (target ROM)". It automates tedious steps such as file replacement, configuration synchronization, and image repacking, lowering the technical barrier for ROM porting on low-end devices.

## 功能特点 / Features

**1. 多源支持 / Multi-Source Support：**
- 移植源可选： ZIP卡刷包 / 单独boot.img+system.img
- Donor source options: ZIP flashable package / Separate boot.img+system.img
- 输出类型可选： ZIP卡刷包（仅支持ZIP源） / boot.img+system.img（支持所有源）
- Output type options: ZIP flashable package (only for ZIP donor source) / boot.img+system.img (for all donor sources)

**2. 自动化移植 / Automated Porting：**
- 自动处理boot镜像：内核替换、fstab分区表适配、SELinux宽容模式开启、ADB调试开启
- Automatic boot image processing: kernel replacement, fstab partition table adaptation, SELinux permissive mode enabling, ADB debugging enabling.
- 自动处理system镜像：驱动文件替换、屏幕DPI同步、设备型号/时区/语言同步
- Automatic system image processing: driver file replacement, screen DPI synchronization, device model/timezone/language synchronization.
- 支持Magisk boot.img修补（可选）
- Supports Magisk boot.img patching (optional).
- 移植时自动读取并打印底包/移植源信息（内核版本、Android版本、芯片平台、系统架构等）
- Automatically reads and prints base/donor info (kernel version, Android version, chip platform, architecture, etc.) during porting.

**3. 体验优化 / Experience Optimization：**
- 防止重复点击：“一键移植”按钮执行中自动禁用，避免多进程/多窗口冲突
- Prevents repeated clicks: The "One-Click Porting" button is automatically disabled during execution to avoid multi-process/window conflicts.
- 移植条目支持全选/三态全选（部分选中显示“-”），滚轮流畅滚动
- Porting items support select-all / tri-state select-all (partial selection shows "-"), with smooth wheel scrolling.
- 结构化日志：清晰显示每一步操作（如“解包boot.img”“替换内核文件”），便于排查问题
- Structured logging: Clearly displays each operation step (e.g., "Unpacking boot.img", "Replacing kernel files") for easier troubleshooting.
- 左下角版本号右侧新增 GitHub / Gitee 仓库图标，点击直接跳转对应仓库
- GitHub / Gitee repo icons added to the right of the version label (bottom-left); click to open the corresponding repository.

**4. 多方案与自动识别 / Presets & Auto Mode：**
- 内置7套预设方案：mt6572/mt6582/mt6592、G79(mt6735/mt6737)、mt6580/mt8321、mt8163平板、**mt6797(Helio X20/X25)** 等
- 7 built-in presets: mt6572/mt6582/mt6592, G79(mt6735/mt6737), mt6580/mt8321, mt8163 tablet, **mt6797 (Helio X20/X25)**, etc.
- **未列芯片（同平台自动识别）**：自动扫描底包并识别替换硬件文件（firmware/HAL/GPU/音频/WiFi/RIL等），不触碰系统框架库
- **Unknown chip (auto mode)**: automatically scans and replaces hardware files (firmware/HAL/GPU/audio/WiFi/RIL, etc.) without touching system framework libraries.
- **仅移植内核（只输出boot）**：跳过system处理，只输出boot.img
- **Kernel-only mode**: skips system processing and outputs only boot.img.

**5. 文件系统修复与自查 / FS Fix & Verification：**
- 符号链接修复（Windows解包丢失的 !<symlink> 标记转回真符号链接，支持raw/sparse）
- Symlink fix (converts !<symlink> markers lost during Windows unpacking back to real symlinks, raw/sparse supported).
- GDT_CSUM校验和重算（修复TWRP刷入报“Structure needs cleaning”）
- GDT_CSUM recalculation (fixes "Structure needs cleaning" when flashing with TWRP).
- inode bitmap修复 + 打包后自动5项文件系统一致性自查
- inode bitmap fix + automatic 5-item filesystem integrity check after packaging.

**6. 缓存优化 / Cache Optimization：**
- base缓存：底包system解包结果按MD5缓存（分块计算），MD5一致且目录存在时跳过重复解包；可勾选“完成后清除base目录”
- Base cache: base system unpack results are cached by MD5 (chunked calculation); unpack is skipped when MD5 matches and the directory exists; optional "clear base directory after completion" checkbox.

**7. 更新检查 / Update Check：**
- 标题栏“检查更新”按钮（30秒超时提示失败），更新源支持 GitHub / Gitee 切换
- "Check Update" button in the title bar (30s timeout shows failure), switchable between GitHub / Gitee sources.
- 启动时静默检查更新，发现新版本自动弹出更新窗口
- Silent update check on startup; pops up the update window automatically when a new version is found.

**8. 版本检测与警告 / Version Detection：**
- 自动检测底包/移植源Android版本（API），Android 8.0+（可能启用Treble/VNDK）与跨大版本移植给出警告
- Auto-detects base/donor Android version (API); warns on Android 8.0+ (possible Treble/VNDK) and cross-major-version porting.

## 环境要求 / Environment Requirements

**运行环境 / Runtime Environment：**
- Python 3.10 及以上版本（需自带 tkinter 库，Windows 通常默认安装）
- Python 3.10 or higher (requires the built-in tkinter library, usually pre-installed on Windows).

## 使用步骤 / Usage Steps

**1. 准备文件 / Prepare Files：**
- 底包：当前设备的 boot.img + system.img（从官方ROM中提取）
- Base package: The current device's boot.img + system.img (extracted from the official ROM).
- 移植源：目标ROM的 ZIP卡刷包 或 boot.img+system.img
- Donor source: The target ROM's ZIP flashable package OR boot.img+system.img.

**2. 启动工具 / Start the Tool：**
- 下载/克隆项目到本地
- Download/clone the project locally.
- 打开终端，进入项目目录，执行命令启动 / Open a terminal, navigate to the project directory, and run:
  ```bash
  python main.py
  ```
  或直接双击 `run.bat` / Or double-click `run.bat`.

**3. 配置移植 / Configure Porting：**
- 选择芯片类型（需与底包芯片匹配）
- Select the chip type (must match the base package chip).
- 勾选需要的移植条目（工具会自动加载对应芯片的默认条目，支持全选）
- Check the required porting items (the tool will auto-load default items for the selected chip; select-all supported).
- 选择输出类型： ZIP卡刷包 / img镜像
- Select the output type: ZIP flashable package / img images.
- （可选）勾选“修补Magisk”，选择Magisk APK并指定架构（如 arm64）
- (Optional) Check "Patch Magisk", select the Magisk APK, and specify the architecture (e.g., arm64).

**4. 执行移植 / Execute Porting：**
- 点击“一键移植”，在弹窗中选择：
- Click "One-Click Porting". In the pop-up window, select:
- 底包的 boot.img 和 system.img
- The base package's boot.img and system.img.
- 移植源的 ZIP卡刷包 或 boot.img+system.img
- The donor source's ZIP flashable package OR boot.img+system.img.
- 等待流程完成，输出文件会保存在 out 目录下
- Wait for the process to complete. Output files will be saved in the out directory.

## 移植核心流程 / Core Porting Process

工具自动执行以下步骤：
The tool automatically executes the following steps:

1. 解压/复制移植源文件到临时目录
  Extract/Copy donor source files to a temporary directory.

2. 解包底包&移植源的boot.img，打印双端内核信息，自动替换内核/分区表，配置SELinux/ADB
  Unpack the base package & donor source's boot.img, print kernel info of both sides, automatically replace the kernel/partition table, and configure SELinux/ADB.

3. 重新打包boot.img
  Repack the boot.img.

4. 解包底包&移植源的system.img，打印双端系统信息，自动替换驱动、同步设备配置
  Unpack the base package & donor source's system.img, print system info of both sides, automatically replace drivers and synchronize device configurations.

5. 打包输出（ZIP卡刷包或img镜像）
  Package the output (ZIP flashable package or img images).

6. 清理临时文件（base缓存默认保留，可勾选完成后清除）
  Clean up temporary files (base cache kept by default; optional cleanup after completion).

> 仅移植内核（kernel-only）模式：只执行第1~3步并输出 boot.img，跳过 system 处理。
> Kernel-only mode: only executes steps 1-3 and outputs boot.img, skipping system processing.

## 注意事项 / Notes

**1. 兼容性前提 / Compatibility Prerequisites：**
- 底包与移植源的芯片架构必须一致，且建议为同平台/同芯片系列（如均为MT6739、MT6737），驱动才兼容
- The chip architecture of the base package and donor source must match, and they should ideally be the same platform/chip series (e.g., both MT6739/MT6737) for driver compatibility.
- 底包与移植源的system分区大小建议接近，避免镜像生成失败
- The system partition sizes of the base package and donor source should be similar to avoid image generation failures.

**2. 版本限制 / Version Limits：**
- 本工具面向 Android 7.1.2 及更低版本（无VNDK）的老设备；Android 8.0+（有VNDK/Treble）建议直接刷GSI
- This tool targets legacy devices on Android 7.1.2 and below (no VNDK); for Android 8.0+ (with VNDK/Treble), flashing GSI is recommended.
- 底包与移植源Android大版本差≥3时工具会警告，HAL接口可能不兼容
- The tool warns when base/donor Android major versions differ by ≥3; HAL interfaces may be incompatible.

**3. 风险提示 / Risk Warning：**
- 刷机有风险，请提前备份设备数据
- Flashing carries risks; please back up your device data in advance.
- 仅在测试设备上使用，请勿用于商用或非法用途
- Use only on test devices. Do not use for commercial or illegal purposes.

**4. 其他说明 / Other Notes：**
- 输出ZIP卡刷包时，仅支持以ZIP卡刷包作为移植源
- When outputting a ZIP flashable package, only a ZIP flashable package is supported as the donor source.
- 请确保底包boot已去除加密/签名校验，本工具不负责去除校验
- Make sure the base boot has encryption/signature verification removed; this tool does not handle that.

## 常见问题 / FAQ

Q：点击“一键移植”后按钮变灰，无其他反应？

A：这是防止重复执行的机制，工具正在后台处理流程，可通过“日志输出”查看进度。

Q：ADB调试未生效？

A：工具会优先修改 system/build.prop 中的 ro.debuggable 等配置，若未生效可手动检查该文件。

Q：镜像生成失败？

A：检查 bin 目录下的工具是否与当前系统平台匹配（如Windows对应 win/x86_64 目录）。

Q：移植后卡第一屏或外放无声？

A：多为底包与移植源非同平台导致驱动不兼容。请确认两者为同芯片系列，并优先使用auto模式或匹配方案；音频异常可检查音频驱动/参数是否随底包替换。

Q: After clicking "One-Click Porting", the button turns gray and there's no other response?

A: This is a mechanism to prevent repeated execution. The tool is processing in the background. Check the progress via the "Log Output".

Q: ADB debugging doesn't take effect?

A: The tool prioritizes modifying configurations like ro.debuggable in system/build.prop. If it doesn't work, manually check that file.

Q: Image generation failed?

A: Check if the tools in the bin directory match your system platform (e.g., Windows corresponds to the win/x86_64 directory).

Q: Stuck at first screen or no external speaker sound after porting?

A: Usually caused by driver incompatibility when base/donor are not from the same platform. Make sure they are the same chip series, prefer the auto mode or a matching preset; for audio issues, check whether audio drivers/params were replaced from the base package.

## 免责声明 / Disclaimer

本工具仅用于ROM移植技术学习与交流，请勿用于侵犯他人知识产权、违反设备厂商协议的行为。因使用本工具导致的设备损坏、数据丢失等问题，开发者不承担任何责任。

This tool is intended only for technical learning and exchange regarding ROM porting. Do not use it for infringing on others' intellectual property rights or violating device manufacturer agreements. The developer bears no responsibility for device damage, data loss, or other issues arising from the use of this tool.

## 软件截图 / Software Screenshots

<img width="678" height="316" alt="image" src="https://github.com/user-attachments/assets/4e5d2075-0369-40a0-b7ee-f8eec5314379" />

<img width="677" height="318" alt="image" src="https://github.com/user-attachments/assets/0f298a4a-4b6a-43b8-b6c0-e0d7ca4552a6" />





## 感谢[@affggh](https://github.com/affggh)分享的原文件，此移植工具基于原工具进行的改进 / Thanks to [@affggh](https://github.com/affggh) for sharing the original files. This porting tool is an improvement based on the original tool.

原作者/Original Author [@affggh](https://github.com/affggh)

## 基于原文件的主要改动 / Major Changes Based on the Original Files

1.修复了处理build.prop文件时遇到非utf-8字符导致报错

1.Fixed errors caused by non-UTF-8 characters when processing the build.prop file.

2.新增了单独system和boot镜像移植为img镜像的功能

2.Added the function to port separate system and boot images into img images.

3.优化了输出日志的描述

3.Optimized the description of the output logs.

4.解决了工具在报错时无法自动删除临时文件以及漏删base文件夹

4.Fixed the issue where the tool failed to automatically delete temporary files and leaked the base folder upon error.

5.解决了重复点击“一键移植”按钮会弹出多个窗口的问题

5.Fixed the issue where repeated clicks on the "One-Click Porting" button would open multiple windows.

**近期更新 / Recent Updates：**
- 1.2-beta5（自 beta4 之后的所有改动 / all changes after beta4）：新增mt6797(Helio X20/X25)方案与双架构驱动补齐；G79外放无声根治（音频/TFA功放驱动）；auto模式增强（lib64/egl/TFA）；移植信息自动读取与日志优化；方案改名与排序；UI交互优化（移植条目滚轮修复与滚动速度优化、三态全选，部分选中显示“-”、左下角仓库图标快捷入口）；版本号更新
  - 1.2-beta5: Added mt6797 (Helio X20/X25) preset with dual-arch drivers; fixed G79 no-sound issue (audio/TFA amp drivers); enhanced auto mode (lib64/egl/TFA); auto info reading & log optimization; preset renaming & ordering; UI improvements (wheel scrolling fix & speed, tri-state select-all showing "-" for partial, repo icons quick entry at bottom-left); version bump.
- 1.2-beta4：更新检查（GitHub/Gitee双源、静默启动检查、30s超时）；base缓存与“完成后清除base目录”选项；API版本检测与跨大版本/VNDK警告；sparse镜像支持；仅移植内核只输出boot；左下角版本号显示、Magisk选择按钮
  - 1.2-beta4: Update check (GitHub/Gitee sources, silent startup check, 30s timeout); base cache & "clear base after completion" option; API version detection with cross-version/VNDK warnings; sparse image support; kernel-only outputs boot only; version label at bottom-left, Magisk picker button.
- 早期修复：符号链接丢失/GDT_CSUM校验和/inode bitmap/bootimg全局变量不重置（卡开机根因）等致命bug修复，硬件驱动配置全面适配现代MTK设备（vendor分区）
  - Earlier fixes: fatal bugs including lost symlinks / GDT_CSUM checksum / inode bitmap / bootimg module globals not reset (boot-loop root cause); hardware driver configs fully adapted to modern MTK devices (vendor partition).

## 改进者QQ/邮箱 / Improver's QQ/Email

3368436451@qq.com

## 相关群聊 / Related Chat Group

![qrcode_1770570404334](https://github.com/user-attachments/assets/3dbaaedb-818e-4b15-8df8-b423a63edd0e)
