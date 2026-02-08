## MTK低端机ROM移植工具
 
# 项目介绍
 
这是一个针对 **MTK低端芯片系列（如MT65xx、MT67xx入门款）** 的ROM移植辅助工具，旨在简化“底包（当前设备官方ROM）”与“移植源（目标ROM）”之间的boot/system镜像适配流程，自动完成文件替换、配置同步、镜像打包等繁琐步骤，降低低端机ROM移植的技术门槛。
 
# 功能特点
 
**1. 多源支持：** 
- 移植源可选： ZIP卡刷包  /  单独boot.img+system.img 
- 输出类型可选： ZIP卡刷包 （仅支持ZIP源） /  boot.img+system.img （支持所有源）

**2. 自动化移植：**
- 自动处理boot镜像：内核替换、fstab分区表适配、SELinux宽容模式开启、ADB调试开启
- 自动处理system镜像：驱动文件替换、屏幕DPI同步、设备型号/时区/语言同步
- 支持Magisk boot.img修补（可选）

**3. 体验优化：**
- 防止重复点击：“一键移植”按钮执行中自动禁用，避免多进程/多窗口冲突
- 自动清理：流程结束后自动删除 base / tmp 临时目录，无文件残留
- 结构化日志：清晰显示每一步操作（如“解包boot.img”“替换内核文件”），便于排查问题
 
# 环境要求
 
**1. 运行环境：**
- Python 3.8 及以上版本（需自带 tkinter 库，Windows/macOS通常默认安装）

**2. 工具依赖：**
- 项目 bin 目录下需放置对应平台的二进制工具（已内置常见平台版本）：
-  make_ext4fs ：用于生成system.img
-  img2simg ：用于转换稀疏镜像
-  sdat2img / img2sdat ：用于SDAT格式与IMG格式互转
 
# 使用步骤
 
**1. 准备文件：**
- 底包：当前设备的 boot.img  +  system.img （从官方ROM中提取）
- 移植源：目标ROM的 ZIP卡刷包  或  boot.img+system.img 

**2. 启动工具：**
- 下载/克隆项目到本地
- 打开终端，进入项目目录，执行命令启动：
  ```bash
  # 若入口文件为其他名称（如prottool.py），替换为对应文件名
  python main.py

**3. 配置移植：**
- 选择芯片类型（如 mt65xx ，需与底包芯片匹配）
- 勾选需要的移植条目（工具会自动加载对应芯片的默认条目）
- 选择输出类型： ZIP卡刷包  /  img镜像 
- （可选）勾选“修补Magisk”，选择Magisk APK并指定架构（如 arm64 ）

**4. 执行移植：**
- 点击“一键移植”，在弹窗中选择：
- 底包的 boot.img 和 system.img 
- 移植源的 ZIP卡刷包  或  boot.img+system.img 
- 等待流程完成，输出文件会保存在 out 目录下
 
# 移植核心流程
 
工具自动执行以下步骤：
 
1. 解压/复制移植源文件到临时目录

2. 解包底包&移植源的boot.img，自动替换内核/分区表，配置SELinux/ADB

3. 重新打包boot.img

4. 解包底包&移植源的system.img，自动替换驱动、同步设备配置

5. 打包输出（ZIP卡刷包或img镜像）

6. 清理临时文件
 
# 注意事项
 
**1. 兼容性前提：**
- 底包与移植源的芯片架构必须一致（如均为 arm 或 arm64 ）
- 底包与移植源的system分区大小建议接近，避免镜像生成失败

**2. 风险提示：**
- 刷机有风险，请提前备份设备数据
- 仅在测试设备上使用，请勿用于商用或非法用途

**3. 其他说明：**
- 输出ZIP卡刷包时，仅支持以ZIP卡刷包作为移植源
 
# 常见问题
 
Q：点击“一键移植”后按钮变灰，无其他反应？
A：这是防止重复执行的机制，工具正在后台处理流程，可通过“日志输出”查看进度。
 
Q：ADB调试未生效？
A：工具会优先修改 system/build.prop 中的 ro.debuggable 等配置，若未生效可手动检查该文件。
 
Q：镜像生成失败？
A：检查 bin 目录下的工具是否与当前系统平台匹配（如Windows对应 win/x86_64 目录）。
 
# 免责声明
 
本工具仅用于ROM移植技术学习与交流，请勿用于侵犯他人知识产权、违反设备厂商协议的行为。因使用本工具导致的设备损坏、数据丢失等问题，开发者不承担任何责任。

# 软件截图
<img width="943" height="456" alt="image" src="https://github.com/user-attachments/assets/5985d82c-78c2-46db-9702-158014caa543" />


<img width="948" height="471" alt="image" src="https://github.com/user-attachments/assets/0e5c8c30-8d12-4595-8ac2-37519ad6979f" />


# 感谢bilibili@洛可KoCleo分享的原文件，此移植工具基于原工具进行的改进
原作者：【洛可KoCleo的个人空间-哔哩哔哩】 https://b23.tv/jclWvor

# 基于原文件的主要改动

1.修复了处理build.prop文件时遇到非utf-8字符导致报错

2.新增了单独system和boot镜像移植为img镜像的功能

3.优化了输出日志的描述

4.解决了工具在报错时无法自动删除临时文件以及漏删base文件夹

5.解决了重复点击“一键移植”按钮会弹出多个窗口的问题

# 改进者QQ/邮箱

3368436451@qq.com

# 相关群聊

![qrcode_1770570404334](https://github.com/user-attachments/assets/3dbaaedb-818e-4b15-8df8-b423a63edd0e)

