# Comandos Git para Subir Lune CD v3.0 (Versión Windows)

## 🚀 Preparar el Repositorio para la Nueva Versión

### Paso 1: Abrir Git en Windows
```powershell
# Opción 1: Usar Git Bash (Recomendado)
# Click derecho en la carpeta → "Git Bash Here"

# Opción 2: Usar PowerShell con Git
# Abrir PowerShell como Administrador
cd "C:\Users\DiegoB)\Desktop\Proyecto_Lune_CD\Lune_CD"

# Opción 3: Usar CMD
# Abrir CMD como Administrador
cd "C:\Users\DiegoB)\Desktop\Proyecto_Lune_CD\Lune_CD"
```

### Paso 2: Limpiar y preparar
```powershell
# Ejecutar los comandos de limpieza (ver LIMPIEZA_V3_WINDOWS.md)
# ... (ejecutar todos los comandos de limpieza)

# Verificar que solo queden los archivos nuevos
Get-ChildItem
```

### Paso 3: Inicializar Git (si es nuevo)
```powershell
# Si borramos .git, iniciamos nuevo
git init

# Configurar usuario (si no está configurado)
git config user.name "Diego Lizarraga"
git config user.email "tu-email@example.com"
```

### Paso 4: Agregar archivos nuevos
```powershell
# Agregar todos los archivos nuevos
git add .

# Verificar qué se va a subir
git status

# Hacer el commit inicial de la v3.0
git commit -m "🌙 Lune CD v3.0 - Reescritura completa con Next.js + Electron

✨ Características principales:
- Menú estilo videojuego con animaciones impresionantes
- Chat inteligente con Ollama local y chat.z.ai
- Mascota de escritorio animada con efectos mágicos
- Interfaz minimalista y moderna
- 100% offline y privado
- Integración con sistema operativo
- Instalación simplificada con un solo comando

🔧 Cambios técnicos:
- Migrado de Python/Tkinter a Next.js 15 + Electron
- TypeScript para mayor robustez
- Tailwind CSS para diseños modernos
- API RESTful para el chat
- Arquitectura modular y escalable

🚀 Esta versión redefine completamente la experiencia de Lune CD"
```

### Paso 5: Conectar con GitHub (si es repositorio nuevo)
```powershell
# Agregar remote de GitHub
git remote add origin https://github.com/DiegoLizarraga/Lune_CD.git

# O si ya existe, actualizar URL
git remote set-url origin https://github.com/DiegoLizarraga/Lune_CD.git

# Verificar remote
git remote -v
```

### Paso 6: Subir a GitHub
```powershell
# Hacer push forzado (porque es una reescritura completa)
git push -u origin main --force

# O si prefieres crear una nueva rama primero
git checkout -b version-3.0
git push -u origin version-3.0
```

---

## 🔄 Si el repositorio ya existe y quieres actualizar

### Opción A: Subir como nueva rama
```powershell
# Crear rama para la v3.0
git checkout -b v3.0-complete-rewrite

# Agregar y commitear cambios
git add .
git commit -m "🌙 Lune CD v3.0 - Reescritura completa

Nueva versión desde cero con:
- Next.js 15 + Electron
- Menú de videojuego
- Chat inteligente dual
- Mascota animada
- 100% offline"

# Subir rama
git push -u origin v3.0-complete-rewrite

# Luego hacer Pull Request en GitHub para mergear a main
```

### Opción B: Reemplazar main completamente
```powershell
# Hacer backup del main actual (opcional)
git checkout -b backup-v2.0
git push origin backup-v2.0

# Volver a main y reemplazar todo
git checkout main
git add .
git commit -m "🌙 Lune CD v3.0 - Reescritura completa

Reemplazo total de la versión 2.0 por una arquitectura moderna.
Ver README.md para todos los detalles de la nueva versión."

# Forzar push a main
git push origin main --force
```

---

## 📋 Checklist Antes de Subir

