# -*- coding: utf-8 -*-
"""
brotli.py — .br 解压统一入口（多后端探测，跨平台，开箱即用）

背景：Android 9+ OTA 卡刷包中 system/vendor 分区常为 new.dat.br（brotli 压缩）。
brotli 没有可用的纯 Python 实现（唯一项目无许可证且极慢），故采用与
openssl 加速组件一致的多后端策略，探测顺序依次为
  1. 工具自带 brotli 二进制（Windows：bin\\win\\x86_64\\brotli.exe，随包分发；
     Linux：系统命令或下方内置 vendor 库）
  2. 工具内置 vendor brotli 库（porttool\\_vendor_brotli\\，按解释器 ABI 匹配
     cp312/cp313/cp314 × win/linux，开箱即用，无需 pip 安装）
  3. 系统 PATH 中的 brotli 命令（Linux 发行版 apt/dnf 安装后即有）
  4. Python 的 brotli 库（pip install brotli，跨平台）
  5. Python 的 brotlicffi 库（pip install brotlicffi，跨平台）
均未命中时抛出 BrotliUnavailable 并在日志中给出明确安装提示（不静默降级）。

注意：老固件（Android 8 以下，new.dat 无 .br）不会触发本模块。
"""
import os
import shutil
import subprocess
import sys

# ---- 异常 ----------------------------------------------------------
class BrotliUnavailable(RuntimeError):
    """未找到任何可用的 brotli 解码后端。"""


# ---- 后端探测 ------------------------------------------------------
# 工具自带 brotli.exe 路径（随包分发在 bin\win\x86_64）
_TOOL_BIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'bin', 'win', 'x86_64', 'brotli.exe')
# 工具内置 vendor 库目录（wheel 解包，扁平结构：_brotli.pyd/.so + brotli.py）
_VENDOR_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '_vendor_brotli')
_BIN = None          # 外部 brotli 命令路径（None=未找到）
_MOD = None          # 已导入的 Python 库模块（vendor / brotli / brotlicffi）
_BACKEND_NAME = None

def _probe():
    global _BIN, _MOD, _BACKEND_NAME
    if _BACKEND_NAME is not None:
        return
    # 1) 工具自带 brotli.exe → 系统命令
    for cand in (_TOOL_BIN, shutil.which('brotli')):
        if not cand:
            continue
        # 冒烟验证：命令确实能执行（避免 PATH 里是同名垃圾）
        try:
            r = subprocess.run([cand, '--version'], capture_output=True,
                               timeout=10, text=True)
            if r.returncode == 0 or 'brotli' in (r.stdout + r.stderr).lower():
                _BIN = cand
                _BACKEND_NAME = 'bundle-cmd' if cand == _TOOL_BIN else 'system-cmd'
                return
        except Exception:
            pass
    _BIN = None
    # 2) 工具内置 vendor 库（按 ABI 试 import，匹配不上自动跳过）
    if os.path.isdir(_VENDOR_DIR):
        for sub in sorted(os.listdir(_VENDOR_DIR)):
            pkgdir = os.path.join(_VENDOR_DIR, sub)
            if not os.path.isfile(os.path.join(pkgdir, 'brotli.py')):
                continue
            try:
                sys.path.insert(0, pkgdir)
                mod = __import__('brotli')
                if hasattr(mod, 'decompress'):
                    _MOD = mod
                    _BACKEND_NAME = 'vendor:' + sub.split('-')[2]
                    return
            except Exception:
                pass
            finally:
                sys.path.pop(0)
    # 3) Python 库
    for modname in ('brotli', 'brotlicffi'):
        try:
            mod = __import__(modname)
            # 冒烟验证存在解压 API
            if hasattr(mod, 'decompress'):
                _MOD = mod
                _BACKEND_NAME = 'python:' + modname
                return
        except Exception:
            continue
    _BACKEND_NAME = 'none'


def backend_name():
    """当前生效的后端名称（用于日志输出）。"""
    _probe()
    return _BACKEND_NAME


def is_available():
    _probe()
    return _BACKEND_NAME != 'none'


# ---- 解压 ----------------------------------------------------------
def brotli_decompress(src_path, dst_path, emit=None):
    """把 .br 文件解压到目标文件。
    src_path / dst_path：绝对或相对路径。
    emit(msg)：日志回调（默认 print）。
    失败抛出 BrotliUnavailable / 子进程错误。
    """
    if emit is None:
        emit = print
    _probe()
    if _BACKEND_NAME == 'none':
        raise BrotliUnavailable(
            "未找到可用的 brotli 解码后端：工具已内置 Windows brotli.exe（bin\\win\\x86_64）"
            "与 Python 库（porttool\\_vendor_brotli\\，cp312-314），请确认这些文件未被删除或损坏；"
            "Linux 可另行 apt/dnf install brotli 或 pip install brotli。"
            "（仅 Android 9+ 固件的 new.dat.br 需要，老固件不受影响）")
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)) or '.', exist_ok=True)
    if _BIN:
        if _BACKEND_NAME == 'bundle-cmd':
            emit("【解压】使用工具自带 brotli 命令解压 %s ..." % os.path.basename(src_path))
        else:
            emit(f"【解压】使用系统 brotli 命令解压 {os.path.basename(src_path)} ...")
        r = subprocess.run([_BIN, '-d', '-f', '-o', dst_path, src_path],
                           capture_output=True, timeout=3600)
        if r.returncode != 0:
            raise RuntimeError(
                f"brotli 解压失败（exit {r.returncode}）："
                f"{r.stderr.decode('utf-8', errors='replace').strip()}")
        return
    emit(f"【解压】使用内置/系统 brotli 库（{_BACKEND_NAME}）解压 {os.path.basename(src_path)} ...")
    # #94：流式解压（Decompressor.process 增量），避免 GB 级 .br 整文件读入内存
    decompressor = getattr(_MOD, 'Decompressor', None)
    if decompressor is None:
        # 罕见：库仅一次性 decompress、无流式 API → 回退整文件（保留可用性）
        try:
            with open(src_path, 'rb') as f:
                data = _MOD.decompress(f.read())
            with open(dst_path, 'wb') as f:
                f.write(data)
        except Exception as e:
            raise RuntimeError(f"brotli 库解压失败：{e}")
        return
    try:
        d = decompressor()
        with open(src_path, 'rb') as fin, open(dst_path, 'wb') as fout:
            while True:
                chunk = fin.read(1 << 20)
                if not chunk:
                    break
                fout.write(d.process(chunk))
        # 仅 brotlicffi 的 Decompressor 有 finish()；官方 brotli 库无（增量已输出完）
        finish = getattr(d, 'finish', None)
        if finish:
            tail = finish()
            if tail:
                with open(dst_path, 'ab') as fout:
                    fout.write(tail)
    except Exception as e:
        raise RuntimeError(f"brotli 库解压失败：{e}")
