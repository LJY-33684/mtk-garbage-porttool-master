# -*- coding: utf-8 -*-
"""ext4 镜像一致性自查（模拟 e2fsck 关键检查）
1. 全组描述符 bg_checksum（GDT_CSUM）
2. 目录项引用的 inode 在 inode bitmap 中标记为使用
3. 文件/目录实际引用的数据块在块位图中标记为使用
4. 目录项 file_type 与 inode 类型一致
"""
import sys, struct, ctypes
from porttool.ext4 import Volume, InodeType, ext4_inode, ext4_extent, ext4_extent_idx, ext4_extent_header
from porttool.symlink_fix import verify_gd_checksums, MARKER

IMG = sys.argv[1] if len(sys.argv) > 1 else 'out/system.img'

f = open(IMG, 'rb')
v = Volume(f)
sb = v.superblock
bs = v.block_size
inode_size = sb.s_inode_size
errors = []
total_inodes = sb.s_inodes_count

# 位图访问
def bitmap_bit(offset, bit):
    f.seek(offset + bit // 8)
    b = f.read(1)[0]
    return bool(b & (1 << (7 - bit % 8)))

def inode_bitmap_bit(inode_idx):
    g, idx = divmod(inode_idx - 1, sb.s_inodes_per_group)
    bmap = v.group_descriptors[g].bg_inode_bitmap
    return bitmap_bit(bmap * bs, idx)

def block_bitmap_bit(block_idx):
    g, idx = divmod(block_idx, sb.s_blocks_per_group)
    bmap = v.group_descriptors[g].bg_block_bitmap
    return bitmap_bit(bmap * bs, idx)

def extents(inode):
    ino = inode.inode
    out = []
    if not (ino.i_flags & ext4_inode.EXT4_EXTENTS_FL):
        return out
    nodes = [inode.offset + ext4_inode.i_block.offset]
    while nodes:
        hdr_off = nodes.pop()
        f.seek(hdr_off); raw = f.read(ctypes.sizeof(ext4_extent_header))
        if len(raw) < ctypes.sizeof(ext4_extent_header):
            continue
        hdr = ext4_extent_header.from_buffer_copy(raw)
        if hdr.eh_magic != 0xF30A:
            continue
        if hdr.eh_depth != 0:
            f.seek(hdr_off + ctypes.sizeof(ext4_extent_header))
            raw = f.read(ctypes.sizeof(ext4_extent_idx) * hdr.eh_entries)
            for i in range(hdr.eh_entries):
                idx = ext4_extent_idx.from_buffer_copy(raw, i * ctypes.sizeof(ext4_extent_idx))
                nodes.append(idx.ei_leaf * bs)
        else:
            f.seek(hdr_off + ctypes.sizeof(ext4_extent_header))
            raw = f.read(ctypes.sizeof(ext4_extent) * hdr.eh_entries)
            for i in range(hdr.eh_entries):
                ext = ext4_extent.from_buffer_copy(raw, i * ctypes.sizeof(ext4_extent))
                out.append((ext.ee_block, (ext.ee_start_hi << 32) | ext.ee_start_lo, ext.ee_len))
    return out

print('== 1. 组描述符校验和 ==')
ok, bad = verify_gd_checksums(IMG)
print('  %s (bad=%s)' % ('PASS' if ok else 'FAIL', bad))
if not ok:
    errors.append('组校验和不匹配: %s' % bad)

print('== 2. 目录项 inode 位图 / 块位图 / file_type 一致性 ==')
checked_inodes = set()
checked_blocks = set()
count_files = 0

def walk(inode, path):
    global count_files
    ino = inode.inode
    # inode 是否在位图
    if not inode_bitmap_bit(inode.inode_idx):
        errors.append('inode %d (%s) 不在 inode bitmap' % (inode.inode_idx, path))
    checked_inodes.add(inode.inode_idx)
    # 数据块是否在位图
    for fb, start, cnt in extents(inode):
        for k in range(cnt):
            b = start + k
            checked_blocks.add(b)
            if not block_bitmap_bit(b):
                errors.append('块 %d (%s) 未在位图中标记' % (b, path))
    if not inode.is_dir:
        count_files += 1
        return
    for name, inode_n, ftype in inode.open_dir():
        if name in ('.', '..'):
            continue
        child = v.get_inode(inode_n, ftype)
        # file_type 与 inode mode 类型一致性
        mode_type = child.inode.i_mode & 0xF000
        if ftype == InodeType.DIRECTORY and mode_type != 0x4000:
            errors.append('%s: dirent=DIR 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
        elif ftype == InodeType.SYMBOLIC_LINK and mode_type != 0xA000:
            errors.append('%s: dirent=SYMLINK 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
        elif ftype == InodeType.FILE and mode_type not in (0x8000, 0xA000):
            errors.append('%s: dirent=FILE 但 inode mode=0x%X' % (path + '/' + name, child.inode.i_mode))
        # 标记文件残留检查（顺带）
        if ftype == InodeType.FILE:
            head = child.open_read().read(10)
            if head == MARKER:
                errors.append('%s: 仍是 !<symlink> 标记文件' % (path + '/' + name))
        if ftype == InodeType.DIRECTORY:
            walk(child, path + '/' + name)

walk(v.root, '')
print('  检查文件/链接/目录 inode 数: %d, 引用数据块数: %d' % (len(checked_inodes), len(checked_blocks)))
print('  错误数: %d' % len(errors))
for e in errors[:20]:
    print('   !!', e)

f.close()
print('\n== 结论: %s ==' % ('全部通过' if not errors else '存在 %d 个问题' % len(errors)))
