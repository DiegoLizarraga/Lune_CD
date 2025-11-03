const { createServer } = require('http')
const { parse } = require('url')
const next = require('next')

// Configuración del servidor - La magia detrás de Lune CD v3.0
const dev = process.env.NODE_ENV !== 'production'
const hostname = 'localhost'
const port = process.env.PORT || 3000

// Inicializar Next.js - El framework web súper rápido que usamos
const app = next({ dev, hostname, port })
const handle = app.getRequestHandler()

// Preparar la aplicación y crear el servidor
app.prepare().then(() => {
  createServer(async (req, res) => {
    try {
      // Parsear la URL para saber qué página pide el usuario
      const parsedUrl = parse(req.url, true)
      
      // Dejar que Next.js maneje la petición
      await handle(req, res, parsedUrl)
    } catch (err) {
      // Si algo sale mal, mostrar error bonito
      console.error('¡Ups! Algo salió mal en:', req.url, err)
      res.statusCode = 500
      res.end('Error interno del servidor - Lune está trabajando en ello...')
    }
  })
    .once('error', (err) => {
      console.error('Error crítico del servidor:', err)
      process.exit(1)
    })
    .listen(port, () => {
      console.log(`🚀 Lune CD v3.0 está listo en http://${hostname}:${port}`)
      console.log('🌙 Tu mascota virtual está despertando...')
      console.log('✨ ¡La magia está sucediendo!')
    })
})