try:
    from .ui import MyUI
except ImportError:
    # CLI（porttool_cli.py / fscheck.py）在无 tkinter 的机器上不应因 GUI 模块导入失败而崩溃；
    # GUI 入口 __main__.py 的 main() 内会重新导入 MyUI，此处缺失不影响 GUI。
    MyUI = None
from .configs import *
from .utils import *