@echo off
rem ============================================================
rem  lune_patata.bat - Lune en la terminal (modo patata)
rem  Sin Qt, sin animaciones, sin mascota: solo texto y caritas.
rem  Sirve tambien de rescate si la interfaz normal no abre.
rem ============================================================
setlocal
cd /d "%~dp0"
title Lune CD - modo patata

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  No encontre Python. Descargalo de https://www.python.org/downloads/
    echo  ^(marca "Add python to PATH"^) y vuelve a ejecutar este archivo.
    echo.
    pause
    exit /b 1
)

python patata.py %*
if errorlevel 1 (
    echo.
    echo  Lune termino con un error. Si faltan dependencias, ejecuta instalar_lune.bat
    pause
)
endlocal
