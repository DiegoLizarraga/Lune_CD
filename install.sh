#!/bin/bash
# install.sh — Instalador rápido para Lune CD v7.0 + OpenRouter
# Uso: bash install.sh

set -e

echo "🌙 Instalador de Lune CD v7.0 + OpenRouter + Claude Code"
echo "========================================================"
echo ""

# Detectar OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    OS_TYPE="windows"
fi

echo "✅ Sistema detectado: $OS_TYPE"
echo ""

# Verificar Python
echo "🔍 Verificando Python 3.10+..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python $PYTHON_VERSION encontrado"
echo ""

# Crear entorno virtual (opcional)
echo "📦 Instalando dependencias..."
pip install --upgrade pip setuptools wheel

# Instalar dependencias del proyecto
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✅ Dependencias de requirements.txt instaladas"
fi

# Instalar dependencias adicionales para OpenRouter
echo ""
echo "🔌 Instalando soporte OpenRouter + Claude Code..."
pip install \
    requests>=2.31.0 \
    aiofiles>=23.0.0 \
    pyperclip>=1.8.2 \
    edge-tts>=6.1.0 \
    python-dotenv>=1.0.0

echo "✅ Dependencias OpenRouter instaladas"
echo ""

# Instalar como comando global
echo "📝 Instalando 'lune' como comando global..."
pip install -e .

if [ $? -eq 0 ]; then
    echo "✅ Instalación completada"
    echo ""
    echo "🚀 Ahora puedes usar desde cualquier carpeta:"
    echo ""
    echo "   lune \"¿Hola, cómo estás?\""
    echo "   lune chat                  # Chat interactivo"
    echo "   lune code \"escribe python\""
    echo "   lune models                # Listar modelos"
    echo "   lune test-connection       # Probar OpenRouter"
    echo ""
    echo "📖 Tu API key ya está configurada en datos.json"
    echo ""
    echo "🌙 ¡Lune está listo!"
else
    echo "❌ Error durante la instalación"
    exit 1
fi
