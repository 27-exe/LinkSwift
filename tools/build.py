#!/usr/bin/env python3
"""
构建发布产物：linkswift.user.js

从上游原始脚本出发，依次做：
  1. 打「aria2 单任务并发数」补丁
  2. 改写元数据（@name/@version/@namespace/@updateURL/@downloadURL …）
  3. 输出为 **纯 ASCII 文件名** linkswift.user.js

为什么要 ASCII 文件名
--------------------
上游文件名是中文「（改）网盘直链下载助手.user.js」，raw URL 必须
percent-encoding（%EF%BC%88…）。实测油猴的「从 URL 安装」对这个 URL
会报「无法从该 URL 加载脚本」/ 404，而同样的地址 curl 能正常取到。
改成纯 ASCII 后 URL 无编码歧义，油猴 / 浏览器 / curl 行为一致。

用法
----
    # 从上游 dev 分支取原始脚本并构建
    git fetch upstream dev
    python3 tools/build.py --upstream upstream/dev

    # 从本地已打过补丁的文件重新构建（改元数据时用）
    python3 tools/build.py --from-local "（改）网盘直链下载助手.user.js"
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

OUT_NAME = "linkswift.user.js"
UPSTREAM_PATH = "（改）网盘直链下载助手.user.js"

OWNER = "27-exe"
REPO = "LinkSwift"
BRANCH = "concurrency"

# 元数据
META = {
    "@name": "LinkSwift 并发版",
    "@namespace": "github.com/27-exe/linkswift-concurrency",
    "@version": "1.1.4-conc.1",
    "@author": "Hmjz100、油小猴（并发补丁：27-exe）",
    "@homepageURL": f"https://github.com/{OWNER}/{REPO}",
    "@homepage": f"https://github.com/{OWNER}/{REPO}",
    "@supportURL": f"https://github.com/{OWNER}/{REPO}/issues",
    "@updateURL": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{OUT_NAME}",
    "@downloadURL": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{OUT_NAME}",
}

HEADER_NOTE = """
// ============================================================================
// 本分支（concurrency）的改动 —— 相对上游 hmjz100/LinkSwift @ dev (v1.1.4)
//
// 1) Aria2 设置弹窗新增「单任务并发数」输入框（data-type="aria2.split"）
// 2) sendLinkToAria2 的 aria2.addUri options 增加 per-task 选项
//      split 与 max-connection-per-server
//
// 为什么需要：网盘直链是「每连接限速」模型 ——
//      UC 网盘   每连接约 100 KB/s
//      夸克网盘  每连接约  10 KB/s
//    总量 ≈ 并发数 × 每连接限速。上游推给 aria2 时不传并发选项，
//    完全依赖 aria2 守护进程的全局配置（split=16 时 UC 只有约 1.5 MB/s）。
//    实测本机：split=384 时 UC 约 37 MB/s（_conns=384_）。
//
// 兼容性：配置项留空 / 填 0 / 填非法值时都不传这两个选项，
//    行为与上游完全一致，退回 aria2 全局配置。
//
// 维护：27-exe · 构建脚本 tools/build.py · 补丁器 tools/apply_linkswift_patch.py
// ============================================================================
"""


def load_patch_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ap", os.path.join(HERE, "apply_linkswift_patch.py"))
    if spec is None or spec.loader is None:
        sys.exit("无法加载 apply_linkswift_patch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_upstream(ref: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{ref}:{UPSTREAM_PATH}"],
        cwd=REPO_ROOT, capture_output=True)
    if out.returncode != 0:
        sys.exit(f"取上游文件失败: {out.stderr.decode()[:300]}")
    return out.stdout.decode("utf-8")


def fix_uc_missing_cookie(text: str) -> tuple[str, int]:
    """补 dev 分支 UC 分支漏传的 Cookie（上游 bug）。

    上游 v1.1.4（dev）重写了 headers 处理，UC 分支给下载器的 headers
    变成 `{UA, Sec-Ch-Ua}` —— **没有 Cookie**。而取链请求是带
    `"Cookie": String(document.cookie)` 的，所以取链成功、直链也拿到了，
    但推给 aria2 后请求不带 Cookie，UC 的 OSS 回调就报
    `RequestDeniedByCallback: require login [auth not found]` → HTTP 403。

    夸克分支没这个问题（它有 `"Cookie": temp.pugs ? cookie : String(document.cookie)`），
    stable（v1.1.3）与增强版用的是另一套 convert 模板，本身就带 Cookie。

    命中 0 处 = 该版本不需要此修复（stable / 增强版），直接跳过。
    """
    old = ('headers: { "User-Agent": config.$uc.api.ua.main, '
           '"Sec-Ch-Ua": config.$uc.api.ua.secCh }')
    new = ('headers: { "User-Agent": config.$uc.api.ua.main, '
           '"Sec-Ch-Ua": config.$uc.api.ua.secCh, '
           '"Cookie": String(document.cookie) }')
    n = text.count(old)
    if n == 0:
        return text, 0
    return text.replace(old, new), n


def rewrite_meta(text: str, version: str | None = None) -> str:
    meta = dict(META)
    if version:
        meta["@version"] = version
    for k, v in meta.items():
        pat = re.compile(r"^\s*//\s*" + re.escape(k) + r"\s+.*$", re.M)
        if pat.search(text):
            text = pat.sub(f"// {k:14} {v}", text, count=1)
        else:
            text = re.sub(r"^(\s*//\s*@version\s+.*)$", r"\1\n// " + k.ljust(14) + " " + v,
                          text, count=1, flags=re.M)
    if HEADER_NOTE.strip() not in text:
        text = text.replace("// ==/UserScript==",
                            "// ==/UserScript==" + HEADER_NOTE, 1)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", default="upstream/dev",
                    help="上游 ref（默认 upstream/dev）")
    ap.add_argument("--from-local", help="从本地文件构建（已打过补丁）")
    ap.add_argument("-o", "--output", default=os.path.join(REPO_ROOT, OUT_NAME))
    ap.add_argument("--version", help="显式指定 @version（如 1.1.4-conc.2）")
    a = ap.parse_args()

    ap_mod = load_patch_module()

    if a.from_local:
        with open(a.from_local, encoding="utf-8") as f:
            text = f.read()
        if 'data-type="aria2.split"' not in text:
            text = ap_mod.apply_patch(text)
        else:
            print("（输入已含补丁，跳过打补丁步骤）")
    else:
        text = fetch_upstream(a.upstream)
        text = ap_mod.apply_patch(text)
        print(f"✓ 已对 {a.upstream} 打并发补丁")

    text, nfix = fix_uc_missing_cookie(text)
    if nfix:
        print(f"✓ 已修补 dev 版 UC 分支漏传的 Cookie（{nfix} 处）")
    else:
        print("· UC 分支 Cookie 正常，无需修补")

    text = rewrite_meta(text, a.version)
    final_version = a.version or META["@version"]

    with open(a.output, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    # 自检
    assert 'data-type="aria2.split"' in text, "缺 split 输入框"
    assert '"max-connection-per-server"' in text, "缺并发选项"
    assert META["@downloadURL"] in text, "@downloadURL 未写入"
    assert final_version in text, "@version 未写入"
    r = subprocess.run(["node", "--check", a.output], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"node --check 失败:\n{r.stderr[:500]}")

    print(f"✓ 构建完成: {a.output}  ({len(text)} 字符, node --check PASS)")
    print(f"  @name        {META['@name']}")
    print(f"  @version     {final_version}")
    print(f"  @downloadURL {META['@downloadURL']}")


if __name__ == "__main__":
    main()
