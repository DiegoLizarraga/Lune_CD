"""
servicios/diagnostico.py — «¿Tengo todo lo que necesito?»: la comprobación de Lune.

`LunePatata.exe --comprobar` (o `python patata.py --comprobar`) la imprime y sale con 0
si todo va bien y 1 si algo falla. Es la prueba de humo del build (packaging/construir.py)
y de la instalación de prueba en GitHub (.github/workflows/release.yml), y te sirve a ti
para saber qué le falta a tu Lune. Con `--json`, lo mismo en JSON.

Secciones, en este orden:
  recursos  lo que trae Lune y solo se lee (la piel web, el vídeo de inicio, las fuentes…)
  datos     que tu carpeta de datos (y la local) se puedan escribir, y el espacio libre
  modulos   que se importen las librerías que van en el paquete
  equipo    tu micrófono y tus altavoces, y si el modelo del dictado ya está bajado (sin
            ellos no es un fallo de Lune: salen como «no aplica», también en el build)
  red       solo con red=True: COMPROBACIONES_RED (internet, la clave de OpenRouter,
            Ollama, el bot de Telegram y Node.js). Lo que no tienes configurado sale como
            «no aplica». La clave y el token nunca salen en el detalle (servicios/pruebas).

Con red, el informe es «Comprobar que todo funciona» de Ajustes (web: la tarjeta
extra/diagnostico.jsx por la señal `diagnostico` del puente; nativa: ui/pruebas_qt.py) y
`/diagnostico` de patata. Las pruebas de cada apartado viven en servicios/pruebas.py, las
mismas que los botones «Probar» de Ajustes.

Sin Qt al importar: todo se importa dentro de comprobar(), y en un orden que no repite el
crash de MSVCP140 (nucleo/runtime_win.py): primero la precarga del runtime de C++, luego
lo de C++ (ctranslate2, onnxruntime, av, faster_whisper), después PyQt6 y el resto. Al
final se mira qué msvcp140.dll acabó cargada de verdad.

Resultado (se puede pasar a JSON tal cual):
    {"ok": bool, "version": "11.2", "modo": "instalada"|"codigo",
     "items": [{"id", "seccion", "nombre", "ok": True|False|None, "detalle"}]}
ok None = no aplica aquí (p. ej. pywin32 fuera de Windows): no cuenta como fallo.

Añadir una comprobación: una función (Contexto) -> (ok, detalle) y una Comprobacion(id,
seccion, nombre, funcion) en la lista que toque (o en COMPROBACIONES_RED). Si la función
lanza, el item sale con ok False y la excepción como detalle: nunca tumba el informe.
`comprobar(…, parar=fn)` deja de comprobar en cuanto fn() dice True (la interfaz se cierra).

Los ajustes (claves, URLs, modelo de Whisper) se leen de datos.json y config.json SIN
escribir nada: la comprobación no crea ni migra archivos (Contexto.ajustes los cambia).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

Resultado = Tuple[Optional[bool], str]

SECCIONES = {
    "recursos": "Lo que traigo",
    "datos": "Tus carpetas",
    "modulos": "Librerías",
    "equipo": "Tu equipo",
    "red": "Red y servicios",
}

# El runtime de C++ que necesitan ctranslate2 y onnxruntime (ver nucleo/runtime_win.py).
MSVC_MINIMA = (14, 40)

# Dentro de la app («Comprobar que todo funciona» de Ajustes) lo que aún no está cargado no se
# carga solo para mirarlo: QtWebEngine no se puede importar después de crear la QApplication,
# y lo del dictado son cientos de MB que se quedarían en memoria (y es lo que podría tumbar el
# proceso si el runtime de C++ fuera el viejo). De esos basta con saber que están: «Probar
# dictado» los carga de verdad, y `--comprobar` (otro proceso) también.
SOLO_MIRAR_EN_APP = ("PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtMultimedia", "ctranslate2",
                     "onnxruntime", "av", "faster_whisper")
SIN_CARGAR = "_lune_sin_cargar"


@dataclass
class Contexto:
    """Dónde mirar y cómo importar. Los tests lo rellenan con carpetas y módulos falsos."""
    recursos: Path
    datos: Path
    local: Path
    importar: Callable[[str], Any] = importlib.import_module
    windows: bool = sys.platform == "win32"
    # Precarga del runtime de C++ antes de nada pesado; devuelve su informe para el log.
    precargar: Optional[Callable[[], str]] = None
    # Qué msvcp140.dll hay cargada en el proceso: (ruta, versión) o None.
    msvc_cargada: Optional[Callable[[], Optional[Tuple[str, Tuple[int, ...]]]]] = None
    informe_precarga: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    # Tu equipo y la red (servicios/pruebas). None = lo de verdad; los tests ponen falsos.
    http: Optional[Callable[..., Any]] = None                 # como requests.get(url, headers=, timeout=)
    ajustes: Optional[Callable[[], Dict[str, Any]]] = None    # claves y URLs (ver _ajustes)
    node: Optional[Callable[[], Dict[str, Any]]] = None       # actualizador.estado_node
    sonido: Any = None                                        # el módulo sounddevice (o uno falso)
    whisper: Optional[Callable[[str], bool]] = None           # voz_entrada.modelo_descargado
    disco: Optional[Callable[[str], Any]] = None              # shutil.disk_usage
    listar_ollama: Optional[Callable[[str], Tuple[bool, List[str], str]]] = None
    carpeta_bot: Optional[Callable[[], bool]] = None          # TelegramBotWorker.preparar_carpeta


@dataclass(frozen=True)
class Comprobacion:
    id: str
    seccion: str
    nombre: str
    funcion: Callable[[Contexto], Resultado]


def _corto(texto: Any, maximo: int = 220) -> str:
    t = " ".join(str(texto).split())
    return t if len(t) <= maximo else t[: maximo - 1] + "…"


def _fallo(e: BaseException) -> str:
    return _corto(f"{type(e).__name__}: {e}")


# ── Recursos (lo que trae Lune) ──────────────────────────────────────────────────

def _archivo(relativa: str) -> Callable[[Contexto], Resultado]:
    def comprobar(ctx: Contexto) -> Resultado:
        ruta = ctx.recursos / relativa
        if ruta.is_file() and ruta.stat().st_size > 0:
            return True, relativa
        return False, f"no encuentro {relativa}"
    return comprobar


def _carpeta(relativa: str, patron: str) -> Callable[[Contexto], Resultado]:
    def comprobar(ctx: Contexto) -> Resultado:
        ruta = ctx.recursos / relativa
        n = sum(1 for p in ruta.glob(patron) if p.is_file()) if ruta.is_dir() else 0
        if n:
            return True, f"{relativa}/ ({n} {'archivo' if n == 1 else 'archivos'})"
        return False, f"no encuentro {relativa}/{patron}"
    return comprobar


RECURSOS: List[Comprobacion] = [
    Comprobacion("piel_web", "recursos", "Piel web (interfaz completa)",
                 _archivo("ui_web/ui_kits/lune-desktop/index.html")),
    Comprobacion("video_inicio", "recursos", "Vídeo de inicio", _archivo("assets/inicio.mp4")),
    Comprobacion("icono", "recursos", "Mi icono", _archivo("assets/lune_icon.ico")),
    Comprobacion("fuentes", "recursos", "Fuentes", _carpeta("fonts", "*.ttf")),
    Comprobacion("caritas", "recursos", "Mis caritas (interfaz ligera)", _carpeta("lune_face", "*.png")),
    Comprobacion("sonidos", "recursos", "Sonidos por defecto", _archivo("sonidos/default/pack.json")),
    Comprobacion("plantilla_datos", "recursos", "Plantilla de datos", _archivo("datos.example.json")),
]


# ── Tus carpetas (se tienen que poder escribir) ──────────────────────────────────

def _escribible(ruta: Path) -> Resultado:
    ruta.mkdir(parents=True, exist_ok=True)
    prueba = ruta / f".lune_prueba_{uuid.uuid4().hex[:8]}.tmp"
    try:
        prueba.write_text("ok", encoding="utf-8")
        leido = prueba.read_text(encoding="utf-8")
    finally:
        try:
            prueba.unlink()
        except OSError:
            pass
    return (leido == "ok"), str(ruta)


def _datos_escribible(ctx: Contexto) -> Resultado:
    return _escribible(ctx.datos)


def _local_escribible(ctx: Contexto) -> Resultado:
    if Path(ctx.local).resolve() == Path(ctx.datos).resolve():
        return None, "es la misma que la de datos"
    return _escribible(ctx.local)


def _de_prueba(r: Dict[str, Any]) -> Resultado:
    """Lo que devuelve servicios/pruebas ({ok, mensaje}) como (ok, detalle)."""
    return r.get("ok"), str(r.get("mensaje") or "")


def _pruebas():
    from servicios import pruebas
    return pruebas


def _espacio(ctx: Contexto) -> Resultado:
    return _de_prueba(_pruebas().espacio_libre(ctx.datos, uso=ctx.disco))


DATOS: List[Comprobacion] = [
    Comprobacion("carpeta_datos", "datos", "Carpeta de tus datos", _datos_escribible),
    Comprobacion("carpeta_local", "datos", "Carpeta local (registros y cachés)", _local_escribible),
    Comprobacion("espacio_libre", "datos", "Espacio libre", _espacio),
]


# ── Librerías (lo que va dentro del paquete) ─────────────────────────────────────

def _version(mod: Any) -> str:
    v = getattr(mod, "__version__", None) or getattr(mod, "VERSION", None) or ""
    return str(v) if isinstance(v, (str, int, float)) else ""


def _modulo(nombre_modulo: str, extra: Optional[Callable[[Any, Contexto], str]] = None,
            solo_windows: bool = False) -> Callable[[Contexto], Resultado]:
    """Importa `nombre_modulo`; si hay `extra`, además comprueba algo con él (y su texto
    va al detalle; si lanza, el item falla)."""
    def comprobar(ctx: Contexto) -> Resultado:
        if solo_windows and not ctx.windows:
            return None, "solo en Windows"
        mod = ctx.importar(nombre_modulo)
        if getattr(mod, SIN_CARGAR, False):      # dentro de la app: está, pero no se carga para mirarlo
            return True, "está (lo cargo cuando haga falta)"
        detalle = _version(mod)
        if extra is not None:
            mas = extra(mod, ctx)
            detalle = f"{detalle} · {mas}" if detalle and mas else (mas or detalle)
        return True, detalle
    comprobar.modulo = nombre_modulo           # para modulos_empaquetados()
    return comprobar


def _ctranslate2(mod: Any, ctx: Contexto) -> str:
    # Esto ya usa la librería de C++ (y su runtime): con el MSVCP140 viejo aquí moriría.
    tipos = mod.get_supported_compute_types("cpu")
    return "CPU: " + ", ".join(sorted(str(t) for t in tipos))


def _onnxruntime(mod: Any, ctx: Contexto) -> str:
    return ", ".join(mod.get_available_providers())


def _faster_whisper(mod: Any, ctx: Contexto) -> str:
    # El VAD (silero_vad_v6.onnx) no lo recoge ningún hook de PyInstaller: sin él, el dictado falla.
    utils = ctx.importar("faster_whisper.utils")
    carpeta = Path(utils.get_assets_path())
    vad = sorted(carpeta.glob("silero_vad*.onnx"))
    if not vad:
        raise FileNotFoundError(f"falta el VAD (silero_vad*.onnx) en {carpeta}")
    return vad[-1].name


def _huggingface(mod: Any, ctx: Contexto) -> str:
    # Lo que usa faster_whisper para descargar el modelo la primera vez (import perezoso).
    if not callable(getattr(mod, "snapshot_download", None)):
        raise ImportError("sin snapshot_download")
    return "descarga del modelo lista"


def _sounddevice(mod: Any, ctx: Contexto) -> str:
    return str(mod.get_portaudio_version()[1])


def _pygame(mod: Any, ctx: Contexto) -> str:
    sdl = getattr(mod, "get_sdl_version", None)
    return ("SDL " + ".".join(map(str, sdl()))) if callable(sdl) else ""


def _imageio_ffmpeg(mod: Any, ctx: Contexto) -> str:
    exe = Path(mod.get_ffmpeg_exe())
    if not exe.is_file():
        raise FileNotFoundError(f"no está el binario de ffmpeg ({exe})")
    return exe.name


def _requests(mod: Any, ctx: Contexto) -> str:
    certifi = ctx.importar("certifi")
    cacert = Path(certifi.where())
    if not cacert.is_file():
        raise FileNotFoundError(f"no están los certificados de certifi ({cacert})")
    return "certificados de certifi"


def _pil(mod: Any, ctx: Contexto) -> str:
    if ctx.windows:
        ctx.importar("PIL.ImageGrab")             # la captura de la asistente
    return ""


def _precarga_msvc(ctx: Contexto) -> Resultado:
    """No es una librería: la precarga del runtime de C++ ANTES de todo lo pesado. Va la
    primera de la sección para que el orden quede escrito en la lista."""
    if not ctx.windows:
        return None, "solo en Windows"
    informe = ctx.precargar() if ctx.precargar else ""
    ctx.informe_precarga = informe or ""
    return True, ctx.informe_precarga or "hecho"


def _msvc_final(ctx: Contexto) -> Resultado:
    """Qué msvcp140.dll quedó cargada después de importarlo todo (el crash de Whisper)."""
    if not ctx.windows:
        return None, "solo en Windows"
    cargada = ctx.msvc_cargada() if ctx.msvc_cargada else None
    if not cargada:
        return None, "no hay ninguna cargada"
    ruta, version = cargada
    texto = f"{'.'.join(map(str, version))} ({ruta})"
    if tuple(version[:2]) < MSVC_MINIMA and any(version):
        return False, f"{texto}: es vieja, el dictado cerraría Lune"
    return True, texto


MODULOS: List[Comprobacion] = [
    Comprobacion("precarga_msvc", "modulos", "Precarga del runtime de C++", _precarga_msvc),
    # Lo de C++ primero (con el runtime nuevo ya en el proceso), luego Qt.
    Comprobacion("ctranslate2", "modulos", "Motor del dictado (ctranslate2)", _modulo("ctranslate2", _ctranslate2)),
    Comprobacion("onnxruntime", "modulos", "ONNX Runtime", _modulo("onnxruntime", _onnxruntime)),
    Comprobacion("av", "modulos", "Audio del dictado (PyAV)", _modulo("av")),
    Comprobacion("faster_whisper", "modulos", "Dictado (faster-whisper)", _modulo("faster_whisper", _faster_whisper)),
    Comprobacion("huggingface_hub", "modulos", "Descarga del modelo de dictado",
                 _modulo("huggingface_hub", _huggingface)),
    Comprobacion("qt_webengine", "modulos", "Interfaz completa (QtWebEngine)", _modulo("PyQt6.QtWebEngineWidgets")),
    Comprobacion("qt_multimedia", "modulos", "Vídeo de Qt (QtMultimedia)", _modulo("PyQt6.QtMultimedia")),
    Comprobacion("numpy", "modulos", "numpy (mezclador)", _modulo("numpy")),
    Comprobacion("sounddevice", "modulos", "Sonido y micrófono (PortAudio)", _modulo("sounddevice", _sounddevice)),
    Comprobacion("pygame", "modulos", "Mi voz (pygame)", _modulo("pygame", _pygame)),
    Comprobacion("edge_tts", "modulos", "Voz de edge-tts", _modulo("edge_tts")),
    Comprobacion("gtts", "modulos", "Voz de respaldo (gTTS)", _modulo("gtts")),
    Comprobacion("pypdf", "modulos", "Leer PDF (pypdf)", _modulo("pypdf")),
    Comprobacion("docx", "modulos", "Leer Word (python-docx)", _modulo("docx")),
    Comprobacion("pil", "modulos", "Imágenes y capturas (Pillow)", _modulo("PIL", _pil)),
    Comprobacion("psutil", "modulos", "Info del sistema (psutil)", _modulo("psutil")),
    Comprobacion("zeroconf", "modulos", "Red de Lune (zeroconf)", _modulo("zeroconf")),
    Comprobacion("websockets", "modulos", "Hub de la red (websockets)", _modulo("websockets")),
    Comprobacion("requests", "modulos", "Internet (requests + certifi)", _modulo("requests", _requests)),
    Comprobacion("ffmpeg", "modulos", "mp3 y ogg (ffmpeg)", _modulo("imageio_ffmpeg", _imageio_ffmpeg)),
    Comprobacion("win32gui", "modulos", "Ventanas de Windows (pywin32)", _modulo("win32gui", solo_windows=True)),
    Comprobacion("comtypes", "modulos", "Audio por app (comtypes)", _modulo("comtypes", solo_windows=True)),
    Comprobacion("msvc_cargada", "modulos", "Runtime de C++ en uso", _msvc_final),
]

# ── Ajustes (leídos sin escribir nada) ───────────────────────────────────────────

def _leer_json(ruta: Path) -> Dict[str, Any]:
    try:
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _ajustes_de_verdad(ctx: Contexto) -> Dict[str, Any]:
    """Lo que hace falta de datos.json y config.json de la carpeta de datos, sin escribir
    nada (ni la plantilla de datos.json ni la migración de config.json)."""
    d, c = _leer_json(Path(ctx.datos) / "datos.json"), _leer_json(Path(ctx.datos) / "config.json")
    apis = d.get("apis") if isinstance(d.get("apis"), dict) else {}
    modelos = d.get("modelos") if isinstance(d.get("modelos"), dict) else {}
    voz = c.get("voz") if isinstance(c.get("voz"), dict) else {}
    texto = lambda v, defecto="": str(v if v not in (None, "") else defecto).strip()   # noqa: E731
    return {
        "openrouter_key": texto(apis.get("openrouter_key")),
        "openrouter_model": texto(modelos.get("openrouter_model"), "openrouter/auto"),
        "ollama_url": texto(modelos.get("ollama_url"), "http://localhost:11434"),
        "ollama_model": texto(modelos.get("ollama_model")),
        "telegram_token": texto(apis.get("telegram_token")),
        "telegram_admin_id": texto(apis.get("telegram_admin_id")),
        "modelo_whisper": texto(voz.get("modelo_whisper"), "base"),
    }


def _ajustes(ctx: Contexto) -> Dict[str, Any]:
    if "ajustes" not in ctx.extra:
        try:
            ctx.extra["ajustes"] = dict((ctx.ajustes or (lambda: _ajustes_de_verdad(ctx)))() or {})
        except Exception:           # noqa: BLE001
            ctx.extra["ajustes"] = {}
    return ctx.extra["ajustes"]


# ── Tu equipo (sin red; lo que falta aquí no es un fallo de Lune) ──────────────────

def _audio(ctx: Contexto) -> Resultado:
    sd = ctx.sonido
    if sd is None:
        try:
            sd = ctx.importar("sounddevice")
        except Exception:           # noqa: BLE001 (ImportError u OSError de PortAudio)
            return False, "No puedo usar el sonido: falta PortAudio (sounddevice)."
    return _de_prueba(_pruebas().probar_audio(sd))


def _whisper(ctx: Contexto) -> Resultado:
    modelo = _ajustes(ctx).get("modelo_whisper") or "base"
    return _de_prueba(_pruebas().probar_whisper(modelo, descargado=ctx.whisper,
                                                faltan=[] if ctx.whisper is not None else None))


EQUIPO: List[Comprobacion] = [
    Comprobacion("audio", "equipo", "Micrófono y altavoces", _audio),
    Comprobacion("whisper_modelo", "equipo", "Modelo del dictado (Whisper)", _whisper),
]


# ── Red y servicios (solo con red=True) ───────────────────────────────────────────

def _internet(ctx: Contexto) -> Resultado:
    return _de_prueba(_pruebas().probar_internet(http=ctx.http))


def _openrouter(ctx: Contexto) -> Resultado:
    a = _ajustes(ctx)
    return _de_prueba(_pruebas().probar_openrouter(a.get("openrouter_key"), a.get("openrouter_model"),
                                                   http=ctx.http))


def _ollama(ctx: Contexto) -> Resultado:
    a = _ajustes(ctx)
    if not a.get("ollama_model"):
        return None, "No uso Ollama: no hay modelo local elegido (Ajustes, apartado Ollama)."
    return _de_prueba(_pruebas().probar_ollama(a.get("ollama_url"), a.get("ollama_model"),
                                               listar=ctx.listar_ollama))


def _telegram(ctx: Contexto) -> Resultado:
    a = _ajustes(ctx)
    p = _pruebas()
    t = p.probar_token_telegram(a.get("telegram_token"), http=ctx.http)
    if t["ok"] is not True:
        return _de_prueba(t)
    # El token vale: lo demás del bot (tu ID y su carpeta; Node va aparte).
    i = p.probar_id_telegram(a.get("telegram_admin_id"))
    try:
        carpeta = bool((ctx.carpeta_bot or p._carpeta_bot_real)())
    except Exception:               # noqa: BLE001
        carpeta = False
    if not carpeta:
        return False, f"{t['mensaje']} Pero no encuentro la carpeta del bot ({p.CARPETA_BOT_TG}): reinstala Lune."
    if i["ok"] is False:
        return False, f"{t['mensaje']} {i['mensaje']}"
    return True, t["mensaje"] + ("" if i["ok"] else f" {i['mensaje']}")


def _node(ctx: Contexto) -> Resultado:
    necesario = bool(_ajustes(ctx).get("telegram_token"))
    return _de_prueba(_pruebas().probar_node(ctx.node, necesario=necesario))


# Las de red: solo con comprobar(red=True). Se añaden aquí.
COMPROBACIONES_RED: List[Comprobacion] = [
    Comprobacion("internet", "red", "Internet", _internet),
    Comprobacion("openrouter", "red", "Clave de OpenRouter (nube)", _openrouter),
    Comprobacion("ollama", "red", "Ollama (modelo local)", _ollama),
    Comprobacion("telegram", "red", "Bot de Telegram", _telegram),
    Comprobacion("node", "red", "Node.js (bots)", _node),
]


def comprobaciones(red: bool = False) -> List[Comprobacion]:
    """La lista completa, en el orden en que se corren."""
    return [*RECURSOS, *DATOS, *MODULOS, *EQUIPO, *(COMPROBACIONES_RED if red else [])]


def modulos_empaquetados() -> List[str]:
    """Lo que comprobar() importa por nombre (para los hiddenimports de packaging/lune.spec:
    PyInstaller no ve los import_module con cadena)."""
    fijos = ["faster_whisper.utils", "certifi", "PIL.ImageGrab", "nucleo.runtime_win", "nucleo.rutas", "version",
             "servicios.pruebas"]
    vistos = [getattr(c.funcion, "modulo", None) for c in MODULOS]
    return list(dict.fromkeys([m for m in vistos if m] + fijos))


# ── Por defecto: lo de verdad ────────────────────────────────────────────────────

def _precargar_de_verdad() -> str:
    from nucleo import runtime_win
    runtime_win.precargar_msvc()
    return runtime_win.ultimo_informe


def _msvc_de_verdad() -> Optional[Tuple[str, Tuple[int, ...]]]:
    """(ruta, versión) de la msvcp140.dll cargada en este proceso, sin cargarla."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k32.GetModuleHandleW.restype = wintypes.HMODULE
    k32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    k32.GetModuleFileNameW.restype = wintypes.DWORD
    h = k32.GetModuleHandleW("msvcp140.dll")
    if not h:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    if not k32.GetModuleFileNameW(h, buf, 1024):
        return None
    from nucleo.runtime_win import version_dll
    return buf.value, version_dll(buf.value)


