"""
patata.py — Modo PATATA: Lune en la terminal, sin nada más.

Sin Qt, sin animaciones, sin imágenes, sin mascota: solo texto. Sirve para:
  · usar a Lune desde una consola porque te gusta así, o
  · rescatarla cuando la interfaz no abre (PyQt6 roto, equipo muy justo…).

Conserva lo que importa: el MISMO cerebro (Ollama, OpenRouter o una API
compatible con OpenAI), la MISMA memoria (memoria.json), la MISMA personalidad
(personajes de datos.json) y la MISMA voz del personaje. Las emociones que el
modelo marca con <|ACT|> se muestran como caritas de teclado.

    python patata.py            (o doble clic en lune_patata.bat)

La consola es UNA (nucleo/consola.ConsolaAsincrona): un solo lector de la
entrada. Cuando Lune pide permiso para algo («¿Lo hago? [s/N]»), tu siguiente
línea es la respuesta; sin respuesta en 60 s, no lo hace. Los avisos (resultado
de una acción, un fallo de la voz) no rompen lo que estás escribiendo.

Acciones: el modelo las pide con <|CALL …|> (lune_core/acciones.py). Las de
lectura van solas; abrir una app pregunta. El formato antiguo (ABRIR_URL:,
TOOL:) ya no hace nada.

Alarmas, salvapantallas y baile (cortes 5 y 6), sin Qt: las alarmas y los
temporizadores suenan también aquí (banner, sonido y título; Enter apaga, «p»
pospone; con la app de ventanas abierta a la vez suena UNA vez), el salvapantallas
es el título «(-_-) zzZ 23:41» y, con música, el título baila. «Avísame en 10
minutos» o «baila» escritos en el chat van directos, como «abre youtube». El
título va por capas: alarma 60, modo juego 50, baile 20, salvapantallas 10.

Comida, Discord y arranque con Windows (cortes 7 y 8), sin Qt: /comer (texto y el
sonido del trago o del mordisco; «toma un batido» escrito en el chat va directo),
la presencia de Discord propia («Lune CD · Terminal»: en la terminal, pensando, o
nada con un juego delante; si la app de ventanas ya publica, publica ella) y
/autoinicio. `patata.py --autoinicio` (entrada de Windows en su variante /patata:
consola minimizada) repara la entrada y, si la interfaz ya no es patata, abre la
app de ventanas y se va.

Una sola patata a la vez (servicios/instancia_patata): si ya hay una (p. ej. la que
arrancó con Windows y vuelves a abrir Lune), la nueva le pide que traiga su consola
al frente —si Windows no deja, parpadea y dice «¡Sigo aquí!»— y se va. main.py en
modo patata hace lo mismo en vez de abrir otra terminal.

Bailes y Minecraft (cortes 9 y 10), sin Qt: /bailes pone la canción de un baile de tu
biblioteca (bailes/) por el Mezclador y el título baila a su ritmo (aquí no hay
esqueleto: baila a su manera); /mc reacciona a tu partida con «Lune: …» (latest.log,
sin tocar el juego) y maneja el bot de Minecraft (se instala solo con /mc instalar).
«Ponme el baile de X» y «conecta el bot de Minecraft» escritos en el chat van directos.
Mientras Lune piensa, el bot pausa su modelo (comparten Ollama).

Sueño: aquí no hay mascota que dormir, pero la regla es la misma
(nucleo/sueno.ReglaSueno, avatar.dormir_min). Si vuelves tras una pausa larga,
antes de la respuesta sale «Lune se quedó dormida hace N min… (-_-) zzZ» y, a
veces, una frase al despertar (lune_core/frases_mascota).

Comandos:
  /ayuda                        esta ayuda
  /memoria · /olvida <texto>    lo que Lune recuerda de ti
  /personaje [nombre]           ver o cambiar de personaje
  /proveedor [ollama|openrouter|compat]   con qué cerebro respondo (/local, /nube)
  /modelo [nombre]              ver o cambiar el modelo del proveedor actual
  /estado                       proveedor, parámetros, voz y acciones
  /temp [0-2|preciso|equilibrado|creativo]   temperatura o preset
  /ctx [n|8k|16k…]              ventana de contexto de Ollama (tokens)
  /liberar                      saca el modelo local de la memoria (VRAM)
  /compat [url <u>|modelo <m>|off]   API compatible con OpenAI: estado y prueba
  /voces [filtro]               voces de edge-tts (mexico, mujer, multi…)
  /voz [on|off|<id>|prueba [texto]|motor <m>|velocidad <n>|tono <n>]
  /herramientas                 lo que Lune puede hacer en tu PC desde aquí
  /nuevo                        conversación nueva (presupuesto de acciones repuesto)
  /limpiar                      conversación nueva y pantalla limpia
  /menu [n [opción]]            acciones rápidas numeradas: voz, modo juego, tema, arrancar con
                                Windows, liberar memoria y salir (/menu 2 elige la segunda)
  /tema [nombre]                colores de esta terminal: cian, magenta_mate, violeta, rojo_neon,
                                ambar o verde_acido
  /caritas [clasico|kaomoji]    caritas de teclado :D o kaomoji (^▽^)
  /juego [on|off|auto]          modo juego: con un juego delante Lune baja su prioridad (se ve
                                en el título de la consola); on/off lo fuerzan, auto lo detecta
  /ram                          libera la memoria que Lune no está usando ahora
  /alarma HH:MM [lmxjvsd|todos] [texto]   alarma (sin días: una sola vez) · /alarma probar
  /alarmas [on|off]             lista de alarmas y temporizadores (con su id) o encenderlas/apagarlas
  /borrar_alarma <id|n>         quita una alarma o un temporizador (id o número de /alarmas)
  /timer 10m [texto] · /timers  temporizador (10m, 1h30, 90s, 1:30…) y los que hay
  /apagar · /posponer           la alarma que suena (también Enter o «p» mientras suena)
  /bailar [segundos] · /bailar auto on|off · /bailar apps · /bailar permitir <app> ·
  /bailar quitar <app> · /parar   Lune baila en el título (con música, sola)
  /bailes [texto] · /bailes <n> · /bailes parar|pausa|siguiente|anterior · /bailes bucle on|off
                                tus bailes (carpeta bailes/): suena la canción y el título baila a su
                                ritmo (Enter o /parar para); «ponme el baile de X» en el chat, igual
  /mc · /mc log on|off · /mc bot on [host[:puerto]]|off · /mc instalar · /mc di <texto> · /mc <orden> (sígueme, ven, para, mina 10 hierro…)
                                Minecraft: reacciones a tu partida (latest.log) y el bot (solo servidores
                                con online-mode=false; /mc instalar lo descarga, ~400 MB y Node 18+)
  /comer [batido|pastel] [sabor] · /comer on|off   darle de comer (texto y sonido) o apagar la comida
  /discord [on|off|estado] · /discord id <número>  presencia en Discord (solo «Lune CD · Terminal» y
                                un estado fijo; el Application ID de discord.com/developers)
  /autoinicio [on|off|estado|como bandeja|mascota|ventana|espera N]   arrancar con Windows (aquí:
                                esta terminal, minimizada) y cómo abre la app de ventanas
  /interfaz [web|nativo]        vuelve a las ventanas (completa o bajos recursos) y cierra la terminal
  /salir
  (La terminal no tiene bandeja, menú radial ni atajos globales: eso es de las ventanas.
  Tampoco pantalla grande: el salvapantallas es el título, con salvapantallas.activo.
  Sentarse en la barra o en una ventana es cosa de la mascota de las ventanas.)
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Optional

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import datos, personajes                      # noqa: E402
from nucleo.consola import ConsolaAsincrona               # noqa: E402
from nucleo.memoria import MemoriaManager                 # noqa: E402
from nucleo.sueno import ReglaSueno                       # noqa: E402
from lune_core import expresiones, marcadores             # noqa: E402
from lune_core.frases_mascota import frases_para          # noqa: E402
from lune_core.acciones import (CADUCADA, RECHAZADA,      # noqa: E402
                                limpiar_texto)
from lune_core.catalogo_herramientas import ORIGEN_USUARIO  # noqa: E402
from lune_core.prompt import GRAMATICA_EMOCIONES          # noqa: E402
from lune_core.reglas_prompt import reglas_herramientas   # noqa: E402
from servicios.ai_manager import AIManager                # noqa: E402

MODO = "patata"              # modo del catálogo de herramientas
_AUTO = object()

# Emoción canónica → carita de teclado (esto ES la mascota en modo patata).
CARITAS = {
    "happy": ":D", "sad": ":(", "angry": ">:(", "think": ":/", "surprised": ":O",
    "awkward": "^^'", "question": ":?", "curious": "o_O", "neutral": ":|",
    "nervous": "^^;", "wave": "o/", "dismiss": "-_-",
    "laughing": "xD", "bored": "-.-",
}

# Las mismas emociones en kaomoji (config patata.caritas = "kaomoji", /caritas).
KAOMOJI = {
    "happy": "(^▽^)", "sad": "(╥_╥)", "angry": "(╬`益´)", "think": "(・_・ヾ", "surprised": "(°o°)",
    "awkward": "(^_^;)", "question": "(・・?)", "curious": "(o_O)", "neutral": "(・_・)",
    "nervous": "(;^_^)", "wave": "(^_^)/", "dismiss": "(￣ー￣)",
    "laughing": "(≧▽≦)", "bored": "(=_=)",
}
_EMOCION_DE_CARITA = {v: k for k, v in CARITAS.items()}
ESTILOS_CARITAS = ("clasico", "kaomoji")

SI = frozenset({"s", "si", "sí", "y", "yes"})
# Prioridad del reclamo «¿Lo hago? [s/N]» en la consola: la alarma que suena
# (servicios/alarmas_patata) va por encima y el baile (-10) por debajo.
PRIORIDAD_APROBACION = 0
ALIAS_PROVEEDOR = {"local": "ollama", "nube": "openrouter", "api": "compat"}
CLAVE_MODELO = {"ollama": "ollama_model", "openrouter": "openrouter_model",
                "compat": "compat_model"}
_RE_MODELO = re.compile(r"^[\w.:/@+\-]{1,160}$")
CTX_MIN, CTX_MAX = 512, 131072

# /interfaz: volver a las ventanas (config interfaz.modo, lo lee main.py al arrancar).
MODOS_INTERFAZ = {"web": "web", "completa": "web", "completo": "web",
                  "nativo": "nativo", "nativa": "nativo", "bajos": "nativo", "ligera": "nativo",
                  "ligero": "nativo"}
NOMBRE_INTERFAZ = {"web": "completa", "nativo": "de bajos recursos"}
ESPERA_ARRANQUE_S = 1.5      # si la app muere antes (falta PyQt6…), patata no se cierra
# Windows: la app va sin consola y desacoplada de esta terminal (cerrarla no la mata).
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


# Colores ANSI (Windows 10+ los soporta al activar VT). Con --sin-color van vacíos.
def _colores(activar: bool):
    if not activar:
        return {k: "" for k in ("cyan", "yellow", "dim", "bold", "red", "reset")}
    if os.name == "nt":
        os.system("")          # activa el procesamiento de secuencias VT en la consola
    return {"cyan": "\033[96m", "yellow": "\033[93m", "dim": "\033[90m",
            "bold": "\033[1m", "red": "\033[91m", "reset": "\033[0m"}


def una_linea(texto: Any, maximo: int = 160) -> str:
    """Texto del modelo → una línea imprimible (sin controles, bidi ni saltos), recortada."""
    s = "" if texto is None else str(texto)
    s = s.replace("\r\n", "\n").replace("\n", " ⏎ ")
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp"))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= maximo else s[:maximo - 1].rstrip() + "…"


def leer_ctx(texto: str) -> Optional[int]:
    """'8192', '8k', '16K' → tokens; None si no es un número razonable."""
    t = str(texto or "").strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(k?)", t)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    n = int(n * 1024) if m.group(2) else int(n)
    return n if CTX_MIN <= n <= CTX_MAX else None


def url_compat_valida(url: str) -> Optional[str]:
    """http(s)://host[:puerto][/ruta], sin usuario:clave ni espacios. None si no vale."""
    from urllib.parse import urlparse
    u = str(url or "").strip().rstrip("/")
    if not u or any(ch.isspace() for ch in u) or len(u) > 300:
        return None
    try:
        p = urlparse(u)
        _ = p.port                       # lanza con un puerto imposible
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname or "@" in p.netloc:
        return None
    return u


