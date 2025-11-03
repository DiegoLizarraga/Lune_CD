const { contextBridge, ipcRenderer } = require('electron')

// Exponer las funciones de Electron al navegador de forma segura
// Esto permite que la interfaz web hable con el sistema operativo
contextBridge.exposeInMainWorld('electronAPI', {
  // Comandos para abrir aplicaciones del sistema
  openApp: (appName) => ipcRenderer.invoke('open-app', appName),
  
  // Control de ventanas
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  closeApp: () => ipcRenderer.invoke('close-app'),
  showMainWindow: () => ipcRenderer.invoke('show-main-window'),
  
  // Eventos - para cuando la mascota quiere abrir la ventana principal
  onShowMainWindow: (callback) => {
    ipcRenderer.on('show-main-window', callback)
    return () => ipcRenderer.removeListener('show-main-window', callback)
  }
})

// Exponer la API fetch para poder hacer peticiones a Ollama y chat.z.ai
// Esto es importante para que el chat funcione
contextBridge.exposeInMainWorld('fetchAPI', {
  fetch: (url, options) => {
    return fetch(url, options)
  }
})