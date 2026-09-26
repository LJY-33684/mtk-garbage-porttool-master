# -*- coding: utf-8 -*-
"""
MTK LK 去警告补丁 —— 移植工具集成版

逻辑来自 mtk-lk-warning-patch 仓库（lk_core.py），随移植工具整体分发，
除标准库外零依赖，可直接 import 调用。

用途：一键去除 MTK lk.img / lk.bin 镜像的 Orange/Red State + dm-verity
开机警告和 5 秒启动延时。

参考: https://www.hovatek.com/forum/thread-31664.html
"""
from __future__ import annotations

import hashlib
import os
import time
import struct
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------
MAGIC = 0x58881688
EXT_MAGIC = 0x58891689
PART_SIZE = 0x100000                      # lk 分区大小 1MB

# 5 秒延时 / 警告分发函数的特征码
SIG_PRE_A10 = bytes.fromhex('7B441B681B68012B')      # Android 10 以下
SIG_A10PLUS = bytes.fromhex('7B441B681B68022B')      # Android 10 及以上
SIGS = [('Android 10 以下', SIG_PRE_A10),
        ('Android 10 及以上', SIG_A10PLUS)]

PATCH_A_LEAD = bytes.fromhex('08B5002008BD')         # push {r3,lr}; movs r0,#0; pop {r3,pc}
PREFIX = bytes.fromhex('08B5')                       # 命中处前 4 字节必须是 08B5****

# 警告文本（补丁 B 要清空的内容）
WARN_KEYS = [
    b'Orange State',
    b'Red State',
    b'Your device will boot in 5 seconds',
    b"Your device has been unlocked and can't be trusted",
    b'Your device has failed verification and may not',
    b'work properly',
]

# 内核启动参数 —— 绝对不能动
GUARD_KEYS = [
    b'androidboot.verifiedbootstate',
    b'androidboot.veritymode',
    b'androidboot.atm',
]


# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------
def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def find_all(data: bytes, needle: bytes) -> List[int]:
    out, s = [], 0
    while True:
        i = data.find(needle, s)
        if i < 0:
            return out
        out.append(i)
        s = i + 1


def cstr(data: bytes, off: int, limit: int = 96) -> str:
    if not (0 <= off < len(data)):
        return ''
    e = data.find(b'\0', off)
    if e < 0 or e - off > limit:
        e = off + limit
    return data[off:e].decode('utf-8', 'replace').replace('\n', ' ').strip()


def diff_ranges(a: bytes, b: bytes) -> List[Tuple[int, int]]:
    """返回 [a, b] 中所有不同的连续区间 (start, end_inclusive)"""
    out, s = [], None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if s is None:
                s = i
        elif s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, min(len(a), len(b)) - 1))
    return out


# ----------------------------------------------------------------------------
# 解析
# ----------------------------------------------------------------------------
def parse_header(data: bytes) -> Dict:
    if len(data) < 0x38:
        return {'valid': False, 'reason': '文件太小'}
    magic, size = struct.unpack_from('<II', data, 0)
    ext = struct.unpack_from('<I', data, 0x30)[0]
    name = data[8:20].split(b'\0')[0].decode('latin1', 'replace')
    return {
        'valid': magic == MAGIC,
        'magic': magic,
        'size': size,
        'ext_magic': ext,
        'name': name,
        'reason': '' if magic == MAGIC else 'magic 不匹配（可能不是 MTK LK 镜像）',
    }


def find_patch_a(data: bytes) -> Optional[Dict]:
    """定位警告分发函数（教程方法二的特征码）"""
    for arch, sig in SIGS:
        for sig_off in find_all(data, sig):
            pre = data[sig_off - 4:sig_off]
            if len(pre) == 4 and pre[:2] == PREFIX:
                off = sig_off - 4
                old12 = bytes(data[off:off + 12])
                if len(old12) < 12:
                    continue
                new12 = PATCH_A_LEAD + old12[6:12]
                return {
                    'offset': off,
                    'sig_offset': sig_off,
                    'arch': arch,
                    'old12': old12,
                    'new12': new12,
                }
    return None


