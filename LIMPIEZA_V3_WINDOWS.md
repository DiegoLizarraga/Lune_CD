# 🧹 Comandos para Limpiar Archivos Antiguos de Lune CD (Versión Windows)

## 📋 ANTES de ejecutar estos comandos:
1. **¡HAZ UN BACKUP!** Si hay algo importante, cópialo a otra carpeta
2. **Cierra Ollama** y cualquier proceso de Lune
3. **Abre PowerShell o CMD como Administrador**
4. **Navega a la carpeta del proyecto**: `cd C:\Users\DiegoB)\Desktop\Proyecto_Lune_CD\Lune_CD`

---

## 🗑️ Comandos de Limpieza (Ejecutar en orden)

### Paso 1: Borrar archivos Python antiguos
```powershell
# Archivos principales de Python
Remove-Item main.py -Force -ErrorAction SilentlyContinue
Remove-Item enhanced_model.py -Force -ErrorAction SilentlyContinue
Remove-Item integrate_ollama.py -Force -ErrorAction SilentlyContinue
Remove-Item verificar_instalacion.py -Force -ErrorAction SilentlyContinue
Remove-Item server.py -Force -ErrorAction SilentlyContinue
Remove-Item app.py -Force -ErrorAction SilentlyContinue
Remove-Item gui.py -Force -ErrorAction SilentlyContinue
Remove-Item pet.py -Force -ErrorAction SilentlyContinue
Remove-Item assistant.py -Force -ErrorAction SilentlyContinue

# Archivos de configuración viejos
Remove-Item lune_config.json -Force -ErrorAction SilentlyContinue
Remove-Item config.json -Force -ErrorAction SilentlyContinue
Remove-Item settings.json -Force -ErrorAction SilentlyContinue
```

### Paso 2: Borrar carpetas antiguas
```powershell
# Carpetas de Python
Remove-Item src -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item utils -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item components -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item models -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item assets -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item static -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item templates -Recurse -Force -ErrorAction SilentlyContinue

# Carpetas de caché y temporales
Remove-Item __pycache__ -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .pytest_cache -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item *.egg-info -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item dist -Recurse -Force -ErrorAction SilentlyContinue
```

### Paso 3: Borrar archivos de dependencias viejas
```powershell
# Requirements y archivos de Python
Remove-Item requirements*.txt -Force -ErrorAction SilentlyContinue
Remove-Item setup.py -Force -ErrorAction SilentlyContinue
Remove-Item Pipfile -Force -ErrorAction SilentlyContinue
Remove-Item Pipfile.lock -Force -ErrorAction SilentlyContinue
Remove-Item poetry.lock -Force -ErrorAction SilentlyContinue
Remove-Item pyproject.toml -Force -ErrorAction SilentlyContinue

# Archivos de entorno viejos
Remove-Item .python-version -Force -ErrorAction SilentlyContinue
Remove-Item venv -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item env -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .venv -Recurse -Force -ErrorAction SilentlyContinue
```

### Paso 4: Borrar archivos de documentación vieja
```powershell
# Documentación antigua
Remove-Item SETUP_OLLAMA.md -Force -ErrorAction SilentlyContinue
Remove-Item GUIA_RAPIDA.md -Force -ErrorAction SilentlyContinue
Remove-Item CHANGELOG.md -Force -ErrorAction SilentlyContinue
Remove-Item CONTRIBUTING.md -Force -ErrorAction SilentlyContinue
Remove-Item LICENSE.md -Force -ErrorAction SilentlyContinue

# Mantener solo README.md (lo vamos a reemplazar)
```

### Paso 5: Borrar archivos temporales y caché
```powershell
# Archivos temporales
Remove-Item *.pyc -Force -ErrorAction SilentlyContinue
Remove-Item *.pyo -Force -ErrorAction SilentlyContinue
Remove-Item *.pyd -Force -ErrorAction SilentlyContinue
Remove-Item *.log -Force -ErrorAction SilentlyContinue
Remove-Item *.tmp -Force -ErrorAction SilentlyContinue
Remove-Item .DS_Store -Force -ErrorAction SilentlyContinue
Remove-Item Thumbs.db -Force -ErrorAction SilentlyContinue

# Archivos de editor
Remove-Item .vscode\settings.json -Force -ErrorAction SilentlyContinue
Remove-Item .idea -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item *.swp -Force -ErrorAction SilentlyContinue
Remove-Item *.swo -Force -ErrorAction SilentlyContinue
Remove-Item *~ -Force -ErrorAction SilentlyContinue
```

