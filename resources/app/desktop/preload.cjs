const { contextBridge, ipcRenderer } = require('electron')

/**
 * 渲染进程只拿到这几个能力，没有 Node。
 * 主进程通过 'command' 通道下发菜单/全局快捷键触发的动作。
 */
contextBridge.exposeInMainWorld('desktop', {
  isDesktop: true,
  platform: process.platform,
  onCommand: (cb) => {
    ipcRenderer.on('command', (_event, command) => cb(command))
  },
  setStatus: (payload) => {
    ipcRenderer.send('status', payload)
  },
  /** 把界面里改好的快捷键交给主进程重新注册；返回注册失败的那些 */
  setHotkeys: (combos) => {
    ipcRenderer.send('hotkeys', combos)
  },
  onHotkeysResult: (cb) => {
    ipcRenderer.on('hotkeys-result', (_event, failed) => cb(failed))
  },
  closeToTrayHintShown: () => {
    ipcRenderer.send('close-hint-shown')
  },
  // 0.1.6 本地补丁：整份状态读写成一个 JSON 文件
  store: {
    load: () => ipcRenderer.invoke('tt:store-load'),
    save: (data) => ipcRenderer.invoke('tt:store-save', data),
    del: () => ipcRenderer.invoke('tt:store-del'),
    path: () => ipcRenderer.invoke('tt:store-path'),
    reveal: () => ipcRenderer.invoke('tt:store-reveal'),
  },
})
