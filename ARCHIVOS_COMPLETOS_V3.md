# 🌙 Lune CD v3.0 - Archivos Listos para Copiar y Pegar

## 📁 Aquí tienes TODOS los archivos necesarios para la versión 3.0

### 🎯 Instrucciones Fáciles:
1. **Crea una carpeta nueva** (o limpia la actual)
2. **Copia y pega** cada archivo en su lugar correcto
3. **Ejecuta los comandos** de instalación
4. ¡Listo! 🚀

---

## 📋 ESTRUCTURA DE CARPETAS A CREAR:

```
Lune_CD/
├── 📁 electron/
│   ├── main.js
│   └── preload.js
├── 📁 public/
│   ├── index.html
│   └── pet.html
├── 📁 src/
│   └── 📁 app/
│       ├── 📁 api/
│       │   ├── 📁 chat/
│       │   │   └── route.ts
│       │   └── 📁 status/
│       │       └── route.ts
│       ├── globals.css
│       ├── layout.tsx
│       └── page.tsx
├── .env
├── .env.example
├── .gitignore
├── COMANDOS_GIT_WINDOWS.md
├── LIMPIEZA_V3_WINDOWS.md
├── package.json
├── README.md
├── server.js
└── tailwind.config.ts
```

---

## 📄 ARCHIVOS PARA COPIAR (En orden de creación):

### 1️⃣ Archivos Raíz (Copiar en la carpeta principal Lune_CD/)

#### 📄 package.json
```json
{
  "name": "lune-cd-mascota-virtual",
  "version": "3.0.0",
  "description": "Lune CD v3.0 - Tu mascota virtual inteligente con chat y menú de videojuego",
  "main": "electron/main.js",
  "homepage": "./",
  "private": true,
  "scripts": {
    "dev": "nodemon --exec \"node server.js\" --watch server.js --watch src --ext ts,tsx,js,jsx",
    "build": "next build",
    "start": "NODE_ENV=production node server.js",
    "electron": "electron .",
    "electron-dev": "concurrently \"npm run dev\" \"wait-on http://localhost:3000 && electron .\"",
    "electron-build": "npm run build && electron-builder",
    "dist": "npm run build && electron-builder --publish=never",
    "lint": "next lint"
  },
  "dependencies": {
    "@radix-ui/react-accordion": "^1.2.11",
    "@radix-ui/react-alert-dialog": "^1.1.14",
    "@radix-ui/react-aspect-ratio": "^1.1.7",
    "@radix-ui/react-avatar": "^1.1.10",
    "@radix-ui/react-checkbox": "^1.3.2",
    "@radix-ui/react-collapsible": "^1.1.11",
    "@radix-ui/react-context-menu": "^2.2.15",
    "@radix-ui/react-dialog": "^1.1.14",
    "@radix-ui/react-dropdown-menu": "^2.1.15",
    "@radix-ui/react-hover-card": "^1.1.14",
    "@radix-ui/react-label": "^2.1.7",
    "@radix-ui/react-menubar": "^1.1.15",
    "@radix-ui/react-navigation-menu": "^1.2.13",
    "@radix-ui/react-popover": "^1.1.14",
    "@radix-ui/react-progress": "^1.1.7",
    "@radix-ui/react-radio-group": "^1.3.7",
    "@radix-ui/react-scroll-area": "^1.2.9",
    "@radix-ui/react-select": "^2.2.5",
    "@radix-ui/react-separator": "^1.1.7",
    "@radix-ui/react-slider": "^1.3.5",
    "@radix-ui/react-slot": "^1.2.3",
    "@radix-ui/react-switch": "^1.2.5",
    "@radix-ui/react-tabs": "^1.1.12",
    "@radix-ui/react-toast": "^1.2.14",
    "@radix-ui/react-toggle": "^1.1.9",
    "@radix-ui/react-toggle-group": "^1.1.10",
    "@radix-ui/react-tooltip": "^1.2.7",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.1.1",
    "concurrently": "^9.2.1",
    "electron": "^39.0.0",
    "electron-builder": "^26.0.12",
    "framer-motion": "^12.23.2",
    "lucide-react": "^0.525.0",
    "next": "15.3.5",
    "nodemon": "^3.1.10",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwind-merge": "^3.3.1",
    "tailwindcss-animate": "^1.0.7",
    "tsx": "^4.20.3",
    "wait-on": "^9.0.1",
    "z-ai-web-dev-sdk": "^0.0.10"
  },
  "devDependencies": {
    "@eslint/eslintrc": "^3",
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "15.3.5",
    "tailwindcss": "^4",
    "typescript": "^5"
  },
  "build": {
    "appId": "com.lune-cd.mascota-virtual",
    "productName": "Lune CD v3.0 - Mascota Virtual",
    "directories": {
      "output": "dist"
    },
    "files": [
      "electron/**/*",
      "public/**/*",
      ".next/**/*",
      "server.js",
      "package.json"
    ],
    "win": {
      "target": "nsis",
      "icon": "public/icon.ico"
    },
    "mac": {
      "target": "dmg",
      "icon": "public/icon.icns"
    },
    "linux": {
      "target": "AppImage",
      "icon": "public/icon.png"
    }
  },
  "keywords": [
    "mascota-virtual",
    "chat-inteligente",
    "escritorio",
    "ollama",
    "electron",
    "nextjs",
    "ia-local",
    "lune-cd"
  ],
  "author": "Diego Lizarraga",
  "license": "MIT"
}
```

