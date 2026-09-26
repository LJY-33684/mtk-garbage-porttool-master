#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MTK 低端机移植工具 —— 命令行桥接入口 (CLI Bridge)

给其它平台（Java / C / C++ / Rust ...）的 UI 壳调用用的纯命令行接口：
参数传入（路径、方案、条目开关、输出类型），日志/结果经 stdout 传出
（可选 --log-file 同时落盘）。壳只需要启动本进程、喂参数、读输出。

接口规范详见根目录 TASK_UI_SHELL.md（Task 使用说明）。

子命令：
  port          移植（普通 / kernel-only / recovery-only，img 或 zip 输出）
  lk            LK 去警告（scan / patch / verify / restore）
  fscheck       文件系统自查（对生成的 system.img 做完整性检查）
  check-update  检查更新（读取远程 latest_version.txt 与本版本比较）

顶层查询：
  --chipsets    列出全部可用方案名（壳动态加载下拉框）
  --items       列出某方案的移植条目（配合 --chipset）
  --version     输出版本号

退出码：
  0 = 成功
  1 = 参数/校验错误（用法错误、文件缺失、非法组合）
  2 = 移植/执行失败（流程跑完但出错）
"""
import sys
import os
import json
import argparse
import copy
import subprocess
import urllib.request

# ---- 根目录定位：本文件在仓库根，porttool/ 是包目录 ----
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from porttool.configs import support_chipset_portstep          # 方案配置
from porttool.utils import portutils, tool_version, tool_author  # 移植核心 + 版本


# ============================================================
# 日志接口：stdout + 可选文件 双写（Tee），供 stdlog 使用
# 约定：所有日志行带【】前缀标记，与 GUI 日志完全一致；
#       print(..., file=log) 接口即 stdlog 协议（需 write/flush）
# ============================================================
class TeeLog:
    """同时写 stdout 与（可选）日志文件；兼容 portutils 的 stdlog 参数。"""
    def __init__(self, logfile=None):
        self.logfile = None
        if logfile:
            self.logfile = open(logfile, 'w', encoding='utf-8')
    def write(self, s):
        sys.stdout.write(s)
        if self.logfile:
            self.logfile.write(s)
    def flush(self):
        sys.stdout.flush()
        if self.logfile:
            self.logfile.flush()
    def close(self):
        if self.logfile:
            self.logfile.flush()
            self.logfile.close()
            self.logfile = None


def build_items(chipset, item_ons, item_offs, extra):
    """构造移植条目字典：deepcopy 方案配置 + 勾选拍平到顶层（_flag 语义） + 附加项。"""
    items = copy.deepcopy(support_chipset_portstep[chipset])
    # 拍平勾选：顶层键优先于 flags（与 portutils._flag 读取顺序一致）
    for k in item_ons:
        items[k] = True
    for k in item_offs:
        items[k] = False
    # 附加项（Magisk / 清理缓存）
    items['patch_magisk'] = extra.get('patch_magisk', False)
    items['magisk_apk'] = extra.get('magisk_apk', '')
    items['target_arch'] = extra.get('target_arch', 'arm')
    items['clean_base_after'] = extra.get('clean_base_after', False)
    return items


def mode_flags(chipset):
    """从方案配置取模式标记：lk / recovery / kernel_only。"""
    f = support_chipset_portstep.get(chipset, {}).get('flags', {})
    return bool(f.get('lk_patch_mode')), bool(f.get('recovery_only_mode')), bool(f.get('kernel_only_mode'))


# ============================================================
# port 子命令：移植
# ============================================================
def cmd_port(a, log):
    chipset = a.chipset
    if chipset not in support_chipset_portstep:
        print(f"【参数错误】未知方案：{chipset}（可用方案见 --chipsets）", file=log)
        return 1
    lk_mode, rec_mode, ker_mode = mode_flags(chipset)
    if lk_mode:
        print(f"【参数错误】方案「{chipset}」为 LK 修补方案，请使用 lk 子命令（lk scan/patch/verify/restore --folder ...）", file=log)
        return 1

    # ---- 移植源 ----
    if a.donor_zip:
        source_type, port_source = 'zip', a.donor_zip
        if not os.path.isfile(port_source):
            print(f"【参数错误】移植包不存在：{port_source}", file=log)
            return 1
    else:
        source_type = 'img'
        donor_sys = a.donor_system or ''
        if rec_mode or ker_mode:
            # recovery / kernel-only：移植源只有 boot/recovery，system 不参与
            port_source = (a.donor_boot, '')
        else:
            port_source = (a.donor_boot, donor_sys)
        if not os.path.isfile(a.donor_boot):
            print(f"【参数错误】移植用 boot 镜像不存在：{a.donor_boot}", file=log)
            return 1
        if not rec_mode and not ker_mode and donor_sys and not os.path.isfile(donor_sys):
            print(f"【参数错误】移植用 system 镜像不存在：{donor_sys}", file=log)
            return 1

    # ---- 底包 ----
    base_sys = a.base_system or ''
    if rec_mode or ker_mode:
        base_sys = ''  # recovery / kernel-only：底包 system 不参与
    if not os.path.isfile(a.base_boot):
        print(f"【参数错误】底包 boot 镜像不存在：{a.base_boot}", file=log)
        return 1
    if not rec_mode and not ker_mode and not base_sys:
        print("【参数错误】普通移植模式缺少底包 system（--base-system）", file=log)
        return 1
    if not rec_mode and not ker_mode and not os.path.isfile(base_sys):
        print(f"【参数错误】底包 system 镜像不存在：{base_sys}", file=log)
        return 1

    # ---- 输出类型 ----
    genimg = (a.out_type == 'img')
    # GUI 同款校验：kernel-only / recovery-only 仅支持 img；zip 输出必须 zip 源
    if (ker_mode or rec_mode) and not genimg:
        print("【参数错误】kernel-only / recovery-only 仅支持 img 输出（--out-type img）", file=log)
        return 1
    if rec_mode and source_type == 'zip':
        print("【参数错误】recovery-only 仅支持 img 移植源（不支持 --donor-zip）", file=log)
        return 1
    if not genimg and source_type != 'zip':
        print("【参数错误】输出 zip 卡刷包时必须使用 zip 移植源（--donor-zip）", file=log)
        return 1

    # ---- 条目 ----
    items = build_items(chipset, a.item or [], a.no_item or [],
                        {'patch_magisk': a.patch_magisk, 'magisk_apk': a.magisk_apk,
                         'target_arch': a.target_arch, 'clean_base_after': a.clean_base})

    print(f"【CLI】方案：{chipset}", file=log)
    print(f"【CLI】输出：{'img镜像' if genimg else 'zip卡刷包'} / 移植源：{source_type}", file=log)
    try:
        pu = portutils(items, a.base_boot, base_sys, port_source, source_type, genimg, log)
        print(f"【CLI】输出目录：{pu.outdir}", file=log)
        pu.start()
    except Exception as e:
        import traceback
        print(f"【移植异常】执行过程出错：{e}", file=log)
        print(traceback.format_exc(), file=log)
        return 2
    return 0


# ============================================================
# lk 子命令：LK 去警告（scan / patch / verify / restore）
# ============================================================
def cmd_lk(a, log):
    from porttool import LKPatch
    folder = a.folder
    if not folder or not os.path.isdir(folder):
        print(f"【参数错误】固件目录不存在：{folder}", file=log)
        return 1
    op = a.lk_op
    if op == 'scan':
        ok = LKPatch.scan_report(folder, log)
    elif op == 'patch':
        ok = LKPatch.patch_files(folder, log,
                                 patch_a=a.patch_a, patch_b=a.patch_b,
                                 auto_backup=a.auto_backup, gen_report=a.gen_report,
                                 inplace=a.inplace)
    elif op == 'verify':
        ok = LKPatch.verify_files(folder, log)
    elif op == 'restore':
        ok = LKPatch.restore_files(folder, log)
    else:
        print(f"【参数错误】未知 lk 操作：{op}", file=log)
        return 1
    return 0 if ok else 2


# ============================================================
# fscheck 子命令：文件系统自查（复用 fscheck.py）
# ============================================================
def cmd_fscheck(a, log):
    img = a.image
    if not os.path.isfile(img):
        print(f"【参数错误】镜像不存在：{img}", file=log)
        return 1
    # fscheck.py 是顶层执行脚本，走子进程；cwd 固定在仓库根保证 import porttool
    p = subprocess.run([sys.executable, os.path.join(_ROOT, 'fscheck.py'), img],
                       cwd=_ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.stdout:
        print(p.stdout, file=log)
    if p.stderr:
        print(p.stderr, file=log)
    return 0 if p.returncode == 0 else 2


# ============================================================
# check-update 子命令：远程版本比较
# latest_version.txt 格式（兼容有/无引号）：
#   latest_version=tag
#   update_url_1=GitHub下载直链  /  update_url_2=Gitee下载直链  /  update_url=通用链接
# ============================================================
def cmd_check_update(a, log):
    import re
    try:
        with urllib.request.urlopen(a.url, timeout=30) as r:
            text = r.read().decode('utf-8', 'replace')
        m_v = re.search(r'latest_version\s*=\s*"?([^"\n]+)"?', text)
        m_u = re.search(r'update_url(?:_\d+)?\s*=\s*"?([^"\n]+)"?', text)
        remote = m_v.group(1).strip() if m_v else ''
        url = m_u.group(1).strip() if m_u else ''
        print(f"【更新检查】本地版本：{tool_version}", file=log)
        print(f"【更新检查】远程版本：{remote}", file=log)
        if not remote:
            print("【更新检查】无法解析远程版本（格式：latest_version=\"tag\"）", file=log)
            return 2
        if remote == tool_version:
            print(f"【更新检查】当前已是最新版本（{tool_version}）", file=log)
        else:
            print(f"【更新检查】发现新版本：{remote}（下载地址：{url}）", file=log)
        return 0
    except Exception as e:
        print(f"【更新检查】失败：{e}", file=log)
        return 2


# ============================================================
# 顶层查询：--chipsets / --items / --version
# ============================================================
def main(argv=None):
    p = argparse.ArgumentParser(
        prog='porttool_cli',
        description='MTK 低端机移植工具命令行桥接入口（供其它平台 UI 壳调用）')
    p.add_argument('--chipsets', action='store_true', help='列出全部可用方案名')
    p.add_argument('--items', action='store_true', help='列出指定方案的全部移植条目（需 --chipset）')
    p.add_argument('--chipset', default='', help='方案名（--items 查询 / 移植时使用）')
    p.add_argument('--version', action='store_true', help='输出版本号')

    sub = p.add_subparsers(dest='cmd', metavar='{port,lk,fscheck,check-update}')

    # port
    sp = sub.add_parser('port', help='移植（普通 / kernel-only / recovery-only）')
    sp.add_argument('--chipset', required=True, help='方案名（--chipsets 可查）')
    sp.add_argument('--base-boot', required=True, help='底包 boot.img（recovery 模式为底包 recovery 镜像）')
    sp.add_argument('--base-system', default='', help='底包 system.img（recovery/kernel-only 模式可省）')
    sp.add_argument('--donor-boot', default='', help='移植用 boot.img（img 源必填；lk 模式为固件目录）')
    sp.add_argument('--donor-system', default='', help='移植用 system.img（img 源；recovery/kernel-only 可省）')
    sp.add_argument('--donor-zip', default='', help='移植用 zip 卡刷包（zip 源；输出 zip 时必填）')
    sp.add_argument('--out-type', choices=['img', 'zip'], default='img', help='输出类型（默认 img）')
    sp.add_argument('--item', action='append', default=[], metavar='KEY', help='开启移植条目（可多次）')
    sp.add_argument('--no-item', action='append', default=[], metavar='KEY', help='关闭移植条目（可多次）')
    sp.add_argument('--patch-magisk', action='store_true', help='修补 Magisk')
    sp.add_argument('--magisk-apk', default='', help='Magisk APK 路径')
    sp.add_argument('--target-arch', default='arm', help='目标架构（默认 arm）')
    sp.add_argument('--clean-base', action='store_true', help='完成后清除 base 缓存目录')
    sp.add_argument('--log-file', default='', help='额外日志文件（stdout 照常输出）')

    # lk
    sl = sub.add_parser('lk', help='LK 去警告')
    sl.add_argument('lk_op', metavar='op', choices=['scan', 'patch', 'verify', 'restore'], help='操作')
    sl.add_argument('--folder', required=True, help='固件目录（GeekFlashTool readback 目录）')
    sl.add_argument('--patch-a', action='store_true', help='patch：补丁A（去橙/红警告并追加5秒延时）')
    sl.add_argument('--patch-b', action='store_true', help='patch：补丁B（清空警告文本）')
    sl.add_argument('--auto-backup', action='store_true', help='patch：自动备份原镜像')
    sl.add_argument('--gen-report', action='store_true', help='patch：生成补丁报告')
    sl.add_argument('--inplace', action='store_true', help='patch：原地写入（默认输出到 out/）')
    sl.add_argument('--log-file', default='', help='额外日志文件')

    # fscheck
    sf = sub.add_parser('fscheck', help='文件系统自查（对 system.img 做完整性检查）')
    sf.add_argument('image', help='要检查的镜像路径（默认 out/system.img）')
    sf.add_argument('--log-file', default='', help='额外日志文件')

    # check-update
    su = sub.add_parser('check-update', help='检查更新（远程 latest_version.txt 与本版本比较）')
    su.add_argument('--url', required=True, help='latest_version.txt 的 URL')
    su.add_argument('--log-file', default='', help='额外日志文件')

    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        # argparse 内建错误（未知子命令/缺参数）默认退出码 2，统一为 1=参数错误
        if e.code == 2:
            return 1
        raise

    # ---- 顶层查询 ----
    if a.version:
        print(tool_version)
        return 0
    if a.chipsets:
        for name in support_chipset_portstep:
            print(name)
        return 0
    if a.items:
        if a.chipset not in support_chipset_portstep:
            print(f"【参数错误】未知方案：{a.chipset}", file=sys.stdout)
            return 1
        cfg = support_chipset_portstep[a.chipset]
        keys = list(cfg.get('flags', {}).keys())
        for k in keys:
            v = cfg['flags'][k]
            print('%s=%s' % (k, 'true' if v else 'false'))
        return 0

    if a.cmd is None:
        p.print_help()
        return 1

    log = TeeLog(getattr(a, 'log_file', ''))
    try:
        if a.cmd == 'port':
            rc = cmd_port(a, log)
        elif a.cmd == 'lk':
            rc = cmd_lk(a, log)
        elif a.cmd == 'fscheck':
            rc = cmd_fscheck(a, log)
        elif a.cmd == 'check-update':
            rc = cmd_check_update(a, log)
        else:
            rc = 1
    finally:
        log.close()
    return rc


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