def find_warnings(data: bytes) -> List[Tuple[int, int, str]]:
    """返回需要清空的文本区间 [(start, end_exclusive, 文本)]"""
    found = []
    for k in WARN_KEYS:
        for i in find_all(data, k):
            found.append((i, len(k)))
    if not found:
        return []
    found.sort()
    guard = data.find(GUARD_KEYS[0])
    out = []
    for n, (s, klen) in enumerate(found):
        e = found[n + 1][0] if n + 1 < len(found) else s + klen + 1
        if guard > 0:
            e = min(e, guard)
        if e > s:
            out.append((s, e, cstr(data, s)))
    return out


def scan(data: bytes) -> Dict:
    """完整扫描，供界面展示"""
    hdr = parse_header(data)
    warns = [(s, cstr(data, s)) for s, _e, _t in find_warnings(data)]
    p = find_patch_a(data)
    already = bool(find_all(data, PATCH_A_LEAD)) and p is None
    params = {}
    for g in GUARD_KEYS:
        vals = []
        for i in find_all(data, g):
            vals.append(cstr(data, i))
        params[g.decode()] = vals
    # 尾部填充
    tail_off = 0x200 + hdr.get('size', 0)
    tail = data[tail_off:] if 0 < tail_off < len(data) else b''
    tail_nonzero = sum(1 for b in tail if b != 0)
    # 适配结论：一眼判断该镜像能否打补丁
    if not hdr['valid']:
        if not any(data):
            fit, fit_ok = '不匹配（全零文件，疑似空占位槽位，无需打补丁）', False
        else:
            fit, fit_ok = '不匹配（非 MTK LK 镜像：magic 错误）', False
    elif p:
        fit, fit_ok = '适配（%s平台，可打补丁）' % p['arch'], True
    elif already:
        fit, fit_ok = '已打过补丁（无原始特征码）', True
    elif not warns:
        fit, fit_ok = '不匹配（无特征码且无警告文本，可能是空占位文件）', False
    else:
        fit, fit_ok = '不匹配（特征码未找到，该镜像不支持去延时）', False
    return {
        'size': len(data),
        'md5': md5(data),
        'header': hdr,
        'warnings': warns,
        'patch_a': p,
        'already_patched': already,
        'params': params,
        'payload_end': tail_off,
        'tail_nonzero': tail_nonzero,
        'fit': fit,
        'fit_ok': fit_ok,
    }


# ----------------------------------------------------------------------------
# 打补丁
# ----------------------------------------------------------------------------
def apply(data: bytes, patch_a: bool = True, patch_b: bool = True):
    """返回 (新数据, 日志列表[(级别, 文本)])"""
    d = bytearray(data)
    log: List[Tuple[str, str]] = []

    if patch_a:
        p = find_patch_a(d)
        if p is None:
            if find_all(d, PATCH_A_LEAD):
                log.append(('warn', '补丁A：特征码未找到，但检测到已打补丁的痕迹，跳过'))
            else:
                log.append(('warn', '补丁A：未找到 5 秒延时特征码，镜像可能不匹配，跳过'))
        else:
            d[p['offset']:p['offset'] + 12] = p['new12']
            log.append(('ok', '补丁A @0x%06X  %s -> %s  (%s)'
                        % (p['offset'], p['old12'].hex().upper(),
                           p['new12'].hex().upper(), p['arch'])))
            log.append(('info', '       该函数是橙/红状态警告分发器，改为 return 0 后'
                                '警告文本与 5 秒等待一并跳过'))
    else:
        log.append(('info', '补丁A：未启用'))

    if patch_b:
        ws = find_warnings(d)
        if not ws:
            log.append(('warn', '补丁B：未找到警告文本（可能已清空）'))
        for s, e, t in ws:
            d[s:e] = b'\x00' * (e - s)
            log.append(('ok', '补丁B @0x%06X-0x%06X (%2d 字节) 清空: %s'
                        % (s, e - 1, e - s, t[:46])))
        log.append(('info', '       内核参数 androidboot.* 未改动'))
    else:
        log.append(('info', '补丁B：未启用'))

    return bytes(d), log


