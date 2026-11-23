#!/usr/bin/env python3
"""
给 LinkSwift 打「aria2 单任务并发数」补丁。

用法:
    python3 apply_linkswift_patch.py <原始.user.js> [-o <输出.user.js>]

改动两处:
  1. Aria2 设置弹窗加一个输入框 data-type="aria2.split"
     （存储/回填是 LinkSwift 的通用机制，无需额外代码）
  2. sendLinkToAria2 的 aria2.addUri options 加 split 与
     max-connection-per-server

兼容两个上游变体:
  v1  main / 稳定版 v1.1.3 —— params: [`token:${rpc.token}`, [link], {dir,out,header}]
  v2  dev / v1.1.4        —— params: [[link], {...spread..., header: header_parts}]

兼容性: 老配置没有 split 字段时读不到就不传这两个选项，行为与改前完全一致；
填 0 / 留空 / 非法值 = 用 aria2 全局配置。

锚点必须唯一命中，否则报错退出 —— 不做模糊匹配，避免改错地方。
"""

import argparse
import re
import sys

# --- 改动 1 锚点：设置弹窗里 aria2.dir 所在的 label 块 ---
# main:  <label class="pl-setting-item">
# dev :  <label class="${mount} setting-item">
#
# 行尾用 \r?\n 兼容：上游 .gitattributes 规定 `* text eol=crlf`，
# 所以工作副本是 CRLF，而 raw 下载的是 LF —— 两种都要能匹配。
FORM_RE = re.compile(
    r'(\t\t\t\t<label class="[^"]*setting-item">\r?\n'
    r'\t+<div>存储路径</div>\r?\n'
    r'\t+<input[^>]*data-type="aria2\.dir"[^>]*>\r?\n'
    r'\t+</label>)'
)

# --- 改动 2 锚点：aria2.addUri 的 options 里的 header 行 ---
# main: \t\t\t\t\t\theader: headers
# dev : \t\t\t\t\t\theader: header_parts
HEADER_RE = re.compile(r'(\t\t\t\t\t\theader: (?:headers|header_parts)\r?\n)')

SPLIT_BLOCK = """\t\t\t\t\t\t// 单任务并发数：留空/0/非法值时不传，退回 aria2 全局配置。
\t\t\t\t\t\t// 网盘直链是「每连接限速」模型（UC ~100KB/s，夸克 ~10KB/s），
\t\t\t\t\t\t// 总量 ≈ 并发数 × 每连接限速，所以并发是唯一的加速杠杆。
\t\t\t\t\t\t// 用 per-task 选项而非改全局配置，其他任务的并发不受影响。
\t\t\t\t\t\t...(function () {
\t\t\t\t\t\t\tlet s = parseInt(selected.split, 10);
\t\t\t\t\t\t\treturn (Number.isFinite(s) && s > 0)
\t\t\t\t\t\t\t\t? { split: String(s), "max-connection-per-server": String(s) }
\t\t\t\t\t\t\t\t: {};
\t\t\t\t\t\t})(),
"""


def build_new_form(m: re.Match) -> str:
    """在原 label 块后追加一个「单任务并发数」输入框。"""
    old = m.group(1)
    mount = re.search(r'<label class="([^"]*)"', old).group(1)
    if "mount" in mount:
        cls = f"{mount} input swal2-input listener-rpc-input"
    else:
        cls = "swal2-input pl-input listener-rpc-input"
    new = f"""				<label class="{mount}">
					<div>单任务并发数</div>
					<input type="number" autocomplete="off" min="1" max="1024" placeholder="留空=全局；UC 384，夸克 1024" class="{cls}" data-type="aria2.split" value="">
				</label>"""
    return old + new


def detect_eol(text: str) -> str:
    """检测文件主行尾。插入的内容必须跟随，避免混合行尾。"""
    return "\r\n" if "\r\n" in text else "\n"


def apply_patch(text: str) -> str:
    if 'data-type="aria2.split"' in text:
        raise SystemExit("脚本已经打过补丁了。")

    forms = FORM_RE.findall(text)
    if len(forms) != 1:
        raise SystemExit(
            f"设置弹窗锚点匹配 {len(forms)} 次（应为 1）。\n"
            f"LinkSwift 版本可能已变，请人工合并。")

    headers = HEADER_RE.findall(text)
    if len(headers) != 1:
        raise SystemExit(
            f"sendLinkToAria2 锚点匹配 {len(headers)} 次（应为 1）。\n"
            f"LinkSwift 版本可能已变，请人工合并。")

    eol = detect_eol(text)
    split_block = SPLIT_BLOCK.replace("\n", eol)

    text = FORM_RE.sub(
        lambda m: build_new_form(m).replace("\n", eol), text, count=1)
    text = HEADER_RE.sub(lambda m: split_block + m.group(1), text, count=1)

    # 自检
    assert 'data-type="aria2.split"' in text, "缺 split 输入框"
    assert '"max-connection-per-server"' in text, "缺并发选项"
    assert text.count('aria2.split') >= 1
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="原始 .user.js")
    ap.add_argument("-o", "--output", help="输出 .user.js（默认原地覆盖）")
    a = ap.parse_args()

    with open(a.src, encoding="utf-8") as f:
        text = f.read()

    out = apply_patch(text)
    dst = a.output or a.src
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"已打补丁: {dst}  ({len(text)} -> {len(out)} 字符)")
    print("改动 1: 设置弹窗新增「单任务并发数」输入框")
    print("改动 2: aria2.addUri options 加 split / max-connection-per-server")
    print("用法: 脚本菜单 → 设置 → Aria2 服务器 → 配置 → 填并发数")


if __name__ == "__main__":
    main()
