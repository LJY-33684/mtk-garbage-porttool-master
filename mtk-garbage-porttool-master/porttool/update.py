# update.py — 更新检查功能模块（网络请求、版本解析、内容拉取、markdown 渲染）
# 由 ui.py 调用，ui.py 只负责窗口与交互
import urllib.request
import json
import base64
import re
import webbrowser
from tkinter import END

# 更新源配置
UPDATE_SOURCES = {
    'GitHub': {
        'raw': 'https://raw.githubusercontent.com/LJY-33684/mtk-garbage-porttool-master/main/latest_version.txt',
        'api': 'https://api.github.com/repos/LJY-33684/mtk-garbage-porttool-master/releases/tags/{tag}',
        'contents_api': 'https://api.github.com/repos/LJY-33684/mtk-garbage-porttool-master/contents/latest_version.txt',
        'notes_api': 'https://api.github.com/repos/LJY-33684/mtk-garbage-porttool-master/contents/update_notes/{tag}.md',
        'url_key': 'update_url_1',
    },
    'Gitee': {
        'raw': 'https://gitee.com/Q3368436451/mtk-garbage-porttool-master/raw/main/latest_version.txt',
        'api': 'https://gitee.com/api/v5/repos/Q3368436451/mtk-garbage-porttool-master/releases/tags/{tag}',
        'notes_api': 'https://gitee.com/api/v5/repos/Q3368436451/mtk-garbage-porttool-master/contents/update_notes/{tag}.md',
        'url_key': 'update_url_2',
    },
}
UPDATE_TIMEOUT = 30  # 秒
_UA = "MTK-PortTool"


class UpdateResult:
    """更新检查结果对象（线程安全，只读数据）"""
    __slots__ = ('ok', 'tag', 'body', 'download_url', 'reason')

    def __init__(self, ok=False, tag=None, body='', download_url=None, reason=''):
        self.ok = ok
        self.tag = tag
        self.body = body
        self.download_url = download_url
        self.reason = reason


def fetch_update_info(source, timeout=UPDATE_TIMEOUT):
    """线程安全：请求对应源 latest_version.txt + 更新内容（markdown）。

    返回 UpdateResult：
      ok=True  时 tag/body/download_url 有效
      ok=False 时 reason 为失败原因
    """
    src_cfg = UPDATE_SOURCES.get(source, UPDATE_SOURCES['GitHub'])
    result = UpdateResult()
    try:
        # 1. 请求对应源的 latest_version.txt
        # GitHub 优先用 contents API（无 CDN 缓存，修改后立即可见），失败降级 raw
        raw = None
        if source == 'GitHub' and 'contents_api' in src_cfg:
            try:
                req_c = urllib.request.Request(src_cfg['contents_api'], headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req_c, timeout=timeout) as resp_c:
                    file_data = json.loads(resp_c.read().decode("utf-8"))
                    raw = base64.b64decode(file_data['content']).decode("utf-8-sig")
            except Exception:
                raw = None
        if raw is None:
            req = urllib.request.Request(src_cfg['raw'], headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
            result.reason = "版本信息格式错误"
        else:
            # 选择对应源的下载链接
            download_url = all_urls.get(src_cfg['url_key']) or all_urls.get('update_url')
            # 3. 获取更新内容：优先仓库内 update_notes/{tag}.md（contents API 通道，与 latest_version.txt 同链路），失败降级 releases API
            body = fetch_release_body(src_cfg, tag, timeout)
            result.ok = True
            result.tag = tag
            result.body = body
            result.download_url = download_url

    except Exception as e:
        err_str = str(e).lower()
        if "timed out" in err_str or "timeout" in err_str:
            result.reason = "网络超时"
        else:
            result.reason = f"网络错误: {e}"
    return result


def fetch_release_body(src_cfg, tag, timeout=UPDATE_TIMEOUT):
    """获取更新内容（markdown）：notes_api -> releases API -> 兜底提示"""
    body = ""
    try:
        notes_url = src_cfg.get('notes_api', '').format(tag=tag)
        if notes_url:
            req_n = urllib.request.Request(notes_url, headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req_n, timeout=timeout) as resp_n:
                notes_data = json.loads(resp_n.read().decode("utf-8"))
                body = base64.b64decode(notes_data['content']).decode("utf-8-sig").strip()
    except Exception:
        body = ""
    if not body:
        try:
            api_url = src_cfg['api'].format(tag=tag)
            req2 = urllib.request.Request(api_url, headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                release_data = json.loads(resp2.read().decode("utf-8"))
                body = release_data.get("body", "") or ""
        except Exception:
            pass
    if not body:
        body = f"## {tag}\n\n更新内容获取失败，请前往下载页面查看详情。"
    return body


def render_markdown(text_widget, markdown_text):
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
            _insert_inline(text_widget, content)
            text_widget.insert(END, '\n')
            continue
        if re.match(r'^\d+\.\s+', stripped):
            content = re.sub(r'^\d+\.\s+', '', stripped)
            text_widget.insert(END, stripped.split('.')[0] + '. ', 'list')
            _insert_inline(text_widget, content)
            text_widget.insert(END, '\n')
            continue

        # 普通行（处理内联格式）
        if stripped:
            _insert_inline(text_widget, stripped)
        text_widget.insert(END, '\n')


def _insert_inline(text_widget, text):
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
                tag_name = f"link_{id(url)}"
                text_widget.insert(END, label, tag_name)
                text_widget.tag_bind(tag_name, '<Button-1>', lambda e, u=url: webbrowser.open(u))
            else:
                text_widget.insert(END, part)
        else:
            text_widget.insert(END, part)