# ----------------------------------------------------------------------------
# 校验
# ----------------------------------------------------------------------------
def verify(orig: bytes, new: bytes) -> Dict:
    r = {
        'size_same': len(orig) == len(new),
        'diff_ranges': diff_ranges(orig, new),
        'header_ok': orig[:0x50] == new[:0x50],
        'guards': {},
        'residual': {},
        'patch_a_ok': False,
        'md5_orig': md5(orig),
        'md5_new': md5(new),
    }
    for g in GUARD_KEYS:
        r['guards'][g.decode()] = (orig.count(g), new.count(g))
    for k in WARN_KEYS:
        r['residual'][k.decode()] = new.count(k)

    # 反汇编验证（capstone 可选）
    p = find_patch_a(orig)
    if p:
        seg = new[p['offset']:p['offset'] + 6]
        r['patch_a_ok'] = seg == PATCH_A_LEAD
        r['patch_a_offset'] = p['offset']
    return r


def disasm_patch(data: bytes, offset: int, count: int = 5) -> List[str]:
    """尝试反汇编补丁点，需要 capstone；不可用时返回空列表"""
    try:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    except ImportError:
        return []
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    out = []
    p = offset
    end = offset + 0x20
    while p < end and len(out) < count:
        got = False
        for ins in md.disasm(data[p:end], p):
            out.append('%06X  %-8s %s' % (ins.address, ins.mnemonic, ins.op_str))
            p = ins.address + ins.size
            got = True
            break
        if not got:
            p += 2
    return out


# ----------------------------------------------------------------------------
# 文件辅助
# ----------------------------------------------------------------------------
LK_NAMES = ['lk.img', 'lk2.img', 'lk.bin', 'lk2.bin',
            'lk_a.img', 'lk_b.img', 'lk_a.bin', 'lk_b.bin']

# 本次输出目录：out/<时间戳>/（点击"打补丁"时生成并固定，同一批 lk/lk2 输出到同一目录）
_OUT_TS = None


def _out_dir() -> str:
    global _OUT_TS
    if _OUT_TS is None:
        _OUT_TS = time.strftime("%Y%m%d-%H：%M：%S")
    d = os.path.join(os.getcwd(), 'out', _OUT_TS)
    os.makedirs(d, exist_ok=True)
    return d


def _rel(p: str) -> str:
    """相对 cwd 的正斜杠路径（日志展示用）"""
    return os.path.relpath(p, os.getcwd()).replace(os.sep, '/')


def detect_lk_files(folder: str) -> List[str]:
    """在目录中找出 lk / lk2 镜像（含 A/B 双槽）"""
    if not os.path.isdir(folder):
        return []
    out = []
    for n in LK_NAMES:
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            out.append(p)
    if out:
        return out
    # 退路：按前缀匹配
    for n in sorted(os.listdir(folder)):
        low = n.lower()
        if low.startswith('lk') and low.endswith(('.img', '.bin')):
            out.append(os.path.join(folder, n))
    return out


def backup_path(path: str) -> str:
    """备份统一输出到移植工具 out/<时间戳>/ 目录（与原文件分开，避免污染固件目录）"""
    base, ext = os.path.splitext(os.path.basename(path))
    return os.path.join(_out_dir(), base + '_original_backup' + ext)


def patched_path(path: str) -> str:
    """打补丁产物统一输出到移植工具 out/<时间戳>/ 目录（点击打补丁时创建）"""
    base, ext = os.path.splitext(os.path.basename(path))
    return os.path.join(_out_dir(), base + '_patched' + ext)


