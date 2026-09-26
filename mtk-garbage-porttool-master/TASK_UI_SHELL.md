# Task 使用说明：命令行桥接接口 / UI Shell Bridge Task

> 本文档定义根目录 `porttool_cli.py`（命令行桥接入口）的全部使用接口与规范，
> 供其它平台（Java / C / C++ / Rust / .NET 等）UI 壳调用。
> 壳只需启动本进程、按本文档传参、读取 stdout / 日志文件，即可复用工具的全部核心功能。

## 1. 概述 / Overview

`porttool_cli.py` 是纯命令行进程接口（无 GUI 依赖，不引入 tkinter）：

- **传入**：命令行参数（方案名、镜像路径、移植条目开关、输出类型、日志文件）
- **传出**：stdout 日志流（与 GUI 日志格式完全一致，带 `【】` 标记）+ 可选 `--log-file` 落盘 + 退出码
- **产物**：写入仓库根 `out/<时间戳>/` 子目录

壳开发时只需要：**拼参数 → 起进程 → 读 stdout / 退出码**。

## 2. 运行环境 / Requirements

- Python 3.9+（Windows / Linux 均可；主战场 Windows）
- 纯标准库，**无需第三方依赖**（CLI 不加载 tkinter；核心逻辑仅用 stdlib + 自带工具模块）
- 工作目录 = 仓库根目录（CLI 启动时自动 `chdir` 到根目录，壳无需关心）
- 首次运行会生成 `tmp/`、`base/`、`out/` 运行目录（与 GUI 相同）

## 3. 退出码 / Exit Codes

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 参数 / 校验错误（用法错误、方案不存在、文件缺失、非法组合） |
| `2` | 移植 / 执行失败（流程跑完但出错，日志中必有 `【移植异常】` 或 `【参数错误】`） |

壳必须依据退出码判断结果；不要用 stdout 文本做唯一判据（文本用于展示，退出码用于逻辑）。

## 4. 查询接口（壳动态加载配置）/ Query Interface

| 命令 | 输出 | 用途 |
|---|---|---|
| `python porttool_cli.py --version` | 版本号（如 `1.3-beta2`） | 版本展示 / 更新比较 |
| `python porttool_cli.py --chipsets` | 每行一个方案名 | 壳动态构建"芯片类型"下拉框 |
| `python porttool_cli.py --items --chipset "<方案名>"` | 每行 `条目键=值`（true/false） | 壳动态构建"移植条目"勾选列表 |

`--items` 输出的是该方案 `flags` 的**默认值**；壳勾选后通过 `port --item/--no-item` 回传。

## 5. 移植子命令 `port` / Port Subcommand

```
python porttool_cli.py port \
  --chipset "<方案名>" \
  --base-boot <底包boot.img路径> \
  [--base-system <底包system.img路径>] \
  --donor-boot <移植用boot.img路径> \
  [--donor-system <移植用system.img路径>] | --donor-zip <移植用zip路径> \
  [--out-type img|zip] \
  [--item <KEY>]... [--no-item <KEY>]... \
  [--patch-magisk] [--magisk-apk <路径>] [--target-arch arm] \
  [--clean-base] [--log-file <路径>]
```

### 5.1 文件传入接口（核心）/ File Inputs

| 参数 | 必填 | 说明 |
|---|---|---|
| `--chipset` | 是 | 方案名，必须与 `--chipsets` 输出完全一致 |
| `--base-boot` | 是 | 底包 boot.img（recovery 方案为底包 recovery 镜像） |
| `--base-system` | 视模式 | 底包 system.img；**普通移植必填**；kernel-only / recovery-only 模式省略 |
| `--donor-boot` | img 源必填 | 移植用 boot.img（recovery 方案为移植用 recovery 镜像） |
| `--donor-system` | 普通模式必填 | 移植用 system.img |
| `--donor-zip` | zip 源 | 移植用 zip 卡刷包（与 donor-boot/donor-system 二选一） |
| `--out-type` | 否 | `img`（默认）/ `zip` |

