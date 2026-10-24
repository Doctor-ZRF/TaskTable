#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把他的 0.1.6（含新 UI/快捷键）+ 我的补丁合成 0.1.7-local"""
import os, re, shutil, subprocess, sys

TMP   = r"C:/Users/16542/AppData/Local/Temp/tt_merge"
HIS   = r"C:/Users/16542/AppData/Local/Temp/tt_cmp/his"          # 他解包后的 app
MINE  = r"D:/Desktop/TaskTable-0.1.6-win-x64/resources/app"      # 我的补丁版 app
BUILD = r"D:/Desktop/TaskTable-0.1.7-build"                       # 输出（整个程序目录）
VERSION = "0.1.7-local"

# ---------- 1. 用他的程序目录做骨架 ----------
if os.path.isdir(BUILD):
    shutil.rmtree(BUILD)
shutil.copytree(r"D:/Desktop/TaskTable_temp/TaskTable-0.1.6-win-x64", BUILD)
res = os.path.join(BUILD, "resources")
app = os.path.join(res, "app")
if os.path.isfile(os.path.join(res, "app.asar")):
    os.rename(os.path.join(res, "app.asar"), os.path.join(res, "app.asar.his-0.1.6.bak"))
shutil.copytree(HIS, app)          # 散开他的 app
print("[1] 骨架 = 他的 0.1.6，app 已散开")

# ---------- 2. main.cjs / preload.cjs 用三方合并结果 ----------
for f in ("main.cjs", "preload.cjs"):
    src = os.path.join(TMP, "merged." + f if f == "main.cjs" else "merged.preload.cjs")
    src = os.path.join(TMP, "merged." + f)
    with open(src, encoding='utf-8', newline='') as fh:
        txt = fh.read()
    assert "<<<<<<<" not in txt, f"{f} 还有冲突"
    with open(os.path.join(app, "desktop", f), 'w', encoding='utf-8', newline='') as fh:
        fh.write(txt.replace('\n', '\r\n'))
print("[2] main.cjs / preload.cjs = 三方合并结果（两边功能都在）")

# ---------- 3. 给渲染层打补丁（用他的别名）----------
src_js = os.path.join(TMP, "his.beauty.js")
s = open(src_js, encoding='utf-8').read()

def sub_once(old, new, label):
    global s
    n = s.count(old)
    assert n == 1, f"{label}: 锚点命中 {n} 次"
    s = s.replace(old, new, 1)
    print(f"     ✓ {label}")

