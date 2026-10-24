# TaskTable（四象限工作表）· 0.1.7-local

桌面端「艾森豪威尔四象限」任务管理小工具（Electron + React 19），托盘常驻、`Alt+Q` 速录、到点/节律/停滞三类提醒。

本仓库是在原版 **0.1.5** 基础上打的本地补丁，主题是：**把数据从浏览器数据库里搬出来，变成一个可被网盘 / NAS 同步的 JSON 文件**，并做了几处交互修正。

## 下载（Windows 64 位）

[![Release](https://img.shields.io/badge/release-v0.1.7--local-blue)](https://github.com/Doctor-ZRF/TaskTable/releases/latest)

到 [Releases](https://github.com/Doctor-ZRF/TaskTable/releases/latest) 下载
`TaskTable-0.1.7-local-win-x64.zip`（约 152 MB）→ 解压到任意目录 → 双击 `TaskTable.exe`。

- 不需要装 Node / Electron / npm，**解压即用**
- 首次运行若遇 SmartScreen「Windows 已保护你的电脑」：更多信息 → 仍要运行（exe 未签名）
- 数据默认写到 `%APPDATA%\TaskTableData\data\state.json`

## 仓库内容

| 路径 | 说明 |
|---|---|
| `resources/app/desktop/main.cjs` | Electron 主进程：窗口/托盘/快捷键 + 文件存储 IPC（原子写、冲突留档、并集合并、旧数据迁移） |
| `resources/app/desktop/preload.cjs` | contextBridge 暴露 `window.desktop.store` |
| `resources/app/dist/` | 渲染层 bundle（Vite 构建产物，含下面所有界面补丁） |
| `使用说明-数据同步.txt` | 面向使用者的完整说明（路径优先级、同步配法、限制、回滚） |

**不含** Electron 运行时（`TaskTable.exe` 246 MB、各类 dll/pak 超过 GitHub 单文件限制）。想直接运行请见下方「运行方式」。

## 这个版本是什么

`0.1.7-local` = **原作者 0.1.6**（快捷键自定义 + 界面改造）+ **本地补丁**（数据文件化 + 多机同步）。
两边的改动通过三方合并（0.1.5 为共同基线）合成，两边功能都在。

### 原作者 0.1.6 带来的

- 全局快捷键可在界面里自定义（`registerHotkeys` + IPC，注册失败会回报）
- 「已完成 / 提醒」合并为「历史」页；「怎么用」改为「关于」面板（含历史版本更新）
- 「今天」列卡片重构为 `.row-body` / `.row-title` / `.row-status` 结构，新增 `data-quad` / `data-task-id`
- 深色主题、四象限环形进度、就地编辑标题等样式扩展

### 本地补丁带来的

1. **数据文件化**：整份状态（任务/提醒/设置/节律日志）存成单个 `state.json`，
   默认 `%APPDATA%\TaskTableData\data\state.json`（每台机器一份，不进程序目录）。
   路径优先级：`TASKTABLE_DATA_FILE` 环境变量 > `%APPDATA%\TaskTableData\data-path.txt` > 默认。
   - 写入用「临时文件 `.tmp` + 改名」原子替换；
   - 首次启动会把旧版存在 IndexedDB 里的数据自动导出成该文件；文件意外丢失时会自愈。
2. **多机同步语义**：两边都改过时先留档 `state.conflict-<机器名>-<时间>.json`，再按任务 id
   **并集合并**（同一条以 `lastTouchedAt` 更新者为准）；删除不跨机器传播。
3. **导航栏「↻ 同步」**：按需重读数据文件并合并，不用重启程序。
   （中央的「速录」圆钮保留原作者的方案。）
4. **卡片底部进展记录可折叠**：`▸ 进展 N · 最新一条预览`，点开看全部。
5. **设置 → 数据**：新增「数据文件 + 路径 + 打开文件夹」，文案改为说明文件存储与同步方式。

## 数据与同步

- 程序里看路径：设置 → 数据 → 「数据文件」，右侧「打开文件夹」。
- 想多台机器同步：用任意同步盘（Syncthing 内核的网盘客户端亦可）同步 `...\TaskTableData\data` 这**一个文件夹**，两台都设为双向。
- `.gitignore` 已忽略 `data/`、`data.migrated-*/`、`data-path.txt`、`*.conflict-*.json`、`state*.json`，不会误提交个人任务。

## 运行方式

**开发跑（不需要那个 246 MB 的 exe）**：本仓库的 `resources/app` 本身就是一个完整的 Electron 应用目录
（`package.json` 的 `main` 指向 `desktop/main.cjs`），所以装个 Electron 运行时就能跑：

```bash
npm i -D electron
npx electron resources/app
```

**当成桌面程序跑**：取一份 Electron 运行时目录（含 `TaskTable.exe` 与各种 dll），把本仓库的 `resources/app`
放进它的 `resources/` 下（不要同时存在同名的 `app.asar`），然后运行 `TaskTable.exe`
（原版是 `resources/app.asar`；本补丁改成散开的 `resources/app` 目录，方便直接改 JS 并随时回滚）。

## 想参与改进？

- 这个仓库是**在原版构建产物上打的补丁**：`desktop/*.cjs` 是可读源码，`dist/` 是压缩后的 bundle。
  所以直接改界面会很痛苦 —— 要做正经功能开发，请以**原作者的源码工程**为准。
- [PATCHES.md](PATCHES.md) 把每一处改动都列了出来（压缩产物的原始锚点 + 建议在源码里的落点），
  原作者可以直接照着合进源码，不需要读 minified 代码。
- 本仓库欢迎：Issue 报 bug / 提需求、README 与脚本类 PR、以及新的补丁建议。

## License

本仓库暂未添加 LICENSE 文件，按默认规则 = **保留所有权利**。
若要公开使用或分发，请先与原程序作者确认授权（建议在上游选定 MIT 或 GPL-3.0，本仓库随之声明）。

## 来源与致谢

原程序由朋友借助 AI agent 开发；本仓库只是在其构建产物上做的本地改动记录。

## ⚠️ 换版本须知（踩过的坑）

1. **程序目录里不能同时存在 `resources/app.asar` 和 `resources/app/`** ——
   Electron 的加载顺序是 `app.asar` 优先，asar 在就会静默加载 asar 里的旧代码，
   你改了 `resources/app/` 却不生效，且界面会显示"另一个版本"。
   本仓库使用散开的 `resources/app/`，所以 `resources/` 下只保留：
   `app/` + `app.asar.orig-0.1.5.bak`（备份）+ `default_app.asar`。
2. **换版本 = 整个文件夹替换**，不要往旧文件夹里拷 `resources/`（会混入 asar 或残留旧资源）。
3. 数据在 `%APPDATA%\TaskTableData\data\state.json`，换程序目录不影响数据；
   但两台电脑的 exe 不要同时指向同一个用户 profile（单实例锁会互相顶掉）。
