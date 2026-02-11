## MTK低端机ROM移植工具 / MTK Low-End Device ROM Porting Tool
 
# 项目介绍/ Project Introduction
 
这是一个针对 **MTK低端芯片系列（如MT65xx、MT67xx入门款）** 的ROM移植辅助工具，旨在简化“底包（当前设备官方ROM）”与“移植源（目标ROM）”之间的boot/system镜像适配流程，自动完成文件替换、配置同步、镜像打包等繁琐步骤，降低低端机ROM移植的技术门槛。

This is a ROM porting assistance tool specifically designed for MTK low-end chip series (such as MT65xx, MT67xx entry-level models). It aims to simplify the adaptation process of boot/system images between the "base package (official ROM of the current device)" and the "donor source (target ROM)". It automates tedious steps such as file replacement, configuration synchronization, and image repacking, lowering the technical barrier for ROM porting on low-end devices.
 
# 功能特点 / Features
 
**1. 多源支持 / Multi-Source Support：** 
- 移植源可选： ZIP卡刷包  /  单独boot.img+system.img 
- Donor source options: ZIP flashable package / Separate boot.img+system.img
- 输出类型可选： ZIP卡刷包 （仅支持ZIP源） /  boot.img+system.img （支持所有源）
- Output type options: ZIP flashable package (only for ZIP donor source) / boot.img+system.img (for all donor sources)

**2. 自动化移植/ Automated Porting：**
- 自动处理boot镜像：内核替换、fstab分区表适配、SELinux宽容模式开启、ADB调试开启
- Automatic boot image processing: kernel replacement, fstab partition table adaptation, SELinux permissive mode enabling, ADB debugging enabling.
- 自动处理system镜像：驱动文件替换、屏幕DPI同步、设备型号/时区/语言同步
- Automatic system image processing: driver file replacement, screen DPI synchronization, device model/timezone/language synchronization.
- 支持Magisk boot.img修补（可选）
- Supports Magisk boot.img patching (optional).

**3. 体验优化/ Experience Optimization：**
- 防止重复点击：“一键移植”按钮执行中自动禁用，避免多进程/多窗口冲突
- Prevents repeated clicks: The "One-Click Porting" button is automatically disabled during execution to avoid multi-process/window conflicts.
- 自动清理：流程结束后自动删除 base / tmp 临时目录，无文件残留
- Auto-cleanup: Automatically deletes base / tmp temporary directories after the process finishes, leaving no residual files.
- 结构化日志：清晰显示每一步操作（如“解包boot.img”“替换内核文件”），便于排查问题
- Structured logging: Clearly displays each operation step (e.g., "Unpacking boot.img", "Replacing kernel files") for easier troubleshooting.
 
# 环境要求/ Environment Requirements
 
**运行环境/ Runtime Environment：**
- Python 3.8 及以上版本（需自带 tkinter 库，Windows/macOS通常默认安装）
- Python 3.8 or higher (requires the built-in tkinter library, usually pre-installed on Windows/macOS).

# 使用步骤/ Usage Steps
 
**1. 准备文件/ Prepare Files：**
- 底包：当前设备的 boot.img  +  system.img （从官方ROM中提取）
- Base package: The current device's boot.img + system.img (extracted from the official ROM).
- 移植源：目标ROM的 ZIP卡刷包  或  boot.img+system.img 
- Donor source: The target ROM's ZIP flashable package OR boot.img+system.img.