LOAD_PREFIX = '''
 try {
  if (window.desktop && window.desktop.store) {
   const __f = await window.desktop.store.load();
   if (!window.__ttPathLogged && __f && __f.file) {
    window.__ttPathLogged = 1, console.log("[tasktable] 数据文件：" + __f.file);
   }
   if (__f && __f.ok) {
    if (__f.data && Array.isArray(__f.data.tasks)) return __f.data;
    const __fileEmpty = __f.data === null, __cleared = !!__f.cleared;
    if (localStorage.getItem("tasktable:filemigrated") === "1" && !(__fileEmpty && !__cleared)) return null;
   } else {
    console.warn("[tasktable] 数据文件读取失败，回退 IndexedDB", __f && __f.error);
   }
  }
 } catch (__e) {
  console.warn("[tasktable] 文件后端异常，回退 IndexedDB", __e);
 }
'''
SAVE_PREFIX = '''
 try {
  if (window.desktop && window.desktop.store) {
   const __r = await window.desktop.store.save(s);
   if (__r && __r.ok) {
    __r.conflict && console.warn("[tasktable] 别处也改过数据文件，已留档：" + __r.conflict),
    __r.mergedRemote > 0 && console.warn("[tasktable] 已从别处合并进 " + __r.mergedRemote + " 条任务（重启后完整可见）");
    return;
   }
   console.warn("[tasktable] 数据文件写入失败，回退 IndexedDB", __r && __r.error);
  }
 } catch (__e) {
  console.warn("[tasktable] 文件后端异常，回退 IndexedDB", __e);
 }
'''
CLEAR_PREFIX = '''
 try {
  if (window.desktop && window.desktop.store) {
   const __r = await window.desktop.store.del();
   if (__r && __r.ok) return;
  }
 } catch (__e) {
  console.warn("[tasktable] 数据文件删除失败", __e);
 }
'''
HELPERS = '''
function __ttMergeStates(local, remote) {
 if (!remote || !Array.isArray(remote.tasks)) return local;
 const m = new Map;
 for (const t of remote.tasks) { if (t && t.id) m.set(t.id, t); }
 for (const t of (Array.isArray(local.tasks) ? local.tasks : [])) {
  if (!t || !t.id) continue;
  const q = m.get(t.id);
  if (q) { m.set(t.id, (Number(q.lastTouchedAt) || 0) > (Number(t.lastTouchedAt) || 0) ? q : t); } else { m.set(t.id, t); }
 }
 const out = { ...remote, ...local };
 out.tasks = [ ...m.values() ].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
 const r = new Map;
 for (const x of (Array.isArray(remote.reminders) ? remote.reminders : [])) { if (x && x.id) r.set(x.id, x); }
 for (const x of (Array.isArray(local.reminders) ? local.reminders : [])) { if (x && x.id && !r.has(x.id)) r.set(x.id, x); }
 out.reminders = [ ...r.values() ];
 return out;
}

async function __ttReload() {
 try {
  if (!window.desktop || !window.desktop.store) return { ok: !1, msg: "没有文件后端" };
  const r = await window.desktop.store.load();
  if (!r || !r.ok) return { ok: !1, msg: String((r && r.error) || "读取失败") };
  if (!r.data || !Array.isArray(r.data.tasks)) return { ok: !1, msg: r.data ? "文件里没有 tasks" : "数据文件还不存在" };
  const cur = _t && Array.isArray(_t.tasks) ? _t : null, before = cur ? cur.tasks.length : 0;
  const merged = cur ? __ttMergeStates(cur, r.data) : r.data;
  V.replaceState(merged);
  const total = (merged.tasks || []).length;
  return { ok: !0, added: Math.max(0, total - before), total };
 } catch (e) {
  return { ok: !1, msg: String((e && e.message) || e) };
 }
}

function __ttReloadClick(ev) {
 const b = ev && ev.currentTarget;
 if (b) { try { b.textContent = "读取中…"; } catch (_) {} }
 __ttReload().then(r => {
  if (!b) return;
  try {
   b.textContent = r.ok ? (r.added > 0 ? "已同步 +" + r.added : "已是最新") : "读取失败";
   setTimeout(() => { try { b.textContent = "↻ 同步"; } catch (_) {} }, 1800);
  } catch (_) {}
 });
}

function __ttLogTime(f) {
 const r = new Date(f), m = new Date;
 if (r.getFullYear() === m.getFullYear() && r.getMonth() === m.getMonth() && r.getDate() === m.getDate()) return po(f);
 return oc(f);
}

function __TTLogs({ logs }) {
 const [open, setOpen] = B.useState(!1);
 if (!Array.isArray(logs) || logs.length === 0) return null;
 const sorted = logs.slice().sort((a, b) => (Number(b.at) || 0) - (Number(a.at) || 0)), last = sorted[0] || {};
 const stop = e => { e.stopPropagation(); };
 return c.jsxs("div", { className: "tt-logs", onClick: stop, children: [
  c.jsxs("button", { type: "button", className: "tt-logs-toggle", title: open ? "收起进展记录" : "展开全部进展记录",
   onClick: e => { stop(e), setOpen(o => !o); }, children: [
   c.jsx("span", { className: "chv", children: open ? "▾" : "▸" }),
   c.jsxs("span", { className: "cnt", children: [ "进展 ", logs.length ] }),
   !open && c.jsx("span", { className: "prev", title: __ttLogTime(last.at) + " · " + (last.text || ""), children: last.text })
  ] }),
  open && c.jsx("div", { className: "tt-log-list", children: sorted.map(x => c.jsxs("div", { className: "tt-log-entry", children: [
   c.jsx("span", { className: "t", children: __ttLogTime(x.at) }),
   c.jsx("span", { className: "x", children: x.text })
  ] }, x.id)) })
 ] });
}

function __TTDataPath() {
 const [info, setInfo] = B.useState(null);
 B.useEffect(() => {
  let a = !0;
  try { window.desktop && window.desktop.store && window.desktop.store.path && window.desktop.store.path().then(r => { a && setInfo((r && r.file) || ""); }).catch(() => {}); } catch (_) {}
  return () => { a = !1; };
 }, []);
 const open = () => { try { window.desktop && window.desktop.store && window.desktop.store.reveal(); } catch (_) {} };
 return c.jsx(ot, { label: "数据文件", sub: info || "读取中…", control: c.jsx(vt, { variant: "tinted", size: "sm", onClick: open, children: "打开文件夹" }) });
}
'''

