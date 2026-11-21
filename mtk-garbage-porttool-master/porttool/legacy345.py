#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT6572 / MT6582 / MT6592 —— Linux 3.4.5 跨版本移植核心模块。

把 Timmkoo T6 与 Huawei Y511 两次实战提炼出的流程固化为可复用管线。
与 3.4.67 的 portutils 相比，3.4.5 这一代有三个硬性差异，必须先处理：

  1. 内核普遍没有 SELinux
     新框架的 init 加载策略失败会 "rebooting into recovery mode" 死循环。
     → 需要 init 二进制兼容补丁 + cmdline 用 androidboot.selinux=disabled。
  2. MTK 魔改 Binder 把 waiter.private 无条件当 task_struct*
     Android 7 的 epoll 等待项 private 为 NULL → 内核空指针 panic。
     → 需要内核跳板补丁（本模块自动定位 site 与无人引用的 cave）。
  3. 旧 GPU 栈（Mali API 19）与新框架 ABI 不合
     → 保留目标机原厂 GPU 栈，做同长度改名 + shim + 转发桥。

阶段（每步都有可验证出口，不通过不进下一步）：
    S0 取证   S1 内核   S2 boot   S3 system   S4 闭包   S5 打包

接入方式：本模块被 portutils 标准管线按移植条目调用（非独立管线，输入输出
与其它方案完全一致）——configs.json 预设 'mt6572/mt6582/mt6592 kernel-3.4.5
(Android 4.x-7.x)' 置 legacy345_mode，并勾选 patch_binder_kernel /
selinux_disabled_cmdline / patch_module_order 三个条目；标准流程在 __port_boot
里分派到本模块的 KernelImage/patch_binder/reorder_mtk_module_loads 原语。
Legacy345Porter（S0~S5）保留为可独立复用的取证/编排参考与回归测试载体。
"""

import gzip
import hashlib
import json
import lzma
import os
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

MTK_MAGIC = 0x58881688
SPARSE_MAGIC = 0xED26FF3A

# 目标机硬件栈：只覆盖「与新框架 ABI 无关、纯对接内核驱动」的文件。
# 实机验证过的最小白名单（T6→Y511 成功移植所用）：
#   - GPU 用户态直连内核 ioctl 的库（libMali / gralloc），必须来自目标机
#   - 内核模块、固件、WiFi 配置、6620_launcher、按键布局
# 其余 HAL（audio/camera/sensors…）属于 Android 版本胶水层，保留 donor 版本，
# 整体覆盖 lib/hw、lib/egl 目录会把 Android 7 的 HAL 换成 4.2 实现导致必坏。
HARDWARE_PATHS = [
    'lib/libMali.so',
    'lib/hw/gralloc.mt6572.so',
    'lib/hw/gralloc.mt6582.so',
    'lib/hw/gralloc.mt6592.so',
    'lib/modules',
    'etc/firmware',
    'etc/wifi',
    'bin/6620_launcher',
    'usr/keylayout/mtk-kpd.kl',
]

# donor 里常缺、但新框架的 OMX 库会引用
OMX_FIXUPS = ['libmhalImageCodec.so', 'libmmprofile.so',
              'libstagefright_memutil.so']

# MTK 3.4.5 模块加载顺序：ccci 在 STP 前，STP core 在 combo 前
# 规范槽位用主名；wlan 按芯片有 mt6572/mt6582 两个变体，归一到同一槽位。
MTK_MODULE_ORDER = [
    'devinfo.ko', 'sec.ko', 'devapc.ko',
    'ccci_plat.ko', 'ccci.ko',
    'mtk_stp_wmt.ko', 'mtk_stp_bt.ko', 'mtk_stp_gps.ko', 'mtk_fm_drv.ko',
    'mtk_wmt_wifi.ko', 'wlan_mt6582.ko',
    'vcodec_kernel_driver.ko',
]
_WLAN = ('wlan_mt6582.ko', 'wlan_mt6572.ko')   # 同一槽位的芯片变体（主名在前）
# insmod 行：native `insmod <path>` 或 `exec -- <helper> insmod <path>`（helper 形态原样保留）
_INSMOD_RE = re.compile(r'^([ \t]*(?:(?:exec\b[^\n]*?)?insmod[ \t]+)(\S+\.ko)[^\n]*?)[ \t]*$')
_RANK = {}
for _i, _n in enumerate(MTK_MODULE_ORDER):
    _RANK[_n] = _i
for _w in _WLAN:
    _RANK[_w] = _RANK['wlan_mt6582.ko']


def _module_line_form(sample_line):
    """从一条现有 insmod 行提取「命令模板」：(head, tail)。

    head = 行首到模块 basename 之前（含 helper 与 /system/lib/modules/ 前缀），
    tail = basename(.ko) 之后到行尾。新行 = head + 模块名 + tail，
    从而原样保留 native / exec -- helper 与路径前缀，只换模块文件名。
    """
    m = _INSMOD_RE.match(sample_line)
    if not m:
        return '    insmod /system/lib/modules/', '.ko'
    path = m.group(2)                       # 例如 /system/lib/modules/wlan_mt6582.ko
    idx = sample_line.find(path)
    slash = path.rfind('/')
    base_start = idx + slash + 1            # basename（含 .ko）在原行中的起点
    head = sample_line[:base_start]
    tail = sample_line[idx + len(path):].rstrip()
    return head, tail


def rewrite_mtk_module_loads(txt):
    """重写 rc 的 MTK 模块加载段：按 MTK_MODULE_ORDER 全量重排并补全缺失项。

    - 识别现有 MTK 模块 insmod 行（native 与 `exec -- <helper>` 两种形态都认）；
    - 以 donor 自己使用的命令形态为模板，重写整段规范模块清单：
      缺失的槽位补上，已存在的槽位调整顺序；wlan 芯片变体沿用 donor 实际用的名字
      （不写死 mt6572/mt6582）；未知模块行（传感器等）原样保留、不动；
    - 插入锚点：优先原模块段所在触发器（如 on post-fs-data）之后，
      其次第一个 `on boot` 之前，最后追加文件尾；
    - 不写死任何机器专属名（helper 名/参数从现有行探测），可跨 donor 通用；
    - 幂等：已规范有序时返回原文不变。
    返回 (新文本, 规范槽位数, 补全数, 是否变更)。
    """
    lines = txt.split('\n')
    rec = []                                # (line_idx, basename)
    for i, ln in enumerate(lines):
        m = _INSMOD_RE.match(ln)
        if not m:
            continue
        base = m.group(2).rsplit('/', 1)[-1]
        if base in _RANK:
            rec.append((i, base))

    have_slots = set()
    chosen = {}                             # slot idx -> basename（donor 实际用名优先）
    for _, b in rec:
        s = _RANK[b]
        if s not in chosen:
            chosen[s] = b
        have_slots.add(s)
    missing = len(MTK_MODULE_ORDER) - len(have_slots)

    if rec:
        head, tail = _module_line_form(lines[rec[0][0]])
    else:
        head, tail = '    insmod /system/lib/modules/', '.ko'
    block = [head + chosen.get(i, MTK_MODULE_ORDER[i]) + tail
             for i in range(len(MTK_MODULE_ORDER))]

    # 删除原识别行，得到不含模块段的骨架
    rec_idx = set(i for i, _ in rec)
    kept = [ln for i, ln in enumerate(lines) if i not in rec_idx]

    # 计算插入位置（在 kept 坐标系里）
    pos = None
    if rec:
        t0 = rec[0][0] - 1
        if 0 <= t0 < len(lines) and re.match(r'^\s*on\s+\S', lines[t0]):
            removed_before = sum(1 for i in rec_idx if i < t0)
            pos = (t0 - removed_before) + 1
    if pos is None:
        for j, ln in enumerate(kept):
            if re.match(r'^on boot\b', ln):
                pos = j
                break
    if pos is None:
        for j, ln in enumerate(kept):
            if re.match(r'^\s*on\s+post-fs-data\b', ln):
                pos = j + 1
                break
    if pos is None:
        pos = len(kept)

    out = kept[:pos] + block + kept[pos:]
    new = '\n'.join(out)
    changed = new != txt
    return new, len(MTK_MODULE_ORDER), missing, changed


def _elf32_load_segments(data):
    """ELF32 的 PT_LOAD 表 (file_off, vaddr, filesz)；非 ELF32 返回 None。"""
    if len(data) < 52 or data[:4] != b'\x7fELF' or data[4] != 1:
        return None
    try:
        ph_off = struct.unpack('<I', data[0x1c:0x20])[0]
        ph_num, ph_entsize = struct.unpack('<HH', data[0x2a:0x2e])
    except struct.error:
        return None
    segs = []
    for i in range(ph_num):
        o = ph_off + i * ph_entsize
        if o + 32 > len(data):
            break
        t, off, va, _pa, fs, _ms, _fl, _al = struct.unpack('<8I', data[o:o + 32])
        if t == 1 and fs:
            segs.append((off, va, fs))
    return segs or None


def _off2va(segs, off):
    for o, v, f in segs:
        if o <= off < o + f:
            return v + (off - o)
    return None


SECFAIL_NEEDLE = b'Security failure; rebooting into recovery mode'


def classify_init_selinux_boot(init_bytes):
    """判定移植源 init 二进制的启动期 SELinux 失败路径（字节级取证，无外部依赖）。

    背景（AOSP 7.0.0_r1 / 7.1.2_r36 源码，与维护者核对一致）：
      selinux_status_from_cmdline() **只认 androidboot.selinux=permissive**，没有
      disabled 这个值；selinux_initialize() 无条件调用 selinux_android_load_policy()，
      失败即 security_failure() → "Security failure; rebooting into recovery mode"。
      → 底包内核无 selinuxfs 时，**任何 cmdline 值都救不了 stock init**；
        能开机的前提是 donor init 已被去掉该失败路径（TestMT6572 / ferhung
        mt6582_patches 一类社区补丁，典型改法是 load_policy 失败分支 return false）。

    判定两个字节特征：
      parses_cmdline     —— init 里有 'androidboot.selinux' 串（stock 的 cmdline 解析器）
      secfail_referenced —— 'Security failure; rebooting into recovery mode' 串是否
                            仍被字面量池引用（被删干净的补丁会让串变悬空/消失）

    verdict：
      'patched'  两者皆无 → boot 期无失败重启路径，安全（cmdline 仅作保险）
      'stock'    解析 cmdline 且失败消息被引用 → 无 selinuxfs 底包上必启动失败
      'partial'  只有其一 → 风险不明，提示人工确认
      'unknown'  非 ELF32 / 找不到该消息（如 4.x init，本就不含此逻辑）
    """
    out = {'parses_cmdline': None, 'secfail_present': None,
           'secfail_referenced': None, 'verdict': 'unknown'}
    if not init_bytes:
        return out
    out['parses_cmdline'] = b'androidboot.selinux' in init_bytes
    p = init_bytes.find(SECFAIL_NEEDLE)
    if p < 0:
        # 4.x init 之类根本没有这条消息；无法判定也意味着无此失败路径
        out['verdict'] = 'unknown'
        return out
    start = init_bytes.rfind(b'\x00', 0, p) + 1
    segs = _elf32_load_segments(init_bytes)
    if segs is None:
        return out
    out['secfail_present'] = True
    va = _off2va(segs, start)
    if va is None:
        return out
    out['secfail_referenced'] = init_bytes.count(struct.pack('<I', va)) > 0
    if out['parses_cmdline'] and out['secfail_referenced']:
        out['verdict'] = 'stock'
    elif not out['parses_cmdline'] and not out['secfail_referenced']:
        out['verdict'] = 'patched'
    else:
        out['verdict'] = 'partial'
    return out


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def align(n, a):
    return (n + a - 1) // a * a


def is_sparse(p):
    try:
        with open(p, 'rb') as f:
            return struct.unpack('<I', f.read(4))[0] == SPARSE_MAGIC
    except Exception:
        return False


def elf_needed(path):
    """读 32 位 ELF 的 DT_NEEDED 列表。"""
    d = open(path, 'rb').read()
    if d[:4] != b'\x7fELF' or d[4] != 1:
        return []
    shoff = struct.unpack('<I', d[0x20:0x24])[0]
    shentsize, shnum, shstrndx = struct.unpack('<HHH', d[0x2e:0x34])
    if not shnum:
        return []
    secs = []
    for i in range(shnum):
        o = shoff + i * shentsize
        secs.append(struct.unpack('<IIIIIIIIII', d[o:o + 40]))
    strtab = secs[shstrndx]
    byname = {}
    for f in secs:
        s = strtab[4] + f[0]
        e = d.index(b'\x00', s)
        byname[d[s:e].decode('utf-8', 'replace')] = f
    if '.dynamic' not in byname or '.dynstr' not in byname:
        return []
    dy, st = byname['.dynamic'], byname['.dynstr']
    out = []
    p = dy[4]
    while p < dy[4] + dy[5]:
        tag, val = struct.unpack('<II', d[p:p + 8])
        p += 8
        if tag == 0:
            break
        if tag == 1:
            e = d.index(b'\x00', st[4] + val)
            out.append(d[st[4] + val:e].decode('utf-8', 'replace'))
    return out


class BootImage:
    """ANDROID! v0 boot/recovery（含 MTK 512 字节 ramdisk 包装）。"""

    def __init__(self, path):
        self.path = str(path)
        self.raw = Path(path).read_bytes()
        if self.raw[:8] != b'ANDROID!':
            raise ValueError('%s 不是 ANDROID! boot 镜像' % path)
        (self.ksize, self.kaddr, self.rsize, self.raddr,
         self.ssize, self.saddr, self.tags, self.page,
         self.dt_size, self.osver) = struct.unpack('<10I', self.raw[8:48])
        self.name = self.raw[48:64].split(b'\x00')[0].decode('latin-1')
        self.cmdline = self.raw[64:576].split(b'\x00')[0].decode('latin-1')
        self.sha_id = self.raw[576:608]
        self.header = self.raw[:self.page]
        off = self.page
        self.kernel = self.raw[off:off + self.ksize]
        off += align(self.ksize, self.page)
        self.ramdisk = self.raw[off:off + self.rsize]
        off += align(self.rsize, self.page)
        self.second = self.raw[off:off + self.ssize] if self.ssize else b''
        self.mtk_wrapper = None
        self.gz = self.ramdisk
        if len(self.ramdisk) > 512:
            magic, size, typ = struct.unpack('<III', self.ramdisk[:12])
            if magic == MTK_MAGIC:
                self.mtk_wrapper = self.ramdisk[:512]
                self.gz = self.ramdisk[512:512 + size]

    def entries(self):
        try:
            raw = gzip.decompress(self.gz)
        except Exception:
            raw = lzma.decompress(self.gz, format=lzma.FORMAT_XZ)
        out, pos = [], 0
        while pos + 110 <= len(raw):
            if raw[pos:pos + 6] != b'070701':
                break
            hdr = raw[pos:pos + 110]
            v = [int(hdr[6 + i * 8:14 + i * 8], 16) for i in range(13)]
            name = raw[pos + 110:pos + 110 + v[11] - 1].decode('utf-8', 'replace')
            start = align(pos + 110 + v[11], 4)
            data = raw[start:start + v[6]]
            nxt = align(start + v[6], 4)
            if name == 'TRAILER!!!':
                return out, (hdr, name, data), raw[nxt:]
            out.append([name, v, data, hdr])
            pos = nxt
        return out, None, b''

    @staticmethod
    def pack_cpio(entries, trailer=None, trailing=None):
        out = bytearray()
        for item in entries:
            name, data = item[0], item[2]
            raw_hdr = item[3] if len(item) > 3 else None
            nb = name.encode('utf-8') + b'\x00'
            reuse = False
            if raw_hdr and len(raw_hdr) == 110:
                if (int(raw_hdr[6 + 6 * 8:14 + 6 * 8], 16) == len(data) and
                        int(raw_hdr[6 + 11 * 8:14 + 11 * 8], 16) == len(nb)):
                    reuse = True
            if reuse:
                out += raw_hdr
            else:
                v = list(item[1]) if isinstance(item[1], list) else [0] * 13
                v[6] = len(data)
                v[11] = len(nb)
                out += b'070701' + ''.join('%08X' % x for x in v).encode()
            out += nb
            out += bytes(align(len(out), 4) - len(out))
            out += data
            out += bytes(align(len(out), 4) - len(out))
        if trailer:
            out += trailer[0] + trailer[1].encode() + b'\x00'
        else:
            nm = b'TRAILER!!!\x00'
            v = [0] * 13
            v[11] = len(nm)
            out += b'070701' + ''.join('%08X' % x for x in v).encode() + nm
        out += bytes(align(len(out), 4) - len(out))
        if trailing is not None:
            out += trailing
        out += bytes(align(len(out), 512) - len(out))
        return bytes(out)

    def repack(self, kernel=None, entries=None, cmdline=None, out=None,
               size=None, compress='zopfli'):
        kernel = self.kernel if kernel is None else kernel
        if entries is not None:
            raw_cpio = self.pack_cpio(entries[0], entries[1], entries[2])
            body = None
            if compress == 'zopfli':
                try:
                    import zopfli.gzip as zg
                    b = bytearray(zg.compress(raw_cpio, numiterations=15))
                    b[8] = 0
                    b[9] = 3
                    body = bytes(b)
                except ImportError:
                    body = None
            if body is None:
                body = gzip.compress(raw_cpio, 9, mtime=0)
        else:
            body = self.gz

        if self.mtk_wrapper:
            wrapper = bytearray(self.mtk_wrapper)
            struct.pack_into('<I', wrapper, 4, len(body))
            ramdisk = bytes(wrapper) + body
        else:
            ramdisk = body

        header = bytearray(self.header)
        struct.pack_into('<I', header, 8, len(kernel))
        struct.pack_into('<I', header, 16, len(ramdisk))
        if cmdline is not None:
            header[64:576] = bytes(512)
            cb = cmdline.encode() if isinstance(cmdline, str) else cmdline
            header[64:64 + len(cb)] = cb
        h = hashlib.sha1()
        for seg in (kernel, ramdisk, b''):
            h.update(seg)
            h.update(struct.pack('<I', len(seg)))
        header[576:608] = h.digest() + bytes(12)

        img = bytearray(header) + kernel
        img += bytes(align(len(img), self.page) - len(img))
        img += ramdisk
        if size:
            if len(img) > size:
                raise ValueError('镜像 %d 超过目标分区 %d' % (len(img), size))
            img += bytes(size - len(img))
        out = out or self.path
        Path(out).write_bytes(bytes(img))
        return out, len(img), hashlib.sha256(img).hexdigest()


class KernelImage:
    """MTK zImage（KERN 头 + gzip/xz 载荷）。"""

    def __init__(self, path):
        self.path = str(path)
        self.raw = Path(path).read_bytes()
        body, self.base = self.raw, 0
        if struct.unpack('<I', self.raw[:4])[0] == MTK_MAGIC:
            size = struct.unpack('<I', self.raw[4:8])[0]
            self.base = 512
            body = self.raw[512:512 + size]
        self.body = body
        self.kind = self.comp_off = self.vmlinux = None
        for pat, kind in ((b'\x1f\x8b\x08', 'gzip'), (b'\xfd7zXZ\x00', 'xz')):
            i = body.find(pat)
            while i >= 0:
                try:
                    if kind == 'gzip':
                        o = zlib.decompressobj(31)
                        v = o.decompress(body[i:]) + o.flush()
                    else:
                        v = lzma.decompress(body[i:], format=lzma.FORMAT_XZ)
                    if v.find(b'Linux version') >= 0:
                        self.kind, self.comp_off, self.vmlinux = kind, i, v
                        break
                except Exception:
                    pass
                i = body.find(pat, i + 1)
            if self.vmlinux:
                break
        if self.vmlinux is None:
            raise ValueError('%s: 找不到可解压的内核载荷' % path)
        self.base_va = 0xc0008000
        m = re.search(rb'Linux version ([0-9.]+)', self.vmlinux)
        self.version = m.group(1).decode() if m else '?'

    def has(self, needle):
        if isinstance(needle, str):
            needle = needle.encode()
        return self.vmlinux.find(needle) >= 0

    def recompress(self, vmlinux, levels=(9, 8), mems=(7, 8, 9)):
        span = len(self.body) - self.comp_off - 8
        best = None          # (level, memlevel, payload)
        for lv in levels:
            for mem in mems:
                c = zlib.compressobj(lv, zlib.DEFLATED, 31, mem)
                gz = c.compress(vmlinux) + c.flush()
                if len(gz) <= span and (best is None or len(gz) < len(best[2])):
                    best = (lv, mem, gz)
        if best is None:
            raise ValueError('补丁后内核压不进原压缩跨度')
        lv, mem, gz = best
        pad = span - len(gz)
        if pad:
            gz = bytearray(gz)
            gz[3] |= 0x08          # Linux 3.4 的 gunzip 只跳 FNAME
            gz = bytes(gz[:10]) + b'P' * (pad - 1) + b'\x00' + bytes(gz[10:])
        return gz, lv, mem, pad

    def rebuild(self, vmlinux, out):
        gz, lv, mem, pad = self.recompress(vmlinux)
        img = bytearray(self.raw[:self.base + self.comp_off])
        img += gz
        img += self.raw[self.base + self.comp_off + len(gz):]
        Path(out).write_bytes(bytes(img))
        return out, lv, mem, pad


def find_cave(vmlinux, need=24, lo=None, hi=None, base=0xc0008000):
    """找无人引用的全零区：字面量与 B/BL 目标都不落入。"""
    n = len(vmlinux)
    lits, branches = set(), set()
    for off in range(0, n - 4, 4):
        w = struct.unpack_from('<I', vmlinux, off)[0]
        if base <= w < base + n:
            lits.add(w)
        if (w & 0x0F000000) in (0x0A000000, 0x0B000000):
            imm = w & 0x00FFFFFF
            if imm & 0x00800000:
                imm -= 0x01000000
            branches.add(base + off + 8 + (imm << 2))
    i = lo or 0
    end = min(hi or n, n)
    while i < end:
        if vmlinux[i] == 0:
            j = i
            while j < n and vmlinux[j] == 0:
                j += 1
            if j - i >= need and i % 4 == 0:
                va = base + i
                if not any(va <= v < va + need for v in lits) and \
                        not any(va <= v < va + need for v in branches):
                    return i, j - i
            i = j
        else:
            i += 1
    return None


def patch_binder(kimg, out):
    """MTK Binder waiter.private NULL 守卫。找到特征就补，找不到返回 None。"""
    v = bytearray(kimg.vmlinux)
    base = kimg.base_va
    needle = bytes.fromhex('003094e5')
    cands, pos = [], v.find(needle)
    while pos >= 0:
        w = bytes(v[pos:pos + 16])
        if b'\x80\xc0\x0b\xe5' in w and bytes.fromhex('020053e3') in w:
            cands.append(pos)
        pos = v.find(needle, pos + 1)
    if not cands:
        return None
    site = cands[0]
    cave = find_cave(bytes(v), 24, lo=0x200000, hi=len(v) - 0x1000, base=base)
    if cave is None:
        return None
    cave_off, cave_len = cave

    def branch(src_va, dst_va, cond=0xe):
        off = dst_va - (src_va + 8)
        if off % 4 or not (-(1 << 25) <= off < (1 << 25)):
            raise ValueError('分支超出范围')
        return struct.pack('<I', (cond << 28) | 0x0A000000 | ((off >> 2) & 0xFFFFFF))

    site_va, cave_va = base + site, base + cave_off
    stub = bytes.fromhex('80c00be5')                # str ip,[fp,#-0x80]
    stub += bytes.fromhex('000054e3')               # cmp r4,#0
    stub += branch(cave_va + 8, site_va - 0x50, 0)  # beq -> 原回调
    stub += bytes.fromhex('003094e5')               # ldr r3,[r4]
    stub += branch(cave_va + 16, site_va + 8)       # b   -> 续
    v[site:site + 4] = branch(site_va, cave_va)
    v[cave_off:cave_off + len(stub)] = stub
    out, lv, mem, pad = kimg.rebuild(bytes(v), out)
    return {'site': hex(site_va), 'cave': hex(cave_va), 'cave_len': cave_len,
            'stub': stub.hex(), 'gzip_level': lv, 'gzip_memlevel': mem,
            'fname_pad': pad, 'output': str(out)}


class Legacy345Porter:
    """3.4.5 一代（MT6572/6582/6592）跨版本移植管线。"""

    def __init__(self, base_boot, base_system, donor_boot, donor_system,
                 log=None, outdir='out', chipset='mt6572'):
        self.base_boot = str(base_boot)
        self.base_system = str(base_system)
        self.donor_boot = str(donor_boot)
        self.donor_system = str(donor_system)
        self.log = log
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.chipset = chipset
        self.report = {'chipset': chipset, 'stages': {}}

    def say(self, msg):
        if self.log is not None:
            try:
                self.log.write(msg + '\n')
                return
            except Exception:
                pass
        print(msg)

    # ---- S0 ----
    def s0_probe(self):
        self.say('【S0 取证】')
        b, d = BootImage(self.base_boot), BootImage(self.donor_boot)
        kp = self.outdir / '_probe_kernel.bin'
        kp.write_bytes(b.kernel)
        bk = KernelImage(kp)
        dp = self.outdir / '_probe_donor.bin'
        dp.write_bytes(d.kernel)
        dk = KernelImage(dp)

        info = {
            'base_kernel': bk.version, 'donor_kernel': dk.version,
            'base_page': b.page, 'donor_page': d.page,
            'base_selinuxfs': bk.has('selinuxfs'),
            'donor_selinuxfs': dk.has('selinuxfs'),
            'base_mali': bk.has('_mali_ukk'),
            'base_pvr': bk.has('pvrsrvkm'),
            'base_emmc_alias': bk.has('/emmc@%s'),
            'base_cmdline': b.cmdline, 'donor_cmdline': d.cmdline,
        }
        self.say('  底包内核 %s  donor 内核 %s' % (info['base_kernel'], info['donor_kernel']))
        self.say('  SELinux 底包=%s donor=%s' % (info['base_selinuxfs'], info['donor_selinuxfs']))
        self.say('  GPU Mali=%s PowerVR=%s' % (info['base_mali'], info['base_pvr']))
        self.say('  /emmc@ 别名支持=%s' % info['base_emmc_alias'])
        if info['base_pvr']:
            self.say('  [警告] 底包是 PowerVR，本管线只处理 Mali 栈')
        if not info['base_selinuxfs']:
            self.say('  → 无 SELinux：init 需兼容补丁，cmdline 用 selinux=disabled')
        for t in (kp, dp):
            if t.exists():
                t.unlink()
        self.report['stages']['s0'] = info
        return info

    # ---- S1 ----
    def s1_kernel(self, skip_binder=False):
        self.say('【S1 内核】')
        b = BootImage(self.base_boot)
        k = self.outdir / 'kernel.bin'
        k.write_bytes(b.kernel)
        if skip_binder:
            self.say('  已跳过')
            self.report['stages']['s1'] = {'skipped': True}
            return k
        img = KernelImage(k)
        out = self.outdir / 'kernel_fixed.bin'
        man = patch_binder(img, out)
        if man is None:
            self.say('  未发现 MTK Binder 缺陷，保持原件')
            shutil.copy(k, out)
            man = {'skipped': 'no binder defect'}
        else:
            self.say('  site %s -> cave %s（填充 %d）'
                     % (man['site'], man['cave'], man['fname_pad']))
        self.report['stages']['s1'] = man
        return out

    # ---- S2 ----
    def s2_boot(self, kernel_path, cmdline=None):
        """合成新 boot：内核来自底包（S1 产物），ramdisk 来自移植源。

        这与实机跑通的做法一致：驱动硬件的必须是底包内核，
        而 init/rc/fstab 属于新框架，只能来自移植源。
        boot 头参数（加载地址/page）沿用底包，保证底包 LK 能正常引导。
        """
        self.say('【S2 boot】')
        b = BootImage(self.base_boot)      # 头参数与分区大小基准
        d = BootImage(self.donor_boot)     # ramdisk 来源
        ents, trailer, trailing = d.entries()
        by = {e[0]: e for e in ents}
        changed = []

        for n in ('fstab.mt6572', 'fstab.mt6582', 'fstab.mt6592', 'fstab'):
            if n in by:
                by[n][2] = self._make_fstab()
                changed.append(n)
                break

        for n in ('init.mt6572.rc', 'init.mt6582.rc', 'init.mt6592.rc'):
            if n in by:
                txt = by[n][2].decode('utf-8', 'replace')
                by[n][2] = self._patch_module_load(txt).encode('utf-8')
                changed.append(n)
                break

        if 'default.prop' in by:
            props = [l for l in by['default.prop'][2].decode('utf-8', 'replace').splitlines()
                     if not l.startswith(('ro.port.build=', 'ro.port.trial='))]
            props += ['ro.port.build=legacy345-port',
                      'ro.zygote.disable_gl_preload=true',
                      'persist.sys.usb.config=mtp,adb',
                      'ro.secure=0', 'ro.adb.secure=0', 'ro.debuggable=1']
            by['default.prop'][2] = ('\n'.join(props) + '\n').encode('utf-8')
            changed.append('default.prop')

        if cmdline is None:
            sel = 'permissive' if self.report['stages'].get('s0', {}).get('base_selinuxfs') \
                else 'disabled'
            cmdline = 'no_console_suspend=1 console=null androidboot.selinux=%s' % sel

        kernel = Path(kernel_path).read_bytes()
        out = self.outdir / 'boot.img'
        _, size, sha = b.repack(kernel=kernel, entries=(ents, trailer, trailing),
                                cmdline=cmdline, out=out, size=0x600000)
        self.say('  boot.img %d 字节 sha256 %s' % (size, sha[:16]))
        self.say('  cmdline: %s' % cmdline)
        self.report['stages']['s2'] = {'output': str(out), 'sha256': sha,
                                       'cmdline': cmdline, 'changed': changed}
        return out

    @staticmethod
    def _make_fstab():
        return (b'# Android fstab - legacy345-port\n'
                b'/dev/emmc@android  /system  ext4  ro,commit=1,noauto_da_alloc  wait\n'
                b'/dev/emmc@usrdata  /data    ext4  noatime,nosuid,nodev,discard  wait,check\n'
                b'/dev/emmc@cache    /cache   ext4  noatime,nosuid,nodev,discard  wait,check\n'
                b'/devices/platform/mtk-msdc.1/mmc_host*  auto  auto  defaults  '
                b'voldmanaged=sdcard1:auto,encryptable=userdata\n')

    @staticmethod
    def _patch_module_load(txt):
        block = ('# legacy345: MTK module load order (ccci before STP, STP core first)\n'
                 'on post-fs-data\n' +
                 ''.join('    exec -- /system/bin/t6-insmod /system/lib/modules/%s\n' % m
                         for m in MTK_MODULE_ORDER) +
                 '    exec -- /system/bin/mknod /dev/devmap c 196 0\n'
                 '    chmod 0444 /dev/devmap\n'
                 '    chown root media /dev/devmap\n'
                 '    setprop persist.mtk.wcn.combo.chipid 0x6572\n')
        pat = re.compile(r'(?:^# legacy345: [^\n]*\n)?'
                         r'(?:^on post-fs-data\n)(?:    exec -- /system/bin/t6-insmod [^\n]*\n)+'
                         r'(?:    (?:exec|chmod|chown|setprop|write) [^\n]*\n)*\n*', re.M)
        txt = pat.sub('', txt)
        m = re.search(r'^on boot', txt, re.M)
        if m:
            return txt[:m.start()] + block + '\n' + txt[m.start():]
        return txt.rstrip() + '\n\n' + block

    # ---- S3 system ----
    def s3_system(self, donor_dir, base_dir):
        """把底包（目标机）硬件栈覆盖到 donor system 树上。

        donor_dir / base_dir 是上游 imgextractor 解出来的目录。
        Windows 解包会把符号链接写成 !<symlink> 标记文件（imgextractor 约定），
        复制时原样带上即可，打包后由 symlink_fix 统一转回真正符号链接。
        """
        self.say('【S3 system】')
        donor, base = Path(donor_dir), Path(base_dir)
        copied = skipped = 0
        for rel in HARDWARE_PATHS:
            src = base / rel
            if not src.exists():
                skipped += 1
                continue
            dst = donor / rel
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            copied += 1
        self.say('  换入硬件栈 %d 项，底包无此路径跳过 %d 项' % (copied, skipped))
        bridge = self._bridge_gpu(donor)
        for x in bridge:
            self.say('  ' + x)
        self.report['stages']['s3'] = {'copied': copied, 'skipped': skipped,
                                       'gpu_bridge': bridge}
        return donor

    @staticmethod
    def _bridge_gpu(sysroot):
        """同长度改名桥接：仅在 donor 自带桥接库时启用。

        libt6shim / libt6gl 是 T6 案例产物（donor system 的一部分）。
        若 donor 里没有它们，改名会把 GPU 依赖指向不存在的库，
        因此必须先检测，缺失时只做提示、不改名。
        """
        res = []
        has_shim = (sysroot / 'lib' / 'libt6shim.so').exists()
        has_gl = (sysroot / 'lib' / 'libt6gl.so').exists()
        if not has_shim and not has_gl:
            res.append('donor 无 libt6shim/libt6gl 桥接库，GPU 保持 donor 原样'
                       '（若 SurfaceFlinger 报 API mismatch，需要带桥接库的 donor）')
            return res
        mali = sysroot / 'lib' / 'libMali.so'
        if has_shim and mali.exists():
            d = mali.read_bytes()
            i = d.find(b'libbinder.so')
            if i > 0 and d[:i] + b'libt6shim.so' + d[i + 12:] != d:
                mali.write_bytes(d[:i] + b'libt6shim.so' + d[i + 12:])
                res.append('libMali: libbinder -> libt6shim')
        if has_gl:
            for g in ('gralloc.mt6572.so', 'gralloc.mt6582.so', 'gralloc.mt6592.so'):
                f = sysroot / 'lib' / 'hw' / g
                if not f.exists():
                    continue
                d = bytearray(f.read_bytes())
                j = d.find(b'libMali.so')
                if j > 0 and bytes(d[j:j + 11]) == b'libMali.so\0':
                    d[j:j + 11] = b'libt6gl.so\0'
                    f.write_bytes(bytes(d))
                    res.append('%s: libMali -> libt6gl' % g)
        return res

    # ---- S4 ----
    def s4_closure(self, sysroot):
        self.say('【S4 闭包】')
        sysroot = Path(sysroot)
        present = set()
        for dp, dn, fn in os.walk(sysroot):
            present.update(fn)
        missing = {}
        for sub in ('lib', 'lib/hw', 'lib/egl', 'vendor/lib'):
            d = sysroot / sub
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if not f.is_file() or not f.name.endswith('.so'):
                    continue
                try:
                    deps = elf_needed(str(f))
                except Exception:
                    continue
                for dep in deps:
                    if dep not in present:
                        missing.setdefault(dep, []).append(f.name)
        for dep, who in sorted(missing.items()):
            self.say('  缺 %-28s <- %s' % (dep, ', '.join(sorted(who)[:3])))
        if not missing:
            self.say('  动态库闭包完整')
        self.report['stages']['s4'] = {'unresolved': {k: sorted(set(v))
                                                      for k, v in missing.items()}}
        return missing

    # ---- S5 ----
    def s5_pack(self, sysroot, out_img, size, make_ext4fs):
        self.say('【S5 打包】')
        out_img = str(out_img)
        if os.path.exists(out_img):
            os.remove(out_img)
        cmd = [str(make_ext4fs), '-l', str(size), '-a', '/system',
               '-L', 'system', out_img, str(sysroot)]
        self.say('  ' + ' '.join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError('make_ext4fs 失败: %s' % (r.stderr or r.stdout))
        sha = sha256_file(out_img)
        self.say('  %s  %d 字节 sha256 %s'
                 % (out_img, os.path.getsize(out_img), sha[:16]))
        self.report['stages']['s5'] = {'output': out_img, 'sha256': sha,
                                       'bytes': os.path.getsize(out_img)}
        return out_img

    def write_report(self, path=None):
        p = Path(path or (self.outdir / 'port_report.json'))
        p.write_text(json.dumps(self.report, indent=2, ensure_ascii=False),
                     encoding='utf-8')
        return p