def read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def write_file(path: str, data: bytes) -> None:
    with open(path, 'wb') as f:
        f.write(data)


def human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return '%.1f %s' % (n, unit) if unit != 'B' else '%d B' % n
        n /= 1024.0
    return str(n)


# ----------------------------------------------------------------------------
# 移植工具集成层
# ----------------------------------------------------------------------------
def run_lk_patch(folder: str, log=None) -> bool:
    """移植工具集成入口（目录模式）：自动检测 lk/lk2 镜像 → 逐个打补丁

    复用原版 LKTool 的目录选择方式：
    - 目录中检测 lk.img / lk2.img（含 lk.bin / A/B 槽等，见 detect_lk_files）
    - 每个镜像输出 <原名>_patched.img 到移植工具 out/<时间戳>/ 目录，备份 <原名>_original_backup.img 也在同一目录
    - A/B 双槽（lk + lk2）一起处理

    日志遵循移植工具【】风格；返回 True=全部成功，False=失败/不适配。
    """
    import sys
    from pathlib import Path
    std = log if log is not None else sys.stdout

    print("【LK去警告】开始处理固件目录中的 LK 镜像...", file=std)
    files = detect_lk_files(folder)
    if not files:
        print(f"  ! 目录中未检测到 LK 镜像：{folder}", file=std)
        print("  （查找：lk.img / lk2.img / lk.bin / lk2.bin / lk_a / lk_b 等）", file=std)
        print("【LK去警告】无镜像可处理，流程结束", file=std)
        return False
    print(f"  ├─ 检测到 {len(files)} 个 LK 镜像：", file=std)
    for f in files:
        print(f"  │   - {f}", file=std)

    ok_all = True
    for lk_path in files:
        print(f"\n【LK去警告】处理：{lk_path}", file=std)
        try:
            data = read_file(lk_path)
        except Exception as e:
            print(f"  ! 读取失败：{e}", file=std)
            ok_all = False
            continue

        info = scan(data)

        # 打印扫描信息
        print(f"  ├─ 文件大小：{human_size(len(data))}", file=std)
        print(f"  ├─ MD5：{info['md5']}", file=std)
        hdr = info['header']
        if hdr['valid']:
            print(f"  ├─ LK头：magic=0x{hdr['magic']:08X} name={hdr['name']!r} "
                  f"size={hdr['size']}（0x{hdr['size']:X}）", file=std)
        print(f"  └─ 适配结论：{info['fit']}", file=std)

        if not info['fit_ok']:
            print(f"【LK去警告】{os.path.basename(lk_path)} 不适配，已跳过（fail-safe）", file=std)
            ok_all = False
            continue

        p = info['patch_a']
        if p:
            print(f"  ├─ 警告分发器：@0x{p['offset']:06X}（{p['arch']}）", file=std)
            print(f"  │    原 12 字节：{p['old12'].hex().upper()}", file=std)
            print(f"  │    改 12 字节：{p['new12'].hex().upper()}", file=std)
        if info['warnings']:
            print(f"  ├─ 待清空警告文本：{len(info['warnings'])} 处", file=std)

        new_data, logs = apply(data)
        for lv, text in logs:
            mark = '✓' if lv == 'ok' else ('•' if lv == 'info' else '!')
            print(f"  {mark} {text}", file=std)

        # 输出补丁结果到 out/<时间戳>/（<原名>_patched.img，与普通移植输出目录一致）
        out_img = patched_path(lk_path)
        try:
            write_file(out_img, new_data)
        except Exception as e:
            print(f"  ! 写入输出失败：{e}", file=std)
            ok_all = False
            continue

        # 备份原镜像（放 out/<时间戳>/，供救砖/还原）
        backup = backup_path(lk_path)
        if not Path(backup).exists():
            try:
                write_file(backup, data)
                print(f"  ├─ 已备份原镜像：{_rel(backup)}", file=std)
            except Exception as e:
                print(f"  ! 备份失败（不影响补丁输出）：{e}", file=std)

        # 校验
        v = verify(data, new_data)
        print(f"  ├─ 校验：大小一致={v['size_same']} 头部未动={v['header_ok']} "
              f"补丁A生效={v['patch_a_ok']}", file=std)
        if v['diff_ranges']:
            print(f"  ├─ 差异区间：{len(v['diff_ranges'])} 处（仅补丁点/警告文本，未动内核参数）", file=std)
        for key, vals in info['params'].items():
            if vals:
                print(f"  ├─ 保留内核参数：{key} = {vals}", file=std)
        print(f"  └─ 输出：{_rel(out_img)}", file=std)

    print("\n【LK去警告】处理完成！", file=std)
    print("【提醒】LK 为 A/B 双槽（lk + lk2），两个都要刷，否则设备可能从另一槽启动，警告依旧存在！", file=std)
    return ok_all


