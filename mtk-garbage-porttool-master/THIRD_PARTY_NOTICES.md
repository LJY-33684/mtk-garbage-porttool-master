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
