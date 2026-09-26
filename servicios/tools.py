"""
tools.py — Herramientas de escritorio de Lune CD y sus handlers para el Ejecutor.
=================================================================================

Dos caminos, con reglas distintas:

  · Lo que escribe el USUARIO («abre youtube», «busca gatos», «estado del pc»)
    lo detecta `detectar_llamadas()` (sin IA) y lo ejecuta el MISMO Ejecutor que
    las acciones del modelo (Política, denegación, aprobación de lanzar_app,
    presupuesto y auditoría). `detectar_y_ejecutar()` ya no ejecuta nada solo.
  · Lo que pide el MODELO va por el Ejecutor (lune_core/acciones.py) con un
    único formato, `<|CALL ["herramienta", {args}]|>`: esquema, Política,
    presupuesto, aprobación humana y auditoría. Los handlers que usa el Ejecutor
    viven aquí (`handlers`, firma `fn(args: dict, ctx) -> str | ToolResult`) y
    cada modo crea el suyo con `crear_ejecutor(...)`.

El formato antiguo (`ABRIR_URL:`, `ABRIR_BUSQUEDA:`, `TOOL:`) ya NO se ejecuta:
se saltaba la neutralización de marcadores y un título de ventana o un chat de
Minecraft podían disparar acciones (crítica d). `parsear_respuesta_ia()` solo lo
borra del texto y devuelve la lista de acciones vacía (se mantiene la firma para
no romper a quien la llame).

`ejecutar()` es una llamada DIRECTA, sin Política ni aprobación: sirve para
pruebas y para acciones que el propio usuario pidió en la interfaz. Nunca debe
recibir texto del modelo; para eso está el Ejecutor.

Herramientas de siempre:
  - abrir_url      Abre un sitio web (solo http/https)
  - buscar_web     Búsqueda en Google o YouTube
  - lanzar_app     Lanza aplicaciones del PC (con alias automáticos)
  - sistema_info   Muestra CPU y RAM
Las demás (cambiar_voz, alarmas, mascota…) se enchufan con
`registrar_handler(nombre, fn)` desde el paquete de cada función.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import weakref
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

# Intentar importar dependencias opcionales
try:
    import psutil
except ImportError:
    psutil = None

from lune_core.herramientas import ALIAS_APPS, resolver_app

RAIZ = Path(__file__).resolve().parent.parent
# Auditoría de las acciones del modelo (lune_core/herramientas.Sesion).
AUDIT_POR_DEFECTO = RAIZ / "logs" / "audit.jsonl"
_DEFECTO = object()


# ── Saneamiento ────────────────────────────────────────────────────────────────
# Estas herramientas se disparan con texto que puede venir del MODELO, no solo
# del usuario. Un personaje de roleplay descarrilado podría pedir lanzar
# `x" & del /q ...`, así que nada de shells ni concatenar cadenas en comandos:
# se valida primero y se ejecuta con lista de argumentos.

# Solo letras, números, espacios y unos pocos signos inofensivos.
_APP_VALIDA = re.compile(r"^[\w .\-()]{1,60}$", re.UNICODE)
_ESQUEMAS_PERMITIDOS = ("http", "https")

# Lanzar apps con `cmd /c start` abría una consola negra que parpadeaba.
_SIN_CONSOLA = {}
if os.name == "nt":
    _SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def _nombre_app_seguro(nombre: str) -> Optional[str]:
    """Devuelve el nombre saneado, o None si trae algo sospechoso."""
    nombre = (nombre or "").strip().strip('"').strip("'")
    if not nombre or not _APP_VALIDA.match(nombre):
        return None
    # Ni rutas ni escapes: solo el nombre del ejecutable.
    if any(c in nombre for c in ("/", "\\", "..")):
        return None
    return nombre


def _url_segura(url: str) -> Optional[str]:
    """
    Normaliza y valida una URL. Rechaza esquemas peligrosos como `file:`,
    `javascript:` o `data:`, que webbrowser abriría sin rechistar.
    """
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        return None

    # Si YA trae un esquema, tiene que ser http(s). Comprobarlo antes de añadir
    # el prefijo es lo que evita que «javascript:alert(1)» se convierta en
    # «https://javascript:alert(1)» y pase el filtro por la puerta de atrás.
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", url)
    if m:
        if m.group(1).lower() not in _ESQUEMAS_PERMITIDOS:
            return None
    else:
        url = "https://" + url

    try:
        partes = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if partes.scheme.lower() not in _ESQUEMAS_PERMITIDOS or not partes.netloc:
        return None
    return url


def ctx_acciones(ai_manager: Any = None, proveedor: str = "", modo: str = "") -> dict:
    """
    ctx para el Ejecutor: {modo, proveedor, url, ai}. El modo filtra herramientas;
    proveedor y URL deciden si algo sale del PC (p. ej. la captura de pantalla
    con un proveedor en la nube pide permiso). `ai` (el AIManager) le sirve al
    Ejecutor para saber, AL EJECUTAR, si el contexto del turno llevaba texto de
    terceros (`ai.contexto_contaminado(proveedor)`): entonces todo lo que no sea
    de lectura pide permiso.
    """
    url = ""
    try:
        p = (getattr(ai_manager, "providers", None) or {}).get(proveedor)
        url = str(getattr(p, "base_url", "") or getattr(p, "url", "") or "")
    except Exception:
        url = ""
    return {"modo": modo or None, "proveedor": proveedor or "", "url": url, "ai": ai_manager}


class ToolResult:
    """Contenedor para el resultado de ejecutar una herramienta."""
    def __init__(self, ok: bool, mensaje: str, datos: dict = None):
        self.ok = ok
        self.mensaje = mensaje
        self.datos = datos or {}


def _a_tool_result(salida: Any) -> ToolResult:
    """Lo que devuelve un handler (str, None, ToolResult, dict o tupla) → ToolResult."""
    if isinstance(salida, ToolResult):
        return salida
    if salida is None:
        return ToolResult(True, "Hecho.")
    if isinstance(salida, str):
        return ToolResult(True, salida)
    if isinstance(salida, Mapping) and "ok" in salida:
        return ToolResult(bool(salida.get("ok")), str(salida.get("mensaje", "") or ""))
    if isinstance(salida, tuple) and len(salida) == 2 and isinstance(salida[0], bool):
        return ToolResult(salida[0], str(salida[1]))
    if hasattr(salida, "ok") and hasattr(salida, "mensaje"):
        return ToolResult(bool(salida.ok), str(salida.mensaje))
    return ToolResult(True, str(salida))


class ToolManager:
    def __init__(self):
        # Comandos de texto (camino del usuario y de `ejecutar` con un str).
        self._tools = {
            "buscar_web": self._cmd_buscar_web,
            "abrir_url": self._cmd_abrir_url,
            "lanzar_app": self._cmd_lanzar_app,
            "sistema_info": self._cmd_sistema_info,
        }
        # Handlers con la firma del Ejecutor: fn(args: dict, ctx) -> str | ToolResult.
        self._lock = threading.RLock()
        self._handlers: Dict[str, Callable[[dict, Any], Any]] = {
            "sistema_info": self._h_sistema_info,
            "buscar_web": self._h_buscar_web,
            "abrir_url": self._h_abrir_url,
            "lanzar_app": self._h_lanzar_app,
        }
        # Ejecutores creados con crear_ejecutor(): reciben los handlers que se
        # registren después (la mascota, las alarmas… llegan más tarde).
        self._ejecutores: "weakref.WeakSet" = weakref.WeakSet()

    # Atajos de «abre X» que no necesitan IA.
    ATAJOS_WEB = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "facebook": "https://www.facebook.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "whatsapp": "https://web.whatsapp.com",
        "instagram": "https://www.instagram.com",
        "github": "https://github.com",
        "chatgpt": "https://chatgpt.com",
        "tiktok": "https://www.tiktok.com",
        "twitch": "https://www.twitch.tv",
        "netflix": "https://www.netflix.com",
        "reddit": "https://www.reddit.com",
        "amazon": "https://www.amazon.com",
        "spotify": "https://open.spotify.com",
    }

    # «baila», «¡a bailar!», «para de bailar»: el baile de la mascota sin IA (cortes 5/6).
    # Solo la ORDEN sola (con relleno como «oye Lune» o «porfa»): nunca preguntas («¿baila?»,
    # «¿sabes bailar?»), negaciones («no bailes») ni frases sobre bailar («bailas muy bien»,
    # «mi hermana baila salsa»): eso lo decide el modelo con su herramienta.
    _RELLENO_BAILE = r"(?:(?:oye|oiga|hey|ey|eh|venga|anda|vamos|porfa|porfis|por\s+favor|lune)[\s,!¡.…]+)*"
    _FIN_BAILE = r"(?:[\s,]+(?:lune|porfa|porfis|por\s+favor))*[\s!¡.…]*"
    _BAILA = re.compile(rf"[¡!\s]*{_RELLENO_BAILE}(?:baila|ponte\s+a\s+bailar|bailemos|a\s+bailar){_FIN_BAILE}")
    _PARA_BAILE = re.compile(rf"[¡!\s]*{_RELLENO_BAILE}(?:ya\s+)?(?:para|deja)\s+de\s+bailar{_FIN_BAILE}")

    @classmethod
    def _detectar_pedido(cls, texto: str) -> Optional[Tuple[str, dict]]:
        """(herramienta, args) de un comando escrito por la persona, o None."""
        texto = str(texto or "").strip()
        texto_lower = texto.lower()
        if not texto_lower:
            return None

        # 0. Alarmas y temporizadores con hora o duración explícitas («avísame en 10
        #    minutos», «pon una alarma a las 7»): nucleo/alarmas_nl. Sin hora ni duración
        #    («recuerda que mañana tengo cita») sigue su camino (memoria, IA).
        try:
            from nucleo import alarmas_nl
            p = alarmas_nl.detectar(texto)
        except Exception:
            p = None
        if p:
            return p
        # 0b. Baile de la mascota.
        if cls._BAILA.fullmatch(texto_lower):
            return "mascota_bailar", {}
        if cls._PARA_BAILE.fullmatch(texto_lower):
            return "parar_baile", {}

        # 1. Búsqueda web (YouTube o Google), respetando mayúsculas de la consulta.
        if texto_lower.startswith(("busca ", "buscar ", "investiga ")):
            if "youtube" in texto_lower:
                m = re.search(r"^(busca en youtube|buscar en youtube|busca videos de|busca|buscar)\s+(.+)",
                              texto, flags=re.IGNORECASE)
                if m:
                    return "buscar_web", {"consulta": m.group(2).strip(), "sitio": "youtube"}
            else:
                m = re.search(r"^(busca en google|buscar en google|investiga sobre|investiga|buscar|busca)\s+(.+)",
                              texto, flags=re.IGNORECASE)
                if m:
                    return "buscar_web", {"consulta": m.group(2).strip(), "sitio": "google"}

        # 2. Lanzar una app local.
        if texto_lower.startswith(("abre la app ", "lanza el programa ", "lanza ", "abre el programa ")):
            m = re.search(r"^(abre la app|lanza el programa|lanza|abre el programa)\s+(.+)",
                          texto, flags=re.IGNORECASE)
            if m:
                return "lanzar_app", {"app": m.group(2).strip()}

        # 3. Abrir una web: atajo conocido o dominio/enlace (sin espacios).
        if texto_lower.startswith(("ve a ", "abre la web ", "abre el sitio ", "abre ")):
            m = re.search(r"^(ve a la web de|ve a|abre la web|abre el sitio|abre)\s+(.+)",
                          texto, flags=re.IGNORECASE)
            if m:
                objetivo = m.group(2).strip()
                objetivo_lower = objetivo.lower()
                if objetivo_lower in cls.ATAJOS_WEB:
                    return "abrir_url", {"url": cls.ATAJOS_WEB[objetivo_lower]}
                if "." in objetivo_lower and " " not in objetivo_lower:
                    return "abrir_url", {"url": objetivo}       # mayúsculas de la URL intactas

        # 4. Info del sistema.
        if any(k in texto_lower for k in ("info del sistema", "estado del pc", "cuanta ram")):
            return "sistema_info", {}
        return None

    def detectar_llamadas(self, texto: str) -> list:
        """
        Lo que la persona pide con sus palabras («abre youtube», «lanza paint»,
        «busca gatos», «estado del pc», «avísame en 10 minutos», «pon una alarma a
        las 7», «baila») como `lune_core.acciones.Llamada`s, SIN
        ejecutar nada. Van al Ejecutor como cualquier otra acción (Política,
        denegación, presupuesto, aprobación de lanzar_app y auditoría):

            llamadas = tools.detectar_llamadas(texto)
            if llamadas:
                acciones.ejecutar(llamadas, "usuario", ctx)   # AccionesQt / Ejecutor

        Lista vacía si el texto no es un comando. Las llamadas llevan
        origen 'usuario' y `directa=True` (las escribió la persona, no el modelo:
        el historial contaminado no las afecta). Si los argumentos no cumplen el
        esquema, la llamada viene con `error` y el Ejecutor lo explica.
        """
        from lune_core import catalogo_herramientas as cat
        from lune_core.acciones import INVALIDA, USUARIO, Llamada
        pedido = self._detectar_pedido(texto)
        if pedido is None:
            return []
        nombre, crudo = pedido
        ll = Llamada(nombre, crudo={"texto": str(texto or "")[:200]}, origen=USUARIO, directa=True)
        h = cat.obtener(nombre)
        try:
            ll.args, ignorados = cat.validar(crudo, h.args if h is not None else {})
            ll.ignorados = tuple(ignorados)
        except cat.ArgumentosInvalidos as e:
            ll.args = dict(crudo)
            ll.error, ll.motivo = str(e), INVALIDA
        return [ll]

    def detectar_y_ejecutar(self, texto: str, ejecutor: Any = None, ctx: Any = None,
                            al_resultado: Optional[Callable] = None) -> Optional[ToolResult]:
        """
        OBSOLETO (revisión de seguridad S5): antes lanzaba apps y abría URLs por su
        cuenta, sin Política, denegación ni aprobación, con cualquier texto (también
        la transcripción del modo llamada). Ya NO ejecuta nada por sí mismo:

          · sin `ejecutor` → None (no hace nada; el texto sigue su camino al modelo);
          · con `ejecutor` (AccionesQt o lune_core.acciones.Ejecutor) → le pasa
            `detectar_llamadas(texto)` con origen 'usuario' y devuelve un
            ToolResult(True, …, {"llamadas": [...]}) para decir «ya está atendido»;
            los resultados de verdad llegan por el canal del ejecutor
            (AccionesQt.resultado / `al_resultado`).

        Usa `detectar_llamadas` + el Ejecutor directamente.
        """
        if ejecutor is None:
            return None
        llamadas = self.detectar_llamadas(texto)
        if not llamadas:
            return None
        from lune_core.acciones import USUARIO
        ejecutar = getattr(ejecutor, "ejecutar", None)
        if callable(ejecutar) and not hasattr(ejecutor, "ejecutar_llamadas"):
            ejecutar(llamadas, USUARIO, ctx)                                 # AccionesQt
        elif callable(getattr(ejecutor, "ejecutar_llamadas", None)):
            ejecutor.ejecutar_llamadas(llamadas, USUARIO, ctx, al_resultado)  # Ejecutor
        else:
            return None
        return ToolResult(True, f"Pedido: {llamadas[0].herramienta}", {"llamadas": llamadas})

    def parsear_respuesta_ia(self, respuesta: str) -> Tuple[str, List[Dict]]:
        """
        Compatibilidad: devuelve (texto_sin_marcas, []). El formato antiguo
        (`ABRIR_URL:`, `ABRIR_BUSQUEDA:`, `TOOL:`) y las marcas `<|CALL …|>` se
        quitan del texto, pero NADA se ejecuta desde aquí: las acciones del
        modelo las procesa el Ejecutor (`crear_ejecutor().procesar(...)`).
        """
        from lune_core.acciones import limpiar_texto
        return limpiar_texto(respuesta or ""), []

    def ejecutar(self, herramienta: str, **kwargs) -> ToolResult:
        """
        Ejecuta una herramienta DIRECTAMENTE (sin Política ni aprobación).

          ejecutar("abrir_url", args="https://…")          texto: comando de siempre
          ejecutar("abrir_url", args={"url": "https://…"}) dict: handler del Ejecutor
          ejecutar("cambiar_voz", voz="es-AR-ElenaNeural") claves sueltas = args

        Primero busca en las herramientas propias (con texto) y luego en los
        handlers registrados; los argumentos de un handler se validan contra el
        esquema del catálogo. Nunca con texto del modelo: eso va por el Ejecutor.
        """
        args = kwargs.get("args", None)
        ctx = kwargs.get("ctx")
        if herramienta in self._tools and not isinstance(args, Mapping):
            try:
                func = self._tools[herramienta]
                return func(args) if args else func()
            except Exception as e:
                return ToolResult(False, f"Error en {herramienta}: {str(e)}")

        with self._lock:
            fn = self._handlers.get(herramienta)
        if fn is None:
            return ToolResult(False, f"Herramienta '{herramienta}' no disponible.")
        if args is None:
            args = {k: v for k, v in kwargs.items() if k not in ("args", "ctx")}
        if not isinstance(args, Mapping):
            return ToolResult(False, f"Argumentos no válidos para «{herramienta}».")
        try:
            from lune_core import catalogo_herramientas as cat
            h = cat.obtener(herramienta)
            if h is not None:
                args, _ = cat.validar(args, h.args)
        except Exception as e:
            return ToolResult(False, f"Argumentos no válidos para «{herramienta}»: {e}")
        try:
            return _a_tool_result(fn(dict(args), ctx))
        except Exception as e:
            return ToolResult(False, f"Error en {herramienta}: {str(e)}")

    # ── Handlers para el Ejecutor ──────────────────────────────────────────────

    @property
    def handlers(self) -> Dict[str, Callable[[dict, Any], Any]]:
        """Copia de {nombre: fn(args, ctx)} (las cuatro de siempre + las registradas)."""
        with self._lock:
            return dict(self._handlers)

    def tiene_handler(self, nombre: str) -> bool:
        with self._lock:
            return str(nombre) in self._handlers

    def registrar_handler(self, nombre: str, fn: Callable[[dict, Any], Any]) -> None:
        """
        Enchufa el handler de una herramienta del catálogo (firma
        `fn(args: dict, ctx) -> str | ToolResult`; lanzar = fallo). Llega también
        a los Ejecutores ya creados con `crear_ejecutor`.
        """
        if not callable(fn):
            raise TypeError(f"el handler de «{nombre}» tiene que ser una función")
        nombre = str(nombre)
        with self._lock:
            self._handlers[nombre] = fn
            ejecutores = list(self._ejecutores)
        for ej in ejecutores:
            try:
                ej.registrar_handler(nombre, fn)
            except Exception:
                pass

    def quitar_handler(self, nombre: str) -> None:
        nombre = str(nombre)
        with self._lock:
            self._handlers.pop(nombre, None)
            ejecutores = list(self._ejecutores)
        for ej in ejecutores:
            try:
                ej.quitar_handler(nombre)
            except Exception:
                pass

    def disponibles(self, modo: Optional[str] = None) -> List[str]:
        """Herramientas con handler, registradas y válidas en `modo` (orden del catálogo)."""
        from lune_core import catalogo_herramientas as cat
        from lune_core.herramientas import registro_por_defecto
        return cat.disponibles_en(modo, self.handlers, registro_por_defecto())

    def vincular(self, ejecutor) -> None:
        """Mantiene los handlers de `ejecutor` al día con los de este ToolManager."""
        with self._lock:
            self._ejecutores.add(ejecutor)
            actuales = dict(self._handlers)
        for nombre, fn in actuales.items():
            ejecutor.registrar_handler(nombre, fn)

    def crear_ejecutor(self, pedir_aprobacion=None, *, despachar=None, cerrar_aprobacion=None,
                       programar=None, audit_path: Any = _DEFECTO, registro=None, **kw):
        """
        Ejecutor (lune_core/acciones.py) con el registro completo, una Sesion con
        auditoría en logs/audit.jsonl (`audit_path=None` para no escribirla) y
        los handlers de este ToolManager, que se mantienen al día.

        pedir_aprobacion(pendiente, responder)  enseña la pregunta a un humano
        despachar(fn)                           lleva lo de tras una aprobación a su hilo
        cerrar_aprobacion(id)                   cierra la pregunta al caducar o cancelarse
        """
        from lune_core.acciones import Ejecutor
        from lune_core.herramientas import Sesion, registro_por_defecto
        reg = registro if registro is not None else registro_por_defecto()
        ruta = AUDIT_POR_DEFECTO if audit_path is _DEFECTO else audit_path
        sesion = Sesion(reg, audit_path=ruta or None)
        opciones = dict(kw)
        if programar is not None:
            opciones["programar"] = programar
        ej = Ejecutor(reg, sesion, handlers=self.handlers, pedir_aprobacion=pedir_aprobacion,
                      despachar=despachar, cerrar_aprobacion=cerrar_aprobacion, **opciones)
        self.vincular(ej)
        return ej

    def conectar_voz(self, config=None, voice=None) -> None:
        """Enchufa `cambiar_voz` (servicios/voces.py) con la config y el VoiceEngine de este modo."""
        def cambiar_voz(args: dict, ctx: Any = None) -> str:
            from servicios import voces
            return voces.herramienta_cambiar_voz(args, {"config": config, "voice": voice})
        self.registrar_handler("cambiar_voz", cambiar_voz)

    def _h_sistema_info(self, args: Optional[dict] = None, ctx: Any = None) -> ToolResult:
        return self._cmd_sistema_info()

    def _h_buscar_web(self, args: Optional[dict] = None, ctx: Any = None) -> ToolResult:
        args = args or {}
        consulta = str(args.get("consulta") or "").strip()
        if not consulta:
            return ToolResult(False, "No me dijiste qué buscar.")
        if str(args.get("sitio") or "google").strip().lower() == "youtube":
            return self._cmd_buscar_youtube(consulta)
        return self._cmd_buscar_web(consulta)

    def _h_abrir_url(self, args: Optional[dict] = None, ctx: Any = None) -> ToolResult:
        return self._cmd_abrir_url(str((args or {}).get("url") or ""))

    def _h_lanzar_app(self, args: Optional[dict] = None, ctx: Any = None) -> ToolResult:
        return self._cmd_lanzar_app(str((args or {}).get("app") or ""))

    # ── Implementación de Herramientas ────────────────────────────────────────

    def _cmd_buscar_web(self, query: str) -> ToolResult:
        """Busca en Google."""
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return ToolResult(True, f"Buscando en Google: '{query}'")

    def _cmd_buscar_youtube(self, query: str) -> ToolResult:
        """Busca en YouTube."""
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return ToolResult(True, f"Buscando en YouTube: '{query}'")

    def _cmd_abrir_url(self, url: str) -> ToolResult:
        """Abre una URL, siempre que sea http(s)."""
        url_final = _url_segura(url)
        if not url_final:
            return ToolResult(False, f"No abro esa dirección: «{url}» no es una URL http(s) válida.")

        webbrowser.open(url_final)

        # Nombre de la página solo para mostrarlo bonito en el chat
        try:
            host = urllib.parse.urlparse(url_final).netloc
            dominio = host.replace("www.", "").split(".")[0].capitalize() or "enlace"
        except Exception:
            dominio = "enlace"

        return ToolResult(True, f"Abriendo {dominio}...")

    # Alias técnicos para programas de Windows: los mismos que usa la Política
    # (lune_core/herramientas.py), que deniega mirando el programa ya traducido.
    ALIAS_APPS = ALIAS_APPS

    def _cmd_lanzar_app(self, nombre: str) -> ToolResult:
        """
        Lanza una aplicación local.

        Nunca se pasa por un shell ni se concatena el nombre en una cadena de
        comando: primero se sanea y luego se ejecuta con lista de argumentos.
        """
        limpio = _nombre_app_seguro(nombre)
        if not limpio:
            return ToolResult(False, f"No puedo lanzar «{nombre}»: el nombre no es válido.")

        app_exe = resolver_app(limpio)

        try:
            ruta = shutil.which(app_exe)
            if ruta:
                subprocess.Popen([ruta], **_SIN_CONSOLA)
            elif os.name == "nt":
                # Sin shell=True. `start` resuelve las App Paths del registro
                # (Office y demás), y el nombre ya viene saneado.
                subprocess.Popen(["cmd", "/c", "start", "", app_exe], shell=False, **_SIN_CONSOLA)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", app_exe])
            else:
                return ToolResult(False, f"No encontré «{app_exe}» en el PATH.")
            return ToolResult(True, f"Lanzando aplicación: {limpio}")
        except FileNotFoundError:
            return ToolResult(False, f"No encontré «{app_exe}» en este equipo.")
        except Exception as e:
            return ToolResult(False, f"No se pudo abrir {limpio}: {e}")

    def _cmd_sistema_info(self, *args) -> ToolResult:
        """Información de hardware."""
        if not psutil: return ToolResult(False, "psutil no instalado.")
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        return ToolResult(True, f"**Estado del PC**: CPU {cpu}% | RAM {ram}%")

    def listar_disponibles(self) -> str:
        """Las herramientas que el modelo puede usar aquí (registradas y con handler)."""
        from lune_core import catalogo_herramientas as cat
        from lune_core.herramientas import Riesgo, registro_por_defecto
        reg = registro_por_defecto()
        lineas = ["**Herramientas activas:**"]
        for nombre in cat.disponibles_en(None, self.handlers, reg):
            h, d = cat.obtener(nombre), reg.get(nombre)
            permiso = (" (pide permiso)" if d is not None and
                       (d.requiere_aprobacion or d.riesgo == Riesgo.DESTRUCTIVO) else "")
            lineas.append(f"  · {h.descripcion}{permiso}")
        if len(lineas) == 1:
            lineas.append("  (ninguna)")
        return "\n".join(lineas)
