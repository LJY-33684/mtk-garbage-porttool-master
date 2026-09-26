# MTK低端机ROM移植工具 / MTK Low-End Device ROM Porting Tool

> 当前版本 / Current version：**1.3-beta2p2**

## 项目介绍 / Project Introduction

这是一个针对 **MTK低端芯片系列（如MT65xx、MT67xx入门款）** 的ROM移植辅助工具，旨在简化“底包（当前设备官方ROM）”与“移植源（目标ROM）”之间的boot/system镜像适配流程，自动完成文件替换、配置同步、镜像打包等繁琐步骤，降低低端机ROM移植的技术门槛。

This is a ROM porting assistance tool specifically designed for MTK low-end chip series (such as MT65xx, MT67xx entry-level models). It aims to simplify the adaptation process of boot/system images between the "base package (official ROM of the current device)" and the "donor source (target ROM)". It automates tedious steps such as file replacement, configuration synchronization, and image repacking, lowering the technical barrier for ROM porting on low-end devices.

## 功能特点 / Features

- **1. 多源支持 / Multi-Source Support：**
- 移植源可选： ZIP卡刷包 / 单独boot.img+system.img
- Donor source options: ZIP flashable package / Separate boot.img+system.img
- 输出类型可选： ZIP卡刷包（仅支持ZIP源） / boot.img+system.img（支持所有源）
- Output type options: ZIP flashable package (only for ZIP donor source) / boot.img+system.img (for all donor sources)

- **2. 自动化移植 / Automated Porting：**
- 自动处理boot镜像：内核替换、fstab分区表适配、SELinux宽容模式开启、ADB调试开启
- Automatic boot image processing: kernel replacement, fstab partition table adaptation, SELinux permissive mode enabling, ADB debugging enabling.
- 自动处理system镜像：驱动文件替换、屏幕DPI同步、设备型号/时区/语言同步
- Automatic system image processing: driver file replacement, screen DPI synchronization, device model/timezone/language synchronization.
- 支持Magisk boot.img修补（可选）
- Supports Magisk boot.img patching (optional).
- 移植时自动读取并打印底包/移植源信息（内核版本、Android版本、芯片平台、系统架构等）
- Automatically reads and prints base/donor info (kernel version, Android version, chip platform, architecture, etc.) during porting.

- **3. 体验优化 / Experience Optimization：**
- 防止重复点击：“一键移植”按钮执行中自动禁用，避免多进程/多窗口冲突
- Prevents repeated clicks: The "One-Click Porting" button is automatically disabled during execution to avoid multi-process/window conflicts.
- 移植条目支持全选/三态全选（部分选中显示“-”），滚轮流畅滚动
- Porting items support select-all / tri-state select-all (partial selection shows "-"), with smooth wheel scrolling.
- 结构化日志：清晰显示每一步操作（如“解包boot.img”“替换内核文件”），便于排查问题
- Structured logging: Clearly displays each operation step (e.g., "Unpacking boot.img", "Replacing kernel files") for easier troubleshooting.
- 单实例保护：同一目录仅允许运行一个实例；再次启动可跳转至正在运行的程序，或清除残留状态锁（强杀后自动接管，不再误锁死）
- Single-instance guard: only one instance per directory; re-launch can jump to the running instance or clear the stale lock (auto-takeover after force-kill).
- 时间戳输出目录：移植/打补丁输出统一保存到 out/<时间戳>/ 实时时间戳目录（每次点击开始移植/打补丁时按当前时间生成，如 out/20260926-10：26：45/），各方案底部“打开输出目录”按钮一键跳转
- Timestamped output dirs (out/<timestamp>/, generated in real time at each run, e.g. out/20260926-10：26：45/); an "Open Output Dir" button at the bottom of every mode opens the latest output.