#### 📄 server.js
```javascript
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
```

#### 📄 .env.example
```env
# Ejemplo de configuración - Copia este archivo a .env y ajusta los valores
# Configuración de Ollama - La IA local que hace a Lune inteligente
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# Configuración de la aplicación - No tocar esto a menos que sepas lo que haces
NODE_ENV=development
PORT=3000

# Configuración de Electron - Para que la ventana de escritorio funcione bien
ELECTRON_IS_DEV=true

# NOTA: Esta versión 3.0 no necesita API keys externas, todo funciona localmente
```

#### 📄 .env
```env
# Configuración de Ollama - La IA local que hace a Lune inteligente
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# Configuración de la aplicación - No tocar esto a menos que sepas lo que haces
NODE_ENV=development
PORT=3000

# Configuración de Electron - Para que la ventana de escritorio funcione bien
ELECTRON_IS_DEV=true

# NOTA: Esta versión 3.0 no necesita API keys externas, todo funciona localmente
```

#### 📄 .gitignore
```gitignore
# Dependencias de Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Archivos de compilación de Next.js
.next/
out/
build/
dist/

# Variables de entorno (¡NO SUBIR!)
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Archivos de logs
*.log
logs/

# Archivos temporales
*.tmp
*.temp
.cache/

# Archivos de sistema operativos
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Archivos de editores de código
.vscode/
.idea/
*.swp
*.swo
*~

# Archivos de Electron
app/
release/

# Archivos de TypeScript
*.tsbuildinfo

# Archivos de testing
coverage/
.nyc_output/

# Archivos de package managers
package-lock.json
yarn.lock
pnpm-lock.yaml

# Archivos de configuración local
.eslintcache
.stylelintcache

# Archivos de caché de npm
.npm

# Archivos de runtime
.pnpm-debug.log*

# Archivos de Vercel
.vercel

# Archivos de Turbo
.turbo

# Archivos específicos de Lune CD
# (Agregar aquí si hay archivos específicos que deban ignorarse)

# Archivos de backup
*.bak
*.backup
*.old

# Archivos de databases (si se usan)
*.db
*.sqlite
*.sqlite3

# Archivos de Python viejos (por si acudo quedan)
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
pip-log.txt
pip-delete-this-directory.txt
.tox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Archivos de configuración de Ollama (si existen localmente)
.ollama/
ollama_models/

# Archivos de screenshots para desarrollo
screenshots/
*.png
*.jpg
*.jpeg
*.gif
# (excepto los que son parte del proyecto)

# Archivos de documentación generada
docs/_build/
site/

# Archivos de análisis de código
.sonar/
dependency-cruiser.js

# Archivos de personalización local
.local/
local.json
user-settings.json
```

