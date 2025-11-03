# 🌙 Lune CD v3.0 (esto si va encerio)

¡Bienvenido a la versión 3.0 de Lune CD! Esta es una reescritura completa desde cero usando las tecnologías mas modernas. 

<img width="1024" height="1024" alt="lunecd" src="https://github.com/user-attachments/assets/0866ba0c-f943-4796-ba16-25fcfbdbf7b2" />

---

## ✨ ¿Qué hay de nuevo en la v3.0?

### 🔄 Cambios Totales desde la v2.0

| Característica | Versión 2.0 (Anterior) | Versión 3.0 (Actual) |
|----------------|------------------------|----------------------|
| **Tecnología** | Python + Tkinter | Next.js 15 + Electron |
| **Interfaz** | Ventanas básicas | Menú estilo videojuego |
| **Chat** | Terminal simple | Interfaz minimalista moderna |
| **Instalación** | Múltiples pasos | Instalación con un solo comando |
| **Rendimiento** | Moderado | Ultra rápido y optimizado |
| **Diseño** | Funcional | Profesional y atractivo |
| **Compatibilidad** | Limitada | Multiplataforma mejorada |

### 🆕 Novedades Principales

- **🎮 Menú de Videojuego**: Interfaz increíblemente atractiva con animaciones fluidas (ya que a puro comando no se entendia nada)
- **💬 Chat Moderno**: Diseño minimalista con mensajes animados y efectos visuales
- **🖥️ Aplicación de Escritorio Real**: Ya no es localhost, es una app de escritorio nativa
- **⚡ Rendimiento Mejorado**: Inicio instantáneo y respuestas ultra rápidas
- **🎨 Diseño Profesional**: Gradientes, animaciones y efectos visuales impresionantes
- **🔧 Instalación Simplificada**: Todo configurado para funcionar con `npm install`

---

## 🚀 Instalación Súper Fácil

