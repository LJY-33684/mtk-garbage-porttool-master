import re
import time
from io import StringIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from os import walk, getcwd, chdir, symlink, readlink, name as osname, stat, unlink, chmod
import os
import os.path as op
from shutil import rmtree, copytree, copy2
from stat import S_IWRITE
import lzma
import subprocess
from sys import stdout
from hashlib import md5
from .bootimg import unpack_bootimg, repack_bootimg
from .imgextractor import Extractor
from .symlink_fix import fix_symlinks, fix_inode_bitmaps, verify_image_integrity
from .configs import (
    make_ext4fs_bin,
    magiskboot_bin,
    img2simg_bin,
    simg2img_bin
)

from .sdat2img import main as sdat2img
from .img2sdat import main as img2sdat

from .boot_patch import BootPatcher, parseMagiskApk
import glob
import contextlib
import sys
import platform
import gzip
import zlib

if osname == 'nt':
    from ctypes import windll, wintypes


def _clear_attrs(path):
    """清除 Windows 只读/系统/隐藏属性，使文件可被写入或删除。"""
    try:
        if osname == 'nt':
            windll.kernel32.SetFileAttributesW(str(path), 0x80)  # FILE_ATTRIBUTE_NORMAL
        else:
            # POSIX：保留原有权限，仅确保可写。
            # 不能直接 chmod(path, S_IWRITE)（=0200 只写），否则后续读取文件会 PermissionError 中断移植。
            chmod(path, stat(path).st_mode | 0o222)
    except Exception:
        pass


def _rmtree(path):
    """健壮版 rmtree：遇到只读/系统属性等拒绝删除时，先清属性再重试。"""
    if not Path(path).exists():
        return
    def _onerror(func, p, exc_info):
        _clear_attrs(p)
        try:
            func(p)
        except Exception:
            pass
    rmtree(str(path), onerror=_onerror)


def _fmt_size(nbytes):
    """格式化文件大小（字节 -> 可读文本）。"""
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:.2f} GB"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:.1f} MB"
    return f"{nbytes / 1024:.1f} KB"


# ---------- 移植信息读取（移植流程中自动读取并打印，无独立入口） ----------
_LINUX_VER_RE = re.compile(rb'Linux version\s+([^\x00\n\r]+)')
_LINUX_LOOSE_RE = re.compile(rb'Linux[ \t]+(?:version|kernel)[ \t]*([^\x00\n\r]+)')
_GCC_RE = re.compile(r'gcc version\s+([^\s\)]+)')


def _extract_linux_ver(kernel_path):
    """从内核文件提取 Linux 版本与 GCC 版本。

    支持未压缩 Image、gzip 内核，以及 32 位自解压 zImage
    （版本字符串藏在 gzip/LZMA/xz 压缩 payload 内，需先解压再搜索）。
    """
    p = Path(kernel_path)
    if not p.exists():
        return None, None
    raw = p.read_bytes()
    if raw[:2] == b'\x1f\x8b':  # 直接是 gzip
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    m = _LINUX_VER_RE.search(raw) or _LINUX_LOOSE_RE.search(raw)
    if not m:
        payload = _decompress_zimage_payload(raw)
        if payload:
            m = _LINUX_VER_RE.search(payload) or _LINUX_LOOSE_RE.search(payload)
    if not m:
        return None, None
    ver = m.group(1).decode('latin-1', errors='replace').strip()
    gm = _GCC_RE.search(ver)
    return ver, (gm.group(1) if gm else None)


def _decompress_zimage_payload(raw):
    """尝试从自解压 zImage 中解压出真实 vmlinux（支持 gzip / xz / lzma-alone）。"""
    # gzip payload（zImage 最常见）
    idx = 0
    while True:
        pos = raw.find(b'\x1f\x8b\x08', idx)
        if pos == -1:
            break
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            out = d.decompress(raw[pos:])
            if out and len(out) > 1024 * 1024:  # 排除误匹配的小块
                return out
        except Exception:
            pass
        idx = pos + 3
    # xz payload
    idx = 0
    while True:
        pos = raw.find(b'\xfd7zXZ\x00', idx)
        if pos == -1:
            break
        try:
            d = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
            out = d.decompress(raw[pos:])
            if out and len(out) > 1024 * 1024:
                return out
        except Exception:
            pass
        idx = pos + 1
    # lzma-alone payload（MTK 老内核常用）
    idx = 0
    while True:
        pos = raw.find(b'\x5d\x00\x00\x00', idx)
        if pos == -1:
            break
        try:
            d = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
            out = d.decompress(raw[pos:])
            if out and len(out) > 1024 * 1024:
                return out
        except Exception:
            pass
        idx = pos + 1
    return None


def _read_bootinfo(bootinfo_path):
    """读取 bootimg 解包生成的 bootinfo.txt（base/ramdisk_addr/name/cmdline 等）。"""
    p = Path(bootinfo_path)
    if not p.exists():
        return {}
    info = {}
    for line in p.read_text(encoding='ascii', errors='ignore').splitlines():
        if ':' in line:
            k, v = line.strip().split(':', 1)
            info[k.strip()] = v.strip()
    return info


def _read_build_prop(prop_path):
    """读取 build.prop 全部有效键值（自动检测编码，跳过注释行）。"""
    p = Path(prop_path)
    if not p.exists():
        return {}
    raw = p.read_bytes()
    enc = 'utf-8'
    for enc_cand in ('utf-8', 'gbk', 'latin-1', 'gb18030'):
        try:
            raw.decode(enc_cand)
            enc = enc_cand
            break
        except UnicodeDecodeError:
            continue
    info = {}
    for line in raw.decode(enc, errors='replace').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            info[k.strip()] = v.strip()
    return info


# build.prop 字段 -> 中文标签（按展示顺序）
_SYSTEM_INFO_KEYS = (
    ('ro.build.version.release', 'Android版本'),
    ('ro.build.version.sdk', 'SDK/API'),
    ('ro.build.version.security_patch', '安全补丁'),
    ('ro.product.model', '产品型号'),
    ('ro.product.device', '设备代号'),
    ('ro.product.board', '主板/芯片'),
    ('ro.product.manufacturer', '制造商'),
    ('ro.product.brand', '品牌'),
    ('ro.mediatek.platform', 'MTK平台'),
    ('ro.hardware', 'hardware'),
    ('ro.product.cpu.abi', 'CPU ABI'),
    ('ro.product.cpu.abilist', 'CPU ABI列表'),
    ('ro.build.display.id', '构建ID'),
    ('ro.build.fingerprint', '构建指纹'),
)


def _system_info_rows(prop_path, sys_dir):
    """整理 system 信息（build.prop 摘要 + 目录布局），返回 (标签, 值) 列表。"""
    rows = []
    info = _read_build_prop(prop_path)
    for key, label in _SYSTEM_INFO_KEYS:
        val = info.get(key)
        if val:
            rows.append((label, val))
    d = Path(sys_dir)
    if d.exists():
        # 架构判定：优先 build.prop 的 ABI，辅以 lib64 实际库数（避免空壳 lib64 误判）
        abi = info.get('ro.product.cpu.abi', '')
        lib64 = d / 'lib64'
        n64 = 0
        if lib64.is_dir():
            try:
                n64 = sum(1 for _ in lib64.glob('*.so'))
            except Exception:
                n64 = 0
        if 'arm64' in abi or 'x86_64' in abi:
            arch = '64位(arm64)'
        elif 'arm64' in info.get('ro.product.cpu.abilist', '') or 'x86_64' in info.get('ro.product.cpu.abilist', ''):
            arch = '64位(arm64)'
        elif n64 >= 10:
            arch = f'64位(arm64)，lib64含{n64}个库'
        elif n64 > 0:
            arch = f'32位为主（lib64仅{n64}个库）'
        else:
            arch = '32位(arm)'
        rows.append(('系统架构', arch))
        has_vendor = (d / 'vendor').is_dir()
        rows.append(('Vendor目录', '存在' if has_vendor else '不存在'))
        try:
            n_files = sum(1 for _ in d.rglob('*') if _.is_file())
            rows.append(('文件总数', f'{n_files} 个'))
        except Exception:
            pass
    return rows


def _print_rows(std, title, rows):
    """以树形缩进打印信息区块。"""
    if not rows:
        print(f"{title}：未读取到有效信息", file=std)
        return
    print(f"{title}：", file=std)
    for i, (k, v) in enumerate(rows):
        prefix = "  ├─ " if i < len(rows) - 1 else "  └─ "
        print(f"{prefix}{k}：{v}", file=std)


tool_author = 'affggh'; tool_version = '1.3-beta5p2'

class proputil:
    def __init__(self, propfile: str):
        proppath = Path(propfile)
        if proppath.exists():
            self.propfile = propfile
            self.encoding = self.__detect_encoding(propfile)
            self.propfd = Path(propfile).open('r+', encoding=self.encoding.rstrip('-sig'), newline='\n')  # 写句柄去 sig，避免给无 BOM 文件注入 BOM；newline='\n' 强制 LF，防止 Windows 把 Android 属性文件 CRLF 化
        else:
            raise FileNotFoundError(f"File {propfile} does not exist!")
        self.prop = self.__loadprop

    def __detect_encoding(self, filepath):
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'latin-1', 'gb18030']  # utf-8-sig 剥 BOM
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    f.readlines()
                return encoding
            except UnicodeDecodeError:
                continue
        return 'latin-1'  # 默认回退编码

    @property
    def __loadprop(self) -> list:
        # 默认 universal newline：读入时 \r\n/\r 统一转 \n，避免修改后混入混合行尾；
        # 写句柄已设 newline='\n'，保证落盘纯 LF（Android 属性文件不允许 CRLF）
        with open(self.propfile, 'r', encoding=self.encoding) as f:
            return f.readlines()

    def getprop(self, key: str) -> str | None:
        for i in self.prop:
            if i.startswith(key + '='): return i.rstrip().split('=', 1)[1]
        return None
    
    def setprop(self, key, value) -> None:
        flag: bool = False
        for index, current in enumerate(self.prop):
            if current.startswith(key + '='):
                if not value: value = ''
                self.prop[index] = current.split('=', 1)[0] + '=' + value + '\n'
                flag = True
        if not flag:
            self.prop.append(key + '=' + value + '\n')

    def save(self):
        self.propfd.seek(0, 0)
        self.propfd.truncate()
        self.propfd.writelines(self.prop)
        self.propfd.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()

def _infer_fs_mode(unix_path: str, st_mode: int = 0) -> str:
    """推断 fs_config 权限：可执行文件按 755，其余 644；保留 suid 位。
    #74：判定 = 真实 st_mode 执行位（Linux 解包保留）OR 路径位于 bin/xbin/vendor/bin
    （Windows 落盘后无扩展名二进制的 st_mode 不带执行位，需路径兜底，否则 vendor/bin 全压 0644）"""
    suid = '4' if st_mode & 0o4000 else '0'
    parts = unix_path.lstrip('/').split('/')
    path_exec = len(parts) > 2 and parts[0] == 'system' and (
        parts[1] in ('bin', 'xbin') or (parts[1] == 'vendor' and parts[2] == 'bin')
        or (parts[1] == 'etc' and parts[2] == 'init.d'))  # init.d 脚本需可执行位
    is_exec = bool(st_mode & 0o111) or path_exec
    return suid + ('755' if is_exec else '644')

# Android API → 主版本号（用于判断硬件 HAL ABI 是否跨大版本）。
# 同一主版本内（如 7.0↔7.1、5.0↔5.1）老式 C HAL 基本兼容；主版本不同时，
# 独立服务型 HAL（音频/相机/媒体硬解/基带RIL/WiFi/蓝牙）ABI 会不兼容。
_ANDROID_MAJOR = {
    19: 4, 20: 4,              # 4.4 / 4.4W
    21: 5, 22: 5,              # 5.0 / 5.1
    23: 6,                     # 6.0
    24: 7, 25: 7,              # 7.0 / 7.1（7.0 起 audioserver/mediacodec 独立、HAL 接口变更）
    26: 8, 27: 8,              # 8.0 / 8.1（Treble，gralloc/HWC/sensors 等转 HIDL）
    28: 9, 29: 10, 30: 11,     # 9 / 10 / 11
    31: 12, 32: 12,            # 12 / 12L
    33: 13, 34: 14, 35: 15,    # 13 / 14 / 15
}

def cross_major_version(base_sdk, port_sdk) -> bool:
    """底包(base)与移植源(port)是否处于不同 Android 主版本。
    任一版本读不到(None/未知)时返回 False，保守地不改变原有替换行为。"""
    if base_sdk is None or port_sdk is None:
        return False
    bm = _ANDROID_MAJOR.get(base_sdk)
    pm = _ANDROID_MAJOR.get(port_sdk)
    return bool(bm is not None and pm is not None and bm != pm)

# 向后兼容旧名
audio_cross_version = cross_major_version

# === 跨 Android 大版本硬件替换策略（同平台、Android 7.x 及以下无 VNDK 老设备）===
# 原则：
#  - 独立服务型 HAL（音频/相机/媒体硬解/RIL/WiFi/蓝牙）跨大版本 ABI 不兼容，覆盖底包旧库
#    会让对应独立进程（audioserver/cameraserver/mediacodec/rild/wpa_supplicant/bluetooth）
#    崩溃；这些进程崩溃一般不阻断开机，故跨版本【提示高风险但仍执行替换】，
#    由用户自行权衡（个别设备跨版本替换反而可用，如 mt6582 词典笔补 WiFi 三库）。
#  - 图形栈（gralloc/hwcomposer/GPU EGL）是 surfaceflinger 开机合成必需，不换必黑屏/卡一；
#    Treble(8.0) 前为稳定的 gralloc1/HWC1/EGL C ABI，故跨版本仍成套替换（仅给黑屏警告）。
#  - sensors/lights/power/vibrator/gps 等老式 C HAL 在 8.0 前 ABI 稳定；
#    firmware/mddb/.tp/keylayout 是与硬件绑定的数据，均继续替换。

# 手动 replace 循环：跨版本高风险替换项（音频/相机/RIL/WiFi/蓝牙）。
# 这些组里的 modem/wifi/bt 固件与射频数据由独立的 firmware、mddb 组继续替换，不受影响。
# 注意：跨大版本时不再整组静默跳过，而是【提示高风险但仍执行】，
# 由用户自行决定是否用底包 HAL 覆盖移植源（个别设备跨版本替换反而可用）。
CROSS_SKIP_REPLACE_GROUPS = frozenset({
    'audiodriver', 'audioengine', 'tfa',
    'camera', 'ril', 'wifi', 'bluetooth',
})

