' ============================================================
'  iniciar_lune.vbs - Arranque silencioso de Lune CD
'
'  Lanza la app con pythonw.exe (sin ventana de consola).
'  Para autoarranque: pon un acceso directo a este .vbs en
'  la carpeta de Inicio (Win+R -> shell:startup).
'
'  POR QUE VERIFICA EL INTERPRETE
'  ------------------------------
'  Es habitual tener varios Python instalados. Si se elige uno
'  que no tiene PyQt6, la app muere al importar y —al ir oculta—
'  no pasa absolutamente nada: ni ventana, ni error, ni pista.
'  Por eso aqui se PRUEBA cada candidato ("import PyQt6") y se
'  usa el primero que funcione, en vez de adivinar por ruta.
'
'  Si Lune ya esta abierta, la app detecta la instancia
'  existente y la trae al frente en vez de abrir otra.
' ============================================================
Option Explicit

Dim shell, fso, carpeta, script, pyw, candidatos, i, ruta

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta
script = carpeta & "\main.py"

If Not fso.FileExists(script) Then
    MsgBox "No encuentro main.py en:" & vbCrLf & carpeta, 16, "Lune CD"
    WScript.Quit 1
End If

' ── Candidatos, del mas fiable al menos ─────────────────────
' 1) Entorno virtual del proyecto  2) el pythonw del PATH (el mismo
' que usaste con pip)  3) el lanzador oficial  4) rutas tipicas.
candidatos = Array( _
    carpeta & "\venv\Scripts\pythonw.exe", _
    carpeta & "\.venv\Scripts\pythonw.exe", _
    "pythonw.exe", _
    "pyw.exe", _
    "C:\Program Files\Python313\pythonw.exe", _
    "C:\Program Files\Python312\pythonw.exe", _
    "C:\Program Files\Python311\pythonw.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"), _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"), _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"))

pyw = ""
For i = 0 To UBound(candidatos)
    If pyw = "" Then
        ruta = candidatos(i)
        If SirveEsteInterprete(ruta) Then pyw = ruta
    End If
Next

If pyw = "" Then
    MsgBox "No encontre un Python con las dependencias de Lune." & vbCrLf & vbCrLf & _
           "Instalalas con:" & vbCrLf & _
           "    pip install -r requirements.txt" & vbCrLf & vbCrLf & _
           "Si usas varios Python, hazlo con el mismo que este en el PATH.", _
           16, "Lune CD"
    WScript.Quit 1
End If

' ── EL 1 ES IMPORTANTE, NO LO CAMBIES A 0 ───────────────────
' El segundo parametro de Run es el estilo de ventana, y Windows
' se lo pasa al proceso hijo en STARTUPINFO. Qt lo aplica a la
' PRIMERA ventana de la app: con 0 (oculta), la pantalla de inicio
' se creaba invisible. El proceso corria, el video sonaba, y en
' pantalla no aparecia nada.
'
' No hace falta ocultar nada: pythonw.exe ya arranca sin consola.
' 1 = ventana normal. False = no esperar a que termine.
shell.Run """" & pyw & """ """ & script & """", 1, False


' ── Prueba un interprete: existe y puede importar PyQt6? ────
Function SirveEsteInterprete(exe)
    Dim codigo
    SirveEsteInterprete = False

    ' Las rutas absolutas se comprueban antes; los nombres sueltos
    ' (pythonw.exe, pyw.exe) se dejan al PATH.
    If InStr(exe, "\") > 0 Then
        If Not fso.FileExists(exe) Then Exit Function
    End If

    On Error Resume Next
    ' 0 = sin ventana, True = esperar. Devuelve el codigo de salida.
    codigo = shell.Run("""" & exe & """ -c ""import PyQt6""", 0, True)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    On Error GoTo 0

    If codigo = 0 Then SirveEsteInterprete = True
End Function
