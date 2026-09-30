"""
ui/asiento_qt.py — `ControlAsiento`: la asistente se sienta en ventanas y en la
barra de tareas (corte 7, P03; port de AvatarWindowHandler y
AvatarTaskbarController de Mate-Engine).

Es el controlador de la actividad `sentada` de ServiciosEscritorio
(ui/escritorio.py). La lógica (cuándo encaja, dónde se clava, cuándo se suelta)
es `nucleo/asiento.MaquinaAsiento`; aquí se leen las ventanas
(`servicios/ventanas_ajenas`, solo lectura, por sondeo) y se mueve y reordena
SOLO la ventana de la asistente (`servicios/win_ventana`, que comprueba que es
propia). Todo en px físicos (crítica c.16).

ARRASTRE MANUAL (VRM y animada: CompanionFlotante)
--------------------------------------------------
1. `asistente.arrastre_cambio(True)` → instala el delegado de arrastre y pide el
   punto de asiento (`punto_asiento`; hasta que llega, (w/2, 0.78·h)). Si
   `avatar.sentarse_ventanas` está activo y la tabla deja sentarse, un QTimer de
   66 ms enumera candidatas; con solo la barra, `barra_asiento` a 4 Hz (sin
   enumerar ventanas). Con un juego delante, nada.
2. El delegado (en cada movimiento del ratón): posición libre = inicio + (cursor
   físico − cursor inicial) → `maquina.al_arrastrar`. Libre: mueve la ventana.
   Al encajar: `prioridad.iniciar("sentada", modo)` (si no se permite, no hay
   asiento), `asistente.asiento(True, modo, variante, cb)`, `colocar_sobre`
   (ventana) o «siempre encima» (barra) y clavado provisional con la sonda; el
   `cb` trae el asiento medido con la pose completa y se vuelve a clavar con
   SmoothDamp. Sentada, desliza por el borde. Devuelve True (la asistente no se
   mueve sola).
   Con el ratón QUIETO no hay MouseMove: un QTimer propio (66 ms; 16 ms mientras
   se desliza con SmoothDamp) da la misma muestra con la última posición, así el
   medio segundo sobre el borde cuenta y el deslizamiento acaba aunque no muevas
   el ratón (revisión 7-10).
3. `arrastre_cambio(False)` → para la enumeración; si sigue sentada, queda
   clavada; si no, un último intento con la sonda (`al_soltar(muestreado=True)`).
   Levantarse en la misma pasada vuelve al punto de asiento DE PIE (el sentado
   encajaría con el pecho).

ARRASTRE NATIVO (sprites: AvatarOverlay, startSystemMove)
---------------------------------------------------------
El SO mueve la ventana: al empezar, si estaba sentada, se levanta; al soltar se
enumera UNA vez y `maquina.al_soltar(sonda=…)` decide si encaja (agarre ≥ 0.5 s
y ≥ 10 px) con el mismo clavado.

SENTADA Y QUIETA
----------------
QTimer a 15 Hz: rect visible y estado de la ventana objetivo (cerrada, oculta,
minimizada, maximizada, pantalla completa, cloaked o el borde por encima de su
monitor → se levanta). Si el objetivo se movió, 60 Hz durante 0.5 s y clavado
rígido (el suavizado solo existe justo tras encajar). En cada tic, si no está
justo encima del objetivo, `colocar_sobre`; en la barra, «siempre encima» cada
2 s. `punto_asiento` cada 1 s y al cambiar de pantalla (rueda, tamaño, DPI): si
cambió más de 1 px, se vuelve a clavar. De pie o en reposo no corre nada.

AL LEVANTARSE
-------------
`asistente.asiento(False)`, `asistente.restaurar_orden_z()` y
`prioridad.terminar("sentada")` (reanuda el baile si sigue la música). La
asistente se queda donde estaba, flotando, como en ME. Con `ceder` (juego,
alarma, pantalla grande, MMD) se levanta igual pero recuerda dónde estaba y
`reanudar` la vuelve a sentar si la ventana sigue bien (si no, suelta la
actividad). «Bájate», arrastrarla o colocarla por código (esquina,
`antes_de_colocar`: ui/montaje_vida) durante la cesión → `bajar()`: ya no vuelve
(`prioridad.olvidar("sentada")`).

LA BARRA DE QUÉ MONITOR
-----------------------
La del monitor del punto que importa (sentada: el asiento sobre su barra; buscando:
la sonda), no la del centro de la ventana: con monitores uno encima de otro y el
asiento por encima del centro, el centro caía en el de abajo. Si la barra se oculta
sola, `barra_auto_oculta()` (SHAppBarMessage, un mensaje a Explorer) se guarda 2 s
(`_PantallaConCache`): el tic de 15 Hz no se lo pregunta cada vez.

Señales: `sentada(modo, variante)`, `levantada(motivo)` y `cambio(json)` con
`estado()`. Herramienta: `asistente_sentarse` (`herramientas()`).
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from nucleo import asiento as na
from nucleo.asiento import Desnap, MaquinaAsiento, Mover, Objetivo, Snap, punto_fisico, radio_sonda
from nucleo.fisica import clamp
from servicios import ventanas_ajenas as va
from servicios import win_pantalla as wp

_log = logging.getLogger("lune.asiento")

TEXTO_BARRA_OK = "Me senté en la barra de tareas."
TEXTO_VENTANA_OK = "Me senté en una ventana."
TEXTO_VENTANAS_OFF = "Sentarme en ventanas está desactivado (Ajustes → Sentarse)."
TEXTO_JUEGO = "Ahora no puedo: hay un juego delante."
TEXTO_SIN_VENTANA = "No encuentro una ventana donde sentarme."
TEXTO_SIN_BARRA = "No encuentro la barra de tareas abajo en esta pantalla."
TEXTO_SIN_ASISTENTE = "Necesito estar a la vista para sentarme: sácame primero."
TEXTO_ARRASTRANDO = "Ahora me estás moviendo: suéltame primero."
TEXTO_BAJADA = "Vale, ya me bajé."
TEXTO_NO_SENTADA = "No estaba sentada."
_MOTIVOS_OCUPADA = {
    "juego": "hay un juego delante",
    "alarma": "está sonando una alarma",
    "grande": "estoy en pantalla grande",
    "salvapantallas": "estoy de salvapantallas",
    "mmd": "estoy bailando",
}

OFFSET_MAX = 64
ALTO_ASIENTO_DEFECTO = 0.78          # (w/2, 0.78·h) hasta que la página mide


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("asiento: %s.%s falló", type(obj).__name__, metodo)
        return None


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _par(v: Any) -> Optional[Tuple[float, float]]:
    if isinstance(v, dict):
        x, y = _num(v.get("x")), _num(v.get("y"))
    elif isinstance(v, (list, tuple)) and len(v) >= 2:
        x, y = _num(v[0]), _num(v[1])
    else:
        return None
    return (x, y) if x is not None and y is not None else None


def leer_punto(p: Any) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """{"asiento": [x, y] | {x, y}, "sonda": …} (dict o JSON) → (asiento, sonda) o None."""
    if isinstance(p, (str, bytes)):
        try:
            p = json.loads(p)
        except (TypeError, ValueError):
            return None
    if not isinstance(p, dict):
        return None
    a = _par(p.get("asiento"))
    if a is None:
        return None
    s = _par(p.get("sonda")) or a
    return a, s


class _PantallaConCache:
    """La API de pantalla (win_pantalla) con `barra_auto_oculta()` guardado `TTL_S`:
    es SHAppBarMessage (un SendMessage a Explorer) y, con la barra que se oculta sola,
    el tic de sentada lo pedía a 15 Hz en el hilo de Qt. Lo demás pasa tal cual."""

    TTL_S = 2.0

    def __init__(self, api: Any, reloj: Callable[[], float]):
        self._api = api
        self._reloj = reloj
        self._oculta: Optional[bool] = None
        self._t = -math.inf

    def barra_auto_oculta(self) -> bool:
        t = self._reloj()
        if self._oculta is None or t - self._t >= self.TTL_S:
            self._oculta = bool(self._api.barra_auto_oculta())
            self._t = t
        return self._oculta

    def __getattr__(self, nombre: str) -> Any:
        return getattr(self._api, nombre)


class ControlAsiento(QObject):
    """Controlador de «sentada» (ver la cabecera del módulo)."""

    sentada = pyqtSignal(str, int)          # modo (barra|ventana), variante
    levantada = pyqtSignal(str)             # motivo
    cambio = pyqtSignal(str)                # JSON de estado()

    TIC_MS = 66
    RAPIDO_MS = 16
    RAPIDO_S = 0.5
    REMEDIR_MS = 1000
    TOPMOST_BARRA_MS = 2000
    ENUM_MS = 66
    BARRA_MS = 250
    ARRASTRE_MS = 66                  # muestras del arrastre manual con el ratón quieto

    def __init__(self, escritorio: Any, config: Any, *, api: Any = None, ventana: Any = None, entrada: Any = None,
                 pantalla: Any = None, hwnd_principal: Optional[Callable[[], int]] = None,
                 en_ui: Optional[Callable] = None, reloj: Callable[[], float] = time.monotonic,
                 parent: Optional[QObject] = None, azar: Any = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self._api = api
        if ventana is None:
            from servicios import win_ventana as ventana
        self._win = ventana
        self._entrada = entrada
        self._pantalla = pantalla
        self._pantalla_cache: Optional[_PantallaConCache] = None
        self._hwnd_principal = hwnd_principal
        self._en_ui = en_ui
        self._reloj = reloj
        self.maquina = MaquinaAsiento(azar=azar)
        self._asistente: Any = None
        self._iniciado = False
        self._bus_conectado = False
        self._arrastrando = False
        self._manual = False
        self._delegado_puesto = False
        self._inicio: Optional[va.Rect] = None
        self._c0: Optional[Tuple[int, int]] = None
        self._t_ult = 0.0
        self._candidatas: List[Any] = []
        self._asiento_rel: Optional[Tuple[float, float]] = None
        self._sonda_rel: Optional[Tuple[float, float]] = None
        self._rel_de_pie: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
        self._medido = False
        self._gen = 0
        self._rect_obj_prev: Optional[va.Rect] = None
        self._rapido_hasta = -math.inf
        self._t_topmost = -math.inf
        self._cedido: Optional[Dict[str, Any]] = None
        self._pantalla_qt: Any = None
        self._ultimo_estado = ""
        self._t_enum = QTimer(self)
        self._t_enum.timeout.connect(self._refrescar)
        self._t_tic = QTimer(self)
        self._t_tic.setInterval(self.TIC_MS)
        self._t_tic.timeout.connect(self._tic)
        self._t_remedir = QTimer(self)
        self._t_remedir.setInterval(self.REMEDIR_MS)
        self._t_remedir.timeout.connect(self._remedir)
        self._t_arrastre = QTimer(self)
        self._t_arrastre.setInterval(self.ARRASTRE_MS)
        self._t_arrastre.timeout.connect(self._tic_arrastre)

    # ── Lo compartido ────────────────────────────────────────────────────────────
    def _va(self) -> Any:
        if self._api is None:
            self._api = va.api_defecto()
        return self._api

    def _api_pantalla(self) -> Any:
        if self._pantalla_cache is None:
            self._pantalla_cache = _PantallaConCache(self._pantalla or wp.api_defecto(), self._reloj)
        return self._pantalla_cache

    def _barra_en(self, punto: Optional[Tuple[float, float]], rm: Optional[va.Rect]) -> Optional[va.Candidata]:
        """La barra de abajo del monitor que contiene `punto` (px físicos: el asiento sobre
        la barra, o la sonda). Solo si el punto no cae en ningún monitor, la del centro
        de `rm` (la ventana de la asistente)."""
        api = self._api_pantalla()
        if punto is not None:
            x, y = int(round(punto[0])), int(round(punto[1]))
            try:
                mons = wp.monitores(api)
            except Exception:
                mons = []
            for mon in mons:
                if va._rect(mon.rect).contiene(x, y):
                    return va.barra_asiento(mon, api)
        return va.barra_asiento(rm, api) if rm is not None else None

    def _punto_barra(self, o: Objetivo, rm: Optional[va.Rect]) -> Tuple[float, float]:
        """Sentada en la barra `o`: el asiento (x) sobre su borde (y − 1: dentro de su
        monitor aunque la barra se oculte sola y su rect empiece en el borde de abajo)."""
        x = o.rect.izq + o.rect.ancho / 2.0
        if rm is not None and self._asiento_rel is not None:
            x = punto_fisico(rm, self._asiento_rel, self._dpr())[0]
        return x, o.rect.arriba - 1

    def _cursor(self) -> Optional[Tuple[int, int]]:
        if self._entrada is None:
            from servicios import win_entrada
            self._entrada = win_entrada.api_defecto()
        try:
            c = self._entrada.cursor()
        except Exception:
            return None
        return (int(c[0]), int(c[1])) if c else None

    def _estado_bus(self) -> Any:
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _juego(self) -> bool:
        est = self._estado_bus()
        return bool(est is not None and getattr(est, "juego", False))

    def _prioridad(self) -> Any:
        return getattr(self.escritorio, "prioridad", None)

    def _puede(self) -> bool:
        pr = self._prioridad()
        if pr is None:
            return True
        try:
            return bool(pr.puede("sentada"))
        except Exception:
            return False

    def _cfg(self, clave: str, defecto: Any) -> Any:
        if self.config is None:
            return defecto
        try:
            return self.config.get("avatar", clave, defecto)
        except Exception:
            return defecto

    def _cfg_ventanas(self) -> bool:
        return bool(self._cfg("sentarse_ventanas", False))

    def _cfg_barra(self) -> bool:
        return bool(self._cfg("sentarse_barra", True))

    def _offset(self) -> int:
        try:
            v = int(self._cfg("sentarse_offset_px", 0) or 0)
        except (TypeError, ValueError):
            v = 0
        return int(clamp(v, -OFFSET_MAX, OFFSET_MAX))

    def _hwnd(self) -> int:
        m = self._asistente
        if m is None:
            return 0
        try:
            f = getattr(m, "hwnd", None)
            return int(f() if callable(f) else m.winId())
        except Exception:
            return 0

    def _dpr(self) -> float:
        f = getattr(self._asistente, "devicePixelRatioF", None)
        try:
            d = float(f()) if callable(f) else 1.0
        except Exception:
            d = 1.0
        return d if d > 0 and math.isfinite(d) else 1.0

    def _visible(self) -> bool:
        m = self._asistente
        if m is None:
            return False
        f = getattr(m, "isVisible", None)
        try:
            return bool(f()) if callable(f) else True
        except Exception:
            return False

    def _rect_m(self) -> Optional[va.Rect]:
        h = self._hwnd()
        if not h:
            return None
        try:
            r = self._win.rect_propia(h)
        except Exception:
            return None
        return va._rect(r) if r else None

    def _permitir(self) -> Tuple[int, ...]:
        f = self._hwnd_principal
        if not callable(f):
            return ()
        try:
            h = int(f() or 0)
        except Exception:
            return ()
        return (h,) if h else ()

    def _ocluida(self, hwnd: int, x: int, y: int) -> bool:
        return va.ocluida_en(self._va(), hwnd, x, y, excluir_pid=os.getpid())

    def _nativa(self) -> bool:
        """Sprites: arrastre del SO (startSystemMove), sin delegado."""
        m = self._asistente
        return getattr(m, "render", "") == "sprites" or not callable(getattr(m, "set_arrastre_delegado", None))

    # ── Consultas ────────────────────────────────────────────────────────────────
    @property
    def sentada_en(self) -> str:
        s = self.maquina.sentada
        return s.modo if s is not None else ""

    @property
    def cedida(self) -> bool:
        """De pie porque algo le quitó «sentada» (juego, MMD…) y `reanudar` la volvería a sentar."""
        return self._cedido is not None

    def estado(self) -> dict:
        s = self.maquina.sentada
        return {
            "sentada": s.modo if s is not None else "",
            "variante": s.variante if s is not None else 0,
            "ventanas": self._cfg_ventanas(),
            "barra": self._cfg_barra(),
            "offset": self._offset(),
            "disponible": self._asistente is not None,
            "juego": self._juego(),
            "arrastrando": self._arrastrando,
            "cedida": self._cedido is not None,
        }

    def _emitir(self) -> None:
        txt = json.dumps(self.estado(), ensure_ascii=False, sort_keys=True)
        if txt != self._ultimo_estado:
            self._ultimo_estado = txt
            try:
                self.cambio.emit(txt)
            except RuntimeError:
                pass

    # ── Ciclo de vida (contrato de ServiciosEscritorio) ─────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and not self._bus_conectado:
            try:
                senal.connect(self._on_bus)
                self._bus_conectado = True
            except (TypeError, RuntimeError):
                pass

    def detener(self) -> None:
        """Se levanta si estaba sentada y no deja timers ni delegado. Idempotente."""
        self._iniciado = False
        if self._arrastrando:
            self._cortar_arrastre()
        if self.maquina.sentada is not None:
            self._levantar("usuario")
        self._cedido = None
        for t in (self._t_enum, self._t_tic, self._t_remedir, self._t_arrastre):
            t.stop()
        self._desconectar_pantalla()
        if self._bus_conectado:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._bus_conectado = False

    def set_asistente(self, v: Any) -> None:
        if v is self._asistente:
            return
        if self._arrastrando:
            self._cortar_arrastre()
        if self.maquina.sentada is not None:
            self._levantar("cerrada")
        self._cedido = None
        vieja = self._asistente
        if vieja is not None:
            s = getattr(vieja, "arrastre_cambio", None)
            if s is not None:
                try:
                    s.disconnect(self._on_arrastre)
                except (TypeError, RuntimeError):
                    pass
            if self._delegado_puesto:
                _llamar(vieja, "set_arrastre_delegado", None)
        self._delegado_puesto = False
        self._asistente = v
        self._gen += 1                                    # lo que conteste la de antes ya no vale
        self._medido = False
        self._asiento_rel = self._sonda_rel = None
        self._rel_de_pie = None
        if v is not None:
            s = getattr(v, "arrastre_cambio", None)
            if s is not None and hasattr(s, "connect"):
                try:
                    s.connect(self._on_arrastre)
                except (TypeError, RuntimeError):
                    pass
        self._emitir()

    def ceder(self, c: Any) -> None:
        """La tabla le quita «sentada» (juego, alarma, pantalla grande, MMD): de pie,
        recordando dónde estaba para `reanudar`."""
        s = self.maquina.sentada
        if s is None:
            return
        self._cedido = {"objetivo": s.objetivo, "frac": s.frac, "variante": s.variante}
        self.maquina.levantar("cede")
        self._tras_levantar("cede", terminar=False)

    def reanudar(self, c: Any) -> None:
        """Acabó lo que la interrumpió (la tabla ya volvió a marcar «sentada»):
        se vuelve a sentar en el mismo sitio si sigue bien; si no, suelta."""
        ced, self._cedido = self._cedido, None
        obj = None
        if ced is not None and self._asistente is not None and self._visible() and not self._juego():
            o: Objetivo = ced["objetivo"]
            if o.es_barra:
                rm = self._rect_m()
                b = self._barra_en((o.rect.izq + o.rect.ancho / 2.0, o.rect.arriba - 1), rm)
                if b is not None:
                    obj = Objetivo(int(b.hwnd), True, b.rect)
            elif self._cfg_ventanas() and va.estado_ventana(self._va(), o.hwnd) == "ok":
                r = self._va().rect_visible(o.hwnd)
                if r is not None:
                    obj = Objetivo(o.hwnd, False, va._rect(r))
        if obj is None:
            pr = self._prioridad()
            if pr is not None:
                try:
                    pr.terminar("sentada")
                except Exception:
                    _log.exception("asiento: no pude soltar la actividad")
            self._emitir()
            return
        snap = self.maquina.sentar_directo(obj, frac=ced["frac"], variante=ced["variante"])
        self._gen += 1
        self._aplicar_visual(snap, self._reloj(), provisional=False)

    def recargar_config(self) -> None:
        s = self.maquina.sentada
        if s is not None and s.modo == na.MODO_VENTANA and not self._cfg_ventanas():
            self.bajar("usuario")
        elif s is not None and not self._arrastrando:
            self._armar_tic()
        self._emitir()

    # ── Órdenes ──────────────────────────────────────────────────────────────────
    def sentar(self, sitio: str) -> Tuple[bool, str]:
        """«barra»: la barra de abajo del monitor de la asistente, a la x más cercana.
        «ventana» (exige avatar.sentarse_ventanas): la ventana activa si vale; si
        no, la más alta de su monitor con el borde a la vista. Se desliza hasta allí."""
        sitio = str(sitio or "").strip().lower()
        if sitio == "bajar":
            ok = self.bajar("usuario")
            return ok, TEXTO_BAJADA if ok else TEXTO_NO_SENTADA
        if sitio not in (na.MODO_BARRA, na.MODO_VENTANA):
            return False, "¿Dónde me siento? Dime «barra» o «ventana»."
        if self._asistente is None or not self._visible():
            return False, TEXTO_SIN_ASISTENTE
        if self._juego():
            return False, TEXTO_JUEGO
        if self._arrastrando:
            return False, TEXTO_ARRASTRANDO
        if sitio == na.MODO_VENTANA and not self._cfg_ventanas():
            return False, TEXTO_VENTANAS_OFF
        if not self._puede():
            return False, self._texto_ocupada()
        h, rm = self._hwnd(), self._rect_m()
        if not h or rm is None:
            return False, TEXTO_SIN_ASISTENTE
        self._pedir_punto()
        self._asegurar_rel(rm)
        dpr = self._dpr()
        seat_x = punto_fisico(rm, self._asiento_rel, dpr)[0]
        if sitio == na.MODO_BARRA:
            c = self._barra_en(None, rm)
            if c is None:
                return False, TEXTO_SIN_BARRA
        else:
            c = self._elegir_ventana(h, seat_x)
            if c is None:
                return False, TEXTO_SIN_VENTANA
        texto = TEXTO_BARRA_OK if c.es_barra else TEXTO_VENTANA_OK
        obj = Objetivo(int(c.hwnd), bool(c.es_barra), va._rect(c.rect))
        s = self.maquina.sentada
        if s is not None and s.objetivo.es_barra == obj.es_barra and (obj.es_barra or s.objetivo.hwnd == obj.hwnd):
            return True, texto
        frac = clamp((seat_x - obj.rect.izq) / max(1, obj.rect.ancho), 0.0, 1.0)
        t = self._reloj()
        snap = self.maquina.sentar_directo(obj, frac=frac)
        if not self._aplicar_snap(snap, t):
            return False, self._texto_ocupada()
        return True, texto

    def bajar(self, motivo: str = "usuario") -> bool:
        """Se baja. Si estaba cedida (p. ej. durante la pantalla grande), ya no se
        vuelve a sentar al acabar. True si había algo que deshacer."""
        if self.maquina.sentada is not None:
            self._levantar(motivo)
            return True
        if self._cedido is not None:
            self._cedido = None
            pr = self._prioridad()
            if pr is not None:
                try:
                    pr.olvidar("sentada")
                except Exception:
                    pass
            self._emitir()
            return True
        return False

    def _texto_ocupada(self) -> str:
        est = self._estado_bus()
        for campo, texto in _MOTIVOS_OCUPADA.items():
            v = getattr(est, "bailando" if campo == "mmd" else campo, None) if est is not None else None
            if (campo == "mmd" and v == "mmd") or (campo != "mmd" and v):
                return f"Ahora no puedo sentarme: {texto}."
        return "Ahora no puedo sentarme."

    def _elegir_ventana(self, h: int, seat_x: int) -> Optional[va.Candidata]:
        api = self._va()
        pid = os.getpid()
        cands = va.listar_candidatas(api, excluir_pid=pid, permitir=self._permitir(), ventanas=True, barras=False)
        if not cands:
            return None
        try:
            mon = api.monitor(h)
        except Exception:
            mon = None
        m = va._rect(mon[0]) if mon else None
        try:
            activa = int(api.activa() or 0)
        except Exception:
            activa = 0

        def valida(c: va.Candidata) -> bool:
            r = va._rect(c.rect)
            if m is not None:
                cx, cy = r.centro
                if not m.contiene(cx, cy) or r.arriba < m.arriba:
                    return False
            x = int(clamp(seat_x, r.izq + 1, r.der - 1))
            return not va.ocluida_en(api, c.hwnd, x, r.arriba + 2, excluir_pid=pid)

        for c in cands:
            if c.hwnd == activa and valida(c):
                return c
        for c in cands:
            if valida(c):
                return c
        return None

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["asiento"] = self
        if self._en_ui is not None:
            base["en_ui"] = self._en_ui
        return base

    def herramientas(self) -> dict:
        """{"asistente_sentarse": handler(args, ctx)}."""
        return {"asistente_sentarse": lambda args=None, ctx=None: na.herramienta(args, self._ctx(ctx))}

    # ── Arrastre ─────────────────────────────────────────────────────────────────
    def _on_arrastre(self, on: bool) -> None:
        if on:
            self._empezar_arrastre()
        else:
            self._acabar_arrastre()

    def _buscar_algo(self) -> bool:
        """¿Hay que buscar sitio durante este arrastre?"""
        if self._juego():
            return False
        return self.maquina.sentada is not None or self._cfg_ventanas() or self._cfg_barra()

    def _empezar_arrastre(self) -> None:
        m = self._asistente
        if m is None or self._arrastrando:
            return
        if self._cedido is not None:
            # La mueves mientras estaba cedida (MMD, juego…): al acabar ya no vuelve a su sitio.
            self.bajar("usuario")
        t = self._reloj()
        self._arrastrando = True
        self._manual = not self._nativa()
        self._c0 = self._cursor()
        self._inicio = self._rect_m()
        self._t_ult = t
        self._t_tic.stop()
        self.maquina.al_pulsar(t, self._c0)
        if self.maquina.sentada is not None and not self._manual:
            self._levantar("arrastre")                 # el SO mueve la ventana: no puede deslizar
        self._pedir_punto()
        if self._inicio is not None:
            self._asegurar_rel(self._inicio)
        if self._manual and self._buscar_algo():
            _llamar(m, "set_arrastre_delegado", self._delegado)
            self._delegado_puesto = True
            self._refrescar()
            self._t_enum.start(self.ENUM_MS if self._cfg_ventanas() else self.BARRA_MS)
            self._intervalo_arrastre()
        self._emitir()

    def _cortar_arrastre(self) -> None:
        """Deja el arrastre sin intentar sentarse (asistente cambiada, detener)."""
        self._t_enum.stop()
        self._t_arrastre.stop()
        if self._delegado_puesto:
            _llamar(self._asistente, "set_arrastre_delegado", None)
            self._delegado_puesto = False
        self.maquina.al_soltar(self._reloj())
        self._arrastrando = False
        self._candidatas = []

    def _acabar_arrastre(self) -> None:
        if not self._arrastrando:
            return
        t = self._reloj()
        self._t_enum.stop()
        self._t_arrastre.stop()
        con_delegado = self._delegado_puesto
        if self._delegado_puesto:
            _llamar(self._asistente, "set_arrastre_delegado", None)
            self._delegado_puesto = False
        snap = None
        # Manual: un último intento con la sonda (el medio segundo sobre el borde ya contado
        # por las muestras). Nativo (sprites): el SO la movió; se enumera UNA vez al soltar.
        intentar = (self.maquina.sentada is None and self._buscar_algo()
                    and (con_delegado if self._manual else True))
        if not intentar:
            self.maquina.al_soltar(t)
        else:
            if not self._manual:
                self._refrescar()                        # una sola enumeración al soltar
            rm = self._rect_m()
            if not self._manual:
                self._pedir_punto()                      # síncrono en los sprites
            if rm is not None:
                self._asegurar_rel(rm)
                dpr = self._dpr()
                self.maquina.offset_px = int(round(self._offset() * dpr))
                snap = self.maquina.al_soltar(
                    t, sonda=punto_fisico(rm, self._sonda_rel, dpr), radio=radio_sonda(rm.alto, dpr, self.maquina.p),
                    candidatas=self._candidatas, ocluida=self._ocluida, cursor=self._cursor(), dpr=dpr,
                    asiento=punto_fisico(rm, self._asiento_rel, dpr), muestreado=self._manual)
            else:
                self.maquina.al_soltar(t)
        self._arrastrando = False
        self._candidatas = []
        if snap is not None:
            self._aplicar_snap(snap, t)
        elif self.maquina.sentada is not None:
            self._armar_tic()
        self._emitir()

    def _delegado(self) -> bool:
        """En cada movimiento del arrastre manual. True = ya movió la ventana."""
        if not self._arrastrando or self._asistente is None or self._inicio is None or self._c0 is None:
            return False
        c = self._cursor()
        if c is None:
            return False
        t = self._reloj()
        dt, self._t_ult = t - self._t_ult, t
        h = self._hwnd()
        ini = self._inicio
        actual = self._rect_m()                          # el tamaño cambia si cruza a un monitor con otro DPI
        ancho, alto = (actual.ancho, actual.alto) if actual is not None else (ini.ancho, ini.alto)
        lx, ly = ini.izq + c[0] - self._c0[0], ini.arriba + c[1] - self._c0[1]
        libre = va.Rect(lx, ly, lx + ancho, ly + alto)
        dpr = self._dpr()
        self._asegurar_rel(ini)
        self.maquina.offset_px = int(round(self._offset() * dpr))
        sonda = punto_fisico(libre, self._sonda_rel, dpr)
        asiento = punto_fisico(libre, self._asiento_rel, dpr)
        radio = radio_sonda(alto, dpr, self.maquina.p)
        cands = self._candidatas_con_objetivo()
        res = self.maquina.al_arrastrar(t, c, sonda, radio, cands, self._ocluida, dpr=dpr, asiento=asiento)
        if isinstance(res, Snap):
            self._aplicar_snap(res, t)
        elif isinstance(res, Desnap):
            self._tras_levantar(res.motivo)
        if self.maquina.sentada is not None:
            rm = self._rect_m() or actual or libre
            mov = self.maquina.pin(t, dt, self._rect_objetivo(rm), self._asiento_rel, rm, arrastrando=True,
                                   cursor=c, dpr=dpr)
            if isinstance(mov, Desnap):
                self._tras_levantar(mov.motivo)
            else:
                if isinstance(mov, Mover):
                    self._win.mover(h, mov.x, mov.y)
                self._intervalo_arrastre()
                return True
        self._intervalo_arrastre()
        try:
            return bool(self._win.mover(h, lx, ly))
        except Exception:
            return False

    def _tic_arrastre(self) -> None:
        """Arrastre manual con el ratón QUIETO: sin MouseMove la asistente no llama al
        delegado, así que aquí se da la muestra con la última posición (el medio segundo
        sobre el borde cuenta y el SmoothDamp termina)."""
        if not (self._arrastrando and self._delegado_puesto):
            self._t_arrastre.stop()
            return
        if (self._reloj() - self._t_ult) * 1000.0 >= self.RAPIDO_MS / 2.0:   # si no acaba de moverse
            self._delegado()
        self._intervalo_arrastre()

    def _intervalo_arrastre(self) -> None:
        if not (self._arrastrando and self._delegado_puesto):
            return
        ms = self.RAPIDO_MS if self.maquina.suavizando else self.ARRASTRE_MS
        if self._t_arrastre.interval() != ms:
            self._t_arrastre.setInterval(ms)
        if not self._t_arrastre.isActive():
            self._t_arrastre.start()

    def _refrescar(self) -> None:
        """Candidatas del arrastre (timer de 66 ms con ventanas, 250 ms con solo la barra)."""
        if not self._arrastrando or self._juego():
            self._candidatas = []
            return
        cands: List[Any] = []
        puede = self._puede()
        s = self.maquina.sentada
        if self._cfg_ventanas() and puede:
            try:
                cands.extend(va.listar_candidatas(self._va(), excluir_pid=os.getpid(), permitir=self._permitir(),
                                                  ventanas=True, barras=False))
            except Exception:
                _log.debug("asiento: no pude listar ventanas", exc_info=True)
        if (self._cfg_barra() and puede) or (s is not None and s.objetivo.es_barra):
            rm = self._rect_m() or self._inicio
            if s is not None and s.objetivo.es_barra:
                punto = self._punto_barra(s.objetivo, rm)
            else:
                punto = punto_fisico(rm, self._sonda_rel, self._dpr()) if rm is not None and self._sonda_rel else None
            b = self._barra_en(punto, rm)
            if b is not None:
                cands.append(b)
        self._candidatas = cands

    def _candidatas_con_objetivo(self) -> List[Any]:
        """Las candidatas, con el objetivo actual (si está sentada) al día."""
        cands = list(self._candidatas)
        s = self.maquina.sentada
        if s is None:
            return cands
        r = self._rect_objetivo(self._rect_m() or self._inicio)
        if r is None:
            return [c for c in cands if not self._es_objetivo(c, s.objetivo)]
        nueva = va.Candidata(s.objetivo.hwnd, r, s.objetivo.es_barra, True)
        return [c for c in cands if not self._es_objetivo(c, s.objetivo)] + [nueva]

    @staticmethod
    def _es_objetivo(c: Any, o: Objetivo) -> bool:
        return bool(c.es_barra) == o.es_barra and (o.es_barra or int(c.hwnd) == o.hwnd)

    def _rect_objetivo(self, rm: Optional[va.Rect]) -> Optional[va.Rect]:
        s = self.maquina.sentada
        if s is None:
            return None
        if s.objetivo.es_barra:
            b = self._barra_en(self._punto_barra(s.objetivo, rm), rm)
            return b.rect if b is not None else None
        try:
            r = self._va().rect_visible(s.objetivo.hwnd)
        except Exception:
            return None
        return va._rect(r) if r else None

    # ── Punto de asiento ─────────────────────────────────────────────────────────
    def _asegurar_rel(self, rm: va.Rect) -> None:
        """Mientras la página no mide: (w/2, 0.78·h) en px lógicos."""
        if self._asiento_rel is not None and self._sonda_rel is not None:
            return
        d = self._dpr()
        p = (rm.ancho / d / 2.0, rm.alto / d * ALTO_ASIENTO_DEFECTO)
        self._asiento_rel = self._asiento_rel or p
        self._sonda_rel = self._sonda_rel or p

    def _pedir_punto(self) -> None:
        f = getattr(self._asistente, "punto_asiento", None)
        if not callable(f):
            return
        gen = self._gen
        try:
            f(lambda p, g=gen: self._on_punto(p, g))
        except Exception:
            _log.debug("asiento: la asistente no dio el punto de asiento", exc_info=True)

    def _on_punto(self, p: Any, gen: int) -> None:
        if gen != self._gen:
            return                                        # pedido antes de sentarse o levantarse
        pt = leer_punto(p)
        if pt is None:
            return
        a, s = pt
        antes = self._asiento_rel
        self._asiento_rel, self._sonda_rel = a, s
        self._medido = True
        if self.maquina.sentada is None:
            self._rel_de_pie = (a, s)                     # la pose de pie (para después de levantarse)
        if self.maquina.sentada is not None and not self._arrastrando:
            if antes is None or abs(a[0] - antes[0]) > 1 or abs(a[1] - antes[1]) > 1:
                self._rect_obj_prev = None
                self._tic()                               # vuelve a clavar ya

    def _on_asiento_medido(self, p: Any, gen: int) -> None:
        """El `cb` de `asistente.asiento(True, …)`: el asiento con la pose completa."""
        if gen != self._gen or self.maquina.sentada is None:
            return
        pt = leer_punto(p)
        if pt is None:
            return
        self._asiento_rel, self._sonda_rel = pt
        self._medido = True
        self.maquina.suavizar()
        if not self._arrastrando:
            self._armar_tic()

    def _remedir(self, *_args) -> None:
        if self.maquina.sentada is not None:
            self._pedir_punto()

    def _conectar_pantalla(self) -> None:
        if self._pantalla_qt is not None:
            return
        wh = getattr(self._asistente, "windowHandle", None)
        try:
            w = wh() if callable(wh) else None
        except Exception:
            w = None
        s = getattr(w, "screenChanged", None) if w is not None else None
        if s is not None and hasattr(s, "connect"):
            try:
                s.connect(self._remedir)
                self._pantalla_qt = w
            except (TypeError, RuntimeError):
                pass

    def _desconectar_pantalla(self) -> None:
        w, self._pantalla_qt = self._pantalla_qt, None
        if w is not None:
            try:
                w.screenChanged.disconnect(self._remedir)
            except (TypeError, RuntimeError, AttributeError):
                pass

    # ── Sentarse y levantarse ────────────────────────────────────────────────────
    def _aplicar_snap(self, snap: Snap, t: float) -> bool:
        """Pide la actividad a la tabla y, si la da, la sienta de verdad."""
        pr = self._prioridad()
        if pr is not None:
            try:
                r = pr.iniciar("sentada", snap.modo)
            except Exception:
                _log.exception("asiento: la tabla de prioridades falló")
                r = False
            if not r:
                self.maquina.anular(t)
                self._emitir()
                return False
        self._cedido = None
        self._gen += 1
        self._aplicar_visual(snap, t, provisional=True)
        return True

    def _aplicar_visual(self, snap: Snap, t: float, *, provisional: bool) -> None:
        m = self._asistente
        gen = self._gen
        if provisional and self._sonda_rel is not None:
            self._asiento_rel = self._sonda_rel          # clavado provisional con la sonda
        rm = self._rect_m()
        if rm is not None:
            self._asegurar_rel(rm)
        _llamar(m, "asiento", True, snap.modo, snap.variante, cb=lambda p, g=gen: self._on_asiento_medido(p, g))
        self._orden_z(snap, t, forzar=True)
        self._rect_obj_prev = None
        self._t_remedir.start()
        self._conectar_pantalla()
        if not self._arrastrando:
            self._armar_tic()
        try:
            self.sentada.emit(snap.modo, int(snap.variante))
        except RuntimeError:
            pass
        self._emitir()

    def _levantar(self, motivo: str) -> None:
        d = self.maquina.levantar(motivo)
        self._tras_levantar(d.motivo)

    def _tras_levantar(self, motivo: str, *, terminar: bool = True) -> None:
        self._gen += 1
        self._t_tic.stop()
        self._t_remedir.stop()
        self._desconectar_pantalla()
        self._rect_obj_prev = None
        m = self._asistente
        _llamar(m, "asiento", False)
        _llamar(m, "restaurar_orden_z")
        if motivo != "cede":
            # De pie otra vez: fuera el punto de la pose sentada (en la misma pasada de un
            # arrastre, la sonda sentada encajaría con el pecho y saltaría). La cesión lo
            # conserva: `reanudar` la vuelve a sentar con él.
            if self._rel_de_pie is not None:
                self._asiento_rel, self._sonda_rel = self._rel_de_pie
            else:
                self._asiento_rel = self._sonda_rel = None
                self._medido = False
            if self._arrastrando:
                self._pedir_punto()                       # y se vuelve a medir de pie
        if terminar:
            pr = self._prioridad()
            if pr is not None:
                try:
                    pr.terminar("sentada")
                except Exception:
                    _log.exception("asiento: no pude terminar la actividad")
        try:
            self.levantada.emit(str(motivo))
        except RuntimeError:
            pass
        self._emitir()

    def _orden_z(self, snap: Snap, t: float, *, forzar: bool) -> None:
        h = self._hwnd()
        if not h:
            return
        o = snap.objetivo
        try:
            if o.es_barra:
                if forzar or (t - self._t_topmost) * 1000.0 >= self.TOPMOST_BARRA_MS:
                    self._win.set_encima(h, True)
                    self._t_topmost = t
            elif forzar or not self._win.encima_de(h, o.hwnd):
                self._win.colocar_sobre(h, o.hwnd)
        except Exception:
            _log.debug("asiento: no pude ordenar la ventana", exc_info=True)

    # ── Sentada y quieta ─────────────────────────────────────────────────────────
    def _armar_tic(self) -> None:
        if self.maquina.sentada is None or self._arrastrando:
            return
        self._t_ult = self._reloj()
        self._ajustar_intervalo(self._t_ult)
        if not self._t_tic.isActive():
            self._t_tic.start()

    def _ajustar_intervalo(self, t: float) -> None:
        ms = self.RAPIDO_MS if (self.maquina.suavizando or t < self._rapido_hasta) else self.TIC_MS
        if self._t_tic.interval() != ms:
            self._t_tic.setInterval(ms)

    def _tic(self) -> None:
        s = self.maquina.sentada
        if s is None or self._arrastrando or self._asistente is None:
            self._t_tic.stop()
            return
        t = self._reloj()
        dt, self._t_ult = t - self._t_ult, t
        h = self._hwnd()
        if not h:
            self._levantar("cerrada")
            return
        rm = self._rect_m()
        if rm is None:
            return
        o = s.objetivo
        if o.es_barra:
            b = self._barra_en(self._punto_barra(o, rm), rm)
            if b is None:
                self._levantar("cerrada")
                return
            rect_obj = va._rect(b.rect)
        else:
            api = self._va()
            d = self.maquina.comprobar(va.estado_ventana(api, o.hwnd))
            if d is not None:
                self._tras_levantar(d.motivo)
                return
            try:
                r = api.rect_visible(o.hwnd)
                mon = api.monitor(o.hwnd)
            except Exception:
                r, mon = None, None
            if r is None:
                self._levantar("cerrada")
                return
            rect_obj = va._rect(r)
            if mon and rect_obj.arriba < va._rect(mon[0]).arriba:
                self._levantar("fuera")                  # el borde se fue por arriba de su monitor
                return
        if self._rect_obj_prev is not None and rect_obj != self._rect_obj_prev:
            self._rapido_hasta = t + self.RAPIDO_S       # se mueve: 60 Hz un rato
        self._rect_obj_prev = rect_obj
        self._asegurar_rel(rm)
        dpr = self._dpr()
        self.maquina.offset_px = int(round(self._offset() * dpr))
        mov = self.maquina.pin(t, dt, rect_obj, self._asiento_rel, rm, arrastrando=False, dpr=dpr)
        if isinstance(mov, Desnap):
            self._tras_levantar(mov.motivo)
            return
        if isinstance(mov, Mover):
            self._win.mover(h, mov.x, mov.y)
        if self.maquina.sentada is not None:
            self._orden_z(self.maquina.sentada, t, forzar=False)
        self._ajustar_intervalo(t)

    # ── Bus ──────────────────────────────────────────────────────────────────────
    def _on_bus(self, estado: Any = None, cambios: Any = None) -> None:
        cambios = cambios if isinstance(cambios, dict) else {}
        if "visible" in cambios and estado is not None and not getattr(estado, "visible", True):
            if self.maquina.sentada is not None:
                self.bajar("oculta")
        if "juego" in cambios and estado is not None and getattr(estado, "juego", False):
            self._candidatas = []
            self._t_enum.stop()                         # con un juego delante no se enumera
        if "juego" in cambios:
            self._emitir()


__all__ = ("ControlAsiento", "leer_punto", "TEXTO_BARRA_OK", "TEXTO_VENTANA_OK", "TEXTO_VENTANAS_OFF",
           "TEXTO_JUEGO", "TEXTO_SIN_VENTANA", "TEXTO_SIN_BARRA", "TEXTO_SIN_ASISTENTE")
