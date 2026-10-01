# -*- coding: utf-8 -*-
# ============================================================
# OPPO / Realme / OnePlus 固件解密模块（三合一）
# Merged and modified from B. Kerler's tools (MIT License):
#   ofp_mtk_decrypt.py   (c) B. Kerler 2022
#   ozipdecrypt.py       (c) B. Kerler 2017-2020
#   opscrypto.py         (c) B. Kerler 2019-2021
#   https://github.com/bkerler
# Modified by mtk-garbage-porttool (1.3-beta3):
#   - AES 后端：openssl 子进程优先（如已安装），内置 pyaes 纯 Python 兜底
#   - 中间缓存统一 tmp/oppo_decrypt/，最终产物输出到指定 outdir
#   - 失败明确报错（不再 exit(0) 伪成功）；原始固件保留不动
# ============================================================
import binascii
import hashlib
import mmap
import os
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from struct import pack, unpack

from . import pyaes
from .utils import _rmtree


# ============================================================
# AES 后端：openssl（快）优先，pyaes（纯 Python）兜底
# ============================================================
def _find_openssl():
    """探测可用 openssl：工具 bin/ 目录（逐个「存在+可运行」体检）→ 系统 PATH。

    #90 修复：候选组件（如 Windows 专用 openssl.exe 在 Linux 上）存在但不可运行
    时，不能直接 return None，必须继续尝试下一个候选，全部失败后再回退系统 PATH，
    否则 Linux/跨平台环境会静默降级 pyaes（大包解密慢约 229 倍）。
    """
    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / 'bin' / 'win' / 'x86_64' / 'openssl.exe',
        root / 'bin' / 'linux' / 'x86_64' / 'openssl',
    ]
    for c in candidates:
        if not c.exists():
            continue
        try:
            r = subprocess.run([str(c), 'version'], capture_output=True, timeout=8)
            if r.returncode == 0:
                return str(c)
        except Exception:
            pass
    # 全部候选失败 → 回退系统 PATH（Linux 发行版自带 /usr/bin/openssl）
    w = shutil.which('openssl')
    if w:
        try:
            r = subprocess.run([w, 'version'], capture_output=True, timeout=8)
            if r.returncode == 0:
                return w
        except Exception:
            pass
    return None


_OPENSSL = _find_openssl()


def backend_name():
    """当前 AES 后端名称（供日志显示）。"""
    return 'openssl（加速）' if _OPENSSL else 'pyaes（纯Python）'


