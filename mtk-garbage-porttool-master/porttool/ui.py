# 导入必要的库和模块
import webbrowser
import threading
import os
from tkinter import (
    ttk,
    Toplevel,
    scrolledtext,
    StringVar,
    BooleanVar,
    Canvas,
    Text,
    PhotoImage,
    END,
    WORD,
)
from tkinter.filedialog import askopenfilename, askdirectory
from tkinter import messagebox
from os import getcwd
from pathlib import Path
from multiprocessing.dummy import DummyProcess

# 导入自定义模块（需确保这些模块存在于同级目录）
from .configs import support_chipset, support_chipset_portstep
from .utils import portutils, tool_version
from .update import fetch_update_info, render_markdown

class FileChooser(Toplevel):
    """文件选择弹窗类：用于选择底包、移植源文件"""
    def __init__(self, parent, pack_type, chipset=None):
        super().__init__(parent)
        self.title("请选择底包的boot, system和要移植的源")
        self.pack_type = pack_type  # 接收输出类型（zip/img）
        # 当前移植方案是否 recovery-only：仅需选择底包Recovery + 移植Recovery 两个镜像
        self.is_recovery = bool(
            support_chipset_portstep.get(chipset, {}).get('flags', {}).get('recovery_only_mode', False)
        ) if chipset else False
        if self.is_recovery:
            self.title("请选择底包Recovery镜像和移植Recovery镜像")
        # 当前移植方案是否 kernel-only：只需底包boot + 移植源boot（无 system 参与）
        self.is_kernel_only = bool(
            support_chipset_portstep.get(chipset, {}).get('flags', {}).get('kernel_only_mode', False)
        ) if chipset else False
        if self.is_kernel_only:
            self.title("请选择底包boot镜像和移植源boot镜像")
        # 移植源类型（仅img输出时可切换，zip输出时强制为zip）
        self.source_type = StringVar(value='zip')
        # 底包相关变量
        self.baseboot = StringVar()
        self.basesys = StringVar()
        # 移植源相关变量
        self.portzip = StringVar()    # zip卡刷包路径
        self.portboot = StringVar()   # 单镜像boot.img路径
        self.portsys = StringVar()    # 单镜像system.img路径
        
        # 自动填充已存在的底包路径（如果base目录有对应的img）；LK去警告模式无需预填
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
            
            if self.is_kernel_only:
                # kernel-only：移植源仅需 boot（zip 或 img-boot），不显示移植用system
                if self.source_type.get() == 'zip':
                    zip_frame.pack(side='top', fill='x', padx=5, pady=5)
                    img_boot_frame.pack_forget()
                    img_sys_frame.pack_forget()
                else:
                    zip_frame.pack_forget()
                    img_boot_frame.pack(side='top', fill='x', padx=5, pady=5)
                    img_sys_frame.pack_forget()
                return
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
        
        # ========== Recovery 模式布局：只显示 底包Recovery + 移植Recovery ==========
        if self.is_recovery:
            # 标签改为 Recovery 语义
            self.frame[0][1].config(text="底包Recovery镜像")
            self.frame[3][1].config(text="移植Recovery镜像")
            for i in (self.frame[0], self.frame[3]):
                for idx, widget in enumerate(i):
                    if idx == 0:  # frame组件
                        widget.pack(side='top', fill='x', padx=5, pady=5)
                    elif idx == 2:  # entry输入框
                        widget.pack(side='left', fill='x', padx=5, pady=5)
                    else:  # label/button
                        widget.pack(side='left', padx=5, pady=5)
            ttk.Label(
                self,
                text="说明：仅支持输出 img 镜像。底包Recovery提供与设备匹配的内核和boot参数，移植Recovery提供第三方ramdisk（如TWRP）。",
                foreground="blue"
            ).pack(side='top', fill='x', padx=5, pady=5)
            # 底部确定按钮
            bottomframe = ttk.Frame(self)
            bottombutton = ttk.Button(bottomframe, text='确定', command=self.destroy)
            bottombutton.pack(side='right', padx=5, pady=5)
            bottomframe.pack(side='bottom', fill='x', padx=5, pady=5)
            return

        # ========== kernel-only 模式布局：只需 底包boot + 移植源boot（无 system 参与） ==========
        if self.is_kernel_only:
            # 底包：只显示 boot 框
            for idx, widget in enumerate(self.frame[0]):
                if idx == 0:
                    widget.pack(side='top', fill='x', padx=5, pady=5)
                elif idx == 2:
                    widget.pack(side='left', fill='x', padx=5, pady=5)
                else:
                    widget.pack(side='left', padx=5, pady=5)
            self.frame[1][0].pack_forget()  # 隐藏底包system
            # 移植源类型选择（zip/img 均可）
            sourcetype_frame = ttk.Frame(self)
            ttk.Label(sourcetype_frame, text="移植源类型：", width=16).pack(side='left', padx=5, pady=5)
            ttk.Radiobutton(
                sourcetype_frame, text="zip卡刷包", variable=self.source_type, value='zip',
                command=__toggle_source_type
            ).pack(side='left', padx=5)
            ttk.Radiobutton(
                sourcetype_frame, text="单独img镜像", variable=self.source_type, value='img',
                command=__toggle_source_type
            ).pack(side='left', padx=5)
            sourcetype_frame.pack(side='top', fill='x', padx=5, pady=5)
            # 移植源框（zip 包 / 移植用boot），隐藏移植用system
            for i in (self.frame[2], self.frame[3]):
                for idx, widget in enumerate(i):
                    if idx == 0:
                        widget.pack(side='top', fill='x', padx=5, pady=5)
                    elif idx == 2:
                        widget.pack(side='left', fill='x', padx=5, pady=5)
                    else:
                        widget.pack(side='left', padx=5, pady=5)
            self.frame[4][0].pack_forget()  # 隐藏移植用system
            __toggle_source_type()  # 按当前源类型修正显示
            ttk.Label(
                self,
                text="说明：仅移植内核只需底包boot与移植源boot，输出 boot.img（无需 system）。",
                foreground="blue"
            ).pack(side='top', fill='x', padx=5, pady=5)
            # 底部确定按钮
            bottomframe = ttk.Frame(self)
            bottombutton = ttk.Button(bottomframe, text='确定', command=self.destroy)
            bottombutton.pack(side='right', padx=5, pady=5)
            bottomframe.pack(side='bottom', fill='x', padx=5, pady=5)
            return

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
        # Recovery 模式：底包Recovery + 移植Recovery，强制 img 源/输出
        if self.is_recovery:
            return [self.baseboot.get(), '', self.portboot.get(), 'img']
        # kernel-only 模式：只需底包boot + 移植源boot（无 system 参与）
        if self.is_kernel_only:
            if self.source_type.get() == 'zip':
                return [self.baseboot.get(), '', self.portzip.get(), 'zip']
            else:
                return [self.baseboot.get(), '', (self.portboot.get(), ''), 'img']
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

