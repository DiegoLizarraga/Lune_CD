; packaging/lune.iss — El instalador de Lune (Inno Setup 6, en español).
;
; No se compila a mano: packaging/construir.py le pasa
;   /DVersion=11.2 /DVersionWin=11.2.0.0 /DOrigen=<dist\Lune CD> /DSalida=<dist>
; y deja dist\LuneCD-Setup-<versión>.exe (el que se sube a GitHub Releases).
;
; Qué hace:
;   · Se instala SOLO para ti, sin pedir administrador: %LOCALAPPDATA%\Programs\Lune CD
;     (PrivilegesRequired=lowest, sin preguntar otra cosa).
;   · Menú Inicio: «Lune CD» (Lune.exe, con el AppUserModelID fijo que también pone la app,
;     para que el icono anclado y la búsqueda de Windows no se desemparejen) y «Lune CD
;     (terminal)» (LunePatata.exe). En el escritorio, solo si lo marcas.
;   · Tus datos (%APPDATA%\Lune CD) y lo local (%LOCALAPPDATA%\Lune CD) nunca los toca al
;     instalar ni al actualizar. Al desinstalar pregunta (por defecto, no se borran).
;   · Antes de reemplazar archivos espera a que Lune se cierre (mutex LuneCD_Abierta, el
;     de nucleo/rutas.MUTEX_ABIERTA). El actualizador lo lanza en silencio con /RELANZAR=1
;     para que Lune se vuelva a abrir al terminar.
;   · Al desinstalar quita la entrada de arranque con Windows (Run\LuneCD) solo si apunta
;     a esta instalación (tu copia de código tiene la suya).

#ifndef Version
  #error Falta /DVersion=<versión> (lo pasa packaging/construir.py)
#endif
#ifndef VersionWin
  #define VersionWin Version + ".0.0"
#endif
#ifndef Origen
  #define Origen "..\dist\Lune CD"
#endif
#ifndef Salida
  #define Salida "..\dist"
#endif

#define AppUserModelID "DiegoLizarraga.LuneCD"

