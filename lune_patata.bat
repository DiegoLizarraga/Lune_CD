@echo off
rem ============================================================
rem  lune_patata.bat - Lune en la terminal (modo patata)
rem  Sin Qt, sin animaciones, sin mascota: solo texto y caritas.
rem  Sirve tambien de rescate si la interfaz normal no abre.
rem  Busca Python igual que instalar_lune.bat (el "python" de la
rem  Microsoft Store no cuenta: no ejecuta nada).
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title Lune CD - modo patata

call :buscar_python
if defined PY goto :hay_python
echo.
echo  No encontre Python 3.10 o mas nuevo. Abre instalar_lune.bat: te ayuda a
echo  instalarlo (o descargalo de https://www.python.org/downloads/ marcando
echo  "Add python.exe to PATH") y vuelve a abrir este archivo.
echo.
pause
exit /b 1

:hay_python
%PY% patata.py %*
if errorlevel 1 goto :error
goto :fin

:error
echo.
echo  Lune termino con un error. Si faltan dependencias, ejecuta instalar_lune.bat
pause

:fin
endlocal
exit /b 0

rem ---- Subrutinas ---------------------------------------------

:buscar_python
set "PY="
call :probar python
if not defined PY call :probar py -3
for %%V in (313 312 311 314 310) do if not defined PY call :probar "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
for %%V in (313 312 311 314 310) do if not defined PY call :probar "%ProgramFiles%\Python%%V\python.exe"
exit /b 0

:probar
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0
