# 第三方版权声明 / Third-Party Notices

本工具（mtk-garbage-porttool）主体以 **GNU General Public License v3.0（GPL-3.0）** 发布。
在遵循 GPL-3.0 的前提下，本工具包含以下采用 **MIT License** 的第三方开源组件。MIT 与 GPL-3.0 兼容。

---

## 1. OPPO/Realme/OnePlus 固件解密逻辑

本工具的 `porttool/oppo_decrypt.py` 合并、修改自以下由 **B. Kerler** 编写的 MIT 许可组件（合并文件头已保留原版权行并注明 Modified by）：

| 原文件 | 功能 | 版权 |
|---|---|---|
| `ofp_mtk_decrypt.py` | OPPO MTK OFP 固件解密（AES-CFB128） | Copyright (c) 2022 B. Kerler |
| `ozipdecrypt.py` | Realme/OPPO OZIP 固件解密（AES-ECB） | Copyright (c) 2017-2020 B. Kerler |
| `opscrypto.py` | OnePlus OPS 固件解包（自定义流密码） | Copyright (c) 2019-2021 B. Kerler |

来源仓库：<https://github.com/bkerler/OPPO_Decrypt_Tools>（经 <https://github.com/ColdWindScholar/TIK> 集成）。

## 2. pyaes（纯 Python AES 实现）

- 位置：`porttool/pyaes/`
- 版本：1.6.1（未改动，随附其 `LICENSE.txt`）
- 版权：Copyright (c) 2014 Richard Moore
- 用途：在未检测到 openssl 时作为 AES 解密的内置兜底后端。
- 来源：<https://github.com/ricmoo/pyaes>

## 3. Brotli（解压组件）

- 位置：
  - Windows 二进制：`bin/win/x86_64/brotli.exe`（Google 官方 Windows 静态版，随包分发）
  - Python 库：`porttool/_vendor_brotli/`（官方 PyPI wheel 解包，cp312/cp313/cp314 × Windows/Linux，按解释器 ABI 自动匹配）
- 版本：1.2.0
- 版权：Copyright (c) 2009, 2010, 2013-2016 by the Brotli Authors（MIT License）
- 用途：OPPO/Realme/OnePlus 固件解密 img 输出时解压 `system/vendor.new.dat.br`（Android 9+ 固件）；zip 输出与 Android 8 以下老固件不使用
- 来源：<https://github.com/google/brotli> / <https://pypi.org/project/Brotli/>

## 4. OpenSSL（AES 解密加速组件）

- 位置：`bin/win/x86_64/`：`openssl.exe` + `libeay32.dll` + `ssleay32.dll` + `cygwin1.dll`（Cygwin 运行库，openssl 依赖，四件套随包分发）
- 版本：1.0.2u（20 Dec 2019，Windows x64 Cygwin 构建）
- 版权：Copyright (c) 1998-2019 The OpenSSL Project（OpenSSL License + SSLeay License，双许可）
- 用途：OPPO/Realme/OnePlus 固件解密（AES-CFB128/ECB）的首选加速后端；未检测到时自动回落到内置纯 Python 的 `porttool/pyaes/`
- 来源：<https://www.openssl.org/source/>（Windows 构建自 Shining Light Productions，<https://slproweb.com/products/Win32OpenSSL.html>）
- 注：OpenSSL 许可与本项目采用的 GPL-3.0 存在历史兼容性争议（广告条款），本组件随包分发仅为功能加速；因存在纯 Python 兜底（pyaes），使用方若需纯 GPL 合规分发可自行移除本组件，功能不受影响。

## 5. AOSP 工具链（ext4 镜像制作/转换，Apache-2.0）

- 位置与清单：
  - Windows：`bin/win/x86_64/` 下 `e2fsdroid.exe`、`e2fstool.exe`、`ext2simg.exe`、`img2simg.exe`、`make_ext4fs.exe`、`mke2fs.exe`、`simg2img.exe` + `mke2fs.conf`
  - Linux：`bin/linux/aarch64/` 与 `bin/linux/x86_64/` 下 `img2simg`、`make_ext4fs`、`simg2img`
- 版权：Copyright (c) 2007-2015 The Android Open Source Project（Apache License 2.0）
- 用途：system.img 打包（make_ext4fs / mke2fs / e2fsdroid）、ext4/simg 镜像转换（ext2simg / img2simg / simg2img）、ext4 校验修复（e2fstool）
- 来源：<https://android.googlesource.com/platform/external/e2fsprogs/> 等 AOSP 组件构建产物
- 注：AOSP 亦要求随分发附 Apache-2.0 许可证文本（见本文件末尾「The Apache License, Version 2.0」）

## 6. Magisk（magiskboot 引导修补工具，GPL-3.0）

- 位置：`bin/win/x86_64/magiskboot.exe`、`bin/linux/aarch64/magiskboot`、`bin/linux/x86_64/magiskboot`、`bin/update-binary`
- 版权：Copyright (c) 2016-2023 topjohnwu（GPL-3.0）
- 用途：boot.img 解包/重打包（内核、ramdisk、dtb 处理）与 Magisk 修补支持
- 来源：<https://github.com/topjohnwu/Magisk>
- 注：magiskboot 与本项目同为 GPL-3.0，无许可兼容性问题