def _openssl_decrypt(mode, key, iv, data):
    args = [_OPENSSL, 'enc', '-d', mode, '-K',
            binascii.hexlify(key).decode(), '-nosalt', '-nopad']
    if iv is not None:
        args += ['-iv', binascii.hexlify(iv).decode()]
    r = subprocess.run(args, input=data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError('openssl 解密失败：' + r.stderr.decode('utf-8', 'replace').strip())
    return r.stdout


def aes_ecb_decrypt(key, data):
    """AES-128-ECB 解密（自动补齐块，返回前 len(data) 字节）。"""
    n = len(data)
    pad = (-n) % 16
    if pad:
        data = data + b'\x00' * pad
    if _OPENSSL:
        out = _openssl_decrypt('-aes-128-ecb', key, None, data)
    else:
        # pyaes ECB .decrypt 为单块方法，多块须逐块解密
        _m = pyaes.AESModeOfOperationECB(key)
        out = b''.join(_m.decrypt(data[i:i + 16]) for i in range(0, len(data), 16))
    return out[:n]


def aes_cfb128_decrypt(key, iv, data):
    """AES-128-CFB（段128位）解密，返回前 len(data) 字节。"""
    n = len(data)
    pad = (-n) % 16
    if pad:
        data = data + b'\x00' * pad
    if _OPENSSL:
        out = _openssl_decrypt('-aes-128-cfb', key, iv, data)
    else:
        # pyaes 的 segment_size 单位为字节（16 = CFB128）；CFB 走 Decrypter 流接口
        _dec = pyaes.Decrypter(pyaes.AESModeOfOperationCFB(key, iv, segment_size=16))
        out = _dec.feed(data) + _dec.feed()
    return out[:n]


# ============================================================
# 一、OFP（MTK）解密 —— ofp_mtk_decrypt.py
# ============================================================
def swap(ch):
    return ((ch & 0xF) << 4) + ((ch & 0xF0) >> 4)


def keyshuffle(key, hkey):
    for i in range(0, 0x10, 4):
        key[i] = swap(hkey[i] ^ key[i])
        key[i + 1] = swap(hkey[i + 1] ^ key[i + 1])
        key[i + 2] = swap(hkey[i + 2] ^ key[i + 2])
        key[i + 3] = swap(hkey[i + 3] ^ key[i + 3])
    return key


def mtk_shuffle(key, keylength, inp, inputlength):
    for i in range(0, inputlength):
        k = key[i % keylength]
        h = (((inp[i]) & 0xF0) >> 4) | (16 * ((inp[i]) & 0xF))
        inp[i] = k ^ h
    return inp


def mtk_shuffle2(key, keylength, inp, inputlength):
    for i in range(0, inputlength):
        tmp = key[i % keylength] ^ inp[i]
        inp[i] = ((tmp & 0xF0) >> 4) | (16 * (tmp & 0xF))
    return inp


_OFP_KEYTABLES = [
    ["67657963787565E837D226B69A495D21",  # A77 CPH1715, F1S A1601 MT6750
     "F6C50203515A2CE7D8C3E1F938B7E94C",
     "42F2D5399137E2B2813CD8ECDF2F4D72"],
    ["9E4F32639D21357D37D226B69A495D21",
     "A3D8D358E42F5A9E931DD3917D9A3218",
     "386935399137416B67416BECF22F519A"],
    ["892D57E92A4D8A975E3C216B7C9DE189",
     "D26DF2D9913785B145D18C7219B89F26",
     "516989E4A1BFC78B365C6BC57D944391"],
    ["27827963787265EF89D126B69A495A21",
     "82C50203285A2CE7D8C3E198383CE94C",
     "422DD5399181E223813CD8ECDF2E4D72"],
    ["3C4A618D9BF2E4279DC758CD535147C3",
     "87B13D29709AC1BF2382276C4E8DF232",
     "59B7A8E967265E9BCABE2469FE4A915E"],
    ["1C3288822BF824259DC852C1733127D3",  # A83 CPH1827, Realme 3 RMX1827
     "E7918D22799181CF2312176C9E2DF298",
     "3247F889A7B6DECBCA3E28693E4AAAFE"],
    ["1E4F32239D65A57D37D2266D9A775D43",
     "A332D3C3E42F5A3E931DD991729A321D",
     "3F2A35399A373377674155ECF28FD19A"],
    ["122D57E92A518AFF5E3C786B7C34E189",
     "DD6DF2D9543785674522717219989FB0",
     "12698965A132C76136CC88C5DD94EE91"],
    ["ab3f76d7989207f2",  # AES KEY
     "2bf515b3a9737835"]  # AES IV
]


def _safe_unhexlify(h, index):
    try:
        if len(h) % 2:
            raise binascii.Error('odd-length hex string')
        return bytearray(binascii.unhexlify(h))
    except (binascii.Error, ValueError) as e:
        raise ValueError(f'OFP 密钥表 keyid={index} 存在非法 hex（{h}）：{e}')


def _ofp_getkey(index):
    kt = _OFP_KEYTABLES[index]
    if len(kt) == 3:
        obskey = _safe_unhexlify(kt[0], index)
        encaeskey = _safe_unhexlify(kt[1], index)
        encaesiv = _safe_unhexlify(kt[2], index)
        aeskey = binascii.hexlify(
            hashlib.md5(mtk_shuffle2(obskey, 16, encaeskey, 16)).digest())[:16]
        aesiv = binascii.hexlify(
            hashlib.md5(mtk_shuffle2(obskey, 16, encaesiv, 16)).digest())[:16]
    else:
        aeskey = bytes(kt[0], 'utf-8')
        aesiv = bytes(kt[1], 'utf-8')
    return aeskey, aesiv


def _ofp_brutekey(rf, emit):
    rf.seek(0)
    encdata = rf.read(16)
    for keyid in range(0, len(_OFP_KEYTABLES)):
        try:
            aeskey, aesiv = _ofp_getkey(keyid)
            data = aes_cfb128_decrypt(aeskey, aesiv, encdata)
        except Exception as e:
            emit(f"【警告】keyid={keyid} 密钥表异常（{e}），跳过该 keyid")
            continue
        if data[:3] == b"MMM":
            return aeskey, aesiv
    emit("【错误】OFP 密钥不匹配（当前密钥表未覆盖此机型），已中止")
    return None


def _clean_cstring(inp):
    return inp.replace(b"\x00", b"").decode('utf-8')


def _ofp_mtk(filename, outdir, emit):
    hdrkey = bytearray(b"geyixue")
    filesize = os.stat(filename).st_size
    hdrlength = 0x6C
    with open(filename, 'rb') as rf:
        keyiv = _ofp_brutekey(rf, emit)
        if not keyiv:
            return False
        aeskey, aesiv = keyiv
        rf.seek(filesize - hdrlength)
        hdr = mtk_shuffle(hdrkey, len(hdrkey),
                          bytearray(rf.read(hdrlength)), hdrlength)
        prjname, _unknown, _reserved, cpu, flashtype, hdr2entries, prjinfo, _crc = \
            unpack("46s Q 4s 7s 5s H 32s H", hdr)
        hdr2length = hdr2entries * 0x60
        prjname = _clean_cstring(prjname)
        prjinfo = _clean_cstring(prjinfo)
        cpu = _clean_cstring(cpu)
        flashtype = _clean_cstring(flashtype)
        if prjname:
            emit(f"  - 项目名：{prjname}")
        if prjinfo:
            emit(f"  - 项目信息：{prjinfo}")
        if cpu:
            emit(f"  - CPU：{cpu}")
        if flashtype:
            emit(f"  - 闪存类型：{flashtype}")

        rf.seek(filesize - hdr2length - hdrlength)
        hdr2 = mtk_shuffle(hdrkey, len(hdrkey),
                           bytearray(rf.read(hdr2length)), hdr2length)
        for i in range(0, len(hdr2) // 0x60):
            entry = hdr2[i * 0x60:(i * 0x60) + 0x60]
            name, start, length, enclength, partfile, _crc = \
                unpack("<32s Q Q Q 32s Q", entry)
            name = name.replace(b"\x00", b"").decode('utf-8')
            partfile = partfile.replace(b"\x00", b"").decode('utf-8')
            emit(f"  - 导出分区 \"{name}\" → {partfile}")
            with open(os.path.join(outdir, partfile), 'wb') as wb:
                if enclength > 0:
                    rf.seek(start)
                    encdata = rf.read(enclength)
                    if enclength % 16 != 0:
                        encdata += b"\x00" * (16 - (enclength % 16))
                    data = aes_cfb128_decrypt(aeskey, aesiv, encdata)
                    wb.write(data[:enclength])
                    length -= enclength
                while length > 0:
                    size = 0x200000 if length >= 0x200000 else length
                    wb.write(rf.read(size))
                    length -= size
    emit("  - OFP 全部分区导出完成")
    return True


# ============================================================
# 二、OZIP（Realme / OPPO）解密 —— ozipdecrypt.py
# ============================================================
_OZIP_KEYS = [
    "D6EECF0AE5ACD4E0E9FE522DE7CE381E",  # mnkey
    "D6ECCF0AE5ACD4E0E92E522DE7C1381E",  # mkey
    "D6DCCF0AD5ACD4E0292E522DB7C1381E",
    "D7DCCE1AD4AFDCE2393E5161CBDC4321",  # testkey
    "D7DBCE2AD4ADDCE1393E5521CBDC4321",  # utilkey
    "D7DBCE1AD4AFDCE1393E5121CBDC4321",  # R11s CPH1719
    "D4D2CD61D4AFDCE13B5E01221BD14D20",  # FindX CPH1871
    "261CC7131D7C1481294E532DB752381E",
    "1CA21E12271335AE33AB81B2A7B14622",  # Realme 2 Pro
    "D4D2CE11D4AFDCE13B3E0121CBD14D20",  # K1
    "1C4C1EA3A12531AE491B21BB31613C11",  # Realme 3 Pro / X / 5 Pro / Q
    "1C4C1EA3A12531AE4A1B21BB31C13C21",  # Reno 10x zoom
    "1C4A11A3A12513AE441B23BB31513121",  # Reno 2
    "1C4A11A3A12589AE441B23BB31517733",  # Realme X2
    "1C4A11A3A22513AE541B53BB31513121",  # Realme 5
    "2442CE821A4F352E33AE81B22BC1462E",  # R17 Pro
    "14C2CD6214CFDC2733AE81B22BC1462C",  # CPH1803 A3s
    "1E38C1B72D522E29E0D4ACD50ACFDCD6",
    "12341EAAC4C123CE193556A1BBCC232D",
    "2143DCCB21513E39E1DCAFD41ACEDBD7",
    "2D23CCBBA1563519CE23C1C4AA1E3412",  # A77 CPH1715 MT6750T
    "172B3E14E46F3CE13E2B5121CBDC4321",  # Realme 1 MTK P60
    "ACAA1E12A71431CE4A1B21BBA1C1C6A2",  # Realme U1 MTK P70
    "ACAC1E13A12531AE4A1B22BB31C1CC22",  # Realme 3 RMX1825 P70
    "1C4411A3A12533AE441B21BB31613C11",  # A1k CPH1923 MTK P22
    "1C4416A8A42717AE441523B336513121",  # Reno3 MTK / A92 / A72
    "55EEAA33112133AE441B23BB31513121",  # RenoAce
    "ACAC1E13A12531AE4A1B21BB31C13C21",  # Reno / K3
    "ACAC1E13A72431AE4A1B22BBA1C1C6A2",  # A9
    "12CAC11211AAC3AEA2658690122C1E81",  # A1 / A83t
    "1CA21E12271435AE331B81BBA7C14612",  # CPH1909 A5s MT6765
    "D1DACF24351CE4F279CE32ED87323216",
    "A1CC75115CAECB890E4A563CA1AC67C8",
    "2132321EA2CA86621A11241ABA512722",
    "22A21E821743E5EE33AE81B227B1462E",
]


def _ozip_keytest(data, emit):
    for key in _OZIP_KEYS:
        dat = aes_ecb_decrypt(binascii.unhexlify(key), data)
        if dat[0:4] in (b'\x50\x4B\x03\x04', b'\x41\x56\x42\x30',
                        b'\x41\x4E\x44\x52'):
            emit("  - 找到正确 AES 密钥：" + key)
            return binascii.unhexlify(key)
    return None


def _rmrf(path):
    import stat
    if os.path.exists(path):
        if os.path.isfile(path):
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        else:
            shutil.rmtree(path, onerror=lambda a, n, e: (os.chmod(n, stat.S_IWRITE), os.remove(n)))


def _ozip_decryptfile(key, rfilename, emit):
    """PK 型 OZIP：对提取出的单个加密文件就地解密。"""
    with open(rfilename, 'rb') as rr:
        with open(rfilename + ".tmp", 'wb') as wf:
            rr.seek(0x10)
            dsize = int(rr.read(0x10).replace(b"\x00", b"").decode('utf-8'), 10)
            rr.seek(0x1050)
            emit(f"  - 解密 {os.path.basename(rfilename)}")
            flen = os.stat(rfilename).st_size - 0x1050
            BATCH_N = 512  # 攒批：512 块 × 0x4000 = 8MB 密文一次解密，避免逐 16KB 起子进程（#89）
            while dsize > 0:
                blobs = []    # 本批密文块（每块 0x4000，尾块可能不足）
                wsize_l = []  # 每块实际写入长度（受 dsize 限制）
                for _ in range(BATCH_N):
                    if dsize <= 0:
                        break
                    size = 0x4000 if flen > 0x4000 else flen
                    data = rr.read(size)
                    if len(data) == 0:
                        break
                    wsize = dsize if dsize < size else size
                    blobs.append(data)
                    wsize_l.append(wsize)
                    flen -= size
                    dsize -= wsize
                if not blobs:
                    break
                dec = aes_ecb_decrypt(key, b''.join(blobs))
                off = 0
                for data, wsize in zip(blobs, wsize_l):
                    wf.write(dec[off:off + wsize])
                    off += len(data)
    os.remove(rfilename)
    os.rename(rfilename + ".tmp", rfilename)


def _ozip_decryptfile2(key, rfilename, wfilename):
    """mode2 分段解密（OPPOENCRYPT! 块链）。返回 1 表示结构异常。"""
    with open(rfilename, 'rb') as rr:
        with open(wfilename, 'wb') as wf:
            bstart = 0
            goon = True
            while goon:
                rr.seek(bstart)
                header = rr.read(12)
                if len(header) == 0:
                    break
                if header != b"OPPOENCRYPT!":
                    return 1
                rr.seek(0x10 + bstart)
                bdsize = int(rr.read(0x10).replace(b"\x00", b"").decode('utf-8'), 10)
                if bdsize < 0x40000:
                    goon = False
                rr.seek(0x50 + bstart)
                while bdsize > 0:
                    data = rr.read(0x10)
                    if len(data) == 0:
                        break
                    size = 0x10 if bdsize >= 0x10 else bdsize
                    wf.write(aes_ecb_decrypt(key, data)[:size])
                    bdsize -= 0x10
                    data = rr.read(0x3FF0)
                    if len(data) == 0:
                        break
                    bdsize -= 0x3FF0
                    wf.write(data)
                bstart = bstart + 0x40000 + 0x50
    return 0


def _ozip_mode2(filename, workdir, emit):
    """CPH1803 / CPH1909 类：zip 内文件按 OPPOENCRYPT! 块链加密。"""
    import stat
    temp = os.path.join(workdir, "temp")
    outzip = os.path.join(workdir, os.path.basename(filename)[:-5] + ".zip")
    with open(filename, 'rb') as fr:
        with zipfile.ZipFile(filename, 'r') as zipObj:
            if os.path.exists(temp):
                _rmrf(temp)
            os.mkdir(temp)
            emit("  - 正在查找密钥 ...")
            for zi in zipObj.infolist():
                orgfilename = zi.filename
                if "boot.img" in orgfilename:
                    zi.filename = "out"
                    zipObj.extract(zi, temp)
                    zi.filename = orgfilename
                    with open(os.path.join(temp, "out"), 'rb') as rr:
                        magic = rr.read(12)
                        if magic == b"OPPOENCRYPT!":
                            rr.seek(0x50)
                            key = _ozip_keytest(rr.read(16), emit)
                            if key is None:
                                emit("【错误】OZIP 密钥不匹配（需从 recovery 反推密钥），已中止")
                                return None
                            break
                        else:
                            # 明文 OZIP（PK 型但未加密，如部分 realmeUI 1.0 旧包）：
                            # boot.img 非 OPPOENCRYPT! → 整包按普通卡刷包使用，无需解密
                            emit("【提示】该 OZIP 为明文（boot.img 未加密），无需解密，按普通卡刷包使用")
                            if os.path.exists(outzip):
                                os.remove(outzip)
                            emit("  - 正在复制固件包 ...")
                            import shutil
                            with open(filename, 'rb') as _fr, open(outzip, 'wb') as _fw:
                                shutil.copyfileobj(_fr, _fw, 4 << 20)
                            try:
                                _rmrf(temp)
                            except Exception:
                                pass
                            return outzip
            else:
                emit("【错误】固件中未找到 boot.img，无法确定密钥")
                return None

            emit("  - 正在解密并重建固件包 ...")
            if os.path.exists(outzip):
                os.remove(outzip)
            with zipfile.ZipFile(outzip, 'w', zipfile.ZIP_DEFLATED) as Wzip:
                for zi in zipObj.infolist():
                    orgfilename = zi.filename
                    zi.filename = "out"
                    zipObj.extract(zi, temp)
                    zi.filename = orgfilename
                    with open(os.path.join(temp, "out"), 'rb') as rr:
                        magic = rr.read(12)
                    if magic == b"OPPOENCRYPT!":
                        emit(f"  - 解密 {orgfilename}")
                        dec = os.path.join(temp, "out") + ".dec"
                        if _ozip_decryptfile2(key, os.path.join(temp, "out"), dec) == 1:
                            emit("【错误】mode2 块结构异常，已中止")
                            return None
                        Wzip.write(dec, orgfilename)
                        os.remove(os.path.join(temp, "out"))
                        os.remove(dec)
                    else:
                        Wzip.write(os.path.join(temp, "out"), orgfilename)
                        os.remove(os.path.join(temp, "out"))
            _rmrf(temp)
    return outzip


def _ozip(filename, workdir, emit):
    """OZIP 解密，返回解密后的 .zip 路径（失败 None）。"""
    with open(filename, 'rb') as fr:
        magic = fr.read(12)
        if magic == b"OPPOENCRYPT!":
            pk = False
        elif magic[:2] == b"PK":
            pk = True
        else:
            emit("【错误】OZIP 魔数无法识别（应为 OPPOENCRYPT!），已中止")
            return None

        if not pk:
            # 普通 OZIP：整包解密
            fr.seek(0x1050)
            key = _ozip_keytest(fr.read(16), emit)
            if key is None:
                emit("【错误】OZIP 密钥不匹配（需从 recovery 反推密钥），已中止")
                return None
            outzip = os.path.join(workdir, os.path.basename(filename)[:-5] + ".zip")
            BATCH = 1024  # 攒批：每批 1024 组（16B 密文 + 0x4000 明文），密文拼块一次解密，避免逐 16B 起子进程
            with open(outzip, 'wb') as wf:
                fr.seek(0x1050)
                emit("  - 正在整包解密 ...")
                while True:
                    enc = []      # 本批密文块（每块 16B）
                    plain = []    # 本批明文段（每段 0x4000，尾段可能不足）
                    for _ in range(BATCH):
                        data = fr.read(16)
                        if len(data) == 0:
                            break
                        enc.append(data)
                        data = fr.read(0x4000)
                        if len(data) == 0:
                            break
                        plain.append(data)
                    if not enc:
                        break
                    dec = aes_ecb_decrypt(key, b''.join(enc))
                    n = len(enc)
                    for i in range(n):
                        wf.write(dec[i * 16:(i + 1) * 16])
                        if i < len(plain):
                            wf.write(plain[i])
            return outzip
        else:
            # PK 型 OZIP：读 oppo_metadata 按清单逐文件解密
            outpath = os.path.join(workdir, "work")
            if os.path.exists(outpath):
                shutil.rmtree(outpath)
            os.mkdir(outpath)
            try:
                zobj = zipfile.ZipFile(filename, 'r')
            except zipfile.BadZipFile as e:
                emit("【错误】固件 zip 结构损坏或解密可能不完整（%s），已中止" % e)
                return None
            with zobj as zo:
                clist = []
                try:
                    zo.extract('oppo_metadata', outpath)
                    with open(os.path.join(outpath, 'oppo_metadata')) as rt:
                        for line in rt:
                            clist.append(line[:-1])
                except Exception:
                    emit("  - 未找到 oppo_metadata，按 mode2 处理 ...")
                    return _ozip_mode2(filename, workdir, emit)

                fname = ''
                if "firmware-update/vbmeta.img" in clist:
                    fname = "firmware-update/vbmeta.img"
                elif "vbmeta.img" in clist:
                    fname = 'vbmeta.img'
                if fname:
                    zo.extract(fname, outpath)
                    with open(os.path.join(outpath, fname.replace("/", os.sep)), "rb") as rt:
                        rt.seek(0x1050)
                        key = _ozip_keytest(rt.read(16), emit)
                        if key is None:
                            emit("【错误】OZIP 密钥不匹配（需从 recovery 反推密钥），已中止")
                            return None
                else:
                    emit("【错误】固件中未找到 vbmeta.img，无法确定密钥")
                    return None

                outzip = os.path.join(workdir, os.path.basename(filename)[:-5] + ".zip")
                emit("  - 正在按清单解密并重建固件包 ...")
                with zipfile.ZipFile(outzip, 'w', zipfile.ZIP_DEFLATED) as Wzip:
                    for info in zo.infolist():
                        orgfilename = info.filename
                        info.filename = "out"
                        zo.extract(info, outpath)
                        info.filename = orgfilename
                        out_file = os.path.join(outpath, "out")
                        if clist and info.filename in clist:
                            _ozip_decryptfile(key, out_file, emit)
                        elif not clist:
                            with open(out_file, 'rb') as rr:
                                m2 = rr.read(12)
                            if m2 == b"OPPOENCRYPT!":
                                _ozip_decryptfile(key, out_file, emit)
                        Wzip.write(out_file, orgfilename)
                return outzip


# ============================================================
# 三、OPS（OnePlus）解密 —— opscrypto.py
# ============================================================
def _mmap_io(filename, mode, length=0):
    if mode == "rb":
        with open(filename, mode="rb") as f:
            return mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
    elif mode == "wb":
        if os.path.exists(filename):
            length = os.stat(filename).st_size
        else:
            with open(filename, "wb") as wf:
                wf.write(length * b'\0')
        with open(filename, mode="r+b") as f:
            return mmap.mmap(f.fileno(), length=length, access=mmap.ACCESS_WRITE)


_OPS_KEY = unpack("<4I", bytes.fromhex("d1b5e39e5eea049d671dd5abd2afcbaf"))

_OPS_MBOX5 = [0x60, 0x8a, 0x3f, 0x2d, 0x68, 0x6b, 0xd4, 0x23, 0x51, 0x0c,
              0xd0, 0x95, 0xbb, 0x40, 0xe9, 0x76] + [0] * 44 + [0x0a, 0x00]
_OPS_MBOX6 = [0xAA, 0x69, 0x82, 0x9E, 0x5D, 0xDE, 0xB1, 0x3D, 0x30, 0xBB,
              0x81, 0xA3, 0x46, 0x65, 0xa3, 0xe1] + [0] * 44 + [0x0a, 0x00]
_OPS_MBOX4 = [0xC4, 0x5D, 0x05, 0x71, 0x99, 0xDD, 0xBB, 0xEE, 0x29, 0xA1,
              0x6D, 0xC7, 0xAD, 0xBF, 0xA4, 0x3F] + [0] * 44 + [0x0a, 0x00]

_OPS_SBOX = bytes.fromhex(
    "c66363a5c66363a5f87c7c84f87c7c84ee777799ee777799f67b7b8df67b7b8dfff2f20dfff2f20dd66b6bbdd66b6bbdde6f6fb1de6f6fb191c5c55491c5c55460303050603030500201010302010103ce6767a9ce6767a9562b2b7d562b2b7de7fefe19e7fefe19b5d7d762b5d7d7624dababe64dababe6ec76769aec76769a8fcaca458fcaca451f82829d1f82829d89c9c94089c9c940fa7d7d87fa7d7d87effafa15effafa15b25959ebb25959eb8e4747c98e4747c9fbf0f00bfbf0f00b41adadec41adadecb3d4d467b3d4d4675fa2a2fd5fa2a2fd45afafea45afafea239c9cbf239c9cbf53a4a4f753a4a4f7e4727296e47272969bc0c05b9bc0c05b75b7b7c275b7b7c2e1fdfd1ce1fdfd1c3d9393ae3d9393ae4c26266a4c26266a6c36365a6c36365a7e3f3f417e3f3f41f5f7f702f5f7f70283cccc4f83cccc4f6834345c6834345c51a5a5f451a5a5f4d1e5e534d1e5e534f9f1f108f9f1f108e2717193e2717193abd8d873abd8d87362313153623131532a15153f2a15153f0804040c0804040c95c7c75295c7c75246232365462323659dc3c35e9dc3c35e3018182830181828379696a1379696a10a05050f0a05050f2f9a9ab52f9a9ab50e0707090e07070924121236241212361b80809b1b80809bdfe2e23ddfe2e23dcdebeb26cdebeb264e2727694e2727697fb2b2cd7fb2b2cdea75759fea75759f1209091b1209091b1d83839e1d83839e582c2c74582c2c74341a1a2e341a1a2e361b1b2d361b1b2ddc6e6eb2dc6e6eb2b45a5aeeb45a5aee5ba0a0fb5ba0a0fba45252f6a45252f6763b3b4d763b3b4db7d6d661b7d6d6617db3b3ce7db3b3ce5229297b5229297bdde3e33edde3e33e5e2f2f715e2f2f711384849713848497a65353f5a65353f5b9d1d168b9d1d1680000000000000000c1eded2cc1eded2c4020206040202060e3fcfc1fe3fcfc1f79b1b1c879b1b1c8b65b5bedb65b5bedd46a6abed46a6abe8dcbcb468dcbcb4667bebed967bebed97239394b7239394b944a4ade944a4ade984c4cd4984c4cd4b05858e8b05858e885cfcf4a85cfcf4abbd0d06bbbd0d06bc5efef2ac5efef2a4faaaae54faaaae5edfbfb16edfbfb16864343c5864343c59a4d4dd79a4d4dd7663333556633335511858594118585948a4545cf8a4545cfe9f9f910e9f9f9100402020604020206fe7f7f81fe7f7f81a05050f0a05050f0783c3c44783c3c44259f9fba259f9fba4ba8a8e34ba8a8e3a25151f3a25151f35da3a3fe5da3a3fe804040c0804040c0058f8f8a058f8f8a3f9292ad3f9292ad219d9dbc219d9dbc7038384870383848f1f5f504f1f5f50463bcbcdf63bcbcdf77b6b6c177b6b6c1afdada75afdada7542212163422121632010103020101030e5ffff1ae5ffff1afdf3f30efdf3f30ebfd2d26dbfd2d26d81cdcd4c81cdcd4c180c0c14180c0c142613133526131335c3ecec2fc3ecec2fbe5f5fe1be5f5fe1359797a2359797a2884444cc884444cc2e1717392e17173993c4c45793c4c45755a7a7f255a7a7f2fc7e7e82fc7e7e827a3d3d477a3d3d47c86464acc86464acba5d5de7ba5d5de73219192b3219192be6737395e6737395c06060a0c06060a019818198198181989e4f4fd19e4f4fd1a3dcdc7fa3dcdc7f4422226644222266542a2a7e542a2a7e3b9090ab3b9090ab0b8888830b8888838c4646ca8c4646cac7eeee29c7eeee296bb8b8d36bb8b8d32814143c2814143ca7dede79a7dede79bc5e5ee2bc5e5ee2160b0b1d160b0b1daddbdb76addbdb76dbe0e03bdbe0e03b6432325664323256743a3a4e743a3a4e140a0a1e140a0a1e924949db924949db0c06060a0c06060a4824246c4824246cb85c5ce4b85c5ce49fc2c25d9fc2c25dbdd3d36ebdd3d36e43acacef43acacefc46262a6c46262a6399191a8399191a8319595a4319595a4d3e4e437d3e4e437f279798bf279798bd5e7e732d5e7e7328bc8c8438bc8c8436e3737596e373759da6d6db7da6d6db7018d8d8c018d8d8cb1d5d564b1d5d5649c4e4ed29c4e4ed249a9a9e049a9a9e0d86c6cb4d86c6cb4ac5656faac5656faf3f4f407f3f4f407cfeaea25cfeaea25ca6565afca6565aff47a7a8ef47a7a8e47aeaee947aeaee910080818100808186fbabad56fbabad5f0787888f07878884a25256f4a25256f5c2e2e725c2e2e72381c1c24381c1c2457a6a6f157a6a6f173b4b4c773b4b4c797c6c65197c6c651cbe8e823cbe8e823a1dddd7ca1dddd7ce874749ce874749c3e1f1f213e1f1f21964b4bdd964b4bdd61bdbddc61bdbddc0d8b8b860d8b8b860f8a8a850f8a8a85e0707090e07070907c3e3e427c3e3e4271b5b5c471b5b5c4cc6666aacc6666aa904848d8904848d80603030506030305f7f6f601f7f6f6011c0e0e121c0e0e12c26161a3c26161a36a35355f6a35355fae5757f9ae5757f969b9b9d069b9b9d0178686911786869199c1c15899c1c1583a1d1d273a1d1d27279e9eb9279e9eb9d9e1e138d9e1e138ebf8f813ebf8f8132b9898b32b9898b32211113322111133d26969bbd26969bba9d9d970a9d9d970078e8e89078e8e89339494a7339494a72d9b9bb62d9b9bb63c1e1e223c1e1e221587879215878792c9e9e920c9e9e92087cece4987cece49aa5555ffaa5555ff5028287850282878a5dfdf7aa5dfdf7a038c8c8f038c8c8f59a1a1f859a1a1f809898980098989801a0d0d171a0d0d1765bfbfda65bfbfdad7e6e631d7e6e631844242c6844242c6d06868b8d06868b8824141c3824141c3299999b0299999b05a2d2d775a2d2d771e0f0f111e0f0f117bb0b0cb7bb0b0cba85454fca85454fc6dbbbbd66dbbbbd62c16163a2c16163a")


def _ops_gsbox(offset):
    return int.from_bytes(_OPS_SBOX[offset:offset + 4], 'little')


def _ops_key_update(iv1, asbox):
    d = iv1[0] ^ asbox[0]
    a = iv1[1] ^ asbox[1]
    b = iv1[2] ^ asbox[2]
    c = iv1[3] ^ asbox[3]
    e = _ops_gsbox(((b >> 0x10) & 0xff) * 8 + 2) ^ \
        _ops_gsbox(((a >> 8) & 0xff) * 8 + 3) ^ \
        _ops_gsbox((c >> 0x18) * 8 + 1) ^ \
        _ops_gsbox((d & 0xff) * 8) ^ asbox[4]
    h = _ops_gsbox(((c >> 0x10) & 0xff) * 8 + 2) ^ \
        _ops_gsbox(((b >> 8) & 0xff) * 8 + 3) ^ \
        _ops_gsbox((d >> 0x18) * 8 + 1) ^ \
        _ops_gsbox((a & 0xff) * 8) ^ asbox[5]
    i = _ops_gsbox(((d >> 0x10) & 0xff) * 8 + 2) ^ \
        _ops_gsbox(((c >> 8) & 0xff) * 8 + 3) ^ \
        _ops_gsbox((a >> 0x18) * 8 + 1) ^ \
        _ops_gsbox((b & 0xff) * 8) ^ asbox[6]
    a = _ops_gsbox(((d >> 8) & 0xff) * 8 + 3) ^ \
        _ops_gsbox(((a >> 0x10) & 0xff) * 8 + 2) ^ \
        _ops_gsbox((b >> 0x18) * 8 + 1) ^ \
        _ops_gsbox((c & 0xff) * 8) ^ asbox[7]
    g = 8
    for f in range(asbox[0x3c] - 2):
        d = e >> 0x18
        m = h >> 0x10
        s = h >> 0x18
        z = e >> 0x10
        l = i >> 0x18
        t = e >> 8
        e = _ops_gsbox(((i >> 0x10) & 0xff) * 8 + 2) ^ \
            _ops_gsbox(((h >> 8) & 0xff) * 8 + 3) ^ \
            _ops_gsbox((a >> 0x18) * 8 + 1) ^ \
            _ops_gsbox((e & 0xff) * 8) ^ asbox[g]
        h = _ops_gsbox(((a >> 0x10) & 0xff) * 8 + 2) ^ \
            _ops_gsbox(d * 8 + 1) ^ \
            _ops_gsbox((h & 0xff) * 8) ^ asbox[g + 1]
        i = _ops_gsbox((z & 0xff) * 8 + 2) ^ \
            _ops_gsbox(s * 8 + 1) ^ \
            _ops_gsbox((i & 0xff) * 8) ^ asbox[g + 2]
        a = _ops_gsbox((t & 0xff) * 8 + 3) ^ \
            _ops_gsbox((m & 0xff) * 8 + 2) ^ \
            _ops_gsbox(l * 8 + 1) ^ \
            _ops_gsbox((a & 0xff) * 8) ^ asbox[g + 3]
        g = g + 4
    return [
        (_ops_gsbox(((i >> 0x10) & 0xff) * 8) & 0xff0000) ^
        (_ops_gsbox(((h >> 8) & 0xff) * 8 + 1) & 0xff00) ^
        (_ops_gsbox((a >> 0x18) * 8 + 3) & 0xff000000) ^
        _ops_gsbox((e & 0xff) * 8 + 2) & 0xFF ^ asbox[g],
        (_ops_gsbox(((a >> 0x10) & 0xff) * 8) & 0xff0000) ^
        (_ops_gsbox(((i >> 8) & 0xff) * 8 + 1) & 0xff00) ^
        (_ops_gsbox((e >> 0x18) * 8 + 3) & 0xff000000) ^
        (_ops_gsbox((h & 0xff) * 8 + 2) & 0xFF) ^ asbox[g + 3],
        (_ops_gsbox(((e >> 0x10) & 0xff) * 8) & 0xff0000) ^
        (_ops_gsbox(((a >> 8) & 0xff) * 8 + 1) & 0xff00) ^
        (_ops_gsbox((h >> 0x18) * 8 + 3) & 0xff000000) ^
        (_ops_gsbox((i & 0xff) * 8 + 2) & 0xFF) ^ asbox[g + 2],
        (_ops_gsbox(((h >> 0x10) & 0xff) * 8) & 0xff0000) ^
        (_ops_gsbox(((e >> 8) & 0xff) * 8 + 1) & 0xff00) ^
        (_ops_gsbox((i >> 0x18) * 8 + 3) & 0xff000000) ^
        (_ops_gsbox((a & 0xff) * 8 + 2) & 0xFF) ^ asbox[g + 1]]


def _ops_key_custom(inp, rkey, outlength=0, encrypt=False, mbox=None):
    outp = bytearray()
    inp = bytearray(inp)
    pos = outlength
    outp_extend = outp.extend
    ptr = 0
    length = len(inp)
    if outlength != 0:
        while pos < len(rkey):
            if length == 0:
                break
            buffer = inp[pos]
            outp_extend(rkey[pos] ^ buffer)
            rkey[pos] = buffer
            length -= 1
            pos += 1
    if length > 0xF:
        for ptr in range(0, length, 0x10):
            rkey = _ops_key_update(rkey, mbox)
            if pos < 0x10:
                slen = ((0xf - pos) >> 2) + 1
                tmp = [rkey[i] ^ int.from_bytes(
                    inp[pos + i * 4 + ptr:pos + i * 4 + ptr + 4], "little")
                    for i in range(0, slen)]
                outp.extend(b"".join(tmp[i].to_bytes(4, 'little')
                                     for i in range(0, slen)))
                if encrypt:
                    rkey = tmp
                else:
                    rkey = [int.from_bytes(
                        inp[pos + i * 4 + ptr:pos + i * 4 + ptr + 4], "little")
                        for i in range(0, slen)]
            length = length - 0x10
    if length != 0:
        rkey = _ops_key_update(rkey, _OPS_SBOX)
        j = pos
        m = 0
        while length > 0:
            data = inp[j + ptr:j + ptr + 4]
            if len(data) < 4:
                data += b"\x00" * (4 - len(data))
            tmp = int.from_bytes(data, 'little')
            outp_extend((tmp ^ rkey[m]).to_bytes(4, 'little'))
            if encrypt:
                rkey[m] = tmp ^ rkey[m]
            else:
                rkey[m] = tmp
            length -= 4
            j += 4
            m += 1
    return outp


def _ops_extractxml(filename, rkey, workdir, mbox):
    sfilename = os.path.join(workdir, "settings.xml")
    filesize = os.stat(filename).st_size
    with _mmap_io(filename, 'rb') as rf:
        rf.seek(filesize - 0x200)
        hdr = rf.read(0x200)
        xmllength = int.from_bytes(hdr[0x18:0x18 + 4], 'little')
        xmlpad = 0x200 - (xmllength % 0x200)
        rf.seek(filesize - 0x200 - (xmllength + xmlpad))
        inp = rf.read(xmllength + xmlpad)
    outp = _ops_key_custom(inp, list(rkey), 0, mbox=mbox)
    if b"xml " not in outp:
        return None
    with _mmap_io(sfilename, 'wb', xmllength) as wf:
        wf.write(outp[:xmllength])
    return outp[:xmllength].decode('utf-8')


def _ops_decryptfile(rkey, filename, path, wfilename, start, length, emit, mbox):
    sha256 = hashlib.sha256()
    emit(f"  - 提取（加密）{wfilename}")
    with _mmap_io(filename, 'rb') as rf:
        rf.seek(start)
        data = rf.read(length)
        if length % 4:
            data += (4 - (length % 4)) * b'\x00'
        outp = _ops_key_custom(data, rkey, 0, mbox=mbox)
        sha256.update(outp[:length])
        with _mmap_io(os.path.join(path, wfilename), 'wb', length) as wf:
            wf.write(outp[:length])
    if length % 0x1000 > 0:
        sha256.update(b"\x00" * (0x1000 - (length % 0x1000)))
    return sha256.hexdigest()


def _ops_copyfile(filename, path, wfilename, start, length, emit):
    emit(f"  - 提取 {wfilename}")
    with _mmap_io(filename, 'rb') as rf:
        with _mmap_io(os.path.join(path, wfilename), 'wb', length) as wf:
            rf.seek(start)
            while length > 0:
                size = 0x100000 if length >= 0x100000 else length
                wf.write(rf.read(size))
                length -= size


def _ops_calc_digest(filename):
    with _mmap_io(filename, 'rb') as rf:
        data = rf.read()
    sha256 = hashlib.sha256()
    sha256.update(data)
    if len(data) % 0x1000 > 0:
        sha256.update(b"\x00" * (0x1000 - (len(data) % 0x1000)))
    return sha256.hexdigest()


def _ops(filename, outdir, workdir, emit):
    xml = None
    mbox_used = None
    for name, mbox in (("MBox5", _OPS_MBOX5), ("MBox6", _OPS_MBOX6),
                       ("MBox4", _OPS_MBOX4)):
        # 每次尝试使用独立的初始 key（避免被上一次尝试修改）
        xml = _ops_extractxml(filename, _OPS_KEY, workdir, mbox)
        if xml is not None:
            mbox_used = mbox
            emit(f"  - 密钥方案：{name}")
            break
    if xml is None:
        emit("【错误】OPS 密钥不匹配（MBox4/5/6 均不支持此固件），已中止")
        return False

    rkey = list(_OPS_KEY)
    root = ET.fromstring(xml)
    for child in root:
        if child.tag == "SAHARA":
            for item in child:
                if item.tag == "File":
                    wfilename = item.attrib["Path"]
                    start = int(item.attrib["FileOffsetInSrc"]) * 0x200
                    length = int(item.attrib["SizeInByteInSrc"])
                    _ops_decryptfile(rkey, filename, outdir, wfilename,
                                     start, length, emit, mbox_used)
        elif child.tag == "UFS_PROVISION":
            for item in child:
                if item.tag == "File":
                    wfilename = item.attrib["Path"]
                    start = int(item.attrib["FileOffsetInSrc"]) * 0x200
                    length = int(item.attrib["SizeInByteInSrc"])
                    _ops_copyfile(filename, outdir, wfilename,
                                  start, length, emit)
        elif "Program" in child.tag:
            for item in child:
                if "filename" in item.attrib:
                    wfilename = item.attrib["filename"]
                    if wfilename == "":
                        continue
                    sparse = item.attrib["sparse"] == "true"
                    start = int(item.attrib["FileOffsetInSrc"]) * 0x200
                    length = int(item.attrib["SizeInByteInSrc"])
                    sha256 = item.attrib["Sha256"]
                    _ops_copyfile(filename, outdir, wfilename,
                                  start, length, emit)
                    if not sparse:
                        csha = _ops_calc_digest(os.path.join(outdir, wfilename))
                        if sha256 != csha:
                            emit(f"【警告】分区 {wfilename} SHA256 校验不一致")
                else:
                    for sub in item:
                        if "filename" in sub.attrib:
                            wfilename = sub.attrib["filename"]
                            if wfilename == "":
                                continue
                            sparse = sub.attrib["sparse"] == "true"
                            start = int(sub.attrib["FileOffsetInSrc"]) * 0x200
                            length = int(sub.attrib["SizeInByteInSrc"])
                            sha256 = sub.attrib["Sha256"]
                            _ops_copyfile(filename, outdir, wfilename,
                                          start, length, emit)
                            if not sparse:
                                csha = _ops_calc_digest(
                                    os.path.join(outdir, wfilename))
                                if sha256 != csha:
                                    emit(f"【警告】分区 {wfilename} SHA256 校验不一致")
    emit("  - OPS 全部分区导出完成")
    return True


# ============================================================
# 格式识别与统一入口
# ============================================================
def detect_format(path):
    """按扩展名 + 魔数识别固件格式：ofp_mtk / ozip / ops / None。"""
    name = path.lower()
    try:
        with open(path, 'rb') as f:
            magic = f.read(12)
    except OSError:
        return None
    if name.endswith('.ops'):
        return 'ops'
    if name.endswith('.ofp'):
        return 'ofp_mtk'
    if name.endswith('.ozip'):
        if magic == b'OPPOENCRYPT!' or magic[:2] == b'PK':
            return 'ozip'
    # 扩展名缺失/不符时的魔数兜底
    if magic == b'OPPOENCRYPT!':
        return 'ozip'
    return None


def _convert_to_img(outdir, emit):
    """把展开目录中的 .new.dat[.br] 转换成分区 img（复用工具 sdat2img）。
    boot.img / firmware-update 等已是镜像，原样保留。
    #91：不再只处理 system/vendor——动态收集全部 *.new.dat.br 分区
    （含 Android 10+ 的 product/odm/system_ext 等），逐个转换，遗漏分区不再静默。
    .br 需先经 brotli 解压（多后端：系统命令 → Python 库，无则明确提示）。
    转换完成后清理大中间文件（new.dat.br / new.dat / transfer.list / patch.dat）。
    返回 True/False。
    """
    from .sdat2img import main as sdat2img
    from . import brotli
    ok = True
    # 动态收集分区：*.new.dat.br 优先，*.new.dat 且配对 transfer.list 兜底
    parts = []
    for fn in sorted(os.listdir(outdir)):
        if fn.endswith('.new.dat.br'):
            parts.append(fn[:-len('.new.dat.br')])
        elif fn.endswith('.new.dat') and os.path.isfile(
                os.path.join(outdir, fn[:-len('.new.dat')] + '.transfer.list')):
            parts.append(fn[:-len('.new.dat')])
    seen = set()
    parts = [p for p in parts if not (p in seen or seen.add(p))]
    if not parts:
        return ok
    for part in parts:
        br = os.path.join(outdir, f'{part}.new.dat.br')
        dat = os.path.join(outdir, f'{part}.new.dat')
        tlist = os.path.join(outdir, f'{part}.transfer.list')
        img = os.path.join(outdir, f'{part}.img')
        if os.path.isfile(br):
            emit(f"【格式转换】检测到 {part}.new.dat.br，解压为 {part}.new.dat ...")
            if not os.path.isfile(dat):
                try:
                    brotli.brotli_decompress(br, dat, emit)
                except brotli.BrotliUnavailable as e:
                    emit(f"【错误】{e}")
                    emit(f"【提示】{part}.new.dat.br 未转换，原文件保留在输出目录（boot/firmware 等镜像不受影响）")
                    ok = False
                    continue
                except Exception as e:
                    emit(f"【错误】brotli 解压失败：{e}")
                    ok = False
                    continue
            emit(f"【解压完成】{part}.new.dat 已生成")
        if os.path.isfile(dat) and os.path.isfile(tlist):
            emit(f"【格式转换】{part}.new.dat → {part}.img ...")
            try:
                sdat2img(tlist, dat, img, emit)
                emit(f"【转换完成】{part}.img 已生成")
            except SystemExit as e:
                emit(f"【错误】sdat2img 转换失败（exit {e.code}）")
                ok = False
                continue
            except Exception as e:
                emit(f"【错误】sdat2img 转换失败：{e}")
                ok = False
                continue
            # 清理大中间文件（保留 img）
            for f in (br, dat, tlist, os.path.join(outdir, f'{part}.patch.dat')):
                try:
                    if os.path.isfile(f):
                        os.remove(f)
                except Exception:
                    pass
            emit(f"【清理】已移除 {part} 转换中间文件（.br/.dat/transfer.list/patch.dat）")
    return ok


def decrypt(path, outdir, log=None, out_type='img'):
    """固件解密统一入口。
    path：固件文件（.ofp/.ozip/.ops）
    outdir：最终产物目录（镜像输出位置）
    out_type：'img'（默认）展开并转换成分区镜像；'zip' 直接输出解密后的卡刷 zip（不展开）
    log：日志文件对象（默认 stdout）
    返回 True/False。
    """
    def emit(msg):
        print(msg, file=log)

    if not os.path.isfile(path):
        emit(f"【错误】固件文件不存在：{path}")
        return False
    fmt = detect_format(path)
    workdir = Path("tmp/oppo_decrypt")
    if workdir.exists():
        _rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    emit(f"【解密】固件：{path}")
    emit(f"【解密】识别格式：{fmt}")
    emit(f"【解密】AES 后端：{backend_name()}")
    emit(f"【解密】输出类型：{'zip 卡刷包（不展开）' if out_type == 'zip' else 'img 镜像'}")
    if _OPENSSL is None:
        if sys.platform.startswith('linux'):
            emit("【提示】未检测到 OpenSSL 命令，已自动使用内置 pyaes（纯Python）解密（功能正常，速度较慢）；"
                 "Linux 可安装系统 openssl 提速：Debian/Ubuntu: apt install openssl，CentOS: dnf install openssl")
        else:
            emit("【提示】未检测到 OpenSSL 加速组件，已自动使用内置 pyaes（纯Python）解密（功能正常，速度较慢）；"
                 "如需加速可双击运行工具目录下的「获取openssl加速组件.bat」（可选）")
    ok = False
    try:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        if fmt == 'ofp_mtk':
            if out_type == 'zip':
                emit("【提示】OFP 固件为分区镜像流、无卡刷 zip 形态，out_type 仅对 OZIP 生效，本次仍按镜像输出")
            ok = _ofp_mtk(path, outdir, emit)
        elif fmt == 'ozip':
            zippath = _ozip(path, str(workdir), emit)
            if zippath:
                if out_type == 'zip':
                    # 不展开：解密后的 zip 即标准卡刷包（META-INF + new.dat.br + firmware-update）
                    base = os.path.basename(path)
                    if base.lower().endswith('.ozip'):
                        base = base[:-5] + '.zip'
                    else:
                        base = os.path.splitext(base)[0] + '.zip'
                    dst = os.path.join(outdir, base)
                    shutil.move(zippath, dst)
                    emit(f"【输出】解密卡刷包（未展开）：{dst}")
                    ok = True
                else:
                    emit(f"【解压】正在展开固件镜像到 {outdir} ...")
                    outdir_abs = os.path.abspath(outdir)
                    with zipfile.ZipFile(zippath) as zf:
                        for name in zf.namelist():
                            target = os.path.abspath(os.path.join(outdir_abs, name))
                            if not (target == outdir_abs or target.startswith(outdir_abs + os.sep)):
                                emit(f"[警告] 跳过非法 zip 条目（路径穿越）: {name}")
                                continue
                            zf.extract(name, outdir_abs)
                    conv_ok = _convert_to_img(outdir, emit)
                    if conv_ok:
                        ok = True
                    else:
                        # #92：解密本身已成功，仅部分分区格式转换失败——不报「解密失败」
                        emit("【提示】固件解密成功，但部分分区格式转换失败，原 .new.dat[.br] 已保留在输出目录（boot/firmware 等镜像不受影响）")
                        ok = True
        elif fmt == 'ops':
            if out_type == 'zip':
                emit("【提示】OPS 固件为分区镜像流、无卡刷 zip 形态，out_type 仅对 OZIP 生效，本次仍按镜像输出")
            ok = _ops(path, outdir, str(workdir), emit)
        else:
            emit("【错误】无法识别的固件格式（非 OFP/OZIP/OPS），请确认文件")
            ok = False
    except Exception as e:
        emit(f"【错误】解密失败：{e}")
        ok = False
    finally:
        try:
            _rmtree(workdir)
        except Exception:
            pass
    if ok:
        emit(f"【完成】固件已{'输出卡刷包到' if out_type == 'zip' else '解密到'}：{outdir}")
    return ok
