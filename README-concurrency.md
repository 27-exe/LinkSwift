# LinkSwift 并发版（27-exe）

[LinkSwift](https://github.com/hmjz100/LinkSwift) 的 fork，增加 **aria2 单任务并发数** 设置。

上游作者：Hmjz100、油小猴 · 许可：AGPL-3.0-or-later · 本分支仅新增并发相关改动。

## 为什么需要这个改动

网盘分享直链是**「每连接限速」**模型：

| 网盘 | 每连接限速 | 合理并发 | 实测峰值 |
|---|---|---|---|
| UC (`drive.uc.cn`) | ~100 KB/s | 256–384 | **37–38 MB/s** |
| 夸克 (`pan.quark.cn`) | ~10 KB/s | 512–1024 | ~9 MB/s |

总量 ≈ 并发数 × 每连接限速。而上游 `sendLinkToAria2` 只给 aria2 传
`dir` / `out` / `header`，**不传并发选项**，所以并发完全由 aria2 守护进程的
全局配置决定（`split=16` 时 UC 只有约 1.5 MB/s）。

上游 issue #253「获取RPC后通过motrix下载发现速度很慢，大概100kb」作者回复
「没办法，我都是是忍着的」—— 他把限速归因于网盘侧。实际上 aria2 侧是可以
补的，本分支就是那个补丁。

## 改动内容（两处）

### 1. 设置弹窗新增「单任务并发数」

脚本菜单 → ⚙️ 设置 → **Aria2 服务器** → 配置 → 「单任务并发数」

- **UC 填 384**，**夸克填 1024**
- 留空 / 填 0 / 填非法值 → 不传并发选项，**行为与上游完全一致**，
  退回 aria2 全局配置

存储和回填无需额外代码：LinkSwift 的机制是通用的
（`data("type").split(".")[1]`）。

### 2. `aria2.addUri` 的 options 增加 per-task 选项

```js
...(function () {
    let s = parseInt(selected.split, 10);
    return (Number.isFinite(s) && s > 0)
        ? { split: String(s), "max-connection-per-server": String(s) }
        : {};
})()
```

用 **per-task 选项**而不是改 aria2 全局配置 —— 你的 aria2 守护进程可能还要
跑其他负载，那些任务不该被提并发。

> **两个键必须一起给**：`max-connection-per-server` 是单服务器硬上限，优先级
> 高于 `split`。只给 `split` 会被它压回去（实测 `split=384` + `x=16`
> → 实际只有 16 条连接）。

## 安装

油猴里直接打开这个链接安装（**纯 ASCII 文件名，无编码歧义**）：

```
https://raw.githubusercontent.com/27-exe/LinkSwift/concurrency/linkswift.user.js
```

`@updateURL` / `@downloadURL` 已指向同一地址，**油猴会自动更新**。

> 上游的文件名是中文「（改）网盘直链下载助手.user.js」，raw URL 必须
> percent-encoding。实测油猴的「从 URL 安装」对那种 URL 会报
> 「无法从该 URL 加载脚本」/ 404（同样地址 curl 能正常取到）。
> 所以发布产物统一用 ASCII 名 `linkswift.user.js`。
>
> 脚本 `@name` 是「LinkSwift 并发版」、`@namespace` 是
> `github.com/27-exe/linkswift-concurrency` —— 与上游脚本在油猴里是
> 两个独立条目，不会互相覆盖。要换回上游版，卸载这个再装上游即可。

## 仓库结构

```
concurrency/                       ← 本分支
├── linkswift.user.js              ← 发布产物（唯一事实源，ASCII 文件名）
├── README-concurrency.md          ← 本文件
└── tools/
    ├── build.py                   ← 构建脚本：取上游 → 打补丁 → 改元数据 → 输出
    ├── apply_linkswift_patch.py   ← 补丁器（幂等，锚点不唯一则报错退出）
    ├── verify_patch.js            ← 行为验证脚本
    └── .gitignore
```

**发布产物不入库上游原名文件** —— 它由 `tools/build.py` 从
`upstream/dev` 现场生成，避免两份副本不同步。

## 维护

### 同步上游更新

```bash
git fetch upstream dev
python3 tools/build.py --upstream upstream/dev   # 打补丁 + 改元数据 + node --check
git add linkswift.user.js
git commit -m "同步上游 dev" && git push origin concurrency
```

不需要 rebase —— `concurrency` 分支与 `upstream/dev` 各自独立演进，
只通过 `build.py` 传递内容。

### 补丁器覆盖的两个上游变体

| 变体 | `sendLinkToAria2` 的 options 结构 |
|---|---|
| `main` / v1.1.3 | `params: [\`token:${rpc.token}\`, [link], {dir, out, header}]` |
| `dev` / v1.1.4 | `params: [[link], {...spread..., out, header: header_parts}]` |

## 已验证

- `node --check` 语法 PASS
- options 构造：填数字→带上；留空/0/非法→不传（四种输入逐一验证）
- 真打 aria2：`conns=384`、`38.01 MB/s`，**全局 `split=16` 未被改动**

## 致谢与许可

本仓库是 [LinkSwift](https://github.com/hmjz100/LinkSwift) 的 fork，
原作者 Hmjz100、油小猴，遵循 **AGPL-3.0-or-later**。
本分支仅新增上述并发相关改动，上游代码版权归原作者所有。