print("[3] 渲染层补丁")
sub_once('async function Kg() {', 'async function Kg() {' + LOAD_PREFIX, 'Kg 读：文件后端优先 + 迁移闸门')
sub_once('  if (o) return o;', '  if (o) {\n   try {\n    if (window.desktop && window.desktop.store) {\n     window.desktop.store.save(o).then(() => localStorage.setItem("tasktable:filemigrated", "1"));\n     console.log("[tasktable] 已把 IndexedDB 里的旧数据导出成数据文件");\n    }\n   } catch (__e) {}\n   return o;\n  }', 'Kg：旧库数据自动导出')
sub_once('async function gv(s) {', 'async function gv(s) {' + SAVE_PREFIX, 'gv 写：文件后端优先')
sub_once('async function Jg() {', 'async function Jg() {' + CLEAR_PREFIX, 'Jg 清空：删文件')
sub_once('const rc = [ {', HELPERS + '\nconst rc = [ {', '插入 6 个辅助函数')
sub_once('}), p && c.jsxs("div", {\n    className: "log-input",', '}), c.jsx(__TTLogs, { logs: s.logs }), p && c.jsxs("div", {\n    className: "log-input",', '卡片：插入进展折叠行')
sub_once('c.jsx("div", {\n    className: "navbar-right",', 'c.jsx(vt, { variant: "plain", size: "sm", title: "重新读取数据文件 —— 另一台电脑同步过来以后点一下", onClick: __ttReloadClick, children: "↻ 同步" }), c.jsx("div", {\n    className: "navbar-right",', '导航栏：插入 ↻ 同步（保留他的中央圆钮）')
sub_once('footer: "数据只存在这台机器的浏览器里（IndexedDB），不上传任何服务器。换机器或重装前记得导出。",',
         'footer: "数据存在用户目录，每台电脑一份，不进程序目录（所以程序可以整包传 GitHub）。多机同步就把这个 data 文件夹加进绿联云同步任务；要换位置：在 %APPDATA%\\\\TaskTableData\\\\data-path.txt 写一行新路径。",',
         '设置页：更新数据说明')
sub_once('children: [ c.jsx(ot, {\n    label: "当前数据量",', 'children: [ c.jsx(__TTDataPath, {}), c.jsx(ot, {\n    label: "当前数据量",', '设置页：插入数据文件行')
cnt = s.count('children: [ "v", "0.1.6" ]')
assert cnt >= 1, "版本号锚点没找到"
s = s.replace('children: [ "v", "0.1.6" ]', 'children: [ "v", "%s" ]' % VERSION)
print(f"     ✓ 版本号 → {VERSION}（{cnt} 处）")

patched = os.path.join(TMP, "his.patched.js")
open(patched, 'w', encoding='utf-8').write(s)

# ---------- 4. 压缩回去 ----------
os.makedirs(os.path.join(app, "dist", "assets"), exist_ok=True)
out_js = os.path.join(TMP, "index-merged.js")
r = subprocess.run(["node", os.path.join(TMP, "node_modules/terser/bin/terser"), patched,
                    "-c", "-m", "-o", out_js], capture_output=True, text=True)
print("[4] terser:", "OK" if r.returncode == 0 else r.stderr[:300], "→", os.path.getsize(out_js), "字节")

# ---------- 5. CSS ----------
his_css_file = [f for f in os.listdir(os.path.join(app, "dist", "assets")) if re.match(r"index-.*\.css$", f)][0]
css = open(os.path.join(app, "dist", "assets", his_css_file), encoding='utf-8', newline='').read()
mine_css = open(os.path.join(MINE, "dist", "assets", "index-Caf03dXQ.css"), encoding='utf-8', newline='').read()
marker = "/* 0.1.6-local 补丁：卡片内可展开的进展记录 */"
tt_block = mine_css[mine_css.find(marker):]
single_col = "@media(max-width:60rem){.worksheet{display:block}.col-matrix{margin-top:var(--sp-5)}}"
css_out = (css.rstrip('\n') + "\n" + tt_block.replace('0.1.6-local', '0.1.7-local') + "\n"
           + "/* 他的 .row-body 是横向 flex（标题+倒计时并排），进展行必须独占一整行 */\n"
           + ".row-body{flex-wrap:wrap}\n"
           + ".tt-logs{flex:0 0 100%;width:100%}\n"
           + single_col + "\n")
css_name = "index-merged.css"
open(os.path.join(app, "dist", "assets", css_name), 'w', encoding='utf-8', newline='').write(css_out)
print("[5] CSS 追加完成:", len(css_out), "字节（头像/卡片挤压规则没加：他新结构用 row-title/row-remain，已不需要）")

# ---------- 6. index.html / 清理旧资源 / package.json ----------
idx = os.path.join(app, "dist", "index.html")
html = open(idx, encoding='utf-8').read()
html = re.sub(r'/assets/index-[\w-]+\.js', '/assets/index-merged.js', html)
html = re.sub(r'/assets/index-[\w-]+\.css', '/assets/index-merged.css', html)
open(idx, 'w', encoding='utf-8').write(html)
for f in [his_css_file] + [x for x in os.listdir(os.path.join(app, "dist", "assets")) if re.match(r"index-[A-Za-z0-9]+\.js$", x)]:
    if f not in ("index-merged.js", "index-merged.css"):
        os.remove(os.path.join(app, "dist", "assets", f))
shutil.copy(out_js, os.path.join(app, "dist", "assets", "index-merged.js"))
pkg = os.path.join(app, "package.json")
j = open(pkg, encoding='utf-8').read()
j = re.sub(r'"version":\s*"[^"]*"', '"version": "%s"' % VERSION.split('-')[0], j)
open(pkg, 'w', encoding='utf-8').write(j)
print("[6] index.html 指向 index-merged.js/css，旧资源已删，package.json →", VERSION.split('-')[0])
print("\nDONE →", BUILD)
