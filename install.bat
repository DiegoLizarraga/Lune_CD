@echo off
REM install.bat - Instalador para Lune CD v7.0 + OpenRouter (Windows)
REM Uso: install.bat

echo.
echo 🌙 Instalador de Lune CD v7.0 + OpenRouter + Claude Code
echo ========================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python no está instalado o no está en PATH
    echo    Descárgalo desde: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python encontrado
echo.

REM Actualizar pip
echo 📦 Actualizando pip...
python -m pip install --upgrade pip setuptools wheel

REM Instalar dependencias de requirements.txt
if exist requirements.txt (
    echo 📦 Instalando dependencias...
    pip install -r requirements.txt
    if %errorlevel% equ 0 (
        echo ✅ Dependencias instaladas
    )
)

echo.
echo 🔌 Instalando soporte OpenRouter + Claude Code...
pip install ^
    requests>=2.31.0 ^
    aiofiles>=23.0.0 ^
    pyperclip>=1.8.2 ^
    edge-tts>=6.1.0 ^
    python-dotenv>=1.0.0

if %errorlevel% equ 0 (
    echo ✅ Dependencias OpenRouter instaladas
) else (
    echo ❌ Error instalando dependencias
    pause
    exit /b 1
)

echo.
echo 📝 Instalando "lune" como comando global...
pip install -e .

if %errorlevel% equ 0 (
    echo.
    echo ✅ Instalación completada
    echo.
    echo 🚀 Ahora puedes usar desde PowerShell o CMD:
    echo.
    echo    lune "¿Hola, cómo estás?"
    echo    lune chat                  
    echo    lune code "escribe python"
    echo    lune models                
    echo    lune test-connection       
    echo.
    echo 📖 Tu API key ya está configurada en datos.json
    echo.
    echo 🌙 ¡Lune está listo!
    pause
) else (
    echo ❌ Error durante la instalación
    pause
    exit /b 1
)
