# -*- coding: utf-8 -*-
"""纯 Python 的 LZ4 解压（frame / legacy frame / raw block 自动识别），无第三方依赖。

Android 8+ 的 boot ramdisk 常为 lz4 压缩（boot header v1 时代）。
当运行环境无法安装 PyPI lz4 库（如 Python 3.15 无 wheel、编译失败）时，
本模块提供内置解压能力，保证移植工具解 lz4 ramdisk 不依赖外部包。

用法（bootimg.py 等）：
    from lz4 import decompress
    raw = decompress(lz4_data)   # 自动识别 frame / legacy / block

校验说明：帧头校验、块校验、内容校验均按 LZ4 frame 规范实现，
校验失败抛 Lz4Error，不静默放行。

支持：标准 frame（独立块 block_independent 与依赖块 dependent/linked 均支持）、
legacy frame、raw block 自动识别。带字典（dictionary）的 frame 不支持。
"""


class Lz4Error(Exception):
    """LZ4 解压错误"""
    pass


# ----------------------------- XXH32 ------------------------------

_PRIME1 = 2654435761
_PRIME2 = 2246822519
_PRIME3 = 3266489917
_PRIME4 = 668265263
_PRIME5 = 374761393
_MASK32 = 0xFFFFFFFF


def _rotl(x, r):
    return ((x << r) | (x >> (32 - r))) & _MASK32


def xxh32(data, seed=0):
    """xxHash32，返回 32 位无符号整数（LZ4 frame 校验用）。"""
    n = len(data)
    i = 0
    if n >= 16:
        v1 = (seed + _PRIME1 + _PRIME2) & _MASK32
        v2 = (seed + _PRIME2) & _MASK32
        v3 = seed & _MASK32
        v4 = (seed - _PRIME1) & _MASK32
        while i <= n - 16:
            l1 = int.from_bytes(data[i:i + 4], 'little')
            l2 = int.from_bytes(data[i + 4:i + 8], 'little')
            l3 = int.from_bytes(data[i + 8:i + 12], 'little')
            l4 = int.from_bytes(data[i + 12:i + 16], 'little')
            v1 = (_rotl((v1 + l1 * _PRIME2) & _MASK32, 13) * _PRIME1) & _MASK32
            v2 = (_rotl((v2 + l2 * _PRIME2) & _MASK32, 13) * _PRIME1) & _MASK32
            v3 = (_rotl((v3 + l3 * _PRIME2) & _MASK32, 13) * _PRIME1) & _MASK32
            v4 = (_rotl((v4 + l4 * _PRIME2) & _MASK32, 13) * _PRIME1) & _MASK32
            i += 16
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _MASK32
    else:
        h = (seed + _PRIME5) & _MASK32
    h = (h + n) & _MASK32
    while i <= n - 4:
        h = (h + int.from_bytes(data[i:i + 4], 'little') * _PRIME3) & _MASK32
        h = (_rotl(h, 17) * _PRIME4) & _MASK32
        i += 4
    while i < n:
        h = (h + data[i] * _PRIME5) & _MASK32
        h = (_rotl(h, 11) * _PRIME1) & _MASK32
        i += 1
    h ^= h >> 15
    h = (h * _PRIME2) & _MASK32
    h ^= h >> 13
    h = (h * _PRIME3) & _MASK32
    h ^= h >> 16
    return h & _MASK32


# ------------------------- LZ4 BLOCK 解压 --------------------------

