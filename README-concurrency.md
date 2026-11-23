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

油猴里直接打开这个链接安装：

```
https://raw.githubusercontent.com/27-exe/LinkSwift/concurrency/%EF%BC%88%E6%94%B9%EF%BC%89%E7%BD%91%E7%9B%98%E7%9B%B4%E9%93%BE%E4%B8%8B%E8%BE%85%E5%8A%A9.user.js
```

`@updateURL` / `@downloadURL` 已指向本仓库的 `concurrency` 分支，
**油猴会自动更新**。

> 脚本 `@name` 改成了「LinkSwift 并发版」、`@namespace` 改成了
> `github.com/27-exe/linkswift-concurrency` —— 与上游脚本在油猴里是
> 两个独立条目，不会互相覆盖。要换回上游版，卸载这个再装上游即可。

## 仓库结构

```
concurrency/                       ← 本分支
├── （改）网盘直链下载助手.user.js  ← 打好补丁的脚本（主产物）
├── （改）百度网盘会员青春版.user.js
└── tools/
    ├── apply_linkswift_patch.py   ← 补丁器（幂等，锚点不唯一则报错退出）
    └── README.md
```

## 维护

### 同步上游更新

```bash
git fetch upstream dev
git rebase upstream/dev          # 或 git merge upstream/dev
python3 tools/apply_linkswift_patch.py "（改）网盘直链下载助手.user.js"
node --check "（改）网盘直链下载助手.user.js"
```

补丁器**锚点必须唯一命中**，否则直接报错退出、不做模糊匹配 —— 上游改了
结构也不会把脚本改坏，只会要求人工合并。

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
