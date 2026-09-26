import re
import time
from io import StringIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from os import walk, getcwd, chdir, symlink, readlink, name as osname, stat, unlink, chmod
import os
import os.path as op
from shutil import rmtree, copytree
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


tool_author = 'affggh'; tool_version = '1.3-beta2p2'

class proputil:
    def __init__(self, propfile: str):
        proppath = Path(propfile)
        if proppath.exists():
            self.propfile = propfile
            self.encoding = self.__detect_encoding(propfile)
            self.propfd = Path(propfile).open('r+', encoding=self.encoding.rstrip('-sig'))  # 写句柄去 sig，避免给无 BOM 文件注入 BOM
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
        parts[1] in ('bin', 'xbin') or (parts[1] == 'vendor' and parts[2] == 'bin'))
    is_exec = bool(st_mode & 0o111) or path_exec
    return suid + ('755' if is_exec else '644')

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
    
    def decompress(zippath: str, outdir: str):
        with ZipFile(zippath, 'r') as zipf:
            zipf.extractall(outdir)
    
    def extract_onefile(zippath: str, filename: str, outpath: str):
        with ZipFile(zippath, 'r') as zipf:
            zipf.extract(filename, outpath)
    
    def compress(zippath: str, indir: str):
        with ZipFile(zippath, 'w', ZIP_DEFLATED) as zipf:
            for root, dirs, files in walk(indir):
                for file in files:
                    file_path = op.join(root, file)
                    zip_path = op.relpath(op.abspath(file_path), op.abspath(indir))
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
        # 屏蔽 bootimg.py 的英文诊断噪音（base/arguments 等），失败时还原以便排查
        err_buf = StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                unpack_bootimg(self.bootpath)
        except Exception:
            sys.stderr.write(err_buf.getvalue())
            raise
        chdir(self.retcwd)
    
    def repack(self):
        chdir(self.bootdir)
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
        err_buf = StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                repack_bootimg(base, cmdline, page_size, padding_size, None)
        except Exception:
            sys.stderr.write(err_buf.getvalue())
            raise
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
                        with portdir.joinpath("bootinfo.txt").open("r+", encoding="utf-8-sig") as f:
                            lines = [i.rstrip() for i in f.readlines()]
                            if any("androidboot.selinux=permissive" in line for line in lines):
                                print(f"  - 已开启SELinux宽容模式，无需重复操作", file=self.std)
                                continue
                            f.truncate(0)
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
            if "*" in val:
                matched = 0
                for file in glob.glob(op.join(str(base_prefix), val)):
                    matched += 1
                    relfile = op.relpath(file, str(base_prefix))
                    dst2 = port_prefix.joinpath(relfile)
                    src_file = base_prefix.joinpath(relfile)
                    if op.isdir(src_file):
                        # 通配命中目录：整体目录替换
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

        # 执行system移植逻辑
        print(f"【开始移植】执行system.img移植逻辑...", file=self.std)
        base_prefix = Path("base/system")
        port_prefix = Path("tmp/rom/system")

        # === 同平台通用自动替换模式 ===
        if self._flag('auto_replace'):
            print(f"【自动替换】同平台通用模式：自动扫描底包硬件文件并替换...", file=self.std)
            auto_count = 0

            # 1. 整个目录替换（固件/配置/GPU驱动）
            auto_dirs = [
                "vendor/firmware", "etc/firmware",
                "vendor/etc/mddb", "etc/mddb",
                "vendor/etc/audio_param", "etc/audio_param",
                "vendor/etc/.tp",
                "vendor/lib/egl", "lib/egl",
                "etc/wifi", "etc/bluetooth",
                "etc/ht120_mtc",
                # 音频配置文件
                "etc/audio_effects.conf", "vendor/etc/audio_effects.conf",
                "vendor/etc/audio_policy.conf", "vendor/etc/audio_device.xml",
                # GPU egl（arm64 双架构）
                "vendor/lib64/egl", "lib64/egl",
                # TFA 功放常见目录（NXP 外放功放）
                "etc/tfa98xx", "etc/tfa9895", "etc/tfa9897", "vendor/etc/tfa98xx",
                # GPS 配置
                "vendor/etc/agps_profiles_conf2.xml",
                # 键盘布局
                "usr/keylayout",
                # /system/bin 下 RIL 守护进程（同平台替换安全）
                "bin/ccci_fsd", "bin/ccci_mdinit", "bin/gsm0710muxd", "bin/rild",
            ]
            for d in auto_dirs:
                p = base_prefix.joinpath(d)
                if p.is_dir() or p.is_file():
                    if d in ('vendor/firmware', 'etc/firmware'):
                        print(f"  - 整目录替换 {d}（含 modem 等平台固件，auto 同平台通用模式）", file=self.std)
                    __replace(d)
                    auto_count += 1

            # 2. HAL 模块目录（所有 .so 全替换，含 arm64 双架构）
            for hwdir in ["lib/hw", "vendor/lib/hw", "lib64/hw", "vendor/lib64/hw"]:
                src_dir = base_prefix.joinpath(hwdir)
                if src_dir.is_dir():
                    for sofile in src_dir.glob("*.so"):
                        rel = str(sofile.relative_to(base_prefix)).replace("\\", "/")
                        __replace(rel)
                        auto_count += 1

            # 3. 硬件库关键词匹配（/vendor/lib/ 和 /lib/ 下的 .so）
            hw_lib_keywords = [
                'audio', 'gralloc', 'hwcomposer', 'camera', 'cam',
                'sensors', 'lights', 'gps', 'power', 'bluetooth',
                'vibrator', 'thermal', 'wifi', 'wlan', 'ril', 'ccci',
                'mali', 'imgegl', 'pvr', 'vulkan', 'omx', 'codec',
                'vcodec', '3a', 'featureio', 'imageio', 'showlogo',
                'gralloc_extra', 'ksensor', 'rgbwlight', 'mtk-ril',
                'mtkfusion', 'libbt-vendor', 'libem_wifi', 'libccci',
                'librilutils', 'libvia-ril', 'libviagpsrpc', 'libgpu',
                'libmtkcam', 'libcam', 'libmhal', 'libmtkjpeg',
                'libjpg', 'libswjpg', 'libhardware_legacy', 'libwpa',
                'libwifi', 'libnetd', 'libdrm', 'libsecure', 'tfa',
            ]
            # 只扫描 vendor/lib 与 vendor/lib64（vendor 分区的硬件驱动库），不扫 /lib 根目录（系统框架库不能换）
            for libdir in ["vendor/lib", "vendor/lib64"]:
                src_dir = base_prefix.joinpath(libdir)
                if src_dir.is_dir():
                    for sofile in src_dir.glob("*.so"):
                        name = sofile.name.lower()
                        if any(kw in name for kw in hw_lib_keywords):
                            rel = str(sofile.relative_to(base_prefix)).replace("\\", "/")
                            __replace(rel)
                            auto_count += 1

            # /lib 根目录下少数确实需要替换的硬件兼容库（单独列出，不做关键词扫描）
            lib_hw_specific = [
                "lib/libhardware_legacy.so",
                "lib/libwpa_client.so",
                "lib/libwifi-service.so",
                "lib/libreference-ril.so",
                "lib/libril.so",
                "lib/mtk-ril.so",
            ]
            for rel in lib_hw_specific:
                if base_prefix.joinpath(rel).exists():
                    __replace(rel)
                    auto_count += 1

            # 3b. 非 Treble 主路径：/system/lib 与 /system/lib64 硬件库白名单（前缀匹配，安全项与手动方案同源）
            legacy_lib_prefixes = [
                'libcam.', 'libcam_utils', 'libcamalgo', 'libcamdrv', 'libcameracustom',
                'lib3a', 'libfeatureio', 'libimageio', 'libmhal', 'libmtkjpeg', 'libjpg',
                'librilmtk', 'libmtkril', 'librilutils', 'libvia-ril',
                'libmtkomx', 'libstagefrighthw', 'libudf', 'libmtk_vt',
                'libmali', 'libgles_mali', 'libshowlogo',
                'libaudiocomp', 'libaudioroute', 'libaudiocust', 'libtfa',
            ]
            # 精确文件名排除（带 .so 后缀）：只排除这些框架库本身，
            # 不误伤白名单前缀命中的硬件适配库（如 libstagefrighthw.so）
            LEGACY_EXCLUDE = (
                'libstagefright.so', 'libdrm.so', 'libbinder.so', 'libc.so',
                'libandroid_runtime.so', 'libcameraservice.so', 'libaudioflinger.so',
                'libmedia.so', 'libnetd.so', 'libwilhelm.so',
            )
            for libdir in ["lib", "lib64"]:
                src_dir = base_prefix.joinpath(libdir)
                if src_dir.is_dir():
                    for sofile in src_dir.glob("*.so"):
                        name = sofile.name.lower()
                        if (any(name.startswith(p) for p in legacy_lib_prefixes)
                                and name not in LEGACY_EXCLUDE):
                            rel = str(sofile.relative_to(base_prefix)).replace("\\", "/")
                            __replace(rel)
                            auto_count += 1
                            print(f"  - 替换 {rel}", file=self.std)

            # 4. 硬件守护进程关键词匹配（只扫 vendor/bin，/bin 是系统工具不替换）
            hw_bin_keywords = [
                'ccci_', 'rild', 'gsm0710muxd', 'mtkfusion',
                'wpa_', 'hostapd', 'netdiag', 'agpsd', 'boot_logo',
            ]
            for bindir in ["vendor/bin"]:
                src_dir = base_prefix.joinpath(bindir)
                if src_dir.is_dir():
                    for binfile in src_dir.iterdir():
                        if binfile.is_file():
                            name = binfile.name.lower()
                            if any(kw in name for kw in hw_bin_keywords):
                                rel = str(binfile.relative_to(base_prefix)).replace("\\", "/")
                                __replace(rel)
                                auto_count += 1

            print(f"【自动替换】完成，共替换 {auto_count} 个硬件文件/目录", file=self.std)

        for item in self.items['flags']:
            item_flag = self._flag(item)
            if not item_flag or item in ['replace_kernel', 'replace_fstab', 'replace_init']:
                continue
            
            if item.startswith("replace_"):
                replace_type = item[len("replace_"):]
                # auto 模式下手动选项优先：若 replace 字典有配置则用手动路径覆盖自动替换结果
                if not self.items.get('replace', {}).get(replace_type):  # #55补：空值也跳过（防空转）
                    continue  # 该方案未配置此替换项的路径，跳过
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
                            locale = bp.getprop('ro.product.locale')
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
                                print(f"  - 跳过（底包中未找到ro.product.locale）", file=self.std)
                    else:
                        print(f"  - 跳过（未找到build.prop）", file=self.std)
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
                        with updater_script_path.open('r+', encoding='utf-8') as f:
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
                with fc_path.open('r+', encoding='utf-8-sig') as fc:
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
            
            # 写入文件系统配置
            with config_dir.joinpath("system_fs_config").open('w', encoding='utf-8') as f:
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
                        mode_set = False
                        for idx, farg in enumerate(fargs):
                            match farg:
                                case 'uid': uid = fargs[idx+1]
                                case 'gid': gid = fargs[idx+1]
                                case 'mode':
                                    mode = fargs[idx+1]; mode_set = True
                                case 'fmode':
                                    mode = fargs[idx+1]; mode_set = True  # 文件权限优先（fs_config 逐文件语义）
                                case 'dmode':
                                    # #72：目录权限仅兜底——set_metadata_recursive 同时给 dmode/fmode 时，
                                    # 以 fmode（文件权限）为准，避免后写参数覆盖先写
                                    if not mode_set:
                                        mode = fargs[idx+1]; mode_set = True
                                case 'capabilities': 
                                    extra = 'capabilities=' + fargs[idx+1] if fargs[idx+1] != '0x0' else ''
                                case 'selabel': selable = fargs[idx+1]
                        
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
        
        # 生成配置文件
        print(f"【配置生成】写入权限配置文件...", file=self.std)
        with config_dir.joinpath("system_fs_config").open('w', encoding='utf-8') as f:
            for fs in sorted(fs_label):
                f.write(" ".join(filter(None, fs)) + '\n')
        
        with config_dir.joinpath("system_file_contexts").open('w', encoding='utf-8') as f:
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