**2. 启动工具/ Start the Tool：**
- 下载/克隆项目到本地
- Download/clone the project locally.
- 打开终端，进入项目目录，执行命令启动/Open a terminal, navigate to the project directory, and run:
  ```bash
  # 若入口文件为其他名称（如prottool.py），替换为对应文件名
  # If the entry file has a different name (e.g., prottool.py), replace it accordingly.
  python main.py

**3. 配置移植/ Configure Porting：**
- 选择芯片类型（如 mt65xx ，需与底包芯片匹配）
- Select the chip type (e.g., mt65xx, must match the base package chip).
- 勾选需要的移植条目（工具会自动加载对应芯片的默认条目）
- Check the required porting items (the tool will auto-load default items for the selected chip).
- 选择输出类型： ZIP卡刷包  /  img镜像 
- Select the output type: ZIP flashable package / img images.
- （可选）勾选“修补Magisk”，选择Magisk APK并指定架构（如 arm64 ）
- (Optional) Check "Patch Magisk", select the Magisk APK, and specify the architecture (e.g., arm64).

**4. 执行移植 / Execute Porting：**
- 点击“一键移植”，在弹窗中选择：
- Click "One-Click Porting". In the pop-up window, select:
- 底包的 boot.img 和 system.img 
- The base package's boot.img and system.img.
- 移植源的 ZIP卡刷包  或  boot.img+system.img
-  The donor source's ZIP flashable package OR boot.img+system.img.
- 等待流程完成，输出文件会保存在 out 目录下
- Wait for the process to complete. Output files will be saved in the out directory.
 
# 移植核心流程/ Core Porting Process
 
工具自动执行以下步骤：
The tool automatically executes the following steps:
 
1. 解压/复制移植源文件到临时目录
  Extract/Copy donor source files to a temporary directory.

2. 解包底包&移植源的boot.img，自动替换内核/分区表，配置SELinux/ADB
  Unpack the base package & donor source's boot.img, automatically replace the kernel/partition table, and configure SELinux/ADB.

3. 重新打包boot.img
  Repack the boot.img.

4. 解包底包&移植源的system.img，自动替换驱动、同步设备配置
  Unpack the base package & donor source's system.img, automatically replace drivers and synchronize device configurations.

5. 打包输出（ZIP卡刷包或img镜像）
  Package the output (ZIP flashable package or img images).

6. 清理临时文件
  Clean up temporary files.
 
# 注意事项/ Notes
 
**1. 兼容性前提 / Compatibility Prerequisites：**
- 底包与移植源的芯片架构必须一致（如均为 arm 或 arm64 ）
- The chip architecture of the base package and donor source must match (e.g., both arm or arm64).
- 底包与移植源的system分区大小建议接近，避免镜像生成失败
- The chip architecture of the base package and donor source must match (e.g., both arm or arm64).

**2. 风险提示 / Risk Warning：**
- 刷机有风险，请提前备份设备数据
- Flashing carries risks; please back up your device data in advance.
- 仅在测试设备上使用，请勿用于商用或非法用途
- Use only on test devices. Do not use for commercial or illegal purposes.

**3. 其他说明 / Other Notes：**
- 输出ZIP卡刷包时，仅支持以ZIP卡刷包作为移植源
- When outputting a ZIP flashable package, only a ZIP flashable package is supported as the donor source.
 
# 常见问题 / FAQ
 
Q：点击“一键移植”后按钮变灰，无其他反应？

A：这是防止重复执行的机制，工具正在后台处理流程，可通过“日志输出”查看进度。
 
Q：ADB调试未生效？

A：工具会优先修改 system/build.prop 中的 ro.debuggable 等配置，若未生效可手动检查该文件。
 
Q：镜像生成失败？

A：检查 bin 目录下的工具是否与当前系统平台匹配（如Windows对应 win/x86_64 目录）。

Q: After clicking "One-Click Porting", the button turns gray and there's no other response?

A: This is a mechanism to prevent repeated execution. The tool is processing in the background. Check the progress via the "Log Output".

Q: ADB debugging doesn't take effect?

A: The tool prioritizes modifying configurations like ro.debuggable in system/build.prop. If it doesn't work, manually check that file.

Q: Image generation failed?

A: Check if the tools in the bin directory match your system platform (e.g., Windows corresponds to the win/x86_64 directory).

# 免责声明 / Disclaimer
 
本工具仅用于ROM移植技术学习与交流，请勿用于侵犯他人知识产权、违反设备厂商协议的行为。因使用本工具导致的设备损坏、数据丢失等问题，开发者不承担任何责任。

This tool is intended only for technical learning and exchange regarding ROM porting. Do not use it for infringing on others' intellectual property rights or violating device manufacturer agreements. The developer bears no responsibility for device damage, data loss, or other issues arising from the use of this tool.

# 软件截图 / Software Screenshots
<img width="943" height="456" alt="image" src="https://github.com/user-attachments/assets/5985d82c-78c2-46db-9702-158014caa543" />


<img width="948" height="471" alt="image" src="https://github.com/user-attachments/assets/0e5c8c30-8d12-4595-8ac2-37519ad6979f" />


# 感谢bilibili@洛可KoCleo分享的原文件，此移植工具基于原工具进行的改进 / Thanks to bilibili@洛可KoCleo for sharing the original files. This porting tool is an improvement based on the original tool.

原作者/Original Author：【洛可KoCleo的个人空间-哔哩哔哩】 https://b23.tv/jclWvor

# 基于原文件的主要改动 / Major Changes Based on the Original Files

1.修复了处理build.prop文件时遇到非utf-8字符导致报错

1. Fixed errors caused by non-UTF-8 characters when processing the build.prop file.

2.新增了单独system和boot镜像移植为img镜像的功能

2.Added the function to port separate system and boot images into img images.

3.优化了输出日志的描述

3. Optimized the description of the output logs.

4.解决了工具在报错时无法自动删除临时文件以及漏删base文件夹

4.Fixed the issue where the tool failed to automatically delete temporary files and leaked the base folder upon error.

5.解决了重复点击“一键移植”按钮会弹出多个窗口的问题

5.Fixed the issue where repeated clicks on the "One-Click Porting" button would open multiple windows.

# 改进者QQ/邮箱 / Improver's QQ/Email

3368436451@qq.com

# 相关群聊 / Related Chat Group

![qrcode_1770570404334](https://github.com/user-attachments/assets/3dbaaedb-818e-4b15-8df8-b423a63edd0e)