class MyUI(ttk.Labelframe):
    """主UI框架类"""
    def __init__(self, parent):
        super().__init__(parent, text="MTK 低端机移植工具")
        self.update_source = StringVar(value='GitHub')  # 更新源：GitHub / Gitee
        self._update_lock = threading.Lock()  # 更新检查互斥锁（静默/手动串行）
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
        self.clean_base_after = BooleanVar(value=False)  # 完成后清除base缓存目录

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
            # 当前移植方案（芯片类型下拉框）
            chipset = self.chipset_select.get()
            is_recovery = bool(
                support_chipset_portstep.get(chipset, {}).get('flags', {}).get('recovery_only_mode', False)
            )
            is_kernel_only = bool(
                support_chipset_portstep.get(chipset, {}).get('flags', {}).get('kernel_only_mode', False)
            )
            # 校验：Recovery 模式仅支持 img 镜像输出（zip 输出无意义）
            if is_recovery and self.pack_type.get() == 'zip':
                print("错误：仅移植Recovery模式仅支持 img 镜像输出，请将输出类型切换为 img！", file=self.log)
                self.is_running = False
                self.port_button.config(state='normal')
                return

            # 获取选择的文件路径（传递输出类型和当前方案给FileChooser）
            files = FileChooser(self, self.pack_type.get(), chipset).get()
            baseboot, basesys, port_source, source_type = files
            
            # 校验：zip输出时必须用zip源
            if self.pack_type.get() == 'zip' and source_type != 'zip':
                print("错误：输出zip卡刷包时仅支持zip格式的移植源！", file=self.log)
                # 重置状态+启用按钮
                self.is_running = False
                self.port_button.config(state='normal')
                return
            
            # 检查底包文件是否存在
            if is_recovery:
                # Recovery 模式：只校验底包Recovery + 移植Recovery，不需要 system
                if not (baseboot != '' and Path(baseboot).exists()):
                    print("底包Recovery镜像未选择或不存在", file=self.log)
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
                if not (port_source != '' and Path(port_source).exists()):
                    print("移植Recovery镜像未选择或不存在", file=self.log)
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
            elif is_kernel_only:
                # kernel-only：只需底包boot，不需要底包system
                if not (baseboot != '' and Path(baseboot).exists()):
                    print("底包boot镜像未选择或不存在", file=self.log)
                    self.is_running = False
                    self.port_button.config(state='normal')
                    return
            else:
                for file_path in [baseboot, basesys]:
                    if not Path(file_path).exists() or file_path == '':
                        print(f"文件{file_path}未选择或不存在", file=self.log)
                        # 重置状态+启用按钮
                        self.is_running = False
                        self.port_button.config(state='normal')
                        return
            
            # 检查移植源文件是否存在
            if is_recovery:
                pass  # 已在上面校验
            elif is_kernel_only:
                if source_type == 'zip':
                    if not Path(port_source).exists() or port_source == '':
                        print(f"移植包{port_source}未选择或不存在", file=self.log)
                        # 重置状态+启用按钮
                        self.is_running = False
                        self.port_button.config(state='normal')
                        return
                else:
                    portboot, _portsys = port_source
                    if not Path(portboot).exists() or portboot == '':
                        print("移植用boot.img未选择或不存在", file=self.log)
                        # 重置状态+启用按钮
                        self.is_running = False
                        self.port_button.config(state='normal')
                        return
            elif source_type == 'zip':
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
            if is_recovery:
                print(f"底包Recovery路径：{baseboot}\n移植Recovery路径：{port_source}", file=self.log)
            elif is_kernel_only:
                print(f"底包boot路径：{baseboot}", file=self.log)
                if source_type == 'zip':
                    print(f"移植包路径：{port_source}", file=self.log)
                else:
                    print(f"移植用boot.img路径：{port_source[0]}", file=self.log)
            else:
                print(f"底包boot路径：{baseboot}\n底包system路径：{basesys}", file=self.log)
                if source_type == 'zip':
                    print(f"移植包路径：{port_source}", file=self.log)
                else:
                    print(f"移植用boot.img路径：{port_source[0]}\n移植用system.img路径：{port_source[1]}", file=self.log)
            
            # 配置移植参数（深拷贝，避免勾选值污染模块级全局配置）
            import copy
            newdict = copy.deepcopy(support_chipset_portstep[self.chipset_select.get()])
            for key, tkbool in self.item:
                newdict[key] = tkbool.get()
            
            # Magisk相关配置
            newdict['patch_magisk'] = self.patch_magisk.get()
            newdict['magisk_apk'] = self.magisk_apk.get()
            newdict['target_arch'] = self.target_arch.get()
            newdict['clean_base_after'] = self.clean_base_after.get()
            
            # 校验：kernel-only 模式仅支持 img 输出（zip 输出会生成无 system 内容的坏包）
            if is_kernel_only and self.pack_type.get() == 'zip':
                print("错误：仅移植内核模式（kernel-only）仅支持 img 输出，请将输出类型切换为 img！", file=self.log)
                self.is_running = False
                self.port_button.config(state='normal')
                return
            # 确定输出类型（zip→genimg=False，img→genimg=True）
            genimg = True if self.pack_type.get() == 'img' else False

            # #61：img 输出下 generate_script 不生效（仅 zip 输出走脚本生成）——显式提示，避免静默空转（与 CLI #70 对齐）
            if genimg and newdict.get('generate_script'):
                print('【提示】generate_script 仅 zip 输出生效，img 输出下该条目将被忽略（非错误）', file=self.log)
            
            # 定义移植进程的执行函数（封装逻辑，确保流程结束后重置状态）
            def run_port_process():
                try:
                    # 启动移植逻辑（Recovery 模式：basesys 置空，移植源为单 recovery 元组）
                    _port_src = (port_source, '') if is_recovery else port_source
                    _base_sys = '' if is_recovery else basesys
                    _pu = portutils(
                        newdict, baseboot, _base_sys, _port_src, 'img' if is_recovery else source_type, genimg, self.log
                    )
                    self.last_outdir = str(_pu.outdir)
                    port_process = _pu.start
                    port_process()  # 执行移植
                except Exception as e:
                    import traceback
                    print(f"【移植异常】执行过程出错：{str(e)}", file=self.log)
                    # 打印完整堆栈，便于定位问题（只给一行 str(e) 很难排查）
                    print(traceback.format_exc(), file=self.log)
                finally:
                    # 无论成功/失败，都重置状态+启用按钮
                    self.is_running = False
                    self.port_button.config(state='normal')
                    print("【提示】移植流程结束，按钮已恢复可用！", file=self.log)
            
            # 启动移植进程（避免UI阻塞）
            DummyProcess(target=run_port_process).start()
            
        except Exception as e:
            # 捕获所有异常，确保状态重置
            import traceback
            print(f"【执行异常】{str(e)}", file=self.log)
            print(traceback.format_exc(), file=self.log)
            self.is_running = False
            self.port_button.config(state='normal')
    
    # ========== LK去警告 功能（原版 LKTool 全功能，除清空日志） ==========
    def _lk_selected(self):
        """返回当前勾选的要处理镜像路径列表"""
        folder = self.lk_dir_var.get().strip().strip('"')
        if not folder or not Path(folder).is_dir():
            return []
        if not getattr(self, 'lk_files', None):
            return []
        return [p for p, v in self.lk_files if v.get()]

    def _lk_browse(self):
        d = askdirectory(title='选择固件目录（GeekFlashTool readback 目录）')
        if d:
            self.lk_dir_var.set(d)
            self._lk_detect()

    def _lk_detect(self):
        """重新检测目录中的 lk/lk2 镜像（重建勾选列表）"""
        folder = self.lk_dir_var.get().strip().strip('"')
        for w in self.lk_filebox.winfo_children():
            w.destroy()
        self.lk_files = []
        if not folder or not Path(folder).is_dir():
            self.lk_hint.config(text="目录不存在", foreground='red')
            self.lk_status.set("目录不存在")
            return
        from .LKPatch import detect_lk_files, read_file, human_size
        found = detect_lk_files(folder)
        if not found:
            self.lk_hint.config(text="该目录下没有 lk.img / lk2.img", foreground='red')
            self.lk_status.set("未检测到镜像")
            return
        for p in found:
            v = BooleanVar(value=True)
            ttk.Checkbutton(self.lk_filebox, variable=v,
                            text='%s   (%s)' % (Path(p).name, human_size(Path(p).stat().st_size))
                            ).pack(side='left', padx=(0, 12))
            self.lk_files.append((p, v))
        same = ''
        if len(found) >= 2:
            try:
                d0 = read_file(found[0])
                if all(read_file(f) == d0 for f in found[1:]):
                    same = '  ·  内容完全相同（A/B 双槽，需同时刷入）'
            except OSError:
                pass
        self.lk_hint.config(text='检测到 %d 个镜像%s' % (len(found), same), foreground='#0066cc')
        self.lk_status.set('检测到 %d 个镜像' % len(found))
        print(f"【LK检测】目录 {folder} 检测到 {len(found)} 个 LK 镜像", file=self.log)

    def _lk_scan(self):
        from .LKPatch import scan_report
        if not self._lk_selected():
            print("请先选择固件目录并勾选要处理的镜像", file=self.log)
            return
        scan_report(self.lk_dir_var.get().strip().strip('"'), self.log, self._lk_selected())

    def _lk_patch(self):
        from .LKPatch import patch_files
        sel = self._lk_selected()
        if not sel:
            print("请先选择固件目录并勾选要处理的镜像", file=self.log)
            return
        patch_files(self.lk_dir_var.get().strip().strip('"'), self.log, sel,
                    patch_a=self.lk_var_a.get(), patch_b=self.lk_var_b.get(),
                    auto_backup=self.lk_var_bak.get(), gen_report=self.lk_var_ver.get(),
                    inplace=self.lk_var_inplace.get())

    def _lk_verify(self):
        from .LKPatch import verify_files
        if not self._lk_selected():
            print("请先选择固件目录并勾选要处理的镜像", file=self.log)
            return
        verify_files(self.lk_dir_var.get().strip().strip('"'), self.log, self._lk_selected())

    def _lk_restore(self):
        from .LKPatch import restore_files
        sel = self._lk_selected()
        if not sel:
            print("请先选择固件目录并勾选要处理的镜像", file=self.log)
            return
        names = '\n'.join('  ' + Path(p).name for p in sel)
        if not messagebox.askyesno("LK去警告", "将用备份覆盖以下文件：\n\n%s\n\n确认还原？" % names):
            return
        restore_files(self.lk_dir_var.get().strip().strip('"'), self.log, sel)

    def _lk_open_dir(self):
        # 跳转到输出目录：打开最近一次包含 LK 产物（备份/补丁）的时间戳目录；
        # 跨会话仍能打开上次打补丁的输出；无任何产物时提示
        from .LKPatch import latest_lk_out_dir
        folder = latest_lk_out_dir()
        if not folder:
            print("尚未生成输出目录，请先选择固件目录并打补丁", file=self.log)
            return
        try:
            os.startfile(folder)
        except Exception as e:
            print(f"打开目录失败：{e}", file=self.log)

    def _open_last_outdir(self):
        """打开最近一次移植的输出目录 out/<时间戳>/"""
        outdir = getattr(self, 'last_outdir', None)
        if not outdir or not Path(outdir).is_dir():
            print("尚未完成移植，没有可打开的输出目录", file=self.log)
            return
        try:
            os.startfile(outdir)
        except Exception as e:
            print(f"打开输出目录失败：{e}", file=self.log)

    def __setup_widgets(self):
        """初始化主UI的所有组件"""

        def __scroll_event(event):
            """移植条目滚动事件处理（Windows滚轮）"""
            # 每格滚动 2 行（约44px）；触控板/高精度滚轮 delta 为 120 的倍数，自动放大
            lines = max(1, abs(event.delta) // 120) * 2
            scroll_num = -lines if event.delta > 0 else lines
            actcanvas.yview_scroll(scroll_num, 'units')
        
        def __scroll_up(event):
            actcanvas.yview_scroll(-2, 'units')
        
        def __scroll_down(event):
            actcanvas.yview_scroll(2, 'units')

        def __bind_wheel(widget):
            """递归绑定滚轮事件：修复鼠标悬停在复选框上时滚轮失效的问题"""
            widget.bind("<MouseWheel>", __scroll_event)
            widget.bind("<Button-4>", __scroll_up)   # Linux 滚轮上
            widget.bind("<Button-5>", __scroll_down)  # Linux 滚轮下
            for child in widget.winfo_children():
                __bind_wheel(child)
        
        def __scroll_func(event):
            """更新滚动区域"""
            actcanvas.configure(scrollregion=actcanvas.bbox("all"), width=300, height=180)
        
        def __create_cv_frame():
            """创建移植条目滚动画布内的frame"""
            self.actcvframe = ttk.Frame(actcanvas)
            # 记录 window item id，切换方案销毁 frame 时须一并删除，否则 bbox 残留撑大滚动范围
            self._cv_item = actcanvas.create_window(0, 0, window=self.actcvframe, anchor='nw')
            self.actcvframe.bind("<Configure>", __scroll_func)
            actcanvas.update()
        
        def __sync_select_all():
            """条目勾选变化时同步全选框状态（三态：✓全选 / -部分 / 空全不选）"""
            vals = [v.get() for _, v in self.item]
            if all(vals):
                self.select_all_var.set(True)
                self.select_all_box.state(['!alternate'])
            elif not any(vals):
                self.select_all_var.set(False)
                self.select_all_box.state(['!alternate'])
            else:
                # 部分选中：框内显示 "-"
                self.select_all_var.set(False)
                self.select_all_box.state(['alternate'])
        
        def __toggle_select_all():
            """全选/全不选：空或部分选中时点击 -> 全部勾选(✓)；全选状态下点击 -> 全部取消(空)"""
            vals = [v.get() for _, v in self.item]
            if all(vals):
                for _, v in self.item:
                    v.set(False)
            else:
                for _, v in self.item:
                    v.set(True)
            __sync_select_all()
        
        def __load_port_item(select):
            """加载选中芯片类型对应的移植条目"""
            print(f"选中移植方案为{select}...", file=self.log)
            item_dict = {k: v for k, v in support_chipset_portstep[select]['flags'].items()
                         if k not in ('recovery_only_mode', 'kernel_only_mode', 'lk_patch_mode')}
            # 仅移植Recovery / 仅移植内核 方案只输出 img：隐藏无意义的 generate_script 条目
            if ('recovery_only_mode' in support_chipset_portstep[select]['flags']
                    or 'kernel_only_mode' in support_chipset_portstep[select]['flags']):
                item_dict.pop('generate_script', None)
            self.item = []
            self.itembox = []
            
            # 销毁原有移植条目frame（同时删除画布中的 window item，避免 bbox 残留导致滚动过头留白）
            if hasattr(self, 'actcvframe'):
                actcanvas.delete(self._cv_item)
                self.actcvframe.destroy()
            __create_cv_frame()

            # LK去警告 模式：左侧整体切换为原版 LK 工具面板（去掉"支持的移植条目"框与一键移植）
            _is_lk = bool(
                support_chipset_portstep.get(select, {}).get('flags', {}).get('lk_patch_mode', False)
            )
            if _is_lk:
                self.item = []
                self.itembox = []
                # 隐藏常规左侧控件：支持移植条目框 / 一键移植 / 输出类型与magisk区
                actframe.pack_forget()
                self.port_button.pack_forget()
                buttonlabel.pack_forget()
                if hasattr(self, '_extra'):
                    self._extra.pack_forget()
                # 显示 LK 工具面板（占左侧大部分区域）
                self.lk_panel.pack(side='top', fill='both', expand='yes', padx=5, pady=5)
                self.pack_type.set('img')
                print("LK去警告模式：已切换为 LK 工具界面（扫描/打补丁/校验/还原备份/打开输出目录），仅支持 img 输出", file=self.log)
                return

            # 创建移植条目复选框
            for index, item_key in enumerate(item_dict):
                self.item.append([item_key, BooleanVar(value=item_dict[item_key])])
                self.itembox.append(
                    ttk.Checkbutton(
                        self.actcvframe, 
                        text=item_key, 
                        variable=self.item[index][1],
                        command=__sync_select_all
                    )
                )
            
            # 布局移植条目复选框
            for checkbox in self.itembox:
                checkbox.pack(side='top', fill='x', padx=5)
            
            # 按实际条目数动态调整滚动范围：
            # 条目少时（内容低于视口高度）不可滚动、不产生空白；条目多时可滚动到全部内容
            actcanvas.configure(scrollregion=(0, 0, 300, max(154, len(self.itembox) * 22)))
            # 递归绑定滚轮，确保鼠标在复选框/全选框上时也能滚动
            __bind_wheel(self.actcvframe)
            __sync_select_all()
        
            # Recovery 模式：隐藏 zip 卡刷包输出选项与修补magisk区（仅支持 img 镜像输出）
            _is_rec = bool(
                support_chipset_portstep.get(select, {}).get('flags', {}).get('recovery_only_mode', False)
            )
            _is_ko = bool(
                support_chipset_portstep.get(select, {}).get('flags', {}).get('kernel_only_mode', False)
            )
            if _is_rec:
                self.output_label.grid_forget()
                self.buttoncheck1.grid_forget()
                self.buttoncheck2.grid_forget()
                self.recovery_hint_label.grid(column=0, row=0, padx=5, pady=5, columnspan=2)
                self.buttonmagisk.grid_forget()
                self.magiskarch.grid_forget()
                self.magiskapkentry.grid_forget()
                self.magiskapkbtn.grid_forget()
                # 强制使用 img 镜像输出
                self.pack_type.set('img')
                print("仅移植Recovery模式：仅支持 img 镜像输出，已隐藏 zip 卡刷包与修补magisk选项", file=self.log)
            elif _is_ko:
                # kernel-only：隐藏 zip 卡刷包输出选项（保留 magisk 修补），仅支持 img
                self.output_label.grid_forget()
                self.buttoncheck1.grid_forget()
                self.buttoncheck2.grid_forget()
                self.recovery_hint_label.grid(column=0, row=0, padx=5, pady=5, columnspan=2)
                # 恢复 magisk 显示（recovery 分支可能已将其隐藏）
                self.buttonmagisk.grid(column=0, row=1, padx=5, pady=5, sticky='w', columnspan=2)
                if self.patch_magisk.get():
                    self.magiskarch.grid(column=0, row=2, padx=5, pady=5, sticky='nsew', columnspan=2)
                    self.magiskapkentry.grid(column=0, row=3, padx=5, pady=5, sticky='ew')
                    self.magiskapkbtn.grid(column=1, row=3, padx=(0, 5), pady=5, sticky='e')
                self.pack_type.set('img')
                print("仅移植内核模式：仅支持 img 镜像输出，已隐藏 zip 卡刷包选项", file=self.log)
            else:
                self.recovery_hint_label.grid_forget()
                self.buttoncheck1.grid(column=0, row=0, padx=5, pady=5)
                self.buttoncheck2.grid(column=1, row=0, padx=5, pady=5)
                self.buttonmagisk.grid(column=0, row=1, padx=5, pady=5, sticky='w', columnspan=2)
                # 恢复 Magisk 展开状态（若已勾选）
                if self.patch_magisk.get():
                    self.magiskarch.grid(column=0, row=2, padx=5, pady=5, sticky='nsew', columnspan=2)
                    self.magiskapkentry.grid(column=0, row=3, padx=5, pady=5, sticky='ew')
                    self.magiskapkbtn.grid(column=1, row=3, padx=(0, 5), pady=5, sticky='e')
            # 非 LK 方案：恢复左侧常规布局（隐藏 LK 工具面板）
            self.lk_panel.pack_forget()
            actframe.pack(side='top', fill='x', expand='yes')
            self.port_button.pack(side='top', fill='both', padx=5, pady=5, expand='yes')
            buttonlabel.pack(side='top', padx=5, pady=5, fill='x', expand='yes')
            if hasattr(self, '_extra'):
                self._extra.pack(side='top', padx=5, pady=(0, 5), fill='x')

        # ========== 左侧配置区域 ==========
        optframe = ttk.Frame(self)
        
        # 芯片类型选择
        optlabel = ttk.Label(optframe)
        ttk.Label(optlabel, text="芯片类型", anchor='e').pack(side='left', padx=5, pady=5)
        self.chipset_menu = ttk.OptionMenu(
            optlabel, 
            self.chipset_select, 
            support_chipset[0], 
            *support_chipset, 
            command=__load_port_item
        )
        self.chipset_menu.pack(side='left', fill='x', padx=5, pady=5)
        optlabel.pack(side='top', fill='x')
        
        # 移植条目滚动区域（标题右侧带全选复选框）
        actframe = ttk.Labelframe(optframe, height=180)
        actframe_header = ttk.Frame(actframe)
        ttk.Label(actframe_header, text="支持的移植条目").pack(side='left', padx=(0, 6))
        self.select_all_var = BooleanVar(value=False)
        self.select_all_box = ttk.Checkbutton(
            actframe_header,
            text="全选",
            variable=self.select_all_var,
            command=__toggle_select_all
        )
        self.select_all_box.pack(side='left')
        actframe.configure(labelwidget=actframe_header)
        actcanvas = Canvas(actframe)
        actscroll = ttk.Scrollbar(actframe, orient='vertical', command=actcanvas.yview)
        actcanvas.configure(
            yscrollcommand=actscroll.set, 
            scrollregion=(0, 0, 300, 180), 
            yscrollincrement=22  # 1个单位≈1行复选框高度，滚动按行计
        )
        actcanvas.bind("<MouseWheel>", __scroll_event)  # 绑定鼠标滚轮
        actscroll.pack(side='right', fill='y')
        actcanvas.pack(side='right', fill='x', expand='yes', anchor='e')
        actframe.pack(side='top', fill='x', expand='yes')
        __create_cv_frame()
        
        # 操作按钮区域（与"支持的移植条目"同款 Labelframe，标题=输出类型）
        buttonlabel = ttk.Labelframe(optframe)
        _out_header = ttk.Frame(buttonlabel)
        self.output_label = ttk.Label(_out_header, text="输出类型")
        self.output_label.pack(side='left', padx=(0, 6))
        buttonlabel.configure(labelwidget=_out_header)
        # 输出类型下方的其他选项区（修补magisk / 完成后清除base），与输出类型框明显分隔
        self._extra = ttk.Frame(optframe)
        # 一键移植按钮（保存到self.port_button，用于禁用/启用）
        self.port_button = ttk.Button(
            optframe, 
            text="一键移植", 
            command=self.__start_port
        )
        self.port_button.pack(side='top', fill='both', padx=5, pady=5, expand='yes')

        # 打开输出目录按钮（移植完成后跳转 out/<时间戳>/）
        self.open_out_btn = ttk.Button(
            optframe,
            text="打开输出目录",
            command=self._open_last_outdir
        )
        self.open_out_btn.pack(side='bottom', fill='x', padx=5, pady=(0, 5))
        
        # Recovery 模式下的输出类型提示（仅支持 img 镜像）
        self.recovery_hint_label = ttk.Label(buttonlabel, text="仅支持输出 img 镜像", foreground='#0066cc')
        self.buttoncheck1 = ttk.Checkbutton(
            buttonlabel, 
            text="zip卡刷包", 
            variable=self.pack_type, 
            onvalue='zip', 
            offvalue='img'
        )
        self.buttoncheck2 = ttk.Checkbutton(
            buttonlabel, 
            text="img镜像", 
            variable=self.pack_type, 
            onvalue='img', 
            offvalue='zip'
        )
        self.buttoncheck1.grid(column=0, row=0, padx=5, pady=5)
        self.buttoncheck2.grid(column=1, row=0, padx=5, pady=5)
        
        # Magisk修补配置
        self.magiskarch = ttk.OptionMenu(
            self._extra, 
            self.target_arch, 
            "arm64", 
            *["arm64", "arm", "x86", "x86_64"]
        )
        self.magiskapkentry = ttk.Entry(self._extra, textvariable=self.magisk_apk)
        self.magiskapkentry.bind("<Double-Button-1>", lambda x:self.magisk_apk.set(askopenfilename()))
        self.magiskapkbtn = ttk.Button(self._extra, text="选择", width=6, command=lambda: self.magisk_apk.set(askopenfilename()))

        # Magisk修补复选框（控制架构/APK输入框显示）
        self.buttonmagisk = ttk.Checkbutton(
            self._extra,
            text="修补magisk",
            variable=self.patch_magisk,
            onvalue=True,
            offvalue=False,
            command=lambda: (
                self.magiskapkentry.grid_forget(),
                self.magiskapkbtn.grid_forget(),
                self.magiskarch.grid_forget(),
            ) if not self.patch_magisk.get() else (
                self.magiskarch.grid(column=0, row=2, padx=5, pady=5, sticky='nsew', columnspan=2),
                self.magiskapkentry.grid(column=0, row=3, padx=5, pady=5, sticky='ew'),
                self.magiskapkbtn.grid(column=1, row=3, padx=(0, 5), pady=5, sticky='e')
            )
        )
        self.buttonmagisk.grid(column=0, row=1, padx=5, pady=5, sticky='w', columnspan=2)

        # 完成后清除base缓存目录
        ttk.Checkbutton(
            self._extra,
            text="完成后清除base目录",
            variable=self.clean_base_after,
            onvalue=True,
            offvalue=False
        ).grid(column=0, row=4, padx=5, pady=5, sticky='w', columnspan=2)

        buttonlabel.pack(side='top', padx=5, pady=5, fill='x', expand='yes')
        self._extra.pack(side='top', padx=5, pady=(0, 5), fill='x')


        # ========== LK去警告 面板（选择 LK 方案时替换左侧常规布局，原版 LKTool 界面） ==========
        self.lk_panel = ttk.Labelframe(optframe, text="MTK LK 去警告工具")
        # 固件目录行
        _lkdir = ttk.Frame(self.lk_panel)
        self.lk_dir_var = StringVar()
        ttk.Label(_lkdir, text="固件目录").pack(side='left', padx=(5, 4))
        ttk.Entry(_lkdir, textvariable=self.lk_dir_var).pack(side='left', fill='x', expand='yes')
        ttk.Button(_lkdir, text="浏览...", width=7, command=self._lk_browse).pack(side='left', padx=(4, 2))
        ttk.Button(_lkdir, text="重新检测", width=8, command=self._lk_detect).pack(side='left', padx=(0, 5))
        _lkdir.pack(side='top', fill='x', padx=5, pady=(8, 4))
        # 待处理镜像提示 + 勾选列表（动态重建）
        self.lk_hint = ttk.Label(self.lk_panel, text="未选择目录", foreground='gray')
        self.lk_hint.pack(side='top', anchor='w', padx=8)
        self.lk_filebox = ttk.Frame(self.lk_panel)
        self.lk_filebox.pack(side='top', fill='x', padx=8, pady=(0, 6))
        self.lk_files = []
        # 补丁选项
        _o1 = ttk.Frame(self.lk_panel)
        self.lk_var_a = BooleanVar(value=True)
        self.lk_var_b = BooleanVar(value=True)
        ttk.Checkbutton(_o1, text="补丁A：去橙/红警告+5s延时", variable=self.lk_var_a).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(_o1, text="补丁B：清空警告文本", variable=self.lk_var_b).pack(side='left')
        _o1.pack(side='top', anchor='w', padx=8, pady=(2, 2))
        _o2 = ttk.Frame(self.lk_panel)
        self.lk_var_bak = BooleanVar(value=True)
        self.lk_var_ver = BooleanVar(value=True)
        self.lk_var_inplace = BooleanVar(value=False)
        ttk.Checkbutton(_o2, text="自动备份", variable=self.lk_var_bak).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(_o2, text="生成校验报告", variable=self.lk_var_ver).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(_o2, text="直接覆盖原文件", variable=self.lk_var_inplace).pack(side='left')
        _o2.pack(side='top', anchor='w', padx=8, pady=(2, 6))
        # 功能按钮（原版 LKTool 全功能，除清空日志；左侧较窄分行排布）
        _btns1 = ttk.Frame(self.lk_panel)
        for _t, _c in (("扫描", self._lk_scan), ("打补丁", self._lk_patch),
                       ("校验", self._lk_verify)):
            ttk.Button(_btns1, text=_t, width=8, command=_c).pack(side='left', padx=3, pady=3)
        _btns1.pack(side='top', fill='x', padx=8, pady=(6, 0))
        _btns2 = ttk.Frame(self.lk_panel)
        for _t, _c in (("还原备份", self._lk_restore), ("打开输出目录", self._lk_open_dir)):
            ttk.Button(_btns2, text=_t, width=10, command=_c).pack(side='left', padx=3, pady=3)
        _btns2.pack(side='top', fill='x', padx=8)
        # 状态行
        self.lk_status = StringVar(value='就绪：选择固件目录后点击"重新检测"')
        ttk.Label(self.lk_panel, textvariable=self.lk_status, foreground='gray', font=('Microsoft YaHei', 8)
                  ).pack(side='top', anchor='w', padx=8, pady=(6, 6))
        self.lk_panel.pack_forget()  # 默认隐藏，选择 LK 方案时显示
        # 版本号行（左下角，修补面具选项下面）：左侧版本号，右侧 GitHub / Gitee 仓库图标
        bottom_row = ttk.Frame(optframe)
        bottom_row.pack(side='bottom', fill='x', padx=8, pady=(0, 5))
        ttk.Label(bottom_row, text=f"版本号：{tool_version}", font=('Microsoft YaHei', 8), foreground='gray').pack(side='left')

        # 仓库图标（点击跳转对应仓库，靠右显示）
        _icon_dir = Path(__file__).resolve().parent
        _repos = [
            (_icon_dir / 'icon_github.png', 'https://github.com/LJY-33684/mtk-garbage-porttool-master'),
            (_icon_dir / 'icon_gitee.png', 'https://gitee.com/Q3368436451/mtk-garbage-porttool-master'),
        ]
        for _icon_path, _repo_url in _repos:
            try:
                _img = PhotoImage(file=str(_icon_path))
                _lbl = ttk.Label(bottom_row, image=_img, cursor='hand2')
                _lbl.image = _img  # 防止被垃圾回收
                _lbl.pack(side='right', padx=(0, 3))
                _lbl.bind('<Button-1>', lambda e, url=_repo_url: webbrowser.open(url))
            except Exception:
                pass  # 图标文件缺失时静默跳过，不阻塞启动

        optframe.pack(side='left', padx=5, pady=5, fill='y', expand='no')
        
        # ========== 右侧日志区域 ==========
        logframe = ttk.Labelframe(self, text="日志输出")
        self.log = LogLabel(logframe)
        self.log.pack(side='left', fill='both', anchor='center')
        logframe.pack(side='left', padx=5, pady=5, fill='both', expand='yes')

        # 初始加载移植条目
        __load_port_item(self.chipset_select.get())

        # 更新结果事件绑定（后台线程通过 event_generate 通知主线程刷新 UI）
        self.bind('<<UpdateResult>>', self._on_update_result_event)

        # 启动时静默检查更新（仅发现新版本时弹窗，失败/已是最新均不提示）
        threading.Thread(target=lambda: self._fetch_update_worker(silent=True), daemon=True).start()


    # ========== 检查更新功能（网络逻辑见 update.py）==========

    def _on_check_update(self):
        """检查更新按钮点击回调"""
        self._check_update_btn.config(text="检查更新中...", state="disabled")
        # 后台线程请求，避免阻塞 UI
        t = threading.Thread(target=self._fetch_update_worker, daemon=True)
        t.start()

    def _fetch_update_worker(self, silent=False):
        """后台线程：请求 latest_version.txt + 更新内容（网络逻辑见 update.py）
        silent=True 时：失败不弹提示、版本相同不弹窗，仅在发现新版本时弹出更新窗口
        """
        # 互斥锁：静默检查与手动检查串行，避免并发请求导致拉取失败
        with self._update_lock:
            source = self.update_source.get()
            result = fetch_update_info(source)

        # 调度到主线程更新 UI（Tkinter 非线程安全：后台线程只暂存结果并产生事件，由主线程处理）
        try:
            self._update_result = result
            self._update_silent = silent
            self.event_generate('<<UpdateResult>>')
        except Exception:
            # 如果事件调度失败（极端情况），非静默模式下直接在后台线程尝试恢复按钮
            if not silent:
                try:
                    self._check_update_btn.config(text="检查更新", state="normal")
                except Exception:
                    pass

    def _on_update_result_event(self, _event=None):
        """主线程处理更新结果（由后台线程 event_generate 触发）"""
        result = getattr(self, '_update_result', None)
        if result is None:
            return
        silent = getattr(self, '_update_silent', False)
        if result.ok:
            if not (silent and result.tag == tool_version):
                self._on_update_success(result.tag, result.body, result.download_url)
        else:
            if not silent:
                self._on_update_failed(result.reason)

    def _on_update_success(self, tag, body, download_url):
        """检查更新成功（主线程）"""
        self._check_update_btn.config(text="检查更新", state="normal")
        self._show_update_dialog(tag, body, download_url)

    def _on_update_failed(self, reason):
        """检查更新失败（主线程）"""
        self._check_update_btn.config(text="检查更新失败", state="normal")
        # 3秒后恢复按钮文字
        self.after(3000, lambda: self._check_update_btn.config(text="检查更新"))

    def _show_update_dialog(self, tag, body, download_url):
        """显示更新内容弹窗（markdown 格式 + 标题右侧前往下载按钮）"""
        win = Toplevel(self)
        win.title(f"当前已是最新版本 - {tag}" if tag == tool_version else f"发现新版本 - {tag}")
        win.geometry("640x480")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        # 标题栏：左侧标题 + 右侧前往下载按钮
        header_frame = ttk.Frame(win)
        header_frame.pack(fill='x', padx=12, pady=(10, 5))
        title_text = f"当前已是最新版本：{tag}" if tag == tool_version else f"发现新版本：{tag}"
        ttk.Label(header_frame, text=title_text, font=('Microsoft YaHei', 12, 'bold')).pack(side='left')

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

        render_markdown(text_widget, body)
        text_widget.config(state='disabled')  # 只读
