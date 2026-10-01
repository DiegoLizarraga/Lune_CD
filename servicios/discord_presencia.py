"""
servicios/discord_presencia.py — Qué publica Lune en Discord y cuándo (Rich Presence).

QUÉ SE PUBLICA (y nada más)
---------------------------
- `details`: «Lune CD · Escritorio · 3D | Escritorio · animación | Escritorio · sprites |
  Ventana | Terminal».
- `state`: un texto FIJO de `ESTADOS`, el primero que se cumple por prioridad
  (alarma, pantalla grande, salvapantallas, llamada, arrastrando, bailando,
  comiendo, siesta sentada, durmiendo, sentada en la barra / en una ventana,
  pensando, hablando, en el escritorio, charlando, en la terminal).
- Con un juego delante: actividad **null** (nada; ni siquiera «jugando»).
- `timestamps.start` = cuándo arrancó el proceso; `assets`: imagen grande «lune»
  con el texto «Lune CD» (+ « · <modelo VRM>» solo con `discord.mostrar_modelo`)
  y la pequeña del modo (vrm, animado, sprites, web, nativo o patata).
- Un botón «Conoce a Lune» solo si `discord.boton_url` es una https válida.
- `pid` = el de este proceso: si Lune muere, Discord borra la actividad solo.

NUNCA se publica: el texto del chat, títulos de ventanas, nombres de programas
(ni la app de música ni el juego), el nombre del personaje, el texto de las
alarmas ni el usuario del PC. `construir_actividad` solo mira la CLAVE del
estado y la config: aunque la foto del estado traiga esas cosas, no hay camino
por el que lleguen al JSON.

CUÁNDO
------
Todo pasa en el hilo «LuneDiscordRPC» (nunca en el de Qt):
- Apagado, o encendido sin Application ID (D1): no hay hilo (o duerme en un
  Event sin sondear). En cuanto aparece el ID en la config y alguien llama a
  `actualizar()`/`habilitar()` (la tarjeta, un cambio de estado), conecta.
- Sin Discord abierto: reintenta a los 15 s, 30 s y luego cada 60 s. Si Discord
  dice que el Application ID no vale (cierre 4000), no reintenta hasta que
  cambie el ID.
- Mutex `Local\\LuneDiscordRPC`: si la app o patata ya publican, esta instancia
  no conecta y dice «otra Lune ya publica»; lo vuelve a mirar cada 5 s (mirar el
  mutex no cuesta nada, y tras un cambio de interfaz el hilo de la ventana vieja
  lo suelta en cuanto borra su actividad).
- Conectado: `atender()` (PeekNamedPipe) cada 100 ms y la foto del estado cada
  1 s o al instante con `actualizar()`. Antirrebote de 1.5 s, al menos 4 s entre
  envíos (Discord admite 5 cada 20 s), coalescencia (solo sale el último) y
  nada de reenviar lo idéntico. Pasar a juego (null) se salta el antirrebote.
- `habilitar(False)` y `cerrar()`: actividad null (como mucho 1 s) y fuera.

    p = Presencia(config, estado_fn)      # estado_fn() → dict (ver abajo)
    p.on_estado = lambda e: ...           # {activo, conectado, usuario, error, publicando, sin_id}
    p.habilitar(True); p.actualizar(); p.cerrar()

`estado_fn()` devuelve un dict con los campos de nucleo.estado_asistente.EstadoAsistente
(juego, alarma, grande, sentada…) más `modo` ("normal" web · "br" nativa ·
"patata") y, opcional, `modelo` (nombre del VRM; solo se usa con mostrar_modelo).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import PurePath
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

from servicios.discord_ipc import CODIGO_ID_NO_VALIDO, ID_OK, ClienteIPC, TXT_ID_NO_VALIDO
from servicios.mutex_win import MutexNombrado

_log = logging.getLogger("lune.discord")

NOMBRE_MUTEX = "Local\\LuneDiscordRPC"
MAX_BYTES = 128
MAX_URL = 512
ETIQUETA_BOTON = "Conoce a Lune"

ANTIRREBOTE_S = 1.5
INTERVALO_MIN_S = 4.0
COALESCER_MAX_S = 10.0          # un estado que no para de cambiar sale igual a los 10 s
REINTENTOS_S = (15.0, 30.0, 60.0)
REINTENTO_OTRA_LUNE_S = 5.0     # el mutex lo tiene otra Lune (o el hilo de la ventana de antes)
TIC_S = 0.1                     # PeekNamedPipe conectado
SONDEO_ESTADO_S = 1.0           # la foto del estado, por si nadie llama a actualizar()
TIMEOUT_CONECTAR_S = 5.0

TXT_OTRA_LUNE = "Otra Lune ya publica en Discord."
TXT_RECHAZADO = "Discord rechazó el Application ID."


def motivo(estado: Any) -> str:
    """Por qué no está conectada, en una frase con el siguiente paso ("" si lo está). Lo
    enseñan el «Reconectar» de Ajustes (web y nativa) y el estado de la tarjeta."""
    from servicios import discord_ipc as ipc
    e = estado if isinstance(estado, dict) else {}
    if e.get("conectado"):
        return ""
    if not e.get("activo"):
        return "La presencia está apagada: enciéndela primero."
    if e.get("sin_id"):
        return "Falta el Application ID: crea una app en discord.com/developers y pega aquí su ID."
    error = str(e.get("error") or "").strip()
    if error == TXT_OTRA_LUNE:
        return ("Otra Lune ya publica en Discord (otra ventana o la terminal): ciérrala o apágale "
                "Discord allí y vuelvo a probar sola.")
    if error in (TXT_RECHAZADO, TXT_ID_NO_VALIDO):
        return ("Discord no acepta ese Application ID: cópialo otra vez de discord.com/developers (tu "
                "app, «Application ID»).")
    if error == ipc.TXT_SIN_DISCORD:
        return "Discord no está abierto: abre la app de escritorio de Discord (la web no vale) y pulsa Reconectar."
    if error == ipc.TXT_NO_RESPONDE:
        return "Discord no responde: espera a que acabe de abrir (o reinícialo) y pulsa Reconectar."
    if error == ipc.TXT_CORTADA:
        return "Discord cerró la conexión: vuelvo a intentarlo yo sola en un momento."
    if error:
        return f"Sin conectar: {error}"
    return "Todavía no conecto: espero a que Discord conteste."

# (clave, texto fijo) en orden de prioridad. El juego no está: con juego, null.
ESTADOS: Tuple[Tuple[str, str], ...] = (
    ("alarma", "Con una alarma sonando"),
    ("grande", "En pantalla grande"),
    ("salvapantallas", "Durmiendo en el salvapantallas"),
    ("llamada", "En una llamada"),
    ("arrastrando", "Paseando por la pantalla"),
    ("bailando", "Bailando ♪"),
    ("comiendo", "Merendando"),
    ("siesta", "Echando una siesta sentada"),
    ("durmiendo", "Durmiendo (-_-) zzZ"),
    ("sentada_barra", "Sentada en la barra de tareas"),
    ("sentada_ventana", "Sentada en una ventana"),
    ("pensando", "Pensando…"),
    ("hablando", "Hablando"),
    ("escritorio", "En el escritorio"),
    ("charlando", "Charlando"),
    ("terminal", "En la terminal"),
)
_TEXTOS: Dict[str, str] = dict(ESTADOS)

# Formas de la asistente en escritorio (render del BusEstado) → (texto de `details`,
# imagen pequeña). Dice dónde está Lune (como «Ventana» y «Terminal») y con qué forma.
_ASISTENTES: Dict[str, Tuple[str, str]] = {
    "vrm": ("Escritorio · 3D", "vrm"),
    "animado": ("Escritorio · animación", "animado"),
    "sprites": ("Escritorio · sprites", "sprites"),
    "carita": ("Escritorio · sprites", "sprites"),
}
_PATATA = frozenset({"patata", "terminal"})
_NATIVA = frozenset({"br", "nativo", "nativa"})


def _campo(est: Any, nombre: str, defecto: Any = None) -> Any:
    if isinstance(est, dict):
        return est.get(nombre, defecto)
    return getattr(est, nombre, defecto)


def es_patata(modo: str) -> bool:
    return str(modo or "").strip().lower() in _PATATA


def render_visible(est: Any) -> str:
    """El render de la asistente en escritorio si está A LA VISTA ("" si no hay)."""
    r = str(_campo(est, "render", "") or "").strip().lower()
    if r not in _ASISTENTES:
        return ""
    return r if _campo(est, "visible", True) else ""


def clave_estado(est: Any, *, modo: str, render: str) -> Optional[str]:
    """La clave de `ESTADOS` que toca (o None = actividad null, con un juego delante).

    `render`: el de la asistente en escritorio a la vista ("" = no está fuera).
    """
    if _campo(est, "juego"):
        return None
    for campo in ("alarma", "grande", "salvapantallas", "llamada", "arrastrando"):
        if _campo(est, campo):
            return campo
    if _campo(est, "bailando"):
        return "bailando"
    if _campo(est, "comiendo"):
        return "comiendo"
    sentada = str(_campo(est, "sentada", "") or "")
    if _campo(est, "durmiendo"):
        return "siesta" if sentada else "durmiendo"
    if sentada:
        return "sentada_barra" if sentada == "barra" else "sentada_ventana"
    if _campo(est, "pensando"):
        return "pensando"
    if _campo(est, "hablando"):
        return "hablando"
    if es_patata(modo):
        return "terminal"
    if str(render or "").strip().lower() in _ASISTENTES:
        return "escritorio"
    return "charlando"


def cabe(texto: Any, n_bytes: int) -> str:
    """Recorta `texto` a `n_bytes` de UTF-8 sin partir caracteres. Discord pide
    al menos 2 caracteres: lo más corto se rellena con un blanco braille."""
    t = str(texto or "")
    n = max(2, int(n_bytes))
    b = t.encode("utf-8")
    if len(b) > n:
        t = b[:n].decode("utf-8", errors="ignore")
    while len(t) < 2:
        relleno = t + "⠀"
        if len(relleno.encode("utf-8")) > n:
            relleno = t + " "
        t = relleno
    return t


def _cfg(config: Any, clave: str, defecto: Any = None) -> Any:
    try:
        if isinstance(config, dict):
            return (config.get("discord") or {}).get(clave, defecto)
        return config.get("discord", clave, defecto)
    except Exception:
        return defecto


def client_id(config: Any) -> str:
    return str(_cfg(config, "client_id", "") or "").strip()


def url_boton(url: Any) -> str:
    """La URL del botón si es https válida y cabe (≤512 B); si no, ""."""
    u = str(url or "").strip()
    if not u or len(u.encode("utf-8")) > MAX_URL:
        return ""
    if any(c.isspace() or ord(c) < 32 or c in "<>\"'`\\" for c in u):
        return ""
    try:
        partes = urlsplit(u)
    except ValueError:
        return ""
    if partes.scheme != "https" or not partes.hostname or "." not in partes.hostname:
        return ""
    return u


def _nombre_modelo(modelo: Any) -> str:
    """Nombre del modelo VRM, sin ruta ni extensión ni caracteres de control."""
    m = str(modelo or "").strip()
    if not m:
        return ""
    try:
        p = PurePath(m.replace("\\", "/"))
        m = p.stem if p.suffix.lower() in (".vrm", ".glb") else p.name
    except Exception:
        pass
    return re.sub(r"[\x00-\x1f\x7f]", "", m).strip()


def detalle(modo: str, render: str) -> Tuple[str, str]:
    """(texto de `details` sin el «Lune CD · », imagen pequeña)."""
    r = str(render or "").strip().lower()
    if es_patata(modo):
        return "Terminal", "patata"
    if r in _ASISTENTES:
        return _ASISTENTES[r]
    return "Ventana", ("nativo" if str(modo or "").strip().lower() in _NATIVA else "web")


def construir_actividad(clave: Optional[str], *, modo: str, render: str, inicio_ms: int,
                        config: Any, modelo: str = "") -> Optional[dict]:
    """La actividad para SET_ACTIVITY (None = null). Solo textos fijos y la config."""
    if clave is None:
        return None
    texto = _TEXTOS.get(clave, _TEXTOS["charlando"])
    sub, pequena = detalle(modo, render)
    grande = "Lune CD"
    nombre = _nombre_modelo(modelo)
    if nombre and bool(_cfg(config, "mostrar_modelo", False)) and str(render or "").lower() == "vrm":
        grande = f"Lune CD · {nombre}"
    actividad: Dict[str, Any] = {
        "details": cabe(f"Lune CD · {sub}", MAX_BYTES),
        "state": cabe(texto, MAX_BYTES),
        "timestamps": {"start": int(inicio_ms)},
        "assets": {
            "large_image": "lune",
            "large_text": cabe(grande, MAX_BYTES),
            "small_image": pequena,
            "small_text": cabe(sub, MAX_BYTES),
        },
    }
    url = url_boton(_cfg(config, "boton_url", ""))
    if url:
        actividad["buttons"] = [{"label": ETIQUETA_BOTON, "url": url}]
    return actividad


def actividad_de(foto: Any, *, config: Any, inicio_ms: int) -> Optional[dict]:
    """Foto del estado (dict de estado_fn) → actividad. Atajo de las dos de arriba."""
    modo = str(_campo(foto, "modo", "normal") or "normal")
    render = render_visible(foto)
    clave = clave_estado(foto, modo=modo, render=render)
    return construir_actividad(clave, modo=modo, render=render, inicio_ms=inicio_ms,
                               config=config, modelo=str(_campo(foto, "modelo", "") or ""))


def _inicio_proceso_ms() -> int:
    """Cuándo arrancó ESTE proceso (ms desde 1970), para `timestamps.start`."""
    try:
        import psutil
        return int(psutil.Process(os.getpid()).create_time() * 1000)
    except Exception:
        return int(time.time() * 1000)


_NUNCA = object()        # «todavía no se ha enviado nada» (distinto de None = null)


class Presencia:
    """La presencia de Lune en Discord (ver el docstring del módulo).

    `hilo=False` no crea el hilo: los tests llaman a `paso()` a mano con un reloj falso.
    """

    def __init__(self, config: Any, estado_fn: Callable[[], dict], *,
                 cliente: Callable[..., Any] = ClienteIPC,
                 mutex: Callable[[str], Any] = MutexNombrado,
                 reloj: Callable[[], float] = time.monotonic,
                 esperar: Optional[Callable[[threading.Event, Optional[float]], Any]] = None,
                 hilo: bool = True, pid: Optional[int] = None, inicio_ms: Optional[int] = None):
        self.config = config
        self.estado_fn = estado_fn
        self.on_estado: Optional[Callable[[dict], None]] = None
        self._fab_cliente = cliente
        self._fab_mutex = mutex
        self._reloj = reloj
        self._esperar = esperar if esperar is not None else (lambda ev, t: ev.wait(t))
        self._usar_hilo = bool(hilo)
        self._pid = int(pid) if pid is not None else os.getpid()
        self._inicio_ms = int(inicio_ms) if inicio_ms is not None else _inicio_proceso_ms()

        self._lock = threading.RLock()          # flags y estado
        self._lock_paso = threading.Lock()      # un solo paso() a la vez
        self._evento = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._parar: Optional[threading.Event] = None

        self._habilitada = False
        self._sucio = True
        self._cliente: Any = None
        self._id_conectado = ""
        self._id_rechazado = ""
        self._mutex: Any = None
        self._fallos = 0
        self._proximo_intento = 0.0
        self._enviada: Any = _NUNCA
        self._t_envio = -1e18
        self._deseada: Any = _NUNCA
        self._t_cambio = 0.0
        self._t_pendiente: Optional[float] = None
        self._t_sondeo = -1e18
        self._reintentar_ya = False             # reconectar(): el paso siguiente olvida las esperas
        self._estado: Dict[str, Any] = self._estado_base()

    # ── API (cualquier hilo; no bloquea salvo cerrar) ──────────────────────────
    def habilitar(self, on: bool) -> None:
        with self._lock:
            self._habilitada = bool(on)
            self._sucio = True
        self._despertar()

    def actualizar(self) -> None:
        """El estado de Lune cambió (o la config): mirar ya, sin esperar al sondeo."""
        with self._lock:
            self._sucio = True
        self._despertar()

    def reconectar(self) -> None:
        """«Reconectar» de Ajustes: el próximo paso olvida la espera entre intentos (15 s,
        30 s, 60 s) y un Application ID rechazado (por si lo arreglaste en Discord) y lo
        intenta ya. No bloquea: lo hace el hilo de la presencia."""
        with self._lock:
            self._reintentar_ya = True
            self._sucio = True
        self._despertar()

    def estado(self) -> dict:
        with self._lock:
            e = dict(self._estado)
        if isinstance(e.get("publicando"), dict):
            e["publicando"] = dict(e["publicando"])
        return e

    @property
    def habilitada(self) -> bool:
        return self._habilitada

    def cerrar(self, timeout: float = 1.0) -> None:
        """Actividad null (≤1 s), cierra la conexión y para el hilo. Idempotente;
        después se puede volver a habilitar."""
        with self._lock:
            self._habilitada = False
            hilo, parar = self._hilo, self._parar
            self._hilo, self._parar = None, None
        if parar is not None:
            parar.set()
        self._evento.set()
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(max(0.0, float(timeout)))
        elif hilo is None:
            with self._lock_paso:
                self._finalizar()

    # ── Hilo ──────────────────────────────────────────────────────────────────
    def _necesita_hilo(self) -> bool:
        """Solo con algo que hacer con Discord: encendida y con un Application ID
        bien formado (o una conexión que cerrar)."""
        return (self._habilitada and bool(ID_OK.match(client_id(self.config)))) or self._cliente is not None

    def _despertar(self) -> None:
        if not self._usar_hilo:
            return
        nuevo: Optional[threading.Thread] = None
        with self._lock:
            vivo = self._hilo is not None and self._hilo.is_alive()
            if not vivo and self._necesita_hilo():
                self._parar = threading.Event()
                nuevo = self._hilo = threading.Thread(target=self._bucle, args=(self._parar,),
                                                      name="LuneDiscordRPC", daemon=True)
        if nuevo is not None:
            nuevo.start()
        elif not vivo:
            # Sin hilo ni falta que haga (apagada o sin Application ID): el paso no
            # toca Discord, solo refleja el estado. Barato en cualquier hilo.
            with self._lock_paso:
                self.paso()
        self._evento.set()

    def _bucle(self, parar: threading.Event) -> None:
        try:
            while not parar.is_set():
                self._evento.clear()
                with self._lock_paso:
                    espera = self.paso()
                if parar.is_set():
                    break
                self._esperar(self._evento, espera)
        except Exception:
            _log.exception("discord: el hilo de la presencia falló")
        finally:
            with self._lock_paso:
                with self._lock:
                    # Tras un cerrar() cuyo join venció y un habilitar() rápido, otro
                    # hilo ya lleva la conexión: este no la toca.
                    relevado = self._parar is not None and self._parar is not parar
                if not relevado:
                    self._finalizar()

    # ── Un paso de la máquina ─────────────────────────────────────────────────
    def paso(self) -> Optional[float]:
        """Hace lo que toque ahora. → segundos hasta el próximo paso (None = hasta que
        alguien llame a habilitar/actualizar)."""
        ahora = self._reloj()
        with self._lock:
            habilitada = self._habilitada
            sucio, self._sucio = self._sucio, False
            reintentar, self._reintentar_ya = self._reintentar_ya, False
        if reintentar:                          # reconectar(): sin esperas ni ID rechazado
            self._fallos = 0
            self._proximo_intento = 0.0
            self._id_rechazado = ""
        cid = client_id(self.config)

        if not habilitada:
            self._desconectar(limpiar=True)
            self._soltar_mutex()
            self._fallos = 0
            self._proximo_intento = 0.0
            self._poner_estado(activo=False, conectado=False, usuario="", error="", publicando=None, sin_id=False)
            return None
        if not cid:
            self._desconectar(limpiar=True)
            self._soltar_mutex()
            self._poner_estado(activo=True, conectado=False, usuario="", error="", publicando=None, sin_id=True)
            return None
        if not ID_OK.match(cid):
            self._desconectar(limpiar=True)
            self._soltar_mutex()
            self._poner_estado(activo=True, conectado=False, usuario="", error=TXT_ID_NO_VALIDO,
                               publicando=None, sin_id=False)
            return None
        if cid == self._id_rechazado:
            self._poner_estado(activo=True, conectado=False, usuario="", error=TXT_RECHAZADO,
                               publicando=None, sin_id=False)
            return None
        if self._cliente is not None and self._id_conectado != cid:
            _log.info("discord: cambió el Application ID; vuelvo a conectar")
            self._desconectar(limpiar=True)
            self._fallos = 0
            self._proximo_intento = 0.0

        if self._cliente is None:
            espera = self._intentar_conectar(cid, ahora)
            if espera is not _CONECTADO:
                return espera
            sucio = True

        cliente = self._cliente
        try:
            cliente.atender()
        except Exception:
            _log.debug("discord: atender falló", exc_info=True)
        if not getattr(cliente, "conectado", False):
            return self._caida(cliente, ahora)

        if sucio or ahora - self._t_sondeo >= SONDEO_ESTADO_S:
            self._t_sondeo = ahora
            deseada = self._actividad_deseada()
            if deseada is not _NUNCA and deseada != self._deseada:
                self._deseada = deseada
                self._t_cambio = ahora
                if self._t_pendiente is None:
                    self._t_pendiente = ahora

        if self._deseada is _NUNCA or self._deseada == self._enviada:
            self._t_pendiente = None
            return TIC_S
        urgente = self._deseada is None or self._enviada is _NUNCA
        listo = self._t_envio + INTERVALO_MIN_S
        if not urgente:
            limite = (self._t_pendiente if self._t_pendiente is not None else ahora) + COALESCER_MAX_S
            listo = max(listo, min(self._t_cambio + ANTIRREBOTE_S, limite))
        if ahora + 1e-9 < listo:
            return min(TIC_S, listo - ahora)
        self._enviar(cliente, self._deseada, ahora)
        return TIC_S

    # ── Piezas del paso ───────────────────────────────────────────────────────
    def _intentar_conectar(self, cid: str, ahora: float) -> Any:
        if ahora < self._proximo_intento:
            return self._proximo_intento - ahora
        if self._mutex is None:
            try:
                self._mutex = self._fab_mutex(NOMBRE_MUTEX)
            except Exception:
                _log.exception("discord: no pude crear el mutex")
                self._mutex = None
        dueno = True
        if self._mutex is not None:
            try:
                dueno = bool(self._mutex.adquirir())
            except Exception:
                dueno = False
        if not dueno:
            self._proximo_intento = ahora + REINTENTO_OTRA_LUNE_S
            self._poner_estado(activo=True, conectado=False, usuario="", error=TXT_OTRA_LUNE,
                               publicando=None, sin_id=False)
            return self._proximo_intento - ahora
        try:
            cliente = self._fab_cliente(cid)
            r = cliente.conectar(TIMEOUT_CONECTAR_S, cancelar=self._cancelado)
        except Exception as e:
            _log.debug("discord: conectar falló", exc_info=True)
            cliente, r = None, {"ok": False, "error": f"No pude conectar con Discord ({e}).", "codigo": 0}
        if r.get("ok") and cliente is not None:
            self._cliente = cliente
            self._id_conectado = cid
            self._fallos = 0
            self._proximo_intento = 0.0
            self._enviada = _NUNCA
            self._deseada = _NUNCA
            self._t_pendiente = None
            self._t_envio = -1e18
            _log.info("discord: conectada a Discord")
            self._poner_estado(activo=True, conectado=True, usuario=str(r.get("usuario") or ""),
                               error="", publicando=None, sin_id=False)
            return _CONECTADO
        if int(r.get("codigo") or 0) == CODIGO_ID_NO_VALIDO:
            self._id_rechazado = cid
            _log.warning("discord: Discord rechazó el Application ID; no reintento hasta que cambie")
            self._poner_estado(activo=True, conectado=False, usuario="", error=TXT_RECHAZADO,
                               publicando=None, sin_id=False)
            return None
        self._programar_reintento(ahora)
        self._poner_estado(activo=True, conectado=False, usuario="", error=str(r.get("error") or ""),
                           publicando=None, sin_id=False)
        return self._proximo_intento - ahora

    def _programar_reintento(self, ahora: float) -> None:
        espera = REINTENTOS_S[min(self._fallos, len(REINTENTOS_S) - 1)]
        self._fallos += 1
        self._proximo_intento = ahora + espera

    def _caida(self, cliente: Any, ahora: float) -> Optional[float]:
        """Discord cerró (o se cerró): soltar y reintentar, salvo ID rechazado."""
        codigo = int(getattr(cliente, "codigo_cierre", 0) or 0)
        error = str(getattr(cliente, "error", "") or "")
        self._cliente = None
        self._id_conectado = ""
        self._enviada = _NUNCA
        self._deseada = _NUNCA
        try:
            cliente.cerrar(limpiar=False)
        except Exception:
            pass
        if codigo == CODIGO_ID_NO_VALIDO:
            self._id_rechazado = client_id(self.config)
            self._poner_estado(activo=True, conectado=False, usuario="", error=TXT_RECHAZADO,
                               publicando=None, sin_id=False)
            return None
        _log.info("discord: se cortó la conexión (%s)", error or "sin motivo")
        self._fallos = 0
        self._programar_reintento(ahora)
        self._poner_estado(activo=True, conectado=False, usuario="", error=error,
                           publicando=None, sin_id=False)
        return self._proximo_intento - ahora

    def _actividad_deseada(self) -> Any:
        try:
            foto = self.estado_fn() or {}
        except Exception:
            _log.debug("discord: estado_fn falló", exc_info=True)
            return _NUNCA
        try:
            return actividad_de(foto, config=self.config, inicio_ms=self._inicio_ms)
        except Exception:
            _log.exception("discord: no pude construir la actividad")
            return _NUNCA

    def _enviar(self, cliente: Any, actividad: Optional[dict], ahora: float) -> None:
        try:
            r = cliente.set_activity(actividad, self._pid)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        self._t_envio = ahora
        self._t_pendiente = None
        # Enviada aunque Discord la rechace: reintentar lo mismo fallaría igual.
        # Se vuelve a mandar cuando cambie el estado.
        self._enviada = actividad
        if not getattr(cliente, "conectado", False):
            return                      # el paso siguiente lo trata como caída
        publicando = None if actividad is None else {"details": actividad.get("details", ""),
                                                     "state": actividad.get("state", "")}
        self._poner_estado(activo=True, conectado=True, usuario=self._estado.get("usuario", ""),
                           error="" if r.get("ok") else str(r.get("error") or ""),
                           publicando=publicando, sin_id=False)

    def _desconectar(self, limpiar: bool) -> None:
        cliente, self._cliente = self._cliente, None
        self._id_conectado = ""
        self._enviada = _NUNCA
        self._deseada = _NUNCA
        self._t_pendiente = None
        if cliente is not None:
            try:
                cliente.cerrar(limpiar=limpiar)
            except Exception:
                _log.debug("discord: cerrar falló", exc_info=True)
            _log.info("discord: desconectada")

    def _soltar_mutex(self) -> None:
        m, self._mutex = self._mutex, None
        if m is not None:
            try:
                m.liberar()
            except Exception:
                pass

    def _finalizar(self) -> None:
        self._desconectar(limpiar=True)
        self._soltar_mutex()
        self._poner_estado(activo=False, conectado=False, usuario="", error="", publicando=None, sin_id=False)

    def _cancelado(self) -> bool:
        with self._lock:
            parar = self._parar
            return (not self._habilitada) or (parar is not None and parar.is_set())

    # ── Estado para la UI ─────────────────────────────────────────────────────
    @staticmethod
    def _estado_base() -> Dict[str, Any]:
        return {"activo": False, "conectado": False, "usuario": "", "error": "",
                "publicando": None, "sin_id": False}

    def _poner_estado(self, **campos: Any) -> None:
        with self._lock:
            nuevo = dict(self._estado)
            nuevo.update(campos)
            if nuevo == self._estado:
                return
            self._estado = nuevo
            copia = dict(nuevo)
        fn = self.on_estado
        if fn is not None:
            try:
                fn(copia)
            except Exception:
                _log.debug("discord: on_estado falló", exc_info=True)


_CONECTADO = object()


__all__ = ("ESTADOS", "NOMBRE_MUTEX", "ETIQUETA_BOTON", "ANTIRREBOTE_S", "INTERVALO_MIN_S",
           "REINTENTOS_S", "REINTENTO_OTRA_LUNE_S", "clave_estado", "cabe", "construir_actividad", "actividad_de",
           "url_boton", "client_id", "detalle", "render_visible", "es_patata", "Presencia", "motivo")
