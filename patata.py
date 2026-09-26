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
  /salir
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

SI = frozenset({"s", "si", "sí", "y", "yes"})
ALIAS_PROVEEDOR = {"local": "ollama", "nube": "openrouter", "api": "compat"}
CLAVE_MODELO = {"ollama": "ollama_model", "openrouter": "openrouter_model",
                "compat": "compat_model"}
_RE_MODELO = re.compile(r"^[\w.:/@+\-]{1,160}$")
CTX_MIN, CTX_MAX = 512, 131072


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


def _en_hilo(fn: Callable[[], None]) -> None:
    """Lo que sigue a una aprobación sale del hilo lector de la consola (tiene que ser rápido)."""
    threading.Thread(target=fn, name="lune-accion", daemon=True).start()


def _config_por_defecto():
    try:
        from nucleo.config import Config
        return Config()
    except Exception:
        return None


class Patata:
    def __init__(self, color: bool = True, *, consola: Any = None, config: Any = _AUTO,
                 ai: Any = None, memoria: Any = None, voice: Any = _AUTO, tools: Any = _AUTO,
                 audit_path: Any = _AUTO, reloj_sueno: Optional[Callable[[], float]] = None,
                 **opciones_ejecutor):
        self.c = _colores(color)
        self.config = _config_por_defecto() if config is _AUTO else config
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

    def _lune(self, cara: str, texto: str) -> str:
        c = self.c
        return f"{c['cyan']}Lune {c['yellow']}{cara}{c['reset']}  {texto}"

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
            return CARITAS["neutral"]
        return CARITAS.get(str(acts[-1].get("emotion", "neutral")), CARITAS["neutral"])

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
        # memoria por comando ("recuerda que…")
        try:
            r = self.memoria.procesar_mensaje_usuario(texto)
        except Exception:
            r = None
        if r:
            self._p(self._lune(":D", r) + "\n"); return
        # herramienta directa ("abre youtube", "estado del pc"): la pidió la persona.
        # Va al Ejecutor como cualquier acción (política, presupuesto, aprobación y
        # auditoría); el resultado llega por _al_resultado (en línea o tras el «s»).
        if self.tools is not None and self.ejecutor is not None:
            try:
                llamadas = self.tools.detectar_llamadas(texto)
            except Exception:
                llamadas = []
            if llamadas:
                self.ejecutor.ejecutar_llamadas(llamadas, ORIGEN_USUARIO, self._ctx(), self._al_resultado)
                return

        ctx = self._ctx()
        self.consola.escribir(f"{c['cyan']}Lune{c['reset']}  ")
        on_token = self._imprimir_stream()
        prov = (getattr(self.ai, "providers", {}) or {}).get(self.provider)
        if prov is not None:
            try:
                prov.cancel_flag = False
            except Exception:
                pass
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
        try:
            self.consola.titulo(f"Lune {cara} · patata")
        except Exception:
            pass
        self._hablar(limpio)
        try:
            self.memoria.procesar_respuesta_lune(limpio)
        except Exception:
            pass
        if llamadas:
            self.ejecutor.ejecutar_llamadas(llamadas, ORIGEN_USUARIO, ctx, self._al_resultado)

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
            with self._lock:
                self._reclamos.pop(pid, None)
            self._actividad()                         # contestar «s/n» también es estar ahí
            responder(str(linea or "").strip().lower() in SI)

        cancelar = self.consola.reclamar(al_responder, prompt=f"{c['yellow']}¿Lo hago? [s/N]{c['reset']} ")
        with self._lock:
            self._reclamos[pid] = cancelar
        try:
            self.consola.parpadear()
        except Exception:
            pass

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
        acciones = {
            "/ayuda": lambda a: (__doc__.split("Comandos:")[1].strip("\n")
                                 if "Comandos:" in __doc__ else ""),
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
        }
        if cmd == "/limpiar":
            self.nueva_conversacion()
            os.system("cls" if os.name == "nt" else "clear")
            return False
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

    # ── Bucle ────────────────────────────────────────────────────────────────────
    def cerrar(self) -> None:
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
        self._p(f"{c['bold']}{c['cyan']}月 {nombre} — modo patata{c['reset']} "
                f"{c['dim']}({self._describir_proveedor()}){c['reset']}")
        self._p(f"{c['dim']}Solo texto. Caritas en vez de mascota. /ayuda para los comandos, "
                f"/salir para irte.{c['reset']}\n")
        self._p(self._lune("o/", "Lune en línea. Dime qué necesitas.") + "\n")
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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return Patata(color="--sin-color" not in argv).correr()
    except KeyboardInterrupt:
        # Ctrl+C mientras arranca o se despide: se sale sin traceback.
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
