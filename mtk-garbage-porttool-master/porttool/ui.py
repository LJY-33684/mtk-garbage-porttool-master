# 导入必要的库和模块
import urllib.request
import json
import re
import webbrowser
import threading
from tkinter import (
    ttk,
    Toplevel,
    scrolledtext,
    StringVar,
    BooleanVar,
    Canvas,
    Text,
    END,
    WORD,
)
from tkinter.filedialog import askopenfilename
from os import getcwd
from pathlib import Path
from multiprocessing.dummy import DummyProcess

# 导入自定义模块（需确保这些模块存在于同级目录）
from .configs import support_chipset, support_chipset_portstep
from .utils import portutils, tool_version

class FileChooser(Toplevel):
    """文件选择弹窗类：用于选择底包、移植源文件"""
    def __init__(self, parent, pack_type):
        super().__init__(parent)
        self.title("请选择底包的boot, system和要移植的源")
        self.pack_type = pack_type  # 接收输出类型（zip/img）
        
        # 移植源类型（仅img输出时可切换，zip输出时强制为zip）
        self.source_type = StringVar(value='zip')
        # 底包相关变量
        self.baseboot = StringVar()
        self.basesys = StringVar()
        # 移植源相关变量
        self.portzip = StringVar()    # zip卡刷包路径
        self.portboot = StringVar()   # 单镜像boot.img路径
        self.portsys = StringVar()    # 单镜像system.img路径
        
        # 自动填充已存在的底包路径（如果base目录有对应的img）
        basesys_path = Path("base/system.img")
        baseboot_path = Path("base/boot.img")
        if basesys_path.exists():
            self.basesys.set(basesys_path.absolute())
        if baseboot_path.exists():
            self.baseboot.set(baseboot_path.absolute())
        
        self.frame = []  # 存储所有文件选择的frame组件
        self.__setup_widgets()
        self.focus()  # 聚焦当前弹窗
    
    def __setup_widgets(self):
        """初始化弹窗内的所有UI组件"""
        def __match(val) -> str:
            """根据索引返回对应的标签文本"""
            match val:
                case 0: return "底包boot镜像"
                case 1: return "底包system镜像"
                case 2: return "移植包(zip)"
                case 3: return "移植用boot.img"
                case 4: return "移植用system.img"
                case _: return ""
        
        def __choose_file(val: StringVar):
            """文件选择按钮回调：选择文件并更新对应变量"""
            val.set(askopenfilename(initialdir=getcwd()))
            self.focus()
        
        def __toggle_source_type():
            """切换移植源类型时的UI显示逻辑（仅img输出时生效）"""
            if self.pack_type != 'img':
                return
            
            zip_frame = self.frame[2][0]        # zip移植包选择框
            img_boot_frame = self.frame[3][0]   # 单镜像boot选择框
            img_sys_frame = self.frame[4][0]    # 单镜像system选择框
            
            if self.source_type.get() == 'zip':
                zip_frame.pack(side='top', fill='x', padx=5, pady=5)
                img_boot_frame.pack_forget()
                img_sys_frame.pack_forget()
            else:
                zip_frame.pack_forget()
                img_boot_frame.pack(side='top', fill='x', padx=5, pady=5)
                img_sys_frame.pack(side='top', fill='x', padx=5, pady=5)
        
        # 初始化所有文件选择的frame（底包boot、底包system、zip源、img boot、img system）
        for index, current_var in enumerate([
            self.baseboot, self.basesys, self.portzip, self.portboot, self.portsys
        ]):
            frame = ttk.Frame(self)
            label = ttk.Label(frame, text=__match(index), width=16)
            entry = ttk.Entry(frame, textvariable=current_var, width=40)
            button = ttk.Button(frame, text="选择文件", command=lambda x=current_var: __choose_file(x))
            self.frame.append([frame, label, entry, button])
        
        # 布局底包相关frame（固定显示）
        for i in self.frame[:2]:
            for idx, widget in enumerate(i):
                if idx == 0:  # frame组件
                    widget.pack(side='top', fill='x', padx=5, pady=5)
                elif idx == 2:  # entry输入框
                    widget.pack(side='left', fill='x', padx=5, pady=5)
                else:  # label/button
                    widget.pack(side='left', padx=5, pady=5)
        
        # 根据输出类型控制移植源类型选择框的显示
        if self.pack_type == 'img':
            # img输出：显示移植源类型选择框
            sourcetype_frame = ttk.Frame(self)
            ttk.Label(sourcetype_frame, text="移植源类型：", width=16).pack(side='left', padx=5, pady=5)
            ttk.Radiobutton(
                sourcetype_frame, 
                text="zip卡刷包", 
                variable=self.source_type, 
                value='zip', 
                command=__toggle_source_type
            ).pack(side='left', padx=5)
            ttk.Radiobutton(
                sourcetype_frame, 
                text="单独img镜像", 
                variable=self.source_type, 
                value='img', 
                command=__toggle_source_type
            ).pack(side='left', padx=5)
            sourcetype_frame.pack(side='top', fill='x', padx=5, pady=5)
        else:
            # zip输出：隐藏移植源类型选择，显示提示文本
            tip_frame = ttk.Frame(self)
            ttk.Label(
                tip_frame, 
                text="提示：输出zip时仅支持zip格式的移植源", 
                foreground="blue"
            ).pack(side='left', padx=5, pady=5)
            tip_frame.pack(side='top', fill='x', padx=5, pady=5)
        
        # 布局移植源相关frame
        for i in self.frame[2:]:
            for idx, widget in enumerate(i):
                if idx == 0:  # frame组件
                    if self.pack_type == 'zip':
                        # zip输出：仅显示zip移植包选择框
                        if i == self.frame[2]:
                            widget.pack(side='top', fill='x', padx=5, pady=5)
                        else:
                            widget.pack_forget()
                    else:
                        # img输出：默认显示zip选择框，img选择框初始隐藏
                        if i == self.frame[2]:
                            widget.pack(side='top', fill='x', padx=5, pady=5)
                        else:
                            widget.pack_forget()
                elif idx == 2:  # entry输入框
                    widget.pack(side='left', fill='x', padx=5, pady=5)
                else:  # label/button
                    widget.pack(side='left', padx=5, pady=5)
        
        # 底部确定按钮
        bottomframe = ttk.Frame(self)
        bottombutton = ttk.Button(bottomframe, text='确定', command=self.destroy)
        bottombutton.pack(side='right', padx=5, pady=5)
        bottomframe.pack(side='bottom', fill='x', padx=5, pady=5)
    
    def get(self) -> tuple:
        """获取选择的文件路径和源类型
        返回格式：(baseboot, basesys, port_source, source_type)
        """
        self.wait_window(self)
        # zip输出时强制source_type为zip
        if self.pack_type == 'zip':
            return [self.baseboot.get(), self.basesys.get(), self.portzip.get(), 'zip']
        else:
            if self.source_type.get() == 'zip':
                return [self.baseboot.get(), self.basesys.get(), self.portzip.get(), 'zip']
            else:
                return [self.baseboot.get(), self.basesys.get(), (self.portboot.get(), self.portsys.get()), 'img']