def contexto_real() -> Contexto:
    from nucleo import rutas
    return Contexto(recursos=rutas.RECURSOS, datos=rutas.DATOS, local=rutas.LOCAL,
                    precargar=_precargar_de_verdad, msvc_cargada=_msvc_de_verdad)


def importar_sin_cargar(nombre: str, *, cargados: Optional[Dict[str, Any]] = None,
                        buscar: Optional[Callable[[str], Any]] = None) -> Any:
    """Como importlib.import_module, salvo lo de SOLO_MIRAR_EN_APP que aún no esté cargado:
    de eso solo se mira que esté (find_spec) y se devuelve una marca (SIN_CARGAR)."""
    cargados = sys.modules if cargados is None else cargados
    if nombre in cargados:
        return cargados[nombre]
    if nombre in SOLO_MIRAR_EN_APP:
        try:
            spec = (buscar or importlib.util.find_spec)(nombre)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            raise ImportError(f"No module named '{nombre}'")
        return SimpleNamespace(**{SIN_CARGAR: True})
    return importlib.import_module(nombre)


def contexto_en_app() -> Contexto:
    """El contexto de verdad para comprobar DENTRO de la app (la tarjeta de la web y el diálogo
    de la nativa): sin cargar lo de SOLO_MIRAR_EN_APP y sin precargar el runtime (lo hizo la
    app al arrancar; el item «Runtime de C++ en uso» dice cuál quedó)."""
    ctx = contexto_real()
    ctx.importar = importar_sin_cargar
    ctx.precargar = lambda: "la hizo la app al arrancar"
    return ctx


