# 1.2-beta6

本次版本覆盖 beta5 之后的所有改动：修复 SDAT 卡刷包结构错误与分区硬编码、kernel-only 输出坏包拦截、三轮深挖复查发现的配置/底层模块问题，并补全 mt6572/mt6580 老芯片的 wifi 替换能力。

## 新增

- **SDAT 卡刷包结构修复**：新增 block_image_update 刷机脚本分支；移植源无 SELinux xattr 时自动回退底包 system_file_contexts；镜像先以 raw 修复完毕再转 sparse，符号链接/自查不再崩
- **刷机脚本分区自动解析**：从移植源 updater-script 自动识别 system/boot 分区（mmcblk0pX），不再硬编码固定分区；支持 boot-only 卡刷包（system 缺失仅刷 boot 并提示）
- **kernel-only 输出拦截**：仅移植内核 + ZIP 输出会产生空 system 坏包，现按输出类型二次拦截并提示切换 img 输出（防绕过 UI 直接调用）
- **mt6572 / mt6580 wifi 替换补全**：两个老芯片方案新增 `replace_wifi` 开关与真实 wifi 条目（wpa_supplicant/hostapd/wpa_cli/etc/wifi/libwpa_client/libwifi-service）；底包缺失路径打印「跳过（底包中不存在 xxx）」不再中断
- **权限推断增强**：bin / xbin 精确匹配 + suid 位保留，img 与 SDAT 两段逻辑一致

## 修复

**配置 / 替换体系**

- mt6580 camera 组补开关；平板方案 gps/ril 无组开关删除、init 组保留空组；mt6797 replace_init 双重执行（#1–#3）
- wifi 组收窄：mt6797 / G79 / 平板方案 `vendor/firmware` 整目录替换收窄为 `wifi*` 通配，避免误换 modem 固件；`vendor/firmware` 跨组重复去重（#4 / #23 / #24）
- auto 白名单补 libcam_utils；libstagefrighthw 排除子串矛盾修正（#7 / #16）
- auto 模式 `vendor/firmware` 维持整目录替换（收窄会漏换 modem）并打印日志提示（#11）
- 仅移植内核方案死配置移除；change_locale 补语言/区域同步（#22 / #13）

**boot / 脚本 / 系统处理**

- boot 阶段 replace 组直接索引 KeyError 防御（#5）
- `__pack_fit_size` 返回 int，避免 `-l` 参数带小数点（#10）
- updater-script format() 分区硬编码改动态（#8）
- BootPatcher 缺 magiskboot 时友好阻断，不再硬崩（#37）

**底层模块**

- ext4 BlockReader 单块读取 / size_readable 单位换算 / xattrs 前缀死参数 / get_inode NameError / xattr 异常保护（#31–#35）
- imgextractor 大文件分块流式拷贝（32 位进程防 OOM）、路径空格决策留档、Linux 非 root chown 容错、双重赋值清理（#25–#28）
- proputil UTF-8 BOM 首行、parseMagiskApk 旧版 apk 防御、img 源输出名 TypeError、bootutil split 一致性（#19 / #20 / #21 / #14）
- sdat2img 注释与行为对齐（#29）

**工具 / 启动 / 更新**

- fscheck.py 改包导入；bin / configs.json 读取基于文件定位，不再依赖当前工作目录（#12 / #18）
- 更新检查线程安全：后台线程仅产生事件，UI 由主线程处理（#17）

## 核验

- Windows 下 zip 条目反斜杠问题（#40）经实测反驳确认**误报，不修**
- 全部 40 项复查问题闭环（39 项修复 + 1 项撤案），无遗留必修项
- 回归验证全过：SDAT e2e、auto 卡刷包 e2e（分区自动解析）、kernel-only 拦截两向、wifi 移植 e2e、全量编译

## 注意事项

- 面向 **Android 7.1.2 及更低版本**（无 VNDK）老设备；Android 8.0+（有 VNDK / Treble）建议直接刷 GSI
- 仅支持 **同平台 / 同芯片系列** 之间移植，跨平台会导致驱动不兼容、无法开机
- 仅移植内核（kernel-only）模式只输出 boot.img，不处理 system
