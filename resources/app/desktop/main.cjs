const path = require('node:path')
const { pathToFileURL } = require('node:url')
const {
  app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain,
  nativeImage, protocol, net, shell, Notification,
} = require('electron')

const DIST = path.join(__dirname, '..', 'dist')
const DEV_URL = 'http://127.0.0.1:5183/'
const INDEX = 'app://local/'

const isDev = process.argv.includes('--dev')
let win = null
let tray = null
let quitting = false
let status = { today: 0, unread: 0 }
let closeHintShown = false

/* ===== 0.1.6 本地补丁：把「整份状态」存成一个 JSON 文件，方便网盘 / NAS 同步 =====
   数据放在【用户目录】，不放在程序目录 —— 程序目录要能原样传到 GitHub，不能夹带个人数据。
   路径优先级：
     1) 环境变量 TASKTABLE_DATA_FILE
     2) %APPDATA%\TaskTable\data-path.txt 的第一行有效行（每台电脑各自配置）
     3) 程序目录下的 data-path.txt（旧版遗留位置，仅作兼容）
     4) 默认 %APPDATA%\TaskTable\data\state.json */
const fs = require('node:fs')
const os = require('node:os')
const crypto = require('node:crypto')

// exe 所在目录：只用来找旧版遗留的 data 目录，以及读取兼容用的 data-path.txt
const APP_ROOT = path.dirname(app.getPath('exe'))

// 每台电脑各自的配置/数据根目录
function configDir() {
  // 注意：不能叫 TaskTable —— Windows 不区分大小写，会和 Electron 自己的 userData
  // 目录 %APPDATA%	asktable（浏览器缓存那一大堆）撞成同一个。
  return path.join(app.getPath('appData'), 'TaskTableData')
}

function readPathFile(file) {
  try {
    if (!fs.existsSync(file)) return null
    const line = fs.readFileSync(file, 'utf8').split(/\r?\n/)
      .map(s => s.trim()).find(s => s && !s.startsWith('#'))
    return line ? path.resolve(line) : null
  } catch (_) {
    return null
  }
}

function defaultDataFile() {
  return path.join(configDir(), 'data', 'state.json')
}

function dataFilePath() {
  const envPath = (process.env.TASKTABLE_DATA_FILE || '').trim()
  if (envPath) return path.resolve(envPath)
  return readPathFile(path.join(configDir(), 'data-path.txt'))
    || readPathFile(path.join(APP_ROOT, 'data-path.txt'))
    || defaultDataFile()
}

/* 旧版本把数据放在 <程序目录>\data\state.json。
   新版第一次启动时把它搬进用户目录，并把旧目录改名留档，
   这样程序目录就干净了（可以整个传 GitHub）。 */
function migrateLegacyAppData() {
  try {
    const target = defaultDataFile()
    if (dataFilePath() !== target) return null // 用户自己指定了路径，不动
    if (fs.existsSync(target)) return null
    const legacyDir = path.join(APP_ROOT, 'data')
    const legacy = path.join(legacyDir, 'state.json')
    if (!fs.existsSync(legacy)) return null
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.copyFileSync(legacy, target)
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    try {
      fs.renameSync(legacyDir, path.join(APP_ROOT, 'data.migrated-' + stamp))
    } catch (_) {}
    try {
      const ignore = path.join(path.dirname(target), '.stignore')
      if (!fs.existsSync(ignore)) fs.writeFileSync(ignore, 'state.conflict-*.json\n', 'utf8')
    } catch (_) {}
    return target
  } catch (_) {
    return null
  }
}

const MIGRATED_TO = migrateLegacyAppData()

function sha256(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex')
}

let knownHash = null // 上次读到 / 写入时文件内容的指纹，用来发现别的机器改过它

function storeLoad() {
  const file = dataFilePath()
  try {
    if (!fs.existsSync(file)) {
      knownHash = null
      // 目录里有没有「主动清空」留下的 state.json.deleted-* 痕迹
      let cleared = false
      try {
        const base = path.basename(file) + '.deleted-'
        cleared = fs.readdirSync(path.dirname(file)).some(n => n.startsWith(base))
      } catch (_) {}
      return { ok: true, file, data: null, missing: true, cleared }
    }
    const text = fs.readFileSync(file, 'utf8')
    knownHash = sha256(text)
    return { ok: true, file, data: JSON.parse(text) }
  } catch (err) {
    return { ok: false, file, error: String((err && err.message) || err) }
  }
}

