@echo off
rem ============================================================
rem  instalar_lune.bat - Instalador de Lune CD para usuarios nuevos
rem  Abre una ventana que explica cada componente y deja elegir
rem  que instalar. Solo necesita Python (viene con Tkinter).
rem ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  No encontre Python en este equipo.
    echo  Descargalo de https://www.python.org/downloads/  ^(marca "Add python to PATH"^)
    echo  y vuelve a ejecutar este archivo.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

python instalador.py
if errorlevel 1 (
    echo.
    echo  El instalador termino con un error. Revisa el mensaje de arriba.
    pause
)
endlocal
