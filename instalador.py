"""
instalador.py — Instalador de Lune CD para usuarios nuevos (ventana con Tkinter).

Explica QUÉ hace cada componente y PARA QUÉ sirve (p. ej. "esto es para que Lune
hable"), marca lo que ya está instalado, y deja elegir qué instalar. Usa solo la
librería estándar (Tkinter viene con Python) para poder correr ANTES de instalar
nada más. Se lanza con `instalar_lune.bat` o desde Ajustes → "Instalar componentes".

Para un usuario nuevo (2026-09):
  · deja marcado lo recomendado (lo de requirements.txt + la interfaz completa);
  · instala el núcleo junto y cada opcional POR SEPARADO: si uno falla (p. ej. no
    tiene versión para un Python muy nuevo) los demás siguen, y el resumen lo dice;
  · PyQt6-WebEngine con la misma versión que PyQt6;
  · al acabar comprueba el núcleo, crea el acceso directo «Lune CD» (escritorio y
    menú Inicio) y ofrece «Abrir Lune»; todo queda también en instalacion.log.

La lista de componentes vive en servicios/actualizador.py (NUCLEO y OPCIONALES);
aquí hay una copia de respaldo por si ese módulo no se puede importar.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# ── Componentes (respaldo; la fuente de verdad es servicios/actualizador.py) ────
_NUCLEO_RESPALDO = {
    "Núcleo de Lune (obligatorio)": {
        "modulos": {"PyQt6": "PyQt6", "requests": "requests", "websockets": "websockets"},
        "nota": "La ventana, la conexión con los modelos y la red entre equipos. Sin esto no arranca.",
    },
    "Sonido: mezclador, alarmas y bailes (obligatorio)": {
        "modulos": {"numpy": "numpy", "sounddevice": "sounddevice", "imageio_ffmpeg": "imageio-ffmpeg"},
        "nota": "numpy: el mezclador de sonidos, las alarmas y los bailes (sin él no cargan). "
                "sounddevice: la salida del mezclador. imageio-ffmpeg: leer mp3/ogg/m4a.",
    },
}
if sys.platform == "win32":
    _NUCLEO_RESPALDO["Windows: mascota y detector de música (obligatorio)"] = {
        "modulos": {"win32gui": "pywin32", "comtypes": "comtypes"},
        "nota": "La mascota fantasma y la ventana activa (pywin32); el detector de música y el "
                "audio por programa para bailar (comtypes). Solo Windows.",
    }
_OPCIONALES_RESPALDO = {
    "Voz de salida (Lune habla)": {"modulos": {"edge_tts": "edge-tts", "pygame": "pygame"},
        "nota": "Para que Lune lea sus respuestas en voz alta (edge-tts necesita internet)."},
    "Voz de entrada (dictado)": {"modulos": {"faster_whisper": "faster-whisper", "sounddevice": "sounddevice"},
        "nota": "Para hablarle por micrófono y para el modo llamada. 100% local; pesa bastante."},
    "Interfaz completa (piel web animada)": {"modulos": {"PyQt6.QtWebEngineWidgets": "PyQt6-WebEngine"},
        "nota": "La interfaz animada, la mascota en video y el avatar 3D (VRM). Sin esto se usa la nativa ligera."},
    "Leer PDF": {"modulos": {"pypdf": "pypdf"}, "nota": "Para adjuntar PDF al chat."},
    "Leer Word (.docx)": {"modulos": {"docx": "python-docx"}, "nota": "Para adjuntar Word al chat."},
    "Optimizador del sistema": {"modulos": {"psutil": "psutil"},
        "nota": "Monitor de CPU/RAM y limpieza; también el modo juego, el recorte de RAM y reconocer programas."},
    "Red local (descubrir dispositivos)": {"modulos": {"zeroconf": "zeroconf"},
        "nota": "Para que Lune encuentre otros equipos con Lune en tu red."},
    "Comentar lo que ves en pantalla": {"modulos": {"PIL": "Pillow"},
        "nota": "La captura con la que la mascota comenta tu pantalla (nunca con un juego abierto)."},
    "Voz 100% local (Kokoro)": {"modulos": {"kokoro_onnx": "kokoro-onnx"},
        "nota": "Lune habla sin internet. Necesita además espeak-ng y los pesos en modelos_voz/."},
    "Conversión de voz RVC (experimental)": {"modulos": {"rvc_python": "rvc-python"},
        "nota": "Cambia el timbre de voz con un modelo .pth. Muy pesado (torch)."},
}


# Red de seguridad: lo que requirements.txt pide y las tablas (las de
# servicios/actualizador.py o las de respaldo) no traigan. Lo del núcleo se añade AL
# NÚCLEO aunque ya salga como opcional (antes numpy se quedaba en opcional y sin él no
# cargan el mezclador, las alarmas con sonido ni los bailes).
_EXTRAS_NUCLEO = {
    "Sonidos, alarmas y mascota (obligatorio)": {
        "modulos": {"numpy": "numpy", "sounddevice": "sounddevice", "imageio_ffmpeg": "imageio-ffmpeg"},
        "nota": "El mezclador de sonidos de la mascota, alarmas y bailes (numpy + sounddevice) y "
                "un ffmpeg para leer mp3/ogg/m4a (imageio-ffmpeg; sin él solo .wav).",
    },
}
if sys.platform == "win32":
    _EXTRAS_NUCLEO["Windows: mascota y audio por proceso (obligatorio)"] = {
        "modulos": {"win32gui": "pywin32", "comtypes": "comtypes"},
        "nota": "Ventanas de la mascota (atravesar clics, ventana activa) y el audio por programa "
                "para bailar con la música. Solo Windows.",
    }
_EXTRAS_OPCIONALES = {
    "Voz de respaldo (gTTS)": {"modulos": {"gtts": "gtts"},
                               "nota": "Si edge-tts falla, Lune habla con la voz de Google."},
}


def _paquetes(*tablas) -> set:
    return {p.lower() for tabla in tablas for info in tabla.values() for p in info["modulos"].values()}


def _con_extras(nucleo: dict, opcionales: dict):
    """Añade a las tablas los paquetes de los extras que falten: los del núcleo, si no
    están YA EN EL NÚCLEO (marcado por defecto) aunque salgan como opcionales; los
    opcionales, si no están en ninguna."""
    nuevo_nucleo = dict(nucleo)
    for nombre, info in _EXTRAS_NUCLEO.items():
        faltan = {m: p for m, p in info["modulos"].items() if p.lower() not in _paquetes(nuevo_nucleo)}
        if faltan:
            nuevo_nucleo[nombre] = {**info, "modulos": faltan}
    nuevos_opcionales = dict(opcionales)
    for nombre, info in _EXTRAS_OPCIONALES.items():
        faltan = {m: p for m, p in info["modulos"].items()
                  if p.lower() not in _paquetes(nuevo_nucleo, nuevos_opcionales)}
        if faltan:
            nuevos_opcionales[nombre] = {**info, "modulos": faltan}
    return nuevo_nucleo, nuevos_opcionales


def _tablas():
    try:
        sys.path.insert(0, str(RAIZ))
        from servicios import actualizador as A
        return _con_extras(A.NUCLEO, A.OPCIONALES)
    except Exception:
        return _con_extras(_NUCLEO_RESPALDO, _OPCIONALES_RESPALDO)


def _instalado(modulos: dict) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in modulos)


def estado_node(which=None, ejecutar=None) -> dict:
    """{ok, version, mensaje} de Node.js, que no es de pip: lo necesitan los bots de
    Telegram y de Minecraft. El de servicios/actualizador.py o, si no se puede importar,
    un aviso sin comprobar la versión."""
    try:
        sys.path.insert(0, str(RAIZ))
        from servicios import actualizador as A
        return A.estado_node(which=which, ejecutar=ejecutar)
    except Exception:
        import shutil
        ruta = (which or shutil.which)("node")
        return {"ok": bool(ruta), "version": "",
                "mensaje": ("Node.js: encontrado (los bots de Telegram y Minecraft piden la 18 o más nueva)."
                            if ruta else "Falta Node.js 18 o más nuevo (nodejs.org) para el bot de Telegram "
                                         "y el de Minecraft. El resto de Lune funciona sin él.")}


# ── Lo que se marca solo para un usuario nuevo ──────────────────────────────────
# Lo recomendado es lo que trae requirements.txt (lo que Lune usa en un equipo normal)
# más la interfaz «Completa», que es la que se abre por defecto. Lo pesado (dictado,
# Kokoro, RVC) se queda sin marcar: se elige a propósito.
RECOMENDADOS_ADEMAS = {"pyqt6-webengine"}
ARCHIVO_LOG = RAIZ / "instalacion.log"
SIN_CONSOLA = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def requisitos(ruta: Path = RAIZ / "requirements.txt") -> set:
    """Paquetes de requirements.txt que aplican a esta plataforma (en minúsculas, sin versión)."""
    import re
    nombres = set()
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return nombres
    for linea in lineas:
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        paquete, _, marca = linea.partition(";")
        if "win32" in marca and sys.platform != "win32":
            continue
        nombres.add(re.split(r"[<>=!~ \[]", paquete.strip(), maxsplit=1)[0].lower())
    return nombres


def recomendado(info: dict, base: set = None) -> bool:
    """¿Se marca solo? Si todos sus paquetes están en requirements.txt (o en los de además)."""
    base = requisitos() if base is None else base
    paquetes = {p.lower() for p in info["modulos"].values()}
    return bool(paquetes) and paquetes <= (base | RECOMENDADOS_ADEMAS)


def aviso_python(version=None) -> str:
    """Aviso sobre la versión de Python ("" si no hace falta)."""
    v = tuple(version or sys.version_info)[:2]
    if v < (3, 10):
        return (f"Python {v[0]}.{v[1]} es demasiado viejo: Lune necesita 3.10 o más nuevo. "
                "Instala Python 3.13 desde python.org (o con instalar_lune.bat).")
    if v >= (3, 14):
        return (f"Python {v[0]}.{v[1]} es muy nuevo: algún componente opcional (el dictado, "
                "por ejemplo) puede no tener versión todavía. Si alguno falla, instala Python 3.13.")
    return ""


def version_pyqt6(ejecutar=subprocess.run) -> str:
    """Versión de PyQt6 instalada en ESTE Python ("" si no está). En un proceso aparte:
    así ve lo que se acaba de instalar."""
    try:
        r = ejecutar([sys.executable, "-c", "import importlib.metadata as m; print(m.version('PyQt6'))"],
                     capture_output=True, text=True, timeout=60, **SIN_CONSOLA)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def paquetes_para(info: dict, pyqt: str = "") -> list:
    """Los paquetes pip de un componente. PyQt6-WebEngine va con la MISMA versión que
    PyQt6 (6.9 con 6.9): si no coinciden, la interfaz completa no arranca."""
    salida = []
    for paquete in info["modulos"].values():
        partes = pyqt.split(".")
        if paquete.lower() == "pyqt6-webengine" and len(partes) >= 2:
            salida.append(f"{paquete}=={partes[0]}.{partes[1]}.*")
        else:
            salida.append(paquete)
    return salida


def plan_instalacion(elegidos: list) -> list:
    """[(nombre, info, obligatorio)] → pasos [(titulo, info_o_None, obligatorio)]: primero
    pip al día, luego TODO el núcleo junto y después cada opcional por separado (si uno
    falla, por ejemplo por no tener versión para este Python, los demás siguen)."""
    pasos = [("pip al día", None, True)]
    nucleo = [info for _n, info, obligatorio in elegidos if obligatorio]
    if nucleo:
        juntos = {m: p for info in nucleo for m, p in info["modulos"].items()}
        pasos.append(("Núcleo de Lune", {"modulos": juntos}, True))
    pasos += [(n, info, False) for n, info, obligatorio in elegidos if not obligatorio]
    return pasos


def _pip(paquetes: list, escribir, ejecutar=None) -> int:
    """pip install; cada línea de salida va a `escribir`. → código de salida."""
    orden = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *paquetes]
    escribir(f"> {' '.join(orden[1:])}\n")
    if ejecutar is not None:
        return ejecutar(orden, escribir)
    p = subprocess.Popen(orden, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", **SIN_CONSOLA)
    for linea in p.stdout:
        escribir(linea)
    return p.wait()


def ejecutar_plan(pasos: list, escribir, ejecutar=None, pyqt=None) -> dict:
    """Corre los pasos y devuelve {"ok": [titulos], "fallo": [titulos]}. `ejecutar(orden,
    escribir) → código` y `pyqt() → versión` se inyectan en los tests."""
    pyqt = pyqt or version_pyqt6
    hechos = {"ok": [], "fallo": []}
    for titulo, info, _obligatorio in pasos:
        escribir(f"\n== {titulo} ==\n")
        if info is None:                                  # pip al día (si falla, se sigue igual)
            _pip(["--upgrade", "pip"], escribir, ejecutar)
            continue
        paquetes = paquetes_para(info, pyqt() if "PyQt6-WebEngine" in info["modulos"].values() else "")
        codigo = _pip(paquetes, escribir, ejecutar)
        if codigo != 0 and paquetes != list(info["modulos"].values()):
            escribir("No había esa versión exacta; pruebo con la más nueva.\n")
            codigo = _pip(list(info["modulos"].values()), escribir, ejecutar)
        hechos["ok" if codigo == 0 else "fallo"].append(titulo)
    return hechos


def comprobar_nucleo(ejecutar=subprocess.run) -> tuple:
    """(ok, texto): ¿arranca lo imprescindible en este Python?"""
    prueba = "import PyQt6.QtWidgets, requests, websockets, numpy"
    try:
        r = ejecutar([sys.executable, "-c", prueba], capture_output=True, text=True, timeout=120, **SIN_CONSOLA)
    except Exception as e:
        return False, f"No pude comprobar el núcleo: {e}"
    if r.returncode == 0:
        return True, "Núcleo comprobado: Lune puede arrancar."
    ultima = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["?"]
    return False, f"Al núcleo le falta algo: {ultima[0]}"


def _ps(texto: str) -> str:
    """Cadena literal de PowerShell (comillas simples; una ' se escribe '')."""
    return "'" + str(texto).replace("'", "''") + "'"


def orden_accesos_directos(raiz: Path = RAIZ, escritorio: bool = True, menu_inicio: bool = True) -> str:
    """Script de PowerShell que crea «Lune CD.lnk» (abre iniciar_lune.vbs con el icono de
    Lune) en el escritorio y en el menú Inicio. GetFolderPath respeta un escritorio movido
    a OneDrive. Solo WScript.Shell: no hace falta pywin32 (aún no está instalado)."""
    wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    carpetas = ([("Desktop")] if escritorio else []) + (["Programs"] if menu_inicio else [])
    lineas = ["$sh = New-Object -ComObject WScript.Shell"]
    for carpeta in carpetas:
        lineas += [
            f"$l = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath('{carpeta}')) 'Lune CD.lnk'))",
            f"$l.TargetPath = {_ps(wscript)}",
            f"$l.Arguments = {_ps(chr(34) + str(raiz / 'iniciar_lune.vbs') + chr(34))}",
            f"$l.WorkingDirectory = {_ps(raiz)}",
            f"$l.IconLocation = {_ps(raiz / 'assets' / 'lune_icon.ico')}",
            "$l.Description = 'Lune CD, tu asistente de escritorio'",
            "$l.Save()",
        ]
    return "; ".join(lineas)


def crear_accesos_directos(raiz: Path = RAIZ, escritorio: bool = True, menu_inicio: bool = True,
                           ejecutar=subprocess.run) -> tuple:
    """(ok, texto). Solo Windows."""
    if sys.platform != "win32":
        return False, "Los accesos directos son solo para Windows."
    if not (escritorio or menu_inicio):
        return True, ""
    try:
        r = ejecutar(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                      orden_accesos_directos(raiz, escritorio, menu_inicio)],
                     capture_output=True, text=True, timeout=60, **SIN_CONSOLA)
    except Exception as e:
        return False, f"No pude crear el acceso directo: {e}"
    if r.returncode != 0:
        return False, f"No pude crear el acceso directo: {(r.stderr or '').strip()[:200]}"
    donde = " y ".join(t for t, si in (("el escritorio", escritorio), ("el menú Inicio", menu_inicio)) if si)
    return True, f"Acceso directo «Lune CD» creado en {donde}."


