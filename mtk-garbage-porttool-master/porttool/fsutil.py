# -*- coding: utf-8 -*-
"""fsutil.py — 文件系统小工具（从 mtk-garbage-porttool 的 porttool/utils.py 摘出）

原 utils.py 是移植工具 2600+ 行的功能集合，解密模块只用到下面两个函数，
因此按「摘函数不搬文件」原则独立成模块，避免把 bootimg/ext4/configs 等
移植依赖带进本工具。

依赖：仅标准库。
"""
import os
from os import name as osname, stat, chmod
from pathlib import Path
from shutil import rmtree

if osname == 'nt':
    from ctypes import windll


def _clear_attrs(path):
    """清除 Windows 只读/系统/隐藏属性，使文件可被写入或删除。"""
    try:
        if osname == 'nt':
            windll.kernel32.SetFileAttributesW(str(path), 0x80)  # FILE_ATTRIBUTE_NORMAL
        else:
            # POSIX：保留原有权限，仅确保可写。
            # 不能直接 chmod(path, S_IWRITE)（=0200 只写），否则后续读取文件会 PermissionError。
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