# 音频三组：硬件 primary HAL / 音频参数路由库 / TFA 功放，与移植源 ROM 的音频框架
# （libaudioflinger / audio_policy / audio_effects 配置）强成套。实测即使同芯片、同 Android
# 大版本，跨机型用底包音频 HAL 覆盖移植源，也会让 audioserver 加载即空指针崩溃（SIGSEGV
# fault addr 0x4）、卡第二屏（mt6582 Android7.1.2 同版本移植实证）。因此这三组默认关闭、
# 保留移植源整套以优先保证开机；仅当用户手动勾选时执行，并打印醒目风险警告。
AUDIO_REPLACE_GROUPS = frozenset({
    'audiodriver', 'audioengine', 'tfa',
})

# 图形栈：GPU(mali等)/gralloc 与移植源 ROM 的 surfaceflinger/图形框架强成套，且是开机合成必需。
# 实测跨大版本（5.0→7.1.2）用底包旧 GPU/gralloc 覆盖移植源 → 黑屏/壁纸异常（mt6582 词典笔实证），
# 故跨大版本【保留移植源、跳过替换】；同 Android 大版本内 C ABI 稳定可替换、照常替换。
# hwcomposer 例外：它直接与底包内核 DISP/DSI 驱动强绑定（走 ioctl 通道，非纯 framework ABI），
# 移植源高版本 hwcomposer 在底包内核上黑屏/壁纸异常（词典笔 5.0→7.1.2 实测：保留移植源 → 黑屏；
# 设备侧换回底包 hwcomposer → 壁纸立即正常）。故 hwcomposer 不在本集合内，跨大版本照常替换=保留底包。
GRAPHICS_REPLACE_GROUPS = frozenset({
    'malidriver', 'gralloc',
})

class updaterutil:
    def __init__(self, fd):
        self.fd = fd
        if not self.fd:
            raise IOError("fd is not valid!")
        self.content = self.__parse_commands
    
    @property
    def __parse_commands(self):
        self.fd.seek(0, 0)
        commands = re.findall(r'(\w+)\((.*?)\)', self.fd.read().replace('\n', ''))
        parsed_commands = [[command, *(arg[0] or arg[1] or arg[2] for arg in re.findall(r'(?:"([^"]+)"|(\b\d+\b)|(\b\S+\b))', args))] for command, args in commands]
        return parsed_commands

    def generate(self, author: str, version: str, partitions: dict, sdat: bool = False):
        def add_quotes_if_needed(arg):
            return arg if arg.isdigit() else f'"{arg}"'
        self.fd.seek(0, 0)
        updater_script = self.fd.read().replace('\n', '')
        pattern = r'(\w+)\((.*?)\)'
        commands = re.findall(pattern, updater_script)
        filtered_commands = [(command, *(arg[0] or arg[1] or arg[2] for arg in re.findall(r'(?:"([^"]+)"|(\b\d+\b)|(\b\S+\b))', args))) for command, args in commands if command in {'symlink', 'set_metadata_recursive', 'set_metadata'}]
        updater_script_content = [f"{command}({', '.join(map(add_quotes_if_needed, args))});" for command, *args in filtered_commands]

        # #36：partitions 为空（6/7 方案默认无分区信息）时，从移植源 updater-script 自动解析分区路径
        parts = dict(partitions or {})
        if not parts.get("system") or not parts.get("boot"):
            parsed = self.__parse_partitions(updater_script)
            parts.setdefault("system", parsed.get("system"))
            parts.setdefault("boot", parsed.get("boot"))

        if sdat:
            # sdat 卡刷包必须同时具备 system 与 boot 分区信息
            if not (parts.get("system") and parts.get("boot")):
                return None
            sys_ok = boot_ok = True
        else:
            # 常规卡刷包：boot 必需（仅移植内核方案可只刷 boot）；system 缺失时跳过 system 段
            sys_ok = bool(parts.get("system"))
            boot_ok = bool(parts.get("boot"))
            if not boot_ok:
                return None

        header_commands = [
            "ui_print(\"\");",
            "ui_print(\"======== Auto Generated By MTK PORT TOOL ========\");",
            f"ui_print(\"- Author: {author}\");",
            f"ui_print(\"- Version: {version}\");",
            f"ui_print(\"- MTK PORT TOOL Info below:\");",
            f"ui_print(\"    TOOL Author: {tool_author}\");",
            f"ui_print(\"    TOOL Version: {tool_version}\");",
            f"ui_print(\"{'='*49}\");",
        ]
        if sdat:
            # sdat 卡刷包：块级写入，文件树/符号链接/metadata 均由 new.dat 内嵌保留
            body_commands = [
                "ifelse(is_mounted(\"/system\"), unmount(\"/system\"));",
                "set_progress(0.1);",
                "ui_print(\"- Flashing system (SDAT)...\");",
                "set_progress(0.2);",
                f"block_image_update(\"{parts['system']}\", package_extract_file(\"system.transfer.list\"), \"system.new.dat\", \"system.patch.dat\");",
                "set_progress(0.8);",
                "ui_print(\"- Flash boot image...\");",
                f"package_extract_file(\"boot.img\", \"{parts['boot']}\");",
                "set_progress(0.9);",
                "ui_print(\"- Done!\");",
                "set_progress(1);",
            ]
        else:
            body_commands = [
                "ifelse(is_mounted(\"/system\"), unmount(\"/system\"));",
            ]
            if sys_ok:
                body_commands += [
                    f"run_program(\"mke2fs\", \"{parts['system']}\");",
                    f"format(\"ext4\", \"EMMC\", \"{parts['system']}\", \"0\", \"/system\");",
                    "set_progress(0.1);",
                    "ui_print(\"- Mounting system partition...\");",
                    f"mount(\"ext4\", \"EMMC\", \"{parts['system']}\", \"/system\", \"max_batch_time=0,commit=1,data=ordered,barrier=1,errors=panic,nodelalloc\");",
                    "ui_print(\"- Extract system conditionally...\");",
                    "set_progress(0.2);",
                    "package_extract_dir(\"system\", \"/system\");",
                    "set_progress(0.5);",
                    "ui_print(\"- Create symlinks and setup metadata...\");",
                    *updater_script_content,
                    "set_progress(0.8);",
                ]
            else:
                body_commands += [
                    "set_progress(0.1);",
                    "ui_print(\"- 未解析到 system 分区信息，仅刷写 boot...\");",
                ]
            body_commands += [
                "ui_print(\"- Flash boot image...\");",
                f"package_extract_file(\"boot.img\", \"{parts['boot']}\");",
                "set_progress(0.9);",
                "ui_print(\"- Done!\");",
            ]
            if sys_ok:
                body_commands += ["unmount(\"/system\");"]
            body_commands += ["set_progress(1);"]
        full_commands = header_commands + body_commands
        return "\n".join(full_commands)

    def __parse_partitions(self, script: str) -> dict:
        """#36：从移植源 updater-script 文本解析 system/boot 分区路径"""
        parts = {}
        m = re.search(r'(?:format|mount)\("(?:ext4|yaffs2|f2fs)",\s*"EMMC",\s*"([^"]+)"', script, re.I)
        if m:
            parts["system"] = m.group(1)
        else:
            m = re.search(r'block_image_update\("([^"]+)"', script)
            if m:
                parts["system"] = m.group(1)
        for m in re.finditer(r'package_extract_file\(\s*"([^"]*boot[^"]*)",\s*"([^"]+)"\s*\)', script, re.I):
            parts["boot"] = m.group(2)
            break
        return parts

class ziputil:
    def __init__(self):
        pass

    @staticmethod
    def _safe_extract_member(zipf, name, outdir):
        """#170 zip slip：校验解压目标路径不逃出 outdir"""
        outdir_abs = op.abspath(outdir)
        target = op.abspath(op.join(outdir_abs, name))
        if not target.startswith(outdir_abs + op.sep) and target != outdir_abs:
            raise ValueError(f"非法 zip 条目（路径穿越）: {name}")
        zipf.extract(name, outdir_abs)
        # #193：S_IFLNK 条目经 zipfile.extract 后类型信息丢失（Windows 解成普通文件、
        # 无 !<symlink> 标记），导致 decompress→compress 往返后符号链接变普通文件。
        # 此处还原为与 Windows 解包产物一致的 !<symlink> 标记文件（目标转 UTF-16 带 BOM），
        # compress 侧统一识别（#122 词典笔 WiFi 根因同源）——闭环。
        try:
            _zi = zipf.getinfo(name)
            _is_symlink = (_zi.create_system == 3 and
                           ((_zi.external_attr >> 16) & 0o170000) == 0o120000)
            if _is_symlink and not op.islink(target):
                with open(target, 'rb') as _f:
                    _raw = _f.read()
                _text = _raw.decode('utf-8', errors='replace').rstrip('\0')
                with open(target, 'wb') as _f:
                    _f.write(b"!<symlink>" + _text.encode('utf-16') + b'\0\0')
        except (OSError, KeyError, UnicodeError):
            pass

    def decompress(zippath: str, outdir: str):
        with ZipFile(zippath, 'r') as zipf:
            for name in zipf.namelist():
                ziputil._safe_extract_member(zipf, name, outdir)

    def extract_onefile(zippath: str, filename: str, outpath: str):
        with ZipFile(zippath, 'r') as zipf:
            outdir = op.dirname(outpath)
            ziputil._safe_extract_member(zipf, filename, outdir)
    
    def compress(zippath: str, indir: str):
        _symlink_mark = bytes.fromhex('213C73796D6C696E6B3EFFFE')
        with ZipFile(zippath, 'w', ZIP_DEFLATED) as zipf:
            for root, dirs, files in walk(indir):
                for file in files:
                    file_path = op.join(root, file)
                    zip_path = op.relpath(op.abspath(file_path), op.abspath(indir)).replace('\\', '/')
                    # 真符号链接（类 Unix 环境解包 S_IFLNK 条目时 zipfile 直接建 os.symlink，
                    # 无 !<symlink> 标记）→ 读取链接目标，写回带 Unix 软链接属性的条目；
                    # 否则 zipf.write 会跟随链接把目标内容当普通文件写入，往返后类型丢失。
                    if op.islink(file_path):
                        try:
                            _target = readlink(file_path)
                            _zi = ZipInfo(zip_path)
                            _zi.create_system = 3                 # Unix
                            _zi.external_attr = 0o120777 << 16    # S_IFLNK | rwxrwxrwx
                            _zi.compress_type = ZIP_DEFLATED
                            zipf.writestr(_zi, _target)
                            continue
                        except OSError:
                            pass
                    # Windows 解包产物中的软链接标记文件（!<symlink>）→ 转成带 Unix 软链接
                    # 属性的 zip 条目（数据为链接目标文本），刷机侧才能恢复为真正的符号链接；
                    # 否则会被当作普通小文件刷入，命令不可执行（#122 词典笔 WiFi 根因）。
                    try:
                        with open(file_path, 'rb') as _f:
                            _head = _f.read(12)
                        if _head == _symlink_mark:
                            with open(file_path, 'rb') as _f:
                                _f.seek(12)
                                _target = _f.read().decode('utf-16').rstrip('\0')
                            _zi = ZipInfo(zip_path)
                            _zi.create_system = 3                 # Unix
                            _zi.external_attr = 0o120777 << 16    # S_IFLNK | rwxrwxrwx
                            _zi.compress_type = ZIP_DEFLATED
                            zipf.writestr(_zi, _target)
                            continue
                    except OSError:
                        pass
                    zipf.write(file_path, zip_path)

class xz_util:
    def __init__(self):
        pass

    def compress(src_file_path, dest_file_path):
        with open(src_file_path, 'rb') as src_file:
            with lzma.open(dest_file_path, 'wb') as dest_file:
                dest_file.write(src_file.read())

class bootutil:
    def __init__(self, bootpath):
        self.bootpath = op.abspath(bootpath)
        self.bootdir = op.dirname(self.bootpath)
        self.retcwd = getcwd()
    
    def unpack(self):
        chdir(self.bootdir)
        err_buf = StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                unpack_bootimg(self.bootpath)
        except Exception:
            sys.stderr.write(err_buf.getvalue())
            raise
        finally:
            chdir(self.retcwd)
    
    def repack(self):
        chdir(self.bootdir)
        try:
            with open("bootinfo.txt", encoding='utf-8-sig') as f:
                (
                    base,
                    ramdisk_addr,
                    second_addr,
                    tags_addr,
                    page_size,
                    name,
                    cmdline,
                    padding_size,
                ) = [i.lstrip("\x00").rstrip().split(':', 1)[1] for i in iter(f.readline, "")]
            cmdline = cmdline.strip()  # #174：与 base/page_size 等数值字段去空格对齐
            err_buf = StringIO()
            try:
                with contextlib.redirect_stderr(err_buf):
                    repack_bootimg(base, cmdline, page_size, padding_size, None)
            except Exception:
                sys.stderr.write(err_buf.getvalue())
                raise
        finally:
            chdir(self.retcwd)
    
    def __enter__(self):
        return self

    def __exit__(self, *vars):
        chdir(self.retcwd)