### Paso 6: Borrar archivos de tests viejos
```powershell
# Tests antiguos
Remove-Item tests -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item test_*.py -Force -ErrorAction SilentlyContinue
Remove-Item *_test.py -Force -ErrorAction SilentlyContinue
Remove-Item conftest.py -Force -ErrorAction SilentlyContinue
Remove-Item pytest.ini -Force -ErrorAction SilentlyContinue
Remove-Item tox.ini -Force -ErrorAction SilentlyContinue
```

### Paso 7: Limpiar archivos de Git viejos (opcional)
```powershell
# Si quieres empezar con un Git limpio
Remove-Item .git -Recurse -Force -ErrorAction SilentlyContinue
# Luego: git init, git add ., git commit -m "Lune CD v3.0 - Nueva versión completa"
```

---

## 🖱️ MÉTODO ALTERNATIVO: Manual (Más Seguro)

Si prefieres no usar comandos, puedes borrar manualmente:

### 1. Abre el Explorador de Archivos
- Navega a `C:\Users\DiegoB)\Desktop\Proyecto_Lune_CD\Lune_CD\`

### 2. Selecciona y borra estos archivos:
```
📄 Archivos para borrar:
- main.py
- enhanced_model.py
- integrate_ollama.py
- verificar_instalacion.py
- server.py (el viejo)
- app.py
- gui.py
- pet.py
- assistant.py
- lune_config.json
- config.json
- settings.json
- requirements*.txt
- setup.py
- Pipfile
- Pipfile.lock
- poetry.lock
- pyproject.toml
- SETUP_OLLAMA.md
- GUIA_RAPIDA.md
- CHANGELOG.md
- CONTRIBUTING.md
- LICENSE.md
```

### 3. Selecciona y borra estas carpetas:
```
📁 Carpetas para borrar:
- src (la vieja)
- utils
- components
- models
- assets
- static
- templates
- __pycache__
- .pytest_cache
- *.egg-info
- build
- dist
- venv
- env
- .venv
- tests
- .idea
- .vscode (settings.json)
- .git (si quieres empezar de cero)
```

### 4. Borrar archivos ocultos
- En el Explorador, ve a "Ver" → "Elementos ocultos"
- Borra: `.DS_Store`, `Thumbs.db`, `*.pyc`, `*.log`

---

## ✅ VERIFICACIÓN Final

Después de la limpieza, tu carpeta debería verse así:

```
Lune_CD/
├── 📁 electron/
├── 📁 public/
├── 📁 src/          (la nueva, con app/, api/, etc.)
├── 📄 .env
├── 📄 .env.example
├── 📄 .gitignore
├── 📄 package.json
├── 📄 README.md
├── 📄 server.js
└── 📄 tailwind.config.ts
```

### Comando para verificar qué quedó:
```powershell
# Mostrar archivos en la carpeta
Get-ChildItem

# Mostrar estructura de carpetas
tree /f
```

---

## 🚀 Listo para la v3.0

Una vez ejecutados estos comandos o borrado manualmente:
1. **Copia los nuevos archivos** que te proporcioné
2. **Abre PowerShell o CMD** en la carpeta
3. **Ejecuta**: `npm install`
4. **Inicia**: `npm run electron-dev`

¡Y listo! Tendrás Lune CD v3.0 funcionando perfectamente 🌙

---

## ⚠️ ADVERTENCIA IMPORTANTE

- **Estos comandos borran permanentemente archivos**
- **No hay vuelta atrás** una vez ejecutados
- **Asegúrate de no necesitar nada de lo viejo**
- **Si tienes dudas, haz backup antes**

**¡El responsable de la pérdida de datos es tú!** ⚠️

---

## 💡 Tips Adicionales para Windows

### Para borrar archivos que no se dejan borrar:
```powershell
# Cerrar procesos que puedan estar usando los archivos
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Stop-Process -Force

# O usar el comando del con fuerza
del /f /q archivo.py
```

### Para limpiar espacio en disco:
```powershell
# Limpiar carpeta temp
Remove-Item $env:TEMP\* -Recurse -Force -ErrorAction SilentlyContinue

# Limpiar caché de npm
npm cache clean --force
```