@echo off
rem ============================================================
rem  instalar_lune.bat - Instalador de Lune CD para usuarios nuevos
rem
rem  1) Busca un Python de verdad (3.10 o mas nuevo). El "python" que
rem     trae Windows sin instalar nada es un atajo a la Microsoft Store
rem     que no ejecuta nada: se descarta porque no pasa la prueba.
rem  2) Si no hay, ofrece instalar Python 3.13 con winget (solo para tu
rem     usuario, sin permisos de administrador) o abre python.org.
rem  3) Pone pip al dia y abre la ventana del instalador (instalador.py),
rem     que explica cada componente, crea el acceso directo y abre Lune.
rem     Si ese Python no trae Tkinter, instala requirements.txt aqui.
rem
rem  instalar_lune.bat /probar   solo dice que Python usaria (tests).
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title Lune CD - instalador

call :buscar_python
if /i "%~1"=="/probar" goto :probar_y_salir
if defined PY goto :hay_python

echo.
echo  No encontre Python 3.10 o mas nuevo en este equipo.
where winget >nul 2>nul
if errorlevel 1 goto :sin_python
echo.
choice /c SN /n /m " Quieres que lo instale ahora (Python 3.13, solo para tu usuario)? [S/N] "
if errorlevel 2 goto :sin_python
echo.
echo  Instalando Python 3.13 con winget. Puede tardar un par de minutos...
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
call :buscar_python
if defined PY goto :hay_python
echo.
echo  winget termino, pero aun no encuentro Python. Cierra esta ventana y
echo  abre instalar_lune.bat otra vez; si sigue igual, instalalo a mano.

:sin_python
echo.
echo  Descarga Python de https://www.python.org/downloads/
echo  (en el instalador marca "Add python.exe to PATH") y vuelve a abrir este archivo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:hay_python
echo.
echo  Usare este Python: %PY%
%PY% -m pip --version >nul 2>nul
if not errorlevel 1 goto :pip_listo
echo  Este Python no trae pip: lo instalo...
%PY% -m ensurepip --upgrade
:pip_listo
%PY% -m pip install --upgrade pip --disable-pip-version-check -q

%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 goto :sin_ventana

%PY% instalador.py
if errorlevel 1 goto :error_ventana
goto :fin

:error_ventana
echo.
echo  El instalador termino con un error. Revisa el mensaje de arriba.
pause
goto :fin

:sin_ventana
echo.
echo  Este Python no trae Tkinter (la ventana del instalador).
echo  Instalo lo basico aqui mismo con requirements.txt...
echo.
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :error_consola
echo.
echo  Listo. Abre Lune con iniciar_lune.vbs
pause
goto :fin

:error_consola
echo.
echo  Algo fallo: revisa el mensaje de arriba.
pause
goto :fin

:probar_y_salir
echo python=%PY%
exit /b 0

:fin
endlocal
exit /b 0

rem ---- Subrutinas ---------------------------------------------

:buscar_python
rem Primero el del PATH (el mismo que usa iniciar_lune.vbs), luego el
rem lanzador py y las rutas tipicas (las de winget, --scope user, incluidas).
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
