# -*- coding: utf-8 -*-
"""
ext4 镜像符号链接修复模块
=========================
背景：Windows 下 imgextractor 解包 system.img 时，把符号链接写成
`!<symlink>` 标记文件；随后 make_ext4fs 打包时把这些标记当作普通文件，
导致生成的 system.img 里原本的符号链接（/bin/app_process、/etc/mddb、
app 内 jni so 等）全部变成 34~76 字节的文本文件，刷入后系统无法正常启动。

本模块在 make_ext4fs 生成镜像后，直接改写 ext4 镜像的 inode / 目录项 /
块位图，把 `!<symlink>` 标记文件转回真正的符号链接（S_IFLNK）：
  - inode：i_mode = 0xA1FF(S_IFLNK|0777)，i_size = 目标长度，
    i_flags 清空（去掉 EXTENTS/INLINE），i_block 内联目标路径（快链接），
    释放原数据块
  - 父目录项：file_type 由 1(FILE) 改为 7(SYMBOLIC_LINK)
  - 块位图 / 组描述符 / 超级块：释放的块标记为空闲并回写统计
镜像为 make_ext4fs 生成的 raw ext4（无 metadata_csum），无需重算校验和。
"""
import io
import struct
import ctypes
import os

from .ext4 import (
    Volume,
    InodeType,
    ext4_inode,
    ext4_extent,
    ext4_extent_idx,
    ext4_extent_header,
)

MARKER = b'!<symlink>'
S_IFLNK = 0xA000
SYMLINK_MODE = 0xA1FF  # S_IFLNK | 0777

# 稀疏镜像魔数 (0xED26FF3A, little-endian 首字节)
SPARSE_MAGIC = b'\x3a\xff\x26\xed'


def _normalize_log(log):
    """兼容多种日志对象：可调用 / 带 write 方法的文件对象 / None"""
    if log is None:
        return lambda *a: None
    if callable(log):
        return log
    if hasattr(log, 'write'):
        return lambda msg: log.write(str(msg) + '\n')
    return lambda *a: None


