#!/usr/bin/env python3
from tkinter import Tk
from .ui import (
    MyUI
)
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


def main():
    # 高 DPI 必须在 Tk() 之前设置
    scaling = _setup_high_dpi()

    root = Tk()
    root.title("MTK Port Tool")
    #root.geometry("860x480")

    if scaling != 1.0:
        root.tk.call('tk', 'scaling', scaling)

    myapp = MyUI(root)
    myapp.pack(side='top', fill='both', padx=5, pady=5, expand='yes')

    root.update()
    root.mainloop()
