const { app, BrowserWindow, screen, ipcMain, shell } = require('electron')
const path = require('path')
const isDev = process.env.NODE_ENV === 'development'

// Variables para las ventanas de Lune
let mainWindow
let petWindow

// Crear la ventana principal - Donde está el menú de videojuego
function createMainWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  
  mainWindow = new BrowserWindow({
    width: 450,
    height: 650,
    x: 50,
    y: 50,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js')
    },
    frame: false, // Sin bordes para look moderno
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    transparent: true,
    show: false
  })

  // Cargar la página principal
  mainWindow.loadFile('public/index.html')
  
  // Mostrar ventana cuando esté lista
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // En desarrollo, abrir herramientas para programadores
  if (isDev) {
    mainWindow.webContents.openDevTools()
  }
}

// Crear la ventana de la mascota - La esfera animada en el escritorio
function createPetWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  
  petWindow = new BrowserWindow({
    width: 170,
    height: 170,
    x: width - 220,
    y: height - 220,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    transparent: true,
    hasShadow: false
  })

  // Cargar la página de la mascota
  petWindow.loadFile('public/pet.html')
  
  // Hacer que la mascota no bloquee clicks del mouse
  petWindow.setIgnoreMouseEvents(true)
}

// Cuando Electron esté listo, crear las ventanas
app.whenReady().then(() => {
  createMainWindow()
  createPetWindow()

  // Si el usuario cierra todas las ventanas y reabre la app
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow()
      createPetWindow()
    }
  })
})

// Cuando se cierren todas las ventanas
app.on('window-all-closed', () => {
  // En macOS, las apps suelen quedarse abiertas
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// --- Comandos para controlar el sistema ---

// Abrir aplicaciones con comandos de voz
ipcMain.handle('open-app', async (event, appName) => {
  const { exec } = require('child_process')
  
  switch(appName.toLowerCase()) {
    case 'vscode':
    case 'visual studio code':
      if (process.platform === 'win32') {
        exec('code')
      } else if (process.platform === 'darwin') {
        exec('open -a "Visual Studio Code"')
      } else {
        exec('code')
      }
      break
      
    case 'browser':
    case 'navegador':
      if (process.platform === 'win32') {
        exec('start chrome')
      } else if (process.platform === 'darwin') {
        exec('open -a "Google Chrome"')
      } else {
        exec('google-chrome')
      }
      break
      
    case 'calculator':
    case 'calculadora':
      if (process.platform === 'win32') {
        exec('calc')
      } else if (process.platform === 'darwin') {
        exec('open -a Calculator')
      } else {
        exec('gnome-calculator')
      }
      break
      
    default:
      throw new Error(`Lune no reconoce esta aplicación: ${appName}`)
  }
})

// Minimizar ventana principal
ipcMain.handle('minimize-window', () => {
  if (mainWindow) {
    mainWindow.hide()
  }
})

// Cerrar aplicación completamente
ipcMain.handle('close-app', () => {
  app.quit()
})

// Mostrar ventana principal (cuando haces click en la mascota)
ipcMain.handle('show-main-window', () => {
  if (mainWindow) {
    mainWindow.show()
    mainWindow.focus() // Traer la ventana al frente
  }
})