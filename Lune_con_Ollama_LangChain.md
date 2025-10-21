# 🚀 Guía de Instalación: Lune con Ollama + LangChain

## Paso 1: Instalar Ollama

### Windows
1. Descarga Ollama desde: https://ollama.com/download/windows
2. Ejecuta el instalador
3. Ollama se iniciará automáticamente como servicio

### macOS
```bash
brew install ollama
```

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## Paso 2: Verificar que Ollama esté corriendo

```bash
# En una terminal, ejecuta:
ollama --version
```

Si ves la versión, ¡Ollama está instalado correctamente!

## Paso 3: Descargar un modelo

Elige un modelo según tu hardware:

### Para PCs con 4-6GB RAM (ligero y rápido)
```bash
ollama pull phi3:mini
```

### Para PCs con 8-12GB RAM (recomendado)
```bash
ollama pull llama3.2:3b
```

### Para PCs con 16GB+ RAM (mejor calidad)
```bash
ollama pull llama3.1:8b
```

### Para mejor soporte en español
```bash
ollama pull nous-hermes2
```

## Paso 4: Actualizar dependencias de Python

```bash
pip install -r requirements_enhanced.txt
```

## Paso 5: Actualizar main.py

Reemplaza esta línea en `main.py`:
```python
from local_model import LocalModel
```

Por:
```python
from enhanced_model import EnhancedLocalModel
```

Y cambia la inicialización:
```python
# Antes:
self.local_model = LocalModel()

# Después:
self.local_model = EnhancedLocalModel(
    model_name="llama3.2:3b",  # o el modelo que descargaste
    use_ollama=True
)
```

## 🎯 Modelos Recomendados

| Modelo | RAM Mínima | Velocidad | Calidad | Español |
|--------|-----------|-----------|---------|---------|
| `phi3:mini` | 4GB | ⚡⚡⚡ | ⭐⭐ | ⭐⭐ |
| `llama3.2:3b` | 6GB | ⚡⚡ | ⭐⭐⭐ | ⭐⭐⭐ |
| `llama3.1:8b` | 12GB | ⚡ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| `nous-hermes2` | 8GB | ⚡⚡ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| `mistral` | 8GB | ⚡⚡ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

## 🔧 Comandos Útiles de Ollama

```bash
# Ver modelos instalados
ollama list

# Descargar un modelo
ollama pull <modelo>

# Eliminar un modelo
ollama rm <modelo>

# Probar un modelo en terminal
ollama run llama3.2:3b

# Detener Ollama
# Windows: Busca "Ollama" en Servicios y detenerlo
# Linux/Mac: killall ollama
```

## 🎨 Ventajas del Nuevo Sistema

### Con Ollama + LangChain:
✅ Respuestas mucho más naturales y contextuales
✅ Memoria de conversación (recuerda las últimas 5 interacciones)
✅ Entiende contexto y puede mantener hilos de conversación
✅ Mejor comprensión del lenguaje natural
✅ Respuestas más precisas y relevantes
✅ 100% privado - todo local

### Fallback automático:
✅ Si Ollama no está disponible, usa el modelo de reglas
✅ No se rompe la aplicación
✅ Transición transparente

## 🐛 Solución de Problemas

### "Ollama no responde"
```bash
# Windows: Reinicia el servicio de Ollama
# Linux/Mac:
ollama serve
```

### "Error al descargar modelo"
```bash
# Verifica tu conexión a internet y prueba:
ollama pull llama3.2:3b --insecure
```

### "Respuestas muy lentas"
- Usa un modelo más ligero (phi3:mini)
- Cierra otras aplicaciones
- Verifica que tengas suficiente RAM disponible

### "Import Error: langchain"
```bash
pip install --upgrade langchain langchain-community ollama-python
```

## 📊 Comparación: Antes vs Después

### ANTES (Modelo basado en reglas)
```
Usuario: "¿Cómo puedo organizar mejor mi día?"
Lune: "No estoy segura de entender. Puedes decirme 'ayuda'..."
```

### DESPUÉS (Con Ollama)
```
Usuario: "¿Cómo puedo organizar mejor mi día?"
Lune: "Te recomiendo usar mis funciones de notas y recordatorios. 
Puedes crear una lista de tareas con 'toma nota' y programar 
recordatorios con 'recuérdame'. También puedo ayudarte a priorizar 
si me cuentas qué tienes pendiente."
```

## 🚀 Próximos Pasos

Una vez que todo funcione:

1. **Experimenta con diferentes modelos** para encontrar el mejor para ti
2. **Personaliza el prompt** en `enhanced_model.py` para ajustar la personalidad de Lune
3. **Aumenta la memoria** cambiando `k=5` a `k=10` para conversaciones más largas
4. **Implementa RAG** (Retrieval Augmented Generation) para que Lune recuerde información de sesiones anteriores

## 💡 Tips de Uso

- Los modelos más grandes (8b, 13b) dan mejores respuestas pero son más lentos
- Ollama usa GPU si está disponible, lo que acelera mucho las respuestas
- Puedes tener múltiples modelos instalados y cambiar entre ellos
- El primer mensaje siempre es más lento (el modelo se está cargando)

## 📚 Recursos Adicionales

- [Documentación de Ollama](https://github.com/ollama/ollama)
- [Documentación de LangChain](https://python.langchain.com/)
- [Lista de modelos disponibles](https://ollama.com/library)
- [Comunidad de Ollama en Discord](https://discord.gg/ollama)

---

¿Problemas? Abre un issue en el repositorio o contacta al desarrollador.