# 改动清单（相对于原版 0.1.5 构建产物）

这份文件是给**原作者 / 想把它合进源码的人**看的：本仓库是在构建产物上打的补丁，
所以这里逐个说明改了哪里、原代码长什么样、建议在源码里怎么落。

> 说明：`resources/app/desktop/*.cjs` 本来就是未压缩源码，可以逐行对照；
> `resources/app/dist/assets/index-*.js` 是 Vite 打包后的**压缩产物**，下面的锚点是压缩后的原始片段，
> 在源码工程里应还原成对应的组件 / 函数。

---

## 一、数据层（新功能，原版没有）

### 1. `desktop/main.cjs`

| 新增 | 作用 |
|---|---|
| `configDir()` | 返回 `%APPDATA%\TaskTableData`。**不能叫 `TaskTable`** —— Windows 路径不区分大小写，会和 Electron 自己的 userData 目录 `%APPDATA%\tasktable` 撞成同一个。 |
| `readPathFile(file)` / `defaultDataFile()` / `dataFilePath()` | 数据文件路径解析。优先级：`TASKTABLE_DATA_FILE` > `%APPDATA%\TaskTableData\data-path.txt` > `<exe目录>\data-path.txt`（旧版兼容）> 默认 `%APPDATA%\TaskTableData\data\state.json`。 |
| `migrateLegacyAppData()` | 首次启动把旧位置 `<exe目录>\data\state.json` 复制到新位置，并把旧目录改名 `data.migrated-<时间戳>`。目标已存在时不动。 |
| `sha256()` + `knownHash` | 记录上次读到的文件指纹，用于发现「别的机器改过这个文件」。 |
| `storeLoad()` | 读文件；返回 `{ ok, file, data, missing, cleared }`。`cleared` = 目录里有没有 `state.json.deleted-*`（用户主动清空过的痕迹，避免自动复活）。 |
| `storeSave(data)` | **原子写**：写 `state.json.tmp`（命中 Syncthing 默认的 `*.tmp` 忽略规则）→ `renameSync` 覆盖。写前比对 hash，不一致则先把对方版本留档为 `state.conflict-<hostname>-<ISO时间>.json`。 |
| `mergeStates()` / `mergeList()` / `pickNewer()` | 并集合并：`tasks` / `reminders` 按 `id` 合并，同 id 取 `lastTouchedAt` 较新的一方；`settings` 以本机为准；`snoozed` / `rhythmLog` 做对象合并；`tasks` 按 `order` 排序。 |
| `storeDelete()` | 把文件改名成 `state.json.deleted-<时间戳>`（不直接删，留痕用于 `cleared` 判断）。 |
| IPC | `tt:store-load` / `tt:store-save` / `tt:store-del` / `tt:store-path` / `tt:store-reveal`（后两个给设置页显示路径 + 在资源管理器里定位）。 |

### 2. `desktop/preload.cjs`

在 `contextBridge.exposeInMainWorld('desktop', {...})` 里加：

```js
store: {
  load: () => ipcRenderer.invoke('tt:store-load'),
  save: (data) => ipcRenderer.invoke('tt:store-save', data),
  del: () => ipcRenderer.invoke('tt:store-del'),
  path: () => ipcRenderer.invoke('tt:store-path'),
  reveal: () => ipcRenderer.invoke('tt:store-reveal'),
},
```

### 3. 渲染层存储函数（bundle 里的锚点）

原版只有三个存储函数，全部是 `async`，因此可以直接把「优先文件后端、失败回退 IndexedDB」插在函数开头，业务代码一行不用改：

| 压缩名 | 作用 | 原始签名 |
|---|---|---|
| `Gg()` | 读整份状态 | `async function Gg(){try{const f=await vo(),...` |
| `mv(f)` | 写整份状态（`gl()` 里 400 ms 防抖后调用） | `async function mv(f){try{const r=await vo(),...` |
| `Xg()` | 清空 | `async function Xg(){try{const f=await vo(),...` |

