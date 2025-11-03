# Comandos Git para Subir Lune CD v3.0

## 🚀 Preparar el Repositorio para la Nueva Versión

### Paso 1: Limpiar y preparar
```bash
# Navegar a la carpeta del proyecto
cd Lune_CD

# Ejecutar los comandos de limpieza (ver LIMPIEZA_V3.md)
# ... (ejecutar todos los comandos de limpieza)

# Verificar que solo queden los archivos nuevos
ls -la
```

### Paso 2: Inicializar Git (si es nuevo)
```bash
# Si borramos .git, iniciamos nuevo
git init

# Configurar usuario (si no está configurado)
git config user.name "Diego Lizarraga"
git config user.email "tu-email@example.com"
```

### Paso 3: Agregar archivos nuevos
```bash
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

### Paso 4: Conectar con GitHub (si es repositorio nuevo)
```bash
# Agregar remote de GitHub
git remote add origin https://github.com/DiegoLizarraga/Lune_CD.git

# O si ya existe, actualizar URL
git remote set-url origin https://github.com/DiegoLizarraga/Lune_CD.git
```

### Paso 5: Subir a GitHub
```bash
# Hacer push forzado (porque es una reescritura completa)
git push -u origin main --force

# O si prefieres crear una nueva rama primero
git checkout -b version-3.0
git push -u origin version-3.0
```

---

## 🔄 Si el repositorio ya existe y quieres actualizar

### Opción A: Subir como nueva rama
```bash
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

# Luego hacer Pull Request para mergear a main
```

### Opción B: Reemplazar main completamente
```bash
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
```bash
# 1. Verificar que la app funcione
npm run electron-dev

# 2. Verificar que no haya archivos viejos
git status
# Solo deberían aparecer los archivos nuevos

# 3. Verificar el README
cat README.md
# Debe ser la versión v3.0

# 4. Verificar package.json
cat package.json
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
✅ LIMPIEZA_V3.md
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