# ----------------------------------------------------------------------------
# 移植工具集成层 —— 原版 LKTool 全功能（除清空日志）
# ----------------------------------------------------------------------------
def _pick(folder: str, selected=None) -> List[str]:
    """返回要处理的镜像列表：selected 传入时用之，否则检测目录内全部"""
    files = selected if selected is not None else detect_lk_files(folder)
    return [f for f in files if f] if files else []


def scan_report(folder: str, log=None, selected=None) -> bool:
    """【扫描】只检测不打补丁（对齐原版 do_scan）。返回 True=完成（含不适配）"""
    import sys
    std = log if log is not None else sys.stdout
    files = _pick(folder, selected)
    if not files:
        print("【LK扫描】目录中未检测到 LK 镜像，请先选择固件目录", file=std)
        return False
    print(f"【LK扫描】共 {len(files)} 个镜像，开始扫描（只检测，不打补丁）...", file=std)
    for p in files:
        name = os.path.basename(p)
        try:
            data = read_file(p)
        except OSError as e:
            print(f"  ! 读取失败 {name}: {e}", file=std)
            continue
        s = scan(data)
        print(f"  【{name}】 {human_size(s['size'])}   MD5 {s['md5']}", file=std)
        print(f"    适配状态: {s['fit']}", file=std)
        h = s['header']
        if h['valid']:
            print(f"    头部: magic 0x{h['magic']:08X} · ext 0x{h['ext_magic']:08X} · "
                  f"size 0x{h['size']:X} · name {h['name']!r}", file=std)
        else:
            print(f"    头部: 异常 —— {h['reason']}", file=std)
        print(f"    负载结束于 0x{s['payload_end']:06X}，其后 {s['tail_nonzero']} 个非零字节", file=std)
        if s['warnings']:
            print(f"    警告文本 {len(s['warnings'])} 段:", file=std)
            for off, t in s['warnings']:
                print(f"      @0x{off:06X}  {t}", file=std)
        else:
            print(f"    警告文本: 无（可能已清空）", file=std)
        if s['patch_a']:
            pa = s['patch_a']
            print(f"    补丁点: @0x{pa['offset']:06X}   {pa['arch']}", file=std)
            print(f"            {pa['old12'].hex().upper()}  ->  {pa['new12'].hex().upper()}", file=std)
        elif s['already_patched']:
            print(f"    补丁点: 未找到（检测到已打补丁的痕迹）", file=std)
        else:
            print(f"    补丁点: 未找到 —— 镜像可能不匹配，请勿打补丁", file=std)
        for k, vals in s['params'].items():
            if vals:
                print(f"    内核参数: {k}  {len(vals)} 项（不会被改动）", file=std)
        print('', file=std)
    print("【LK扫描】扫描完成", file=std)
    return True


