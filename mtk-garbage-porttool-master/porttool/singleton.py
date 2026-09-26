# -*- coding: utf-8 -*-
"""单实例锁：同一目录只允许运行一个程序实例。

锁文件存放在工具根目录（与 main.py 同级），记录当前实例 PID。
再次启动时若锁文件中的 PID 仍存活，则认为已有实例在运行：
- 提示用户已有实例，可选择跳转至正在运行的窗口，或直接退出；
- 若 PID 已不存在（进程被强杀/崩溃留下的残留锁），自动接管并重新上锁。
"""
import os
import sys
import time
from pathlib import Path

_LOCK_NAME = ".mtk_porttool.lock"


def tool_root():
    """以入口脚本所在目录作为工具根目录（main.py 同级）。"""
    f = Path(sys.argv[0]).resolve()
    if f.name == "__main__.py":
        # `python -m porttool` 时入口是 porttool/__main__.py，取其上级目录
        f = f.parent.parent
    else:
        # 直接运行 main.py / 打包 exe：取脚本所在目录
        f = f.parent
    return f


def _lock_path():
    return tool_root() / _LOCK_NAME


def _pid_alive(pid):
    """检查 PID 对应的进程是否仍存活。"""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        STILL_ACTIVE = 259
        # 显式声明参数/返回类型，避免 64 位句柄被截断导致 CloseHandle 崩溃
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.GetLastError.restype = ctypes.c_ulong
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        h = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            # ERROR_ACCESS_DENIED(5) 说明进程存在但无权限查询
            return kernel32.GetLastError() == 5
        try:
            # 已终止但句柄未完全回收的进程对象：OpenProcess 仍能打开，
            # 用 GetExitCodeProcess 判断是否仍在运行（STILL_ACTIVE=259）。
            # 强杀残留的进程会返回真实退出码，避免被误判为"仍在运行"导致锁死。
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True  # 查询失败时保守认为存活
        finally:
            kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire():
    """尝试获取单实例锁。

    返回 (ok, pid)：ok=True 表示本实例可继续运行（pid=自身 PID）；
    ok=False 表示已有实例在运行（pid=已运行实例的 PID）。
    """
    lp = _lock_path()
    if lp.exists():
        pid = 0
        try:
            pid = int(lp.read_text(encoding="utf-8").strip() or 0)
        except Exception:
            pid = 0
        if pid and _pid_alive(pid):
            return False, pid
        # 残留锁（进程已退出），忽略并接管
    try:
        lp.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    return True, os.getpid()


def release():
    """释放本实例持有的锁（进程退出时调用）。"""
    lp = _lock_path()
    try:
        if lp.exists() and lp.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lp.unlink()
    except Exception:
        pass


def clear_lock():
    """用户手动清除状态锁：上次进程被强制结束后残留的锁导致误报时使用。"""
    lp = _lock_path()
    try:
        if lp.exists():
            lp.unlink()
    except Exception:
        pass


def pid_alive(pid):
    """公开接口：判断指定 PID 的进程是否仍存活。"""
    return _pid_alive(pid)


def _find_window(pid):
    """枚举顶层可见窗口，返回属于 pid 的**面积最大**的窗口句柄（主窗口）；找不到返回 None。

    同一进程可能同时有主窗口和更新提示等小弹窗，取面积最大者更接近用户期望跳转的目标。
    """
    import ctypes
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_int)
    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_int]
    user32.EnumWindows.restype = ctypes.c_bool
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
    user32.GetWindowRect.restype = ctypes.c_int

    best = {"hwnd": None, "area": -1}

    def _cb(hwnd, _lparam):
        proc_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if proc_id.value == pid and user32.IsWindowVisible(hwnd):
            r = ctypes.wintypes.RECT()
            try:
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                area = (r.right - r.left) * (r.bottom - r.top)
            except Exception:
                area = 0
            if area > best["area"]:
                best["hwnd"], best["area"] = hwnd, area
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return best["hwnd"]


def _force_foreground(hwnd):
    """把窗口带到前台。Windows 有前台锁限制，逐级尝试多种方式，全部失败返回 False。"""
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int]
    user32.AttachThreadInput.restype = ctypes.c_int
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int
    user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_ulong]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    user32.InvalidateRect.restype = ctypes.c_bool
    user32.UpdateWindow.argtypes = [ctypes.c_void_p]
    user32.UpdateWindow.restype = ctypes.c_bool
    user32.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    user32.RedrawWindow.restype = ctypes.c_int
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    user32.PostMessageW.restype = ctypes.c_bool
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
    user32.GetWindowRect.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_ulong]

    SW_RESTORE = 9
    SW_SHOW = 5
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0001
    SWP_NOSIZE = 0x0002

    # 1) 恢复窗口显示：最小化→还原；被隐藏（托盘）→重新显示
    user32.ShowWindow(hwnd, SW_RESTORE)
    if not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, SW_SHOW)
    # 等待窗口恢复动画处理完成，避免重绘消息被动画吞掉
    try:
        time.sleep(0.15)
    except Exception:
        pass
    # 强制整窗重绘：恢复/隐藏唤醒后 tkinter 可能不重绘（白屏），组合手段确保立即刷新
    try:
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0100 | 0x0200)
        # RDW_INVALIDATE | RDW_ERASE | RDW_UPDATENOW | RDW_ALLCHILDREN
    except Exception:
        pass
    try:
        # 异步投递 WM_PAINT 与 WM_MOUSEMOVE（等效"鼠标放上去"），交给 Tk 自己刷新
        user32.PostMessageW(hwnd, 0x000F, 0, 0)  # WM_PAINT
        user32.PostMessageW(hwnd, 0x0200, 0, 0)  # WM_MOUSEMOVE
    except Exception:
        pass
    try:
        # 模拟窗口微移 1px 再移回：等效于用户"移动窗口"，触发 Tk 完整重绘
        r = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w = r.right - r.left
        h = r.bottom - r.top
        user32.SetWindowPos(hwnd, 0, r.left + 1, r.top, w, h, 0x0004)  # SWP_NOZORDER
        user32.SetWindowPos(hwnd, 0, r.left, r.top, w, h, 0x0004)
    except Exception:
        pass

    # 2) 模拟一次 Alt 按键，解除系统前台锁（允许"用户操作"获得前台）
    try:
        user32.keybd_event(0x12, 0, 0, 0)   # ALT 按下
        user32.keybd_event(0x12, 0, 2, 0)   # ALT 释放
    except Exception:
        pass

    # 3) AttachThreadInput：把自己挂到当前前台窗口的线程上再抢前台
    attached = False
    try:
        cur_tid = kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        fg_tid = 0
        if fg:
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(p))
            fg_tid = p.value
        if fg_tid and fg_tid != cur_tid:
            attached = user32.AttachThreadInput(cur_tid, fg_tid, True) != 0
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    finally:
        if attached:
            try:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                pass

    # 4) 验证是否已在前台；没有则用置顶兜底（强制可见并压到前台）
    try:
        if user32.GetForegroundWindow() != hwnd:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    except Exception:
        pass
    return True


def focus_window(pid):
    """把指定 PID 进程的主窗口带到前台（Windows）。找不到窗口或激活失败时返回 False。

    全程 try/except 兜底：任何一步失败都快速返回，绝不阻塞调用方（tkinter 主线程）。
    """
    if os.name != "nt":
        return False
    try:
        hwnd = _find_window(pid)
        if not hwnd:
            return False
        return _force_foreground(hwnd)
    except Exception:
        return False
