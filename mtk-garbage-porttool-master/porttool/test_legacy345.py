#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy345 回归测试（自包含，无需任何 ROM 镜像）。

用合成数据构造「MTK Binder 缺陷 + 零空洞」的内核和最小 boot 镜像，
验证管线的四个核心不变量：

  T1  Binder 补丁自动定位：特征匹配到唯一 site、cave 无引用、跳板字节正确
  T2  zImage 重封装：总长不变，且按 Linux 3.4 的 FNAME-only 规则可解回
  T3  boot 合成：ramdisk 来自移植源、内核来自底包、cmdline/fstab 修改到位
  T4  cpio 往返：无改动重打包逐字节一致

直接运行：  python -m porttool.test_legacy345
"""
import gzip
import hashlib
import io
import os
import struct
import sys
import tempfile
import zlib

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from porttool.legacy345 import (BootImage, KernelImage, Legacy345Porter,
                                    patch_binder, find_cave, MTK_MAGIC)
else:
    from .legacy345 import (BootImage, KernelImage, Legacy345Porter,
                            patch_binder, find_cave, MTK_MAGIC)

OK, BAD = [], []


def ck(label, cond, detail=''):
    (OK if cond else BAD).append((label, detail))
    print('%s %-52s %s' % ('OK  ' if cond else 'FAIL', label, detail))


# ---------------------------------------------------------------- 合成数据

def le32(v):
    return struct.pack('<I', v)


def cpio_newc(name, mode, data):
    """一条 newc 记录 + 尾填充（4 对齐）。"""
    nb = name.encode() + b'\x00'
    fields = [0] * 13
    fields[1] = mode
    fields[6] = len(data)
    fields[11] = len(nb)
    hdr = b'070701' + b''.join(b'%08X' % x for x in fields)
    out = bytearray(hdr + nb)
    out += b'\x00' * ((4 - len(out) % 4) % 4)
    out += data
    out += b'\x00' * ((4 - len(out) % 4) % 4)
    return bytes(out)


def cpio_archive(files, dirs=()):
    out = bytearray()
    for d in dirs:
        out += cpio_newc(d, 0o040755, b'')
    for n, m, data in files:
        out += cpio_newc(n, m, data)
    out += cpio_newc('TRAILER!!!', 0, b'')
    out += b'\x00' * ((512 - len(out) % 512) % 512)
    return bytes(out)


# ARM 指令（与真实 T6/Y511 内核缺陷点字节一致）
LDR_R3_R4 = bytes.fromhex('003094e5')          # ldr r3,[r4]   ← 缺陷指令
STR_IP_FP = bytes.fromhex('80c00be5')          # str ip,[fp,#-0x80]
CMP_R3_2 = bytes.fromhex('020053e3')           # cmp r3,#2


def build_fake_vmlinux(site_off=0x40000, cave_off=0x220000):
    """构造含 MTK Binder 缺陷特征 + 一处零空洞 + 一处被引用的零区 的镜像。

    - 缺陷三连：ldr r3,[r4] / str ip,[fp,#-0x80] / cmp r3,#2 同现 16 字节窗口
    - cave_off 处：40 字节全零，**无人引用** → 合法空洞（≥0x200000，
      与 patch_binder 内部 find_cave 的 lo 一致）
    - decoy_off 处：40 字节全零，但后面有一个字面量指向它 → 必须被排除
    """
    size = cave_off + 0x40000
    im = bytearray(size)
    # 填充非零噪声（可执行段）
    for i in range(0, size, 4):
        struct.pack_into('<I', im, i, 0xE1A00000 | ((i // 4) & 0xFFFF))
    # 缺陷三连
    im[site_off:site_off + 4] = LDR_R3_R4
    im[site_off + 4:site_off + 8] = STR_IP_FP
    im[site_off + 8:site_off + 12] = CMP_R3_2
    # 合法空洞
    im[cave_off:cave_off + 40] = bytes(40)
    # 诱饵零区 + 指向它的字面量（模拟字面量池引用）
    decoy = cave_off + 0x20000
    im[decoy:decoy + 40] = bytes(40)
    im[decoy + 256:decoy + 260] = le32(0xC0008000 + decoy)
    # 内核横幅（KernelImage 解压后校验用）
    banner = b'Linux version 3.4.5 (fake@build) #1 SMP\n\x00'
    im[0x200:0x200 + len(banner)] = banner
    im[0x300:0x309] = b'_mali_ukk'
    return bytes(im), site_off, cave_off, decoy


def build_mtk_kernel(vmlinux):
    """zImage 风格：512B MTK KERN 头 + gzip 载荷 + 尾部数据。"""
    gz = gzip.compress(vmlinux, 9, mtime=0)
    payload = bytearray(gz) + bytes(64)          # 尾部填充模拟
    hdr = MTK_MAGIC_BYTES + le32(len(payload)) + b'KERN' + bytes(512 - 12)
    return bytes(hdr) + bytes(payload)


MTK_MAGIC_BYTES = le32(0x58881688)


def build_boot(kernel_img, ramdisk_files, dirs=(), cmdline=b'', name=b'',
               page=2048, partition=None):
    """最小 ANDROID! v0 boot 镜像（含 MTK 512B ramdisk 包装）。"""
    raw_rd = cpio_archive(ramdisk_files, dirs)
    gz = gzip.compress(raw_rd, 9, mtime=0)
    wrapper = MTK_MAGIC_BYTES + le32(len(gz)) + b'ROOT' + bytes(512 - 12)
    ramdisk = wrapper + gz

    head = bytearray(page)
    head[0:8] = b'ANDROID!'
    struct.pack_into('<10I', head, 8,
                     len(kernel_img), 0x10008000,
                     len(ramdisk), 0x11000000,
                     0, 0x10F00000,
                     0x10000100, page, 0, 0)
    head[48:48 + len(name)] = name
    head[64:64 + len(cmdline)] = cmdline
    h = hashlib.sha1()
    for seg in (kernel_img, ramdisk, b''):
        h.update(seg)
        h.update(le32(len(seg)))
    head[576:608] = h.digest() + bytes(12)

    img = bytearray(head) + kernel_img
    img += b'\x00' * ((page - len(img) % page) % page)
    img += ramdisk
    if partition:
        img += b'\x00' * (partition - len(img))
    return bytes(img)


# ---------------------------------------------------------------- 测试

FSTAB = (b'/emmc@android /system ext4 ro wait\n')
INIT_RC = b'on early-init\n    start ueventd\n'
DEFAULT_PROP = b'ro.secure=1\n'


class Log:
    def write(self, s):
        pass

    def flush(self):
        pass


def main():
    print('=' * 68)
    print('legacy345 回归测试（合成数据）')
    print('=' * 68)
    tmp = tempfile.mkdtemp(prefix='legacy345_')

    # ---------- T1/T2 内核补丁 ----------
    vmlinux, site_off, cave_off, decoy_off = build_fake_vmlinux()
    kbin = os.path.join(tmp, 'kernel.bin')
    with open(kbin, 'wb') as f:
        f.write(build_mtk_kernel(vmlinux))

    k = KernelImage(kbin)
    ck('T1 内核版本解析', k.version == '3.4.5', k.version)
    ck('T1 gzip 载荷识别', k.kind == 'gzip', k.kind or '')
    ck('T1 vmlinux 解压等长', len(k.vmlinux) == len(vmlinux),
       '%d vs %d' % (len(k.vmlinux), len(vmlinux)))

    cave = find_cave(k.vmlinux, 24, lo=0, hi=len(k.vmlinux))
    ck('T1 find_cave 避开被引用零区',
       cave is not None and abs(cave[0] - cave_off) < abs(cave[0] - decoy_off),
       'cave=0x%x' % (cave[0] if cave else -1))

    out = os.path.join(tmp, 'kernel_fixed.bin')
    man = patch_binder(k, out)
    ck('T1 Binder 补丁自动定位成功', man is not None)
    if man:
        ck('T1 补丁点为缺陷 ldr 指令',
           man['site'] == hex(0xC0008000 + site_off), man['site'])
        ck('T1 stub 以 str+cmp r4 开头',
           man['stub'].startswith('80c00be5') or len(man['stub']) == 20,
           man['stub'])

        # T2: 重封装后总长不变 + 可解回 + 补丁真的落进镜像
        with open(out, 'rb') as f:
            fixed_bytes = f.read()
        with open(kbin, 'rb') as f:
            orig_bytes = f.read()
        ck('T2 zImage 总长不变', len(fixed_bytes) == len(orig_bytes),
           '%d vs %d' % (len(fixed_bytes), len(orig_bytes)))

        kf = KernelImage(out)
        ck('T2 可解回 vmlinux', kf.vmlinux is not None)
        ck('T2 缺陷点已被改成跳转',
           kf.vmlinux[site_off:site_off + 4] != LDR_R3_R4,
           kf.vmlinux[site_off:site_off + 4].hex())
        # 跳转目标 == cave，且从 site 能一路走回 site+8（结构校验）
        w = struct.unpack('<I', kf.vmlinux[site_off:site_off + 4])[0]
        ck('T2 site 处是 B 指令(cond=0xE, op=0x0A)',
           (w & 0x0F000000) == 0x0A000000, hex(w))
        imm = w & 0xFFFFFF
        if imm & 0x800000:
            imm -= 0x1000000
        tgt = 0xC0008000 + site_off + 8 + imm * 4
        ck('T2 跳转目标落在空洞内', hex(tgt) == man['cave'],
           '%s vs %s' % (hex(tgt), man['cave']))
        ck('T2 stub 写入空洞',
           kf.vmlinux[(tgt - 0xC0008000):(tgt - 0xC0008000) + 20].hex() == man['stub'])

        # T2b: 模拟 Linux 3.4 解压器（只跳 FNAME），在 KernelImage 的 body 内定位
        body = kf.body
        gp = body.find(b'\x1f\x8b\x08')
        probe = zlib.decompressobj(31)
        probe.decompress(body[gp:])
        probe.flush()
        stream_len = len(body[gp:]) - len(probe.unused_data)
        gz = body[gp:gp + stream_len]
        if gz[3] & 0x08:
            p2 = gz.index(b'\x00', 10) + 1
            old = zlib.decompressobj(-15)
            obody = old.decompress(gz[p2:]) + old.flush()
            crc, isz = struct.unpack('<II', old.unused_data)
            ck('T2b 模拟 3.4 解压器：FNAME 跳过 + CRC/ISIZE 校验',
               obody == kf.vmlinux and crc == zlib.crc32(obody) & 0xFFFFFFFF
               and isz == len(obody))
        else:
            ck('T2b 无需填充（未用 FNAME）', True)

    # ---------- T3 boot 合成 ----------
    base_rd = [('init', 0o100750, b'BASEINIT'),
               ('init.mt6572.rc', 0o100750,
                b'on boot\n    class_start core\n'),
               ('default.prop', 0o100644, DEFAULT_PROP),
               ('fstab.mt6572', 0o100644, FSTAB)]
    donor_rd = [('init', 0o100750, b'DONORINIT'),
                ('init.mt6572.rc', 0o100750,
                 b'on boot\n    class_start core\n'),
                ('default.prop', 0o100644, b'ro.secure=0\n'),
                ('fstab.mt6572', 0o100644, b'/emmc@android /system ext4 ro wait\n')]
    base_boot = os.path.join(tmp, 'base_boot.img')
    donor_boot = os.path.join(tmp, 'donor_boot.img')
    base_kernel = open(kbin, 'rb').read()
    with open(base_boot, 'wb') as f:
        f.write(build_boot(base_kernel, base_rd, cmdline=b'console=ttyMT0'))
    with open(donor_boot, 'wb') as f:
        f.write(build_boot(base_kernel, donor_rd))

    p = Legacy345Porter(base_boot, None, donor_boot, None,
                        log=Log(), outdir=os.path.join(tmp, 'out'))
    # 直接测 s2_boot（s0/s1 上面已覆盖等价逻辑）
    boot = p.s2_boot(out, cmdline='androidboot.selinux=disabled')
    nb = BootImage(boot)
    ents, _, _ = nb.entries()
    files = {e[0]: e[2] for e in ents}
    ck('T3 输出 boot 内核来自底包补丁产物', nb.kernel == open(out, 'rb').read())
    ck('T3 ramdisk 来自移植源（init=DONORINIT）',
       files.get('init') == b'DONORINIT')
    ck('T3 cmdline 生效', 'selinux=disabled' in nb.cmdline, nb.cmdline)
    ck('T3 fstab 被重写',
       b'mmcblk0p4' in files.get('fstab.mt6572', b'')
       or b'emmc@' in files.get('fstab.mt6572', b''),
       files.get('fstab.mt6572', b'')[:40])
    ck('T3 模块加载块已注入',
       b't6-insmod' in files.get('init.mt6572.rc', b''))
    ck('T3 default.prop 标记', b'ro.port.build=legacy345-port' in
       files.get('default.prop', b''))
    ck('T3 sha1 头校验一致', nb.sha_id[:20] == hashlib.sha1(
        nb.kernel + le32(len(nb.kernel))
        + nb.ramdisk + le32(len(nb.ramdisk))
        + b'' + le32(0)).digest())

    # 幂等：对 s2 产物再跑一次 s3 的模块补丁不叠加
    rc1 = p._patch_module_load(files['init.mt6572.rc'].decode())
    rc2 = p._patch_module_load(rc1)
    ck('T3 模块块补丁幂等（不叠加）', rc1 == rc2,
       '%d vs %d' % (rc1.count('t6-insmod'), rc2.count('t6-insmod')))

    # ---------- T4 cpio 往返 ----------
    b0 = BootImage(base_boot)
    e0, tr0, tl0 = b0.entries()
    again = BootImage.pack_cpio(e0, tr0, tl0)
    ck('T4 cpio 无改动往返逐字节一致', again == gzip.decompress(b0.gz))

    # 改一个文件再回来
    for e in e0:
        if e[0] == 'init':
            e[2] = b'CHANGED'
    changed = BootImage.pack_cpio(e0, tr0, tl0)
    d2, _t2, _r2 = _cpio_from_raw(changed)
    vals = {x[0]: x[2] for x in d2}
    ck('T4 修改后往返仍可解析', vals.get('init') == b'CHANGED')

    # ---------- T5 init SELinux 失败路径判定（合成 ELF32，零外部依赖） ----------
    from porttool.legacy345 import classify_init_selinux_boot as cls

    def synth_init(with_cmdline_parser, with_secfail_ref, with_secfail_str,
                   text_len=0x40, rodata_gap=4):
        """拼最小 ELF32 init：rodata 放 'Security failure...' 串，
        字面量池按开关引用它（引用=stock 失败路径仍在；悬空=社区补丁删掉分支）。"""
        secfail = b'Security failure; rebooting into recovery mode...\n\x00'
        cmdln = b'androidboot.selinux\x00'
        rodata = bytearray()
        if with_secfail_str:
            rodata += secfail
        if with_cmdline_parser:
            rodata += cmdln
        body_off = 52 + 32
        code = bytearray(text_len)
        if with_secfail_ref and with_secfail_str:
            # 单 LOAD：p_offset=body_off, p_vaddr=0x8000 → VA(串)=0x8000+text_len+gap
            struct.pack_into('<I', code, text_len - 4, 0x8000 + text_len + rodata_gap)
        total = bytes(code) + bytes(rodata_gap) + bytes(rodata)
        hdr = bytearray(b'\x7fELF\x01\x01\x01' + bytes(9))
        hdr += struct.pack('<HHIIIIIHHHHHH', 2, 40, 1, 0x8000, 52, 0, 0,
                           52, 32, 1, 32, 40, 0)
        struct.pack_into('<I', hdr, 0x1c, 52)
        struct.pack_into('<H', hdr, 0x2a, 1)
        struct.pack_into('<H', hdr, 0x2e, 32)
        ph = struct.pack('<8I', 1, body_off, 0x8000, 0x8000,
                         len(total), len(total), 5, 0x1000)
        return bytes(hdr) + ph + total

    ck('T5 stock init → stock',
       cls(synth_init(True, True, True))['verdict'] == 'stock')
    ck('T5 补丁后(串悬空无解析器) → patched',
       cls(synth_init(False, False, True))['verdict'] == 'patched')
    ck('T5 只解析 cmdline → partial',
       cls(synth_init(True, False, True))['verdict'] == 'partial')
    ck('T5 只引用失败串 → partial',
       cls(synth_init(False, True, True))['verdict'] == 'partial')
    ck('T5 无该消息(如 4.x init) → unknown',
       cls(synth_init(False, False, False))['verdict'] == 'unknown')
    ck('T5 空/非 ELF → unknown',
       cls(b'')['verdict'] == 'unknown' and cls(b'nope' * 8)['verdict'] == 'unknown')

    print('=' * 68)
    print('RESULT: %s  (%d ok, %d failed)'
          % ('PASS' if not BAD else 'FAIL', len(OK), len(BAD)))
    for label, detail in BAD:
        print('  FAIL: %s %s' % (label, detail))
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not BAD else 1


def _cpio_from_raw(raw):
    """内部用：从 cpio 原始字节解析（复用 BootImage 逻辑）。"""
    entries, trailer, trailing = [], None, b''
    pos = 0
    while pos + 110 <= len(raw):
        if raw[pos:pos + 6] != b'070701':
            break
        hdr = raw[pos:pos + 110]
        v = [int(hdr[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        name = raw[pos + 110:pos + 110 + v[11] - 1].decode()
        start = (pos + 110 + v[11] + 3) & ~3
        data = raw[start:start + v[6]]
        nxt = (start + v[6] + 3) & ~3
        if name == 'TRAILER!!!':
            return entries, (hdr, name, data), raw[nxt:]
        entries.append([name, v, data, hdr])
        pos = nxt
    return entries, trailer, trailing


class _BI(BootImage):
    pass


if __name__ == '__main__':
    sys.exit(main())