## 7. Cygwin1.dll（LGPL-3.0，openssl 依赖的 Windows 运行库）

- 位置：`bin/win/x86_64/cygwin1.dll`
- 版权：Copyright (c) 2000-2019 Red Hat, Inc. 及其他贡献者（GNU LGPL-3.0）
- 用途：openssl.exe（Cygwin 构建）运行所需的 POSIX 兼容运行库
- 来源：<https://cygwin.com/>
- 注：LGPL-3.0 允许随商业/闭源程序再分发；本工具以 GPL-3.0 发布，兼容。源码获取见 Cygwin 项目官网

---

## The MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## The Apache License, Version 2.0（AOSP 工具链随附，节选核心条款）

```
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.

"License" shall mean the terms and conditions for use, reproduction,
and distribution as defined by Sections 1 through 9 of this document.

"Licensor" shall mean the copyright owner or entity authorized by
the copyright owner that is granting the License.

"Legal Entity" shall mean the union of the acting entity and all
other entities that control, are controlled by, or are under common
control with that entity.

"You" (or "Your") shall mean an individual or Legal Entity
exercising permissions granted by this License.

"Source" form shall mean the preferred form for making modifications,
including but not limited to software source code, documentation
source, and configuration files.

"Object" form shall mean any form resulting from mechanical
transformation or translation of a Source form, including but
not limited to compiled object code, generated documentation,
and conversions to other media types.

"Work" shall mean the work of authorship, whether in Source or
Object form, made available under the License, as indicated by a
copyright notice that is included in or attached to the work.

"Derivative Works" shall mean any work, whether in Source or Object
form, that is based on (or derived from) the Work and for which the
editorial revisions, annotations, elaborations, or other modifications
represent, as a whole, an original work of authorship.

"Contribution" shall mean any work of authorship, including
the original version of the Work and any modifications or additions
to that Work or Derivative Works thereof, that is intentionally
submitted to Licensor for inclusion in the Work by the copyright owner
or by an individual or Legal Entity authorized to submit on behalf of
the copyright owner.

"Contributor" shall mean Licensor and any individual or Legal Entity
on behalf of whom a Contribution has been received by Licensor and
subsequently incorporated within the Work.

2. Grant of Copyright License. Subject to the terms and conditions of
this License, each Contributor hereby grants to You a perpetual,
worldwide, non-exclusive, no-charge, royalty-free, irrevocable
copyright license to reproduce, prepare Derivative Works of,
publicly display, publicly perform, sublicense, and distribute the
Work and such Derivative Works in Source or Object form.

3. Grant of Patent License. Subject to the terms and conditions of
this License, each Contributor hereby grants to You a perpetual,
worldwide, non-exclusive, no-charge, royalty-free, irrevocable
(except as stated in this section) patent license to make, have made,
use, offer to sell, sell, import, and otherwise transfer the Work,
where such license applies only to those patent claims licensable
by such Contributor that are necessarily infringed by their
Contribution(s) alone or by combination of their Contribution(s)
with the Work to which such Contribution(s) was submitted.

4. Redistribution. You may reproduce and distribute copies of the
Work or Derivative Works thereof in any medium, with or without
modifications, and in Source or Object form, provided that You
meet the following conditions:

(a) You must give any other recipients of the Work or
    Derivative Works a copy of this License; and

(b) You must cause any modified files to carry prominent notices
    stating that You changed the files; and

(c) You must retain, in the Source form of any Derivative Works
    that You distribute, all copyright, patent, trademark, and
    attribution notices from the Source form of the Work,
    excluding those notices that do not pertain to any part of
    the Derivative Works; and

(d) If the Work includes a "NOTICE" text file as part of its
    distribution, then any Derivative Works that You distribute must
    include a readable copy of the attribution notices contained
    within such NOTICE file.

5. Submission of Contributions. Unless You explicitly state otherwise,
any Contribution intentionally submitted for inclusion in the Work
by You to the Licensor shall be under the terms and conditions of
this License, without any additional terms or conditions.

6. Trademarks. This License does not grant permission to use the trade
names, trademarks, service marks, or product names of the Licensor,
except as required for reasonable and customary use in describing the
origin of the Work and reproducing the content of the NOTICE file.

7. Disclaimer of Warranty. Unless required by applicable law or
agreed to in writing, Licensor provides the Work (and each
Contributor provides its Contributions) on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
implied, including, without limitation, any warranties or conditions
of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
PARTICULAR PURPOSE.

8. Limitation of Liability. In no event and under no legal theory,
whether in tort (including negligence), contract, or otherwise,
unless required by applicable law (such as deliberate and grossly
negligent acts) or agreed to in writing, shall any Contributor be
liable to You for damages, including any direct, indirect, special,
incidental, or consequential damages of any character arising as a
result of this License or out of the use or inability to use the
Work.

9. Accepting Warranty or Additional Liability. While redistributing
the Work or Derivative Works thereof, You may choose to offer,
and charge a fee for, acceptance of support, warranty, indemnity,
or other liability obligations and/or rights consistent with this
License. However, in accepting such obligations, You may act only
on Your own behalf and on Your sole responsibility.
```

完整文本见 <http://www.apache.org/licenses/LICENSE-2.0>。
