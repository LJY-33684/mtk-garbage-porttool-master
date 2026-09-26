#!/usr/bin/env python3
from tkinter import Tk
from .ui import (
    MyUI
)
from . import singleton
from os import name
if name == 'nt':
    import ctypes
    from multiprocessing.dummy import freeze_support
    freeze_support()


def _setup_high_dpi():
    """在创建任何窗口之前设置进程 DPI 感知，否则高分辨率屏下窗口/字体极小。

    必须在 Tk() 之前调用；在窗口创建后设置不生效。
    """
    if name != 'nt':
        return 1.0
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2（优先，支持多显示器不同缩放）
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # 回退：PROCESS_SYSTEM_DPI_AWARE = 1
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                # 再回退：旧式 SetProcessDPIAware（Win7/8）
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    try:
        scalefactor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
        return scalefactor / 75.0
    except Exception:
        return 1.0


def _show_already_running(pid):
    """同目录已有实例在运行：弹出提示窗口。

    可选：跳转至已运行窗口 / 清除残留状态锁后继续 / 直接退出。
    返回 True=用户已清除状态锁且本进程已重新上锁，可继续启动；False=关闭退出。
    """
    import tkinter as tk
    from tkinter import ttk

    root = Tk()
    root.title("MTK 移植工具")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    msg = ("检测到本目录已有一个正在运行的实例。\n"
           "同一目录仅允许运行一个实例，以免文件读写冲突。\n"
           "如需同时运行多个实例，请将本工具所在目录复制到其他位置后再打开运行。\n\n"
           "提示：若你确认当前并没有其他实例在运行、但仍弹出此窗口，\n"
           "说明上次进程被强制结束后残留了状态锁，请点击「清除状态锁」按钮后重试。")
    ttk.Label(root, text=msg, justify='left', wraplength=420).pack(padx=20, pady=(16, 6))

    result = {"clear": False}
    tip = ttk.Label(root, text="", foreground="#cc0000")
    btns = ttk.Frame(root)

    def _jump():
        try:
            singleton.focus_window(pid)
        finally:
            # 无论跳转成功与否，都关闭提示窗并退出本实例，避免窗口残留
            root.destroy()

    def _clear():
        # 若检测到仍有实例在运行：二次弹窗让用户确认是否强制清除
        if singleton.pid_alive(pid):
            import tkinter.messagebox as messagebox
            ans = messagebox.askyesno(
                "确认清除状态锁",
                "检测到仍有一个实例可能在运行（PID：%s）。\n\n"
                "强制清除状态锁后，该实例将失去本工具的单实例保护，\n"
                "若两实例同时操作可能造成文件冲突。\n\n"
                "确认强制清除并继续启动吗？\n"
                "（若该实例仍在使用，建议先关闭它，或点击「跳转至正在运行的程序」切换过去）" % pid,
                parent=root)
            if not ans:
                return
        # 实例已确认退出 / 用户确认强制清除：删除状态锁并重新上锁
        singleton.clear_lock()
        ok, _ = singleton.acquire()
        if ok:
            result["clear"] = True
            root.destroy()
        else:
            tip.config(text="清除后仍检测到其他实例在运行，请先确认是否已有程序打开。")
            tip.pack(pady=(0, 4))

    ttk.Button(btns, text="跳转至正在运行的程序", command=_jump).pack(side='left', padx=6)
    ttk.Button(btns, text="清除状态锁", command=_clear).pack(side='left', padx=6)
    ttk.Button(btns, text="好的", command=root.destroy).pack(side='left', padx=6)
    btns.pack(pady=(6, 14))

    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{x}+{y}")
    root.mainloop()
    return result["clear"]


def main():
    # 高 DPI 必须在 Tk() 之前设置
    scaling = _setup_high_dpi()

    # 单实例检查：同目录只允许一个实例
    ok, pid = singleton.acquire()
    if not ok:
        # 用户清除状态锁成功时（_show_already_running 返回 True）已在本进程重新上锁，继续启动
        if not _show_already_running(pid):
            return
    import atexit
    atexit.register(singleton.release)

    root = Tk()
    root.title("MTK Port Tool")
    #root.geometry("860x480")

    if scaling != 1.0:
        root.tk.call('tk', 'scaling', scaling)

    myapp = MyUI(root)
    myapp.pack(side='top', fill='both', padx=5, pady=5, expand='yes')

    root.update()
    root.mainloop()