def _plano(texto: Any) -> str:
    """«Magenta Mate», «rojo-neón» → «magenta_mate», «rojo_neon» (para /tema y /caritas)."""
    s = unicodedata.normalize("NFD", str(texto or "").strip().lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[\s\-]+", "_", s)


def preset_tema(texto: Any) -> Optional[str]:
    """Nombre de preset de nucleo/tema.PRESETS (id, etiqueta o inicio único) o None."""
    from nucleo import tema
    t = _plano(texto)
    if not t:
        return None
    if t in tema.PRESETS:
        return t
    for pid, etiqueta in tema.ETIQUETAS.items():
        if pid in tema.PRESETS and _plano(etiqueta) == t:
            return pid
    candidatos = [p for p in tema.PRESETS if p.startswith(t)]
    return candidatos[0] if len(candidatos) == 1 else None


def ayuda() -> str:
    """El texto de /ayuda: la sección «Comandos:» de este módulo; si a las ayudas de /bailes
    y /mc (servicios/bailes_terminal.AYUDA y minecraft_terminal.AYUDA) les falta algo aquí,
    se añaden al final (sin Qt)."""
    texto = __doc__.split("Comandos:")[1].strip("\n") if "Comandos:" in (__doc__ or "") else ""
    for modulo in ("servicios.bailes_terminal", "servicios.minecraft_terminal"):
        try:
            import importlib
            extra = str(getattr(importlib.import_module(modulo), "AYUDA", "") or "")
        except Exception:
            extra = ""
        if extra and extra not in texto:
            texto += "\n  " + extra
    return texto


def _en_hilo(fn: Callable[[], None]) -> None:
    """Lo que sigue a una aprobación sale del hilo lector de la consola (tiene que ser rápido)."""
    threading.Thread(target=fn, name="lune-accion", daemon=True).start()


def _config_por_defecto():
    try:
        from nucleo.config import Config
        return Config()
    except Exception:
        return None


def python_sin_consola(exe: Optional[str] = None) -> str:
    """El pythonw.exe hermano del intérprete actual (la app de ventanas no necesita
    consola); si no existe, el mismo intérprete."""
    exe = exe or sys.executable
    ruta = Path(exe)
    if os.name == "nt" and ruta.name.lower() == "python.exe":
        pyw = ruta.with_name("pythonw.exe")
        if pyw.exists():
            return str(pyw)
    return str(exe)


def lanzar_app_qt(modo: str = "", *, raiz: Path = RAIZ, popen: Optional[Callable[..., Any]] = None,
                  espera_s: float = ESPERA_ARRANQUE_S, extra: tuple = ()) -> bool:
    """Abre la app de ventanas (main.py) sin consola y desacoplada de esta terminal:
    si cierras la consola, la app sigue. Lee el modo de config (interfaz.modo).

    Sin importar Qt aquí: se comprueba que PyQt6 esté instalado buscándolo, no
    importándolo. Si la app se cierra con error en los primeros segundos (le falta
    algo), lanza RuntimeError con el motivo para que patata no se vaya. True si
    quedó abierta (o terminó bien: otra Lune ya estaba abierta y se trajo al frente).
    `extra`: argumentos para main.py (p. ej. ("--autoinicio",))."""
    import importlib.util
    import subprocess
    script = Path(raiz) / "main.py"
    if not script.exists():
        raise RuntimeError(f"no encuentro {script.name}")
    if importlib.util.find_spec("PyQt6") is None:
        raise RuntimeError("este Python no tiene PyQt6 (ejecuta instalar_lune.bat o "
                           "pip install -r requirements.txt)")
    exe = python_sin_consola()
    kw: Dict[str, Any] = {"cwd": str(raiz), "stdin": subprocess.DEVNULL,
                          "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                          "close_fds": True}
    if os.name == "nt":
        sin_consola = Path(exe).name.lower() == "pythonw.exe"
        kw["creationflags"] = _CREATE_NEW_PROCESS_GROUP | (
            _DETACHED_PROCESS if sin_consola else _CREATE_NO_WINDOW)
    else:
        kw["start_new_session"] = True
    proc = (popen or subprocess.Popen)([exe, str(script), *[str(a) for a in (extra or ())]], **kw)
    if espera_s and espera_s > 0:
        try:
            codigo = proc.wait(timeout=espera_s)
        except subprocess.TimeoutExpired:
            return True                               # sigue viva: arrancó
        except Exception:
            return True
        if codigo not in (0, None):
            raise RuntimeError(f"la interfaz se cerró al arrancar (código {codigo}); "
                               "mira logs/ o ejecuta instalar_lune.bat")
    return True


class Patata:
    def __init__(self, color: bool = True, *, consola: Any = None, config: Any = _AUTO,
                 ai: Any = None, memoria: Any = None, voice: Any = _AUTO, tools: Any = _AUTO,
                 audit_path: Any = _AUTO, reloj_sueno: Optional[Callable[[], float]] = None,
                 lanzador: Optional[Callable[[str], Any]] = None,
                 juego: Any = None, prioridad: Optional[Callable[[bool], Any]] = None,
                 recortar: Optional[Callable[[], Any]] = None, autoinicio: Any = None,
                 alarmas: Any = _AUTO, baile: Any = _AUTO, salvapantallas: Any = _AUTO,
                 comida: Any = _AUTO, sistema: Any = _AUTO, con_windows: bool = False,
                 bailes: Any = _AUTO, minecraft: Any = _AUTO,
                 **opciones_ejecutor):
        self.c = _colores(color)
        self._c_base = dict(self.c)                          # /tema parte de aquí cada vez
        self.config = _config_por_defecto() if config is _AUTO else config
        # Corte 4 en la terminal (sin Qt): modo juego con su hilo (DetectorJuego y la
        # prioridad del proceso), /ram, /tema, /caritas y /menu. Inyectables en tests.
        self._det_juego = juego                              # DetectorJuego (perezoso)
        self._prioridad_fn = prioridad                       # modo_juego.aplicar_prioridad
        self._recortar_fn = recortar                         # recorte_ram.recortar
        self._autoinicio = autoinicio                        # servicios.autoinicio
        self._juego_activo = False
        self._pensando = False                               # esperando al modelo (Discord: «Pensando…»)
        self.con_windows = bool(con_windows)                 # arrancó con Windows (--autoinicio)
        self._juego_motivo = ""
        self._prioridad_baja = False
        self._lock_juego = threading.Lock()
        self._parar_juego = threading.Event()
        self._hilo_juego: Optional[threading.Thread] = None
        self._desp = None                                    # Despachador de /menu
        self._salir_pedido = False
        self._ultima_cara = CARITAS["neutral"]
        self._aplicar_tema_consola()
        # /interfaz: abre la app de ventanas (lanzador(modo) -> bool; inyectable en tests).
        self._lanzador = lanzador or lanzar_app_qt
        # Sueño: hora (monótona) de la última actividad (tu última línea —mensaje, comando
        # o «s/n»— o el fin de la última respuesta); la regla se lee de config en cada turno.
        self._reloj_sueno = reloj_sueno or time.monotonic
        self._ultima_actividad = self._reloj_sueno()
        self._frases = None                                  # FrasesMascota (perezosa)
        self.consola = consola if consola is not None else ConsolaAsincrona(self._texto_prompt())
        self.ai = ai if ai is not None else AIManager()
        self.memoria = memoria if memoria is not None else MemoriaManager()
        self.provider = self._proveedor_inicial()
        self.voice = self._crear_voz() if voice is _AUTO else voice
        self.tools = self._crear_tools() if tools is _AUTO else tools
        # Cortes 5/6 (sin Qt): alarmas (servicios/alarmas_patata), baile en el título
        # (servicios/baile_terminal) y salvapantallas en el título
        # (servicios/salvapantallas_terminal). Arrancan en correr(); None = sin ellos.
        self.alarmas = self._crear_alarmas() if alarmas is _AUTO else alarmas
        self.baile = self._crear_baile() if baile is _AUTO else baile
        self.salvapantallas = (self._crear_salvapantallas() if salvapantallas is _AUTO
                               else salvapantallas)
        if self.alarmas is not None and self.tools is not None:
            try:
                self.alarmas.registrar_herramientas(self.tools)   # temporizador, alarma…
            except Exception:
                pass
        # Cortes 7/8 (sin Qt): la comida (servicios/comida_terminal: /comer y la
        # herramienta dar_de_comer) y Discord + arranque con Windows
        # (servicios/sistema_terminal: /discord, /autoinicio). None = sin ellos.
        self.comida = self._crear_comida() if comida is _AUTO else comida
        self.sistema = self._crear_sistema() if sistema is _AUTO else sistema
        if self.comida is not None and self.tools is not None:
            try:
                self.comida.registrar_herramientas(self.tools)    # dar_de_comer
            except Exception:
                pass
        # Cortes 9/10 (sin Qt): los bailes de tu biblioteca (servicios/bailes_terminal: /bailes;
        # la canción por el Mezclador y el título baila a su ritmo, con el MISMO BaileTerminal)
        # y Minecraft (servicios/minecraft_terminal: /mc, reacciones a tu partida y el bot).
        # None = sin ellos.
        self.bailes = self._crear_bailes() if bailes is _AUTO else bailes
        self.minecraft = self._crear_minecraft() if minecraft is _AUTO else minecraft
        for pieza in (self.bailes, self.minecraft):     # listar_bailes, mascota_bailar, minecraft_*…
            if pieza is not None and self.tools is not None:
                try:
                    pieza.registrar_herramientas(self.tools)
                except Exception:
                    pass
        self._reclamos: Dict[str, Callable[[], None]] = {}   # aprobación → cancelar()
        self._lock = threading.Lock()
        self.ejecutor = None
        if self.tools is not None and hasattr(self.tools, "crear_ejecutor"):
            kw = dict(opciones_ejecutor)
            if audit_path is not _AUTO:
                kw["audit_path"] = audit_path
            try:
                self.ejecutor = self.tools.crear_ejecutor(
                    self._pedir_aprobacion, despachar=_en_hilo,
                    cerrar_aprobacion=self._cerrar_aprobacion, **kw)
            except Exception:
                self.ejecutor = None

    # ── Piezas ───────────────────────────────────────────────────────────────────
    def _cfg(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        try:
            return self.config.get(seccion, clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def _feature(self, clave: str, defecto: bool) -> bool:
        try:
            return bool(self.config.feature(clave, defecto)) if self.config is not None else defecto
        except Exception:
            return defecto

    def _texto_prompt(self) -> str:
        c = self.c
        texto = str(self._cfg("patata", "prompt", "tú > ") or "tú > ").rstrip()
        return f"{c['bold']}{texto}{c['reset']} "

    def _proveedor_inicial(self) -> str:
        provs = getattr(self.ai, "providers", {}) or {}
        if datos.ollama_model() and "ollama" in provs:
            return "ollama"
        if datos.openrouter_key() or "compat" not in provs:
            return "openrouter"
        return "compat"

    def _crear_voz(self):
        """VoiceEngine con la voz del personaje activo; mudo si no hay motor ni tarjeta."""
        try:
            from servicios.voice import VoiceEngine
            v = VoiceEngine(self.config, on_error=self._aviso_voz)
        except Exception:
            return None
        if self._feature("voz_auto", False) and v.available:
            v._enabled = True
        return v

    def _crear_tools(self):
        """ToolManager con las cuatro de siempre y `cambiar_voz` (config + voz de esta sesión)."""
        try:
            from servicios.tools import ToolManager
            tm = ToolManager()
        except Exception:
            return None
        try:
            tm.conectar_voz(self.config, self.voice)
        except Exception:
            pass
        return tm

    def _en_juego(self) -> bool:
        return bool(getattr(self, "_juego_activo", False))

    def _crear_alarmas(self):
        """AlarmasTerminal (alarmas.json, el mismo que la app; suena una vez aunque las
        dos estén abiertas). None si no se puede."""
        try:
            from servicios.alarmas_patata import AlarmasTerminal
            return AlarmasTerminal(self.consola, self.config, voice=self.voice, colores=self.c)
        except Exception:
            return None

    def _crear_baile(self):
        try:
            from servicios.baile_terminal import BaileTerminal
            return BaileTerminal(self.consola, self.config, colores=self.c, en_juego=self._en_juego)
        except Exception:
            return None

    def _crear_salvapantallas(self):
        try:
            from servicios.salvapantallas_terminal import SalvapantallasTerminal
            return SalvapantallasTerminal(self.consola, self.config, en_juego=self._en_juego,
                                          restaurar_titulo=self._poner_titulo)
        except Exception:
            return None

    def _crear_comida(self):
        try:
            from servicios.comida_terminal import ComidaTerminal
            return ComidaTerminal(self.consola, self.config, colores=self.c, en_juego=self._en_juego,
                                  nombre=lambda: (personajes.get_activo() or {}).get("nombre", "Lune"))
        except Exception:
            return None

    def _crear_sistema(self):
        try:
            from servicios.sistema_terminal import SistemaTerminal
            return SistemaTerminal(self.consola, self.config, en_juego=self._en_juego,
                                   pensando=lambda: bool(getattr(self, "_pensando", False)),
                                   autoinicio=self._autoinicio or None)
        except Exception:
            return None

    def _crear_bailes(self):
        try:
            from servicios.bailes_terminal import BailesTerminal
            return BailesTerminal(self.consola, self.config, colores=self.c, en_juego=self._en_juego,
                                  baile=getattr(self, "baile", None))
        except Exception:
            return None

    def _crear_minecraft(self):
        try:
            from servicios.minecraft_terminal import MinecraftTerminal
            return MinecraftTerminal(self.consola, self.config, voice=self.voice, colores=self.c,
                                     en_juego=self._en_juego,
                                     pensando=lambda: bool(getattr(self, "_pensando", False)))
        except Exception:
            return None

    def _discord_al_dia(self) -> None:
        """Algo que Discord publica cambió (pensando, juego): que lo vea ya."""
        s = getattr(self, "sistema", None)
        if s is not None:
            try:
                s.actualizar()
            except Exception:
                pass

    def _ctx(self) -> dict:
        try:
            from servicios.tools import ctx_acciones
            return ctx_acciones(self.ai, self.provider, MODO)
        except Exception:
            return {"modo": MODO, "proveedor": self.provider, "url": "", "ai": self.ai}

    def _acciones_permitidas(self) -> bool:
        return self.ejecutor is not None and self._feature("acciones_ia", True)

    # ── Salida (todo por la consola compartida) ──────────────────────────────────
    def _p(self, texto: str = "", end: str = "\n") -> None:
        self.consola.imprimir(texto, end=end)

    def traer_al_frente(self) -> None:
        """Alguien volvió a abrir Lune (otra patata, o la app en modo patata): esta
        consola delante (si Windows deja; si no, parpadea) y una línea. Hilo del aviso."""
        from servicios.instancia_patata import traer_consola_al_frente
        if not traer_consola_al_frente():
            try:
                self.consola.parpadear(hasta_foco=True)
            except Exception:
                pass
        self.consola.aviso(self._lune("o/", "¡Sigo aquí! Ya estaba abierta en esta terminal."))

    def _lune(self, cara: str, texto: str) -> str:
        c = self.c
        cara = self._en_estilo(cara)
        return f"{c['cyan']}Lune {c['yellow']}{cara}{c['reset']}  {texto}"

    # ── Caritas y colores (patata.caritas, patata.tema) ─────────────────────────
    def _estilo_caritas(self) -> str:
        estilo = _plano(self._cfg("patata", "caritas", "clasico"))
        return estilo if estilo in ESTILOS_CARITAS else "clasico"

    def _cara(self, emocion: str) -> str:
        """La carita de una emoción canónica en el estilo elegido (clasico o kaomoji)."""
        tabla = KAOMOJI if self._estilo_caritas() == "kaomoji" else CARITAS
        return tabla.get(str(emocion or ""), tabla["neutral"])

    def _en_estilo(self, cara: str) -> str:
        """Una carita clásica (":D") en el estilo elegido; lo demás, tal cual."""
        emocion = _EMOCION_DE_CARITA.get(cara)
        return self._cara(emocion) if emocion else cara

    def _tema_consola(self) -> str:
        """Preset de patata.tema (el color de «Lune» en esta terminal); si no vale, cian."""
        return preset_tema(self._cfg("patata", "tema", "cian")) or "cian"

    def _aplicar_tema_consola(self) -> None:
        """El color de «Lune» con la paleta del preset (ANSI truecolor, nucleo/tema);
        con el cian de siempre, el color ANSI de siempre. Sin color, nada."""
        base = self._c_base.get("cyan", "")
        if not base:
            return
        preset = self._tema_consola()
        if preset == "cian":
            self.c["cyan"] = base
            return
        try:
            from nucleo import tema
            self.c["cyan"] = tema.ansi(tema.paleta(preset)["cyan-500"])
        except Exception:
            self.c["cyan"] = base

    def _poner_titulo(self, cara: Optional[str] = None) -> None:
        """Título de la consola: la última carita y, con un juego delante, «modo juego».
        Con capas (nucleo/consola.titulo_capa), el modo juego es la capa «juego» (50):
        una alarma (60) se ve por encima; el baile (20) y el salvapantallas (10), debajo."""
        if cara:
            self._ultima_cara = cara
        texto = f"Lune {self._ultima_cara} · patata"
        capa = getattr(self.consola, "titulo_capa", None)
        try:
            if callable(capa):
                self.consola.titulo(texto)
                capa("juego", texto + " · modo juego" if self._juego_activo else None, 50)
            else:
                self.consola.titulo(texto + (" · modo juego" if self._juego_activo else ""))
        except Exception:
            pass

    def _aviso_voz(self, mensaje: str) -> None:
        """on_error del VoiceEngine (llega del hilo de audio): aviso sin romper el prompt."""
        c = self.c
        try:
            self.consola.aviso(f"{c['dim']}(voz) {una_linea(mensaje, 200)}{c['reset']}")
        except Exception:
            pass

    # ── Prompt: igual que la app (personalidad + memoria + herramientas + emociones) ──
    def _system_prompt(self, ctx: Optional[dict] = None) -> str:
        base = personajes.build_system_prompt(personajes.get_activo())
        try:
            mem = self.memoria.obtener_contexto_para_prompt()
        except Exception:
            mem = ""
        if mem:
            base += "\n\nCONTEXTO DE MEMORIA DEL USUARIO:\n" + mem
        if self._acciones_permitidas():
            try:
                reglas = reglas_herramientas(self.ejecutor.registro, MODO,
                                             set(self.ejecutor.handlers), ctx=ctx)
            except Exception:
                reglas = ""
            if reglas:
                base += "\n\n" + reglas
        return base + "\n\n" + GRAMATICA_EMOCIONES

    # ── Salida por consola (stream con los marcadores <|…|> ocultos) ────────────
    def _imprimir_stream(self):
        estado = {"buf": "", "dentro": False, "impreso": False}

        def on_token(t: str):
            s = estado["buf"] + t
            out = ""
            while s:
                if estado["dentro"]:
                    j = s.find("|>")
                    if j < 0:
                        break                      # marcador a medias: esperar
                    estado["dentro"] = False
                    s = s[j + 2:]
                    continue
                i = s.find("<|")
                if i < 0:
                    if s.endswith("<"):            # podría empezar "<|" en el próximo token
                        out += s[:-1]; s = "<"
                        break
                    out += s; s = ""
                else:
                    out += s[:i]; estado["dentro"] = True; s = s[i + 2:]
            estado["buf"] = s
            if out:
                estado["impreso"] = True
                self.consola.escribir(out)
        on_token.estado = estado
        return on_token

    def _carita(self, control) -> str:
        acts = [v for k, v in control if k == "act"]
        if not acts:
            return self._cara("neutral")
        return self._cara(str(acts[-1].get("emotion", "neutral")))

    # ── Sueño (la mascota que no hay) ────────────────────────────────────────────
    def _frases_mascota(self):
        """FrasesMascota del personaje activo (con el reloj de la sesión), o None."""
        if self._frases is None:
            try:
                self._frases = frases_para(personajes.get_activo(), reloj=self._reloj_sueno)
            except Exception:
                self._frases = False
        return self._frases or None

    def _actividad(self) -> None:
        """Apunta «ahora» como última actividad: una línea tuya (mensaje, comando o la
        respuesta s/n a una pregunta) o el final de una respuesta de Lune."""
        try:
            self._ultima_actividad = self._reloj_sueno()
        except Exception:
            pass

    def _avisar_si_durmio(self) -> Optional[str]:
        """Antes de responder: si la pausa desde la última actividad (tu última línea o
        el fin de la última respuesta, lo más reciente) dio para dormirse
        (avatar.dormir_min), se cuenta con el estilo de la consola. Devuelve el
        aviso impreso o None. Siempre apunta la hora de esta entrada."""
        ahora = self._reloj_sueno()
        pausa = max(0.0, ahora - self._ultima_actividad)
        self._ultima_actividad = ahora
        try:
            regla = ReglaSueno.desde_config(self.config)
            nombre = str((personajes.get_activo() or {}).get("nombre") or "Lune")
            if regla.mensaje_diferido(pausa, nombre) is None:
                return None
            frases = self._frases_mascota()
            frase = frases.elegir("despertar") if frases is not None else None
            aviso = regla.mensaje_diferido(pausa, nombre, frase_despertar=frase)
        except Exception:
            return None
        if not aviso:
            return None
        c = self.c
        primera, _, resto = aviso.partition("\n")
        self._p(f"{c['dim']}{una_linea(primera, 200)}{c['reset']}")
        if resto.strip():
            self._p(self._lune(CARITAS["bored"], una_linea(resto, 200)))
        self._p()
        return aviso

    # ── Un turno ─────────────────────────────────────────────────────────────────
    def responder(self, texto: str):
        self._avisar_si_durmio()             # volviste tras una pausa larga: se había dormido
        try:
            self._responder(texto)
        finally:
            self._actividad()                # la próxima pausa se mide desde aquí

    def _responder(self, texto: str):
        c = self.c
        # herramienta directa ("abre youtube", "estado del pc", "avísame en 10 minutos"):
        # la pidió la persona. Va al Ejecutor como cualquier acción (política,
        # presupuesto, aprobación y auditoría); el resultado llega por _al_resultado (en
        # línea o tras el «s»). Antes que la memoria (cortes 5/6): «recuérdame que a las
        # 5 tengo cita» es una alarma; sin hora ni duración sigue siendo un recuerdo.
        if self.tools is not None:
            try:
                llamadas = self.tools.detectar_llamadas(texto)
            except Exception:
                llamadas = []
            baile = [ll for ll in llamadas if ll.herramienta in ("mascota_bailar", "parar_baile")]
            if baile:
                # «baila» / «para de bailar»: aquí el baile es el título (BaileTerminal). Cortes
                # 9/10: «ponme el baile de X» (con canción) busca en tu biblioteca y pone la
                # canción con el título a su ritmo (BailesTerminal); «para» con una canción
                # puesta la para también.
                r = self._baile_pedido(baile[0])
                if r:
                    self._p(self._lune(":D", str(r)) + "\n")
                return
            if any(ll.herramienta == "mascota_sentarse" for ll in llamadas):
                # «siéntate», «bájate»: eso lo hace la mascota de las ventanas.
                texto_s = None
                if getattr(self, "sistema", None) is not None:
                    try:
                        texto_s = self.sistema.comando("/sentarse")
                    except Exception:
                        texto_s = None
                self._p(self._lune("^^'", texto_s or "Aquí no me puedo sentar: eso es de la mascota.") + "\n")
                return
            if llamadas and self.ejecutor is not None:
                self.ejecutor.ejecutar_llamadas(llamadas, ORIGEN_USUARIO, self._ctx(), self._al_resultado)
                return
        # memoria por comando ("recuerda que…")
        try:
            r = self.memoria.procesar_mensaje_usuario(texto)
        except Exception:
            r = None
        if r:
            self._p(self._lune(":D", r) + "\n"); return

        ctx = self._ctx()
        self.consola.escribir(f"{c['cyan']}Lune{c['reset']}  ")
        on_token = self._imprimir_stream()
        prov = (getattr(self.ai, "providers", {}) or {}).get(self.provider)
        if prov is not None:
            try:
                prov.cancel_flag = False
            except Exception:
                pass
        # Discord (si publica): «Pensando…» mientras llega la respuesta.
        self._pensando = True
        self._discord_al_dia()
        try:
            respuesta = asyncio.run(self.ai.chat(texto, self._system_prompt(ctx),
                                                 provider=self.provider, on_token=on_token))
        except KeyboardInterrupt:
            if prov is not None:
                try:
                    prov.cancel_flag = True
                except Exception:
                    pass
            self._p(f"\n{c['dim']}(interrumpido){c['reset']}\n"); return
        except Exception as e:
            self._p(f"\n{c['red']}(no pude responder: {e}){c['reset']}\n"); return
        finally:
            self._pensando = False
            self._discord_al_dia()
        respuesta = respuesta or ""

        # Acciones: el Ejecutor saca las <|CALL|> (el formato antiguo solo se borra).
        llamadas = []
        if self._acciones_permitidas():
            limpio, llamadas = self.ejecutor.procesar(respuesta, ORIGEN_USUARIO, ctx)
        else:
            limpio = limpiar_texto(respuesta)
        hablable, control = marcadores.separar(limpio)
        if not on_token.estado["impreso"] and hablable.strip():
            self.consola.escribir(hablable.strip())   # respuesta sin streaming (p. ej. un error)
        cara = self._carita(control)
        self._p(f"  {c['yellow']}{cara}{c['reset']}\n")
        self._poner_titulo(cara)
        self._hablar(limpio)
        try:
            self.memoria.procesar_respuesta_lune(limpio)
        except Exception:
            pass
        if llamadas:
            self.ejecutor.ejecutar_llamadas(llamadas, ORIGEN_USUARIO, ctx, self._al_resultado)

    def _baile_pedido(self, ll) -> Optional[str]:
        """Texto para «baila…» / «para de bailar» escritos en el chat (sin IA ni Ejecutor)."""
        bl = getattr(self, "bailes", None)
        bt = getattr(self, "baile", None)
        bailar = ll.herramienta == "mascota_bailar"
        try:
            if bl is not None and ((bailar and (ll.args or {}).get("cancion"))
                                   or (not bailar and bool(getattr(bl, "activo", False)))):
                r = bl.bailar_pedido(ll.args) if bailar else bl.parar_pedido()
                return str(r[1] if isinstance(r, tuple) and len(r) == 2 else r or "")
            if bt is None:
                return "Aquí no puedo bailar."
            return bt.comando("/bailar" if bailar else "/parar")
        except Exception as e:
            return f"No pude: {e}"

    def _hablar(self, limpio: str) -> None:
        """Voz por tramos (cada <|ACT|> es un tramo) si está activada."""
        v = self.voice
        if v is None or not getattr(v, "_enabled", False):
            return
        try:
            plan = expresiones.planificar(limpio)
            v.speak_segmentos(expresiones.segmentos_voz(plan))
        except Exception:
            pass

    # ── Acciones del modelo: resultados y aprobaciones ───────────────────────────
    def _al_resultado(self, res) -> None:
        """Llega de cualquier hilo (en línea, tras aprobar o al caducar)."""
        if res.ok:
            cara, marca = ":D", "✓"
        elif res.estado in (RECHAZADA, CADUCADA):
            cara, marca = "^^'", "✕"
        else:
            cara, marca = ">:(", "✕"
        try:
            self.consola.aviso(self._lune(cara, f"{marca} {una_linea(res.mensaje, 300)}"))
        except Exception:
            pass

    def _pedir_aprobacion(self, pendiente: dict, responder: Callable[[bool], None]) -> None:
        """La próxima línea que escribas es la respuesta: s/sí = hazlo; lo demás = no."""
        c = self.c
        pid = str(pendiente.get("id") or "")
        resumen = una_linea(pendiente.get("resumen") or pendiente.get("herramienta"), 160)
        riesgo = una_linea(pendiente.get("riesgo") or "", 20).lower()
        try:
            segundos = float(pendiente.get("timeout") or 60)
        except (TypeError, ValueError):
            segundos = 60.0
        lineas = [f"{c['yellow']}Lune quiere:{c['reset']} {resumen}"
                  + (f" {c['dim']}({riesgo}){c['reset']}" if riesgo else "")]
        args = pendiente.get("args") or {}
        if isinstance(args, dict):
            for k, v in list(args.items())[:8]:
                lineas.append(f"    {c['dim']}{una_linea(k, 30)}:{c['reset']} {una_linea(v, 120)}")
        lineas.append(f"{c['dim']}Contesta s o n ({segundos:g} s; sin respuesta, no lo hago).{c['reset']}")
        self.consola.aviso("\n".join(lineas))

        def al_responder(linea: str):
            if not str(linea or "").strip() and self._alarma_sonando():
                return False                          # el Enter vacío es de la alarma: sigue esperando
            with self._lock:
                self._reclamos.pop(pid, None)
            self._actividad()                         # contestar «s/n» también es estar ahí
            responder(str(linea or "").strip().lower() in SI)

        cancelar = self.consola.reclamar(al_responder, prompt=f"{c['yellow']}¿Lo hago? [s/N]{c['reset']} ",
                                         prioridad=PRIORIDAD_APROBACION)
        with self._lock:
            self._reclamos[pid] = cancelar
        try:
            self.consola.parpadear()
        except Exception:
            pass

    def _alarma_sonando(self) -> bool:
        aviso = getattr(self.alarmas, "aviso", None)
        return getattr(aviso, "sonando", None) is not None

    def _cerrar_aprobacion(self, pid: str) -> None:
        """Caducó o se canceló (conversación nueva): la línea vuelve al chat."""
        with self._lock:
            cancelar = self._reclamos.pop(str(pid), None)
        if cancelar is not None:
            try:
                cancelar()
            except Exception:
                pass

    def nueva_conversacion(self) -> None:
        try:
            self.ai.clear_history()
        except Exception:
            pass
        if self.ejecutor is not None:
            self.ejecutor.nueva_conversacion()

    # ── Datos del modelo ─────────────────────────────────────────────────────────
    def _guardar_modelos(self, cambios: Dict[str, Any]) -> None:
        """Mezcla `cambios` en datos.json → modelos (None borra la clave) y recarga proveedores."""
        d = datos.cargar() or {}
        m = d.setdefault("modelos", {})
        for k, v in cambios.items():
            if v is None:
                m.pop(k, None)
            else:
                m[k] = v
        datos.guardar(d)
        try:
            self.ai.reload_provider()
        except Exception:
            pass

    def _describir_proveedor(self, pid: Optional[str] = None) -> str:
        pid = pid or self.provider
        if pid == "ollama":
            return f"local · Ollama ({datos.ollama_model() or 'sin modelo'})"
        if pid == "openrouter":
            return f"nube · OpenRouter ({datos.openrouter_model()})"
        if pid == "compat":
            modelo = datos.compat_model() or "el primero que ofrezca"
            return f"API compatible · {modelo} en {datos.compat_url() or '(sin URL)'}"
        return pid

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> bool:
        """Devuelve True si hay que salir. Un comando también cuenta como actividad
        (la pausa del sueño se mide desde aquí)."""
        try:
            return self._comando(linea)
        finally:
            self._actividad()

    def _comando(self, linea: str) -> bool:
        c = self.c
        partes = linea.strip().split(maxsplit=1)
        cmd, arg = partes[0].lower(), (partes[1] if len(partes) > 1 else "")
        if cmd == "/salir":
            return True
        # Cortes 5/6: /alarma, /alarmas, /timer, /apagar… y /bailar, /parar.
        # Cortes 7/8: /comer y /discord, /autoinicio, /sentarse.
        # Cortes 9/10: /bailes (ANTES que el baile: con una canción puesta, su /parar la para
        # con el baile del título; sin canción devuelve None y sigue el /parar de siempre) y /mc.
        for modulo in (getattr(self, "alarmas", None), getattr(self, "bailes", None),
                       getattr(self, "baile", None), getattr(self, "comida", None),
                       getattr(self, "sistema", None), getattr(self, "minecraft", None)):
            if modulo is None:
                continue
            try:
                r = modulo.comando(linea)
            except Exception as e:
                r = f"No pude hacerlo: {e}"
            if r is not None:
                if r:
                    self._p(str(r) + "\n")
                return False
        acciones = {
            "/ayuda": lambda a: ayuda(),
            "/memoria": lambda a: self.memoria._cmd_listar(),
            "/olvida": lambda a: (self.memoria._cmd_olvida(a) if a
                                  else "¿Olvidar qué? /olvida <texto o id>"),
            "/personaje": self._cmd_personaje,
            "/proveedor": self._cmd_proveedor,
            "/nube": lambda a: self._cmd_proveedor("openrouter"),
            "/local": lambda a: self._cmd_proveedor("ollama"),
            "/modelo": self._cmd_modelo,
            "/estado": self._cmd_estado,
            "/temp": self._cmd_temp,
            "/ctx": self._cmd_ctx,
            "/liberar": self._cmd_liberar,
            "/compat": self._cmd_compat,
            "/voces": self._cmd_voces,
            "/voz": self._cmd_voz,
            "/herramientas": self._cmd_herramientas,
            "/nuevo": self._cmd_nuevo,
            "/tema": self._cmd_tema,
            "/caritas": self._cmd_caritas,
            "/juego": self._cmd_juego,
            "/ram": self._cmd_ram,
        }
        if cmd == "/limpiar":
            self.nueva_conversacion()
            os.system("cls" if os.name == "nt" else "clear")
            return False
        if cmd in ("/interfaz", "/menu"):
            fn2 = self._cmd_interfaz if cmd == "/interfaz" else self._cmd_menu
            try:
                texto, salir = fn2(arg.strip())
            except Exception as e:
                texto, salir = f"No pude hacerlo: {e}", False
            if texto:
                self._p(str(texto) + "\n")
            return salir
        fn = acciones.get(cmd)
        if fn is None:
            self._p(f"{c['dim']}Comando desconocido. /ayuda{c['reset']}\n")
            return False
        try:
            texto = fn(arg.strip())
        except Exception as e:
            texto = f"No pude hacerlo: {e}"
        if texto:
            self._p(str(texto) + "\n")
        return False

    def _cmd_personaje(self, arg: str) -> str:
        if not arg:
            return "Personajes: " + ", ".join(p.get("nombre", "") for p in personajes.listar())
        try:
            nombre = personajes.set_activo(arg)       # solo uno que exista (si no, la lista)
        except ValueError as e:
            return una_linea(e, 300)
        if self.voice is not None and hasattr(self.voice, "invalidar_params"):
            self.voice.invalidar_params()             # el personaje puede traer su voz
        self._frases = None                           # y sus propias frases al despertar
        return f"Personaje activo: {nombre}"

    def _cmd_proveedor(self, arg: str) -> str:
        provs = list((getattr(self.ai, "providers", {}) or {}).keys())
        if not arg:
            lista = ", ".join(("*" if p == self.provider else "") + p for p in provs)
            return f"Proveedores: {lista}  ·  ahora: {self._describir_proveedor()}  ·  /proveedor <id>"
        p = arg.strip().lower()
        p = ALIAS_PROVEEDOR.get(p, p)
        if p not in provs:
            if p == "compat":
                return ("La API compatible no está configurada. Ponla con "
                        "/compat url https://…/v1 (la clave va en Ajustes o en datos.json).")
            return f"No conozco «{una_linea(arg, 40)}». Usa uno de: {', '.join(provs)}."
        self.provider = p
        return f"Ahora respondo con {self._describir_proveedor()}."

    def _cmd_modelo(self, arg: str) -> str:
        clave = CLAVE_MODELO.get(self.provider)
        if not arg:
            return f"Modelo actual: {self._describir_proveedor()}  ·  /modelo <nombre>"
        if clave is None:
            return f"No sé cambiar el modelo de «{self.provider}»."
        nombre = arg.strip()
        if not _RE_MODELO.match(nombre):
            return "Ese nombre de modelo no es válido (sin espacios, p. ej. llama3.1:8b)."
        self._guardar_modelos({clave: nombre})
        return f"Modelo de {self.provider}: {nombre}."

    def _cmd_estado(self, arg: str = "") -> str:
        p = datos.parametros_muestreo()
        extra = [f"{k} {p[k]}" for k in ("top_p", "top_k", "min_p", "repeat_penalty", "num_predict", "seed")
                 if p.get(k) is not None]
        lineas = [f"Proveedor: {self._describir_proveedor()}",
                  f"Parámetros: preset {p['preset']} · temperatura {p['temperatura']} · "
                  f"contexto {p['num_ctx']}" + (" · " + " · ".join(extra) if extra else "")]
        try:
            from servicios import voces
            lineas.append(voces.comando_voz("", self.config, self.voice))
        except Exception:
            pass
        if self.ejecutor is None:
            lineas.append("Acciones: no disponibles.")
        else:
            s = self.ejecutor.sesion
            lineas.append(
                f"Acciones: {'permitidas' if self._acciones_permitidas() else 'apagadas (acciones_ia)'} · "
                f"{len(self.ejecutor.disponibles(MODO))} herramientas · gastado {s.gastado}/{s.presupuesto}"
                + (f" · {len(self.ejecutor.pendientes())} esperando tu permiso" if self.ejecutor.pendientes() else ""))
        return "\n".join(lineas)

    def _cmd_temp(self, arg: str) -> str:
        a = arg.strip().lower()
        if not a:
            p = datos.parametros_muestreo()
            return (f"Temperatura {p['temperatura']} · preset {p['preset']}  ·  "
                    "/temp <0-2> o /temp preciso|equilibrado|creativo")
        if a in datos.PRESETS_MUESTREO:
            p = datos.aplicar_preset_muestreo(a)
            try:
                self.ai.reload_provider()
            except Exception:
                pass
            return f"Preset {a}: temperatura {p['temperatura']}."
        try:
            v = float(a.replace(",", "."))
        except ValueError:
            return "Pon un número entre 0 y 2 (p. ej. /temp 0.7) o un preset: preciso, equilibrado, creativo."
        if not (0.0 <= v <= 2.0):
            return "La temperatura va de 0 (precisa) a 2 (muy creativa)."
        v = round(v, 2)
        cambios: Dict[str, Any] = {"temperatura": v}
        preset = datos.preset_muestreo()
        if datos.PRESETS_MUESTREO.get(preset, {}).get("temperatura") != v:
            cambios["preset_muestreo"] = datos.PRESET_PERSONALIZADO
        self._guardar_modelos(cambios)
        return f"Temperatura: {v}."

    def _cmd_ctx(self, arg: str) -> str:
        if not arg:
            return f"Contexto de Ollama: {datos.ollama_num_ctx()} tokens  ·  /ctx 8k (de {CTX_MIN} a {CTX_MAX})"
        n = leer_ctx(arg)
        if n is None:
            return f"Pon un número de tokens entre {CTX_MIN} y {CTX_MAX} (p. ej. /ctx 8192 o /ctx 16k)."
        self._guardar_modelos({"ollama_num_ctx": n})
        nota = "" if self.provider == "ollama" else " (solo afecta a Ollama)"
        return f"Contexto: {n} tokens{nota}. Más contexto = más memoria de vídeo."

    def _cmd_liberar(self, arg: str = "") -> str:
        if "ollama" not in (getattr(self.ai, "providers", {}) or {}):
            return "No hay modelo local que liberar."
        self._p(f"{self.c['dim']}Liberando el modelo local…{self.c['reset']}")
        ok = bool(self.ai.descargar_modelo())
        return ("Listo: el modelo local salió de la memoria. El próximo mensaje tardará un poco más."
                if ok else "Ollama no respondió; no pude liberar el modelo.")

    def _cmd_compat(self, arg: str) -> str:
        partes = arg.split(None, 1)
        orden = partes[0].lower() if partes else ""
        resto = partes[1].strip() if len(partes) > 1 else ""
        if orden == "url":
            u = url_compat_valida(resto)
            if u is None:
                return "URL no válida: usa http(s)://servidor[:puerto]/v1, sin usuario ni clave dentro."
            if u.lower().endswith("/chat/completions"):
                u = u[: -len("/chat/completions")]
            self._guardar_modelos({"compat_url": u})
            aviso = ""
            if u.startswith("http://") and datos.compat_key():
                from servicios.ai_manager import es_host_local
                if not es_host_local(u):
                    aviso = " Ojo: la clave viajaría sin cifrar (http fuera de tu red)."
            return f"API compatible en {u}. Úsala con /proveedor compat.{aviso}"
        if orden == "modelo":
            if not resto or not _RE_MODELO.match(resto):
                return "Pon el nombre del modelo, p. ej. /compat modelo llama-3.1-8b-instant."
            self._guardar_modelos({"compat_model": resto})
            return f"Modelo de la API compatible: {resto}."
        if orden == "off":
            self._guardar_modelos({"compat_url": None})
            if self.provider == "compat":
                self.provider = "ollama" if datos.ollama_model() else "openrouter"
            return f"API compatible apagada. Respondo con {self._describir_proveedor()}."
        if orden:
            return "Uso: /compat · /compat url <https://…/v1> · /compat modelo <nombre> · /compat off"
        if not datos.compat_url():
            return ("API compatible sin configurar (LM Studio, Groq, OpenAI, Together, Mistral…).\n"
                    "  /compat url http://localhost:1234/v1   ·   /compat modelo <nombre>\n"
                    "  La clave, si hace falta, va en Ajustes o en datos.json (modelos.compat_key).")
        self._p(f"{self.c['dim']}Probando {datos.compat_url()}…{self.c['reset']}")
        r = self.ai.probar_compat() or {}
        lineas = [f"{'✓' if r.get('ok') else '✕'} {una_linea(r.get('mensaje', ''), 200)}"
                  + (f" ({r['ms']} ms)" if r.get("ms") is not None else "")]
        modelos = [m if isinstance(m, str) else str(m.get("id", "")) for m in (r.get("modelos") or [])]
        if modelos:
            lineas.append("  Modelos: " + ", ".join(una_linea(m, 60) for m in modelos[:10])
                          + (" …" if len(modelos) > 10 else ""))
        lineas.append(f"  Clave: {'configurada' if datos.compat_key() else 'sin clave'} · "
                      f"modelo: {datos.compat_model() or '(el primero que ofrezca)'}")
        return "\n".join(lineas)

    def _cmd_voces(self, arg: str) -> str:
        from servicios import voces
        actual = ""
        try:
            actual = voces.voz_activa(self.config).id
        except Exception:
            pass
        return voces.texto_voces(arg, actual=actual)

    def _cmd_voz(self, arg: str) -> str:
        from servicios import voces
        return voces.comando_voz(arg, self.config, self.voice)

    def _cmd_herramientas(self, arg: str = "") -> str:
        if self.ejecutor is None:
            return "Las acciones no están disponibles en esta sesión."
        from lune_core import catalogo_herramientas as cat
        from lune_core.herramientas import Riesgo
        lineas = ["Lo que puedo hacer desde aquí (tú escribes, yo lo pido con <|CALL|>):"]
        for nombre in self.ejecutor.disponibles(MODO):
            h, d = cat.obtener(nombre), self.ejecutor.registro.get(nombre)
            permiso = d is not None and (d.requiere_aprobacion or d.riesgo == Riesgo.DESTRUCTIVO)
            lineas.append(f"  · {nombre}: {h.descripcion if h else nombre}"
                          + (" (te pido permiso)" if permiso else ""))
        if not self._acciones_permitidas():
            lineas.append("  (ahora están apagadas: features.acciones_ia)")
        return "\n".join(lineas)

    def _cmd_nuevo(self, arg: str = "") -> str:
        self.nueva_conversacion()
        return "Conversación nueva."

    # ── Corte 4 en la terminal: tema, caritas, memoria, modo juego y /menu ──────
    def _guardar_patata(self, clave: str, valor: Any) -> Optional[str]:
        """config patata.<clave>; devuelve el motivo si no se pudo."""
        if self.config is None:
            return "No puedo guardar la configuración (config.json)."
        try:
            self.config.set("patata", clave, valor)
        except Exception as e:
            return f"No pude guardarlo: {una_linea(e, 200)}"
        return None

    def _cmd_tema(self, arg: str) -> str:
        from nucleo import tema
        actual = self._tema_consola()
        if not arg.strip():
            lista = ", ".join(("*" if p == actual else "") + p for p in tema.PRESETS)
            return f"Temas: {lista}  ·  /tema <nombre> (el color de esta terminal)"
        p = preset_tema(arg)
        if p is None:
            return f"No conozco el tema «{una_linea(arg, 30)}». Temas: {', '.join(tema.PRESETS)}."
        error = self._guardar_patata("tema", p)
        if error:
            return error
        self._aplicar_tema_consola()
        return self._lune(":D", f"Tema {tema.ETIQUETAS.get(p, p)}.")

    def _cmd_caritas(self, arg: str) -> str:
        a = _plano(arg)
        if not a:
            estilo = self._estilo_caritas()
            return (f"Caritas: {estilo} {self._cara('happy')}  ·  /caritas clasico  ·  "
                    f"/caritas kaomoji")
        estilo = {"clasico": "clasico", "clasicas": "clasico", "teclado": "clasico",
                  "kaomoji": "kaomoji", "kaomojis": "kaomoji"}.get(a)
        if estilo is None:
            return "Elige: /caritas clasico (:D) o /caritas kaomoji (^▽^)."
        error = self._guardar_patata("caritas", estilo)
        if error:
            return error
        return self._lune(":D", f"Caritas {estilo}.")

    def _cmd_ram(self, arg: str = "") -> str:
        fn = self._recortar_fn
        if fn is None:
            from servicios.recorte_ram import recortar as fn  # noqa: N813
        try:
            antes, despues = fn()
            antes, despues = float(antes), float(despues)
        except Exception as e:
            return f"No pude liberar memoria: {una_linea(e, 200)}"
        return f"Memoria de Lune: {antes:.0f} MB → {despues:.0f} MB."

    # Modo juego: DetectorJuego (servicios/modo_juego.py, sin Qt) en un hilo cada 2 s.
    def _detector(self):
        if self._det_juego is None:
            try:
                from servicios.modo_juego import DetectorJuego
                self._det_juego = DetectorJuego(self.config)
            except Exception:
                self._det_juego = False
        return self._det_juego or None

    def _cambiar_prioridad(self, baja: bool) -> None:
        fn = self._prioridad_fn
        if fn is None:
            from servicios.modo_juego import aplicar_prioridad as fn
        try:
            fn(bool(baja))
        except Exception:
            pass

    def _tic_juego(self) -> bool:
        """Una lectura del detector; si cambió, lo aplica. True si cambió."""
        det = self._detector()
        if det is None:
            return False
        with self._lock_juego:
            try:
                if not det.detectando() and not self._juego_activo:
                    return False
                _cambio, activo, motivo = det.evaluar()
            except Exception:
                return False
            activo = bool(activo)
            self._juego_motivo = str(motivo or "") if activo else ""
            if activo == self._juego_activo:
                return False
            self._juego_activo = activo
            self._aplicar_juego(activo)
            return True

    def _aplicar_juego(self, activo: bool) -> None:
        """Con un juego delante: prioridad «por debajo de lo normal» (solo Lune) si
        juego.prioridad_baja; al acabar, la de antes. Y el estado en el título."""
        if activo:
            try:
                from servicios.modo_juego import plan
                baja = bool(plan(self.config).prioridad_baja)
            except Exception:
                baja = True
            if baja and not self._prioridad_baja:
                self._cambiar_prioridad(True)
                self._prioridad_baja = True
        elif self._prioridad_baja:
            self._cambiar_prioridad(False)
            self._prioridad_baja = False
        self._poner_titulo()
        self._discord_al_dia()                   # con un juego delante, Discord no ve nada
        try:
            from nucleo.utils import log_info
            log_info(f"[juego] {'entra: ' + (self._juego_motivo or '?') if activo else 'sale'} (patata)")
        except Exception:
            pass

    def _texto_juego(self) -> str:
        det = self._detector()
        if det is None:
            return "El modo juego no está disponible aquí."
        from nucleo.acciones_ui import texto_motivo_juego
        try:
            forzado = det.forzado
        except Exception:
            forzado = None
        if self._juego_activo:
            texto = "Modo juego: activo"
            if self._juego_motivo:
                texto += f" ({texto_motivo_juego(self._juego_motivo)})"
        else:
            texto = "Modo juego: no hay juego delante"
        if forzado is True:
            texto += " · forzado a mano (/juego auto para detectarlo)"
        elif forzado is False:
            texto += " · apagado a mano (/juego auto para detectarlo)"
        elif not bool(self._cfg("juego", "activo", True)):
            texto += " · la detección está apagada (juego.activo)"
        else:
            texto += " · automático"
        return texto + "."

    def _cmd_juego(self, arg: str) -> str:
        det = self._detector()
        if det is None:
            return "El modo juego no está disponible aquí."
        a = _plano(arg)
        forzar = {"on": True, "si": True, "1": True, "forzar": True,
                  "off": False, "no": False, "0": False,
                  "auto": None, "automatico": None}
        if a:
            if a not in forzar:
                return "Uso: /juego · /juego on · /juego off · /juego auto"
            det.forzar(forzar[a])
            self._tic_juego()                    # se aplica ya, sin esperar al hilo
        return self._texto_juego()

    def iniciar_juego(self) -> bool:
        """El hilo del modo juego (una lectura cada DetectorJuego.INTERVALO_S). Lo
        arranca correr(); True si arrancó."""
        if self._hilo_juego is not None:
            return False
        det = self._detector()
        if det is None:
            return False
        try:
            intervalo = max(0.05, float(getattr(det, "INTERVALO_S", 2.0) or 2.0))
        except (TypeError, ValueError):
            intervalo = 2.0
        self._parar_juego.clear()

        def bucle():
            while not self._parar_juego.wait(intervalo):
                try:
                    self._tic_juego()
                except Exception:
                    pass
        self._hilo_juego = threading.Thread(target=bucle, name="lune-juego", daemon=True)
        self._hilo_juego.start()
        return True

    def detener_juego(self) -> None:
        """Para el hilo y devuelve la prioridad si el modo juego la bajó."""
        self._parar_juego.set()
        hilo, self._hilo_juego = self._hilo_juego, None
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(timeout=1.0)
        with self._lock_juego:
            if self._prioridad_baja:
                self._cambiar_prioridad(False)
                self._prioridad_baja = False
            self._juego_activo = False

    # /menu: el catálogo común de acciones (nucleo/acciones_ui) en modo «patata».
    def _despachador(self):
        if self._desp is None:
            from nucleo.acciones_ui import Despachador
            d = Despachador()
            d.registrar("voz", self._accion_voz,
                        marcado=lambda: bool(getattr(self.voice, "_enabled", False)))
            if self._detector() is not None:
                d.registrar("modo_juego_forzar", self._accion_juego, marcado=lambda: self._juego_activo)
            d.registrar("tema", self._accion_tema)
            d.registrar("autoinicio", self._accion_autoinicio, marcado=self._autoinicio_on)
            s = getattr(self, "sistema", None)
            if s is not None:
                d.registrar("discord", lambda: self._p(s.alternar_discord()),
                            marcado=lambda: bool(s.discord_activo))
            # Cortes 9/10: «Mis bailes» (la lista, /bailes), las reacciones a Minecraft y el bot.
            bl = getattr(self, "bailes", None)
            if bl is not None:
                d.registrar("bailes", lambda: self._p(bl.comando("/bailes") or ""))
            mc = getattr(self, "minecraft", None)
            if mc is not None:
                def reacciones():
                    on = bool(mc.alternar_reacciones())
                    self._p("Reacciono a tu partida de Minecraft." if on else "Ya no reacciono a Minecraft.")

                def bot():
                    if mc.bot_conectado or bool(getattr(getattr(mc, "proceso", None), "vivo", False)):
                        mc.desconectar_bot()
                        self._p("Desconecto el bot de Minecraft.")
                    else:
                        _ok, texto = mc.conectar_bot()
                        self._p(una_linea(texto, 300))
                d.registrar("minecraft", reacciones, marcado=lambda: bool(mc.reaccionando))
                d.registrar("minecraft_bot", bot, marcado=lambda: bool(mc.bot_conectado))
            d.registrar("liberar_memoria", lambda: self._p(self._cmd_ram()))
            d.registrar("salir", self._accion_salir)
            self._desp = d
        return self._desp

    def _mod_autoinicio(self):
        if self._autoinicio is None:
            try:
                from servicios import autoinicio
                self._autoinicio = autoinicio
            except Exception:
                self._autoinicio = False
        return self._autoinicio or None

    def _autoinicio_on(self) -> bool:
        m = self._mod_autoinicio()
        try:
            return bool(m.activo()) if m is not None else False
        except Exception:
            return False

    def _accion_voz(self) -> None:
        from servicios import voces
        orden = "off" if getattr(self.voice, "_enabled", False) else "on"
        self._p(voces.comando_voz(orden, self.config, self.voice))

    def _accion_juego(self, arg: str = "") -> None:
        det = self._detector()
        if det is None:
            return
        if not _plano(arg):                      # alternar: forzado → auto; activo → apagar; si no → forzar
            forzado = getattr(det, "forzado", None)
            arg = "auto" if forzado is not None else ("off" if self._juego_activo else "on")
        self._p(self._cmd_juego(arg))

    def _accion_tema(self, arg: str = "") -> None:
        if not str(arg or "").strip():           # sin nombre: el siguiente preset
            from nucleo import tema
            orden = list(tema.PRESETS)
            actual = self._tema_consola()
            arg = orden[(orden.index(actual) + 1) % len(orden)] if actual in orden else orden[0]
        self._p(self._cmd_tema(arg))

    def _accion_autoinicio(self) -> None:
        m = self._mod_autoinicio()
        if m is None:
            self._p("No sé arrancar con Windows desde aquí.")
            return
        try:
            # La variante de patata: consola minimizada, sin PyQt6 (servicios/autoinicio).
            nuevo = bool(m.establecer(not self._autoinicio_on(), "patata"))
        except Exception as e:
            self._p(f"No pude cambiarlo: {una_linea(e, 200)}")
            return
        if self.config is not None:
            try:
                self.config.set("sistema", "autoinicio", nuevo)
            except Exception:
                pass
        self._p("Lune arrancará con Windows." if nuevo else "Lune ya no arranca con Windows.")

    def _accion_salir(self) -> None:
        self._salir_pedido = True

    def _items_menu(self) -> list:
        from nucleo import acciones_ui as au
        d = self._despachador()
        det = self._detector()
        ctx = au.Contexto(
            modo="patata", voz_on=bool(getattr(self.voice, "_enabled", False)),
            juego_forzado=getattr(det, "forzado", None) if det is not None else None,
            autoinicio_on=self._autoinicio_on(), tema_preset=self._tema_consola(),
            juego_activo=self._juego_activo, juego_motivo=self._juego_motivo)
        items = [x for x in au.catalogo(d, None, ctx) if x.get("disponible") and x.get("visible")]
        return sorted(items, key=lambda x: x["id"] == "salir")      # «Salir», la última

    def _cmd_menu(self, arg: str):
        """(texto, salir). Sin número, la lista; con él, la hace (con la opción si la
        hay: /menu 3 violeta)."""
        items = self._items_menu()
        partes = arg.split(None, 1)
        if not partes:
            lineas = ["Menú (/menu <n> para elegir; algunas aceptan una opción: /menu <n> <opción>):"]
            for i, it in enumerate(items, 1):
                marca = "" if it.get("marcado") is None else ("  ✓" if it["marcado"] else "  ·")
                lineas.append(f"  {i}. {it['etiqueta']}{marca}")
            lineas.append("  (Aquí no hay bandeja, menú radial ni atajos globales: eso es de las ventanas.)")
            return "\n".join(lineas), False
        try:
            n = int(partes[0])
        except ValueError:
            ids = [it["id"] for it in items]
            n = ids.index(partes[0].lower()) + 1 if partes[0].lower() in ids else 0
        if not 1 <= n <= len(items):
            return f"No hay la opción «{una_linea(partes[0], 20)}». /menu para verlas.", False
        it = items[n - 1]
        self._salir_pedido = False
        if not self._despachador().ejecutar(it["id"], partes[1] if len(partes) > 1 else ""):
            return f"No pude hacer «{it['etiqueta']}».", False
        salir = self._salir_pedido
        self._salir_pedido = False
        return "", salir

    def _cmd_interfaz(self, arg: str):
        """(texto, salir). Guarda interfaz.modo, abre la app de ventanas y, si abrió,
        patata se cierra (salir=True). Si no pudo, vuelve el modo de antes y sigue aquí."""
        uso = ("Estás en la terminal (modo patata). /interfaz web → la interfaz completa · "
               "/interfaz nativo → la de bajos recursos. Cierro la terminal al abrirla.")
        a = arg.strip().lower()
        if not a:
            return uso, False
        if a in ("patata", "terminal"):
            return "Ya estás en el modo patata.", False
        modo = MODOS_INTERFAZ.get(a)
        if modo is None:
            return f"No conozco la interfaz «{una_linea(arg, 30)}». {uso}", False
        if self.config is None:
            return "No puedo guardar la configuración (config.json): sigo aquí.", False
        anterior = self._cfg("interfaz", "modo", "web")
        try:
            self.config.set("interfaz", "modo", modo)
        except Exception as e:
            return f"No pude guardar el modo: {una_linea(e, 200)}. Sigo aquí.", False
        c = self.c
        self._p(f"{c['dim']}Abriendo la interfaz {NOMBRE_INTERFAZ[modo]}…{c['reset']}")
        motivo = ""
        try:
            ok = bool(self._lanzador(modo))
        except Exception as e:
            ok, motivo = False, una_linea(e, 200)
        if not ok:
            try:
                self.config.set("interfaz", "modo", anterior)
            except Exception:
                pass
            return (f"No pude abrir la interfaz{': ' + motivo if motivo else ''}. Sigo aquí.", False)
        # salir=True: correr() sale del bucle y cerrar() deja nada pendiente.
        return self._lune("o/", "Te espero en la ventana. Cierro la terminal."), True

    # ── Bucle ────────────────────────────────────────────────────────────────────
    def iniciar_ocio(self) -> None:
        """Cortes 5/6: el hilo de las alarmas, el detector de música del baile y el
        salvapantallas del título (cada uno en su hilo). Lo llama correr(). Cortes 7/8:
        la comida (nada que arrancar) y la presencia de Discord (sin hilo si está apagada).
        Cortes 9/10: los bailes y Minecraft (su hilo solo con las reacciones o el bot)."""
        for nombre in ("alarmas", "baile", "salvapantallas", "comida", "sistema", "bailes", "minecraft"):
            modulo = getattr(self, nombre, None)
            if modulo is None:
                continue
            try:
                modulo.iniciar()
            except Exception:
                pass

    def detener_ocio(self) -> None:
        """Para lo de iniciar_ocio y quita sus capas del título (idempotente). Lo que
        sonaba queda en alarmas.json para la próxima vez. Minecraft para el bot (que no
        quede node vivo) y los bailes su canción, ANTES que el baile del título."""
        for nombre in ("minecraft", "bailes", "sistema", "comida", "salvapantallas", "baile", "alarmas"):
            modulo = getattr(self, nombre, None)
            if modulo is None:
                continue
            try:
                modulo.detener()
            except Exception:
                pass

    def cerrar(self) -> None:
        self.detener_ocio()                          # antes que la consola: quitan sus capas
        try:
            self.detener_juego()                     # hilo del modo juego y prioridad de antes
        except Exception:
            pass
        if self.ejecutor is not None:
            self.ejecutor.nueva_conversacion()       # nada pendiente al salir
        if self.voice is not None:
            try:
                self.voice.cancelar()
            except Exception:
                pass
        try:
            self.consola.detener()
        except Exception:
            pass

    def correr(self) -> int:
        c = self.c
        nombre = personajes.get_activo().get("nombre", "Lune")
        if self.con_windows:
            # Arrancó con Windows (consola minimizada): una línea y listo.
            self._p(f"{c['bold']}{c['cyan']}月 {nombre} — modo patata{c['reset']} "
                    f"{c['dim']}(arrancó con Windows · /ayuda){c['reset']}\n")
        else:
            self._p(f"{c['bold']}{c['cyan']}月 {nombre} — modo patata{c['reset']} "
                    f"{c['dim']}({self._describir_proveedor()}){c['reset']}")
            self._p(f"{c['dim']}Solo texto. Caritas en vez de mascota. /ayuda para los comandos, "
                    f"/salir para irte.{c['reset']}\n")
            self._p(self._lune("o/", "Lune en línea. Dime qué necesitas.") + "\n")
        # El título normal desde el principio: al quitarse la última capa (salvapantallas,
        # baile, alarma…) vuelve este, aunque aún no hayas chateado.
        self._poner_titulo()
        try:
            self.iniciar_juego()                     # modo juego: detector cada 2 s (sin Qt)
        except Exception:
            pass
        self.iniciar_ocio()                          # alarmas, baile y salvapantallas
        try:
            while True:
                try:
                    linea = self.consola.leer_linea(self._texto_prompt()).strip()
                except (EOFError, KeyboardInterrupt):
                    self._p(); break
                if not linea:
                    continue
                try:
                    if linea.startswith("/"):
                        if self.comando(linea):
                            break
                        continue
                    self.responder(linea)
                except KeyboardInterrupt:
                    # Ctrl+C fuera del stream (voz, memoria, acciones, un comando
                    # lento): se corta eso y se vuelve al prompt, sin traceback.
                    self._interrumpido()
            self._p(self._lune("o/", "Hasta luego."))
        finally:
            self.cerrar()
        return 0

    def _interrumpido(self) -> None:
        c = self.c
        prov = (getattr(self.ai, "providers", {}) or {}).get(self.provider)
        if prov is not None:
            try:
                prov.cancel_flag = True
            except Exception:
                pass
        if self.voice is not None:
            try:
                self.voice.cancelar()
            except Exception:
                pass
        try:
            self._p(f"\n{c['dim']}(interrumpido){c['reset']}\n")
        except Exception:
            pass


_BANDERAS_AUTOINICIO = frozenset({"--autoinicio", "/autoinicio", "-autoinicio"})


def arranque_con_windows(*, config: Any = _AUTO, autoinicio: Any = None,
                         lanzar: Optional[Callable[[], Any]] = None) -> Optional[int]:
    """`patata.py --autoinicio` (entrada Run en su variante /patata). Repara la entrada
    (carpeta movida o modo cambiado: servicios/autoinicio.reparar, nunca la crea) y, si
    la interfaz ya NO es patata, abre la app de ventanas con --autoinicio y devuelve 0
    (patata se va). None = seguir aquí (sigue siendo patata, o la app no pudo abrir).
    Sin Qt."""
    cfg = _config_por_defecto() if config is _AUTO else config
    try:
        modo = str(cfg.get("interfaz", "modo", "web") or "web") if cfg is not None else "patata"
    except Exception:
        modo = "patata"
    mod = autoinicio
    if mod is None:
        try:
            from servicios import autoinicio as mod
        except Exception:
            mod = None
    if mod is not None:
        try:
            mod.reparar(cfg, modo)
        except Exception:
            pass
    if modo == "patata":
        return None
    try:
        ok = bool((lanzar or (lambda: lanzar_app_qt(modo, extra=("--autoinicio",))))())
    except Exception:
        ok = False
    return 0 if ok else None


TXT_YA_ABIERTA = "Lune ya está abierta en otra terminal (modo patata)."
ESPERA_YA_ABIERTA_S = 4.0     # que dé tiempo a leerlo antes de que se cierre esta consola


def _nueva_instancia():
    """El mutex de instancia única de patata (los tests lo cambian por un doble)."""
    from servicios.instancia_patata import InstanciaPatata
    return InstanciaPatata()


def main(argv=None, *, instancia: Any = None, esperar: Callable[[float], Any] = time.sleep) -> int:
    argv = sys.argv[1:] if argv is None else argv
    con_windows = any(str(a).strip().lower() in _BANDERAS_AUTOINICIO for a in argv)
    if con_windows:
        r = arranque_con_windows()
        if r is not None:
            return r
    inst = instancia if instancia is not None else _nueva_instancia()
    if not inst.adquirir():
        # Ya hay una patata (p. ej. la del arranque con Windows): que se enseñe ella.
        traida = inst.pedir_mostrar()
        print(TXT_YA_ABIERTA + (" Te la traigo al frente." if traida else ""), flush=True)
        if not con_windows:
            esperar(ESPERA_YA_ABIERTA_S)
        return 0
    try:
        p = Patata(color="--sin-color" not in argv, con_windows=con_windows)
        al_frente = getattr(p, "traer_al_frente", None)
        if callable(al_frente):
            inst.escuchar(al_frente)
        return p.correr()
    except KeyboardInterrupt:
        # Ctrl+C mientras arranca o se despide: se sale sin traceback.
        return 130
    finally:
        inst.liberar()


if __name__ == "__main__":
    raise SystemExit(main())
