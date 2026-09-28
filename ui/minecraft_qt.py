"""
ui/minecraft_qt.py — Minecraft en la app (web y nativa): reacciones a tu partida
y el bot de Minecraft de Lune.

`ControlMinecraft` es un controlador de `ServiciosEscritorio` (ui/escritorio.py):
lo registra el montaje como ("minecraft", ctl), SIN actividades de la tabla (no
mueve a la mascota: solo lee el bus), y recibe iniciar, detener y set_mascota.

REACCIONES (config minecraft.reaccionar)
----------------------------------------
- Autodetección cada 10 s, solo con `stat` (nunca se abre el proceso del juego):
  con `auto_con_juego`, lee si hay un latest.log tocado hace <60 s o el juego del
  modo juego es javaw.exe; sin él, siempre que `reaccionar` esté activo.
- Lectura cada 1 s (lune_core/minecraft_log.LectorLog) solo con el log activo; se
  suelta tras 10 min sin cambios y, si luego se vuelve a mover el MISMO archivo, el
  lector nuevo sigue donde se quedó (no se pierde lo que lo ha despertado). Nada
  corre con `reaccionar` apagado y el bot desconectado.
- Los eventos del log y los del bot (observador) se deduplican (mismo tipo y
  jugador en 5 s cuentan una vez), pasan por `Cadencia` y `reaccion`
  (lune_core/minecraft.py) y se entregan según el modo:
    · mascota a la vista → `mascota.decir_reaccion(texto, estado, ms)` (+ voz si
      `voz_reacciones` y no está silenciada);
    · sin mascota (web o nativa) → `anfitrion.aviso(texto)` + `anfitrion.reaccion`;
    · no hay burbuja arrastrándola, con un menú, alarma, pantalla grande,
      salvapantallas, hablando o pensando (ni si decir_reaccion dice que no: la
      burbuja de la IA manda): esa reacción no se dice (queda en los eventos
      recientes con entregado=False);
    · MODO JUEGO (D4): la mascota está oculta. Con el bot conectado y
      `decir_en_juego`, las muertes, logros y peligros los dice el bot en el chat
      del juego; y con `resumen_al_salir`, tus muertes y logros de ESA partida se
      apuntan (el resumen se vacía al entrar) y al salir sale el resumen en la burbuja.
- El texto del juego NUNCA entra en un turno del modelo.

BOT (datos.json minecraft.*, bot.proveedor)
-------------------------------------------
- `instalar_bot()` solo lo llama el botón «Instalar el bot» (D3): nunca una
  herramienta; con el bot en marcha se rechaza (npm ci borra node_modules) y
  detener() la corta (mata npm y sus hijos). `conectar_bot()` valida (Node,
  instalado, dueño) con los requisitos que mira un hilo (`node --version` y
  `node --help` nunca en el hilo de Qt; si aún no se saben, conecta al saberlo) y
  lanza lune_core/minecraft_proceso.ProcesoBot; `desconectar_bot()` y detener() lo
  paran en un hilo (con tope; ProcesoBot mata el árbol).
- Los hilos avisan con `_Aviso` (comprueba que el QObject siga vivo; detener los
  cierra y suelta los on_* del proceso ANTES de pararlo).
- `escritorio.estado_cambio`: `pensando` → `pausa_llm` (comparten Ollama); `juego`
  → `pausa_autonomo` si `pensar_en_juego` está apagado (D4).
- Señales: `estado_cambio(json)`, `evento(json)` {tipo, texto, estado, fuente, t}
  (lo que Lune dijo o apuntó, y las respuestas del bot), `chat(json)` {de, texto}
  (NO CONFIABLE: solo para pintarlo como texto en el panel) y `log_bot(str)`.
"""
from __future__ import annotations

import collections
import json
import logging
import re
import secrets
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal

from lune_core import minecraft as nm
from lune_core import minecraft_log as ml
from lune_core import minecraft_proceso as mp

_log = logging.getLogger("lune.minecraft")

INTERVALO_DETECTAR_MS = 10_000
INTERVALO_LEER_MS = 1_000
SOLTAR_LOG_S = 600.0
RECIENTE_S = 60.0
DEDUP_S = 5.0
MAX_EVENTOS = 50
RETRASO_RESUMEN_MS = 1500
EXE_MINECRAFT = "javaw.exe"
# Lo que el bot dice en el chat del juego en modo juego (lo demás ya lo comenta él mismo).
DECIR_EN_JUEGO = frozenset({"muerte", "logro", "peligro"})
# Estados del bus que impiden una burbuja (el «allowedStates» de Mate-Engine).
BLOQUEAN_BURBUJA = ("arrastrando", "menu_abierto", "alarma", "grande", "salvapantallas", "hablando", "pensando")
_CONTROLES = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def _llamar(obj: Any, metodo: str, *args) -> Any:
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("minecraft: %s.%s falló", type(obj).__name__, metodo)
        return None