#### 📄 tailwind.config.ts
```typescript
import type { Config } from "tailwindcss";

// Configuración de Tailwind CSS para Lune CD v3.0
// Con colores personalizados y animaciones increíbles
const config: Config = {
    darkMode: "class",
    content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
        extend: {
                // Paleta de colores personalizada para Lune CD
                colors: {
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        card: {
                                DEFAULT: 'hsl(var(--card))',
                                foreground: 'hsl(var(--card-foreground))'
                        },
                        popover: {
                                DEFAULT: 'hsl(var(--popover))',
                                foreground: 'hsl(var(--popover-foreground))'
                        },
                        primary: {
                                DEFAULT: 'hsl(var(--primary))',
                                foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                                DEFAULT: 'hsl(var(--secondary))',
                                foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                                DEFAULT: 'hsl(var(--muted))',
                                foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                                DEFAULT: 'hsl(var(--accent))',
                                foreground: 'hsl(var(--accent-foreground))'
                        },
                        destructive: {
                                DEFAULT: 'hsl(var(--destructive))',
                                foreground: 'hsl(var(--destructive-foreground))'
                        },
                        border: 'hsl(var(--border))',
                        input: 'hsl(var(--input))',
                        ring: 'hsl(var(--ring))',
                        chart: {
                                '1': 'hsl(var(--chart-1))',
                                '2': 'hsl(var(--chart-2))',
                                '3': 'hsl(var(--chart-3))',
                                '4': 'hsl(var(--chart-4))',
                                '5': 'hsl(var(--chart-5))'
                        },
                        // Colores adicionales para Lune CD
                        lune: {
                                primary: '#667eea',
                                secondary: '#764ba2',
                                accent: '#ff69b4',
                                dark: '#0f172a',
                                light: '#f8fafc'
                        }
                },
                // Bordes redondeados personalizados
                borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)',
                        'lune': '20px', // Bordes redondeados de Lune
                        'button': '50px', // Botones redondos del menú
                        'message': '18px' // Mensajes del chat
                },
                // Animaciones personalizadas
                keyframes: {
                        'bounce-gentle': {
                                '0%, 20%, 50%, 80%, 100%': { transform: 'translateY(0)' },
                                '40%': { transform: 'translateY(-15px)' },
                                '60%': { transform: 'translateY(-8px)' }
                        },
                        'glow-pulse': {
                                '0%': { textShadow: '0 0 20px rgba(255, 255, 255, 0.5)' },
                                '50%': { textShadow: '0 0 30px rgba(255, 255, 255, 0.8), 0 0 40px rgba(255, 255, 255, 0.6)' },
                                '100%': { textShadow: '0 0 20px rgba(255, 255, 255, 0.5)' }
                        },
                        'float-animation': {
                                '0%, 100%': { transform: 'translateY(0px)' },
                                '50%': { transform: 'translateY(-20px)' }
                        },
                        'message-slide': {
                                '0%': { opacity: '0', transform: 'translateY(20px)' },
                                '100%': { opacity: '1', transform: 'translateY(0)' }
                        },
                        'typing-dot': {
                                '0%, 80%, 100%': { transform: 'scale(0.8)', opacity: '0.5' },
                                '40%': { transform: 'scale(1)', opacity: '1' }
                        },
                        'shimmer': {
                                '0%': { transform: 'translateX(-100%)' },
                                '100%': { transform: 'translateX(100%)' }
                        },
                        'particle-fly': {
                                '0%': { opacity: '1', transform: 'translate(0, 0) scale(1)' },
                                '100%': { opacity: '0', transform: 'translate(var(--x), var(--y)) scale(0.3)' }
                        }
                },
                animation: {
                        'bounce-gentle': 'bounce-gentle 2s infinite',
                        'glow-pulse': 'glow-pulse 2s ease-in-out infinite alternate',
                        'float': 'float-animation 6s ease-in-out infinite',
                        'message-slide': 'message-slide 0.3s ease-out',
                        'typing': 'typing-dot 1.4s infinite ease-in-out',
                        'shimmer': 'shimmer 2s infinite',
                        'particle': 'particle-fly 1.5s ease-out forwards'
                },
                // Sombras personalizadas
                boxShadow: {
                        'lune': '0 15px 40px rgba(102, 126, 234, 0.6)',
                        'lune-hover': '0 10px 30px rgba(0, 0, 0, 0.3)',
                        'button': '0 5px 15px rgba(102, 126, 234, 0.4)',
                        'glow': '0 0 30px rgba(255, 255, 255, 0.8)',
                        'message': '0 2px 4px rgba(0, 0, 0, 0.2)'
                },
                // Gradientes personalizados
                backgroundImage: {
                        'lune-gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'button-gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'glass': 'rgba(255, 255, 255, 0.1)',
                        'glass-dark': 'rgba(15, 23, 42, 0.95)'
                },
                // Backdrop filters para efectos de cristal
                backdropBlur: {
                        'lune': '10px'
                }
        }
  },
  plugins: [],
};
export default config;
```

---

## 🎯 ¡AHORA COPIA LOS ARCHIVOS QUE TE DI ANTES!

Los archivos anteriores son solo la estructura básica. Ahora necesitas copiar todos los archivos que te proporcioné en los mensajes anteriores:

### 📁 Carpetas que necesitas crear:
1. **electron/** (con main.js y preload.js)
2. **public/** (con index.html y pet.html)
3. **src/app/** (con todos los archivos TypeScript y CSS)
4. **src/app/api/chat/** (con route.ts)
5. **src/app/api/status/** (con route.ts)

### 📄 Archivos de documentación:
- **README.md** (la versión v3.0 completa)
- **LIMPIEZA_V3_WINDOWS.md** (comandos para Windows)
- **COMANDOS_GIT_WINDOWS.md** (comandos Git para Windows)

---

## 🚀 PASOS FINALES:

### 1️⃣ Instalar dependencias:
```powershell
npm install
```

### 2️⃣ Iniciar Ollama (en otra terminal):
```powershell
ollama serve
```

### 3️⃣ Iniciar Lune CD v3.0:
```powershell
npm run electron-dev
```

---

## ✅ VERIFICACIÓN FINAL:

La carpeta debería quedar así:
```
Lune_CD/
├── 📁 electron/
├── 📁 public/
├── 📁 src/
├── 📄 .env
├── 📄 .env.example
├── 📄 .gitignore
├── 📄 COMANDOS_GIT_WINDOWS.md
├── 📄 LIMPIEZA_V3_WINDOWS.md
├── 📄 package.json
├── 📄 README.md
├── 📄 server.js
├── 📄 tailwind.config.ts
└── 📁 node_modules/ (se crea con npm install)
```

---

## 🎉 ¡LISTO!

**¡Felicidades! Ahora tienes Lune CD v3.0 completo y listo para usar y subir a GitHub!** 🌙✨

Si tienes algún problema, revisa los archivos de documentación que te proporcioné.