**模式自动判定**：不需要显式传"模式"——CLI 从方案配置的 `flags` 自动识别
`lk_patch_mode` / `recovery_only_mode` / `kernel_only_mode`，并按对应模式做文件校验与流程裁剪。

### 5.2 组合校验规则（与 GUI 完全一致）/ Validation Rules

| 组合 | 结果 |
|---|---|
| kernel-only / recovery-only + `--out-type zip` | 拒绝（仅支持 img） |
| recovery-only + `--donor-zip` | 拒绝（仅支持 img 移植源） |
| `--out-type zip` + img 移植源 | 拒绝（输出 zip 必须用 zip 源） |
| 底包 / 移植源文件不存在 | 拒绝，退出码 `1` |
| 未知方案名 | 拒绝，退出码 `1` |

### 5.3 移植条目传入 / Port Items

- 方案自带默认勾选（`flags`），CLI 默认按方案默认值执行，**无需全量传**
- `--item <KEY>` 开启某条目；`--no-item <KEY>` 关闭某条目（可多次）
- 覆盖规则：命令行 > 方案默认（与 GUI 勾选行为一致，拍平到 items 顶层）
- 常用条目键（可用 `--items` 查全部）：

| 键 | 含义 |
|---|---|
| `replace_kernel` | 替换内核 |
| `selinux_permissive` | 开启 SELinux 宽容模式 |
| `enable_adb` | 开启 ADB 调试 |
| `replace_firmware` / `replace_mddb` | 替换 firmware / mddb |
| `replace_malidriver` / `replace_audiodriver` | 替换 Mali / 音频驱动 |
| `replace_gralloc` / `replace_hwcomposer` | 替换 gralloc / hwcomposer |
| `fit_density` / `change_model` | 同步 DPI / 型号信息 |
| `change_timezone` / `change_locale` | 同步时区 / 语言区域 |
| `single_simcard` / `dual_simcard` | 单 / 双卡配置 |

### 5.4 输出约定 / Outputs

- 产物目录：`out/<YYYYMMDD-HH：MM：SS>/`（**全角冒号**，Windows 目录名限制；每次运行实时生成）
- 产物命名：`boot.img` / `system.img`（img 输出）；`zip 卡刷包`（zip 输出）
- LK 模式：备份 `<名字>_original_backup`、补丁 `<名字>_patched` 同样落在 out 时间戳目录下

## 6. 日志接口（重点）/ Log Interface

日志是壳与用户交互的核心通道，规范如下：

1. **stdout 为主**：所有日志经 stdout 输出，行尾 `\n`；壳应实时读取（可逐行展示）
2. **可选落盘**：`--log-file <路径>` 时 stdout 与文件**双写**（内容一致，UTF-8）
3. **格式**：所有行带 `【】` 中文标记前缀，与 GUI 日志逐字一致，例如：
   - `【开始移植】...` / `【解包boot.img】...` / `【移植项】...` / `【打包完成】...`
   - `【信息】底包 boot.img：`（缩进子行以 `  ├─` / `  └─` 开头）
   - `【CLI】...`：CLI 自身附加的信息行（方案、输出类型、输出目录）
   - `【参数错误】...` / `【移植异常】...` / `【流程结束】...`
4. **进度语义**：`【提示】开始执行...` 到 `【流程结束】...` / `【移植异常】...` 为一个完整任务区间
5. 壳若需要结构化信息（版本、方案列表、条目列表），用第 4 节的查询接口，不要解析日志

## 7. LK 去警告子命令 `lk` / LK Subcommand

```
python porttool_cli.py lk <scan|patch|verify|restore> --folder <固件目录> [选项] [--log-file <路径>]
```

| 操作 | 选项 | 说明 |
|---|---|---|
| `scan` | — | 扫描目录内 LK 镜像并报告警告 |
| `patch` | `--patch-a` `--patch-b` `--auto-backup` `--gen-report` `--inplace` | 打补丁去警告；默认输出到 out/，`--inplace` 原地写 |
| `verify` | — | 校验补丁是否成功 |
| `restore` | — | 用备份还原原镜像 |

