#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy345 回归测试（自包含，无需 ROM 镜像）。

覆盖标准管线真正调用的函数，并逐个复现 PR 审查确认的四类阻塞：
  T1  Binder 补丁：唯一 site / cave 避开字面量+ADR / 跳板字节正确
  T2  zImage 重封装：总长不变，按 Linux 3.4 FNAME-only 规则可解回
  T3  模块段重写：注释隔行不再插顶层、无 .ko.ko、参数不串、wlan 变体正确
  T4  SELinux init 取证：stock/patched/partial/unknown 四类 verdict
  T5  失败路径：多处特征、非法 -0x50 目标、顶层 insmod 均拒绝改

直接运行：  python -m porttool.test_legacy345
"""
import gzip
import os
import struct
import sys
import tempfile
import zlib

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from porttool.utils import (KernelImage, patch_binder, find_cave,
                                rewrite_mtk_module_loads,
                                classify_init_selinux_boot, MTK_MAGIC)
else:
    from .utils import (KernelImage, patch_binder, find_cave,
                        rewrite_mtk_module_loads,
                        classify_init_selinux_boot, MTK_MAGIC)

OK, BAD = [], []


def ck(label, cond, detail=''):
    (OK if cond else BAD).append((label, detail))
    print('%s %-56s %s' % ('OK  ' if cond else 'FAIL', label, detail))


def le32(v):
    return struct.pack('<I', v)


# ARM 指令（与真实 T6/Y511 内核缺陷点字节一致）
LDR_R3_R4 = bytes.fromhex('003094e5')          # ldr r3,[r4]   ← 缺陷指令
STR_IP_FP = bytes.fromhex('80c00be5')          # str ip,[fp,#-0x80]
CMP_R3_2 = bytes.fromhex('020053e3')           # cmp r3,#2

MTK_MAGIC_BYTES = le32(MTK_MAGIC)


def build_fake_vmlinux(site_off=0x40000, cave_off=0x220000):
    """含 Binder 缺陷三连 + 一处合法零洞 + 一处被字面量引用的零区。"""
    size = cave_off + 0x40000
    im = bytearray(size)
    for i in range(0, size, 4):
        struct.pack_into('<I', im, i, 0xE1A00000 | ((i // 4) & 0xFFFF))
    im[site_off:site_off + 4] = LDR_R3_R4
    im[site_off + 4:site_off + 8] = STR_IP_FP
    im[site_off + 8:site_off + 12] = CMP_R3_2
    # site 后 0x20 处放一条 B 回 site-0x50，模拟原回调标签；
    # patch_binder 应优先从该目标反推 null_target，而不是直接硬编码偏移。
    # src=site+0x20, PC=src+8, dst=site-0x50 → off=-0x78 → imm=-0x1e。
    struct.pack_into('<I', im, site_off + 0x20, 0xEAFFFFE2)
    im[cave_off:cave_off + 40] = bytes(40)
    decoy = cave_off + 0x20000
    im[decoy:decoy + 40] = bytes(40)
    im[decoy + 256:decoy + 260] = le32(0xC0008000 + decoy)
    banner = b'Linux version 3.4.5 (fake@build) #1 SMP\n\x00'
    im[0x200:0x200 + len(banner)] = banner
    im[0x300:0x309] = b'_mali_ukk'
    return bytes(im), site_off, cave_off, decoy


def build_fake_vmlinux_adr():
    """ADR 引用的零区在合法洞之前；find_cave 必须跳过它。"""
    size = 0x260000
    im = bytearray(size)
    for i in range(0, size, 4):
        struct.pack_into('<I', im, i, 0xE1A00000 | ((i // 4) & 0xFFFF))
    im[0x40000:0x40004] = LDR_R3_R4
    im[0x40004:0x40008] = STR_IP_FP
    im[0x40008:0x4000c] = CMP_R3_2
    # ADR 指令：add r0, pc, #0xFF0 → 0xC0008000 + 0x200FF8
    # imm12 = rot 14 + imm8 0xFF（ROR(0xFF, 28) = 0xFF0）
    struct.pack_into('<I', im, 0x200000, 0xE28F0EFF)
    im[0x200FF8:0x201020] = bytes(0x28)      # 被 ADR 引用的零区
    im[0x220000:0x220028] = bytes(0x28)      # 合法零洞
    return bytes(im), 0x220000


def build_mtk_kernel(vmlinux):
    """zImage 风格：512B MTK KERN 头 + gzip 载荷 + 尾部数据。"""
    gz = gzip.compress(vmlinux, 9, mtime=0)
    payload = bytearray(gz) + bytes(64)
    hdr = MTK_MAGIC_BYTES + le32(len(payload)) + b'KERN' + bytes(512 - 12)
    return bytes(hdr) + bytes(payload)


def synth_init(with_cmdline_parser, with_secfail_ref, with_secfail_str,
               text_len=0x40, rodata_gap=4):
    """拼最小 ELF32 init：rodata 放失败串，字面量池按开关引用它。"""
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


# ---------------------------------------------------------------- 模块段测试

RC_COMMENT = (
    'on boot\n'
    '    start foo\n'
    '\n'
    '# load MTK modules\n'
    '    insmod /system/lib/modules/mtk_wmt_wifi.ko mac=00:11:22\n'
    '    insmod /system/lib/modules/devinfo.ko\n'
    '\n'
    'service foo /system/bin/foo\n'
    '    class core\n'
)


def test_module_rewrite():
    out, total, added, changed, note = rewrite_mtk_module_loads(
        RC_COMMENT, wlan_name='wlan_mt6572.ko')
    ck('T3 注释/空行隔开仍留在 on boot 段内',
       out.startswith('on boot\n') and '# load MTK modules' in out
       and 'on boot' not in out[out.find('devinfo.ko'):], note)
    ck('T3 不生成 .ko.ko', '.ko.ko' not in out)
    ck('T3 参数只留在原模块', 'mac=00:11:22' in out
       and out.count('mac=00:11:22') == 1
       and 'devinfo.ko mac' not in out)
    ck('T3 缺失 wlan 用 6572 变体', 'wlan_mt6572.ko' in out
       and 'wlan_mt6582.ko' not in out)
    ck('T3 总槽位 12 / 补全 10', total == 12 and added == 10,
       '%d/%d' % (total, added))

    # 幂等
    out2, _t, _a, ch2, _n = rewrite_mtk_module_loads(out, wlan_name='wlan_mt6572.ko')
    ck('T3 模块段幂等', out2 == out and not ch2)

    # 无 insmod 行：补在 on post-fs-data 段尾，不落顶层
    rc_empty = 'on post-fs-data\n    mkdir /data\n\non boot\n    start foo\n'
    out, total, added, changed, note = rewrite_mtk_module_loads(
        rc_empty, wlan_name='wlan_mt6582.ko')
    ck('T3 无 insmod 行时插在 on 段尾', 'mkdir /data' in out
       and out.index('devinfo.ko') > out.index('mkdir /data')
       and out.index('devinfo.ko') < out.index('on boot'))
    ck('T3 无 insmod 行不生成 .ko.ko', '.ko.ko' not in out and total == 12
       and added == 12)

    # 无 on 段：拒绝改
    rc_top = 'insmod /system/lib/modules/devinfo.ko\n'
    out, total, added, changed, note = rewrite_mtk_module_loads(rc_top)
    ck('T3 顶层 insmod 拒绝改写', out == rc_top and not changed
       and ('不在任何段' in note or '不在 on 段' in note))

    # 其他 on 段不搬动、不重复
    rc_two = ('on boot\n    insmod /system/lib/modules/devinfo.ko\n'
              'on post-fs-data\n    insmod /system/lib/modules/sec.ko\n')
    out, total, added, changed, note = rewrite_mtk_module_loads(rc_two)
    ck('T3 其他 on 段保持原样', out.count('devinfo.ko') == 1
       and out.count('sec.ko') == 1
       and out.index('sec.ko') > out.index('on post-fs-data')
       and '其他段' in note)

    # service 块内的 insmod 不得被当成 on 段命令
    rc_service = ('service foo /system/bin/foo\n'
                  '    insmod /system/lib/modules/devinfo.ko\n')
    out, total, added, changed, note = rewrite_mtk_module_loads(rc_service)
    ck('T3 service 块内 insmod 拒绝改写', out == rc_service and not changed
       and 'service' in note)

    # on 段里已有 service 块：无 insmod 时补块必须在 service 之前
    rc_on_service = ('on post-fs-data\n    mkdir /data\n'
                     'service foo /system/bin/foo\n    class core\n')
    out, total, added, changed, note = rewrite_mtk_module_loads(
        rc_on_service, wlan_name='wlan_mt6582.ko')
    ck('T3 无 insmod 时补块不落进 service 块',
       out.index('devinfo.ko') > out.index('mkdir /data')
       and out.index('devinfo.ko') < out.index('service foo'))


def test_find_cave_adr():
    v, valid = build_fake_vmlinux_adr()
    cave = find_cave(v, 24, lo=0x200000, hi=len(v) - 0x1000)
    ck('T1 find_cave 跳过 ADR 引用零区',
       cave is not None and cave[0] == valid,
       'cave=0x%x expect=0x%x' % (cave[0] if cave else -1, valid))


def test_patch_failures(tmp):
    # 两处特征 → 拒绝
    v, *_ = build_fake_vmlinux()
    v = bytearray(v)
    v[0x50000:0x5000c] = v[0x40000:0x4000c]
    p = os.path.join(tmp, 'dup.bin')
    with open(p, 'wb') as f:
        f.write(build_mtk_kernel(bytes(v)))
    diag = []
    man = patch_binder(KernelImage(p), os.path.join(tmp, 'dup_out.bin'), diag)
    ck('T5 多处 Binder 特征拒绝盲选', man is None and diag
       and '2 处' in diag[0], diag[0] if diag else '')

    # site < 0x50 → -0x50 越界 → 拒绝
    v2, site2, *_ = build_fake_vmlinux(site_off=0x40)
    p2 = os.path.join(tmp, 'low.bin')
    with open(p2, 'wb') as f:
        f.write(build_mtk_kernel(v2))
    diag2 = []
    man2 = patch_binder(KernelImage(p2), os.path.join(tmp, 'low_out.bin'), diag2)
    ck('T5 -0x50 目标越界时拒绝补丁', man2 is None and diag2
       and '不在内核范围' in diag2[0], diag2[0] if diag2 else '')

    # 没有回跳 B 时回退 -0x50，但仍校验目标非空
    v3, site3, *_ = build_fake_vmlinux()
    v3 = bytearray(v3)
    struct.pack_into('<I', v3, site3 + 0x20, 0xE1A00000)  # 抹掉回跳 B
    p3 = os.path.join(tmp, 'fallback.bin')
    with open(p3, 'wb') as f:
        f.write(build_mtk_kernel(bytes(v3)))
    man3 = patch_binder(KernelImage(p3), os.path.join(tmp, 'fallback_out.bin'))
    ck('T5 无回跳 B 时回退 -0x50 并校验通过',
       man3 is not None and man3.get('null_source') == 'fallback -0x50'
       and man3.get('null_target') == hex(0xC0008000 + site3 - 0x50),
       '%s / %s' % (man3.get('null_source') if man3 else None,
                    man3.get('null_target') if man3 else None))


def test_selinux():
    ck('T4 stock init → stock',
       classify_init_selinux_boot(synth_init(True, True, True))['verdict'] == 'stock')
    ck('T4 补丁后(串悬空无解析器) → patched',
       classify_init_selinux_boot(synth_init(False, False, True))['verdict'] == 'patched')
    ck('T4 只解析 cmdline → partial',
       classify_init_selinux_boot(synth_init(True, False, True))['verdict'] == 'partial')
    ck('T4 只引用失败串 → partial',
       classify_init_selinux_boot(synth_init(False, True, True))['verdict'] == 'partial')
    ck('T4 无该消息(如 4.x init) → unknown',
       classify_init_selinux_boot(synth_init(False, False, False))['verdict'] == 'unknown')
    ck('T4 空/非 ELF → unknown',
       classify_init_selinux_boot(b'')['verdict'] == 'unknown'
       and classify_init_selinux_boot(b'nope' * 8)['verdict'] == 'unknown')


def main():
    print('=' * 72)
    print('legacy345 回归测试（合成数据）')
    print('=' * 72)
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

    cave = find_cave(k.vmlinux, 24, lo=0x200000, hi=len(k.vmlinux) - 0x1000)
    ck('T1 find_cave 避开被引用零区',
       cave is not None and cave[0] == cave_off,
       'cave=0x%x' % (cave[0] if cave else -1))
    test_find_cave_adr()

    out = os.path.join(tmp, 'kernel_fixed.bin')
    man = patch_binder(k, out)
    ck('T1 Binder 补丁自动定位成功', man is not None)
    if man:
        ck('T1 补丁点为缺陷 ldr 指令',
           man['site'] == hex(0xC0008000 + site_off), man['site'])
        ck('T1 回调目标由 B 反推（非硬编码）',
           man.get('null_source') == 'branch-target'
           and man.get('null_target') == hex(0xC0008000 + site_off - 0x50),
           '%s / %s' % (man.get('null_source'), man.get('null_target')))
        ck('T1 stub 以 str+cmp r4 开头',
           man['stub'].startswith('80c00be5') and len(man['stub']) == 40,
           man['stub'])

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

    test_patch_failures(tmp)
    test_module_rewrite()
    test_selinux()

    print('=' * 72)
    print('RESULT: %s  (%d ok, %d failed)'
          % ('PASS' if not BAD else 'FAIL', len(OK), len(BAD)))
    for label, detail in BAD:
        print('  FAIL: %s %s' % (label, detail))
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not BAD else 1


if __name__ == '__main__':
    sys.exit(main())