### ✅ Verificar que todo esté perfecto:
```powershell
# 1. Verificar que la app funcione
npm run electron-dev

# 2. Verificar que no haya archivos viejos
git status
# Solo deberían aparecer los archivos nuevos

# 3. Verificar el README
Get-Content README.md
# Debe ser la versión v3.0

# 4. Verificar package.json
Get-Content package.json
# Debe decir version 3.0.0

# 5. Verificar que no haya secrets
git grep --cached -i "password\|secret\|key"
# No debería mostrar nada importante
```

### ✅ Archivos que DEBEN estar:
```
✅ README.md (nueva versión v3.0)
✅ package.json (v3.0.0)
✅ server.js
✅ electron/main.js
✅ electron/preload.js
✅ public/index.html
✅ public/pet.html
✅ src/app/layout.tsx
✅ src/app/page.tsx
✅ src/app/globals.css
✅ src/app/api/chat/route.ts
✅ src/app/api/status/route.ts
✅ .env.example
✅ LIMPIEZA_V3_WINDOWS.md
```

### ❌ Archivos que NO DEBEN estar:
```
❌ main.py
❌ enhanced_model.py
❌ requirements.txt
❌ lune_config.json
❌ Cualquier archivo .py
❌ Carpetas src/ viejas de Python
```

---

## 🛠️ Solución de Problemas Comunes en Windows

### Problema: "Git no es reconocido"
```powershell
# Instalar Git for Windows desde: https://git-scm.com/download/win
# O usar GitHub Desktop que incluye Git
```

### Problema: "Permiso denegado"
```powershell
# Abrir PowerShell o CMD como Administrador
# O cambiar permisos de la carpeta
icacls "C:\Users\DiegoB)\Desktop\Proyecto_Lune_CD\Lune_CD" /grant "${env:USERNAME}:(OI)(CI)F"
```

### Problema: "Archivos bloqueados"
```powershell
# Cerrar todos los programas que puedan usar los archivos
# Especialmente VS Code, editores de texto, etc.

# Ver procesos que usan archivos
Get-Process | Where-Object {$_.MainWindowTitle -like "*Lune*"} | Stop-Process -Force
```

### Problema: "Error de autenticación en GitHub"
```powershell
# Configurar credenciales de Git
git config --global credential.helper manager

# O usar Personal Access Token
# GitHub → Settings → Developer settings → Personal access tokens
```

### Problema: "Push rechazado"
```powershell
# Forzar push (cuidado, borra historial)
git push origin main --force

# O usar --force-with-lease (más seguro)
git push origin main --force-with-lease
```

---

## 🎉 Después de Subir

### 1. Crear Release en GitHub
1. Ve a GitHub → Releases → "Create a new release"
2. Tag: `v3.0.0`
3. Title: `🌙 Lune CD v3.0 - Reescritura Completa`
4. Description: Copia el README.md
5. Marcar como "Latest release"

### 2. Actualizar descripción del repositorio
```text
🌙 Lune CD v3.0 - Tu mascota virtual inteligente con chat y menú de videojuego

✨ Características:
- Chat inteligente con Ollama local
- Menú estilo videojuego impresionante
- Mascota de escritorio animada
- 100% offline y privado
- Integración con sistema operativo

🚀 Hecho con Next.js 15 + Electron + TypeScript
```

### 3. Añadir topics al repositorio
```
mascota-virtual, chat-inteligente, ollama, electron, nextjs, typescript, desktop-app, spanish, ai-local
```

---

## 🎯 ¡Listo!

Una vez hecho esto, tendrás:
- ✅ Lune CD v3.0 en GitHub
- ✅ Release oficial creada
- ✅ Documentación completa
- ✅ Repositorio limpio y profesional

**¡Felicidades! Has completado la reescritura más épica de Lune CD 🌙**

---

## 💡 Tips Adicionales para Windows

### Usar GitHub Desktop (más fácil para principiantes)
1. Instala GitHub Desktop
2. Clona el repositorio
3. Arrastra los archivos nuevos a la carpeta
4. Haz commit desde la interfaz
5. Haz push desde la interfaz

### Verificar cambios antes de subir
```powershell
# Ver diferencias
git diff

# Ver historial
git log --oneline

# Ver ramas
git branch -a
```

### Si algo sale mal, volver atrás
```powershell
# Volver al último commit
git reset --hard HEAD~1

# O volver a un estado específico
git reset --hard <commit-hash>
```