### Requisitos Mínimos
- **Node.js** 18 o superior - [Descargar aquí](https://nodejs.org)
- **Ollama** - [Descargar aquí](https://ollama.ai)

### Pasos para Instalar

#### 1️⃣ Clonar el Repositorio
```bash
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD
```

#### 2️⃣ Instalar Ollama (si no lo tienes)
**Windows:**
- Descarga el instalador desde https://ollama.ai/download/windows
- Ejecuta el instalador y listo

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 3️⃣ Descargar Modelo de IA
```bash
# El modelo recomendado (balance perfecto)
ollama pull llama2

# O si quieres algo más ligero
ollama pull phi3:mini
```

#### 4️⃣ Instalar Dependencias del Proyecto
```bash
npm install
```

#### 5️⃣ ¡Ejecutar Lune!
```bash
npm run electron-dev
```

¡Y listo! Lune debería abrirse automáticamente con su increíble menú de videojuego. 🎉

---

## 🎮 ¿Cómo Usar Lune v3.0?

### Menú Principal Estilo Videojuego

Al iniciar Lune, verás un menú impresionante con estas opciones:

- **🤖 Chat Inteligente** - Conversa con Lune sobre cualquier tema
- **⚙️ Configuración** - Ajusta preferencias y verifica conexión
- **❓ Ayuda** - Consulta comandos y funciones disponibles
- **💻 Abrir VS Code** - Lanza Visual Studio Code al instante
- **🌐 Abrir Navegador** - Abre tu navegador web preferido
- **🧮 Abrir Calculadora** - Inicia la calculadora del sistema

### Mascota de Escritorio Animada

Verás una adorable mascota flotando en tu escritorio:
- **🖱️ Click simple** - Abre la ventana principal de Lune
- **🖱️ Doble click** - Activa efectos mágicos de partículas
- **👆 Hover** - Muestra mensajes de estado divertidos

### Chat Inteligente Dual

Lune es súper inteligente y detecta automáticamente qué necesitas:

**Para conversaciones normales:**
- Usa Ollama local (funciona 100% offline)
- Respuestas naturales y fluidas
- Recuerda el contexto de la conversación

**Para dudas de programación:**
- Usa automáticamente chat.z.ai
- Respuestas actualizadas y precisas
- Ejemplos de código incluidos

---

## 🗂️ Estructura del Proyecto v3.0

```
Lune_CD/
├── 📁 src/app/                    # Código principal de la app
│   ├── 🎨 globals.css            # Estilos con animaciones increíbles
│   ├── 📱 page.tsx               # Interfaz principal con menú de juego
│   ├── 🏗️ layout.tsx             # Estructura base de la app
│   └── 🤖 api/                   # Endpoints para el chat
│       ├── 💬 chat/route.ts      # Chat con Ollama y chat.z.ai
│       └── ✅ status/route.ts    # Verificación de servicios
├── 🖥️ electron/                   # Configuración de ventana de escritorio
│   ├── 🪟 main.js                # Ventana principal y sistema
│   └── 🔗 preload.js             # Conexión entre ventanas
├── 🎨 public/                     # Archivos visuales
│   ├── 🏠 index.html             # Página principal
│   ├── 🌙 pet.html               # Mascota de escritorio animada
│   └── 📁 assets/                # Imágenes y recursos
├── ⚙️ server.js                   # Servidor web optimizado
├── 📦 package.json               # Dependencias y scripts
└── 🔧 .env                       # Configuración privada
```

---

## 🧹 Limpieza de Archivos Antiguos

Antes de subir la v3.0, borra estos archivos de la versión anterior:

```bash
# 🗑️ Archivos Python antiguos
rm -f *.py
rm -rf src/
rm -rf utils/

# 🗑️ Configuraciones viejas
rm -f requirements*.txt
rm -f lune_config.json
rm -f integrate_ollama.py
rm -f verificar_instalacion.py

# 🗑️ Documentación antigua
rm -f SETUP_OLLAMA.md
rm -f GUIA_RAPIDA.md
rm -f *.md

# 🗑️ Archivos temporales
rm -rf __pycache__/
rm -rf *.pyc
rm -rf .pytest_cache/
```

---

## 🐛 Solución de Problemas Comunes

### "Ollama no responde"
```bash
# Verificar que Ollama esté corriendo
curl http://localhost:11434/api/tags

# Si no responde, inicia Ollama:
ollama serve
```

### "Error de Node.js"
```bash
# Asegúrate de tener Node.js 18+
node --version

# Si es menor a 18, actualiza desde nodejs.org
```

### "La ventana no abre"
```bash
# Limpia caché de Next.js
rm -rf .next

# Reinstala dependencias
npm install

# Reinicia en modo desarrollo
npm run electron-dev
```

### "Error de dependencias"
```bash
# Instala todo desde cero
rm -rf node_modules package-lock.json
npm install
```

---

## 🎯 Comandos Disponibles

### Para Desarrollo
```bash
npm run electron-dev    # Inicia app en modo desarrollo
npm run dev            # Solo servidor web
npm run electron       # Solo ventana de Electron
```

### Para Producción
```bash
npm run build          # Compila para producción
npm run dist           # Crea instalador ejecutable
npm start              # Inicia versión compilada
```

### Mantenimiento
```bash
npm run lint           # Revisa calidad de código
```

---

## 🌟 Características Técnicas

### ✅ Funcionalidades Principales
- **🤖 Chat Inteligente** con Ollama local
- **💻 Integración con Sistema Operativo**
- **🎨 Interfaz de Videojuego Impresionante**
- **🌙 Mascota de Escritorio Animada**
- **⚡ Ultra Rápido y Optimizado**
- **🔒 100% Privado y Offline**
- **🎮 Efectos Visuales y Animaciones**
- **💬 Memoria Conversacional**

### 🛠️ Tecnología
- **Frontend**: Next.js 15 + React 19
- **Estilos**: Tailwind CSS 4 + Animaciones CSS
- **Escritorio**: Electron 39
- **Chat**: Ollama + chat.z.ai
- **Tipado**: TypeScript 5

---

## 🤝 ¿Cómo Contribuir?

¡Las contribuciones son bienvenidas! 

1. **Fork** el proyecto
2. Crea una **rama** para tu feature (`git checkout -b feature/nueva-funcion`)
3. **Commitea** tus cambios (`git commit -am 'Agregar nueva función'`)
4. **Push** a la rama (`git push origin feature/nueva-funcion`)
5. Abre un **Pull Request**


---

## 🙏 Agradecimientos Especiales

- **Ollama Team** - Por hacer la IA local accesible para todos
- **chat.z.ai** - Por el API increíble para programación
- **Electron** - Por permitir crear apps de escritorio increíbles
- **Next.js** - Por el framework web más rápido del mundo
- **Vercel** - Por mantener Next.js increíble

---

## 🎉 ¡Disfruta Lune CD v3.0!

Esta versión es una reescritura completa que lleva la experiencia de Lune a un nivel completamente nuevo. 

**¡Es más rápido, más bonito y más inteligente que nunca!** 🚀

---


### 🌙 Hecho con ❤️ para hacerte la vida más fácil y divertida

**Versión 3.0** - La revolucion de la reescritura

**¿Problemas?** siempre pero tenemos soluciones

</div>