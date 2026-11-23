// 验证 LinkSwift 并发补丁的行为
// 1) 复刻补丁后的 options 构造逻辑，检查各种输入
// 2) 用生成的 options 真打 aria2，看 connections 是否生效

const http = require("http");

// —— 补丁后的逻辑（与 LinkSwift-并发版.user.js 中的代码一致）——
function buildOptions(selected, dir, out, headers) {
	const o = {
		dir,
		out: filename_or(out),
		header: headers,
		...(function () {
			let s = parseInt(selected.split, 10);
			return (Number.isFinite(s) && s > 0)
				? { split: String(s), "max-connection-per-server": String(s) }
				: {};
		})()
	};
	return o;
}
function filename_or(x) { return x; }

function rpc(method, params) {
	return new Promise((resolve, reject) => {
		const body = JSON.stringify({ jsonrpc: "2.0", id: "1", method, params });
		const req = http.request({
			host: "127.0.0.1", port: 6800, path: "/jsonrpc", method: "POST",
			headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
		}, (res) => {
			let d = "";
			res.on("data", (c) => (d += c));
			res.on("end", () => { try { resolve(JSON.parse(d).result); } catch (e) { reject(e); } });
		});
		req.on("error", reject);
		req.end(body);
	});
}

(async () => {
	console.log("=== 1. options 构造逻辑 ===");
	const cases = [
		["填 384", { split: "384" }],
		["填 1024", { split: "1024" }],
		["留空", {}],
		["填 0", { split: "0" }],
		["填非法值 abc", { split: "abc" }],
	];
	for (const [label, sel] of cases) {
		const o = buildOptions(sel, "/tmp/x", "a.zip", ["UA: test"]);
		const extra = o.split ? `split=${o.split} max-conn=${o["max-connection-per-server"]}` : "(不传，用全局)";
		console.log(`  ${label.padEnd(16)} -> ${extra}`);
	}

	console.log("\n=== 2. 真打 aria2（全局 split=16 不动）===");
	const url = process.argv[2];
	const cookie = process.argv[3];
	if (!url) { console.log("缺少直链参数，跳过"); return; }

	const sel = { split: process.argv[4] || "384" };
	const o = buildOptions(sel, "/home/a27exe/Downloads/_vtest", "v.zip",
		[`User-Agent: Mozilla/5.0`, `Referer: https://drive.uc.cn/`, `Cookie: ${cookie}`]);

	const gid = await rpc("aria2.addUri", [[url], o]);
	console.log(`  addUri gid=${gid}  传入 split=${o.split}`);
	for (const wait of [6000, 8000, 8000]) {
		await new Promise((r) => setTimeout(r, wait));
		const st = await rpc("aria2.tellStatus", [gid]);
		console.log(`  conns=${st.connections}  speed=${(st.downloadSpeed / 1048576).toFixed(2)} MB/s  ` +
			`done=${(st.completedLength / 1048576).toFixed(1)} MB  err=${st.errorCode || "-"}`);
		if (st.errorCode) break;
	}
	await rpc("aria2.forceRemove", [gid]);
	console.log("  已清理测试任务");
})();
