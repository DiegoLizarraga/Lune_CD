' ============================================================
'  iniciar_lune.vbs - Arranque silencioso de Lune CD
'
'  Lanza la app con pythonw.exe (sin ventana de consola).
'  Para arrancar con Windows: Ajustes -> "Arrancar Lune junto
'  con Windows" (escribe la entrada Run del usuario; ver
'  servicios/autoinicio.py). No hace falta ningun acceso directo.
'
'  ARGUMENTOS
'    (ninguno)             pythonw main.py (pantalla de inicio)
'    /autoinicio           pythonw main.py --autoinicio
'                          (sin pantalla de inicio; bandeja, mascota
'                          o ventana tras la espera: nucleo/arranque.py)
'    /autoinicio /patata   python.exe patata.py --autoinicio en una
'                          consola MINIMIZADA (no exige PyQt6)
'    /patata               python.exe patata.py en una consola normal
'    /probar               no lanza nada: escribe el comando con
'                          WScript.Echo (para los tests con cscript)
'
'  POR QUE VERIFICA EL INTERPRETE
'  ------------------------------
'  Es habitual tener varios Python instalados. Si se elige uno
'  que no tiene PyQt6, la app muere al importar y -al ir oculta-
'  no pasa absolutamente nada: ni ventana, ni error, ni pista.
'  Por eso aqui se PRUEBA cada candidato ("import PyQt6") y se
'  usa el primero que funcione, en vez de adivinar por ruta.
'  Para patata basta un python.exe CON consola que arranque
'  ("import sys"): la terminal no necesita Qt.
'
'  Si Lune ya esta abierta, la app detecta la instancia
'  existente y la trae al frente en vez de abrir otra (con
'  /autoinicio no la trae: solo se retira).
'
'  Este archivo es ASCII a proposito (tests/test_arranque.py).
' ============================================================
Option Explicit

Dim shell, fso, carpeta, script, candidatos, i, ruta, exe, orden
Dim arg, autoinicio, patata, probar

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

autoinicio = False
patata = False
probar = False
For i = 0 To WScript.Arguments.Count - 1
    arg = LCase(WScript.Arguments(i))
    If arg = "/autoinicio" Or arg = "--autoinicio" Then autoinicio = True
    If arg = "/patata" Or arg = "--patata" Then patata = True
    If arg = "/probar" Or arg = "--probar" Then probar = True
Next

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta

If patata Then
    LanzarPatata
Else
    LanzarApp
End If
WScript.Quit 0


' -- La app de ventanas (web o nativa) ------------------------
Sub LanzarApp()
    script = carpeta & "\main.py"
    If Not fso.FileExists(script) Then
        Avisar "No encuentro main.py en:" & vbCrLf & carpeta
        WScript.Quit 1
    End If

    ' Candidatos, del mas fiable al menos:
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
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"), _
        "C:\Program Files\Python314\pythonw.exe", _
        "C:\Program Files\Python310\pythonw.exe")

    exe = ""
    For i = 0 To UBound(candidatos)
        If exe = "" Then
            ruta = candidatos(i)
            If SirveEsteInterprete(ruta) Then exe = ruta
        End If
    Next

    If exe = "" Then
        Avisar "No encontre un Python con las dependencias de Lune." & vbCrLf & vbCrLf & _
               "Lo mas facil: doble clic en  instalar_lune.bat  (te explica cada cosa)." & vbCrLf & _
               "O a mano:  pip install -r requirements.txt" & vbCrLf & vbCrLf & _
               "Mientras tanto, Lune sigue disponible en la terminal (modo patata):" & vbCrLf & _
               "    lune_patata.bat" & vbCrLf & vbCrLf & _
               "Si usas varios Python, hazlo con el mismo que este en el PATH."
        WScript.Quit 1
    End If

    orden = """" & exe & """ """ & script & """"
    If autoinicio Then orden = orden & " --autoinicio"

    If probar Then
        WScript.Echo "estilo=1"
        WScript.Echo orden
        Exit Sub
    End If

    ' -- EL 1 ES IMPORTANTE, NO LO CAMBIES A 0 ----------------
    ' El segundo parametro de Run es el estilo de ventana, y Windows
    ' se lo pasa al proceso hijo en STARTUPINFO. Qt lo aplica a la
    ' PRIMERA ventana de la app: con 0 (oculta), la pantalla de inicio
    ' se creaba invisible. El proceso corria, el video sonaba, y en
    ' pantalla no aparecia nada. Con /autoinicio la app decide ella
    ' misma si muestra la ventana o se queda en la bandeja.
    '
    ' No hace falta ocultar nada: pythonw.exe ya arranca sin consola.
    ' 1 = ventana normal. False = no esperar a que termine.
    shell.Run orden, 1, False