class _Fixer:
    def __init__(self, img_path, log=None):
        self.img_path = img_path
        self.log = _normalize_log(log)
        self._f = open(img_path, 'r+b')
        self._v = Volume(self._f)
        self._bs = self._v.block_size
        sb = self._v.superblock
        self._inode_size = sb.s_inode_size
        self._inodes_per_group = sb.s_inodes_per_group
        self._blocks_per_group = sb.s_blocks_per_group
        self._desc_size = sb.s_desc_size
        self._gdt_base = (0x400 // self._bs + 1) * self._bs
        self._freed_by_group = {}
        self._total_freed = 0
        self._uuid = bytes(sb.s_uuid)
        # GDT_CSUM (0x10): 修改组描述符后必须重算 bg_checksum，否则 fsck/mount 报
        # "Structure needs cleaning"
        self._has_gdt_csum = bool(sb.s_feature_ro_compat & 0x10)
        # s_free_blocks_count_lo 偏移（超级块内 0x0C）
        self._sb_free_blocks_off = 0x400 + 0x0C
        # 组描述符内 bg_free_blocks_count_lo 偏移
        self._bg_free_blocks_off = 0x0C

    # ---------- 底层读写 ----------
    def _read(self, offset, n):
        self._f.seek(offset)
        return self._f.read(n)

    def _write(self, offset, data):
        self._f.seek(offset)
        self._f.write(data)

    # ---------- 组描述符校验和 (ext4 GDT_CSUM / CRC-16-ARC) ----------
    @staticmethod
    def _crc16_arc(crc, data):
        """内核/e2fsprogs crc16（CRC-16/ARC，poly 0x8005 反射，初值由参数传入）"""
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _gd_checksum(self, gd_off, group):
        """按 ext4_group_desc_csum（无 metadata_csum、含 GDT_CSUM）重算 bg_checksum"""
        desc = self._read(gd_off, self._desc_size)
        offset = 0x1E  # offsetof(bg_checksum)
        crc = self._crc16_arc(0xFFFF, self._uuid)
        crc = self._crc16_arc(crc, struct.pack('<I', group))
        crc = self._crc16_arc(crc, desc[:offset])
        crc = self._crc16_arc(crc, desc[offset + 2:self._desc_size])
        return crc

    def _write_gd_checksum(self, gd_off, group):
        if not self._has_gdt_csum:
            return
        crc = self._gd_checksum(gd_off, group)
        self._write(gd_off + 0x1E, struct.pack('<H', crc))

    # ---------- extent / 块映射 ----------
    def _inode_block_map(self, inode):
        """返回 [(file_block_idx, disk_block_idx, count), ...]；inline 返回 []"""
        ino = inode.inode
        if not (ino.i_flags & ext4_inode.EXT4_EXTENTS_FL):
            return []
        mapping = []
        nodes = [inode.offset + ext4_inode.i_block.offset]
        while nodes:
            hdr_off = nodes.pop()
            raw = self._read(hdr_off, ctypes.sizeof(ext4_extent_header))
            if len(raw) < ctypes.sizeof(ext4_extent_header):
                continue
            hdr = ext4_extent_header.from_buffer_copy(raw)
            if hdr.eh_magic != 0xF30A:
                continue
            ents = hdr.eh_entries
            if hdr.eh_depth != 0:
                raw = self._read(hdr_off + ctypes.sizeof(ext4_extent_header),
                                 ctypes.sizeof(ext4_extent_idx) * ents)
                for i in range(ents):
                    idx = ext4_extent_idx.from_buffer_copy(
                        raw, i * ctypes.sizeof(ext4_extent_idx))
                    nodes.append(idx.ei_leaf * self._bs)
            else:
                raw = self._read(hdr_off + ctypes.sizeof(ext4_extent_header),
                                 ctypes.sizeof(ext4_extent) * ents)
                for i in range(ents):
                    ext = ext4_extent.from_buffer_copy(raw, i * ctypes.sizeof(ext4_extent))
                    start = (ext.ee_start_hi << 32) | ext.ee_start_lo
                    mapping.append((ext.ee_block, start, ext.ee_len))
        return mapping

    def _free_block(self, disk_block):
        if not disk_block:
            return
        g = disk_block // self._blocks_per_group
        bit = disk_block % self._blocks_per_group
        bmap_disk = self._v.group_descriptors[g].bg_block_bitmap
        bmap_off = bmap_disk * self._bs + bit // 8
        byte = self._read(bmap_off, 1)[0]
        if not (byte & (1 << (7 - bit % 8))):
            # 位图显示该块本就空闲——不应被引用，跳过（防误清共享/重复释放）
            return
        byte &= ~(1 << (7 - bit % 8))
        self._write(bmap_off, bytes([byte]))
        self._freed_by_group[g] = self._freed_by_group.get(g, 0) + 1
        self._total_freed += 1

    # ---------- 目录遍历 ----------
    def _scan(self):
        """返回 markers: [(path, Inode, dirent_ftype_disk_off 或 None)]"""
        markers = []

        def walk_dir(inode, path):
            blkmap = {}
            for fb, db, cnt in self._inode_block_map(inode):
                for k in range(cnt):
                    blkmap[fb + k] = db + k
            data = inode.open_read().read()
            l = len(data)
            is_htree = bool(inode.inode.i_flags & ext4_inode.EXT4_INDEX_FL)
            # 逐块解析；htree 目录的第 0 块是索引元数据（dx_root），跳过
            for fb in range((l + self._bs - 1) // self._bs):
                if fb == 0 and is_htree:
                    continue
                off = fb * self._bs
                end = min(off + self._bs, l)
                db = blkmap.get(fb)
                while off + 8 <= end:
                    inode_n, rec_len, name_len, ftype = struct.unpack_from('<IHBB', data, off)
                    if rec_len == 0:
                        break
                    if off + rec_len > end:
                        break
                    name = data[off + 8: off + 8 + name_len]
                    if name in (b'.', b'..'):
                        off += rec_len
                        continue
                    ftype_disk_off = None
                    if db is not None:
                        ftype_disk_off = db * self._bs + (off + 7) % self._bs
                    if ftype == InodeType.DIRECTORY:
                        try:
                            child = self._v.get_inode(inode_n, InodeType.DIRECTORY)
                        except Exception:
                            off += rec_len
                            continue
                        walk_dir(child, path + '/' + name.decode('utf-8', 'ignore'))
                    elif ftype == InodeType.FILE:
                        try:
                            child = self._v.get_inode(inode_n, InodeType.FILE)
                        except Exception:
                            off += rec_len
                            continue
                        markers.append((path + '/' + name.decode('utf-8', 'ignore'),
                                        child, ftype_disk_off))
                    off += rec_len

        walk_dir(self._v.root, '')
        return markers

    # ---------- 转换单个标记文件 ----------
    def _convert(self, path, child, ftype_disk_off):
        ino = child.inode
        if (ino.i_mode & 0xF000) != 0x8000:  # 仅处理普通文件
            return False
        head = child.open_read().read(len(MARKER))
        if head != MARKER:
            return False
        content = child.open_read().read()
        raw_tgt = content[len(MARKER):]
        # 标记格式: '!<symlink>' + BOM(\xff\xfe) + (char_utf8+0x00)*n + '\x00\x00'
        # 必须先 utf-16 解码成字符串再 rstrip，直接对字节 rstrip 会剥掉最后一字符的配对零
        target = raw_tgt.decode('utf-16', 'ignore').rstrip('\x00')
        if not target:
            return False
        tbytes = target.encode('utf-8')

        data_blocks = []
        for fb, db, cnt in self._inode_block_map(child):
            for k in range(cnt):
                data_blocks.append(db + k)

        inode_off = child.offset
        i_block_area = bytearray(60)
        if len(tbytes) <= 60:
            i_block_area[:len(tbytes)] = tbytes
            new_blocks = 0
            for db in data_blocks:
                self._free_block(db)
        else:
            # 慢链接：目标 > 60 字节，复用第一个数据块存放目标
            if not data_blocks:
                return False
            db = data_blocks[0]
            self._write(db * self._bs, tbytes + b'\x00' * (self._bs - len(tbytes)))
            struct.pack_into('<I', i_block_area, 0, db)
            new_blocks = self._bs // 512
            for extra in data_blocks[1:]:
                self._free_block(extra)

        # 改写 inode
        self._write(inode_off + 0x00, struct.pack('<H', SYMLINK_MODE))   # i_mode
        self._write(inode_off + 0x04, struct.pack('<I', len(tbytes)))    # i_size_lo
        self._write(inode_off + 0x6C, struct.pack('<I', 0))              # i_size_hi
        self._write(inode_off + 0x20, struct.pack('<I', 0))              # i_flags
        self._write(inode_off + 0x1C, struct.pack('<I', new_blocks))     # i_blocks_lo
        self._write(inode_off + 0x74, struct.pack('<H', 0))              # i_osd2_blocks_high
        self._write(inode_off + 0x28, bytes(i_block_area))               # i_block
        # xattr 块（如有）一并释放
        i_file_acl = ino.i_file_acl_lo | (ino.i_file_acl_hi << 32)
        if i_file_acl:
            self._free_block(i_file_acl)
            self._write(inode_off + 0x68, struct.pack('<I', 0))          # i_file_acl_lo
            self._write(inode_off + 0x76, struct.pack('<H', 0))          # i_file_acl_hi
        # 父目录项 file_type: 1(FILE) -> 7(SYMBOLIC_LINK)
        if ftype_disk_off is not None:
            self._write(ftype_disk_off, bytes([InodeType.SYMBOLIC_LINK]))
        self.log('  [修复符号链接] %s -> %s' % (path, target))
        return True

    # ---------- 主流程 ----------
    def run(self):
        markers = self._scan()
        converted = 0
        for path, child, ftype_disk_off in markers:
            try:
                if self._convert(path, child, ftype_disk_off):
                    converted += 1
            except Exception as e:
                self.log('  [警告] 转换失败 %s: %s' % (path, e))
        # 回写空闲块统计
        for g, n in self._freed_by_group.items():
            gd_off = self._gdt_base + g * self._desc_size
            cur = struct.unpack('<H', self._read(gd_off + self._bg_free_blocks_off, 2))[0]
            self._write(gd_off + self._bg_free_blocks_off, struct.pack('<H', cur + n))
            # 修改组描述符后必须重算 bg_checksum，否则真机 fsck/mount 报错
            self._write_gd_checksum(gd_off, g)
        if self._total_freed:
            sb_off = 0x400
            cur = struct.unpack('<I', self._read(sb_off + 0x0C, 4))[0]
            self._write(sb_off + 0x0C, struct.pack('<I', cur + self._total_freed))
        return converted

    def close(self):
        self._f.close()


def is_sparse(img_path):
    """判断镜像是否为 Android sparse 格式"""
    try:
        with open(img_path, 'rb') as f:
            return f.read(4) == SPARSE_MAGIC
    except Exception:
        return False


def fix_symlinks(img_path, log=None, tmp_dir=None):
    """把镜像中的 !<symlink> 标记文件转成真正的 ext4 符号链接。

    支持 raw ext4 与 sparse 格式（sparse 会先解稀疏再重稀疏）。
    返回转换的符号链接数量。
    """
    if log is None:
        log = _normalize_log(None)

    def do_fix(raw_path):
        fx = _Fixer(raw_path, log)
        try:
            n = fx.run()
        finally:
            fx.close()
        return n

    if not is_sparse(img_path):
        return do_fix(img_path)

    # sparse：解稀疏 -> 修复 -> 重新稀疏
    import tempfile
    from .configs import simg2img_bin, img2simg_bin
    import subprocess
    tmpdir = tmp_dir or tempfile.mkdtemp(prefix='symlink_fix_')
    raw_path = os.path.join(tmpdir, 'system_raw.img')
    subprocess.run([simg2img_bin, img_path, raw_path], check=True)
    n = do_fix(raw_path)
    subprocess.run([img2simg_bin, raw_path, img_path], check=True)
    if tmp_dir is None:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    return n


def verify_symlinks(img_path, expected_targets=None):
    """验证镜像中的符号链接：返回 (symlink_list, errors)。

    symlink_list: [(path, target)]
    errors: 不满足条件的说明列表
    """
    f = open(img_path, 'rb')
    v = Volume(f)
    symlinks = []
    errors = []
    want = set(expected_targets or {})

    def walk_dir(inode, path):
        for name, inode_n, ftype in inode.open_dir():
            if name in ('.', '..'):
                continue
            p = path + '/' + name
            if ftype == InodeType.DIRECTORY:
                walk_dir(v.get_inode(inode_n, InodeType.DIRECTORY), p)
            elif ftype == InodeType.SYMBOLIC_LINK:
                child = v.get_inode(inode_n, InodeType.SYMBOLIC_LINK)
                ino = child.inode
                if ino.i_size <= 60:
                    data = child.open_read().read()
                    target = data.decode('utf-8', 'ignore')
                else:
                    # 慢链接：目标存放在 i_block[0] 指向的数据块
                    import struct as _st
                    f.seek(child.offset + 0x28)
                    blk = _st.unpack('<I', f.read(4))[0]
                    f.seek(blk * v.block_size)
                    target = f.read(ino.i_size).decode('utf-8', 'ignore')
                symlinks.append((p, target))
                if p in want and want[p] != target:
                    errors.append('目标不符 %s: 期望 %r 实际 %r' % (p, want[p], target))
            elif ftype == InodeType.FILE:
                # 普通文件不应再是标记文件
                child = v.get_inode(inode_n, InodeType.FILE)
                head = child.open_read().read(10)
                if head == MARKER:
                    errors.append('仍存在未转换的标记文件: %s' % p)

    walk_dir(v.root, '')
    f.close()
    return symlinks, errors


def verify_gd_checksums(img_path):
    """校验镜像所有组描述符的 bg_checksum（与 e2fsck 的 GDT_CSUM 检查同算法）。

    返回 (ok, bad_groups)。bad_groups 为空列表代表全部通过。
    """
    f = open(img_path, 'rb')
    v = Volume(f)
    sb = v.superblock
    if not (sb.s_feature_ro_compat & 0x10):
        f.close()
        return True, []
    uuid = bytes(sb.s_uuid)
    desc_size = sb.s_desc_size
    gdt_base = (0x400 // v.block_size + 1) * v.block_size
    offset = 0x1E
    bad = []
    for g in range(len(v.group_descriptors)):
        f.seek(gdt_base + g * desc_size)
        desc = f.read(desc_size)
        stored = struct.unpack_from('<H', desc, 0x1E)[0]
        crc = _Fixer._crc16_arc(0xFFFF, uuid)
        crc = _Fixer._crc16_arc(crc, struct.pack('<I', g))
        crc = _Fixer._crc16_arc(crc, desc[:offset])
        crc = _Fixer._crc16_arc(crc, desc[offset + 2:desc_size])
        if stored != crc:
            bad.append(g)
    f.close()
    return (len(bad) == 0), bad


def _inode_extents(f, inode, bs):
    """返回 inode 的 extent 列表 [(file_block, disk_block, count), ...]；非 extents inode 返回 []"""
    ino = inode.inode
    out = []
    if not (ino.i_flags & ext4_inode.EXT4_EXTENTS_FL):
        return out
    nodes = [inode.offset + ext4_inode.i_block.offset]
    while nodes:
        hdr_off = nodes.pop()
        f.seek(hdr_off)
        raw = f.read(ctypes.sizeof(ext4_extent_header))
        if len(raw) < ctypes.sizeof(ext4_extent_header):
            continue
        hdr = ext4_extent_header.from_buffer_copy(raw)
        if hdr.eh_magic != 0xF30A:
            continue
        if hdr.eh_depth != 0:
            f.seek(hdr_off + ctypes.sizeof(ext4_extent_header))
            raw = f.read(ctypes.sizeof(ext4_extent_idx) * hdr.eh_entries)
            for i in range(hdr.eh_entries):
                idx = ext4_extent_idx.from_buffer_copy(
                    raw, i * ctypes.sizeof(ext4_extent_idx))
                nodes.append(idx.ei_leaf * bs)
        else:
            f.seek(hdr_off + ctypes.sizeof(ext4_extent_header))
            raw = f.read(ctypes.sizeof(ext4_extent) * hdr.eh_entries)
            for i in range(hdr.eh_entries):
                ext = ext4_extent.from_buffer_copy(
                    raw, i * ctypes.sizeof(ext4_extent))
                out.append((ext.ee_block,
                            (ext.ee_start_hi << 32) | ext.ee_start_lo,
                            ext.ee_len))
    return out


def verify_image_integrity(img_path, log=None):
    """ext4 镜像一致性自查（模拟 e2fsck 关键检查）。

    检查项：
      1. 全组描述符 bg_checksum（GDT_CSUM）
      2. 目录项引用的 inode 在 inode bitmap 中标记为使用
      3. 文件/目录实际引用的数据块在 block bitmap 中标记为使用
      4. 目录项 file_type 与 inode i_mode 类型一致
      5. 无残留 !<symlink> 标记文件

    返回 (ok, errors)。errors 为空列表代表全部通过。
    """
    log = _normalize_log(log)
    f = open(img_path, 'rb')
    v = Volume(f)
    sb = v.superblock
    bs = v.block_size
    errors = []
    checked_inodes = set()
    checked_blocks = set()

    def bitmap_bit(bmap_block, bit):
        f.seek(bmap_block * bs + bit // 8)
        return bool(f.read(1)[0] & (1 << (7 - bit % 8)))

    def inode_bitmap_bit(inode_idx):
        g, idx = divmod(inode_idx - 1, sb.s_inodes_per_group)
        return bitmap_bit(v.group_descriptors[g].bg_inode_bitmap, idx)

    def block_bitmap_bit(block_idx):
        g, idx = divmod(block_idx, sb.s_blocks_per_group)
        return bitmap_bit(v.group_descriptors[g].bg_block_bitmap, idx)

    def walk(inode, path):
        ino = inode.inode
        # 2. inode bitmap
        if not inode_bitmap_bit(inode.inode_idx):
            errors.append('inode %d (%s) 未在 inode bitmap 中标记' % (inode.inode_idx, path))
        checked_inodes.add(inode.inode_idx)
        # 3. 数据块 bitmap
        for fb, start, cnt in _inode_extents(f, inode, bs):
            for k in range(cnt):
                b = start + k
                checked_blocks.add(b)
                if not block_bitmap_bit(b):
                    errors.append('块 %d (%s) 未在 block bitmap 中标记' % (b, path))
        if not inode.is_dir:
            return
        for name, inode_n, ftype in inode.open_dir():
            if name in ('.', '..'):
                continue
            child = v.get_inode(inode_n, ftype)
            # 4. file_type 与 inode mode 一致性
            mode_type = child.inode.i_mode & 0xF000
            if ftype == InodeType.DIRECTORY and mode_type != 0x4000:
                errors.append('%s: dirent=DIR 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
            elif ftype == InodeType.SYMBOLIC_LINK and mode_type != 0xA000:
                errors.append('%s: dirent=SYMLINK 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
            elif ftype == InodeType.FILE and mode_type not in (0x8000, 0xA000):
                errors.append('%s: dirent=FILE 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
            # 5. 标记文件残留
            if ftype == InodeType.FILE:
                head = child.open_read().read(10)
                if head == MARKER:
                    errors.append('%s: 仍是 !<symlink> 标记文件' % (path + '/' + name))
            if ftype == InodeType.DIRECTORY:
                walk(child, path + '/' + name)

    # 1. 组描述符校验和
    gd_ok, gd_bad = verify_gd_checksums(img_path)
    if not gd_ok:
        errors.append('组描述符校验和不匹配: %s' % gd_bad)

    walk(v.root, '')
    f.close()

    log('  [一致性自查] 检查 inode %d 个, 数据块 %d 个, 错误 %d 个' % (
        len(checked_inodes), len(checked_blocks), len(errors)))
    for e in errors[:20]:
        log('    !! ' + e)
    return (len(errors) == 0), errors


def fix_inode_bitmaps(img_path, log=None):
    """修复 make_ext4fs 可能产生的 inode bitmap 未标记问题。

    遍历所有目录项引用的 inode，若其在 inode bitmap 中未标记，则标记之，
    并更新组描述符 bg_free_inodes_count 与 GDT_CSUM。
    返回修复的 inode 数量。
    """
    log = _normalize_log(log)
    f = open(img_path, 'r+b')
    v = Volume(f)
    sb = v.superblock
    bs = v.block_size

    # 收集所有被目录项引用的 inode
    referenced = set()

    def walk(inode):
        referenced.add(inode.inode_idx)
        if not inode.is_dir:
            return
        for name, ino, ftype in inode.open_dir():
            if name in ('.', '..'):
                continue
            walk(v.get_inode(ino, ftype))

    walk(v.root)

    # 检查并修复未标记的 inode
    fixed = 0
    group_fixed = {}
    for ino_num in sorted(referenced):
        g, idx = divmod(ino_num - 1, sb.s_inodes_per_group)
        bmap = v.group_descriptors[g].bg_inode_bitmap
        f.seek(bmap * bs + idx // 8)
        byte = f.read(1)[0]
        if not (byte & (1 << (7 - idx % 8))):
            byte |= (1 << (7 - idx % 8))
            f.seek(bmap * bs + idx // 8)
            f.write(bytes([byte]))
            fixed += 1
            group_fixed[g] = group_fixed.get(g, 0) + 1

    if fixed == 0:
        f.close()
        return 0

    # 更新组描述符 bg_free_inodes_count 并重算 GDT_CSUM
    desc_size = sb.s_desc_size
    gdt_base = (0x400 // bs + 1) * bs
    uuid = bytes(sb.s_uuid)
    has_gdt_csum = bool(sb.s_feature_ro_compat & 0x10)

    for g, cnt in group_fixed.items():
        gd_off = gdt_base + g * desc_size
        # bg_free_inodes_count_lo at offset 0x0E
        f.seek(gd_off + 0x0E)
        cur = struct.unpack('<H', f.read(2))[0]
        new_val = max(0, cur - cnt)
        f.seek(gd_off + 0x0E)
        f.write(struct.pack('<H', new_val))

        if has_gdt_csum:
            f.seek(gd_off)
            desc = bytearray(f.read(desc_size))
            crc = _Fixer._crc16_arc(0xFFFF, uuid)
            crc = _Fixer._crc16_arc(crc, struct.pack('<I', g))
            crc = _Fixer._crc16_arc(crc, bytes(desc[:0x1E]))
            crc = _Fixer._crc16_arc(crc, bytes(desc[0x20:desc_size]))
            struct.pack_into('<H', desc, 0x1E, crc)
            f.seek(gd_off)
            f.write(bytes(desc))

    f.close()
    log('  [inode bitmap 修复] 修复 %d 个未标记 inode' % fixed)
    return fixed


if __name__ == '__main__':
    import sys as _sys
    target = _sys.argv[1] if len(_sys.argv) > 1 else 'out/system.img'
    ok, errs = verify_image_integrity(target, log=print)
    print('\n结论: %s' % ('全部通过' if ok else '存在 %d 个问题' % len(errs)))