class LogLabel(scrolledtext.ScrolledText):
    """带滚动条的日志显示组件"""
    def __init__(self, parent):
        super().__init__(parent)
    
    def write(self, *vars, end='\n'):
        """自定义写入日志方法"""
        for i in vars:
            self.insert('end', i)
        self.insert('end', end)
        self.see('end')  # 自动滚动到末尾
    
    def flush(self): 
        """兼容stdout的flush方法"""
        pass
    
    def print(self, *vars, end='\n'):
        """自定义print方法"""
        print(vars, end=end, file=self)

class MyUI(ttk.Labelframe):
    """主UI框架类"""
    def __init__(self, parent):
        super().__init__(parent, text="MTK 低端机移植工具")
        self.update_source = StringVar(value='GitHub')  # 更新源：GitHub / Gitee
        # 用 labelwidget 实现标题+检查更新按钮（必须在 super 之后创建，parent=self）
        self._header_frame = ttk.Frame(self)
        self._title_label = ttk.Label(self._header_frame, text="MTK 低端机移植工具", font=('Microsoft YaHei', 9, 'bold'))
        self._title_label.pack(side='left', padx=(0, 8))
        self._check_update_btn = ttk.Button(self._header_frame, text="检查更新", width=10, command=self._on_check_update)
        self._check_update_btn.pack(side='left')
        # 更新源选择框（参照芯片类型样式）
        ttk.Label(self._header_frame, text="更新源").pack(side='left', padx=(10, 2))
        self._update_source_menu = ttk.OptionMenu(
            self._header_frame,
            self.update_source,
            'GitHub',
            'GitHub', 'Gitee'
        )
        self._update_source_menu.pack(side='left')
        self.configure(labelwidget=self._header_frame)
        # 核心配置变量
        self.chipset_select = StringVar(value='mt65')  # 芯片类型
        self.pack_type = StringVar(value='zip')        # 输出类型（默认zip）
        self.patch_magisk = BooleanVar(value=False)    # 是否修补magisk
        self.target_arch = StringVar(value='arm64')    # magisk架构
        self.magisk_apk = StringVar(value="magisk.apk")# magisk apk路径

        # ========== 新增：防止重复点击的核心变量 ==========
        self.is_running = False  # 标记是否正在执行移植流程
        self.port_button = None  # 保存一键移植按钮对象
        
        self.item = []      # 移植条目列表
        self.itembox = []   # 移植条目复选框列表
        self.__setup_widgets()  # 初始化UI
    
    def __start_port(self):
        """一键移植按钮回调：执行移植逻辑（修复重复点击问题）"""
        # 1. 检查是否正在运行，防止重复点击
        if self.is_running:
            print("【提示】移植流程正在执行中，请勿重复点击！", file=self.log)
            return
        
        # 2. 检查移植条目是否为空
        if len(self.item) == 0:
            print("Error: 移植条目为0，请先加载移植条目！", file=self.log)
            return
        
        # 3. 标记为运行中，并禁用按钮（核心：防止重复点击）
        self.is_running = True
        self.port_button.config(state='disabled')
        print("【提示】开始执行移植流程，按钮已禁用（流程结束后自动恢复）...", file=self.log)
        
        try:
            # 获取选择的文件路径（传递输出类型给FileChooser）
            files = FileChooser(self, self.pack_type.get()).get()
            baseboot, basesys, port_source, source_type = files
            
            # 校验：zip输出时必须用zip源
            if self.pack_type.get() == 'zip' and source_type != 'zip':
                print("错误：输出zip卡刷包时仅支持zip格式的移植源！", file=self.log)
                # 重置状态+启用按钮
                self.is_running = False
                self.port_button.config(state='normal')
                return
            
            # 检查底包文件是否存在
            for file_path in [baseboot, basesys]:
                if not Path(file_path).exists() or file_path == '':
                    print(f"文件{file_path}未选择或不存在", file=self.log)
                    # 重置状态+启用按钮
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
            
            # 检查移植源文件是否存在
            if source_type == 'zip':
                if not Path(port_source).exists() or port_source == '':
                    print(f"移植包{port_source}未选择或不存在", file=self.log)
                    # 重置状态+启用按钮
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
            else:
                portboot, portsys = port_source
                if not (Path(portboot).exists() and Path(portsys).exists()) or portboot == '' or portsys == '':
                    print("移植用boot.img或system.img未选择或不存在", file=self.log)
                    # 重置状态+启用按钮
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
            
            # 日志输出选择的文件路径
            print(f"底包boot路径：{baseboot}\n底包system路径：{basesys}", file=self.log)
            if source_type == 'zip':
                print(f"移植包路径：{port_source}", file=self.log)
            else:
                print(f"移植用boot.img路径：{port_source[0]}\n移植用system.img路径：{port_source[1]}", file=self.log)
            
            # 配置移植参数
            newdict = support_chipset_portstep[self.chipset_select.get()]
            for key, tkbool in self.item:
                newdict[key] = tkbool.get()
            
            # Magisk相关配置
            newdict['patch_magisk'] = self.patch_magisk.get()
            newdict['magisk_apk'] = self.magisk_apk.get()
            newdict['target_arch'] = self.target_arch.get()
            
            # 确定输出类型（zip→genimg=False，img→genimg=True）
            genimg = True if self.pack_type.get() == 'img' else False
            
            # 定义移植进程的执行函数（封装逻辑，确保流程结束后重置状态）
            def run_port_process():
                try:
                    # 启动移植逻辑
                    port_process = portutils(
                        newdict, baseboot, basesys, port_source, source_type, genimg, self.log
                    ).start
                    port_process()  # 执行移植
                except Exception as e:
                    print(f"【移植异常】执行过程出错：{str(e)}", file=self.log)
                finally:
                    # 无论成功/失败，都重置状态+启用按钮
                    self.is_running = False
                    self.port_button.config(state='normal')
                    print("【提示】移植流程结束，按钮已恢复可用！", file=self.log)
            
            # 启动移植进程（避免UI阻塞）
            DummyProcess(target=run_port_process).start()
            
        except Exception as e:
            # 捕获所有异常，确保状态重置
            print(f"【执行异常】{str(e)}", file=self.log)
            self.is_running = False
            self.port_button.config(state='normal')
    
    def __setup_widgets(self):
        """初始化主UI的所有组件"""
        def __scroll_event(event):
            """移植条目滚动事件处理"""
            scroll_num = int(-event.delta / 2)
            actcanvas.yview_scroll(scroll_num, 'units')
        
        def __scroll_func(event):
            """更新滚动区域"""
            actcanvas.configure(scrollregion=actcanvas.bbox("all"), width=300, height=180)
        
        def __create_cv_frame():
            """创建移植条目滚动画布内的frame"""
            self.actcvframe = ttk.Frame(actcanvas)
            actcanvas.create_window(0, 0, window=self.actcvframe, anchor='nw')
            self.actcvframe.bind("<Configure>", __scroll_func)
            actcanvas.update()
        
        def __load_port_item(select):
            """加载选中芯片类型对应的移植条目"""
            print(f"选中移植方案为{select}...", file=self.log)
            item_dict = support_chipset_portstep[select]['flags']
            self.item = []
            self.itembox = []
            
            # 销毁原有移植条目frame
            if hasattr(self, 'actcvframe'):
                self.actcvframe.destroy()
            __create_cv_frame()
            
            # 创建移植条目复选框
            for index, item_key in enumerate(item_dict):
                self.item.append([item_key, BooleanVar(value=item_dict[item_key])])
                self.itembox.append(
                    ttk.Checkbutton(
                        self.actcvframe, 
                        text=item_key, 
                        variable=self.item[index][1]
                    )
                )
            
            # 布局移植条目复选框
            for checkbox in self.itembox:
                checkbox.pack(side='top', fill='x', padx=5)
        
        # ========== 左侧配置区域 ==========
        optframe = ttk.Frame(self)
        
        # 芯片类型选择
        optlabel = ttk.Label(optframe)
        ttk.Label(optlabel, text="芯片类型", anchor='e').pack(side='left', padx=5, pady=5)
        ttk.OptionMenu(
            optlabel, 
            self.chipset_select, 
            support_chipset[0], 
            *support_chipset, 
            command=__load_port_item
        ).pack(side='left', fill='x', padx=5, pady=5)
        optlabel.pack(side='top', fill='x')
        
        # 移植条目滚动区域
        actframe = ttk.Labelframe(optframe, text="支持的移植条目", height=180)
        actcanvas = Canvas(actframe)
        actscroll = ttk.Scrollbar(actframe, orient='vertical', command=actcanvas.yview)
        actcanvas.configure(
            yscrollcommand=actscroll.set, 
            scrollregion=(0, 0, 300, 180), 
            yscrollincrement=1
        )
        actcanvas.bind("<MouseWheel>", __scroll_event)  # 绑定鼠标滚轮
        actscroll.pack(side='right', fill='y')
        actcanvas.pack(side='right', fill='x', expand='yes', anchor='e')
        actframe.pack(side='top', fill='x', expand='yes')
        __create_cv_frame()
        
        # 操作按钮区域
        buttonlabel = ttk.Label(optframe)
        # 一键移植按钮（保存到self.port_button，用于禁用/启用）
        self.port_button = ttk.Button(
            optframe, 
            text="一键移植", 
            command=self.__start_port
        )
        self.port_button.pack(side='top', fill='both', padx=5, pady=5, expand='yes')
        
        # 输出类型选择
        ttk.Label(buttonlabel, text="输出类型：").grid(column=0, row=0, padx=5, pady=5, columnspan=2)
        buttoncheck1 = ttk.Checkbutton(
            buttonlabel, 
            text="zip卡刷包", 
            variable=self.pack_type, 
            onvalue='zip', 
            offvalue='img'
        )
        buttoncheck2 = ttk.Checkbutton(
            buttonlabel, 
            text="img镜像", 
            variable=self.pack_type, 
            onvalue='img', 
            offvalue='zip'
        )
        buttoncheck1.grid(column=0, row=1, padx=5, pady=5)
        buttoncheck2.grid(column=1, row=1, padx=5, pady=5)
        
        # Magisk修补配置
        magiskarch = ttk.OptionMenu(
            buttonlabel, 
            self.target_arch, 
            "arm64", 
            *["arm64", "arm", "x86", "x86_64"]
        )
        magiskapkentry = ttk.Entry(buttonlabel, textvariable=self.magisk_apk)
        magiskapkentry.bind("<Double-Button-1>", lambda x:self.magisk_apk.set(askopenfilename()))
        
        # Magisk修补复选框（控制架构/APK输入框显示）
        buttonmagisk = ttk.Checkbutton(
            buttonlabel, 
            text="修补magisk", 
            variable=self.patch_magisk, 
            onvalue=True, 
            offvalue=False, 
            command=lambda: (
                magiskapkentry.grid_forget(),
                magiskarch.grid_forget(),
            ) if not self.patch_magisk.get() else (
                magiskarch.grid(column=0, row=3, padx=5, pady=5, sticky='nsew', columnspan=2),
                magiskapkentry.grid(column=0, row=4, padx=5, pady=5, sticky='nsew', columnspan=2)
            )
        )
        buttonmagisk.grid(column=0, row=2, padx=5, pady=5, sticky='w', columnspan=2)
        buttonlabel.pack(side='top', padx=5, pady=5, fill='x', expand='yes')
        
        optframe.pack(side='left', padx=5, pady=5, fill='y', expand='no')
        
        # ========== 右侧日志区域 ==========
        logframe = ttk.Labelframe(self, text="日志输出")
        self.log = LogLabel(logframe)
        self.log.pack(side='left', fill='both', anchor='center')
        logframe.pack(side='left', padx=5, pady=5, fill='both', expand='yes')
        
        # 初始加载移植条目
        __load_port_item(self.chipset_select.get())


    # ========== 检查更新功能 ==========
    UPDATE_SOURCES = {
        'GitHub': {
            'raw': 'https://raw.githubusercontent.com/LJY-33684/mtk-garbage-porttool-master/main/latest_version.txt',
            'api': 'https://api.github.com/repos/LJY-33684/mtk-garbage-porttool-master/releases/tags/{tag}',
            'url_key': 'update_url_1',
        },
        'Gitee': {
            'raw': 'https://gitee.com/Q3368436451/mtk-garbage-porttool-master/raw/main/latest_version.txt',
            'api': 'https://gitee.com/api/v5/repos/Q3368436451/mtk-garbage-porttool-master/releases/tags/{tag}',
            'url_key': 'update_url_2',
        },
    }
    UPDATE_TIMEOUT = 30  # 秒

    def _on_check_update(self):
        """检查更新按钮点击回调"""
        self._check_update_btn.config(text="检查更新中...", state="disabled")
        # 后台线程请求，避免阻塞 UI
        t = threading.Thread(target=self._fetch_update_worker, daemon=True)
        t.start()

    def _fetch_update_worker(self):
        """后台线程：请求 latest_version.txt + 对应源 release 信息"""
        source = self.update_source.get()
        src_cfg = self.UPDATE_SOURCES.get(source, self.UPDATE_SOURCES['GitHub'])
        try:
            # 1. 请求对应源的 latest_version.txt
            req = urllib.request.Request(src_cfg['raw'], headers={"User-Agent": "MTK-PortTool"})
            with urllib.request.urlopen(req, timeout=self.UPDATE_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8-sig")

            # 2. 解析 latest_version.txt（支持有引号/无引号、update_url/update_url_1/update_url_2）
            tag = None
            all_urls = {}
            for line in raw.splitlines():
                line = line.strip()
                m = re.match(r'latest_version\s*=\s*(.+?)\s*$', line)
                if m:
                    tag = m.group(1).strip().strip('"').strip("'")
                m = re.match(r'(update_url(?:_\d+)?)\s*=\s*(.+?)\s*$', line)
                if m:
                    all_urls[m.group(1)] = m.group(2).strip().strip('"').strip("'")

            if not tag:
                self.after(0, lambda: self._on_update_failed("版本信息格式错误"))
                return

            # 版本相同则提示已是最新
            if tag == tool_version:
                self.after(0, lambda: self._on_already_latest(tag))
                return

            # 选择对应源的下载链接
            download_url = all_urls.get(src_cfg['url_key']) or all_urls.get('update_url')

            # 3. 请求对应源 API 获取 release 内容（markdown）
            body = ""
            try:
                api_url = src_cfg['api'].format(tag=tag)
                req2 = urllib.request.Request(api_url, headers={"User-Agent": "MTK-PortTool", "Accept": "application/json"})
                with urllib.request.urlopen(req2, timeout=self.UPDATE_TIMEOUT) as resp2:
                    release_data = json.loads(resp2.read().decode("utf-8"))
                    body = release_data.get("body", "") or ""
                    if not download_url:
                        download_url = release_data.get("html_url", "")
            except Exception:
                body = f"## {tag}\n\n更新内容获取失败，请前往下载页面查看详情。"

            self.after(0, lambda: self._on_update_success(tag, body, download_url))

        except urllib.error.URLError as e:
            reason = "网络超时" if "timed out" in str(e).lower() else f"网络错误: {e}"
            self.after(0, lambda: self._on_update_failed(reason))
        except Exception as e:
            self.after(0, lambda: self._on_update_failed(f"未知错误: {e}"))

    def _on_update_success(self, tag, body, download_url):
        """检查更新成功（主线程）"""
        self._check_update_btn.config(text="检查更新", state="normal")
        self._show_update_dialog(tag, body, download_url)

    def _on_update_failed(self, reason):
        """检查更新失败（主线程）"""
        self._check_update_btn.config(text="检查更新失败", state="normal")
        # 3秒后恢复按钮文字
        self.after(3000, lambda: self._check_update_btn.config(text="检查更新"))

    def _on_already_latest(self, tag):
        """已是最新版本（主线程）"""
        self._check_update_btn.config(text="检查更新", state="normal")
        win = Toplevel(self)
        win.title("检查更新")
        win.geometry("320x140")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        ttk.Label(win, text="当前已是最新版本", font=('Microsoft YaHei', 12, 'bold')).pack(pady=(25, 5))
        ttk.Label(win, text=f"版本号：{tag}", font=('Microsoft YaHei', 10)).pack(pady=5)
        ttk.Button(win, text="确定", command=win.destroy, width=10).pack(pady=15)

    def _show_update_dialog(self, tag, body, download_url):
        """显示更新内容弹窗（markdown 格式 + 标题右侧前往下载按钮）"""
        win = Toplevel(self)
        win.title(f"发现新版本 - {tag}")
        win.geometry("640x480")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        # 标题栏：左侧标题 + 右侧前往下载按钮
        header_frame = ttk.Frame(win)
        header_frame.pack(fill='x', padx=12, pady=(10, 5))
        ttk.Label(header_frame, text=f"发现新版本：{tag}", font=('Microsoft YaHei', 12, 'bold')).pack(side='left')

        def open_download():
            if download_url:
                webbrowser.open(download_url)

        ttk.Button(header_frame, text="前往下载", command=open_download).pack(side='right')

        # markdown 内容区
        content_frame = ttk.Frame(win)
        content_frame.pack(fill='both', expand=True, padx=12, pady=5)

        text_widget = Text(content_frame, wrap=WORD, font=('Microsoft YaHei', 10), padx=8, pady=8)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        text_widget.pack(side='left', fill='both', expand=True)

        self._render_markdown(text_widget, body)
        text_widget.config(state='disabled')  # 只读

    def _render_markdown(self, text_widget, markdown_text):
        """简单 markdown 渲染：标题、粗体、列表、代码块、链接"""
        # 配置 tag 样式
        text_widget.tag_configure('h1', font=('Microsoft YaHei', 16, 'bold'), spacing1=8, spacing3=4)
        text_widget.tag_configure('h2', font=('Microsoft YaHei', 14, 'bold'), spacing1=6, spacing3=3)
        text_widget.tag_configure('h3', font=('Microsoft YaHei', 12, 'bold'), spacing1=4, spacing3=2)
        text_widget.tag_configure('bold', font=('Microsoft YaHei', 10, 'bold'))
        text_widget.tag_configure('code', font=('Consolas', 9), background='#f0f0f0')
        text_widget.tag_configure('link', foreground='#0066cc', underline=True)
        text_widget.tag_configure('list', lmargin1=20, lmargin2=20)

        in_code_block = False
        for line in markdown_text.splitlines():
            stripped = line.strip()

            # 代码块
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                text_widget.insert(END, line + '\n', 'code')
                continue

            # 标题
            if stripped.startswith('### '):
                text_widget.insert(END, stripped[4:] + '\n', 'h3')
                continue
            if stripped.startswith('## '):
                text_widget.insert(END, stripped[3:] + '\n', 'h2')
                continue
            if stripped.startswith('# '):
                text_widget.insert(END, stripped[2:] + '\n', 'h1')
                continue

            # 列表项
            if re.match(r'^[-*]\s+', stripped):
                content = re.sub(r'^[-*]\s+', '', stripped)
                text_widget.insert(END, '• ', 'list')
                self._insert_inline(text_widget, content)
                text_widget.insert(END, '\n')
                continue
            if re.match(r'^\d+\.\s+', stripped):
                content = re.sub(r'^\d+\.\s+', '', stripped)
                text_widget.insert(END, stripped.split('.')[0] + '. ', 'list')
                self._insert_inline(text_widget, content)
                text_widget.insert(END, '\n')
                continue

            # 普通行（处理内联格式）
            if stripped:
                self._insert_inline(text_widget, stripped)
            text_widget.insert(END, '\n')

    def _insert_inline(self, text_widget, text):
        """处理行内 markdown：**粗体**、`代码`、[链接](url)"""
        # 用正则分割：**bold**、`code`、[link](url)
        pattern = r'(\*\*.+?\*\*|`.+?`|\[.+?\]\(.+?\))'
        parts = re.split(pattern, text)
        for part in parts:
            if not part:
                continue
            if part.startswith('**') and part.endswith('**'):
                text_widget.insert(END, part[2:-2], 'bold')
            elif part.startswith('`') and part.endswith('`'):
                text_widget.insert(END, part[1:-1], 'code')
            elif part.startswith('[') and '](' in part:
                m = re.match(r'\[(.+?)\]\((.+?)\)', part)
                if m:
                    label, url = m.group(1), m.group(2)
                    text_widget.insert(END, label, 'link')
                    # 点击链接打开浏览器
                    tag_name = f"link_{id(url)}"
                    text_widget.tag_bind('link', '<Button-1>', lambda e, u=url: webbrowser.open(u))
                else:
                    text_widget.insert(END, part)
            else:
                text_widget.insert(END, part)