[Setup]
AppId={{CA44A144-89E1-4002-9BF6-D6EBE2578EE7}
AppName=Lune CD
AppVersion={#Version}
AppVerName=Lune CD {#Version}
AppPublisher=Diego Lizarraga
AppPublisherURL=https://github.com/DiegoLizarraga/Lune_CD
AppSupportURL=https://github.com/DiegoLizarraga/Lune_CD/issues
AppUpdatesURL=https://github.com/DiegoLizarraga/Lune_CD/releases
AppComments=Tu asistente en el PC, con personalidad
PrivilegesRequired=lowest
DefaultDirName={autopf}\Lune CD
DisableProgramGroupPage=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=..\assets\lune_icon.ico
SetupMutex=LuneCD_Instalador
UninstallDisplayName=Lune CD
UninstallDisplayIcon={app}\Lune.exe
VersionInfoVersion={#VersionWin}
VersionInfoCompany=Lune CD
VersionInfoDescription=Instalador de Lune CD
VersionInfoProductName=Lune CD
VersionInfoProductTextVersion={#Version}
CloseApplications=yes
RestartApplications=no
OutputDir={#Salida}
OutputBaseFilename=LuneCD-Setup-{#Version}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
FinishedLabel=Ya estoy instalada en tu PC. Me encuentras en el menú Inicio como «Lune CD» (y «Lune CD (terminal)» si me prefieres en la consola).
FinishedLabelNoIcons=Ya estoy instalada en tu PC.

[Tasks]
Name: "escritorio"; Description: "Ponerme también en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[InstallDelete]
; Lo del programa de la versión anterior (nunca tus datos: esos viven en %APPDATA%\Lune CD).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Lune CD"; Filename: "{app}\Lune.exe"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"; Comment: "Tu asistente en el PC, con personalidad"
Name: "{autoprograms}\Lune CD (terminal)"; Filename: "{app}\LunePatata.exe"; WorkingDir: "{app}"; Comment: "Lune en la terminal (modo patata)"
Name: "{autodesktop}\Lune CD"; Filename: "{app}\Lune.exe"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"; Comment: "Tu asistente en el PC, con personalidad"; Tasks: escritorio

[Run]
Filename: "{app}\Lune.exe"; Description: "Abrir Lune"; Flags: postinstall skipifsilent nowait
; El actualizador me instala en silencio con /RELANZAR=1: al terminar, Lune vuelve a abrirse.
Filename: "{app}\Lune.exe"; Flags: nowait; Check: RelanzarTrasActualizar

[UninstallDelete]
; Por si algo escribió dentro del programa (lo tuyo está fuera y se pregunta aparte).
Type: filesandordirs; Name: "{app}\_internal"

[Code]
const
  MutexLune = 'LuneCD_Abierta';
  EsperaSilenciosaMs = 20000;
  EsperaConVentanaMs = 3000;
  ClaveRun = 'Software\Microsoft\Windows\CurrentVersion\Run';
  ClaveAprobado = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run';
  ValorRun = 'LuneCD';
  ComoCerrarme = 'Ciérrame (clic derecho en mi icono de la bandeja y «Salir», o /salir en la terminal) y pulsa Reintentar.';

function LuneAbierta: Boolean;
begin
  Result := CheckForMutexes(MutexLune);
end;

{ Espera hasta MaxMs a que Lune suelte su mutex. True si ya está cerrada. }
function EsperarCierre(MaxMs: Integer): Boolean;
var
  Esperado: Integer;
begin
  Esperado := 0;
  while LuneAbierta and (Esperado < MaxMs) do
  begin
    Sleep(250);
    Esperado := Esperado + 250;
  end;
  Result := not LuneAbierta;
end;

{ Reintentar/Cancelar hasta que Lune se cierre. False si cancelas. }
function PedirCierre(const Texto: String): Boolean;
begin
  Result := True;
  while LuneAbierta do
  begin
    if MsgBox(Texto, mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
    EsperarCierre(EsperaConVentanaMs);
  end;
end;

function RelanzarTrasActualizar: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELANZAR|0}') = '1');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  { En silencio viene del actualizador, que cierra Lune justo después de lanzarme: le doy
    hasta 20 s. Con ventanas, un momento y luego te pregunto. }
  if WizardSilent then
  begin
    if not EsperarCierre(EsperaSilenciosaMs) then
      Log('Lune sigue abierta tras 20 s: sigo y CloseApplications se encarga.');
    Exit;
  end;
  if EsperarCierre(EsperaConVentanaMs) then
    Exit;
  Result := PedirCierre('Estoy abierta y así no me puedo instalar encima.' + #13#10#13#10 + ComoCerrarme);
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  if not LuneAbierta then
    Exit;
  if UninstallSilent then
  begin
    EsperarCierre(EsperaSilenciosaMs);
    Exit;
  end;
  Result := PedirCierre('Sigo abierta y así no me puedo desinstalar.' + #13#10#13#10 + ComoCerrarme);
end;

{ La entrada de «arrancar con Windows» (servicios/autoinicio.py), solo si es de esta carpeta. }
procedure QuitarArranqueConWindows;
var
  Valor, Carpeta: String;
begin
  if not RegQueryStringValue(HKCU, ClaveRun, ValorRun, Valor) then
    Exit;
  Carpeta := Lowercase(AddBackslash(ExpandConstant('{app}')));
  if Pos(Carpeta, Lowercase(Valor)) = 0 then
  begin
    Log('La entrada Run\LuneCD no apunta a esta instalación: la dejo como está.');
    Exit;
  end;
  RegDeleteValue(HKCU, ClaveRun, ValorRun);
  RegDeleteValue(HKCU, ClaveAprobado, ValorRun);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos, Local: String;
begin
  if CurUninstallStep = usUninstall then
    QuitarArranqueConWindows;
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Datos := ExpandConstant('{userappdata}\Lune CD');
    Local := ExpandConstant('{localappdata}\Lune CD');
    if not DirExists(Datos) and not DirExists(Local) then
      Exit;
    if MsgBox('Ya me desinstalé. ¿Borro también tus datos?' + #13#10#13#10 +
              'Son tus chats, lo que recuerdo de ti, tus ajustes, tus notas, tus alarmas y tus bailes (' +
              Datos + '), y lo que guardé en ' + Local + ' (registros, cachés y los bots).' + #13#10#13#10 +
              'Si me vuelves a instalar y los dejas, me acordaré de todo. Si dices que sí, se borran para siempre.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(Datos, True, True, True);
      DelTree(Local, True, True, True);
    end;
  end;
end;