End Sub


' -- Patata: Lune en la terminal ------------------------------
Sub LanzarPatata()
    script = carpeta & "\patata.py"
    If Not fso.FileExists(script) Then
        Avisar "No encuentro patata.py en:" & vbCrLf & carpeta
        WScript.Quit 1
    End If

    ' python.exe (CON consola; pythonw no la tendria). Sin PyQt6.
    candidatos = Array( _
        carpeta & "\venv\Scripts\python.exe", _
        carpeta & "\.venv\Scripts\python.exe", _
        "python.exe", _
        "py.exe", _
        "C:\Program Files\Python313\python.exe", _
        "C:\Program Files\Python312\python.exe", _
        "C:\Program Files\Python311\python.exe", _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\python.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\python.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311\python.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python314\python.exe"), _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python310\python.exe"), _
        "C:\Program Files\Python314\python.exe", _
        "C:\Program Files\Python310\python.exe")

    exe = ""
    For i = 0 To UBound(candidatos)
        If exe = "" Then
            ruta = candidatos(i)
            If SirveParaPatata(ruta) Then exe = ruta
        End If
    Next

    If exe = "" Then
        Avisar "No encontre python.exe para abrir Lune en la terminal." & vbCrLf & vbCrLf & _
               "Instala Python desde https://www.python.org/downloads/" & vbCrLf & _
               "(marca ""Add python to PATH"") y vuelve a probar."
        WScript.Quit 1
    End If

    orden = """" & exe & """ """ & script & """"
    If autoinicio Then orden = orden & " --autoinicio"

    If probar Then
        If autoinicio Then
            WScript.Echo "estilo=7"
        Else
            WScript.Echo "estilo=1"
        End If
        WScript.Echo orden
        Exit Sub
    End If

    ' 7 = minimizada y sin quitar el foco: al arrancar Windows la
    ' terminal espera en la barra de tareas. A mano, ventana normal.
    If autoinicio Then
        shell.Run orden, 7, False
    Else
        shell.Run orden, 1, False
    End If
End Sub


' -- Un aviso: MsgBox, o texto con /probar (cscript no espera) --
Sub Avisar(texto)
    If probar Then
        WScript.Echo "ERROR: " & Replace(texto, vbCrLf, " ")
    Else
        MsgBox texto, 16, "Lune CD"
    End If
End Sub


' -- Prueba un interprete: existe y puede importar PyQt6? -----
Function SirveEsteInterprete(ruta_exe)
    SirveEsteInterprete = Responde(ruta_exe, "import PyQt6")
End Function


' -- Para patata basta con que arranque ------------------------
Function SirveParaPatata(ruta_exe)
    SirveParaPatata = Responde(ruta_exe, "import sys")
End Function


Function Responde(ruta_exe, codigo_py)
    Dim codigo
    Responde = False

    ' Las rutas absolutas se comprueban antes; los nombres sueltos
    ' (pythonw.exe, python.exe, py.exe) se dejan al PATH.
    If InStr(ruta_exe, "\") > 0 Then
        If Not fso.FileExists(ruta_exe) Then Exit Function
    End If

    On Error Resume Next
    ' 0 = sin ventana, True = esperar. Devuelve el codigo de salida.
    codigo = shell.Run("""" & ruta_exe & """ -c """ & codigo_py & """", 0, True)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    On Error GoTo 0

    If codigo = 0 Then Responde = True
End Function