def _modo() -> str:
    from nucleo import rutas
    return "instalada" if rutas.INSTALADA else "codigo"


def _version_app() -> str:
    try:
        from version import APP_VERSION
        return str(APP_VERSION)
    except Exception:
        return "?"


def comprobar(red: bool = False, *, ctx: Optional[Contexto] = None,
              al_avanzar: Optional[Callable[[Dict[str, Any]], Any]] = None,
              parar: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """Corre las comprobaciones y devuelve el informe. `al_avanzar(item)` se llama con cada
    item según sale (patata los va imprimiendo: si algo tumba el proceso, se ve hasta dónde
    llegó; la interfaz los va pintando). Con `parar`, antes de cada comprobación se le
    pregunta y, si dice True, el informe acaba ahí (con "parado": True). Nunca lanza por
    una comprobación que falla."""
    if "PYGAME_HIDE_SUPPORT_PROMPT" not in os.environ:
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"       # sin el «Hello from pygame»
    ctx = ctx or contexto_real()
    items: List[Dict[str, Any]] = []
    parado = False
    for c in comprobaciones(red):
        if parar is not None and parar():
            parado = True
            break
        try:
            ok, detalle = c.funcion(ctx)
        except Exception as e:      # ImportError, OSError de una DLL, lo que sea: se apunta
            ok, detalle = False, _fallo(e)
        item = {"id": c.id, "seccion": c.seccion, "nombre": c.nombre,
                "ok": None if ok is None else bool(ok), "detalle": _corto(detalle or "")}
        items.append(item)
        if al_avanzar is not None:
            al_avanzar(item)
    resultado = {"ok": all(i["ok"] is not False for i in items), "version": _version_app(),
                 "modo": _modo(), "items": items}
    if parado:
        resultado["parado"] = True
    return resultado


# ── Informe legible (patata --comprobar) ─────────────────────────────────────────

MARCAS = {True: "[ok]   ", False: "[FALLA]", None: "[--]   "}


def cabecera(version: str, modo: str) -> str:
    como = "instalada" if modo == "instalada" else "desde el código"
    return f"Lune CD {version} - comprobando que no me falte nada ({como})"


def linea(item: Dict[str, Any]) -> str:
    detalle = f"  {item['detalle']}" if item.get("detalle") else ""
    return f"  {MARCAS.get(item.get('ok'), MARCAS[None])} {item['nombre']}{detalle}"


def resumen(resultado: Dict[str, Any]) -> str:
    items = resultado.get("items", [])
    fallan = [i for i in items if i.get("ok") is False]
    cuentan = [i for i in items if i.get("ok") is not None]
    if resultado.get("parado"):
        return f"Lo dejé a medias: comprobé {len(items)} cosas y {len(fallan)} fallaban."
    if not fallan:
        return f"Todo en orden ({len(cuentan)} de {len(cuentan)}): estoy lista."
    nombres = ", ".join(i["nombre"] for i in fallan)
    return f"Me falla{'n' if len(fallan) > 1 else ''} {len(fallan)} de {len(cuentan)}: {nombres}."


# ── Para la interfaz (la señal `diagnostico` del puente y ui/pruebas_qt.py) ────────

def evento_inicio(red: bool = True) -> Dict[str, Any]:
    """Lo primero que se manda: versión, modo y los nombres de las secciones, en orden."""
    secciones = list(dict.fromkeys(c.seccion for c in comprobaciones(red)))
    return {"tipo": "inicio", "version": _version_app(), "modo": _modo(),
            "secciones": [{"id": s, "nombre": SECCIONES.get(s, s)} for s in secciones],
            "total": len(comprobaciones(red))}


def evento_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Un item tal cual sale de comprobar(), con el nombre de su sección."""
    return {"tipo": "item", **item, "seccion_nombre": SECCIONES.get(item.get("seccion"), item.get("seccion"))}


def evento_fin(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """El resumen del final: {tipo: fin, ok, resumen, fallan, cuentan, no_aplica, …}."""
    items = resultado.get("items", [])
    return {"tipo": "fin", "ok": bool(resultado.get("ok")), "version": resultado.get("version", "?"),
            "modo": resultado.get("modo", ""), "resumen": resumen(resultado),
            "fallan": sum(1 for i in items if i.get("ok") is False),
            "cuentan": sum(1 for i in items if i.get("ok") is not None),
            "no_aplica": sum(1 for i in items if i.get("ok") is None),
            "parado": bool(resultado.get("parado"))}


def informe(resultado: Dict[str, Any]) -> str:
    """El informe entero en texto (lo mismo que imprime main() poco a poco)."""
    partes = [cabecera(resultado.get("version", "?"), resultado.get("modo", "")), ""]
    seccion = None
    for item in resultado.get("items", []):
        if item.get("seccion") != seccion:
            seccion = item.get("seccion")
            partes.append(SECCIONES.get(seccion, str(seccion)))
        partes.append(linea(item))
    partes += ["", resumen(resultado)]
    return "\n".join(partes)


def main(como_json: bool = False, red: bool = False, *, escribir: Callable[[str], Any] = None,
         ctx: Optional[Contexto] = None) -> int:
    """Imprime la comprobación y devuelve el código de salida (0 bien, 1 algo falla)."""
    escribir = escribir or (lambda texto: print(texto, flush=True))
    if como_json:
        resultado = comprobar(red, ctx=ctx)
        escribir(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0 if resultado["ok"] else 1

    escribir(cabecera(_version_app(), _modo()))
    estado = {"seccion": None}

    def avanzar(item: Dict[str, Any]) -> None:
        if item["seccion"] != estado["seccion"]:
            estado["seccion"] = item["seccion"]
            escribir("\n" + SECCIONES.get(item["seccion"], item["seccion"]))
        escribir(linea(item))

    resultado = comprobar(red, ctx=ctx, al_avanzar=avanzar)
    escribir("\n" + resumen(resultado))
    return 0 if resultado["ok"] else 1


__all__ = ("Comprobacion", "Contexto", "COMPROBACIONES_RED", "EQUIPO", "SECCIONES", "comprobar",
           "comprobaciones", "modulos_empaquetados", "informe", "main", "evento_inicio", "evento_item",
           "evento_fin", "contexto_real", "contexto_en_app", "importar_sin_cargar")