def _texto(v: Any, tope: int) -> str:
    t = _CONTROLES.sub(" ", str(v if isinstance(v, (str, int, float)) else ""))
    return re.sub(r"\s+", " ", t).strip()[:tope]


def _hilo_normal(fn: Callable[[], Any], nombre: str = "lune-mc") -> None:
    threading.Thread(target=fn, name=nombre, daemon=True).start()


class _Aviso:
    """Lo que un hilo (el lector del bot, requisitos, npm) llama para avisar al hilo de Qt:
    emite la señal `senal` del dueño SOLO si el objeto de C++ sigue vivo, y cerrado no hace
    nada. Nunca se guarda la señal ligada (emitirla con el QObject borrado da
    AttributeError o una violación de acceso). `cerrar()` espera a un aviso a medias: al
    volver, ya no sale ninguno más (detener lo cierra antes del deleteLater)."""

    def __init__(self, dueno: QObject, senal: str):
        self._lock = threading.Lock()
        self._dueno: Optional[QObject] = dueno
        self._senal = senal

    @property
    def abierto(self) -> bool:
        return self._dueno is not None

    def cerrar(self) -> None:
        with self._lock:
            self._dueno = None

    def __call__(self, *valores: Any) -> None:
        with self._lock:
            d = self._dueno
            if d is None:
                return
            try:
                if sip.isdeleted(d):
                    self._dueno = None
                    return
                getattr(d, self._senal).emit(*(valores or (None,)))
            except (RuntimeError, AttributeError):
                self._dueno = None
            except TypeError:
                _log.exception("minecraft: aviso %s con argumentos que no van", self._senal)


