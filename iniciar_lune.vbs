' ============================================================
'  iniciar_lune.vbs - Arranque silencioso de Lune CD
'  Lanza la app sin ventana de consola (usa pythonw).
'  Para autoarranque: pon un acceso directo a este .vbs en
'  la carpeta de Inicio (Win+R -> shell:startup).
' ============================================================
Option Explicit

Dim shell, fso, carpeta, pyw, script

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

' Carpeta donde vive este .vbs (= raiz del proyecto)
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta

script = carpeta & "\main.py"

' Buscar pythonw.exe junto a python (si esta en PATH, basta "pythonw")
pyw = "pythonw.exe"

' Ejecutar oculto (0 = sin ventana), sin esperar a que termine (False)
shell.Run """" & pyw & """ """ & script & """", 0, False