class portutils:
    def __init__(self, items: dict, bootimg: str, sysimg: str, port_source, source_type: str, genimg: bool = False, stdlog = None):
        self.items = items
        self.sysimg = sysimg
        self.bootimg = bootimg
        self.port_source = port_source  # zip路径 或 (boot.img, system.img)元组
        self.source_type = source_type  # 'zip' 或 'img'
        self.genimg = genimg  # True=输出img，False=输出zip
        # 输出统一放在 out/<时间戳>/ 子目录（点击开始移植时生成，Windows 目录名不允许冒号，用中文冒号）
        self.outdir = Path("out") / time.strftime("%Y%m%d-%H：%M：%S")
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.std = stdlog if stdlog else stdout
        self.sdat = False  # 提前赋值，确保属性始终存在
        # 跨 Android 大版本标志：底包与移植源主版本不同时为 True。
        # 在 __port_system 版本检测后置位；置位后对音频/相机/媒体硬解/RIL/WiFi/蓝牙
        # 等独立服务型 HAL 的跨版本替换打印【高风险提示但仍执行】（由用户自行决定），
        # 图形 gralloc/hwcomposer/GPU 仍成套替换。
        self._cross_major = False
        if not self.__check_exist:
            print("【检查失败】必要文件不存在，移植流程终止", file=self.std)
            raise RuntimeError("移植初始化失败：底包或移植源文件不存在，请检查路径配置")
    
    @property
    def __check_exist(self) -> bool:
        # LK去警告 模式：只需 LK 镜像文件
        if self._flag('lk_patch_mode'):
            if not Path(self.bootimg).exists():
                print(f"【缺失文件】LK镜像 {self.bootimg} 不存在", file=self.std)
                return False
            return True
        # Recovery 模式：只需底包Recovery + 移植Recovery（无 system 参与）
        if self._flag('recovery_only_mode'):
            if not Path(self.bootimg).exists():
                print(f"【缺失文件】底包Recovery镜像 {self.bootimg} 不存在", file=self.std)
                return False
            port_boot, _port_sys = self.port_source
            if not Path(port_boot).exists():
                print(f"【缺失文件】移植Recovery镜像 {port_boot} 不存在", file=self.std)
                return False
            return True
        # kernel-only 模式：只需底包boot + 移植源boot（无 system 参与）
        if self._flag('kernel_only_mode'):
            if not Path(self.bootimg).exists():
                print(f"【缺失文件】底包boot镜像 {self.bootimg} 不存在", file=self.std)
                return False
            if self.source_type == 'zip':
                if not Path(self.port_source).exists():
                    print(f"【缺失文件】移植包 {self.port_source} 不存在", file=self.std)
                    return False
            else:
                port_boot, _port_sys = self.port_source
                if not Path(port_boot).exists():
                    print(f"【缺失文件】移植用boot.img {port_boot} 不存在", file=self.std)
                    return False
            return True
        # 检查底包
        for i in (self.sysimg, self.bootimg):
            if not Path(i).exists():
                print(f"【缺失文件】底包文件 {i} 不存在", file=self.std)
                return False
        # 检查移植源
        if self.source_type == 'zip':
            if not Path(self.port_source).exists():
                print(f"【缺失文件】移植包 {self.port_source} 不存在", file=self.std)
                return False
        else:
            port_boot, port_sys = self.port_source
            if not Path(port_boot).exists():
                print(f"【缺失文件】移植用boot.img {port_boot} 不存在", file=self.std)
                return False
            if not Path(port_sys).exists():
                print(f"【缺失文件】移植用system.img {port_sys} 不存在", file=self.std)
                return False
        return True

    def _flag(self, item: str) -> bool:
        """读取移植项开关。优先顶层键（UI 设置方式），回退到 flags 字典。"""
        return bool(self.items.get(item, self.items.get('flags', {}).get(item, False)))

    def __print_boot_info(self, label: str, bootdir: Path):
        """自动读取并打印 boot 镜像信息（内核版本/GCC/boot头参数）。"""
        rows = []
        for kname in ("kernel", "kernel.gz"):
            if bootdir.joinpath(kname).exists():
                lv, gcc = _extract_linux_ver(bootdir.joinpath(kname))
                if lv:
                    rows.append(("内核版本", lv + (f"（GCC {gcc}）" if gcc else "")))
                break
        bi = _read_bootinfo(bootdir.joinpath("bootinfo.txt"))
        for key, label2 in (("base", "base地址"), ("ramdisk_addr", "ramdisk地址"),
                            ("second_addr", "second地址"), ("tags_addr", "tags地址"),
                            ("page_size", "页大小"), ("name", "boot名称"),
                            ("cmdline", "cmdline")):
            if bi.get(key):
                rows.append((label2, bi[key]))
        _print_rows(self.std, f"【信息】{label} boot.img", rows)

    def __print_system_info(self, label: str, prop_path: str, sys_dir: str):
        """自动读取并打印 system 镜像信息（build.prop 关键字段 + 目录布局）。"""
        _print_rows(self.std, f"【信息】{label} system.img",
                    _system_info_rows(prop_path, sys_dir))

    def execv(self, cmd, verbose=False):
        """
        执行系统命令（优化版）
        :param cmd: 命令列表
        :param verbose: 是否输出原始命令和完整输出
        :return: (返回码, 命令输出字节串)
        """
        if verbose:
            print(f"【执行命令】{' '.join(cmd)}", file=self.std)
        
        creationflags = subprocess.CREATE_NO_WINDOW if osname == 'nt' else 0
        # 防御：Linux 下 zip 解压可能丢失执行权限，执行前确保目标二进制可执行（#62）
        if osname != 'nt' and cmd and isinstance(cmd[0], str):
            try:
                os.chmod(cmd[0], 0o755)
            except OSError:
                pass
        try:
            ret = subprocess.run(
                cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags
            )
            cmd_output = ret.stdout
            ret_code = ret.returncode
        except Exception as e:
            err_msg = f"【执行失败】无法执行命令：{str(e)}"
            self.std.write(err_msg + "\n")
            return (-1, err_msg.encode('utf-8'))
        
        if verbose:
            output_str = cmd_output.decode('utf-8', errors='ignore')
            print(f"【命令输出】{output_str}", file=self.std)
        
        return (ret_code, cmd_output)

    def __decompress_portzip(self):
        outdir = Path("tmp/rom")
        if outdir.exists():
            print(f"【清理临时文件】删除已有 tmp/rom 目录", file=self.std)
            _rmtree(outdir)
        outdir.mkdir(parents=True)
        
        # Recovery 模式：无 system 参与，移植源 recovery 由 __port_boot 直接处理
        if self._flag('recovery_only_mode'):
            print(f"【Recovery模式】跳过 system 复制，移植源 recovery 直接进入移植流程", file=self.std)
            return
        # kernel-only 模式：无 system 参与，移植源仅需提供 boot
        if self._flag('kernel_only_mode'):
            if self.source_type == 'zip':
                print(f"【解压移植包】正在解压 {self.port_source} 到 tmp/rom...", file=self.std)
                ziputil.decompress(self.port_source, str(outdir))
                print(f"【解压完成】移植包已解压到 tmp/rom", file=self.std)
            else:
                port_boot, _port_sys = self.port_source
                Path(outdir.joinpath("boot.img")).write_bytes(Path(port_boot).read_bytes())
                print(f"【kernel-only】仅复制移植源 boot.img（不处理 system）", file=self.std)
            return

        if self.source_type == 'zip':
            print(f"【解压移植包】正在解压 {self.port_source} 到 tmp/rom...", file=self.std)
            ziputil.decompress(self.port_source, str(outdir))
            print(f"【解压完成】移植包已解压到 tmp/rom", file=self.std)
        else:
            print(f"【复制镜像】正在复制移植用镜像文件到 tmp/rom...", file=self.std)
            port_boot, port_sys = self.port_source
            # 复制到tmp/rom供后续处理
            Path(outdir.joinpath("boot.img")).write_bytes(Path(port_boot).read_bytes())
            Path(outdir.joinpath("system.img")).write_bytes(Path(port_sys).read_bytes())
            print(f"【复制完成】boot.img和system.img已复制到 tmp/rom", file=self.std)
    
    def __port_boot(self) -> bool:
        def __replace(src: Path, dest: Path):
            print(f"【文件替换】{src.name} -> {dest.parent}/{dest.name}...", file=self.std)
            dest.parent.mkdir(parents=True, exist_ok=True)
            _clear_attrs(dest)
            dest.write_bytes(src.read_bytes())
            return True
        
        basedir = Path("tmp/base")
        portdir = Path("tmp/port")
        
        # 清理旧目录
        if basedir.exists():
            _rmtree(basedir)
        if portdir.exists():
            _rmtree(portdir)
        basedir.mkdir(parents=True)
        portdir.mkdir(parents=True)
        
        # Recovery 模式处理 recovery.img，否则处理 boot.img
        imgname = 'recovery.img' if self._flag('recovery_only_mode') else 'boot.img'
        labelname = 'Recovery镜像' if self._flag('recovery_only_mode') else 'boot.img'
        
        # 复制底包镜像并解包
        print(f"【处理底包】复制底包{labelname}到 tmp/base...", file=self.std)
        basedir.joinpath(imgname).write_bytes(Path(self.bootimg).read_bytes())
        base = basedir.joinpath(imgname)
        
        # 处理移植源boot.img
        if self.source_type == 'zip':
            try:
                print(f"【提取boot.img】从移植包中提取boot.img...", file=self.std)
                ziputil.extract_onefile(self.port_source, "boot.img", "tmp/port/")
            except Exception as e:
                err_msg = f"【提取失败】无法从移植包解压boot.img：{str(e)}"
                print(err_msg, file=self.std)
                return False
        else:
            port_boot, _ = self.port_source
            print(f"【复制{labelname}】复制移植用{labelname}到 tmp/port...", file=self.std)
            Path("tmp/port").joinpath(imgname).write_bytes(Path(port_boot).read_bytes())
        
        port = Path(portdir.joinpath(imgname))
        
        # 解包镜像（recovery 模式下为 recovery.img）
        print(f"【解包{imgname}】正在解包底包{imgname}...", file=self.std)
        bootutil(str(base)).unpack()
        print(f"【解包{imgname}】正在解包移植源{imgname}...", file=self.std)
        bootutil(str(port)).unpack()

        # 自动读取并打印底包/移植源 boot 信息
        self.__print_boot_info("底包", basedir)
        self.__print_boot_info("移植源", portdir)
        
        # 执行移植逻辑（recovery 模式下为 recovery.img）
        print(f"【开始移植】执行{imgname}移植逻辑...", file=self.std)
        for item in self.items['flags']:
            item_flag = self._flag(item)
            if not item_flag:
                continue
            
            match item:
                case 'replace_kernel':
                    print(f"【移植项】替换内核文件...", file=self.std)
                    for i in self.items.get('replace', {}).get('kernel', []):
                        if basedir.joinpath(i).exists():
                            print(f"  - 替换 {i}", file=self.std)
                            __replace(basedir.joinpath(i), portdir.joinpath(i))
                        else:
                            print(f"  - 跳过 {i}（底包中不存在）", file=self.std)
                    # 底包只有一种内核格式时，清掉移植源残留的另一格式，防止 repack 误选
                    if basedir.joinpath('kernel').exists() and not basedir.joinpath('kernel.gz').exists():
                        stale = portdir.joinpath('kernel.gz')
                        if stale.exists():
                            print("  - 移除移植源残留的 kernel.gz（底包为未压缩内核）", file=self.std)
                            stale.unlink()
                    if basedir.joinpath('kernel.gz').exists() and not basedir.joinpath('kernel').exists():
                        stale = portdir.joinpath('kernel')
                        if stale.exists():
                            print("  - 移除移植源残留的 kernel（底包为压缩内核）", file=self.std)
                            stale.unlink()
                case 'replace_fstab':
                    print(f"【移植项】替换分区表文件...", file=self.std)
                    for i in self.items.get('replace', {}).get('fstab', []):
                        if basedir.joinpath(i).exists():
                            print(f"  - 替换 {i}", file=self.std)
                            __replace(basedir.joinpath(i), portdir.joinpath(i))
                        else:
                            print(f"  - 跳过 {i}（底包中不存在）", file=self.std)
                case 'replace_init':
                    # #76：空值守卫——方案 replace 未配置 init 条目时跳过，避免静默空转（与 #55补 对齐）
                    if not self.items.get('replace', {}).get('init'):
                        print("  - 跳过（当前方案 replace 配置无 init 条目）", file=self.std)
                        continue
                    print(f"【移植项】替换ramdisk init配置文件...", file=self.std)
                    for i in self.items.get('replace', {}).get('init', []):
                        if basedir.joinpath(i).exists():
                            print(f"  - 替换 {i}", file=self.std)
                            __replace(basedir.joinpath(i), portdir.joinpath(i))
                        else:
                            print(f"  - 跳过 {i}（底包中不存在）", file=self.std)
                case 'selinux_permissive':
                    print(f"【移植项】开启SELinux宽容模式...", file=self.std)
                    if portdir.joinpath("bootinfo.txt").exists():
                        with portdir.joinpath("bootinfo.txt").open("r+", encoding="utf-8-sig", newline='\n') as f:
                            lines = [i.rstrip() for i in f.readlines()]
                            if any("androidboot.selinux=permissive" in line for line in lines):
                                print(f"  - 已开启SELinux宽容模式，无需重复操作", file=self.std)
                                continue
                            f.truncate(0)
                            f.seek(0, 0)
                            for line in lines:
                                if line.startswith("cmdline:"):
                                    f.write(line + " androidboot.selinux=permissive\n")
                                else:
                                    f.write(line + '\n')
                        print(f"  - SELinux宽容模式已开启", file=self.std)
                    else:
                        print(f"  - 跳过（未找到bootinfo.txt）", file=self.std)
                case 'enable_adb':
                    print(f"【移植项】开启ADB调试...", file=self.std)
                    if portdir.joinpath("initrd/default.prop").exists():
                        with proputil(str(portdir.joinpath("initrd/default.prop"))) as p:
                            kv = [
                                ('ro.secure', '0'), 
                                ('ro.adb.secure', '0'), 
                                ('ro.debuggable', '1'), 
                                ('persist.sys.usb.config', 'mtp,adb')
                            ]
                            for key, value in kv:
                                p.setprop(key, value)
                                print(f"  - 设置 {key} = {value}", file=self.std)
                        print(f"  - ADB调试已开启", file=self.std)
                    else:
                        print(f"  - 跳过（未找到default.prop）", file=self.std)
                case 'fix_storage':
                    # AMG 教程：收敛外置存储拓扑（删 /devices/ 声明 + 补标准 voldmanaged 行 + init.rc 存储修正）
                    print(f"【移植项】存储修复（AMG 教程）...", file=self.std)
                    fixdir = portdir.joinpath("initrd")
                    if not fixdir.is_dir():
                        print(f"  - 跳过（未找到 initrd 目录）", file=self.std)
                        continue
                    # 1) fstab：删除带 /devices/ 的存储行，补 msdc.1 + usbotg 标准行
                    fstabs = sorted(p for p in fixdir.glob("fstab*") if p.is_file())
                    if not fstabs:
                        print(f"  - 跳过 fstab（initrd 中未找到 fstab 文件）", file=self.std)
                    for fstab in fstabs:
                        try:
                            lines = fstab.read_text(encoding="utf-8", errors="ignore").splitlines()
                        except Exception as e:
                            print(f"  - 跳过 {fstab.name}（读取失败：{e}）", file=self.std)
                            continue
                        keep = [ln for ln in lines if not (ln.lstrip().startswith("/devices/") and "voldmanaged=" in ln)]
                        add = []
                        if not any("voldmanaged=sdcard1:auto" in ln for ln in keep):
                            add.append("/devices/platform/mtk-msdc.1/mmc_host* auto auto defaults voldmanaged=sdcard1:auto,encryptable=userdata")
                        if not any("voldmanaged=usbotg:auto" in ln for ln in keep):
                            add.append("/devices/platform/mt_usb auto auto defaults voldmanaged=usbotg:auto")
                        removed = len(lines) - len(keep)
                        if removed or add:
                            out = keep + ([""] + add if add else [])
                            fstab.write_text("\n".join(out) + "\n", encoding="utf-8", newline='\n')  # newline='\n' 强制 LF：CRLF 会让 fstab 解析残留 \r（三张SD卡/挂载异常）
                            print(f"  - 修正 {fstab.name}（删除 {removed} 行 /devices/ 存储声明，补充 sdcard1/usbotg 标准行）", file=self.std)
                        else:
                            print(f"  - {fstab.name} 无需修改", file=self.std)
                    # 2) init.rc：删 ro.vold.primary_physical、补 symlink、on fs 块补 protect/mount_all
                    #    （AMG 教程只改平台主 rc：init.mtXXXX.rc，芯片名取自 fstab.mtXXXX；
                    #      其余 init*.rc（usb/aee/environ 等变体）不动，避免误改）
                    rcs = []
                    if fstabs:
                        chip_fstabs = [p.name for p in fstabs if ".mt" in p.name]
                        chip_name = chip_fstabs[0].replace("fstab.", "") if chip_fstabs else None
                        if chip_name:
                            rcs = sorted(p for p in fixdir.glob(f"init.{chip_name}.rc") if p.is_file())
                    if not rcs:
                        print(f"  - 跳过 init.rc（未定位到平台主文件 init.<chip>.rc）", file=self.std)
                    fstab_name = None
                    if fstabs:
                        # 优先 fstab.mtXXXX（芯片名形式，符合教程），其次裸 fstab
                        chip_fstabs = [p.name for p in fstabs if ".mt" in p.name]
                        fstab_name = chip_fstabs[0] if chip_fstabs else fstabs[0].name
                    for rc in rcs:
                        try:
                            lines = rc.read_text(encoding="utf-8", errors="ignore").splitlines()
                        except Exception as e:
                            print(f"  - 跳过 {rc.name}（读取失败：{e}）", file=self.std)
                            continue
                        orig_len = len(lines)
                        # 2.1) 删除 setprop ro.vold.primary_physical 1
                        lines = [ln for ln in lines if "setprop ro.vold.primary_physical 1" not in ln]
                        # 2.2) on init 块：将旧式 sdcard symlink 替换为标准形式
                        #      （symlink storage/sdcard /sdcard + /mnt/sdcard；已是标准形式则跳过）
                        init_idx = None
                        for i, ln in enumerate(lines):
                            if ln.strip() == "on init":
                                init_idx = i
                                break
                        if init_idx is not None:
                            end = len(lines)
                            for j in range(init_idx + 1, len(lines)):
                                if lines[j].strip().startswith("on ") and lines[j].strip() != "on init":
                                    end = j
                                    break
                            block = lines[init_idx:end]
                            has_std = any("symlink storage/sdcard /sdcard" in ln for ln in block) and \
                                      any("symlink storage/sdcard /mnt/sdcard" in ln for ln in block)
                            if not has_std:
                                # 去掉块内旧式 /sdcard symlink 行（如 symlink /sdcard /mnt/sdcard）
                                block = [ln for ln in block
                                         if not (ln.strip().startswith("symlink") and "/sdcard" in ln
                                                 and "storage/sdcard" not in ln)]
                                new_block = block[:1] + [
                                    "    symlink storage/sdcard /sdcard",
                                    "    symlink storage/sdcard /mnt/sdcard",
                                ] + block[1:]
                                lines = lines[:init_idx] + new_block + lines[end:]
                        # 2.3) on fs 块补 mkdir protect_f/protect_s、mount_all、Mount_END
                        fs_idx = None
                        for i, ln in enumerate(lines):
                            if ln.strip() == "on fs":
                                fs_idx = i
                                break
                        if fs_idx is not None:
                            add_fs = []
                            if not any(ln.strip().startswith("mkdir /protect_f") for ln in lines):
                                add_fs.append("    mkdir /protect_f 0771 system system")
                            if not any(ln.strip().startswith("mkdir /protect_s") for ln in lines):
                                add_fs.append("    mkdir /protect_s 0771 system system")
                            if not any(ln.strip().startswith("mount_all /fstab") for ln in lines) and fstab_name:
                                add_fs.append(f"    mount_all /{fstab_name}")
                            if not any("INIT:NAND:Mount_END" in ln for ln in lines):
                                add_fs.append('    write /proc/bootprof "INIT:NAND:Mount_END"')
                            if add_fs:
                                lines[fs_idx + 1:fs_idx + 1] = add_fs
                        changed = len(lines) != orig_len
                        if changed:
                            rc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline='\n')  # newline='\n' 强制 LF：CRLF 会破坏 init 按 \n 切行（service 注册残留 \r，WiFi 不可用根因）
                            print(f"  - 修正 {rc.name}（删除 primary_physical、补充存储 symlink/protect/mount_all）", file=self.std)
                        else:
                            print(f"  - {rc.name} 无需修改", file=self.std)
                    print(f"  - 存储修复完成", file=self.std)

        # 7.1+ 移植适配：p2p_supplicant 服务标志与底包对齐（只补齐，绝不删除）
        # wpa_supplicant / p2p_supplicant 在 AOSP 中本就是 disabled + oneshot：
        #   disabled —— 开机不由 init 自动拉起，由 framework 通过 ctl.start 管理生命周期；
        #   oneshot  —— 退出后 init 不自动重启，崩溃后等 framework 干净地重新 ctl.start。
        # 若移植源（通常是更低安卓版本）缺少这两个标志，按底包补齐；移植源已具备时保持原样（空操作）。
        # 严禁删除 oneshot：否则 init 会在 supplicant 每次退出后无限自动重启，这些实例 framework
        # 无法接管，表现为每约 5 秒 "Successfully initialized wpa_supplicant" 后静默死亡、
        # framework 永久 "Supplicant not running, cannot connect"（实测 MTK combo 机型必现）。
        try:
            bdir = basedir.joinpath("initrd")
            pdir = portdir.joinpath("initrd")

            def parse_services(text):
                lines = text.splitlines()
                blocks = {}
                i = 0
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith("service "):
                        parts = s.split()
                        svc = parts[1] if len(parts) > 1 else ""
                        j = i + 1
                        while j < len(lines):
                            l2 = lines[j]
                            if l2.strip() == "" or l2[:1] in (" ", "\t"):
                                j += 1
                                continue
                            break
                        blocks[svc] = (i, j, lines[i:j])
                        i = j
                    else:
                        i += 1
                return lines, blocks

            if bdir.is_dir() and pdir.is_dir():
                for brc in sorted(bdir.glob("init.mt*.rc")):
                    prc = pdir.joinpath(brc.name)
                    if not prc.is_file():
                        continue
                    btext = brc.read_text(encoding="utf-8", errors="ignore")
                    ptext = prc.read_text(encoding="utf-8", errors="ignore")
                    if not ('service p2p_supplicant' in btext and 'socket wpa_wlan0' in btext
                            and 'service p2p_supplicant' in ptext):
                        continue
                    _, bblocks = parse_services(btext)
                    plines, pblocks = parse_services(ptext)
                    if 'p2p_supplicant' not in bblocks or 'p2p_supplicant' not in pblocks:
                        continue
                    bblk = bblocks['p2p_supplicant'][2]
                    pbi, pbj, pblk = pblocks['p2p_supplicant']

                    def opt_present(blk, opt):
                        return any(l.strip() == opt for l in blk)

                    need = [o for o in ('disabled', 'oneshot')
                            if opt_present(bblk, o) and not opt_present(pblk, o)]
                    if not need:
                        print(f"  - {brc.name} p2p_supplicant 服务标志（disabled/oneshot）已与底包一致，无需修改", file=self.std)
                        continue
                    indent = "\t"
                    for l in pblk:
                        st = l.strip()
                        if st in ('class main', 'disabled', 'oneshot') or st.startswith(('socket ', 'class ', 'group ', 'user ')):
                            indent = l[:len(l) - len(l.lstrip())] or "\t"
                            break
                    newblk = list(pblk)
                    while newblk and newblk[-1].strip() == "":
                        newblk.pop()
                    newblk.extend(f"{indent}{o}" for o in need)
                    prc.write_text("\n".join(plines[:pbi] + newblk + plines[pbj:]) + "\n", encoding="utf-8", newline='\n')  # newline='\n' 强制 LF，与 init.rc 同防 CRLF 破坏
                    print(f"  - 适配 {brc.name}：p2p_supplicant 对齐底包补齐 {'/'.join(need)}（disabled+oneshot，由 framework 管理 supplicant 生命周期）", file=self.std)
        except Exception as e:
            print(f"  - 跳过 p2p_supplicant 服务对齐（{e}）", file=self.std)

        # 网络修复（set_cn_servers）依赖 CM 系 init.d 机制：/system/bin/sysinit 遍历执行 /system/etc/init.d/*。
        # 若 boot ramdisk 的 init.rc 无 sysinit 服务定义（如 replace_init 用底包 init.rc 覆盖移植源、
        # MTK 原厂底包通常无 sysinit），则 init.d 脚本开机不会执行、网络修复失效。
        # 此处在 repack 前向根 init.rc 补齐标准 sysinit 服务（仅在勾选网络修复时，无副作用最小改动）。
        if self._flag('set_cn_servers'):
            try:
                initrc_path = portdir.joinpath("initrd/init.rc")
                if initrc_path.is_file():
                    rc_text = initrc_path.read_text(encoding="utf-8", errors="ignore")
                    if "service sysinit" not in rc_text:
                        with initrc_path.open('a', encoding='utf-8', newline='\n') as f:  # newline='\n' 强制 LF：CRLF 会破坏 init 按 \n 切行
                            f.write(
                                "\n# MTK 移植工具注入：启用 /system/etc/init.d 开机执行（网络修复等依赖此机制）\n"
                                "service sysinit /system/bin/sysinit\n"
                                "    class main\n"
                                "    user root\n"
                                "    group root\n"
                                "    oneshot\n"
                                "\n"
                                "# 显式触发器：sys.boot_completed=1 由框架必经设置，确保 sysinit 在 settings 服务就绪后执行。\n"
                                "# 仅靠 class main 在部分 MTK 底包 init 上不会拉起（class_start 挂在 on nonencrypted/decrypt，时机不可靠）\n"
                                "on property:sys.boot_completed=1\n"
                                "    start sysinit\n"
                            )
                        print("  - 已向 init.rc 注入 sysinit 服务（启用 init.d 开机执行，网络修复依赖）", file=self.std)
                    else:
                        print("  - init.rc 已含 sysinit 服务，无需注入", file=self.std)
                else:
                    print("  - 跳过 sysinit 注入（boot ramdisk 未找到 init.rc）", file=self.std)
            except OSError as e:
                print(f"  - 注入 sysinit 服务失败（{e}）", file=self.std)

        # 重新打包镜像
        print(f"【打包{imgname}】正在重新打包移植后的{imgname}...", file=self.std)
        bootutil(str(port)).repack()
        outboot = Path(portdir.joinpath("boot-new.img"))
        to = Path("tmp/rom").joinpath(imgname)
        __replace(outboot, to)
        
        # Magisk修补
        if self.items.get("patch_magisk") and op.isfile(self.items.get("magisk_apk")):
            print(f"【Magisk修补】开始修补boot.img...", file=self.std)
            parseMagiskApk(self.items['magisk_apk'], self.items['target_arch'], self.std)
            bp = BootPatcher(magiskboot_bin, legacysar=True, log=self.std)
            if bp.patch(str(to)):
                __replace(Path("new-boot.img"), to)
                unlink("new-boot.img")
                print(f"【Magisk修补】boot.img修补完成", file=self.std)
            else:
                print(f"【Magisk修补】boot.img修补失败", file=self.std)
            bp.cleanup()
        else:
            if self.items.get("patch_magisk"):
                print(f"【Magisk修补】跳过（未找到magisk.apk）", file=self.std)
        
        print(f"【{'recovery移植完成' if self._flag('recovery_only_mode') else 'boot移植完成'}】{imgname}处理完毕", file=self.std)
        return True

    def __port_system(self):
        def __replace(val: str):
            print(f"【文件替换】底包/{val} -> 移植源/{val}...", file=self.std)
            src = base_prefix.joinpath(val)
            dst = port_prefix.joinpath(val)

            def _merge_copy(s, d):
                # 合并复制：覆盖前清掉目标只读位（Windows 只读文件无法直接截断写入）
                if op.lexists(d):
                    _clear_attrs(Path(d))
                copy2(s, d)

            # firmware 目录按硬件/芯片名单个加载，多文件共存无害，采用合并覆盖：
            # 底包固件覆盖同名项，同时保留移植源独有、底包没有的固件（如传感器固件）。
            # mddb / GPU egl / 音频参数 / 热配置等必须与底包对应 HAL/modem 严格配套，仍整套替换。
            merge_dir = 'firmware' in val.replace('\\', '/').lower()
            if "*" in val:
                matched = 0
                for file in glob.glob(op.join(str(base_prefix), val)):
                    matched += 1
                    relfile = op.relpath(file, str(base_prefix))
                    dst2 = port_prefix.joinpath(relfile)
                    src_file = base_prefix.joinpath(relfile)
                    if op.isdir(src_file):
                        # 通配命中目录：firmware 合并，其余整体目录替换
                        if merge_dir:
                            if dst2.exists() and not dst2.is_dir():
                                _clear_attrs(dst2)
                                dst2.unlink()
                            copytree(src_file, dst2, dirs_exist_ok=True, copy_function=_merge_copy)
                            print(f"  - 合并通配目录（保留移植源独有文件）{file}", file=self.std)
                        else:
                            if dst2.exists():
                                if dst2.is_dir():
                                    _rmtree(dst2)
                                else:
                                    _clear_attrs(dst2)
                                    dst2.unlink()
                            copytree(src_file, dst2)
                            print(f"  - 替换通配目录 {file}", file=self.std)
                    else:
                        dst2.parent.mkdir(parents=True, exist_ok=True)
                        _clear_attrs(dst2)
                        dst2.write_bytes(src_file.read_bytes())
                        print(f"  - 替换通配文件 {file}", file=self.std)
                if matched == 0:
                    print(f"  - 未匹配任何文件（底包中无 {val}）", file=self.std)
            elif src.is_dir():
                if merge_dir:
                    if dst.exists() and not dst.is_dir():
                        _clear_attrs(dst)
                        dst.unlink()
                    copytree(src, dst, dirs_exist_ok=True, copy_function=_merge_copy)
                    print(f"  - 合并替换目录 {val}（底包覆盖同名，保留移植源独有固件）", file=self.std)
                else:
                    if dst.exists():
                        if dst.is_dir():
                            _rmtree(dst)
                        else:
                            _clear_attrs(dst)
                            dst.unlink()
                    copytree(src, dst)
                    print(f"  - 替换目录 {val}", file=self.std)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                _clear_attrs(dst)
                dst.write_bytes(src.read_bytes())
                print(f"  - 替换文件 {val}", file=self.std)
            else:
                print(f"  - 跳过（底包中不存在 {val}）", file=self.std)
        
        # 检查并解包底包system.img（分块计算MD5，避免大文件全读入内存）
        unpack_flag = False
        sysmd5 = md5()
        with open(self.sysimg, 'rb') as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                sysmd5.update(chunk)
        sysmd5 = sysmd5.hexdigest()
        md5path = Path("base/system.md5")
        
        # MD5不一致、或MD5一致但目录不存在（上次解包中途失败/手动删了目录），都需要解包
        need_unpack = not md5path.exists() or md5path.read_text().strip() != sysmd5 or not Path("base/system").exists()
        if need_unpack:
            unpack_flag = True
            if Path("base/system").exists():
                print(f"【清理缓存】删除旧的base/system目录", file=self.std)
                _rmtree("base/system")

        if unpack_flag:
            print(f"【解包system.img】正在解包底包system.img到 base/system...", file=self.std)
            _extractor = Extractor()
            _extractor.main(self.sysimg, "base/system")
            for _w in _extractor.warnings:
                print(f"  - {_w}", file=self.std)
            # MD5 必须等解包【成功之后】再写入。
            # 若在解包前写入，一旦解包中途失败，下次运行会因 MD5 一致而跳过解包，
            # 静默使用不完整的 base/system（会导致底包文件被误判为"不存在"而跳过替换）。
            md5path.parent.mkdir(parents=True, exist_ok=True)
            md5path.write_text(sysmd5)
            print(f"【解包完成】底包system.img解包完毕", file=self.std)
        else:
            print(f"【使用缓存】base/system目录已存在且MD5一致，跳过解包", file=self.std)
        
        # 解包移植源system.img
        if Path("tmp/rom/system.new.dat").exists():
            print(f"【格式转换】检测到system.new.dat，转换为img格式...", file=self.std)
            self.sdat = True
            with open("tmp/rom/system.transfer.list", encoding='utf-8-sig') as t:
                self.sdat_ver = int(t.readline().rstrip())
            sdat2img("tmp/rom/system.transfer.list", "tmp/rom/system.new.dat", "tmp/rom/system.img")
            print(f"【转换完成】system.new.dat已转为system.img", file=self.std)
        
        if Path("tmp/rom/system.img").exists():
            print(f"【解包system.img】正在解包移植源system.img到 tmp/rom/system...", file=self.std)
            Extractor().main("tmp/rom/system.img", "tmp/rom/system")
            print(f"【解包完成】移植源system.img解包完毕", file=self.std)

        # 自动读取并打印底包/移植源 system 信息
        self.__print_system_info("底包", "base/system/build.prop", "base/system")
        self.__print_system_info("移植源", "tmp/rom/system/build.prop", "tmp/rom/system")

        # === API 版本检测与跨大版本警告 ===
        _API_VER = {19: "4.4", 20: "4.4W", 21: "5.0", 22: "5.1", 23: "6.0",
                    24: "7.0", 25: "7.1", 26: "8.0", 27: "8.1", 28: "9",
                    29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14", 35: "15"}
        def _read_sdk(prop_path):
            p = Path(prop_path)
            if not p.exists():
                return None
            try:
                with proputil(str(p)) as pp:
                    s = pp.getprop('ro.build.version.sdk')
                return int(s) if s else None
            except Exception:
                return None

        base_sdk = _read_sdk("base/system/build.prop")
        port_sdk = _read_sdk("tmp/rom/system/build.prop")
        if base_sdk is not None:
            ver = _API_VER.get(base_sdk, f"API {base_sdk}")
            print(f"【版本检测】底包 Android {ver}（API {base_sdk}）", file=self.std)
        if port_sdk is not None:
            ver = _API_VER.get(port_sdk, f"API {port_sdk}")
            print(f"【版本检测】移植源 Android {ver}（API {port_sdk}）", file=self.std)
        if base_sdk is None or port_sdk is None:
            print(f"【提示】未能完整读取底包/移植源的 Android 版本（build.prop 缺失或无 ro.build.version.sdk）", file=self.std)
            print(f"  音频驱动替换将按勾选执行，无法进行跨版本自动保护；", file=self.std)
            print(f"  若开机卡第二屏且 logcat 出现 audioserver/audioflinger 崩溃，请手动取消音频相关勾选后重试。", file=self.std)

        # 高版本警告：Android 8.0+ 可能引入 Treble/VNDK，文件替换移植不一定适用
        for label, sdk in (("底包", base_sdk), ("移植源", port_sdk)):
            if sdk is not None and sdk > 25:
                ver = _API_VER.get(sdk, f"API {sdk}")
                print(f"【警告】{label} 为 Android {ver}（API {sdk}），可能已启用 Treble/VNDK", file=self.std)
                print(f"  本工具面向无 VNDK 的老设备（Android 7.1.2 及以下）", file=self.std)
                print(f"  有 VNDK 的设备建议直接刷 GSI，文件替换移植可能导致硬件不工作", file=self.std)

        # 跨大版本警告：底包与移植源 API 差异 >=3 视为跨大版本
        if base_sdk is not None and port_sdk is not None and abs(base_sdk - port_sdk) >= 3:
            bv = _API_VER.get(base_sdk, f"API {base_sdk}")
            pv = _API_VER.get(port_sdk, f"API {port_sdk}")
            print(f"【警告】跨大版本移植：底包 Android {bv} → 移植源 Android {pv}", file=self.std)
            print(f"  跨大版本 HAL 接口可能不兼容，建议同平台同 Android 大版本移植", file=self.std)

        # === 跨 Android 大版本硬件替换策略判定 ===
        # 独立服务型 HAL 的 ABI 随 Android 主版本变化（7.0 起 audioserver/mediacodec 独立，
        # 相机/RIL/WiFi/蓝牙接口随版本演进）。同一主版本内（7.0↔7.1、5.0↔5.1）基本兼容可正常
        # 替换；主版本不同时把底包旧 HAL 盖进移植源，会让对应独立进程崩溃（音频即表现为卡第二屏、
        # ADB 可连）。按主版本号判断，比上面的“API 差≥3”更敏感（6.0 API23 → 7.1 API25 差仅 2 也能抓到）。
        if cross_major_version(base_sdk, port_sdk):
            self._cross_major = True
            bv = _API_VER.get(base_sdk, f"API {base_sdk}")
            pv = _API_VER.get(port_sdk, f"API {port_sdk}")
            print(f"【严重警告】检测到跨 Android 大版本移植：底包 Android {bv} → 移植源 Android {pv}", file=self.std)
            print(f"  下列【独立服务型】HAL/库（音频/相机/媒体硬解/RIL/WiFi/蓝牙）跨大版本 ABI 不兼容，", file=self.std)
            print(f"  用底包旧库覆盖移植源可能导致对应进程崩溃（音频即卡第二屏、WiFi/蓝牙/信号不可用）。", file=self.std)
            print(f"  若已勾选这些替换项，本工具会【继续执行替换】但强烈建议取消；", file=self.std)
            print(f"  若未勾选，则保留移植源自带实现以保证开机（代价是对应功能可能不可用）。", file=self.std)
            print(f"  图形 gralloc/GPU(mali) 与移植源图形框架强成套，跨大版本已【保留移植源】、跳过替换；", file=self.std)
            print(f"    用底包旧 gralloc/GPU 覆盖会黑屏/壁纸异常（词典笔 5.0→7.1.2 实证）；同版本移植则照常替换。", file=self.std)
            print(f"    hwcomposer 例外：与底包内核 DISP/DSI 驱动强绑定，跨大版本【保留底包】（照常替换），", file=self.std)
            print(f"    移植源高版本 hwcomposer 在底包内核上黑屏/壁纸异常（词典笔实证：换回底包 hwcomposer 立即正常）。", file=self.std)
            print(f"  传感器/灯/电源/震动/GPS 等稳定 HAL，以及 firmware/mddb/按键布局等硬件数据照常替换；", file=self.std)
            print(f"    modem/WiFi/蓝牙固件与射频数据（firmware、mddb）与硬件绑定，也照常替换。", file=self.std)

        # 执行system移植逻辑
        print(f"【开始移植】执行system.img移植逻辑...", file=self.std)
        base_prefix = Path("base/system")
        port_prefix = Path("tmp/rom/system")

        # === 同平台通用（未列芯片/同平台自动识别）模式 ===
        # auto 不再用关键词全目录“瞎扫”（旧逻辑会把底包 audio.primary.* 等所有 hw HAL 一并盖进移植源，
        # 跨机型音频 HAL/框架错配即致 audioserver 崩溃、卡第二屏，Dream. mt6582 实证）。
        # 改为与手动方案【统一】：下方遍历 flags / replace 组，以 configs.json 各组里的路径/通配符为“识别词”，
        # 在底包 system 中精准 glob 命中后再替换；是否替换完全由该组 flag（界面勾选 / 默认开关）决定。
        # 默认矩阵（均衡）：GPU/显示HAL、传感器/灯/GPS/电源/震动/散热、firmware/mddb/按键/开机画面默认替换；
        # 相机/基带/WiFi/蓝牙同平台默认替换、跨大版本【提示高风险仍执行】；音频 HAL/引擎/功放默认【不替换】。
        if self._flag('auto_replace'):
            print(f"【自动移植】未列芯片·同平台模式：按内置硬件识别表精准匹配底包文件并替换...", file=self.std)

        for item in self.items['flags']:
            item_flag = self._flag(item)
            if not item_flag or item in ['replace_kernel', 'replace_fstab', 'replace_init']:
                continue
            
            if item.startswith("replace_"):
                replace_type = item[len("replace_"):]
                # 跨 Android 大版本：音频/相机/RIL/WiFi/蓝牙组为高风险项（独立服务型 HAL ABI 不兼容，
                # 覆盖会让对应进程崩溃，音频即表现为卡第二屏；详见版本检测处的严重警告）。
                # 不再整组静默跳过——改为提示高风险但仍执行，由用户自行决定（个别设备跨版本替换反而可用）。
                # 图形 gralloc/malidriver：跨大版本【跳过替换、保留移植源】——
                # 实测底包旧图形栈盖进高版本移植源会黑屏/壁纸异常（mt6582 词典笔 5.0→7.1.2 实证）。
                # hwcomposer 例外：直接与底包内核 DISP/DSI 驱动强绑定，跨大版本【保留底包】（照常替换），
                # 移植源高版本 hwcomposer 在底包内核上黑屏/壁纸异常（词典笔实证：换回底包 hwcomposer 立即正常）。
                # 同版本时照常替换；modem/wifi/bt 固件与射频数据由独立的 firmware、mddb 组继续替换。
                if self._cross_major and replace_type in GRAPHICS_REPLACE_GROUPS:
                    print(f"【移植项】替换{replace_type}相关文件...", file=self.std)
                    print(f"  ! 跨大版本图形栈：{replace_type} 与移植源图形框架（surfaceflinger）强成套，", file=self.std)
                    print(f"  ! 用底包旧图形栈覆盖移植源会导致黑屏/壁纸异常（词典笔 5.0→7.1.2 实证）。", file=self.std)
                    print(f"  ! 已【保留移植源】图形栈、跳过替换；同版本移植仍会正常替换。", file=self.std)
                    continue
                if self._cross_major and replace_type == 'hwcomposer':
                    print(f"【移植项】替换hwcomposer相关文件...", file=self.std)
                    print(f"  ! 跨大版本：hwcomposer 与底包内核 DISP/DSI 驱动强绑定，", file=self.std)
                    print(f"  ! 移植源高版本 hwcomposer 在底包内核上黑屏/壁纸异常（词典笔 5.0→7.1.2 实证），", file=self.std)
                    print(f"  ! 已【保留底包】hwcomposer（照常替换）；gralloc/GPU 仍保留移植源。", file=self.std)
                if self._cross_major and replace_type in CROSS_SKIP_REPLACE_GROUPS:
                    print(f"【移植项】替换{replace_type}相关文件...", file=self.std)
                    print(f"  ! 跨大版本高风险：{replace_type} 为独立服务型 HAL，底包旧库覆盖移植源", file=self.std)
                    print(f"  ! 可能导致对应进程崩溃（音频卡第二屏 / WiFi/蓝牙/信号不可用）。", file=self.std)
                    print(f"  ! 已按勾选继续执行替换；若刷入后功能异常，请取消该项后重新移植。", file=self.std)
                # auto 模式下手动选项优先：若 replace 字典有配置则用手动路径覆盖自动替换结果
                if not self.items.get('replace', {}).get(replace_type):  # #55补：空值也跳过（防空转）
                    continue  # 该方案未配置此替换项的路径，跳过
                if replace_type in AUDIO_REPLACE_GROUPS:
                    print(f"  ! 【高风险警告】你手动开启了「{replace_type}」替换。", file=self.std)
                    print(f"  ! 音频硬件 HAL / 效果策略配置 / 功放库与移植源 ROM 的音频框架（audioflinger 等）强成套，", file=self.std)
                    print(f"  ! 跨机型覆盖底包音频——即使同芯片、同 Android 版本——也可能导致 audioserver 崩溃、卡第二屏或外放异常。", file=self.std)
                    print(f"  ! 该选项默认关闭以优先保证开机；若刷入后卡第二屏 / 无声音 / 炸外放，请取消「{replace_type}」后重新移植。", file=self.std)
                print(f"【移植项】替换{replace_type}相关文件...", file=self.std)
                for i in self.items['replace'][replace_type]:
                    if base_prefix.joinpath(i).exists() or "*" in i:
                        __replace(i)
                    else:
                        print(f"  - 跳过 {i}（底包中不存在）", file=self.std)
                continue
            
            match item:
                case 'single_simcard' | 'dual_simcard':
                    sim_type = "单卡" if item == 'single_simcard' else "双卡"
                    print(f"【移植项】修改为{sim_type}模式...", file=self.std)
                    build_prop_path = port_prefix.joinpath("build.prop")
                    if build_prop_path.exists():
                        with proputil(str(build_prop_path)) as p:
                            kv = [
                                ('persist.multisim.config', 'ss' if item == 'single_simcard' else 'dsds'),
                                ('persist.radio.multisim.config', 'ss' if item == 'single_simcard' else 'dsds'),
                                ('ro.telephony.sim.count', '1' if item == 'single_simcard' else '2'),
                                ('persist.dsds.enabled', 'false' if item == 'single_simcard' else 'true'),
                                ('ro.dual.sim.phone', 'false' if item == 'single_simcard' else 'true')
                            ]
                            for key, value in kv:
                                p.setprop(key, value)
                                print(f"  - 设置 {key} = {value}", file=self.std)
                        print(f"  - {sim_type}模式已配置完成", file=self.std)
                    else:
                        print(f"  - 跳过（未找到system/build.prop）", file=self.std)
                case 'fit_density':
                    print(f"【移植项】同步底包屏幕DPI...", file=self.std)
                    port_prop = port_prefix.joinpath("build.prop")
                    base_prop = base_prefix.joinpath("build.prop")
                    if port_prop.exists() and base_prop.exists():
                        with proputil(str(port_prop)) as pp, proputil(str(base_prop)) as bp:
                            dpi_value = bp.getprop('ro.sf.lcd_density')
                            if dpi_value:
                                pp.setprop('ro.sf.lcd_density', dpi_value)
                                print(f"  - 同步DPI值：{dpi_value}", file=self.std)
                                print(f"  - 提示：ro. 属性只写一次，若被更早来源（ramdisk/cust/lk）先设置，build.prop 中的值会被忽略，开机后请核实实际生效密度", file=self.std)
                            else:
                                print(f"  - 跳过（底包中未找到ro.sf.lcd_density）", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)
                case 'change_timezone':
                    print(f"【移植项】同步底包时区...", file=self.std)
                    port_prop = port_prefix.joinpath("build.prop")
                    base_prop = base_prefix.joinpath("build.prop")
                    if port_prop.exists() and base_prop.exists():
                        with proputil(str(port_prop)) as pp, proputil(str(base_prop)) as bp:
                            timezone = bp.getprop('persist.sys.timezone')
                            if timezone:
                                pp.setprop('persist.sys.timezone', timezone)
                                print(f"  - 同步时区：{timezone}", file=self.std)
                            else:
                                print(f"  - 跳过（底包中未找到persist.sys.timezone）", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)
                case 'change_locale':
                    print(f"【移植项】同步底包语言区域...", file=self.std)
                    port_prop = port_prefix.joinpath("build.prop")
                    base_prop = base_prefix.joinpath("build.prop")
                    if port_prop.exists() and base_prop.exists():
                        with proputil(str(port_prop)) as pp, proputil(str(base_prop)) as bp:
                            locale = bp.getprop('ro.product.locale') or bp.getprop('persist.sys.locale')
                            if locale:
                                pp.setprop('ro.product.locale', locale)
                                pp.setprop('persist.sys.locale', locale)
                                # language/region 拆分（locale 形如 zh-CN）
                                if '-' in locale:
                                    lang, region = locale.split('-', 1)
                                    pp.setprop('ro.product.locale.language', lang)
                                    pp.setprop('ro.product.locale.region', region)
                                print(f"  - 同步语言区域：{locale}", file=self.std)
                            else:
                                print(f"  - 跳过（底包中未找到 ro.product.locale / persist.sys.locale）", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)
                case 'set_cn_servers':
                    print(f"【移植项】切换网络连通性检测/时间服务器为国内节点...", file=self.std)
                    build_prop_path = port_prefix.joinpath("build.prop")
                    if build_prop_path.exists():
                        with proputil(str(build_prop_path)) as p:
                            kv = [
                                # 连通性检测 captive portal：Google -> 小米 MIUI
                                ('captive_portal_http_url', 'http://connect.rom.miui.com/generate_204'),
                                ('captive_portal_https_url', 'https://connect.rom.miui.com/generate_204'),
                                ('captive_portal_use_https', '0'),
                                # NTP 时间同步：Google -> 阿里云
                                ('ro.ntp.server', 'ntp.aliyun.com'),
                            ]
                            for key, value in kv:
                                p.setprop(key, value)
                                print(f"  - 设置 {key} = {value}", file=self.std)
                        print(f"  - 已写入 build.prop（兜底：部分框架/老版本仍读取 ro.* 属性）", file=self.std)
                    else:
                        print(f"  - 跳过 build.prop（未找到 system/build.prop）", file=self.std)
                    # Android 7.1+ 网络验证/时间服务器只读 settings 全局表（captive_portal_* / ntp_server），
                    # 不读 build.prop 的 ro.* 属性；settings 表存在 /data，system 镜像侧改不到。
                    # 方案：注入开机自启脚本，首次开机自动写 settings 后自删（需 root/ADB 权限执行）。
                    initd_dir = port_prefix.joinpath("etc/init.d")
                    try:
                        initd_dir.mkdir(parents=True, exist_ok=True)
                        script_path = initd_dir.joinpath("99cnfix.sh")
                        script = (
                            "#!/system/bin/sh\n"
                            "# MTK 移植工具注入：国内网络连通性检测 + NTP 时间服务器\n"
                            "# 开机自动写入 settings 全局表；幂等：已生效则跳过（恢复出厂清表后自动重写，持续生效）\n"
                            "if [ \"$(id -u)\" != \"0\" ]; then\n"
                            "  echo \"[cnfix] 非 root，跳过（需 root/ADB 权限）\" >> /data/local/tmp/cnfix.log 2>/dev/null\n"
                            "  exit 0\n"
                            "fi\n"
                            "# 等待系统完全启动、settings 服务可用（最多 120s）\n"
                            "i=0\n"
                            "while [ \"$(getprop sys.boot_completed)\" != \"1\" ] && [ $i -lt 60 ]; do\n"
                            "  sleep 2; i=$((i+1))\n"
                            "done\n"
                            "# 幂等守卫：已生效则跳过；恢复出厂设置会清空 settings 表，此处自动重写\n"
                            "if [ \"$(settings get global captive_portal_http_url 2>/dev/null)\" = \"http://connect.rom.miui.com/generate_204\" ]; then\n"
                            "  exit 0\n"
                            "fi\n"
                            "settings put global captive_portal_http_url http://connect.rom.miui.com/generate_204\n"
                            "settings put global captive_portal_https_url https://connect.rom.miui.com/generate_204\n"
                            "settings put global captive_portal_use_https 0\n"
                            "settings put global ntp_server ntp.aliyun.com\n"
                        )
                        # newline='\n' 强制 LF：CRLF 会破坏 sh 脚本（WiFi 修复同源教训）
                        with script_path.open('w', encoding='utf-8', newline='\n') as f:
                            f.write(script)
                        print(f"  - 已注入开机自启脚本 {script_path}（开机自动写 settings，幂等持续生效）", file=self.std)
                        # init.d 执行器检查：99cnfix.sh 依赖 /system/bin/sysinit 开机遍历执行；
                        # boot 侧 sysinit 服务注入已在 __port_boot 完成（勾选本条目时自动补齐）。
                        sysinit_exec = None
                        for cand in ("bin/sysinit", "xbin/sysinit"):
                            if port_prefix.joinpath(cand).exists():
                                sysinit_exec = cand
                                break
                        if sysinit_exec:
                            print(f"  - init.d 执行器已就位（/system/{sysinit_exec}），开机将自动执行 99cnfix.sh", file=self.std)
                        else:
                            print("  - 警告：移植源未发现 /system/bin/sysinit（init.d 执行器），网络修复可能无法开机自动生效；", file=self.std)
                            print("    可开机后手动执行 /system/etc/init.d/99cnfix.sh 一次", file=self.std)
                        print(f"  - 生效条件：设备有 root 或 ADB 有权限；CM 系 ROM（含 init.d 支持）刷完即生效；恢复出厂清表后自动重写", file=self.std)
                    except OSError as e:
                        print(f"  - 注入自启脚本失败（{e}），仅保留 build.prop 兜底", file=self.std)
                case 'fix_storage_system':
                    # AMG 教程补充节：6582 设备移植 6572 固件后存储仍异常时，
                    # 从同版本 6582 移植包提取 sdcard/vold 替换进移植后 system。
                    # 工具替换方向为 底包 -> 移植源，底包即"同版本原厂/移植包"，直接套用。
                    # 独立条目：仅当 boot 侧 fix_storage 修复后存储仍异常时再勾选此兜底项。
                    print(f"【移植项】存储修复·system侧（替换sdcard/vold）...", file=self.std)
                    # 版本一致性守卫：vold/sdcard 与 Android 版本强绑定，跨大版本替换可能直接不可用
                    base_rel = port_rel = None
                    base_bp = base_prefix.joinpath("build.prop")
                    port_bp = port_prefix.joinpath("build.prop")
                    if base_bp.exists() and port_bp.exists():
                        with proputil(str(base_bp)) as b, proputil(str(port_bp)) as p:
                            base_rel = b.getprop('ro.build.version.release')
                            port_rel = p.getprop('ro.build.version.release')
                    if base_rel and port_rel and base_rel != port_rel:
                        print(f"  ! 注意：底包 Android {base_rel} vs 移植源 Android {port_rel} 版本不一致，", file=self.std)
                        print(f"  ! vold/sdcard 与 Android 版本强绑定，跨版本替换可能直接不可用；", file=self.std)
                        print(f"  ! 已按勾选继续执行 system 侧替换（若刷入后存储异常，请取消此项）", file=self.std)
                    for f in ('bin/sdcard', 'bin/vold'):
                        src = base_prefix.joinpath(f)
                        dst = port_prefix.joinpath(f)
                        if src.is_file():
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            _clear_attrs(dst)
                            dst.write_bytes(src.read_bytes())
                            print(f"  - 替换 {f}（底包 -> 移植源）", file=self.std)
                        else:
                            print(f"  - 跳过 {f}（底包中不存在）", file=self.std)
                    print(f"  - system侧存储修复完成", file=self.std)
                case 'enable_adb':
                    print(f"【移植项】开启ADB调试...", file=self.std)
                    build_prop_path = port_prefix.joinpath("build.prop")
                    if build_prop_path.exists():
                        with proputil(str(build_prop_path)) as p:
                            kv = [
                                ('ro.secure', '0'),
                                ('ro.adb.secure', '0'),
                                ('ro.debuggable', '1'),
                                ('persist.sys.usb.config', 'mtp,adb')
                            ]
                            for key, value in kv:
                                p.setprop(key, value)
                                print(f"  - 设置 {key} = {value}", file=self.std)
                        print(f"  - ADB调试已在build.prop中开启", file=self.std)
                    else:
                        print(f"  - 跳过（未找到system/build.prop）", file=self.std)            
                case 'change_model':
                    print(f"【移植项】同步底包设备型号信息...", file=self.std)
                    keys = ['ro.product.manufacturer', 'ro.build.product', 'ro.product.model', 'ro.product.device', 'ro.product.board', 'ro.product.brand']
                    port_prop = port_prefix.joinpath("build.prop")
                    base_prop = base_prefix.joinpath("build.prop")
                    if port_prop.exists() and base_prop.exists():
                        with proputil(str(port_prop)) as pp, proputil(str(base_prop)) as bp:
                            for key in keys:
                                value = bp.getprop(key)
                                if value:
                                    pp.setprop(key, value)
                                    print(f"  - 设置 {key} = {value}", file=self.std)
                                else:
                                    print(f"  - 跳过 {key}（底包中未找到）", file=self.std)
                        print(f"  - 设备型号信息同步完成", file=self.std)
                        print(f"  - 提示：ro. 属性只写一次，若被更早来源（ramdisk/cust/lk）先设置，build.prop 中的值会被忽略，开机后请核实实际生效值", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)
                case 'change_platform':
                    print(f"【移植项】同步底包平台/WLAN信息...", file=self.std)
                    keys = ['ro.mediatek.platform', 'mediatek.wlan.chip', 'mediatek.wlan.module.postfix', 'ro.hardware']
                    port_prop = port_prefix.joinpath("build.prop")
                    base_prop = base_prefix.joinpath("build.prop")
                    if port_prop.exists() and base_prop.exists():
                        with proputil(str(port_prop)) as pp, proputil(str(base_prop)) as bp:
                            for key in keys:
                                value = bp.getprop(key)
                                if value:
                                    pp.setprop(key, value)
                                    print(f"  - 设置 {key} = {value}", file=self.std)
                                else:
                                    print(f"  - 跳过 {key}（底包中未找到）", file=self.std)
                        print(f"  - 平台/WLAN信息同步完成", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)

        # === 补齐移植源缺失的 bin/xbin 命令软链接 ===
        # 老芯片 ROM（CM/AOSP/类原生 zip）打包时常丢失 /system/bin、/system/xbin 的
        # toybox 命令软链接（cat/ls/cp/mknod/insmod/mount...），而 init 脚本用绝对路径
        # 调用（如 init.mt6582.rc: exec /system/bin/mknod /dev/wmtWifi），缺失会导致
        # 设备节点创建失败、WiFi/蓝牙等启动链路异常（词典笔 MT6582 实证：旧版产物
        # 含底包软链接 WiFi 正常，新版产物缺失 WiFi 打不开）。
        # 从底包补齐：仅补缺失条目，不覆盖移植源已有文件（纯命令入口，跨大版本安全）。
        # 目标重写：底包 5.x 的命令软链接指向 toolbox，而 Android 7+ 移植源的核心命令
        # 由 toybox 提供（toolbox 仅剩 start/stop 等少量命令，无 mknod/cat/insmod）。
        # 若照抄底包目标，init 用绝对路径执行 /system/bin/mknod 时仍会失败（词典笔
        # MT6582 实证：底包目标 toolbox 实机 WiFi 依旧打不开；旧版产物目标 toybox 正常）。
        # 因此补齐时按移植源实际命令表重写解释器目标：命令在 toybox 命令表内 -> toybox，
        # 否则回退 toolbox；特殊目标（app_process32/dalvikvm32 等）保留原样。
        print(f"【软链接补齐】从底包补齐 bin/xbin 命令软链接（按移植源解释器重写目标）...", file=self.std)
        _symlink_mark = bytes.fromhex('213C73796D6C696E6B3EFFFE')

        # 探测移植源命令解释器与 toybox 命令表
        _port_toybox = port_prefix.joinpath('bin/toybox')
        _port_toolbox = port_prefix.joinpath('bin/toolbox')
        _toybox_cmds = set()
        if _port_toybox.is_file():
            try:
                for _m in re.finditer(rb'[A-Za-z][A-Za-z0-9_]{1,19}', _port_toybox.read_bytes()):
                    _t = _m.group().decode('ascii', 'ignore')
                    if _t.isalpha() or _t.isalnum():
                        _toybox_cmds.add(_t)
            except OSError:
                pass

        def _rewrite_symlink(_raw: bytes, _name: str) -> bytes:
            if _raw[:len(_symlink_mark)] != _symlink_mark:
                return _raw
            try:
                _tgt = _raw[10:].decode('utf-16-le').rstrip('\x00').lstrip('\ufeff')
            except Exception:
                return _raw
            if _tgt not in ('toolbox', 'toybox'):
                return _raw  # 特殊目标（app_process32/dalvikvm32 等）保留原样
            if _port_toybox.is_file() and _name in _toybox_cmds:
                _new = 'toybox'
            elif _port_toolbox.is_file():
                _new = 'toolbox'
            else:
                return _raw  # 移植源无解释器，保留原目标
            return _symlink_mark + _new.encode('utf-16-le') + b'\x00\x00'

        _merged = 0
        for _rel in ('bin', 'xbin'):
            _bd = base_prefix.joinpath(_rel)
            _pd = port_prefix.joinpath(_rel)
            if not _bd.is_dir():
                continue
            _pd.mkdir(parents=True, exist_ok=True)
            for _e in sorted(_bd.iterdir()):
                if not _e.is_file():
                    continue
                try:
                    _raw = _e.read_bytes()
                    if _raw[:12] != _symlink_mark:
                        continue
                except OSError:
                    continue
                _dst = _pd.joinpath(_e.name)
                if _dst.exists():
                    continue  # 移植源已有同名条目，不覆盖
                try:
                    _new_raw = _rewrite_symlink(_raw, _e.name)
                    _dst.write_bytes(_new_raw)
                    _merged += 1
                    if _new_raw[:len(_symlink_mark)] == _symlink_mark:
                        _t_disp = _new_raw[10:].decode('utf-16-le').rstrip('\x00').lstrip('\ufeff')
                    else:
                        _t_disp = '(原样)'
                    print(f"  - 补齐 {_rel}/{_e.name} -> {_t_disp}", file=self.std)
                except OSError as _err:
                    print(f"  - 跳过 {_rel}/{_e.name}（复制失败：{_err}）", file=self.std)
        if _merged:
            print(f"  - 共补齐 {_merged} 个命令软链接（来自底包，仅补缺失）", file=self.std)
        else:
            print(f"  - 无需补齐（移植源命令软链接已完整）", file=self.std)

        print(f"【system移植完成】system.img处理完毕", file=self.std)
        return True
    
    def __pack_rom(self):
        print(f"【开始打包】生成zip卡刷包...", file=self.std)
        # 执行卡刷包定制逻辑
        for item in self.items['flags']:
            item_flag = self._flag(item)
            if not item_flag:
                continue
            
            match item:
                case 'use_custom_update-binary':
                    print(f"【定制项】使用自定义update-binary...", file=self.std)
                    update_binary_path = Path("tmp/rom/META-INF/com/google/android/update-binary")
                    update_binary_path.parent.mkdir(parents=True, exist_ok=True)
                    update_binary_path.write_bytes(Path("bin/update-binary").read_bytes())
                    print(f"  - 自定义update-binary已替换", file=self.std)
                case 'generate_script':
                    print(f"【定制项】生成自动刷机脚本...", file=self.std)
                    updater_script_path = Path("tmp/rom/META-INF/com/google/android/updater-script")
                    if updater_script_path.exists():
                        with updater_script_path.open('r+', encoding='utf-8', newline='\n') as f:
                            author = self.items.get('author') or tool_author
                            version = self.items.get('version') or tool_version
                            new_script = updaterutil(f).generate(author, version, self.items['partitions'], self.sdat)
                            if new_script:
                                # #68：非 sdat 且方案未配置分区路径（或移植源 updater-script 解析不到 system）时，
                                # generate() 返回"仅刷写 boot"脚本，system 移植静默不生效——显式警告
                                if '仅刷写 boot' in new_script:
                                    print(f"【警告】未解析到 system 分区路径，生成的脚本仅刷写 boot，system 移植不会生效（该方案未配置分区路径，且移植源 updater-script 中未找到 system 分区信息）", file=self.std)
                                f.seek(0, 0)
                                f.truncate()
                                f.write(new_script)
                                print(f"  - 刷机脚本生成成功", file=self.std)
                            else:
                                print(f"  - 刷机脚本生成失败（未解析到分区信息，请确认移植源updater-script含分区路径）", file=self.std)
                    else:
                        print(f"  - 跳过（未找到updater-script）", file=self.std)
        
        # 打包zip
        if isinstance(self.port_source, tuple):
            outname = f"MTK-Ported-{tool_version}.zip"
        else:
            outname = op.basename(self.port_source)
        outpath = self.outdir.joinpath(outname)
        if outpath.exists():
            print(f"【清理旧文件】删除已有 {outpath.name}", file=self.std)
            outpath.unlink()
        
        if self.sdat:
            print(f"【格式处理】使用SDAT格式打包system分区...", file=self.std)
            config_dir = Path("tmp/rom/config")
            config_dir.mkdir(parents=True, exist_ok=True)
            
            # 清理文件上下文配置
            fc_path = config_dir.joinpath("system_file_contexts")
            if fc_path.exists():
                with fc_path.open('r+', encoding='utf-8-sig', newline='\n') as fc:
                    fc_info = list(dict.fromkeys([i.rstrip() for i in fc]))
                    fc.seek(0, 0)
                    fc.truncate()
                    fc.write("\n".join(fc_info))
                print(f"  - 清理重复的文件上下文配置", file=self.std)
            else:
                # 移植源无 SELinux xattr（如 sdat 重建镜像）时 imgextractor 不生成 file_contexts，
                # 回退使用底包的上下文配置，避免 make_ext4fs -S 引用缺失文件失败
                base_fc = Path("base/config/system_file_contexts")
                if base_fc.exists():
                    fc_path.write_bytes(base_fc.read_bytes())
                    print(f"  - 使用底包文件上下文配置", file=self.std)
            
            # 生成文件系统配置
            fs_label = [["/", '0', '0', '0755'], ["/lost+found", '0', '0', '0700']]
            fs_files = [i[0] for i in fs_label]
            
            for root, dirs, files in walk("tmp/rom/system"):
                if "tmp/install" in root.replace('\\', '/'):
                    continue
                for dir in dirs:
                    unix_path = op.join("/system", op.relpath(op.join(root, dir), "tmp/rom/system")).replace("\\", "/").replace("[", "\\[")
                    if unix_path not in fs_files:
                        fs_label.append([unix_path.lstrip('/'), '0', '0', '0755'])
                        fs_files.append(unix_path)
                for file in files:
                    unix_path = op.join("/system", op.relpath(op.join(root, file), "tmp/rom/system")).replace("\\", "/").replace("[", "\\[")
                    if unix_path not in fs_files:
                        link = self.__readlink(op.join(root, file))
                        if link:
                            fs_label.append([unix_path.lstrip('/'), '0', '2000', '0755', link])
                        else:
                            mode = _infer_fs_mode(unix_path, os.stat(op.join(root, file)).st_mode)
                            fs_label.append([unix_path.lstrip('/'), '0', '2000', mode])
                        fs_files.append(unix_path)
            
            # 写入文件系统配置（newline='\n' 强制 LF：fs_config 是 Android 侧文件，CRLF 会污染权限解析）
            with config_dir.joinpath("system_fs_config").open('w', encoding='utf-8', newline='\n') as f:
                for fs in sorted(fs_label):
                    f.write(" ".join(fs) + '\n')
            print(f"  - 生成文件系统配置：{len(fs_label)} 条记录", file=self.std)
            
            # 生成raw镜像
            fit_size = self.__pack_fit_size()
            sys_size = stat(self.sysimg).st_size
            img_size = sys_size if sys_size >= fit_size else fit_size
            
            print(f"【生成镜像】创建system_raw.img（大小：{round(img_size/(1024**3),2)}GB）...", file=self.std)
            # 先生成 raw 镜像（symlink/bitmap/一致性修复需在 raw 上执行），
            # 修复完成后由 img2simg 转为 sparse 再交给 img2sdat
            ret_code, _ = self.execv([
                make_ext4fs_bin, '-J', '-T', '1', '-l', f'{img_size}',
                '-C', str(config_dir.joinpath('system_fs_config')), 
                '-S', str(config_dir.joinpath('system_file_contexts')),
                '-L', 'system', '-a', 'system', 
                str(self.outdir.joinpath("system_raw.img")), "tmp/rom/system"
            ], verbose=False)
            
            if ret_code != 0:
                print(f"【生成失败】system_raw.img创建失败（返回码：{ret_code}）", file=self.std)
                return

            # 修复符号链接（支持 sparse/raw 两种格式）
            print(f"【符号链接修复】正在修复 system_raw.img 中的符号链接...", file=self.std)
            try:
                fixed = fix_symlinks(str(self.outdir.joinpath("system_raw.img")), log=self.std)
                print(f"  - 修复完成，共转换 {fixed} 个符号链接", file=self.std)
            except Exception as e:
                print(f"  - 符号链接修复失败：{e}", file=self.std)

            # 修复 make_ext4fs 可能产生的 inode bitmap 未标记问题
            print(f"\n【inode bitmap 修复】正在检查并修复 inode bitmap...", file=self.std)
            try:
                ib_fixed = fix_inode_bitmaps(str(self.outdir.joinpath("system_raw.img")), log=self.std)
                if ib_fixed > 0:
                    print(f"  - 修复完成，共修复 {ib_fixed} 个未标记 inode", file=self.std)
                else:
                    print(f"  - 无需修复", file=self.std)
            except Exception as e:
                print(f"  - inode bitmap 修复异常：{e}", file=self.std)

            # 文件系统一致性自查
            print(f"【一致性自查】正在校验 system_raw.img 文件系统完整性...", file=self.std)
            try:
                ok, errs = verify_image_integrity(str(self.outdir.joinpath("system_raw.img")), log=self.std)
                if ok:
                    print(f"  - 一致性自查通过", file=self.std)
                else:
                    print(f"  - 一致性自查发现 {len(errs)} 个问题", file=self.std)
            except Exception as e:
                print(f"  - 一致性自查异常：{e}", file=self.std)

            # 转换为稀疏镜像
            print(f"【格式转换】将system_raw.img转为稀疏镜像...", file=self.std)
            ret_code, _ = self.execv([img2simg_bin, str(self.outdir.joinpath("system_raw.img")), str(self.outdir.joinpath("system.img"))], verbose=False)
            if ret_code != 0:
                print(f"【转换失败】稀疏镜像生成失败（返回码：{ret_code}）", file=self.std)
                return
            
            # 转换为SDAT格式
            print(f"【格式转换】将system.img转为SDAT格式...", file=self.std)
            _rmtree("tmp/rom/system")
            img2sdat(str(self.outdir.joinpath("system.img")), "tmp/rom", self.sdat_ver)
            # 注：img2sdat 的 OUTDIR 参数为文件名前缀（prefix + ".transfer.list"），
            # 三件套直接输出在 tmp/rom/ 根，zip 打包后即在 zip 根，无需移动
            if Path("tmp/rom/system.img").exists():
                unlink("tmp/rom/system.img")
            print(f"  - SDAT格式转换完成", file=self.std)
        
        # 非 sdat 移植源：tmp/rom/system.img 是解包遗留的 donor 原版（未移植），
        # 脚本实际刷入的是 system/ 目录；残留会让产物 zip 内含陈旧镜像（#59），打包前删除
        if not self.sdat and Path("tmp/rom/system.img").exists():
            print(f"  - 清理解包遗留的 donor 原版 system.img（非 sdat 打包不引用）", file=self.std)
            unlink("tmp/rom/system.img")

        # 最终打包zip
        print(f"【打包zip】正在压缩为卡刷包...", file=self.std)
        ziputil.compress(str(outpath), "tmp/rom/")
        print(f"【打包完成】卡刷包已生成：{outpath}", file=self.std)
    
    def __pack_img(self):
        """生成img镜像（日志优化核心方法）"""
        def __symlink(src: str, dest: str):
            pdest = Path(dest)
            pdest.parent.mkdir(parents=True, exist_ok=True)
            if osname == 'nt':
                with open(dest, 'wb') as f:
                    f.write(b"!<symlink>" + src.encode('utf-16') + b'\0\0')
            else:
                symlink(src, dest)
        
        print(f"\n【开始打包】生成img镜像文件...", file=self.std)

        # kernel-only 模式：只输出 boot.img，不打包 system.img
        if self._flag('kernel_only_mode'):
            out_boot = self.outdir.joinpath("boot.img")
            out_boot.parent.mkdir(parents=True, exist_ok=True)
            src_boot = Path("tmp/rom/boot.img")
            if src_boot.exists():
                out_boot.write_bytes(src_boot.read_bytes())
                print(f"【kernel-only】仅输出 boot.img（不生成 system.img）", file=self.std)
                print(f"  └─ boot.img：{self.outdir.as_posix()}/boot.img", file=self.std)
            else:
                print(f"【kernel-only】错误：未找到 tmp/rom/boot.img", file=self.std)
            print(f"\n【打包完成】kernel-only 模式，仅 boot.img", file=self.std)
            return

        # recovery-only 模式：只输出 recovery.img，不打包 system.img
        if self._flag('recovery_only_mode'):
            out_rec = self.outdir.joinpath("recovery.img")
            out_rec.parent.mkdir(parents=True, exist_ok=True)
            src_rec = Path("tmp/rom/recovery.img")
            if src_rec.exists():
                out_rec.write_bytes(src_rec.read_bytes())
                print(f"【recovery-only】仅输出 recovery.img（不生成 system.img）", file=self.std)
                print(f"  └─ recovery.img：{self.outdir.as_posix()}/recovery.img", file=self.std)
            else:
                print(f"【recovery-only】错误：未找到 tmp/rom/recovery.img", file=self.std)
            print(f"\n【打包完成】recovery-only 模式，仅 recovery.img", file=self.std)
            return

        updater = Path("tmp/rom/META-INF/com/google/android/updater-script")
        config_dir = Path("tmp/config")
        
        # 清理旧配置
        if config_dir.exists():
            _rmtree(config_dir)
        config_dir.mkdir(parents=True)
        
        # 解析刷机脚本获取权限配置（zip源）或使用默认配置（img源）
        print(f"【配置生成】解析权限配置（SD卡刷包源）...", file=self.std)
        fs_label = [["/", '0', '0', '0755'], ["/lost+found", '0', '0', '0700']]
        fc_label = [['/', 'u:object_r:system_file:s0'], ['/system(/.*)?', 'u:object_r:system_file:s0']]
        
        if updater.exists():
            with updater.open('r', encoding='utf-8') as f:
                contents = updaterutil(f).content
            
            last_fpath = ''
            for content in contents:
                command, *args = content
                match command:
                    case 'symlink':
                        src, *targets = args
                        for target in targets:
                            __symlink(src, str(Path("tmp/rom").joinpath(target.lstrip('/'))))
                    case 'set_metadata' | 'set_metadata_recursive':
                        dirmode = command == 'set_metadata_recursive'
                        fpath, *fargs = args
                        fpath = fpath.replace("+", "\\+").replace("[", "\\[").replace('//', '/')
                        if fpath == last_fpath:
                            continue
                        
                        # 解析权限参数
                        uid, gid, mode, extra = '0', '0', '644', ''
                        selable = 'u:object_r:system_file:s0'
                        fmode_val = dmode_val = None
                        for idx, farg in enumerate(fargs):
                            match farg:
                                case 'uid': uid = fargs[idx+1]
                                case 'gid': gid = fargs[idx+1]
                                case 'mode':
                                    mode = fargs[idx+1]
                                case 'fmode':
                                    fmode_val = fargs[idx+1]
                                case 'dmode':
                                    dmode_val = fargs[idx+1]
                                case 'capabilities':
                                    extra = 'capabilities=' + fargs[idx+1] if fargs[idx+1] != '0x0' else ''
                                case 'selabel': selable = fargs[idx+1]
                        # set_metadata_recursive 的 fpath 是目录，根条目必须用 dmode（通常 0755）；
                        # fmode 是子文件权限，而子文件/子目录由下方实际遍历逐个补全，不能拿 fmode 压目录根。
                        # 旧实现让 dmode 后写覆盖 fmode 恰好正确；#72 改成 fmode 优先会把 /system 挂载点
                        # 压成 0644（无 x 位），system_server 无法遍历，刷入卡第二屏。
                        if dirmode:
                            if dmode_val:
                                mode = dmode_val
                        elif fmode_val:
                            mode = fmode_val
                        
                        fs_label.append([fpath.lstrip('/'), uid, gid, mode, extra])
                        fc_label.append([fpath, selable])
                        last_fpath = fpath
            print(f"  - 从刷机脚本解析到 {len(fs_label)} 条权限配置", file=self.std)
        else:
            print(f"  - 未找到刷机脚本，使用默认权限配置", file=self.std)
        
        # 补充缺失的文件权限
        print(f"【配置生成】补充文件权限配置...", file=self.std)
        fs_files = [i[0] for i in fs_label]
        config_count = 0
        
        for root, dirs, files in walk("tmp/rom/system"):
            if "tmp/install" in root.replace('\\', '/'):
                continue
            
            for dir in dirs:
                unix_path = op.join("/system", op.relpath(op.join(root, dir), "tmp/rom/system")).replace("\\", "/").replace("[", "\\[")
                if unix_path not in fs_files:
                    fs_label.append([unix_path.lstrip('/'), '0', '0', '0755'])
                    fs_files.append(unix_path)
                    config_count += 1
            
            for file in files:
                unix_path = op.join("/system", op.relpath(op.join(root, file), "tmp/rom/system")).replace("\\", "/").replace("[", "\\[")
                if unix_path not in fs_files:
                    link = self.__readlink(op.join(root, file))
                    if link:
                        fs_label.append([unix_path.lstrip('/'), '0', '2000', '0755', link])
                    else:
                        mode = _infer_fs_mode(unix_path, os.stat(op.join(root, file)).st_mode)
                        fs_label.append([unix_path.lstrip('/'), '0', '2000', mode])
                    fs_files.append(unix_path)
                    config_count += 1
        
        print(f"  - 补充 {config_count} 条缺失的权限配置，总计 {len(fs_label)} 条", file=self.std)
        
        # 生成配置文件（newline='\n' 强制 LF，Android 侧文件防 CRLF）
        print(f"【配置生成】写入权限配置文件...", file=self.std)
        with config_dir.joinpath("system_fs_config").open('w', encoding='utf-8', newline='\n') as f:
            for fs in sorted(fs_label):
                f.write(" ".join(filter(None, fs)) + '\n')
        
        with config_dir.joinpath("system_file_contexts").open('w', encoding='utf-8', newline='\n') as f:
            for fc in sorted(fc_label):
                f.write(" ".join(fc) + '\n')
        print(f"  - 配置文件已写入到 tmp/config 目录", file=self.std)
        
        # 生成system.img（日志核心优化）
        fit_size = self.__pack_fit_size()
        sys_size = stat(self.sysimg).st_size
        img_size_bytes = sys_size if sys_size >= fit_size else fit_size
        img_size_gb = round(img_size_bytes / (1024**3), 2)
        
        # 结构化日志输出
        print(f"\n【生成system.img】核心参数说明：", file=self.std)
        print(f"  ├─ 工具：make_ext4fs（创建ext4格式分区镜像）", file=self.std)
        print(f"  ├─ 镜像大小：{img_size_gb} GB（{img_size_bytes} 字节）", file=self.std)
        print(f"  ├─ 镜像标签：system", file=self.std)
        print(f"  ├─ 挂载点：/system", file=self.std)
        print(f"  ├─ 权限配置：{config_dir}/system_fs_config", file=self.std)
        print(f"  ├─ SELinux上下文：{config_dir}/system_file_contexts", file=self.std)
        print(f"  ├─ 源目录：tmp/rom/system", file=self.std)
        print(f"  └─ 输出路径：{self.outdir.as_posix()}/system.img", file=self.std)
        
        print(f"\n【执行中】正在创建system.img文件系统...", file=self.std)
        make_ext4fs_cmd = [
            make_ext4fs_bin,
            '-J', '-T', '1', '-l', f'{img_size_bytes}',
            '-C', str(config_dir.joinpath('system_fs_config')),
            '-S', str(config_dir.joinpath('system_file_contexts')),
            '-L', 'system', '-a', 'system',
            str(self.outdir.joinpath("system.img")), "tmp/rom/system"
        ]
        
        # 执行命令并获取输出
        ret_code, cmd_output = self.execv(make_ext4fs_cmd, verbose=False)
        cmd_output_str = cmd_output.decode('utf-8', errors='ignore')
        
        # 解析命令输出，提取关键信息
        if ret_code == 0:
            # 提取配置条目数
            fs_config_match = re.search(r'loaded (\d+) fs_config entries', cmd_output_str)
            fs_config_count = fs_config_match.group(1) if fs_config_match else "未知"
            
            # 提取镜像大小
            size_match = re.search(r'Size: (\d+)', cmd_output_str)
            if size_match:
                actual_size_gb = round(int(size_match.group(1)) / (1024**3), 2)
                actual_size_info = f"{actual_size_gb} GB"
            else:
                actual_size_info = f"{img_size_gb} GB（预估）"
            
            print(f"【生成成功】system.img创建完成！", file=self.std)
            print(f"  ├─ 权限配置条目：{fs_config_count} 条", file=self.std)
            print(f"  ├─ 实际镜像大小：{actual_size_info}", file=self.std)
            print(f"  └─ 输出路径：{self.outdir.as_posix()}/system.img", file=self.std)

            # 修复符号链接：Windows 解包/打包会把符号链接打成 !<symlink> 标记文件，
            # 这里在 ext4 镜像上把标记文件转回真正的符号链接
            print(f"\n【符号链接修复】正在将 !<symlink> 标记转回真正的符号链接...", file=self.std)
            try:
                fixed = fix_symlinks(str(self.outdir.joinpath("system.img")), log=self.std)
                print(f"  - 修复完成，共转换 {fixed} 个符号链接", file=self.std)
            except Exception as e:
                print(f"  - 符号链接修复失败（不影响其它步骤，但建议检查镜像）：{e}", file=self.std)

            # 修复 make_ext4fs 可能产生的 inode bitmap 未标记问题
            print(f"\n【inode bitmap 修复】正在检查并修复 inode bitmap...", file=self.std)
            try:
                ib_fixed = fix_inode_bitmaps(str(self.outdir.joinpath("system.img")), log=self.std)
                if ib_fixed > 0:
                    print(f"  - 修复完成，共修复 {ib_fixed} 个未标记 inode", file=self.std)
                else:
                    print(f"  - 无需修复", file=self.std)
            except Exception as e:
                print(f"  - inode bitmap 修复异常：{e}", file=self.std)

            # 文件系统一致性自查（组校验和 / 位图 / 目录项类型 / 标记残留）
            print(f"\n【一致性自查】正在校验 system.img 文件系统完整性...", file=self.std)
            try:
                ok, errs = verify_image_integrity(str(self.outdir.joinpath("system.img")), log=self.std)
                if ok:
                    print(f"  - 一致性自查通过", file=self.std)
                else:
                    print(f"  - 一致性自查发现 {len(errs)} 个问题（建议重新生成或检查）", file=self.std)
            except Exception as e:
                print(f"  - 一致性自查异常：{e}", file=self.std)
        else:
            print(f"【生成失败】system.img创建失败！", file=self.std)
            print(f"  ├─ 返回码：{ret_code}", file=self.std)
            print(f"  └─ 错误信息：{cmd_output_str[:500]}", file=self.std)
            return
        
        # 复制boot.img
        print(f"\n【复制文件】复制移植后的boot.img到out目录...", file=self.std)
        self.outdir.joinpath("boot.img").write_bytes(Path("tmp/rom/boot.img").read_bytes())
        
        # 最终提示
        print(f"\n【打包完成】img镜像生成完毕！", file=self.std)
        print(f"  ├─ boot.img：{self.outdir.as_posix()}/boot.img", file=self.std)
        print(f"  └─ system.img：{self.outdir.as_posix()}/system.img", file=self.std)
        

    def __pack_fit_size(self):
        """计算镜像适配大小"""
        total = 0
        for root, dirs, files in walk("tmp/rom/system"):
            for file in files:
                total += stat(op.join(root, file)).st_size
        return int(total * 1.2)  # 预留20%空间

    def __readlink(self, dest: str):
        """读取符号链接"""
        if osname == 'nt':
            with open(dest, 'rb') as f:
                header = f.read(10)
                if header == b'!<symlink>':
                    return f.read().decode('utf-16').rstrip('\0')
                return None
        else:
            try:
                return readlink(dest)
            except:
                return None

    def start(self):
        """启动移植流程"""
        print(file=self.std)
        print("=" * 60, file=self.std)
        print(f"【开始移植】MTK低端机移植工具启动...", file=self.std)
        print(f"  ├─ 工具版本：{tool_version}", file=self.std)
        print(f"  ├─ 输出类型：{'img镜像' if self.genimg else 'zip卡刷包'}", file=self.std)
        print(f"  ├─ 移植源类型：{'zip卡刷包' if self.source_type == 'zip' else '单独img镜像'}", file=self.std)
        # 输入文件概览（路径 + 大小）
        if self._flag('lk_patch_mode'):
            # LK去警告：输入为固件目录（自动检测 lk/lk2）
            print(f"  ├─ 固件目录：{self.bootimg}", file=self.std)
            try:
                from .LKPatch import detect_lk_files as _dlk
                _lks = [op.basename(f) for f in _dlk(self.bootimg)]
                print(f"  └─ 检测到 LK 镜像：{'、'.join(_lks) if _lks else '（未检测到）'}", file=self.std)
            except Exception:
                pass
        else:
            print(f"  ├─ 底包 boot：{self.bootimg}（{_fmt_size(Path(self.bootimg).stat().st_size)}）", file=self.std)
            if self.sysimg:
                print(f"  ├─ 底包 system：{self.sysimg}（{_fmt_size(Path(self.sysimg).stat().st_size)}）", file=self.std)
            else:
                print(f"  ├─ 底包 system：不参与（本方案无需 system）", file=self.std)
            if self.source_type == 'zip':
                print(f"  └─ 移植包：{self.port_source}（{_fmt_size(Path(self.port_source).stat().st_size)}）", file=self.std)
            else:
                pb, ps = self.port_source
                print(f"  ├─ 移植用 boot：{pb}（{_fmt_size(Path(pb).stat().st_size)}）", file=self.std)
                if ps:
                    print(f"  └─ 移植用 system：{ps}（{_fmt_size(Path(ps).stat().st_size)}）", file=self.std)
                else:
                    print(f"  └─ 移植用 system：不参与（本方案无需 system）", file=self.std)
        
        # kernel-only / recovery-only + zip 输出二次拦截：UI 已拦截，此处防绕过 UI 直接调用
        if self._flag('kernel_only_mode') and not self.genimg:
            print(f"【移植失败】kernel-only（仅替换内核）仅支持 img 输出，请将输出类型切换为 img", file=self.std)
            return
        if self._flag('recovery_only_mode') and not self.genimg:
            print(f"【移植失败】recovery-only（仅移植Recovery）仅支持 img 输出，请将输出类型切换为 img", file=self.std)
            return
        if self._flag('recovery_only_mode') and self.source_type == 'zip':
            print(f"【移植失败】recovery-only（仅移植Recovery）仅支持 img 移植源（不支持 zip 卡刷包源）", file=self.std)
            return

        # LK去警告 模式：直接执行 LK 打补丁（无解包 / 无 system 参与）
        if self._flag('lk_patch_mode'):
            if not self.genimg:
                print(f"【移植失败】LK去警告（仅去警告）仅支持 img 输出", file=self.std)
                return
            from .LKPatch import run_lk_patch
            _ok = run_lk_patch(self.bootimg, self.std)
            print(f"\n【流程结束】LK去警告{'成功' if _ok else '失败'}，流程结束", file=self.std)
            return

        try:
            self.__decompress_portzip()
            if not self.__port_boot():
                print(f"【移植失败】boot.img移植过程出错", file=self.std)
                return
            # kernel-only / recovery-only 模式：只处理 boot/recovery，跳过 system.img
            if self._flag('kernel_only_mode'):
                print(f"\n【kernel-only】仅替换内核模式，跳过 system.img 处理", file=self.std)
            elif self._flag('recovery_only_mode'):
                print(f"\n【recovery-only】仅移植Recovery模式，跳过 system.img 处理", file=self.std)
            else:
                self.__port_system()
            
            if self.genimg:
                self.__pack_img()
            else:
                self.__pack_rom()
        
            print(f"\n【流程结束】移植工具执行完毕！", file=self.std)
        finally:  # 新增finally：无论成功/失败都执行清理
            # 异常冒泡到 finally 时，真正的失败点在上面最后一条执行日志附近（先清理后报错只是顺序问题）
            if sys.exc_info()[0] is not None:
                print(f"\n【异常清理】检测到错误：真正的失败点在上面最后一条执行日志附近，以下为清理日志", file=self.std)
            self.clean()
    def clean(self):
        """清理临时文件；base/ 缓存默认保留，勾选"完成后清除base目录"时删除"""
        print(f"【清理临时文件】删除tmp目录...", file=self.std)
        if Path("tmp").exists():
            _rmtree("tmp")
        print(f"【清理完成】临时文件已删除", file=self.std)
        if self.items.get('clean_base_after', False):
            print(f"【清理缓存】删除base目录（已勾选完成后清除）...", file=self.std)
            if Path("base").exists():
                _rmtree("base")
            print(f"【清理完成】base目录已删除", file=self.std)