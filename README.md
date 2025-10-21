# 🌙 Lune CD: Tu Asistente Virtual de Escritorio

Lune CD no es solo una adorable mascota de escritorio; es un asistente virtual inteligente diseñado para integrarse profundamente en tu flujo de trabajo. Inspirado en aplicaciones como Shimeji y Phase Pal, Lune CD combina la interacción visual de una mascota con la potencia de un agente de IA capaz de automatizar tareas, recordar información y ayudarte con tu día a día directamente desde tu escritorio.
<img width="1024" height="1024" alt="lunecd" src="https://github.com/user-attachments/assets/0866ba0c-f943-4796-ba16-25fcfbdbf7b2" />

<img width="1024" height="1024" alt="lunecd" src="https://github.com/user-attachments/assets/0866ba0c-f943-4796-ba16-25fcfbdbf7b2" />

---

## ✨ Características Principales

- **Mascota de Escritorio Animada**: Interactúa con Lune a través de clics y observa sus animaciones (feliz, normal, hablando)
- **IA Local con Ollama + LangChain**: Conversaciones naturales e inteligentes con modelos de lenguaje corriendo 100% en tu PC (sin enviar datos a la nube)
- **Fallback Inteligente**: Si Ollama no está disponible, usa un modelo basado en reglas para seguir funcionando
- **Terminal de Chat Integrada**: Interfaz de terminal limpia y moderna con atajos de teclado globales
- **Integración con el Sistema Operativo**: Abre aplicaciones como Visual Studio Code, navegador o calculadora con comandos simples
- **Gestión de Notas y Recordatorios**: Toma notas rápidas y establece recordatorios inteligentes con notificaciones del sistema
- **Búsqueda Web Privada**: Búsquedas en DuckDuckGo que respetan tu privacidad (sin rastreadores)
- **Análisis de Pantalla Inteligente (OCR)**: Lune monitorea tu pantalla (con tu permiso) y puede recordar temas importantes que veas
- **Calculadora Integrada**: Resuelve expresiones matemáticas al instante
- **Sistema de Notificaciones**: Notificaciones nativas del sistema para recordatorios y alertas importantes
- **Arquitectura Modular**: Código bien organizado y fácil de extender

---

## ¿Qué hay de nuevo?

### ✨ Versión 2.0 - IA Local con Ollama

La nueva versión incluye una integración completa con **Ollama** y **LangChain**, llevando las capacidades de Lune a un nivel completamente nuevo:

#### Antes vs Ahora

| Aspecto | Versión 1.0 (Groq API) | Versión 2.0 (Ollama) |
|---------|------------------------|----------------------|
| **Privacidad** | Datos enviados a la nube | 100% local, cero datos externos |
| **Costo** | Límites de API gratuita | Completamente gratis, sin límites |
| **Conexión** | Requiere internet constante | Funciona sin internet |
| **Calidad** | Excelente | Excelente (modelos similares) |
| **Memoria** | No recuerda conversaciones | Recuerda últimas 5 interacciones |
| **Personalización** | Limitada | Totalmente personalizable |
| **Modelos** | Llama 3 (8B) | Múltiples: Llama 3.x, Mistral, Phi, etc. |

#### Ventajas Clave

✅ **100% Privado**: Todas tus conversaciones permanecen en tu PC  
✅ **Sin Límites**: Usa Lune cuanto quieras, sin restricciones de tokens  
✅ **Sin Conexión**: Funciona offline (excepto para búsquedas web)  
✅ **Memoria Conversacional**: Lune recuerda el contexto de la charla  
✅ **Respuestas Naturales**: Conversaciones más fluidas e inteligentes  
✅ **Múltiples Modelos**: Elige el modelo que mejor se adapte a tu hardware  

---

##  Roadmap del Proyecto

### ✅ Completado

- ✅ Sistema de chatbot inteligente
- ✅ Integración con Ollama + LangChain
- ✅ Mascota de escritorio animada
- ✅ Sistema de notas y recordatorios
- ✅ Búsqueda web privada (DuckDuckGo)
- ✅ Análisis de pantalla con OCR
- ✅ Terminal de chat con atajos globales
- ✅ Notificaciones del sistema
- ✅ Calculadora integrada
- ✅ Fallback automático a modelo de reglas

### 🚧 En Desarrollo (Corto Plazo)

