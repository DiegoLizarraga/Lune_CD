# 🌙 Lune CD v4.0 - Mascota Virtual de Escritorio en Python

¡Bienvenido a la versión 4.0 de Lune CD! Esta es una transformación completa a una **verdadera mascota virtual de escritorio** usando Python puro.

<img width="1024" height="1024" alt="lunecd" src="https://github.com/user-attachments/assets/0866ba0c-f943-4796-ba16-25fcfbdbf7b2" />

---

## ✨ ¿Qué hay de nuevo en la v4.0?

### 🔄 Cambios Revolucionarios desde la v3.0

| Característica | Versión 3.0 (Web) | Versión 4.0 (Desktop) |
|----------------|-------------------|----------------------|
| **Tecnología** | Next.js + Electron | Python puro + PyQt6 |
| **Interfaz** | Menú web | Mascota flotante nativa |
| **Instalación** | npm + Node.js | pip + Python |
| **Rendimiento** | Rápido | Ultra ligero y eficiente |
| **Mascota** | HTML en ventana | Sprite nativo siempre visible |
| **Chat** | Navegador integrado | Ventana nativa flotante |
| **Tamaño** | ~300MB (con Node) | ~50MB (solo Python) |

### 🆕 Novedades Revolucionarias

- **🎨 Mascota Siempre Visible**: Sprite flotante que permanece sobre todas las ventanas
- **🖱️ Completamente Interactiva**: Arrastra, haz click, menú contextual
- **💬 Chat Nativo**: Ventana de chat moderna y ligera
- **🤖 Dual AI**: Groq API o Ollama local a tu elección
- **⚙️ Configuración Fácil**: Panel de configuración intuitivo
- **🎭 Animaciones Fluidas**: Rebotes, saludos y reacciones
- **🪶 Ultra Ligera**: Consume mínimos recursos del sistema
- **🔧 100% Python**: Sin necesidad de Node.js ni dependencias web

---

## 🚀 Instalación Súper Fácil