- **4. 多方案与自动识别 / Presets & Auto Mode：**
- 内置7套预设方案：mt6572/mt6582/mt6592、G79(mt6735/mt6737)、mt6580/mt8321、mt8163平板、**mt6797(Helio X20/X25)** 等
- 7 built-in presets: mt6572/mt6582/mt6592, G79(mt6735/mt6737), mt6580/mt8321, mt8163 tablet, **mt6797 (Helio X20/X25)**, etc.
- **未列芯片（同平台自动识别）**：自动扫描底包并识别替换硬件文件（firmware/HAL/GPU/音频/WiFi/RIL等），不触碰系统框架库
- **Unknown chip (auto mode)**: automatically scans and replaces hardware files (firmware/HAL/GPU/audio/WiFi/RIL, etc.) without touching system framework libraries.
- **仅移植内核（只输出boot）**：跳过system处理，只输出boot.img
- **Kernel-only mode**: skips system processing and outputs only boot.img.
- **仅移植Recovery（只输出recovery）**：独立 recovery.img 移植流程，仅支持 img 镜像输出（参考 [Xxinn034/mtk-legacy-porttool](https://github.com/Xxinn034/mtk-legacy-porttool) 分支实现）
- **Recovery-only mode**: standalone recovery.img porting flow, img output only (based on [Xxinn034/mtk-legacy-porttool](https://github.com/Xxinn034/mtk-legacy-porttool)'s branch).
- **LK去警告（兼容大多数安卓版本）**：去除 Orange/Red 警告与 5 秒延时；支持扫描/打补丁/校验/还原/自动备份（整合自 [justistab3-bot/mtk-lk-warning-patch](https://github.com/justistab3-bot/mtk-lk-warning-patch)）
- **LK warning patch mode** (works on most Android versions): removes Orange/Red warnings + 5s delay; scan/patch/verify/restore/auto-backup (integrated from [justistab3-bot/mtk-lk-warning-patch](https://github.com/justistab3-bot/mtk-lk-warning-patch)).

- **5. 文件系统修复与自查 / FS Fix & Verification：**
- 符号链接修复（Windows解包丢失的 !<symlink> 标记转回真符号链接，支持raw/sparse）
- Symlink fix (converts !<symlink> markers lost during Windows unpacking back to real symlinks, raw/sparse supported).
- GDT_CSUM校验和重算（修复TWRP刷入报“Structure needs cleaning”）
- GDT_CSUM recalculation (fixes "Structure needs cleaning" when flashing with TWRP).
- inode bitmap修复 + 打包后自动5项文件系统一致性自查
- inode bitmap fix + automatic 5-item filesystem integrity check after packaging.

- **6. 缓存优化 / Cache Optimization：**
- base缓存：底包system解包结果按MD5缓存（分块计算），MD5一致且目录存在时跳过重复解包；可勾选“完成后清除base目录”
- Base cache: base system unpack results are cached by MD5 (chunked calculation); unpack is skipped when MD5 matches and the directory exists; optional "clear base directory after completion" checkbox.

- **7. 更新检查 / Update Check：**
- 标题栏“检查更新”按钮（30秒超时提示失败），更新源支持 GitHub / Gitee 切换
- "Check Update" button in the title bar (30s timeout shows failure), switchable between GitHub / Gitee sources.
- 启动时静默检查更新，发现新版本自动弹出更新窗口
- Silent update check on startup; pops up the update window automatically when a new version is found.

- **8. 版本检测与警告 / Version Detection：**
- 自动检测底包/移植源Android版本（API），Android 8.0+（可能启用Treble/VNDK）与跨大版本移植给出警告
- Auto-detects base/donor Android version (API); warns on Android 8.0+ (possible Treble/VNDK) and cross-major-version porting.

## CLI 桥接接口 / CLI Bridge Interface

工具内置纯命令行桥接入口 `porttool_cli.py`（与 main.py 同级），供 **Java / C / C++ / Rust** 等其它平台的 UI 壳复用本工具能力：参数传入（方案、路径、条目开关、输出类型），日志与结果经 stdout 传出（可选 `--log-file` 落盘），退出码约定 **0=成功 / 1=参数·校验错误 / 2=执行失败**。

The tool ships a pure command-line bridge entry `porttool_cli.py` (in the same directory as main.py), so UI shells on other platforms (**Java / C / C++ / Rust** ...) can reuse this tool's capabilities: parameters in (preset, paths, item toggles, output type), logs & results out via stdout (optional `--log-file`), exit codes **0=ok / 1=arg/validation error / 2=execution failure**.

- 子命令：`port`（移植，普通 / kernel-only / recovery-only，img 或 zip 输出）、`lk`（LK 去警告：scan/patch/verify/restore）、`fscheck`（文件系统自查）、`check-update`（检查更新）；顶层查询：`--chipsets` / `--items` / `--version`
- Subcommands: `port` (normal / kernel-only / recovery-only, img or zip output), `lk` (scan/patch/verify/restore), `fscheck` (filesystem integrity check), `check-update`; top-level queries: `--chipsets` / `--items` / `--version`.

完整接口规范见同目录 [TASK_UI_SHELL.md](mtk-garbage-porttool-master/TASK_UI_SHELL.md)（该手册同时随发行版 zip 资产分发，仅下载发行版也能看到接口规范）。

Full interface spec: [TASK_UI_SHELL.md](mtk-garbage-porttool-master/TASK_UI_SHELL.md) in the same directory (also shipped inside the release zip asset, so the spec is available even if you only download the release).

## 环境要求 / Environment Requirements

- **运行环境 / Runtime Environment：**
- Python 3.10 及以上版本（需自带 tkinter 库，Windows 通常默认安装）
- Python 3.10 or higher (requires the built-in tkinter library, usually pre-installed on Windows).

## 使用步骤 / Usage Steps

- **1. 准备文件 / Prepare Files：**
- 底包：当前设备的 boot.img + system.img（从官方ROM中提取）
- Base package: The current device's boot.img + system.img (extracted from the official ROM).
- 移植源：目标ROM的 ZIP卡刷包 或 boot.img+system.img
- Donor source: The target ROM's ZIP flashable package OR boot.img+system.img.

- **2. 启动工具 / Start the Tool：**
- 下载/克隆项目到本地
- Download/clone the project locally.
- 打开终端，进入项目目录，执行命令启动 / Open a terminal, navigate to the project directory, and run:
  ```bash
  python main.py
  ```
  或直接双击 `run.bat` / Or double-click `run.bat`.

- **3. 配置移植 / Configure Porting：**
- 选择芯片类型（需与底包芯片匹配）
- Select the chip type (must match the base package chip).
- 勾选需要的移植条目（工具会自动加载对应芯片的默认条目，支持全选）
- Check the required porting items (the tool will auto-load default items for the selected chip; select-all supported).
- 选择输出类型： ZIP卡刷包 / img镜像
- Select the output type: ZIP flashable package / img images.
- （可选）勾选“修补Magisk”，选择Magisk APK并指定架构（如 arm64）
- (Optional) Check "Patch Magisk", select the Magisk APK, and specify the architecture (e.g., arm64).

- **4. 执行移植 / Execute Porting：**
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

- 解压/复制移植源文件到临时目录
- Extract/Copy donor source files to a temporary directory.

- 解包底包&移植源的boot.img，打印双端内核信息，自动替换内核/分区表，配置SELinux/ADB
- Unpack the base package & donor source's boot.img, print kernel info of both sides, automatically replace the kernel/partition table, and configure SELinux/ADB.

- 重新打包boot.img
- Repack the boot.img.

- 解包底包&移植源的system.img，打印双端系统信息，自动替换驱动、同步设备配置
- Unpack the base package & donor source's system.img, print system info of both sides, automatically replace drivers and synchronize device configurations.

- 打包输出（ZIP卡刷包或img镜像）
- Package the output (ZIP flashable package or img images).

- 清理临时文件（base缓存默认保留，可勾选完成后清除）
- Clean up temporary files (base cache kept by default; optional cleanup after completion).

- 仅移植内核（kernel-only）模式：只执行第1～3步并输出 boot.img，跳过 system 处理。
- Kernel-only mode: only executes steps 1-3 and outputs boot.img, skipping system processing.

## 注意事项 / Notes

- **1. 兼容性前提 / Compatibility Prerequisites：**
- 底包与移植源的芯片架构必须一致，且建议为同平台/同芯片系列（如均为MT6739、MT6737），驱动才兼容
- The chip architecture of the base package and donor source must match, and they should ideally be the same platform/chip series (e.g., both MT6739/MT6737) for driver compatibility.
- 底包与移植源的system分区大小建议接近，避免镜像生成失败
- The system partition sizes of the base package and donor source should be similar to avoid image generation failures.

- **2. 版本限制 / Version Limits：**
- 本工具面向 Android 7.1.2 及更低版本（无VNDK）的老设备；Android 8.0+（有VNDK/Treble）建议直接刷GSI
- This tool targets legacy devices on Android 7.1.2 and below (no VNDK); for Android 8.0+ (with VNDK/Treble), flashing GSI is recommended.
- 底包与移植源Android大版本差≥3时工具会警告，HAL接口可能不兼容
- The tool warns when base/donor Android major versions differ by ≥3; HAL interfaces may be incompatible.

- **3. 风险提示 / Risk Warning：**
- 刷机有风险，请提前备份设备数据
- Flashing carries risks; please back up your device data in advance.
- 仅在测试设备上使用，请勿用于商用或非法用途
- Use only on test devices. Do not use for commercial or illegal purposes.

- **4. 其他说明 / Other Notes：**
- 输出ZIP卡刷包时，仅支持以ZIP卡刷包作为移植源
- When outputting a ZIP flashable package, only a ZIP flashable package is supported as the donor source.
- 请确保底包boot已去除加密/签名校验，本工具不负责去除校验
- Make sure the base boot has encryption/signature verification removed; this tool does not handle that.

## 常见问题 / FAQ

- **Q：** 点击“一键移植”后按钮变灰，无其他反应？
- **A：** 这是防止重复执行的机制，工具正在后台处理流程，可通过“日志输出”查看进度。

- **Q：** ADB调试未生效？
- **A：** 工具会优先修改 system/build.prop 中的 ro.debuggable 等配置，若未生效可手动检查该文件。

- **Q：** 镜像生成失败？
- **A：** 检查 bin 目录下的工具是否与当前系统平台匹配（如Windows对应 win/x86_64 目录）。

- **Q：** 移植后卡第一屏或外放无声？
- **A：** 多为底包与移植源非同平台导致驱动不兼容。请确认两者为同芯片系列，并优先使用auto模式或匹配方案；音频异常可检查音频驱动/参数是否随底包替换。

- **Q:** After clicking "One-Click Porting", the button turns gray and there's no other response?
- **A:** This is a mechanism to prevent repeated execution. The tool is processing in the background. Check the progress via the "Log Output".

- **Q:** ADB debugging doesn't take effect?
- **A:** The tool prioritizes modifying configurations like ro.debuggable in system/build.prop. If it doesn't work, manually check that file.

- **Q:** Image generation failed?
- **A:** Check if the tools in the bin directory match your system platform (e.g., Windows corresponds to the win/x86_64 directory).

- **Q:** Stuck at first screen or no external speaker sound after porting?
- **A:** Usually caused by driver incompatibility when base/donor are not from the same platform. Make sure they are the same chip series, prefer the auto mode or a matching preset; for audio issues, check whether audio drivers/params were replaced from the base package.

## 免责声明 / Disclaimer

本工具仅用于ROM移植技术学习与交流，请勿用于侵犯他人知识产权、违反设备厂商协议的行为。因使用本工具导致的设备损坏、数据丢失等问题，开发者不承担任何责任。

This tool is intended only for technical learning and exchange regarding ROM porting. Do not use it for infringing on others' intellectual property rights or violating device manufacturer agreements. The developer bears no responsibility for device damage, data loss, or other issues arising from the use of this tool.

## 软件截图 / Software Screenshots

<img width="1356" height="670" alt="image" src="https://github.com/user-attachments/assets/42c1f934-4bac-420e-8b2a-12f6ebea2713" />

<img width="1353" height="669" alt="image" src="https://github.com/user-attachments/assets/5ef915a1-53e0-4795-a4e5-950bbb293998" />

<img width="1509" height="619" alt="image" src="https://github.com/user-attachments/assets/0383b891-e021-4021-a738-aabd3137b60e" />

## 感谢[@affggh](https://github.com/affggh)分享的原文件，此移植工具基于原工具进行的改进 / Thanks to [@affggh](https://github.com/affggh) for sharing the original files. This porting tool is an improvement based on the original tool.

原作者/Original Author [@affggh](https://github.com/affggh)

- 恢复模式移植参考 [@Xxinn034](https://github.com/Xxinn034/mtk-legacy-porttool) 分支实现 / Recovery-only porting based on [@Xxinn034](https://github.com/Xxinn034/mtk-legacy-porttool)'s branch.
- LK 去警告工具整合自 [@justistab3-bot](https://github.com/justistab3-bot/mtk-lk-warning-patch) / LK warning patch integrated from [@justistab3-bot](https://github.com/justistab3-bot/mtk-lk-warning-patch).

## 早期改动 / Early Changes

- 修复了处理build.prop文件时遇到非utf-8字符导致报错
- Fixed errors caused by non-UTF-8 characters when processing the build.prop file.

- 新增了单独system和boot镜像移植为img镜像的功能
- Added the function to port separate system and boot images into img images.

- 优化了输出日志的描述
- Optimized the description of the output logs.

- 解决了工具在报错时无法自动删除临时文件以及漏删base文件夹
- Fixed the issue where the tool failed to automatically delete temporary files and leaked the base folder upon error.

- 解决了重复点击“一键移植”按钮会弹出多个窗口的问题
- Fixed the issue where repeated clicks on the "One-Click Porting" button would open multiple windows.

- 符号链接丢失/GDT_CSUM校验和/inode bitmap/bootimg全局变量不重置（卡开机根因）等致命bug修复，硬件驱动配置全面适配现代MTK设备（vendor分区）
- Fatal bugs including lost symlinks / GDT_CSUM checksum / inode bitmap / bootimg module globals not reset (boot-loop root cause); hardware driver configs fully adapted to modern MTK devices (vendor partition).

## 近期更新 / Recent Updates
- 1.3-beta2p2（1.3-beta2p1 的紧急修补 / emergency patch for 1.3-beta2p1）：修复 zip 移植源崩溃（输入概览 UnboundLocalError）；非 sdat zip 输出不再包含未移植的 donor 原版 system.img；CLI LK patch 空转改为强制指定补丁；CLI Magisk 架构默认对齐 GUI（arm64）；发行版 Linux 工具执行权限修复（zip 内 0755 + 运行前自动 chmod）；run.sh shebang 规范化为 /bin/sh；p2 归档轮收尾——Magisk stub 链路修复（stub.apk 缺失不再传空参数 + 输出缺失警告）、平板方案无效「替换init」残留条目清理、boot 移植 init 替换空值守卫（防静默空转）、解包 symlink 目标路径引号清理
  - 1.3-beta2p2 (emergency patch for 1.3-beta2p1): fixed zip-donor crash (UnboundLocalError in input overview); non-sdat zip output no longer embeds the unported donor system.img; CLI LK patch no longer idles silently (requires at least one patch flag); CLI Magisk arch default aligned with GUI (arm64); release Linux tool exec-permission fix (0755 in zip + auto chmod before exec); run.sh shebang normalized to /bin/sh; p2 archiving round — Magisk stub fixes (no empty argv when stub.apk missing + missing-stub warning), tablet preset invalid "replace init" leftover cleanup, empty-value guard for boot init replacement (no silent no-op), symlink target quote cleanup in extraction.
- 1.3-beta2p1（1.3-beta2 的紧急修补 / emergency patch for 1.3-beta2）：修复 CLI 边界问题——`--log-file` 指向无效路径时不再抛 traceback 崩溃（降级为仅 stdout 并提示）；`--donor-zip` 与 `--donor-boot/--donor-system` 互斥校验（原静默忽略改为明确报错）
  - 1.3-beta2p1 (emergency patch for 1.3-beta2): fixed CLI edge cases — invalid `--log-file` path no longer crashes with a traceback (degrades to stdout-only with a notice); `--donor-zip` vs `--donor-boot/--donor-system` mutual-exclusion check (silent ignore now reports an error).
- 1.3-beta2（自 1.3-beta1p1 之后的所有改动 / all changes after beta1p1）：新增 CLI 桥接接口 `porttool_cli.py` 与接口规范 `TASK_UI_SHELL.md`（供其它平台 UI 壳复用；接口/退出码/日志规范详见手册，手册同时随发行版 zip 资产分发）；修复 CLI lk 子命令参数崩溃、argparse 退出码统一、check-update 下载链解析；CLI 与手册随源码置于 `mtk-garbage-porttool-master/` 子目录（与 main.py 同级）
  - 1.3-beta2: added the CLI bridge entry `porttool_cli.py` + interface spec `TASK_UI_SHELL.md` (for UI shells on other platforms; the spec is also shipped inside the release zip); fixed the lk subcommand argument crash, unified argparse exit codes, check-update download-URL parsing; CLI & manual live in `mtk-garbage-porttool-master/` alongside main.py.
- 1.3-beta1p1（1.3-beta1 的紧急修补 / emergency patch for 1.3-beta1）：修复 LK 去警告跨会话备份查找失效——重启工具后「校验」「还原」「打开输出目录」找不到上次会话的备份/补丁（会话级全局变量问题），现改为扫描 out/ 下所有时间戳子目录查找 `<名字>_original_backup` / `<名字>_patched`，旧备份仍可识别
  - 1.3-beta1p1 (emergency patch for 1.3-beta1): fixed LK warning-patch cross-session backup lookup — after restarting the tool, "Verify" / "Restore" / "Open Output Dir" could not find previous backups/patched images (session-level global issue); now scans all timestamped subdirs under out/ for `<name>_original_backup` / `<name>_patched`, old backups remain recognizable.
- 1.3-beta1（自 beta6 之后的所有改动 / all changes after beta6）：新增恢复模式移植（仅移植Recovery，独立 recovery.img 流程，参考 [Xxinn034/mtk-legacy-porttool](https://github.com/Xxinn034/mtk-legacy-porttool) 分支实现）；整合 LK 去警告工具（兼容大多数安卓版本，去Orange/Red警告+5s延时，整合自 [justistab3-bot/mtk-lk-warning-patch](https://github.com/justistab3-bot/mtk-lk-warning-patch)）；输出目录时间戳化（out/<时间戳>/，每次运行实时生成）+ 全方案“打开输出目录”按钮；单实例保护（同目录单实例、跳转至运行实例/清除状态锁/残留锁自动接管）；输出类型区 Labelframe 分组；LZ4 支持强化（内置 lz4.py、失败写日志）；kernel-only/Recovery 输出限制完善；系列整合修复
  - 1.3-beta1: added Recovery-only porting (standalone recovery.img flow, based on [Xxinn034/mtk-legacy-porttool](https://github.com/Xxinn034/mtk-legacy-porttool)'s branch); integrated the LK warning patch tool (works on most Android versions, removes Orange/Red warnings + 5s delay, from [justistab3-bot/mtk-lk-warning-patch](https://github.com/justistab3-bot/mtk-lk-warning-patch)); timestamped output dirs (out/<timestamp>/, generated at each run) + "Open Output Dir" button for all modes; single-instance guard (jump to running instance / clear stale lock / auto-takeover); Labelframe grouping for output type; hardened LZ4 support (built-in lz4.py, failures logged); kernel-only/Recovery output restrictions; integration fixes.
- 1.2-beta6p3（自 beta6p2 之后的所有改动 / all changes after beta6p2）：boot.img 解包兼容性修复——自动搜索 ANDROID! 魔数跳过 MTK 头部等前缀；ramdisk 多格式支持（gzip/raw cpio/lz4），未知格式不再崩溃、复制 ramdisk.raw 兜底；修正带 MTK 头时 padding 对齐错位；识别 boot header v1（Android 8+ system-as-root）——此类设备 ramdisk_size=0 属正常不再误报，Android 7 及以下设备缺失 ramdisk 才给出无法开机的警告
  - 1.2-beta6p3: boot.img unpack compatibility fixes — auto-skip MTK headers via ANDROID! magic search; multi-format ramdisk support (gzip/raw cpio/lz4) with raw-copy fallback on unknown formats (no crash); fixed padding misalignment when an MTK header is present; detects boot header v1 (Android 8+ system-as-root) so ramdisk_size=0 is treated as normal, while warning of unbootable results only when an Android 7-or-lower device lacks a ramdisk.
- 1.2-beta6p2（自 beta6p1 之后的所有改动 / all changes after beta6p1）：解包健壮性全面修复——底包缓存 MD5 写入时序（解包成功后才写，杜绝静默使用残缺底包产出错误镜像）；ext4 目录名 GBK 解码回退、损坏目录块与越界 inode 防御、xattr 两处崩溃修复；单个坏目录不再中断整个移植并输出警告；异常日志补全完整堆栈；Linux 下临时文件权限清理修复；DPI/型号同步增加“ro.* 属性可能被更早来源覆盖”提示；移除 sdat2img Python 2 死代码
  - 1.2-beta6p2: comprehensive extraction robustness fixes — base cache MD5 written only after successful unpack (prevents silently using a partial base and producing broken images); ext4 dir-name GBK fallback, corrupt block & out-of-range inode guards, two xattr crash fixes; a single bad directory no longer aborts the whole port (warnings logged); full traceback on errors; Linux temp-file permission cleanup fix; DPI/model sync now hints that ro.* props may be overridden by earlier sources; removed sdat2img Python 2 dead code.
- 1.2-beta6（自 beta5 之后的所有改动 / all changes after beta5）：SDAT 卡刷包结构修复（block_image_update 脚本/contexts 回退/raw 先行转 sparse）；刷机脚本分区自动解析（不再硬编码，支持 boot-only）；kernel-only + ZIP 坏包拦截；mt6572/mt6580 补 wifi 替换与缺失路径跳过提示；权限推断增强（bin/xbin 精确匹配+suid）；配置收窄与去重（wifi vendor/firmware 通配、libcam_utils/libstagefrighthw 白名单、auto modem 固件保留）；底层模块与工具启动系列修复（ext4/大小换算/xattr、imgextractor 分块/容错、proputil BOM、Magisk 旧版 apk、fscheck 包导入、配置路径基于文件定位、更新检查线程安全）；boot-only 卡刷与 BootPatcher 友好阻断
  - 1.2-beta6: SDAT package structure fix (block_image_update script / contexts fallback / raw-then-sparse); automatic partition parsing in updater scripts (no more hardcoding, boot-only supported); kernel-only + ZIP bad-package guard; wifi replacement added for mt6572/mt6580 with skip notice for missing paths; permission inference refined (exact bin/xbin + suid); config narrowing & dedup (wifi vendor/firmware wildcards, libcam_utils/libstagefrighthw whitelist, auto modem firmware preserved); low-level & tooling fixes (ext4/size/xattr, imgextractor chunked IO/robustness, proputil BOM, legacy Magisk APK, fscheck package import, config paths relative to file, thread-safe update check); BootPatcher friendly abort.
- 1.2-beta5（自 beta4 之后的所有改动 / all changes after beta4）：新增mt6797(Helio X20/X25)方案与双架构驱动补齐；G79外放无声根治（音频/TFA功放驱动）；auto模式增强（lib64/egl/TFA）；移植信息自动读取与日志优化；方案改名与排序；UI交互优化（移植条目滚轮修复与滚动速度优化、三态全选，部分选中显示“-”）；版本号更新
  - 1.2-beta5: Added mt6797 (Helio X20/X25) preset with dual-arch drivers; fixed G79 no-sound issue (audio/TFA amp drivers); enhanced auto mode (lib64/egl/TFA); auto info reading & log optimization; preset renaming & ordering; UI improvements (wheel scrolling fix & speed, tri-state select-all showing "-" for partial); version bump.
- 1.2-beta4：更新检查（GitHub/Gitee双源、静默启动检查、30s超时）；base缓存与“完成后清除base目录”选项；API版本检测与跨大版本/VNDK警告；sparse镜像支持；仅移植内核只输出boot；左下角版本号显示、Magisk选择按钮
  - 1.2-beta4: Update check (GitHub/Gitee sources, silent startup check, 30s timeout); base cache & "clear base after completion" option; API version detection with cross-version/VNDK warnings; sparse image support; kernel-only outputs boot only; version label at bottom-left, Magisk picker button.

## 性能参考 / Performance Reference

> 估算基准 / Baseline：底包 system 2.8GB + 移植源 system 0.94GB，全量移植（boot+system），img 镜像输出。
> 估算模型 / Model：总时长 ≈ 底包大小(GB)×1.5s + 移植源大小(GB)×1.2s + 固定开销约5s，再按 CPU 单核能力与磁盘写入速度打折。

| 配置档次 / Tier | CPU 示例 / Example | 磁盘类型 / Disk | 预估时长 / Est. time | 主要瓶颈 / Bottleneck |
|---|---|---|---|---|
| 高端 High-end | i7-13650HX / i9 HX（8核+，P核4.5GHz+） | Gen4 NVMe | ～15s | 无瓶颈 none |
| 中高端 Upper-mid | i5-12/13代 / R5-5代（6核） | Gen3 NVMe | ～30～45s | 写速 ～1.5GB/s 上限 |
| 中端 Mid | i5-8/10代 / R5-3代（4核） | SATA SSD | 1～1.5 分钟 | 单核 + SSD 写 ～450MB/s |
| 入门 Entry | 赛扬/老奔腾（双核） | SATA SSD | 2～3 分钟 | 单核 |
| 低端 Low-end | 双核 2GHz 级 | 机械盘 7200rpm | 5～10 分钟 | 机械盘 ～100MB/s |
| 下限 Floor | 老双核 + 机械盘 + 5GB+ 镜像 | 机械盘 | 15～30 分钟 | 机械盘近乎全占 |

**镜像规模影响 / Impact of image size**（同一台机器 / same machine）：

| 底包大小 / Base size | 高端 High-end | 中端 Mid | 低端 Low-end |
|---|---|---|---|
| ～1 GB（入门机 ROM） | ～8s | ～40s | 2～4 分钟 |
| ～3 GB | ～15s | 1～1.5 分钟 | 5～10 分钟 |
| ～6 GB（大 ROM） | ～25s | 2～3 分钟 | 10～20 分钟 |

**规律 / Notes**：
- 磁盘 > CPU：镜像越大磁盘占比越高，机械盘换 SATA SSD 通常提速 4～6 倍 / Disk matters more than CPU on large images; HDD→SATA SSD usually gives 4-6x speedup.
- 固定开销约 5s（boot 流程/启动/清理），小镜像时占比高 / ～5s fixed overhead (boot flow/startup/cleanup), dominant on small images.
- 流程串行，多核基本用不上，单核快才是关键 / Pipeline is serial; single-core speed matters more than core count.
- 输出 zip 卡刷包比 img 多一段 img2sdat 差分计算（约 +10～20%）/ Zip output adds img2sdat diffing (～+10-20%).

### 实机测试 / Real-Machine Test

2026-09-26 实测（底包 山寨机 szj 2.8GB + 移植源 巴枪 bq 0.94GB，方案 mt6572/mt6582/mt6592 kernel-3.4.67，全量 img 输出）：

| 项 / Item | 值 / Value |
|---|---|
| 机器 / Machine | THUNDEROBOT R16 雷神笔记本 |
| CPU | Intel Core i7-13650HX（14核20线程，睿频4.9GHz） |
| 内存 / RAM | 16GB DDR5 4800MHz |
| 硬盘 / Disk | Crucial P3 Plus 1TB NVMe（Gen4） |
| 系统 / OS | Windows 11 专业版 |
| 解包（底包+移植源 3.7GB） | 4.2s |
| system 移植（驱动替换 + build.prop） | 5.9s |
| 打包（make_ext4fs 2.79GB + 符号链接修复 + 一致性自查） | 2.5s |
| **总时长 / Total** | **14.8s** |

## 改进者QQ/邮箱 / Improver's QQ/Email

3368436451@qq.com

## 相关群聊 / Related Chat Group

<img width="1284" height="2280" alt="qrcode_1790395495264" src="https://github.com/user-attachments/assets/60010279-d11e-4c42-8148-3f69d9283a9a" />

<img width="1284" height="2280" alt="qrcode_1790395471488" src="https://github.com/user-attachments/assets/4e67f913-927e-4108-8fad-6470730f57e1" />