/* 两台机器都改过时，按 id 合并：谁的 lastTouchedAt 更新就留谁的；两边各自新增的都保留。
   注意：这是「并集」策略 —— 删除不会跨机器传播（另一台仍留着旧任务时，它会被合并回来）。 */
function pickNewer(a, b) {
  const at = Number((a && (a.lastTouchedAt ?? a.at ?? a.createdAt)) || 0)
  const bt = Number((b && (b.lastTouchedAt ?? b.at ?? b.createdAt)) || 0)
  return bt > at ? b : a
}

function mergeList(localList, remoteList) {
  const out = new Map()
  for (const x of Array.isArray(remoteList) ? remoteList : []) {
    if (x && typeof x === 'object' && x.id) out.set(x.id, x)
  }
  for (const x of Array.isArray(localList) ? localList : []) {
    if (!x || typeof x !== 'object' || !x.id) continue
    const prev = out.get(x.id)
    out.set(x.id, prev ? pickNewer(x, prev) : x)
  }
  return [...out.values()]
}

function mergeStates(local, remote) {
  if (!remote || typeof remote !== 'object' || !Array.isArray(remote.tasks)) return null
  const base = Array.isArray(local.tasks) ? local : { ...remote }
  const merged = { ...remote, ...base }
  merged.version = base.version ?? remote.version
  merged.tasks = mergeList(base.tasks, remote.tasks)
  merged.tasks.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  merged.reminders = mergeList(base.reminders, remote.reminders)
  merged.snoozed = { ...(remote.snoozed || {}), ...(base.snoozed || {}) }
  merged.rhythmLog = { ...(remote.rhythmLog || {}), ...(base.rhythmLog || {}) }
  return merged
}

function storeSave(data) {
  const file = dataFilePath()
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    let conflict = null
    let out = data
    let mergedRemote = 0
    if (fs.existsSync(file)) {
      const cur = fs.readFileSync(file, 'utf8')
      if (knownHash && sha256(cur) !== knownHash) {
        // 我们读过之后，别的机器（或同步软件）改过它：先留档，再合并
        const stamp = new Date().toISOString().replace(/[:.]/g, '-')
        const host = String(os.hostname() || 'pc').replace(/[^A-Za-z0-9_-]/g, '')
        conflict = file.replace(/\.json$/i, '') + '.conflict-' + host + '-' + stamp + '.json'
        try { fs.writeFileSync(conflict, cur, 'utf8') } catch (_) {}
        try {
          const merged = mergeStates(data, JSON.parse(cur))
          if (merged) {
            mergedRemote = merged.tasks.length - (Array.isArray(data.tasks) ? data.tasks.length : 0)
            out = merged
          }
        } catch (_) {}
      }
    }
    const text = JSON.stringify(out, null, 2)
    const tmp = file + '.tmp' // 名字以 .tmp 结尾，绿联云 / Syncthing 默认会忽略，不会同步半成品
    fs.writeFileSync(tmp, text, 'utf8')
    fs.renameSync(tmp, file) // 原子替换，同步软件不会读到半个文件
    knownHash = sha256(text)
    return { ok: true, file, conflict, mergedRemote }
  } catch (err) {
    return { ok: false, file, error: String((err && err.message) || err) }
  }
}

function storeDelete() {
  const file = dataFilePath()
  try {
    if (fs.existsSync(file)) fs.renameSync(file, file + '.deleted-' + Date.now())
    knownHash = null
    return { ok: true, file }
  } catch (err) {
    return { ok: false, file, error: String((err && err.message) || err) }
  }
}

ipcMain.handle('tt:store-load', () => storeLoad())
ipcMain.handle('tt:store-save', (_event, data) => storeSave(data))
ipcMain.handle('tt:store-del', () => storeDelete())
ipcMain.handle('tt:store-path', () => ({ file: dataFilePath(), dir: path.dirname(dataFilePath()) }))
ipcMain.handle('tt:store-reveal', () => {
  try {
    const file = dataFilePath()
    if (fs.existsSync(file)) shell.showItemInFolder(file)
    else shell.openPath(path.dirname(file))
    return { ok: true, file }
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) }
  }
})
/* ===== 补丁结束 ===== */

/* 用自定义 scheme 而不是 file://：
   file:// 是不透明源，IndexedDB、Notification 这些都会失效。
   standard + secure 才能拿到正常的源和「安全上下文」。 */
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'app',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, codeCache: true },
  },
])

