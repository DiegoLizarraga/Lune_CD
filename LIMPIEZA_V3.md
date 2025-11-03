# 🧹 Comandos para Limpiar Archivos Antiguos de Lune CD

## 📋 ANTES de ejecutar estos comandos:
1. **¡HAZ UN BACKUP!** Si hay algo importante, guárdalo
2. **Cierra Ollama** y cualquier proceso de Lune
3. **Navega a la carpeta del proyecto**: `cd Lune_CD`

---

## 🗑️ Comandos de Limpieza (Ejecutar en orden)

### Paso 1: Borrar archivos Python antiguos
```bash
# Archivos principales de Python
rm -f main.py
rm -f enhanced_model.py
rm -f integrate_ollama.py
rm -f verificar_instalacion.py
rm -f server.py  # el viejo, no el nuevo
rm -f app.py
rm -f gui.py
rm -f pet.py
rm -f assistant.py

# Archivos de configuración viejos
rm -f lune_config.json
rm -f config.json
rm -f settings.json
```

### Paso 2: Borrar carpetas antiguas
```bash
# Carpetas de Python
rm -rf src/
rm -rf utils/
rm -rf components/
rm -rf models/
rm -rf assets/
rm -rf static/
rm -rf templates/

# Carpetas de caché y temporales
rm -rf __pycache__/
rm -rf .pytest_cache/
rm -rf *.egg-info/
rm -rf build/
rm -rf dist/
```

### Paso 3: Borrar archivos de dependencias viejas
```bash
# Requirements y archivos de Python
rm -f requirements*.txt
rm -f setup.py
rm -f Pipfile
rm -f Pipfile.lock
rm -f poetry.lock
rm -f pyproject.toml

# Archivos de entorno viejos
rm -f .python-version
rm -f venv/
rm -rf env/
rm -rf .venv/
```

### Paso 4: Borrar archivos de documentación vieja
```bash
# Documentación antigua
rm -f SETUP_OLLAMA.md
rm -f GUIA_RAPIDA.md
rm -f CHANGELOG.md
rm -f CONTRIBUTING.md
rm -f LICENSE.md

# Mantener solo README.md (lo vamos a reemplazar)
```

### Paso 5: Borrar archivos temporales y caché
```bash
# Archivos temporales
rm -f *.pyc
rm -f *.pyo
rm -f *.pyd
rm -f *.log
rm -f *.tmp
rm -f .DS_Store
rm -f Thumbs.db

# Archivos de editor
rm -f .vscode/settings.json
rm -f .idea/
rm -f *.swp
rm -f *.swo
rm -f *~
```

### Paso 6: Borrar archivos de tests viejos
```bash
# Tests antiguos
rm -rf tests/
rm -rf test_*.py
rm -f *_test.py
rm -f conftest.py
rm -f pytest.ini
rm -f tox.ini
```

### Paso 7: Limpiar archivos de Git viejos (opcional)
```bash
# Si quieres empezar con un Git limpio
rm -rf .git/
# Luego: git init, git add ., git commit -m "Lune CD v3.0 - Nueva versión completa"
```

---

## ✅ VERIFICACIÓN Final

Después de la limpieza, tu carpeta debería verse así:

```
Lune_CD/
├── 📁 electron/
├── 📁 public/
├── 📁 src/
├── 📄 .env
├── 📄 .env.example
├── 📄 .gitignore
├── 📄 package.json
├── 📄 README.md
├── 📄 server.js
└── 📄 tailwind.config.ts
```

### Comando para verificar qué quedó:
```bash
# Mostrar estructura de carpetas
tree -I 'node_modules|.next'

# O si no tienes tree:
ls -la
```

---

## 🚀 Listo para la v3.0

Una vez ejecutados estos comandos:
1. **Copia los nuevos archivos** que te proporcioné
2. **Ejecuta**: `npm install`
3. **Inicia**: `npm run electron-dev`

¡Y listo! Tendrás Lune CD v3.0 funcionando perfectamente 🌙

---

## ⚠️ ADVERTENCIA IMPORTANTE

- **Estos comandos borran permanentemente archivos**
- **No hay vuelta atrás** una vez ejecutados
- **Asegúrate de no necesitar nada de lo viejo**
- **Si tienes dudas, haz backup antes**

**¡El responsable de la pérdida de datos es tú!** ⚠️