- 🔄 RAG (Retrieval Augmented Generation) para memoria a largo plazo
- 🔄 Sistema de plugins para funcionalidades personalizadas
- 🔄 Interfaz gráfica mejorada con Tkinter/Qt
- 🔄 Modo compacto y modo expandido para la mascota
- 🔄 Temas visuales personalizables

### 🎯 Planeado (Mediano/Largo Plazo)

- 📅 Integración con calendarios (Google Calendar, Outlook)
- 🎤 Comando por voz (Speech-to-Text local)
- 🌐 Conexión con servicios web e IoT
- 📊 Dashboard de productividad
- 🔐 Cifrado de notas sensibles
- 🤝 Sincronización entre dispositivos (opcional)
- 🎨 Editor visual de personalidad de Lune
- 🧠 Sistema de aprendizaje de preferencias del usuario

---

## Instalación y Configuración

### Prerrequisitos

- **Python 3.8 o superior**
- **Git** (opcional, para clonar el repo)
- **Tesseract OCR** (para análisis de pantalla)
- **Ollama** (para IA local) - [Descargar aquí](https://ollama.com/download)

---

### 📦 Método 1: Instalación Completa con Ollama (Recomendado)

#### 1. Clonar el Repositorio

```bash
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD
```

#### 2. Crear un Entorno Virtual

```bash
# Crear entorno virtual
python -m venv venv

# Activar en Windows
venv\Scripts\activate

# Activar en macOS/Linux
source venv/bin/activate
```

#### 3. Instalar Ollama

**Windows:**
- Descarga el instalador: https://ollama.com/download/windows
- Ejecuta el instalador
- Ollama se iniciará automáticamente

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 4. Descargar un Modelo de IA

Elige según tu hardware:

```bash
# Para PC con 4-6GB RAM (ligero y rápido)
ollama pull phi3:mini

# Para PC con 8-12GB RAM (RECOMENDADO - balance ideal)
ollama pull llama3.2:3b

# Para PC con 16GB+ RAM (mejor calidad)
ollama pull llama3.1:8b

# Para mejor soporte en español
ollama pull nous-hermes2
```

Verifica que se descargó:
```bash
ollama list
```

#### 5. Instalar Dependencias de Python

```bash
pip install -r requirements_enhanced.txt
```

#### 6. Instalar Tesseract OCR

**Windows:**
- Descarga: https://github.com/UB-Mannheim/tesseract/wiki
- Marca la opción "Add to PATH" durante la instalación

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa
```

#### 7. Ejecutar Script de Integración (Opcional)

```bash
python integrate_ollama.py
```

Este script verificará todo automáticamente y actualizará los archivos necesarios.

#### 8. Verificar Instalación

```bash
python verificar_instalacion.py
```

#### 9. ¡Ejecutar Lune!

```bash
python main.py
```

Deberías ver:
```
✅ Modelo Ollama 'llama3.2:3b' inicializado correctamente
Atajos de teclado globales configurados:
- Ctrl+T: Mostrar/ocultar terminal
- Ctrl+Q: Cerrar aplicación
```

---

### 📦 Método 2: Instalación Básica (Sin Ollama)

Si no quieres usar Ollama o tienes una PC con pocos recursos, Lune funcionará con el modelo de respaldo basado en reglas:

```bash
# 1. Clonar repositorio
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Instalar dependencias básicas
pip install -r requirements.txt

# 4. Ejecutar
python main.py
```

> **Nota:** Sin Ollama, Lune usará respuestas predefinidas. Para la experiencia completa, se recomienda instalar Ollama.

---

## 💻 Cómo Usar Lune CD

### Iniciar Lune

```bash
python main.py
```

### Atajos de Teclado Globales

- **Ctrl + T**: Mostrar/ocultar terminal de chat
- **Ctrl + Q**: Cerrar Lune completamente
- **Ctrl + N**: Hacer que Lune sonría (cuando está visible)

### Comandos Disponibles

####  Búsqueda Web
```
busca recetas de pasta
qué es la fotosíntesis
información sobre Python
```

#### Control de Aplicaciones
```
abre vscode
abre el navegador
abre calculadora
inicia explorador de archivos
```

####  Gestión de Notas
```
toma nota reunión importante mañana a las 10am
lista mis notas
busca nota reunión
```

####  Recordatorios
```
recuérdame llamar a Juan a las 15:00
recuérdame la reunión en 30 minutos
avisame tomar medicina mañana a las 08:00
```

####  Matemáticas
```
calcula 25 * 4 + 10
cuánto es (100 + 50) / 3
resuelve 15 * (8 + 2)
```

####  Sistema
```
información del sistema
estado del sistema
```

####  Control de Chat
```
ayuda          # Muestra comandos disponibles
limpiar        # Borra historial de chat
salir          # Cierra la sesión de chat
```

###  Conversación Natural (Con Ollama)

Con Ollama instalado, puedes hablar naturalmente:

```
Tú: Hola Lune, ¿cómo estás?
Lune: ¡Hola! Estoy funcionando perfectamente. ¿En qué puedo ayudarte hoy?

Tú: Necesito organizarme mejor
Lune: Puedo ayudarte con eso. Tengo herramientas para tomar notas y crear 
recordatorios. ¿Qué tienes pendiente hoy?

Tú: Tengo que terminar un informe y llamar al dentista
Lune: Perfecto. Vamos a organizarlo:
1. Para el informe: toma nota terminar informe urgente
2. Para el dentista: recuérdame llamar al dentista a las [hora]
¿A qué hora quieres que te recuerde lo del dentista?
```

---

## ⚙️ Configuración

Edita `lune_config.json` para personalizar Lune:

```json
{
    "screen_monitoring": {
        "enabled": true,
        "interval": 60,
        "save_screenshots": false
    },
    "notifications": {
        "enabled": true,
        "duration": 5,
        "sound": false
    },
    "reminders": {
        "enabled": true,
        "check_interval": 30
    },
    "ui": {
        "position": "bottom-left",
        "size": 170,
        "always_on_top": true
    }
}
```

### Opciones Principales

| Opción | Descripción | Valores |
|--------|-------------|---------|
| `screen_monitoring.enabled` | Activa monitoreo de pantalla | `true` / `false` |
| `screen_monitoring.interval` | Frecuencia de captura (segundos) | `30` - `600` |
| `notifications.enabled` | Activa notificaciones | `true` / `false` |
| `notifications.duration` | Duración de notificaciones (seg) | `3` - `10` |
| `reminders.check_interval` | Frecuencia de check recordatorios | `15` - `60` |
| `ui.size` | Tamaño de la mascota (píxeles) | `100` - `250` |
| `ui.position` | Posición inicial | `"bottom-left"`, `"bottom-right"`, `"top-left"`, `"top-right"` |

---

### "Ollama no está corriendo"

```bash
# Verificar si Ollama está instalado
ollama --version

# Iniciar Ollama manualmente
ollama serve
```

### "Model not found"

```bash
# Ver modelos instalados
ollama list

# Descargar un modelo
ollama pull llama3.2:3b
```

### "Import Error: enhanced_model"

Verifica que `enhanced_model.py` esté en la carpeta del proyecto y que actualizaste `main.py` correctamente.

### "Respuestas muy lentas"

1. Usa un modelo más pequeño: `phi3:mini`
2. Cierra otras aplicaciones
3. Verifica RAM disponible con `información del sistema`

### "Atajos de teclado no funcionan"

Ejecuta como administrador (Windows) o con permisos elevados (Linux/Mac).

### Script de Verificación

```bash
python verificar_instalacion.py
```

Este script te dirá exactamente qué está mal y cómo solucionarlo.

---

## 📚 Documentación Adicional

- **[SETUP_OLLAMA.md](SETUP_OLLAMA.md)** - Guía detallada de instalación de Ollama
- **[GUIA_RAPIDA.md](GUIA_RAPIDA.md)** - Guía de inicio rápido
- **[Documentación de Ollama](https://github.com/ollama/ollama)** - Documentación oficial
- **[Documentación de LangChain](https://python.langchain.com/)** - Framework de IA

---
## Agradecimientos :D

- **Ollama Team** por crear una herramienta increíble para ejecutar LLMs localmente
- **LangChain** por el framework que hace la integración de IA más sencilla
- **Hatsune Miku** por ser la inspiración detrás de este proyecto 💙🎤 (a ver si esto se queda para las siguientes versiones)
- **La comunidad de código abierto** por las increíbles herramientas que hacen posible este proyecto
- **DuckDuckGo** por proporcionar búsquedas web que respetan la privacidad

---

## ⭐ Si te gusta Lune CD


<div align="center">

### 🌙 Desarrollado con ❤️ para hacerte más productivo

**Versión 2.0** - Ahora con IA local y privada

</div>
