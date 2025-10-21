# 🚀 Guía de Inicio Rápido - Lune con Ollama

## Paso 1: Descargar un Modelo de IA (IMPORTANTE)

Abre tu terminal/CMD y ejecuta:

```bash
# Para PC normales (8GB+ RAM) - RECOMENDADO
ollama pull llama3.2:3b

# O para PC con poca RAM (4-6GB)
ollama pull phi3:mini

# O para mejor calidad en español (8GB+ RAM)
ollama pull nous-hermes2
```

**Espera a que termine de descargar** (puede tardar 5-10 minutos dependiendo de tu internet).

Para verificar que se descargó correctamente:
```bash
ollama list
```

Deberías ver tu modelo en la lista.

---

## Paso 2: Verificar que Ollama está corriendo

```bash
# Verificar el servicio
ollama serve
```

Si dice "Error: listen tcp :11434: bind: address already in use" es BUENO, significa que ya está corriendo.

Si no arranca automáticamente:
- **Windows**: Busca "Ollama" en el menú inicio y ábrelo
- **Mac/Linux**: Ejecuta `ollama serve` en una terminal y déjala abierta

---

## Paso 3: Instalar Dependencias de Python

En la carpeta de tu proyecto Lune, ejecuta:

```bash
# Instalar dependencias nuevas
pip install langchain langchain-community ollama-python httpx pydantic

# O instalar todo desde el archivo
pip install -r requirements_enhanced.txt
```

---

## Paso 4: Añadir el archivo enhanced_model.py

1. **Copia el código de `enhanced_model.py`** que te proporcioné
2. **Guárdalo** en la misma carpeta donde está tu `main.py`
3. El archivo debe llamarse exactamente: `enhanced_model.py`

---

## Paso 5: Actualizar main.py

Abre `main.py` y busca esta línea (aproximadamente línea 12):

```python
from local_model import LocalModel
```

**Cámbiala por:**
```python
from enhanced_model import EnhancedLocalModel
```

Luego busca esta línea (aproximadamente línea 76):
```python
self.local_model = LocalModel()
```

**Cámbiala por:**
```python
self.local_model = EnhancedLocalModel(
    model_name="llama3.2:3b",  # O el modelo que descargaste
    use_ollama=True
)
```

**Guarda el archivo.**

---

## Paso 6: ¡Ejecutar Lune!

```bash
python main.py
```

O si tienes Python 3:
```bash
python3 main.py
```

---

## 🎯 ¿Qué Verás?

### Al iniciar, deberías ver algo como:

```
✅ Modelo Ollama 'llama3.2:3b' inicializado correctamente
Atajos de teclado globales configurados:
- Ctrl+T: Mostrar/ocultar terminal
- Ctrl+Q: Cerrar aplicación
```

### Si ves esto, hay un problema:
```
⚠️ Ollama no está corriendo. Inicia Ollama con: ollama serve
✅ Modelo de respaldo (reglas) inicializado
```

**Solución:** Abre otra terminal y ejecuta `ollama serve`, luego reinicia Lune.

---

## 🗣️ Cómo Usar Lune

### 1. Mostrar la ventana de chat
Presiona `Ctrl+T` o la ventana aparecerá automáticamente.

### 2. Ejemplos de conversación mejorada

**ANTES (modelo de reglas):**
```
Tú: ¿cómo puedo ser más productivo?
Lune: No estoy segura de entender. Puedes decirme 'ayuda'...
```

**AHORA (con Ollama):**
```
Tú: ¿cómo puedo ser más productivo?
Lune: Te sugiero usar mis funciones de organización. Prueba:
1. Crear notas con 'toma nota [texto]' para ideas rápidas
2. Programar recordatorios con 'recuérdame [tarea] a las [hora]'
3. Revisar tu lista con 'lista mis notas'
También puedo ayudarte a priorizar tareas si me dices qué tienes pendiente.
```

### 3. Comandos que aún funcionan

Todos los comandos originales siguen funcionando:

```bash
# Abrir aplicaciones
abre vscode
abre navegador
abre calculadora

# Notas
toma nota reunión mañana a las 10am
lista mis notas

# Recordatorios
recuérdame llamar a Juan a las 15:00
recuérdame reunión en 30 minutos

# Búsqueda web
busca recetas de pasta
qué es la fotosíntesis

# Matemáticas
calcula 25 * 4 + 10

# Sistema
información del sistema
```

### 4. Conversación natural (NUEVO)

Ahora puedes hablar naturalmente:

```
Tú: Estoy estresado con tanto trabajo
Lune: Entiendo que te sientas así. ¿Quieres que te ayude a organizar 
tus tareas? Podemos crear una lista priorizada o configurar recordatorios 
para que no se te olvide nada importante.

Tú: sí, ayúdame
Lune: Perfecto. Cuéntame, ¿qué tareas tienes pendientes? Puedo ir 
guardándolas como notas mientras hablamos.

Tú: tengo que terminar un proyecto y estudiar para un examen
Lune: De acuerdo, veo dos prioridades. ¿Para cuándo es cada una? 
Puedo crear recordatorios para que no se te pasen las fechas.
```