- `--folder`：固件目录（GeekFlashTool readback 目录），自动检测 `lk.img` / `lk2.img`
- 备份 / 补丁产物写入 out 时间戳目录；跨会话仍可通过产物名找回

## 8. 文件系统自查子命令 `fscheck` / FS Check Subcommand

```
python porttool_cli.py fscheck <system.img路径> [--log-file <路径>]
```

- 复用根目录 `fscheck.py`：校验 ext4 文件系统完整性（GD 校验和、inode/block bitmap、extent 一致性）
- 移植后建议对产物 `out/<时间戳>/system.img` 自查一次

## 9. 更新检查子命令 `check-update` / Update Check Subcommand

```
python porttool_cli.py check-update --url <latest_version.txt的URL> [--log-file <路径>]
```

- 远程文件格式（兼容有/无引号）：`latest_version=tag`（必填）+ 下载地址（任选其一可解析）
  - `update_url_1=<GitHub 下载直链>` / `update_url_2=<Gitee 下载直链>` / `update_url=<通用链接>`
- - 输出本地 / 远程版本对比；相同输出"已是最新"，不同输出"发现新版本 + 下载地址"
- 网络异常 / 解析失败：退出码 `2`，日志 `【更新检查】失败：...`
- 壳可据此实现"检查更新"按钮（30s 超时已内置）

## 10. 壳接入建议 / Shell Integration Notes

1. **下拉框**：启动时跑一次 `--chipsets`，缓存到壳侧；切换方案时 `--items --chipset` 刷新勾选列表
2. **一键移植**：收集勾选 → 生成 `port` 参数 → 异步起进程 → 逐行读 stdout 追加到日志框 → 退出码 0/非0 决定按钮恢复与提示
3. **LK 面板**：目录选择 → `lk scan` → 勾选镜像 → `lk patch/verify/restore`
4. **打开输出目录**：从 stdout 的 `【CLI】输出目录：...` 行取最新路径（或直接浏览 `out/` 下最新时间戳目录）
5. **多实例**：CLI 进程本身无 UI 锁；若壳需要单实例保护，自行在壳层实现（与 GUI 的 singleton 等价）

## 11. 完整示例 / Examples

```bash
# 查询
python porttool_cli.py --chipsets
python porttool_cli.py --items --chipset "mt6572/mt6582/mt6592 kernel-3.4.67"

# 普通移植（img 输出，全默认条目，日志落盘）
python porttool_cli.py port \
  --chipset "mt6572/mt6582/mt6592 kernel-3.4.67" \
  --base-boot "D:\base\boot.img" --base-system "D:\base\system.img" \
  --donor-boot "D:\donor\boot.img" --donor-system "D:\donor\system.img" \
  --out-type img --log-file "D:\port.log"
# 成功退出码 0；产物 out/<时间戳>/boot.img + system.img

# 自定义条目：关闭 DPI 同步、开启单卡
python porttool_cli.py port --chipset "..." --no-item fit_density --item single_simcard ...

# kernel-only（只需 boot）
python porttool_cli.py port --chipset "仅移植内核 (只输出boot)" \
  --base-boot "D:\base\boot.img" --donor-boot "D:\donor\boot.img" --out-type img

# LK 去警告
python porttool_cli.py lk patch --folder "D:\readback" --patch-a --auto-backup

# 文件系统自查
python porttool_cli.py fscheck "out\20260926-14：15：32\system.img"

# 检查更新
python porttool_cli.py check-update --url "https://github.com/LJY-33684/mtk-garbage-porttool-master/raw/main/latest_version.txt"
```

## 12. 版本 / Version

- 本桥接接口随工具版本发布：当前 `1.3-beta2`
- 版本号唯一入口：`porttool/utils.py` 的 `tool_version`（`--version`、日志、zip 内 ui_print 均跟随）