def patch_files(folder: str, log=None, selected=None,
                patch_a: bool = True, patch_b: bool = True,
                auto_backup: bool = True, gen_report: bool = True,
                inplace: bool = False):
    """【打补丁】对齐原版 do_patch（含备份/校验/覆盖选项）。

    返回 (outputs, blocked, problems)：成功输出列表 / 不匹配被拦截列表 / 处理异常列表。
    """
    import sys
    std = log if log is not None else sys.stdout
    files = _pick(folder, selected)
    _out_dir()  # 点击打补丁即创建 out/<时间戳>/ 输出目录
    if not files:
        print("【LK打补丁】目录中未检测到 LK 镜像，请先选择固件目录并勾选要处理的镜像", file=std)
        return [], [], []
    print(f"【LK打补丁】开始...  补丁A={'开' if patch_a else '关'}  补丁B={'开' if patch_b else '关'}  "
          f"自动备份={'开' if auto_backup else '关'}  生成校验报告={'开' if gen_report else '关'}  "
          f"覆盖原文件={'是' if inplace else '否'}", file=std)
    outputs, problems, blocked = [], [], []
    for idx, p in enumerate(files, 1):
        name = os.path.basename(p)
        print(f"  [{idx}/{len(files)}] {name}", file=std)
        try:
            data = read_file(p)
        except OSError as e:
            print(f"    ! 读取失败: {e}", file=std)
            problems.append(name)
            continue
        # 不匹配镜像直接拦截：不备份、不打补丁、不输出
        s = scan(data)
        if not s['fit_ok']:
            print(f"    已拦截: {s['fit']}", file=std)
            blocked.append('%s（%s）' % (name, s['fit']))
            continue
        print(f"    原始 MD5 : {md5(data)}", file=std)
        # 备份
        bak = backup_path(p)
        if auto_backup and not os.path.exists(bak):
            try:
                write_file(bak, data)
                print(f"    已备份   : {_rel(bak)}", file=std)
            except OSError as e:
                print(f"    备份失败: {e}", file=std)
                problems.append(name)
                continue
        elif os.path.exists(bak):
            print(f"    备份已存在: {_rel(bak)}", file=std)
        # 打补丁
        new, logs = apply(data, patch_a=patch_a, patch_b=patch_b)
        for lvl, txt in logs:
            print(f"    {txt}", file=std)
        if new == data:
            print(f"    文件内容未发生变化（可能已经是补丁状态）", file=std)
        out = p if inplace else patched_path(p)
        try:
            write_file(out, new)
        except OSError as e:
            print(f"    写出失败: {e}", file=std)
            problems.append(name)
            continue
        print(f"    新   MD5 : {md5(new)}", file=std)
        print(f"    输出     : {_rel(out)}", file=std)
        outputs.append(out)
        # 校验报告
        if gen_report:
            v = verify(data, new)
            total = sum(e - b + 1 for b, e in v['diff_ranges'])
            guard_ok = all(a == c for a, c in v['guards'].values())
            residual = sum(v['residual'].values())
            good = guard_ok and residual == 0 and v['header_ok']
            print(f"    校验: 差异 {total} 字节 / {len(v['diff_ranges'])} 段 · 内核参数"
                  f"{'完好' if guard_ok else '异常'} · 警告残留 {residual} · 头部"
                  f"{'未变' if v['header_ok'] else '异常'}", file=std)
            if v.get('patch_a_offset') is not None:
                for line in disasm_patch(new, v['patch_a_offset'], 3):
                    print(f"      {line}", file=std)
                if not v['patch_a_ok']:
                    print(f"      !! 补丁点反汇编与预期不符", file=std)
                    problems.append(name)
    # 汇总
    print(f"  ---- 汇总 ----", file=std)
    print(f"  成功输出 {len(outputs)} 个文件", file=std)
    if blocked:
        print(f"  已拦截 {len(blocked)} 个不匹配镜像（未做任何处理）:", file=std)
        for b in blocked:
            print(f"    - {b}", file=std)
    if problems:
        print(f"  以下文件有问题: {', '.join(problems)}", file=std)
    print(f"  刷入提醒：lk 与 lk2 是 A/B 双槽，两个都要刷；只刷一个的话设备可能从另一槽启动，警告依旧存在。", file=std)
    return outputs, blocked, problems