---

## 🎮 Atajos de Teclado

- **Ctrl+T**: Mostrar/ocultar ventana de chat
- **Ctrl+Q**: Cerrar Lune completamente
- **Enter**: Enviar mensaje

---

## 🔧 Cambiar de Modelo

Si quieres probar otro modelo, edita `main.py` donde pusiste:

```python
self.local_model = EnhancedLocalModel(
    model_name="llama3.2:3b",  # Cambia esto
    use_ollama=True
)
```

Modelos recomendados:
- `phi3:mini` - Más rápido, menos RAM
- `llama3.2:3b` - Balance ideal (RECOMENDADO)
- `llama3.1:8b` - Mejor calidad, más lento
- `nous-hermes2` - Mejor para español

---

## 🐛 Solución de Problemas

### Error: "Module 'enhanced_model' not found"
**Solución:** Verifica que `enhanced_model.py` está en la misma carpeta que `main.py`

### Error: "Ollama no está corriendo"
**Solución:** 
```bash
ollama serve
```
Deja esa terminal abierta y ejecuta Lune en otra.

### Error: "Model 'llama3.2:3b' not found"
**Solución:** Descarga el modelo:
```bash
ollama pull llama3.2:3b
```

### Respuestas muy lentas
**Soluciones:**
1. Usa un modelo más pequeño: `phi3:mini`
2. Cierra otras aplicaciones
3. Verifica que tienes suficiente RAM libre

### Respuestas en inglés
**Soluciones:**
1. Usa `nous-hermes2` que es mejor en español
2. O añade al inicio de tus mensajes: "responde en español"

### La ventana no aparece
**Solución:** Presiona `Ctrl+T`

---

## 📊 Comparación: Antes vs Después

### Pregunta: "ayúdame a organizarme"

**ANTES:**
```
Lune: No estoy segura de entender. Puedes decirme 'ayuda' para 
ver todos los comandos disponibles.
```

**AHORA:**
```
Lune: Con gusto te ayudo a organizarte. Tengo varias herramientas:

1. Notas: Guarda información importante con 'toma nota [texto]'
2. Recordatorios: Programa alertas con 'recuérdame [tarea] [hora]'
3. Lista de tareas: Ve todo con 'lista mis notas'

¿Por dónde quieres empezar? ¿Tienes algo urgente que necesites 
recordar?
```

---

## 💡 Tips de Uso

1. **Sé específico en tus preguntas** - Cuanto más contexto des, mejores respuestas obtendrás

2. **Usa comandos para acciones** - Para abrir apps o crear notas, sigue usando los comandos tradicionales

3. **Conversa para planificar** - Usa el lenguaje natural para organizar ideas y tareas

4. **Combina ambos** - Puedes conversar Y usar comandos en la misma sesión

---

## 🎯 Ejemplos de Uso Real

### Ejemplo 1: Organizar el día
```
Tú: Buenos días Lune, ¿me ayudas a organizar mi día?
Lune: ¡Buenos días! Claro que sí. Cuéntame qué tienes pendiente hoy.
Tú: Tengo reunión a las 2pm y debo terminar un informe
Lune: Perfecto. Voy a ayudarte:
- Para la reunión: recuérdame reunión importante a las 13:45
- Para el informe: toma nota terminar informe antes de las 5pm
¿Quieres que te recuerde algo más?
```

### Ejemplo 2: Búsqueda + Conversación
```
Tú: busca información sobre Python
[Lune busca en internet]
Tú: ¿y para qué sirve Python?
Lune: Python es un lenguaje de programación muy versátil. Según 
lo que encontré, se usa para desarrollo web, análisis de datos, 
inteligencia artificial, automatización y mucho más. ¿Te interesa 
aprenderlo? Puedo buscar recursos para principiantes.
```

---

## ✅ Checklist de Instalación

- [ ] Ollama instalado
- [ ] Modelo descargado (`ollama list` para verificar)
- [ ] Ollama corriendo (`ollama serve`)
- [ ] Dependencias de Python instaladas
- [ ] `enhanced_model.py` en la carpeta del proyecto
- [ ] `main.py` actualizado con los cambios
- [ ] Lune ejecutándose sin errores

---

## 🆘 ¿Necesitas Ayuda?

Si algo no funciona:

1. Verifica que completaste todos los pasos
2. Lee los mensajes de error que aparecen
3. Consulta la sección "Solución de Problemas"
4. Verifica que Ollama está corriendo: `ollama list`

---

## 🎉 ¡Listo!

Ahora tienes a Lune con capacidades de IA mejoradas. Disfruta de 
conversaciones más naturales e inteligentes, ¡todo corriendo localmente 
en tu PC!