class ControlMinecraft(QObject):
    """Reacciones a Minecraft + bot (ver el docstring del módulo)."""

    estado_cambio = pyqtSignal(str)
    evento = pyqtSignal(str)
    chat = pyqtSignal(str)
    log_bot = pyqtSignal(str)

    _del_bot = pyqtSignal(object)
    _log_hilo = pyqtSignal(str)
    _fin_hilo = pyqtSignal(object)
    _instalado_hilo = pyqtSignal(bool, str)
    _req_hilo = pyqtSignal(object)

    def __init__(self, escritorio: Any, config: Any, *, anfitrion: Any = None, voice: Any = None,
                 proceso: Any = None, lector: Any = None, en_ui: Optional[Callable] = None,
                 reloj: Callable[[], float] = time.monotonic, parent: Optional[QObject] = None,
                 rng: Any = None, rutas: Optional[Callable[[], List[Any]]] = None,
                 ahora: Callable[[], float] = time.time, datos_mc: Optional[Callable[[], dict]] = None,
                 personaje: Optional[Callable[[], dict]] = None, llm: Optional[Callable[[], Optional[dict]]] = None,
                 hilo: Optional[Callable[..., None]] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.anfitrion = anfitrion
        self.voice = voice
        self._en_ui = en_ui
        self._reloj = reloj
        self._ahora = ahora
        self._rutas = rutas or ml.rutas_candidatas
        self._datos_mc = datos_mc or self._datos_mc_defecto
        self._personaje_fn = personaje or self._personaje_defecto
        self._llm = llm or mp.config_llm
        self._hilo = hilo or _hilo_normal
        # Lector: una fábrica `lector(ruta)` o un lector ya hecho (con poll()).
        self._lector_fijo = lector if lector is not None and hasattr(lector, "poll") else None
        self._fab_lector = lector if callable(lector) and self._lector_fijo is None else None
        self._lector: Any = self._lector_fijo
        self._ruta_log = str(getattr(lector, "ruta", "") or "") if self._lector_fijo is not None else ""
        self._cadencia = nm.Cadencia(reloj, rng)
        self._rng = rng
        self._resumen = nm.Resumen()
        self._recientes: Deque[dict] = collections.deque(maxlen=MAX_EVENTOS)
        self._dedup: Dict[tuple, float] = {}
        self._mascota = getattr(escritorio, "mascota", None)
        self._iniciado = False
        self._conectado_bus = False
        self._juego = False
        self._pensando = False
        self._requisitos: Optional[dict] = None
        self._bot: Dict[str, Any] = {"instalando": False, "conectando": False, "conectado": False, "servidor": "",
                                     "nick": "", "vida": None, "hambre": None, "dia": None, "lluvia": None,
                                     "error": ""}
        self._t_detectar = QTimer(self)
        self._t_detectar.setInterval(INTERVALO_DETECTAR_MS)
        self._t_detectar.timeout.connect(self._detectar)
        self._t_leer = QTimer(self)
        self._t_leer.setInterval(INTERVALO_LEER_MS)
        self._t_leer.timeout.connect(self._leer)
        # Del hilo del bot al de Qt.
        self._del_bot.connect(self._on_bot, Qt.ConnectionType.QueuedConnection)
        self._log_hilo.connect(self._on_log, Qt.ConnectionType.QueuedConnection)
        self._fin_hilo.connect(self._on_fin, Qt.ConnectionType.QueuedConnection)
        self._instalado_hilo.connect(self._on_instalado, Qt.ConnectionType.QueuedConnection)
        self._req_hilo.connect(self._on_requisitos, Qt.ConnectionType.QueuedConnection)
        self._mirando_requisitos = False
        self._conectar_al_saber = False                # «Conectar» antes de saber si hay Node
        self._desconectando = False                    # desconexión pedida: no es un error
        self._foto_log: Optional[dict] = None          # dónde se quedó el lector soltado por inactividad
        self._avisos: List[_Aviso] = []
        self.proceso = proceso if proceso is not None else mp.ProcesoBot()
        self._enganchar_proceso()

    # ── Avisos desde otros hilos ───────────────────────────────────────────────
    def _aviso(self, senal: str) -> _Aviso:
        """Un aviso nuevo hacia `senal` (ver _Aviso); detener() los cierra todos."""
        a = _Aviso(self, senal)
        self._avisos = [x for x in self._avisos if x.abierto] + [a]
        return a

    def _enganchar_proceso(self) -> None:
        for nombre, senal in (("on_evento", "_del_bot"), ("on_log", "_log_hilo"), ("on_fin", "_fin_hilo")):
            try:
                setattr(self.proceso, nombre, self._aviso(senal))
            except Exception:
                pass

    def _soltar_proceso(self) -> None:
        """Antes de parar: el hilo lector del bot ya no puede avisar a este objeto (que se
        borrará con deleteLater mientras el bot aún se está cerrando)."""
        for nombre in ("on_evento", "on_log", "on_fin"):
            try:
                setattr(self.proceso, nombre, None)
            except Exception:
                pass
        for a in self._avisos:
            a.cerrar()
        self._avisos = []
        self._mirando_requisitos = False               # su aviso ya no llegará: se puede volver a mirar

    # ── Valores por defecto (inyectables en tests) ─────────────────────────────
    @staticmethod
    def _datos_mc_defecto() -> dict:
        from nucleo import datos
        return datos.minecraft()

    @staticmethod
    def _personaje_defecto() -> dict:
        try:
            from nucleo import personajes
            return personajes.get_activo() or {}
        except Exception:
            return {}

    def _cfg(self, clave: str, defecto: Any) -> Any:
        try:
            return self.config.get("minecraft", clave, defecto)
        except Exception:
            return defecto

    # ── Contrato de controlador ────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        if getattr(self.proceso, "on_evento", None) is None:
            self._enganchar_proceso()                  # iniciar tras un detener
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and hasattr(senal, "connect"):
            try:
                senal.connect(self._on_bus)
                self._conectado_bus = True
            except (TypeError, RuntimeError):
                self._conectado_bus = False
        est = self._estado_bus()
        self._juego = bool(getattr(est, "juego", False))
        self._pensando = bool(getattr(est, "pensando", False))
        self._actualizar_timers()
        if self.reaccionando:
            self._detectar()
        self._mirar_requisitos()
        self._emitir()

    def detener(self) -> None:
        """Para los timers, suelta el log, corta una instalación en marcha (npm y sus hijos) y
        PARA el bot: fuera del hilo de Qt, con tope y matando su árbol (ProcesoBot.parar). Que
        no quede node huérfano ni si Lune se cierra a mitad: ProcesoBot mete sus hijos en un
        Job de Windows que muere con Lune."""
        self._soltar_proceso()
        _llamar(self.proceso, "cancelar_instalacion")
        if not self._iniciado:
            self._parar_bot_ya()
            return
        self._iniciado = False
        self._t_detectar.stop()
        self._t_leer.stop()
        if self._conectado_bus:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._conectado_bus = False
        self._soltar_log()
        self._parar_bot_ya()

    def _parar_bot_ya(self) -> None:
        self._conectar_al_saber = False
        proceso = self.proceso
        try:
            vivo = bool(getattr(proceso, "vivo", False))
        except Exception:
            vivo = False
        if vivo:
            def parar():
                try:
                    proceso.parar(espera_s=2.0)
                except Exception:
                    _log.exception("minecraft: parar el bot falló")
            self._hilo(parar)
        self._bot.update(conectando=False, conectado=False, instalando=False)

    def set_mascota(self, v: Any) -> None:
        self._mascota = v

    def recargar_config(self) -> None:
        """Ajustes guardados (reaccionar, ruta del log, otros…): se aplican sin reiniciar."""
        if self._lector is not None and self._lector_fijo is None:
            ruta_cfg = str(self._cfg("ruta_log", "") or "").strip()
            if ruta_cfg and ml.ruta_valida(ruta_cfg) != getattr(self._lector, "ruta", None):
                self._soltar_log()
        if self._lector is not None:
            self._lector.otros = bool(self._cfg("reaccionar_otros", False))
        self._actualizar_timers()
        if self._iniciado and self.reaccionando:
            self._detectar()
        if self._iniciado:
            self._mirar_requisitos()
        self._emitir()

    # ── Reacciones ─────────────────────────────────────────────────────────────
    @property
    def reaccionando(self) -> bool:
        return bool(self._cfg("reaccionar", False))

    def alternar_reacciones(self) -> bool:
        nuevo = not self.reaccionando
        try:
            self.config.set("minecraft", "reaccionar", nuevo)
        except Exception:
            _log.exception("minecraft: no pude guardar minecraft.reaccionar")
        if not nuevo:
            self._soltar_log()
        self._actualizar_timers()
        if nuevo and self._iniciado:
            self._detectar()
        self._emitir()
        return nuevo

    def _actualizar_timers(self) -> None:
        on = self._iniciado and self.reaccionando
        if on and self._lector_fijo is None:
            if not self._t_detectar.isActive():
                self._t_detectar.start()
        else:
            self._t_detectar.stop()
        if on and self._lector is not None:
            if not self._t_leer.isActive():
                self._t_leer.start()
        else:
            self._t_leer.stop()

    def _exe_juego(self) -> str:
        juego = _llamar(self.escritorio, "obtener", "juego")
        est = _llamar(juego, "estado") if juego is not None else None
        return str((est or {}).get("exe") or "").lower() if isinstance(est, dict) else ""

    def _nombre_bot(self) -> str:
        return str(self._bot.get("nick") or "")

    def _detectar(self) -> None:
        """Cada 10 s (solo stat): ¿qué latest.log leer? Crea o suelta el lector."""
        if not self.reaccionando:
            self._soltar_log()
            self._actualizar_timers()
            return
        if self._lector_fijo is not None:
            self._actualizar_timers()
            return
        auto = bool(self._cfg("auto_con_juego", True))
        javaw = self._exe_juego() == EXE_MINECRAFT
        ruta_cfg = str(self._cfg("ruta_log", "") or "").strip()
        reciente = None if (javaw or not auto) else RECIENTE_S
        try:
            if ruta_cfg:
                ruta = ml.elegir_log(ruta_cfg, [], ahora=self._ahora)
                if ruta is not None and reciente is not None:
                    ruta = ml.elegir_log("", [ruta], ahora=self._ahora, reciente_s=reciente)
            else:
                ruta = ml.elegir_log("", self._rutas(), ahora=self._ahora, reciente_s=reciente)
        except Exception:
            _log.exception("minecraft: buscar latest.log falló")
            ruta = None
        if ruta is None:
            # Se deja el que había mientras no pasen 10 min sin cambios (lo suelta _leer).
            self._actualizar_timers()
            return
        if self._lector is None or str(getattr(self._lector, "ruta", "")) != str(ruta):
            fab = self._fab_lector or ml.LectorLog
            try:
                self._lector = fab(ruta)
            except Exception:
                _log.exception("minecraft: no pude crear el lector del log")
                self._lector = None
                return
            self._ruta_log = str(ruta)
            try:
                self._lector.nombre_bot = self._nombre_bot()
                self._lector.otros = bool(self._cfg("reaccionar_otros", False))
            except Exception:
                pass
            # El mismo archivo que se soltó por inactividad: sigue donde se quedó (si no, la
            # primera lectura salta lo viejo y se perdería la línea que lo ha despertado).
            foto, self._foto_log = self._foto_log, None
            if foto is not None and foto.get("ruta") == str(ruta):
                _llamar(self._lector, "retomar", foto)
            self._leer()
            self._emitir()
        self._actualizar_timers()

    def _leer(self) -> None:
        lector = self._lector
        if lector is None:
            self._t_leer.stop()
            return
        try:
            eventos = lector.poll()
        except Exception:
            _log.exception("minecraft: leer el log falló")
            eventos = []
        for ev in eventos or []:
            self._recibir(ev)
        if self._lector_fijo is None and lector is self._lector:
            inactivo = _llamar(lector, "inactivo_s")
            if isinstance(inactivo, (int, float)) and inactivo > SOLTAR_LOG_S and self._exe_juego() != EXE_MINECRAFT:
                foto = _llamar(lector, "instantanea")
                self._soltar_log()
                self._foto_log = foto if isinstance(foto, dict) else None
                self._emitir()

    def _soltar_log(self) -> None:
        if self._lector_fijo is not None:
            return
        self._lector = None
        self._ruta_log = ""
        self._foto_log = None                          # soltado a propósito: la próxima vez, desde el final
        self._t_leer.stop()

    def _clave_dedup(self, ev: Any) -> tuple:
        tipo = str(getattr(ev, "tipo", ""))
        jugador = str(getattr(ev, "jugador", "") or "").lower()
        if tipo in ("muerte", "logro", "conexion", "desconexion"):
            return (tipo, jugador)
        return (tipo, jugador, str(getattr(ev, "detalle", "") or "").lower())

    def _recibir(self, ev: Any) -> Optional[nm.Reaccion]:
        """Un evento (del log o del bot) → reacción entregada según el modo. En el hilo de Qt."""
        tipo = str(getattr(ev, "tipo", "") or "")
        if tipo not in nm.EVENTOS:
            return None
        t = self._reloj()
        for k in [k for k, v in self._dedup.items() if t - v >= DEDUP_S]:
            del self._dedup[k]
        clave = self._clave_dedup(ev)
        if clave in self._dedup:
            return None
        self._dedup[clave] = t
        if not self.reaccionando and tipo not in ("bot_conectado", "bot_desconectado"):
            return None                                # reacciones apagadas: solo el estado del bot
        if self._juego and bool(self._cfg("resumen_al_salir", True)):
            self._resumen.anotar(ev)
        if not self._cadencia.admite(tipo):
            return None
        r = nm.reaccion(ev, personaje=self._personaje_fn(), rng=self._rng)
        if r is None:
            return None
        entregado = self._entregar(r, ev)
        self._apuntar({"tipo": tipo, "texto": r.texto, "estado": r.estado,
                       "fuente": str(getattr(ev, "fuente", "log")), "t": self._ahora(), "entregado": bool(entregado)})
        return r

    def _estado_bus(self) -> Any:
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _mascota_visible(self) -> bool:
        m = self._mascota
        if m is None or getattr(m, "cerrado", False):
            return False
        try:
            return bool(m.isVisible())
        except Exception:
            return False

    def _entregar(self, r: nm.Reaccion, ev: Any = None) -> bool:
        tipo = r.evento
        if self._juego:
            if (tipo in DECIR_EN_JUEGO and self._bot.get("conectado") and bool(self._cfg("decir_en_juego", True))):
                return bool(_llamar(self.proceso, "decir", r.texto))
            return False                                # la mascota está oculta: al resumen (ya anotado)
        # Fuera del modo juego lo que no se dice se pierde (queda en «eventos recientes» con
        # entregado=False): el resumen es solo de la partida en modo juego (BM9, como patata).
        est = self._estado_bus()
        if est is not None and any(bool(getattr(est, c, False)) for c in BLOQUEAN_BURBUJA):
            return False
        ok = False
        if self._mascota_visible() and callable(getattr(self._mascota, "decir_reaccion", None)):
            ok = bool(_llamar(self._mascota, "decir_reaccion", r.texto, r.estado, r.ms))
            if not ok:
                return False
        elif self.anfitrion is not None:
            _llamar(self.anfitrion, "aviso", r.texto)
            _llamar(self.anfitrion, "reaccion", r.estado, r.ms)
            ok = True
        if ok and bool(self._cfg("voz_reacciones", False)) and self.voice is not None \
                and not bool(getattr(self.voice, "silenciada", False)):
            _llamar(self.voice, "speak", r.texto)
        return ok

    def _apuntar(self, d: dict) -> None:
        self._recientes.append(d)
        try:
            self.evento.emit(json.dumps(d, ensure_ascii=False))
        except Exception:
            _log.debug("minecraft: no pude emitir el evento", exc_info=True)

    def eventos_recientes(self, n: int = 50) -> List[dict]:
        n = max(0, min(MAX_EVENTOS, int(n)))
        return list(self._recientes)[-n:] if n else []

    # ── Bus del escritorio ─────────────────────────────────────────────────────
    def _on_bus(self, est: Any, cambios: Any = None) -> None:
        cambios = cambios if isinstance(cambios, dict) else {}
        if "pensando" in cambios:
            self._pensando = bool(getattr(est, "pensando", False))
            if self._bot_vivo():
                _llamar(self.proceso, "pausa_llm", self._pensando)
        if "juego" in cambios:
            juego = bool(getattr(est, "juego", False))
            if juego != self._juego:
                self._juego = juego
                self._al_cambiar_juego(juego)
            self._emitir()

    def _al_cambiar_juego(self, juego: bool) -> None:
        if self._bot_vivo() and not bool(self._cfg("pensar_en_juego", False)):
            _llamar(self.proceso, "pausa_autonomo", juego)
        if juego:
            self._resumen.reiniciar()                  # el resumen es de ESTA partida
            return
        if bool(self._cfg("resumen_al_salir", True)) and not self._resumen.vacio:
            QTimer.singleShot(RETRASO_RESUMEN_MS, self._decir_resumen)

    def _decir_resumen(self) -> bool:
        texto = self._resumen.texto()
        self._resumen.reiniciar()
        if not texto or self._juego:
            return False
        r = nm.Reaccion(texto=texto, estado="curious", ms=9000, evento="resumen")
        ok = self._entregar(r)
        self._apuntar({"tipo": "resumen", "texto": texto, "estado": r.estado, "fuente": "lune",
                       "t": self._ahora(), "entregado": bool(ok)})
        return ok

    # ── Bot ────────────────────────────────────────────────────────────────────
    def _bot_vivo(self) -> bool:
        try:
            return bool(getattr(self.proceso, "vivo", False))
        except Exception:
            return False

    @property
    def bot_conectado(self) -> bool:
        return bool(self._bot.get("conectado"))

    def _mirar_requisitos(self, *, conectar: bool = False) -> None:
        """Node y npm en un hilo (`node --version` y `node --help`, que ProcesoBot cachea):
        nada de eso bloquea la interfaz. El estado sale luego; con `conectar`, conecta el
        bot en cuanto lo sepa (el «Conectar» o el relevo que llegó antes de saberlo)."""
        if conectar:
            self._conectar_al_saber = True
        if self._mirando_requisitos:
            return
        self._mirando_requisitos = True
        proceso, aviso = self.proceso, self._aviso("_req_hilo")
        hecho: Dict[str, dict] = {}

        def trabajo():
            try:
                r = dict(proceso.requisitos(refrescar=True))
            except Exception:
                r = {"node": None, "node_ok": False, "npm": False, "instalado": False}
            if r.get("node_ok"):
                _llamar(proceso, "permisos")               # `node --help`, cacheado para arrancar()
            hecho["r"] = r
            aviso(r)
            aviso.cerrar()                             # de un solo uso
        self._hilo(trabajo)
        if "r" in hecho:                               # ya terminó (un hilo inyectado síncrono)
            self._requisitos = dict(hecho["r"])
            self._mirando_requisitos = False

    def _on_requisitos(self, r: Any) -> None:
        self._mirando_requisitos = False
        if isinstance(r, dict):
            self._requisitos = dict(r)
        if self._conectar_al_saber and self._iniciado:
            ok, texto = self.conectar_bot()
            if not ok and texto:
                _llamar(self.anfitrion, "aviso", texto)
        self._conectar_al_saber = False
        self._emitir()

    def requisitos(self, refrescar: bool = False) -> dict:
        """Node, npm e instalado (cacheado; `refrescar` lo vuelve a mirar AQUÍ, bloqueando: la
        app no lo usa, mira en un hilo con _mirar_requisitos)."""
        if self._requisitos is None or refrescar:
            try:
                self._requisitos = dict(self.proceso.requisitos(refrescar=refrescar))
            except TypeError:
                self._requisitos = dict(self.proceso.requisitos())
            except Exception:
                _log.exception("minecraft: requisitos del bot")
                self._requisitos = {"node": None, "node_ok": False, "npm": False, "instalado": False}
        return dict(self._requisitos)

    def _instalando(self) -> bool:
        """Esta ventana instala, u otra (otra ventana o patata: la marca de minecraft-bot/)."""
        if self._bot.get("instalando"):
            return True
        try:
            return bool(getattr(self.proceso, "instalando", False))
        except Exception:
            return False

    def instalar_bot(self) -> Tuple[bool, str]:
        """Botón «Instalar el bot» (D3). En un hilo; nunca lo dispara una herramienta. Con el
        bot en marcha no: npm ci borra node_modules, que el bot está usando (BM11)."""
        if self._instalando():
            return False, "Ya se está instalando."
        if self._bot_vivo():
            texto = "Desconecta el bot antes de reinstalarlo (npm borraría los archivos que está usando)."
            _llamar(self.anfitrion, "aviso", texto)
            self._emitir()
            return False, texto
        self._bot["instalando"] = True
        self._bot["error"] = ""
        self._emitir()
        proceso, aviso = self.proceso, self._aviso("_instalado_hilo")

        def trabajo():
            try:
                ok, texto = proceso.instalar()
            except Exception as e:                       # noqa: BLE001
                ok, texto = False, f"No pude instalar el bot: {e}"[:300]
            aviso(bool(ok), str(texto))
            aviso.cerrar()
        self._hilo(trabajo)
        return True, "Instalando el bot (~400 MB). Tarda unos minutos."

    def _on_instalado(self, ok: bool, texto: str) -> None:
        self._bot["instalando"] = False
        self._bot["error"] = "" if ok else _texto(texto, 400)
        self._mirar_requisitos()
        _llamar(self.anfitrion, "aviso", texto)
        self._apuntar({"tipo": "instalacion", "texto": _texto(texto, 400), "estado": "happy" if ok else "sad",
                       "fuente": "lune", "t": self._ahora(), "entregado": True})
        self._emitir()

    def conectar_bot(self) -> Tuple[bool, str]:
        if self._bot_vivo():
            return False, "El bot ya está conectado."
        if self._instalando():
            return False, "Espera a que termine la instalación."
        # Requisitos de la caché (los mira un hilo: iniciar, recargar_config, tras instalar).
        if self._requisitos is None:
            self._mirar_requisitos(conectar=True)
            if self._requisitos is None:              # aún mirando: conecta al saberlo
                self._emitir()
                return True, "Compruebo Node.js y conecto el bot enseguida…"
        self._conectar_al_saber = False
        req = dict(self._requisitos)
        try:
            req["instalado"] = bool(self.proceso.instalado())
        except Exception:
            pass
        if not req.get("node_ok"):
            self._mirar_requisitos()                  # por si lo acaban de instalar: la próxima vez
            return False, mp.AVISO_SIN_NODE
        if not req.get("instalado"):
            return False, mp.AVISO_INSTALAR
        try:
            cfg = mp.config_bot(self._datos_mc(), self._personaje_fn(), self._llm())
        except ValueError as e:
            self._bot["error"] = str(e)
            self._emitir()
            return False, str(e)
        cfg["pausa_autonomo"] = bool(self._juego and not self._cfg("pensar_en_juego", False))
        cfg["pausa_llm"] = bool(self._pensando)
        if getattr(self.proceso, "on_evento", None) is None:
            self._enganchar_proceso()                  # tras un detener
        try:
            ok, texto = self.proceso.arrancar(cfg)
        except Exception as e:
            ok, texto = False, f"No pude lanzar el bot: {e}"[:300]
        if ok:
            self._desconectando = False
            self._bot.update(conectando=True, conectado=False, error="", servidor=f"{cfg['host']}:{cfg['port']}",
                             nick=cfg["nick"], vida=None, hambre=None, dia=None, lluvia=None)
            if self._lector is not None:
                try:
                    self._lector.nombre_bot = cfg["nick"]
                except Exception:
                    pass
            texto = f"Conectando el bot a {cfg['host']}:{cfg['port']} como {cfg['nick']}…"
        else:
            self._bot["error"] = str(texto)
        self._emitir()
        return bool(ok), str(texto)

    def desconectar_bot(self) -> bool:
        if not self._bot_vivo():
            cambio = bool(self._bot.get("conectado") or self._bot.get("conectando"))
            self._bot.update(conectando=False, conectado=False)
            if cambio:
                self._emitir()
            return False
        self._bot["conectando"] = False
        self._desconectando = True
        self._emitir()
        proceso = self.proceso
        self._hilo(lambda: proceso.parar())
        return True

    def alternar_bot(self) -> Tuple[bool, str]:
        """Para la bandeja o el radial: conecta o desconecta."""
        if self._bot_vivo():
            return self.desconectar_bot(), "Desconecto el bot."
        return self.conectar_bot()

    def orden(self, texto: str, *, origen: str = "usuario") -> Tuple[bool, str]:
        orden = nm.clasificar_orden(texto)
        if orden is None:
            return False, f"El bot no entiende esa orden. Puede: {nm.AYUDA_ORDENES}."
        if not self._bot.get("conectado"):
            return False, "El bot no está conectado."
        id_ = secrets.token_hex(4)
        if not _llamar(self.proceso, "orden", id_, orden):
            return False, "No pude mandarle la orden al bot."
        self._apuntar({"tipo": "orden", "texto": orden, "estado": "", "fuente": str(origen)[:12],
                       "t": self._ahora(), "entregado": True, "id": id_})
        return True, "Se lo he mandado al bot."

    def decir(self, texto: str) -> Tuple[bool, str]:
        t = _texto(texto, 100).lstrip("/\\ ").strip()
        if not t:
            return False, "No hay nada que decir."
        if not self._bot.get("conectado"):
            return False, "El bot no está conectado."
        if not _llamar(self.proceso, "decir", t):
            return False, "No pude mandárselo al bot."
        return True, "Dicho."

    # ── Mensajes del bot (hilo de Qt) ──────────────────────────────────────────
    def _on_bot(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        tipo = msg.get("tipo")
        if tipo == "conectado":
            nick = mp.nick_valido(msg.get("nick")) or self._bot.get("nick") or ""
            self._bot.update(conectando=False, conectado=True, error="", nick=nick)
            if self._lector is not None:
                try:
                    self._lector.nombre_bot = nick
                except Exception:
                    pass
            self._recibir(ml.Evento("bot_conectado", nick, fuente="bot", t=self._ahora()))
        elif tipo == "desconectado":
            estaba = bool(self._bot.get("conectado"))
            pedido = self._desconectando or msg.get("pedido") is True
            self._bot.update(conectando=False, conectado=False, error="" if pedido else _texto(msg.get("motivo"), 200))
            if estaba:
                self._recibir(ml.Evento("bot_desconectado", fuente="bot", t=self._ahora()))
        elif tipo == "estado":
            for clave in ("vida", "hambre"):
                v = msg.get(clave)
                self._bot[clave] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 40 else None
            for clave in ("dia", "lluvia"):
                v = msg.get(clave)
                self._bot[clave] = v if isinstance(v, bool) else None
        elif tipo == "evento":
            self._evento_del_bot(msg)
            return
        elif tipo == "chat":
            de = mp.nick_valido(msg.get("de")) or ""
            texto = _texto(msg.get("texto"), 256)
            if de and texto:
                try:
                    self.chat.emit(json.dumps({"de": de, "texto": texto, "t": self._ahora()}, ensure_ascii=False))
                except Exception:
                    pass
            return
        elif tipo == "respuesta":
            texto = _texto(msg.get("texto"), 300)
            if texto:
                self._apuntar({"tipo": "respuesta", "texto": texto, "estado": "", "fuente": "bot",
                               "t": self._ahora(), "entregado": True, "id": _texto(msg.get("id"), 40)})
            return
        elif tipo == "error":
            self._bot["error"] = _texto(msg.get("mensaje"), 300)
            if msg.get("fatal"):
                self._bot["conectando"] = False
            self._on_log("error: " + self._bot["error"])
        elif tipo != "listo":
            return
        self._emitir()

    def _evento_del_bot(self, msg: dict) -> None:
        tipo = str(msg.get("evento") or "")           # observador.js: {tipo:'evento', evento, jugador, detalle}
        if not tipo:
            return
        if tipo not in nm.EVENTOS or tipo in ("sesion_inicio", "sesion_fin", "conexion", "desconexion",
                                                "bot_conectado", "bot_desconectado"):
            return
        jugador = mp.nick_valido(msg.get("jugador")) or ""
        detalle = _texto(msg.get("detalle"), 64)
        try:
            dueno = str((self._datos_mc() or {}).get("dueno") or "")
        except Exception:
            dueno = ""
        propio = bool(jugador) and jugador.lower() == dueno.lower()
        if tipo in ("muerte", "logro") and not propio and not bool(self._cfg("reaccionar_otros", False)):
            return
        self._recibir(ml.Evento(tipo, jugador, detalle, t=self._ahora(), fuente="bot", propio=propio))

    def _on_log(self, linea: Any) -> None:
        try:
            self.log_bot.emit(_texto(linea, 300))
        except Exception:
            pass

    def _on_fin(self, codigo: Any) -> None:
        estaba = bool(self._bot.get("conectado"))
        pedido, self._desconectando = self._desconectando, False
        self._bot.update(conectando=False, conectado=False)
        if isinstance(codigo, int) and codigo not in (0, None) and not self._bot.get("error") and not pedido:
            self._bot["error"] = f"El bot se cerró (código {codigo})."
        if estaba:
            self._recibir(ml.Evento("bot_desconectado", fuente="bot", t=self._ahora()))
        self._emitir()

    # ── Estado ─────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        # Sin mirar aún (va en un hilo): None = «comprobando».
        req = dict(self._requisitos) if self._requisitos is not None else {"node": None, "node_ok": None, "npm": None}
        try:
            instalado = bool(self.proceso.instalado())
        except Exception:
            instalado = bool(req.get("instalado"))
        bot = dict(self._bot)
        bot["instalado"] = instalado
        bot["instalando"] = self._instalando()
        bot["conectando"] = bool(bot.get("conectando")) and self._bot_vivo()
        lector = self._lector
        return {
            "reaccionar": self.reaccionando,
            "log": {"ruta": self._ruta_log if lector is not None else "", "activo": lector is not None,
                    "yo": mp.nick_valido(getattr(lector, "yo", "")) or "" if lector is not None else ""},
            "bot": bot,
            "requisitos": {"node": req.get("node"),
                           "node_ok": None if req.get("node_ok") is None else bool(req.get("node_ok")),
                           "npm": None if req.get("npm") is None else bool(req.get("npm"))},
            "juego": bool(self._juego),
            "pensando": bool(self._pensando),
        }

    def _emitir(self) -> None:
        try:
            self.estado_cambio.emit(json.dumps(self.estado(), ensure_ascii=False))
        except Exception:
            _log.debug("minecraft: no pude emitir el estado", exc_info=True)

    # ── Herramientas del modelo ────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["minecraft"] = self
        if self._en_ui is not None:
            base["en_ui"] = self._en_ui
        return base

    def herramientas(self) -> dict:
        """{nombre: handler(args, ctx)} de minecraft_estado, minecraft_orden y minecraft_bot."""
        return {
            "minecraft_estado": lambda args=None, ctx=None: nm.herramienta_estado(args, self._ctx(ctx)),
            "minecraft_orden": lambda args=None, ctx=None: nm.herramienta_orden(args, self._ctx(ctx)),
            "minecraft_bot": lambda args=None, ctx=None: nm.herramienta_bot(args, self._ctx(ctx)),
        }


__all__ = ("ControlMinecraft", "DECIR_EN_JUEGO", "BLOQUEAN_BURBUJA")