def abrir_lune(raiz: Path = RAIZ, lanzar=subprocess.Popen) -> None:
    """Abre Lune como lo haría el acceso directo."""
    if sys.platform == "win32":
        lanzar(["wscript.exe", str(raiz / "iniciar_lune.vbs")], cwd=str(raiz))
    else:
        lanzar([sys.executable, str(raiz / "main.py")], cwd=str(raiz))


def main() -> int:
    import datetime
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    nucleo, opcionales = _tablas()
    base = requisitos()
    win = tk.Tk()
    win.title("Instalar Lune CD")
    win.geometry("780x700")
    win.configure(bg="#0f1424")
    estilo = ttk.Style(win)
    try:
        estilo.theme_use("clam")
    except Exception:
        pass
    estilo.configure("TFrame", background="#0f1424")
    estilo.configure("TLabel", background="#0f1424", foreground="#eaf1ff", font=("Segoe UI", 10))
    estilo.configure("Titulo.TLabel", foreground="#00e5ff", font=("Segoe UI", 15, "bold"))
    estilo.configure("Nota.TLabel", foreground="#97a6c4", font=("Segoe UI", 9))
    estilo.configure("Aviso.TLabel", foreground="#ffe000", font=("Segoe UI", 9, "bold"))
    estilo.configure("Ok.TLabel", foreground="#00e5ff", font=("Consolas", 9, "bold"))
    estilo.configure("TCheckbutton", background="#0f1424", foreground="#eaf1ff", font=("Segoe UI", 10, "bold"))
    estilo.map("TCheckbutton", background=[("active", "#0f1424")])
    estilo.configure("TButton", font=("Segoe UI", 10, "bold"))

    raiz = ttk.Frame(win, padding=16); raiz.pack(fill="both", expand=True)
    ttk.Label(raiz, text="月  Instalar Lune CD", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(raiz, style="Nota.TLabel", wraplength=740, justify="left",
              text=f"Python {sys.version.split()[0]} en {sys.executable}\n"
                   "Ya dejé marcado lo recomendado. Cada componente explica para qué sirve; lo que ya "
                   "tienes aparece con OK. Lo pesado (dictado, Kokoro, RVC) lo eliges tú.").pack(anchor="w", pady=(2, 4))
    aviso = aviso_python()
    if aviso:
        ttk.Label(raiz, text=aviso, style="Aviso.TLabel", wraplength=740, justify="left").pack(anchor="w", pady=(0, 6))

    # Lista con scroll
    cont = ttk.Frame(raiz); cont.pack(fill="both", expand=True)
    canvas = tk.Canvas(cont, bg="#0f1424", highlightthickness=0)
    sb = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
    lista = ttk.Frame(canvas)
    lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=lista, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

    filas = []                                         # (nombre, BooleanVar, info, obligatorio)
    def fila(nombre, info, obligatorio):
        ya = _instalado(info["modulos"])
        reco = not obligatorio and recomendado(info, base)
        v = tk.BooleanVar(value=(obligatorio or reco) and not ya)
        f = ttk.Frame(lista, padding=(0, 6)); f.pack(fill="x")
        etiqueta = nombre + ("  (obligatorio)" if obligatorio else "  (recomendado)" if reco else "")
        cb = ttk.Checkbutton(f, text=etiqueta, variable=v)
        cb.pack(anchor="w")
        if ya:
            v.set(False); cb.state(["disabled"])
            ttk.Label(f, text="OK · ya instalado", style="Ok.TLabel").pack(anchor="w", padx=24)
        ttk.Label(f, text=info["nota"], style="Nota.TLabel", wraplength=700, justify="left").pack(anchor="w", padx=24)
        ttk.Label(f, text="pip install " + " ".join(info["modulos"].values()), style="Nota.TLabel").pack(anchor="w", padx=24)
        filas.append((nombre, v, info, obligatorio))
    for n, i in nucleo.items(): fila(n, i, True)
    for n, i in opcionales.items(): fila(n, i, False)

    acceso = tk.BooleanVar(value=sys.platform == "win32")
    if sys.platform == "win32":
        ttk.Checkbutton(raiz, text="Crear el acceso directo «Lune CD» en el escritorio y en el menú Inicio",
                        variable=acceso).pack(anchor="w", pady=(8, 0))

    node = estado_node()
    ttk.Label(raiz, style="Ok.TLabel" if node["ok"] else "Nota.TLabel", wraplength=740, justify="left",
              text=node["mensaje"]).pack(anchor="w", pady=(6, 0))
    ttk.Label(raiz, style="Nota.TLabel", wraplength=740, justify="left",
              text="Aparte de esto (no es de pip): para los bots de Telegram y Minecraft, Node.js 18+ "
                   "(nodejs.org; sus paquetes los instala Lune con npm ci: el de Telegram al encenderlo, "
                   "el de Minecraft con «Instalar el bot» en Ajustes → Minecraft); para el modelo "
                   "local instala Ollama (ollama.com) y baja un modelo con `ollama pull <modelo>`; para "
                   "Kokoro en español instala espeak-ng.").pack(anchor="w", pady=(4, 4))

    log = scrolledtext.ScrolledText(raiz, height=8, bg="#080b16", fg="#eaf1ff", insertbackground="#eaf1ff",
                                    font=("Consolas", 9), relief="flat")
    log.pack(fill="x", pady=(6, 8))

    botones = ttk.Frame(raiz); botones.pack(fill="x")
    btn = ttk.Button(botones, text="Instalar lo marcado")
    btn.pack(side="left")
    btn_abrir = ttk.Button(botones, text="Abrir Lune", command=lambda: (abrir_lune(), win.destroy()))
    btn_abrir.pack(side="left", padx=8)
    if not _instalado({"PyQt6": "PyQt6"}):
        btn_abrir.state(["disabled"])
    ttk.Button(botones, text="Descargar Ollama", command=lambda: webbrowser.open("https://ollama.com/download")).pack(side="left")
    if not node["ok"]:
        ttk.Button(botones, text="Descargar Node.js",
                   command=lambda: webbrowser.open("https://nodejs.org/")).pack(side="left", padx=8)
    ttk.Button(botones, text="Cerrar", command=win.destroy).pack(side="right")

    def escribir(t):
        log.insert("end", t); log.see("end")
        try:
            with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
                f.write(t)
        except OSError:
            pass

    def desde_hilo(t):
        win.after(0, escribir, t)

    def instalar():
        elegidos = [(n, info, obligatorio) for n, v, info, obligatorio in filas if v.get()]
        if not elegidos and not acceso.get():
            escribir("Nada marcado.\n"); return
        btn.state(["disabled"])
        escribir(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M} · Python {sys.version.split()[0]} "
                 f"({sys.executable}) ===\n")

        def correr():
            hechos = ejecutar_plan(plan_instalacion(elegidos), desde_hilo) if elegidos else {"ok": [], "fallo": []}
            ok_nucleo, texto_nucleo = comprobar_nucleo()
            resumen = ["", "== Resumen =="]
            if hechos["ok"]:
                resumen.append("Instalado: " + ", ".join(hechos["ok"]) + ".")
            if hechos["fallo"]:
                resumen.append("No se pudo: " + ", ".join(hechos["fallo"]) + ". El detalle está arriba y en "
                               "instalacion.log; Lune funciona sin lo opcional.")
            resumen.append(texto_nucleo)
            if acceso.get():
                resumen.append(crear_accesos_directos()[1])
            if ok_nucleo:
                resumen.append("Listo: pulsa «Abrir Lune» (o usa el acceso directo).")
            desde_hilo("\n".join(r for r in resumen if r is not None) + "\n")

            def al_final():
                btn.state(["!disabled"])
                if ok_nucleo:
                    btn_abrir.state(["!disabled"])
            win.after(0, al_final)
        threading.Thread(target=correr, daemon=True).start()
    btn.configure(command=instalar)

    win.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