def verify_files(folder: str, log=None, selected=None) -> bool:
    """【校验】原始备份 vs 当前输出（对齐原版 do_verify）。返回 True=完成"""
    import sys
    std = log if log is not None else sys.stdout
    files = _pick(folder, selected)
    if not files:
        print("【LK校验】目录中未检测到 LK 镜像，请先选择固件目录并勾选要处理的镜像", file=std)
        return False
    print("【LK校验】原始备份 vs 当前输出...", file=std)
    for p in files:
        name = os.path.basename(p)
        bak = backup_path(p)
        if not os.path.isfile(bak):
            try:
                s = scan(read_file(p))
                if not s['fit_ok']:
                    print(f"  {name}: 不匹配镜像，已拦截未处理 —— {s['fit']}（因此无备份、无补丁输出可对比）", file=std)
                    continue
            except OSError:
                pass
            print(f"  {name}: 没有备份 {os.path.basename(bak)}，无法对比", file=std)
            continue
        cand = [c for c in (patched_path(p), p) if os.path.isfile(c)]
        if not cand:
            print(f"  {name}: 没有可校验的输出文件", file=std)
            continue
        out = cand[0]
        o, n = read_file(bak), read_file(out)
        v = verify(o, n)
        print(f"  【{os.path.basename(out)}】 vs {os.path.basename(bak)}", file=std)
        print(f"    大小一致 : {'是' if v['size_same'] else '否'}", file=std)
        total = sum(e - b + 1 for b, e in v['diff_ranges'])
        print(f"    差异     : {total} 字节 / {len(v['diff_ranges'])} 段", file=std)
        for b, e in v['diff_ranges']:
            print(f"       0x{b:06X}-0x{e:06X}  ({e - b + 1} 字节)", file=std)
        for k, (a, c) in v['guards'].items():
            print(f"    内核参数 {k}  {a} -> {c}  {'OK' if a == c else '异常'}", file=std)
        res = sum(v['residual'].values())
        print(f"    警告文本残留: {res}  {'OK' if res == 0 else '仍有残留'}", file=std)
        print(f"    头部未变 : {'是' if v['header_ok'] else '否'}", file=std)
        print(f"    MD5 原始 : {v['md5_orig']}", file=std)
        print(f"    MD5 补丁 : {v['md5_new']}", file=std)
        if v.get('patch_a_offset') is not None:
            for line in disasm_patch(n, v['patch_a_offset'], 3):
                print(f"      {line}", file=std)
        print('', file=std)
    print("【LK校验】校验完成", file=std)
    return True


def restore_files(folder: str, log=None, selected=None) -> bool:
    """【还原】用备份覆盖原文件（对齐原版 do_restore）。返回 True=完成"""
    import sys
    std = log if log is not None else sys.stdout
    files = _pick(folder, selected)
    if not files:
        print("【LK还原】目录中未检测到 LK 镜像，请先选择固件目录并勾选要处理的镜像", file=std)
        return False
    todo = [(p, backup_path(p)) for p in files if os.path.isfile(backup_path(p))]
    if not todo:
        print("【LK还原】没有找到备份文件，无需还原", file=std)
        return False
    print("【LK还原】用备份覆盖原文件...", file=std)
    for p, bak in todo:
        try:
            write_file(p, read_file(bak))
            print(f"  已还原 {os.path.basename(p)}  <-  {os.path.basename(bak)}", file=std)
        except OSError as e:
            print(f"  还原失败 {os.path.basename(p)}: {e}", file=std)
    print("【LK还原】还原完成", file=std)
    return True