改法：函数体最前面插入文件后端调用，成功即 `return`，异常/失败走原来的 IndexedDB 逻辑。
另外在 IndexedDB 读取成功、而文件尚不存在时，顺手把结果写一份到文件（旧数据迁移），
并用 `localStorage['tasktable:filemigrated']` 打标记，避免「清空数据后又被旧库复活」。

---

## 二、界面改动

### 1. 导航栏（App 外壳）

原：

```jsx
<div className="navbar-right">
  <Button variant="plain" size="sm" onClick={openHelp} title="怎么用（Alt+H）">? 怎么用</Button>
</div>
```

改：

```jsx
<div className="navbar-right">
  <Button variant="plain" onClick={reloadFromFile} title="重新读取数据文件">↻ 同步</Button>
  <Button variant="filled" onClick={openCapture} title="记一件（Alt+Q）">+ 记一件</Button>
  <Button variant="plain" onClick={openHelp} title="怎么用（Alt+H）">? 怎么用</Button>
</div>
```

- `reloadFromFile`：`store.load()` → 与内存状态 `mergeStates` → `replaceState` → 按钮文案临时变成
  「读取中…」→「已同步 +N」/「已是最新」/「读取失败」，1.8 s 后复位。
- `+ 记一件` 替代原来四象限中央的悬浮圆钮（宽屏下用 CSS 隐藏 `.fab-capture`）。

### 2. 「今天」列的任务卡

- 结构：`<div class="card-top"> <div class="task-title"/> <DueCountdown/> </div>`
- 问题：两者同一行，倒计时是 `white-space:nowrap` 的大号胶囊，标题被压到「最小内容宽度」= 一个汉字，出现「两字一列」。
- 改法（纯 CSS）：
  ```css
  .card-top{flex-wrap:wrap}
  .card-top>.task-title{flex:1 1 100%;min-width:0}
  .card-top>.badge.remain{flex:0 0 auto;margin-left:0;margin-top:.3125rem}
  ```
  即：标题独占一行，倒计时另起一行左对齐。

### 3. 卡片底部的可折叠进展记录（新组件）

原版进展记录只在右侧详情抽屉里可见。新增一个小组件挂在 `task-note` 之后：

```jsx
<ProgressLogs logs={task.logs} />
// 折叠：▸ 进展 3   ← 最新一条的预览（单行省略，title 里给完整内容+时间）
// 展开：▾ 进展 3   ← 全部记录，新→旧，左侧细蓝线缩进
```

要点：`onClick` 全部 `stopPropagation()`，避免触发整行选中 / 打开详情；展开状态是组件内部 state，
不写进数据文件；没有进展的任务渲染 `null`。时间格式：当天 `HH:MM`，跨天 `MM-DD HH:MM`。

### 4. 窄窗口布局修正（原版 bug）

窗口 ≤960 px 时 `.worksheet` 仍是 grid 两行，行被压扁后「今天」列内容溢出、被四象限卡片盖住。
改为块级堆叠：

```css
@media(max-width:60rem){ .worksheet{display:block} .col-matrix{margin-top:var(--sp-5)} }
```

### 5. 隐藏中央悬浮按钮

```css
@media(min-width:46.0625rem){ .fab-capture{display:none} }
```

---

## 三、文案与版本

- 设置 → 数据 → 区块底部说明改成新路径 + 同步方式。
- 新增一行「数据文件 + 路径 + 打开文件夹」（`store.path()` / `store.reveal()`）。
- 左下角版本号 `v0.1.5` → `v0.1.7-local`；`package.json` 的 `version` 同步改为 `0.1.6`。

---

## 四、如果要合进源码工程

1. 在源码里新建 `src/main/storage.ts`：把上面 `storeLoad/storeSave/storeDelete/mergeStates/migrateLegacyAppData` 搬过去（纯 Node，无 Electron 依赖，除 `app.getPath`）；
2. 主进程注册 IPC；
3. preload 暴露 `store`；
4. 把渲染层 `loadState/saveState/clearState` 改成先走 `window.desktop.store`，本地 IndexedDB 仅作降级；
5. 界面：导航栏两个按钮、进展记录组件、三处 CSS；
6. 版本号、README、`.gitignore` 同步。
