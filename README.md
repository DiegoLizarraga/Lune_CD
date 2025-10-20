# 🌙 Lune CD: Tu Asistente Virtual de Escritorio

Lune CD no es solo una adorable mascota de escritorio; es un asistente virtual inteligente diseñado para integrarse profundamente en tu flujo de trabajo. Inspirado en aplicaciones como Shimeji y Phase Pal, Lune CD combina la interacción visual de una mascota con la potencia de un agente de IA capaz de automatizar tareas, recordar información y ayudarte con tu día a día directamente desde tu escritorio.
<img width="1024" height="1024" alt="lunecd" src="https://github.com/user-attachments/assets/0866ba0c-f943-4796-ba16-25fcfbdbf7b2" />

---

## ✨ Características Principales

- **🎨 Mascota de Escritorio Animada**: Interactúa con Lune a través de clics y observa sus animaciones (feliz, normal, hablando)
- **💬 Chatbot Integrado (Groq API)**: Mantén conversaciones naturales con un potente modelo de lenguaje (Llama 3) directamente desde tu terminal
- **🖥️ Integración con el Sistema Operativo**: Abre aplicaciones como Visual Studio Code, tu navegador o la calculadora con simples comandos de voz o texto
- **📝 Gestión de Notas y Recordatorios**: Toma notas rápidas y establece recordatorios inteligentes que Lune te notificará en el momento indicado
- **👁️ Análisis de Pantalla Inteligente (OCR)**: Lune monitorea tu pantalla (con tu permiso) y puede recordar temas importantes que veas
- **🔔 Sistema de Notificaciones**: Recibe notificaciones del sistema para tus recordatorios y alertas importantes
- **🧩 Arquitectura Modular**: Código bien organizado en módulos independientes, facilitando la extensión y el mantenimiento

---

## 🗺️ Roadmap del Proyecto

### ✅ Completado
- Conexión con APIs de Groq
- Creación de chatbot simple con interfaz de terminal
- Sistema básico de mascota de escritorio

### 🚧 En Desarrollo (Corto Plazo)
- Mejora de herramientas de asistencia al usuario
- Optimización del sistema de notas y recordatorios
- Refinamiento de la interfaz de usuario

### 🎯 Planeado (Mediano Plazo)
- Sistema de banco de datos personales (memoria a largo plazo)
- Comando específico para invocación en segundo plano
- Conexión con servicios web e Internet de las Cosas (IoT)
- Integración con más aplicaciones del sistema
- Modo de voz para interacción manos libres

---

## 📁 Estructura del Proyecto

```
Lune_CD/
├── main.py                 # Punto de entrada principal
├── lune_config.json        # Archivo de configuración
├── requirements.txt        # Dependencias del proyecto
├── modules/
│   ├── chatbot.py         # Lógica del chatbot con Groq
│   ├── ui.py              # Interfaz de la mascota
│   ├── tools.py           # Herramientas del sistema
│   ├── notes.py           # Sistema de notas
│   ├── reminders.py       # Sistema de recordatorios
│   ├── screen_monitor.py  # Monitoreo de pantalla (OCR)
│   └── notifications.py   # Sistema de notificaciones
└── assets/
    └── images/            # Sprites de Lune
```

---

## 🚀 Instalación y Configuración

### Prerrequisitos

- Python 3.8 o superior
- Git
- Tesseract OCR (para el análisis de pantalla)

### 1. Clonar el Repositorio

```bash
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD
```

### 2. Crear un Entorno Virtual (Recomendado)

```bash
# Crear entorno virtual
python -m venv venv

# Activar en Windows
venv\Scripts\activate

# Activar en macOS/Linux
source venv/bin/activate
```

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4. Instalar Tesseract OCR

Esta dependencia es crucial para la funcionalidad de análisis de pantalla.

**Windows**: 
- Descarga el instalador desde la [página oficial de Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- Asegúrate de marcar la opción para añadir Tesseract al PATH durante la instalación

**macOS**: 
```bash
brew install tesseract
```

**Linux (Debian/Ubuntu)**:
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa
```

### 5. Configurar tu API Key de Groq

1. Obtén tu API Key gratuita en [Groq Console](https://console.groq.com)
2. Abre el archivo `lune_config.json` (se creará la primera vez que ejecutes la app)
3. Reemplaza `"TU_API_KEY_AQUI"` con tu clave real:

```json
{
    "api_key": "gsk_tu_clave_real_aqui",
    "model": "llama3-8b-8192",
    ...
}
```

---

## 💻 Cómo Usar Lune CD

### Ejecutar la Aplicación

Una vez configurado, simplemente ejecuta:

```bash
python main.py
```

Verás a Lune en tu pantalla y se iniciará una sesión de chat en tu terminal.

### Comandos Disponibles

Puedes interactuar con Lune escribiendo en la terminal. Aquí tienes algunos ejemplos:

| Comando | Descripción |
|---------|-------------|
| `abre el compilador` | Abre Visual Studio Code |
| `abre el navegador` | Abre tu navegador web por defecto |
| `toma nota comprar leche` | Guarda una nota rápida |
| `lista mis notas` | Muestra todas tus notas guardadas |
| `recuérdame la reunión a las 15:00` | Programa un recordatorio |
| `recuérdame llamar a mamá en 30 minutos` | Programa un recordatorio relativo |
| `busca en pantalla tarea` | Busca un tema en el historial de pantalla |
| `información del sistema` | Muestra datos sobre tu PC |
| `salir` | Cierra la sesión de chat |

### Atajos de Teclado

- **Ctrl + T**: Abre o enfoca la terminal de chat
- **Ctrl + N**: Haz que Lune sonría por un momento
- **Ctrl + Q**: Cierra la aplicación por completo

---

## ⚙️ Configuración

Puedes personalizar el comportamiento de Lune CD editando el archivo `lune_config.json`:

```json
{
    "screen_monitoring": {
        "enabled": true,
        "interval": 300
    },
    "notifications": {
        "duration": 5,
        "sound_enabled": true
    },
    "reminders": {
        "check_interval": 60
    },
    "ui": {
        "size": 128,
        "initial_position": [100, 100]
    }
}
```

### Opciones de Configuración

- **screen_monitoring**: Activa/desactiva el monitoreo de pantalla y ajusta el intervalo
- **notifications**: Configura la duración y si quieres sonido en las notificaciones
- **reminders**: Ajusta la frecuencia con la que se comprueban los recordatorios
- **ui**: Cambia el tamaño o la posición inicial de la mascota

---

## 🤝 Cómo Contribuir

¡Las contribuciones son lo que hace que la comunidad de código abierto sea un lugar increíble para aprender, inspirar y crear! Cualquier contribución que hagas será **muy apreciada**.

1. Haz un Fork del proyecto
2. Crea tu Rama de Funcionalidad (`git checkout -b feature/FuncionIncreible`)
3. Haz Commit de tus Cambios (`git commit -m 'Añadiendo una Función Increíble'`)
4. Haz Push a la Rama (`git push origin feature/FuncionIncreible`)
5. Abre un Pull Request

---

## 🙏 Agradecimientos

- A **Groq** por proporcionar una API increíblemente rápida y accesible para modelos de lenguaje
- A **Hatsune Miku** por ser la inspiración detrás de este proyecto 💙🎤
- A la comunidad de código abierto por las increíbles herramientas que hacen posible este proyecto

  
### 🌙 ¿Te gusta Lune CD? ¡Dale una estrella! ⭐

</div>