def decompress_block(data, out=None):
    """解压单个 LZ4 block（无头）。

    out: 依赖块（dependent/linked）模式共享的输出缓冲；传入时本块追加到
    out 末尾并返回 None（匹配允许引用历史数据）。为 None 时新建缓冲并
    返回本块解压的全部内容（独立块模式）。
    """
    own = out is None
    if own:
        out = bytearray()
    start = len(out)
    i = 0
    n = len(data)
    while i < n:
        token = data[i]
        i += 1
        # 字面量长度
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = data[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        out += data[i:i + lit_len]
        i += lit_len
        if i >= n:
            # 最后一个序列可以只有字面量（无 match）
            break
        # 匹配偏移（2 字节小端）
        offset = data[i] | (data[i + 1] << 8)
        i += 2
        if offset == 0:
            raise Lz4Error('invalid match offset 0')
        if offset > len(out):
            raise Lz4Error('match offset %d exceeds output size %d' % (offset, len(out)))
        # 匹配长度 = 低 4 位 + 4，低 4 位为 15 时扩展
        match_len = (token & 0x0F) + 4
        if match_len == 19:
            while True:
                b = data[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        # 允许重叠拷贝（LZ4 语义）
        for _ in range(match_len):
            out.append(out[-offset])
    if own:
        return bytes(out)
    return None


# ------------------------- LZ4 FRAME 解压 --------------------------

_FRAME_MAGIC = 0x184D2204    # 文件字节 04 22 4D 18
_LEGACY_MAGIC = 0x184C2102   # 文件字节 02 21 4C 18


def decompress_frame(data):
    """解压标准 LZ4 frame（带 FLG/BD/校验）。"""
    if len(data) < 7:
        raise Lz4Error('lz4 frame too short (%d bytes)' % len(data))
    if int.from_bytes(data[:4], 'little') != _FRAME_MAGIC:
        raise Lz4Error('not a lz4 frame')
    flg = data[4]
    bd = data[5]
    version = (flg >> 6) & 0x03
    if version != 1:
        raise Lz4Error('unsupported lz4 frame version %d' % version)
    block_indep = (flg >> 5) & 0x01
    block_checksum = (flg >> 4) & 0x01
    has_csize = (flg >> 3) & 0x01
    has_ccs = (flg >> 2) & 0x01
    has_dict = flg & 0x01
    if has_dict:
        raise Lz4Error('lz4 frame with dictionary not supported')
    block_max = 1 << (8 + ((bd >> 4) & 0x07) * 2)
    off = 7
    if has_csize:
        content_size = int.from_bytes(data[6:14], 'little')
        off = 15
    # 头校验和：xxh32(HC 之前的所有头字节，不含 4 字节 magic) 的高 8 位
    if (xxh32(data[4:off - 1], 0) >> 8) & 0xFF != data[off - 1]:
        raise Lz4Error('lz4 frame header checksum mismatch')
    out = bytearray()
    while True:
        if off + 4 > len(data):
            raise Lz4Error('lz4 frame truncated (block size header)')
        block_size = int.from_bytes(data[off:off + 4], 'little')
        off += 4
        if block_size == 0:
            break
        uncompressed = (block_size >> 31) & 0x01
        size = block_size & 0x7FFFFFFF
        if size > block_max:
            raise Lz4Error('lz4 block size %d exceeds max %d' % (size, block_max))
        if off + size > len(data):
            raise Lz4Error('lz4 frame truncated (block data)')
        block = data[off:off + size]
        off += size
        if uncompressed:
            out += block
        elif block_indep:
            out += decompress_block(block)
        else:
            # dependent（linked）块：匹配可引用历史输出，共享累积缓冲
            decompress_block(block, out)
        if block_checksum:
            if off + 4 > len(data):
                raise Lz4Error('lz4 frame truncated (block checksum)')
            if int.from_bytes(data[off:off + 4], 'big') != xxh32(block, 0):
                raise Lz4Error('lz4 block checksum mismatch')
            off += 4
    if has_csize and len(out) != content_size:
        raise Lz4Error('lz4 content size mismatch: declared %d, got %d'
                       % (content_size, len(out)))
    if has_ccs:
        if off + 4 > len(data):
            raise Lz4Error('lz4 frame truncated (content checksum)')
        if int.from_bytes(data[off:off + 4], 'big') != xxh32(bytes(out), 0):
            raise Lz4Error('lz4 content checksum mismatch')
    return bytes(out)


def decompress_legacy(data):
    """解压 legacy LZ4 frame（无 FLG/BD/校验，块均压缩）。"""
    if len(data) < 8:
        raise Lz4Error('legacy lz4 frame too short')
    out = bytearray()
    off = 4
    while True:
        if off + 4 > len(data):
            raise Lz4Error('legacy lz4 frame truncated')
        size = int.from_bytes(data[off:off + 4], 'little')
        off += 4
        if size == 0:
            break
        if off + size > len(data):
            raise Lz4Error('legacy lz4 frame truncated (block)')
        out += decompress_block(data[off:off + size])
        off += size
    return bytes(out)


def decompress(data):
    """自动识别并解压 LZ4 数据（标准 frame / legacy frame）。

    boot ramdisk 的 lz4 帧魔数为 04 22 4D 18（标准 frame）。
    """
    if len(data) < 4:
        raise Lz4Error('lz4 data too short (%d bytes)' % len(data))
    magic = int.from_bytes(data[:4], 'little')
    if magic == _FRAME_MAGIC:
        return decompress_frame(data)
    if magic == _LEGACY_MAGIC:
        return decompress_legacy(data)
    # 无标准/legacy 头：尝试按裸 LZ4 block 解压（部分厂商直接塞 raw block），
    # 失败则明确报错，不静默
    try:
        return decompress_block(data)
    except Lz4Error as e:
        raise Lz4Error('unknown lz4 magic 0x%08x (not frame/legacy)，raw block 解压失败：%s' % (magic, e))