### Requisitos Mínimos
- **Python 3.8+** - [Descargar aquí](https://www.python.org/downloads/)
- **Ollama** (opcional) - [Descargar aquí](https://ollama.ai)
- **Groq API Key** (opcional) - [Obtener aquí](https://console.groq.com)

### Pasos para Instalar

#### 1️⃣ Clonar el Repositorio
```bash
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD
```

#### 2️⃣ Crear Entorno Virtual
```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

#### 3️⃣ Instalar Dependencias
```bash
pip install -r requirements.txt
```

#### 4️⃣ Crear Assets Temporales
```bash
python create_temp_assets.py
```

#### 5️⃣ Configurar API (Opcional)

**Opción A: Usar Groq API (Recomendado para inicio rápido)**
1. Ve a [console.groq.com](https://console.groq.com)
2. Crea una cuenta gratuita
3. Genera una API Key
4. Al ejecutar Lune, ve a Configuración y pega tu API Key

**Opción B: Usar Ollama Local (100% Offline)**
```bash
# Instalar Ollama
# Windows: Descarga desde https://ollama.ai/download/windows
# Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Descargar modelo
ollama pull llama2

# Iniciar Ollama
ollama serve
```

#### 6️⃣ ¡Ejecutar Lune!
```bash
python main.py
```

¡Listo! Verás a Lune flotando en tu escritorio. 🎉

---

## 🎮 ¿Cómo Usar Lune v4.0?

### Mascota Flotante Interactiva

Lune aparecerá como una adorable esfera en tu escritorio:

- **🖱️ Click Izquierdo** - Abre la ventana de chat
- **🖱️ Click Derecho** - Menú de opciones
- **👆 Arrastrar** - Mueve a Lune donde quieras
- **🎭 Animaciones Automáticas** - Lune se mueve y reacciona sola

### Menú Contextual

Click derecho en Lune para acceder a:
- **💬 Abrir Chat** - Conversa con Lune
- **⚙️ Configuración** - Cambia entre Groq y Ollama
- **ℹ️ Acerca de** - Información de la versión
- **❌ Salir** - Cierra Lune

### Ventana de Chat

Chat moderno con interfaz minimalista:
- **Mensajes burbujeantes** - Diseño tipo WhatsApp
- **Procesamiento en segundo plano** - No se congela
- **Historial de conversación** - Lune recuerda el contexto
- **Indicador de escritura** - Sabes cuando Lune está pensando

### Configuración Dual AI

En el panel de configuración puedes:
1. **Elegir proveedor**: Groq API o Ollama Local
2. **Configurar Groq**: Ingresa tu API Key
3. **Configurar Ollama**: URL del servidor local
4. **Guardar cambios**: Se aplican instantáneamente

---

## 🗂️ Estructura del Proyecto v4.0

```
Lune_Desktop/
├── 📄 main.py                      # Punto de entrada principal
├── 📄 requirements.txt             # Dependencias Python
├── 📄 config.json                  # Configuración (auto-generado)
├── 📄 create_temp_assets.py        # Generador de sprites temporales
│
├── 📁 src/                         # Código fuente
│   ├── 📁 ui/                      # Interfaces gráficas
│   │   ├── pet_window.py          # Ventana de la mascota flotante
│   │   ├── chat_window.py         # Ventana de chat
│   │   └── settings_window.py     # Panel de configuración
│   │
│   ├── 📁 ai/                      # Manejadores de IA
│   │   ├── ai_manager.py          # Gestor principal de IA
│   │   ├── groq_handler.py        # Handler de Groq API
│   │   └── ollama_handler.py      # Handler de Ollama
│   │
│   ├── 📁 assets/                  # Recursos visuales
│   │   ├── images/                # Sprites de Lune
│   │   ├── animations/            # GIFs animados
│   │   └── sounds/                # Efectos de sonido
│   │
│   └── 📁 utils/                   # Utilidades
│       ├── config.py              # Gestor de configuración
│       └── tray_icon.py           # Icono de bandeja (futuro)
│
└── 📄 README.md                    # Este archivo
```

---

## 🎨 Personalización

### Crear tus propios sprites

Los sprites temporales son simples círculos de colores. Para crear los tuyos:

1. **Edita `create_temp_assets.py`** para cambiar colores
2. **O reemplaza** los archivos PNG en `src/assets/images/`
3. **Dimensiones recomendadas**: 150x150 píxeles con transparencia

### Sprites que puedes personalizar:
- `lune_idle.png` - Estado en reposo (morado)
- `lune_wave.png` - Saludando (púrpura)
- `lune_talking.png` - Hablando (rosa)
- `lune_thinking.png` - Pensando (lila)
- `lune_happy.png` - Feliz (naranja)

---

## 🐛 Solución de Problemas Comunes

### "ModuleNotFoundError: No module named 'PyQt6'"
```bash
# Asegúrate de tener el entorno virtual activado
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Reinstala dependencias
pip install -r requirements.txt
```

### "No se pueden crear los sprites"
```bash
# Instala Pillow manualmente
pip install Pillow

# Ejecuta el generador de nuevo
python create_temp_assets.py
```

### "Groq API: Error de conexión"
```bash
# Verifica tu API Key en Configuración
# Asegúrate de tener conexión a internet
# La API Key debe ser válida y activa
```

### "Ollama: No se puede conectar"
```bash
# Verifica que Ollama esté corriendo
curl http://localhost:11434/api/tags

# Si no responde, inicia Ollama:
ollama serve

# En otra terminal, verifica el modelo:
ollama list
```

### "La mascota no aparece"
```bash
# Verifica que se crearon los sprites
dir src\assets\images\  # Windows
ls src/assets/images/   # Linux/Mac

# Si no existen, regenera:
python create_temp_assets.py
```

### "Error: Python version too old"
```bash
# Verifica tu versión de Python
python --version

# Debe ser 3.8 o superior
# Actualiza desde python.org si es necesario
```

---

## 🎯 Comandos y Scripts Útiles

### Desarrollo
```bash
# Iniciar Lune
python main.py

# Regenerar sprites
python create_temp_assets.py

# Limpiar cache
# Windows:
del /s /q __pycache__
# Linux/Mac:
find . -type d -name __pycache__ -exec rm -r {} +
```

### Crear Ejecutable (PyInstaller)
```bash
# Instalar PyInstaller
pip install pyinstaller

# Crear ejecutable
pyinstaller --onefile --windowed --icon=src/assets/images/lune_idle.png main.py

# El ejecutable estará en dist/
```

---

## 🌟 Características Técnicas

### ✅ Funcionalidades Principales
- **🎨 Mascota Flotante Nativa** - Siempre visible sobre otras ventanas
- **💬 Chat Inteligente Dual** - Groq API o Ollama local
- **🖱️ Interacción Completa** - Click, drag, menú contextual
- **⚙️ Configuración GUI** - Panel visual fácil de usar
- **🎭 Animaciones Suaves** - Rebotes y movimientos naturales
- **💾 Persistencia** - Guarda configuración automáticamente
- **🔒 100% Privado** - Opción Ollama completamente offline
- **🪶 Ligera** - Consume <100MB de RAM
- **🚀 Rápida** - Inicio en <3 segundos

### 🛠️ Stack Tecnológico
- **Framework UI**: PyQt6 (Cross-platform)
- **IA API**: Groq (Cloud) / Ollama (Local)
- **HTTP Client**: requests / httpx
- **Image Processing**: Pillow (PIL)
- **Config Management**: JSON nativo
- **Threading**: QThread (non-blocking)

---

## 🔮 Roadmap - Próximas Características

### v4.1 (Próximamente)
- [ ] 🔊 **Reconocimiento de Voz** - Habla con Lune
- [ ] 🎵 **Efectos de Sonido** - Respuestas auditivas
- [ ] 🖼️ **Más Animaciones** - Sprites en movimiento
- [ ] 📌 **Icono en Bandeja** - Minimizar a system tray
- [ ] 🎨 **Temas Personalizables** - Colores y estilos

### v4.2 (Futuro)
- [ ] 🤝 **Múltiples Mascotas** - Varias instancias
- [ ] 📅 **Recordatorios** - Lune te avisa de tareas
- [ ] 📊 **Estadísticas** - Trackea tus conversaciones
- [ ] 🌐 **Más Proveedores IA** - OpenAI, Anthropic, etc.
- [ ] 🎮 **Mini Juegos** - Juega con Lune

---

## 🤝 ¿Cómo Contribuir?

¡Las contribuciones son muy bienvenidas! 

### Formas de contribuir:
1. **🎨 Crear sprites mejores** - Diseña sprites profesionales
2. **🐛 Reportar bugs** - Abre un issue detallado
3. **💡 Sugerir features** - Comparte tus ideas
4. **📝 Mejorar documentación** - Ayuda con el README
5. **🔧 Enviar código** - Haz un Pull Request

### Proceso:
1. **Fork** el proyecto
2. Crea una **rama** (`git checkout -b feature/nueva-funcion`)
3. **Commitea** tus cambios (`git commit -am 'Agregar X'`)
4. **Push** a la rama (`git push origin feature/nueva-funcion`)
5. Abre un **Pull Request**

---

## 📜 Historial de Versiones

### v4.0 (Actual) - "Desktop Native"
- 🎉 Reescritura completa en Python puro
- 🎨 Mascota flotante nativa en PyQt6
- 💬 Sistema de chat moderno
- 🤖 Dual AI: Groq + Ollama
- ⚙️ Panel de configuración GUI

### v3.0 - "Web Revolution"
- ⚡ Next.js + Electron
- 🎮 Menú estilo videojuego
- 💻 Aplicación web de escritorio

### v2.0 - "Python Origins"
- 🐍 Python + Tkinter
- 💬 Chat básico en terminal
- 🤖 Ollama local


## 🙏 Agradecimientos Especiales

- **PyQt Team** - Por el increíble framework multiplataforma
- **Ollama Team** - Por democratizar la IA local
- **Groq** - Por su API ultrarrápida y generosa
- **Python Community** - Por las herramientas increíbles
- **Pillow Team** - Por el procesamiento de imágenes

-

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active-success.svg)

**⭐ Si te gusta Lune, regálanos una estrella en GitHub ⭐**

</div>