function serveDist() {
  protocol.handle('app', request => {
    const url = new URL(request.url)
    let rel = decodeURIComponent(url.pathname)
    if (rel === '/' || rel === '') rel = '/index.html'
    const filePath = path.normalize(path.join(DIST, rel))
    // 目录穿越防护
    if (!filePath.startsWith(DIST)) {
      return new Response('forbidden', { status: 403 })
    }
    return net.fetch(pathToFileURL(filePath).toString())
  })
}

/** 托盘图标：32×32，四象限配色画成 2×2 方块（不依赖外部文件） */
function trayIcon() {
  const S = 32
  const buf = Buffer.alloc(S * S * 4) // BGRA
  const put = (x, y, r, g, b) => {
    const i = (y * S + x) * 4
    buf[i] = b
    buf[i + 1] = g
    buf[i + 2] = r
    buf[i + 3] = 255
  }
  const colors = [[255, 59, 48], [52, 199, 89], [255, 149, 0], [142, 142, 147]]
  const origins = [[2, 2], [17, 2], [2, 17], [17, 17]]
  for (let q = 0; q < 4; q++) {
    const [ox, oy] = origins[q]
    const [r, g, b] = colors[q]
    for (let y = 0; y < 13; y++) for (let x = 0; x < 13; x++) put(ox + x, oy + y, r, g, b)
  }
  return nativeImage.createFromBitmap(buf, { width: S, height: S })
}

function appIcon() {
  const p = path.join(__dirname, '..', 'build', 'icon.png')
  const img = nativeImage.createFromPath(p)
  return img.isEmpty() ? undefined : img
}

function showWindow() {
  if (!win) return
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
}

function send(command) {
  showWindow()
  if (win) win.webContents.send('command', command)
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    { label: '显示主窗口', click: showWindow },
    { type: 'separator' },
    { label: '速录…    Alt+Q', click: () => send('capture') },
    { label: '开始归位  Alt+T', click: () => send('triage') },
    { type: 'separator' },
    {
      label: '开机自动启动',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: item => app.setLoginItemSettings({ openAtLogin: item.checked, openAsHidden: true }),
    },
    { type: 'separator' },
    { label: '退出', click: () => { quitting = true; app.quit() } },
  ])
}

function refreshTray() {
  if (!tray) return
  const parts = []
  if (status.today > 0) parts.push(status.today + ' 件待办')
  if (status.unread > 0) parts.push(status.unread + ' 条提醒')
  tray.setToolTip('四象限工作表' + (parts.length ? '\n' + parts.join(' · ') : ''))
  tray.setContextMenu(buildTrayMenu())
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 940,
    minHeight: 620,
    show: false,
    title: '四象限工作表',
    backgroundColor: '#f2f2f7',
    autoHideMenuBar: true,
    icon: appIcon(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  win.once('ready-to-show', () => win.show())

  // 关窗不退出，缩到托盘 —— 桌面端的提醒闭环全靠这个
  win.on('close', event => {
    if (quitting) return
    event.preventDefault()
    win.hide()
    if (!closeHintShown) {
      closeHintShown = true
      if (Notification.isSupported()) {
        new Notification({
          title: '四象限工作表还在后台运行',
          body: '窗口已缩到托盘。提醒会照常送达，按 Alt+Q 随时速录。',
        }).show()
      }
    }
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (isDev && !app.isPackaged) {
    win.loadURL(DEV_URL)
  } else {
    win.loadURL(INDEX)
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', showWindow)

  app.whenReady().then(() => {
    serveDist()
    createWindow()

    tray = new Tray(trayIcon())
    tray.on('click', () => (win && win.isVisible() ? win.hide() : showWindow()))
    refreshTray()

    globalShortcut.register('Alt+Q', () => send('capture'))
    globalShortcut.register('Alt+T', () => send('triage'))

    ipcMain.on('status', (_event, payload) => {
      status = { today: payload?.today ?? 0, unread: payload?.unread ?? 0 }
      refreshTray()
    })
    ipcMain.on('close-hint-shown', () => { closeHintShown = true })

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
      else showWindow()
    })
  })

  app.on('before-quit', () => { quitting = true })
  app.on('will-quit', () => globalShortcut.unregisterAll())
  app.on('window-all-closed', () => { /* 托盘常驻，不退出 */ })
}
