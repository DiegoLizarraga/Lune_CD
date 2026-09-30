"""
ui/escritorio.py — Servicios de escritorio de Lune: un solo sitio para las
piezas que viven fuera de la ventana principal (alarmas, pantalla grande, modo
juego, detector de música, Discord, Minecraft, atajos, bandeja, comida…).

Para qué sirve
--------------
Las funciones portadas de Mate-Engine necesitan tres cosas en común:

1. Un estado compartido de la asistente («¿está sentada? ¿bailando? ¿hay un juego
   delante?»). Es `self.estado`, un `nucleo.estado_asistente.BusEstado` único: la
   presencia de Discord, el radial, el salvapantallas o Minecraft lo LEEN de aquí
   en vez de preguntarle a la ventana de la asistente.
2. Una tabla de prioridades para las máquinas que se pisan (crítica b.6):
   juego > alarma > grande = salvapantallas > mmd > sentada > comida > baile > idle.
   Es `self.prioridad`: decide con `nucleo.estado_asistente` y, al ceder o reanudar
   una actividad, avisa a su controlador para que lo haga físicamente (levantarla
   de la barra, pausar el MMD, volver a sentarla…).
3. Un registro de controladores con el mismo ciclo de vida: `registrar(nombre,
   controlador, actividades)`, `iniciar()`, `detener()`, `set_asistente(ventana)`.
   Los cortes siguientes enchufan aquí sus controladores (alarmas, grande, juego,
   musica, discord, minecraft, atajos, bandeja, despachador, comida, frases,
   recorte) sin tocar main.py ni web_bridge.py cada vez. Hoy el registro está vacío.
4. Las herramientas del modelo que dependen de la app (`cambiar_voz` hoy; las de
   la asistente y las alarmas en cortes siguientes): `conectar_herramientas(tools)`
   las enchufa en el ToolManager de quien lleva la app, y
   `registrar_herramienta(nombre, fn)` deja a un controlador añadir la suya.

Lo instancia una vez quien lleva la app: `LuneBridge` (piel web) o
`LuneCDWindow` (nativa), como `self.escritorio` (las dos no conviven en el
mismo proceso). Cada vez que crean, recrean o sueltan la asistente flotante
llaman a `set_asistente(ventana | None)`, y al salir a `cerrar()`. Así la cola de
eventos de la página (`evento_js` de CompanionFlotante) y el BusEstado tienen
receptor desde el primer corte. Este módulo es solo el adaptador Qt: la lógica
vive en nucleo/ y servicios/ y se prueba sin pantalla.

Contrato de un controlador (todo opcional, por duck typing):
    iniciar()                      arrancar (timers, hilos); se llama en iniciar()
                                   o al registrarlo si ya estaba iniciado
    detener()                      parar y soltar recursos (orden inverso)
    set_asistente(ventana | None)    la asistente flotante cambió
    ceder(cesion)                  la tabla le quita su actividad: deshacerla ya
    reanudar(cesion)               la actividad que la interrumpió acabó: rehacerla
    evento_asistente(tipo, datos)    evento de la página de la asistente (luneEventos)

Hilos: `BusEstado` avisa en el hilo que hizo el cambio. `estado_cambio` se
emite siempre en el hilo de este objeto (el de Qt) y en el orden de los
cambios: si el cambio vino de otro hilo, se reenvía en cola, y mientras quede
alguno en cola los del hilo de Qt también se encolan detrás.
"""
from __future__ import annotations

import inspect
import logging
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

from nucleo import estado_asistente as em
from nucleo.estado_asistente import BusEstado, Cesion, EstadoAsistente, Resultado

_log = logging.getLogger("lune.escritorio")


def crear_asistente(cls: Any, *args, **kw) -> Any:
    """Crea la asistente flotante (CompanionFlotante, AvatarOverlay…) SIN su propio
    icono de bandeja: desde el corte 4 la bandeja es una sola (ui/bandeja.BandejaLune,
    que además le llama a quitar_bandeja() por si acaso). Una clase sin el parámetro
    `bandeja` (anterior al corte 4, o un doble de test) se crea como siempre."""
    init = getattr(cls, "__init__", None)
    try:
        params = inspect.signature(init).parameters if init not in (None, object.__init__) else {}
        acepta = "bandeja" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        acepta = False
    if acepta:
        kw.setdefault("bandeja", False)
    return cls(*args, **kw)


class PuenteHilo:
    """Emite la señal `senal` de `dueno` (un QObject) desde OTRO hilo sin tocarlo nunca
    borrado. Es lo que un controlador da como callback a su hilo (la presencia de
    Discord, las herramientas del modelo que corren en el Ejecutor…) en vez de un
    `self.senal.emit` ligado: ese `emit` guardado, llamado cuando el controlador ya se
    borró (cambio de interfaz con el hilo aún vivo), da AttributeError o una access
    violation. Aquí la señal se resuelve en CADA llamada, se mira que el objeto de C++
    siga vivo y, cerrado, no hace nada. `cerrar()` (en `detener`, y solo al destruirse
    el dueño) espera a una llamada a medias: al volver, ya no sale ninguna más.

        self._puente = PuenteHilo(self, "_desde_hilo")    # hilo.on_algo = self._puente
        ...
        self._puente.cerrar()                              # en detener(), antes de soltar el hilo
    """

    def __init__(self, dueno: QObject, senal: str):
        self._lock = threading.Lock()
        self._dueno: Optional[QObject] = dueno
        self._senal = str(senal)
        try:
            dueno.destroyed.connect(self.cerrar)   # borrado sin detener (cierre de la app)
        except (AttributeError, TypeError, RuntimeError):
            pass

    @property
    def abierto(self) -> bool:
        return self._dueno is not None

    def cerrar(self, *_args) -> None:
        with self._lock:
            self._dueno = None

    def __call__(self, *args: Any) -> None:
        with self._lock:
            d = self._dueno
            if d is None:
                return
            try:
                if sip.isdeleted(d):
                    self._dueno = None
                    return
                getattr(d, self._senal).emit(*args)
            except (RuntimeError, AttributeError):
                self._dueno = None


def _llamar(obj: Any, metodo: str, *args) -> Any:
    """Llama a `obj.metodo(*args)` si existe. Un fallo se registra y no se propaga:
    un controlador roto no puede tumbar a los demás ni el arranque de la app."""
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("escritorio: %s.%s falló", type(obj).__name__, metodo)
        return None


class Prioridad:
    """La tabla de prioridades de `nucleo.estado_asistente` + las acciones físicas.

    `iniciar(actividad, valor)` pregunta a la tabla y, si se permite, llama a
    `ceder(c)` del controlador de cada actividad interrumpida. `terminar(actividad)`
    la apaga y reanuda lo que se había interrumpido (con `reanudar(c)` de su
    controlador). Quien pide la actividad sigue siendo quien la HACE en la asistente.
    """

    TABLA = em.PRIORIDAD
    ACTIVIDADES = em.ACTIVIDADES

    def __init__(self, bus: BusEstado, controlador_de: Callable[[str], Any]):
        self._bus = bus
        self._controlador_de = controlador_de

    def puede(self, actividad: str) -> bool:
        return em.puede(actividad, self._bus.actual())

    def que_ceder(self, actividad: str) -> List[str]:
        return em.que_ceder(actividad, self._bus.actual())

    def activas(self) -> List[str]:
        return em.actividades_activas(self._bus.actual())

    def iniciar(self, actividad: str, valor: Any = None) -> Resultado:
        """Empieza `actividad` si la tabla lo permite. Falso (con `.motivo`) si no."""
        r = self._bus.iniciar_actividad(actividad, valor)
        if r:
            for c in r.ceder:
                self._avisar(c, "ceder")
        return r

    def terminar(self, actividad: str) -> List[Cesion]:
        """Apaga `actividad` y reanuda lo interrumpido. Devuelve lo que se reanudó.

        `terminar_actividad` ya devuelve solo reanudaciones compatibles entre sí
        (de mayor a menor prioridad). Si aun así una no puede empezar (otro hilo
        empezó algo entre medias), no se pierde: queda pendiente de lo que la
        bloquea."""
        hechas: List[Cesion] = []
        for c in self._bus.terminar_actividad(actividad):
            r = self._bus.iniciar_actividad(c.actividad, c.valor)
            if not r:
                self._bus.reanudar_despues(c, r.motivo)
                continue
            for x in r.ceder:
                self._avisar(x, "ceder")
            self._avisar(c, "reanudar")
            hechas.append(c)
        return hechas

    def olvidar(self, actividad: Optional[str] = None) -> None:
        """No reanudar `actividad` (p. ej. «bájate» durante la pantalla grande)."""
        self._bus.olvidar_reanudar(actividad)

    def _avisar(self, c: Cesion, metodo: str) -> None:
        ctl = self._controlador_de(c.actividad)
        if ctl is not None:
            _llamar(ctl, metodo, c)


class ServiciosEscritorio(QObject):
    """Estado compartido, tabla de prioridades y registro de controladores de escritorio."""

    # (EstadoAsistente, {campo: (antes, después)}), siempre en el hilo de Qt.
    # `object` y no `dict`: dict pasaría por QVariantMap y las tuplas saldrían listas.
    estado_cambio = pyqtSignal(object, object)
    # Evento de la página de la asistente (CompanionFlotante.evento_js), reenviado.
    evento_asistente = pyqtSignal(str, dict)
    # La asistente flotante cambió (ventana o None).
    asistente_cambio = pyqtSignal(object)

    _estado_desde_hilo = pyqtSignal(object, object)

    def __init__(self, config=None, *, voice=None, ai=None, bridge=None,
                 bus: Optional[BusEstado] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self.voice = voice
        self.ai = ai
        self.bridge = bridge
        self.estado: BusEstado = bus if bus is not None else BusEstado()
        self.prioridad = Prioridad(self.estado, self._controlador_de_actividad)
        self._controladores: Dict[str, Any] = {}          # nombre → controlador (orden de registro)
        self._actividades: Dict[str, str] = {}             # actividad → nombre del controlador
        self._asistente: Optional[QObject] = None
        self._iniciado = False
        self._hilo = threading.get_ident()                 # hilo de Qt que lo creó
        # Entregas de estado_cambio que esperan en la cola de eventos. Mientras
        # haya alguna, las del hilo de Qt también se encolan (ver _on_estado).
        self._lock_orden = threading.Lock()
        self._en_cola = 0
        self._estado_desde_hilo.connect(self._reemitir_estado, Qt.ConnectionType.QueuedConnection)
        self._cancelar_suscripcion = self.estado.suscribir(self._on_estado)
        # Herramientas del modelo que dependen de esta app (corte 2): se enchufan
        # en el ToolManager con conectar_herramientas(); las que registren los
        # controladores de cortes siguientes, con registrar_herramienta().
        self.tools = None
        self._herramientas: Dict[str, Callable[[dict, Any], Any]] = {}

    # ── Herramientas del modelo ────────────────────────────────────────────────
    def conectar_herramientas(self, tools: Any) -> None:
        """Enchufa en `tools` (servicios.tools.ToolManager) los handlers de esta app.

        Hoy: `cambiar_voz` con la config y el VoiceEngine de este modo. Más las
        que hayan pedido los controladores con `registrar_herramienta`. Los
        Ejecutores creados con `tools.crear_ejecutor()` los reciben también.
        """
        self.tools = tools
        if tools is None:
            return
        conectar_voz = getattr(tools, "conectar_voz", None)
        if callable(conectar_voz):
            try:
                conectar_voz(self.config, self.voice)
            except Exception:
                _log.exception("escritorio: no pude enchufar cambiar_voz")
        for nombre, fn in list(self._herramientas.items()):
            _llamar(tools, "registrar_handler", nombre, fn)

    def registrar_herramienta(self, nombre: str, fn: Callable[[dict, Any], Any]) -> None:
        """Handler `fn(args, ctx) -> str` de una herramienta del catálogo (alarmas,
        asistente…). Llega al ToolManager ya conectado o al que se conecte después."""
        self._herramientas[str(nombre)] = fn
        if self.tools is not None:
            _llamar(self.tools, "registrar_handler", str(nombre), fn)

    def quitar_herramienta(self, nombre: str) -> None:
        self._herramientas.pop(str(nombre), None)
        if self.tools is not None:
            _llamar(self.tools, "quitar_handler", str(nombre))

    # ── Registro de controladores ──────────────────────────────────────────────
    def registrar(self, nombre: str, controlador: Any, actividades: Iterable[str] = ()) -> Any:
        """Añade (o sustituye) un controlador. `actividades`: las de la tabla que
        hace físicamente (recibirá ceder/reanudar de ellas)."""
        nombre = str(nombre)
        actividades = tuple(actividades)
        for a in actividades:
            if a not in em.PRIORIDAD:
                raise ValueError(f"actividad desconocida: {a!r}")
        if nombre in self._controladores:
            self.quitar(nombre)
        self._controladores[nombre] = controlador
        for a in actividades:
            self._actividades[a] = nombre
        if self._iniciado:
            _llamar(controlador, "iniciar")
        if self._asistente is not None:
            _llamar(controlador, "set_asistente", self._asistente)
        return controlador

    def quitar(self, nombre: str) -> bool:
        ctl = self._controladores.pop(nombre, None)
        if ctl is None:
            return False
        for a in [a for a, n in self._actividades.items() if n == nombre]:
            del self._actividades[a]
        if self._iniciado:
            _llamar(ctl, "detener")
        return True

    def obtener(self, nombre: str) -> Any:
        return self._controladores.get(nombre)

    def controladores(self) -> Dict[str, Any]:
        return dict(self._controladores)

    def _controlador_de_actividad(self, actividad: str) -> Any:
        nombre = self._actividades.get(actividad)
        return self._controladores.get(nombre) if nombre else None

    # ── Ciclo de vida ──────────────────────────────────────────────────────────
    @property
    def iniciado(self) -> bool:
        return self._iniciado

    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        for ctl in list(self._controladores.values()):
            _llamar(ctl, "iniciar")

    def detener(self) -> None:
        if not self._iniciado:
            return
        self._iniciado = False
        for ctl in reversed(list(self._controladores.values())):
            _llamar(ctl, "detener")

    # ── Asistente flotante ───────────────────────────────────────────────────────
    @property
    def asistente(self) -> Optional[QObject]:
        return self._asistente

    def set_asistente(self, ventana: Optional[QObject], render: Optional[str] = None) -> None:
        """La asistente flotante actual (CompanionFlotante, AvatarOverlay…) o None.

        Le pasa el BusEstado si sabe recibirlo (`set_bus_estado`), sigue su
        visibilidad (`visibilidad(bool)`) y reenvía sus eventos (`evento_js`).
        """
        if ventana is self._asistente:
            return
        self._soltar_asistente()
        self._asistente = ventana
        if ventana is None:
            # pensando=False apaga solo lo de la asistente (comentar la pantalla); el chat
            # de la ventana sigue pensando si lo estaba (BusEstado.pensar).
            self.estado.actualizar(render="", visible=False, arrastrando=False,
                                   durmiendo=False, hablando=False, pensando=False)
        else:
            self._conectar(ventana, "visibilidad", self._on_visibilidad)
            self._conectar(ventana, "evento_js", self._on_evento_js)
            self._conectar(ventana, "destroyed", self._on_asistente_destruida)
            r = render if render is not None else getattr(ventana, "render", "")
            visible = False
            try:
                visible = bool(ventana.isVisible())
            except Exception:
                pass
            self.estado.actualizar(render=str(r or ""), visible=visible)
            _llamar(ventana, "set_bus_estado", self.estado)
        for ctl in list(self._controladores.values()):
            _llamar(ctl, "set_asistente", ventana)
        self.asistente_cambio.emit(ventana)

    def _soltar_asistente(self, destruida: bool = False) -> None:
        vieja, self._asistente = self._asistente, None
        if vieja is None or destruida:
            return
        for senal, slot in (("visibilidad", self._on_visibilidad),
                            ("evento_js", self._on_evento_js),
                            ("destroyed", self._on_asistente_destruida)):
            try:
                getattr(vieja, senal).disconnect(slot)
            except (AttributeError, TypeError, RuntimeError):
                pass
        _llamar(vieja, "set_bus_estado", None)

    @staticmethod
    def _conectar(obj: QObject, senal: str, slot) -> None:
        s = getattr(obj, senal, None)
        if s is not None and hasattr(s, "connect"):
            try:
                s.connect(slot)
            except (TypeError, RuntimeError):
                pass

    @pyqtSlot(bool)
    def _on_visibilidad(self, visible: bool) -> None:
        self.estado.actualizar(visible=bool(visible))

    @pyqtSlot(str, dict)
    def _on_evento_js(self, tipo: str, datos: dict) -> None:
        self.evento_asistente.emit(tipo, datos)
        for ctl in list(self._controladores.values()):
            _llamar(ctl, "evento_asistente", tipo, datos)

    def _on_asistente_destruida(self, *_args) -> None:
        self._soltar_asistente(destruida=True)
        # Como en set_asistente(None): pensando=False apaga solo la fuente de la asistente
        # (comentar la pantalla); el chat de la ventana sigue pensando si lo estaba.
        self.estado.actualizar(render="", visible=False, arrastrando=False,
                               durmiendo=False, hablando=False, pensando=False)
        for ctl in list(self._controladores.values()):
            _llamar(ctl, "set_asistente", None)
        self.asistente_cambio.emit(None)

    # ── Estado → señal de Qt ───────────────────────────────────────────────────
    def _on_estado(self, estado: EstadoAsistente, cambios: Dict[str, Tuple[Any, Any]]) -> None:
        """Del BusEstado (que avisa en orden, de uno en uno) a `estado_cambio`.

        Directo si viene del hilo de Qt y no hay nada encolado; si no, en cola.
        Así el orden de entrega es siempre el de los cambios: un cambio de otro
        hilo que espera en la cola no puede llegar DESPUÉS de uno posterior hecho
        en el hilo de Qt (su foto vieja sería la última que ven los receptores).
        """
        try:
            with self._lock_orden:
                directo = threading.get_ident() == self._hilo and self._en_cola == 0
                if not directo:
                    self._en_cola += 1
            if directo:
                self.estado_cambio.emit(estado, dict(cambios))
            else:
                self._estado_desde_hilo.emit(estado, dict(cambios))
        except RuntimeError:
            pass                                        # el QObject ya se destruyó

    def _reemitir_estado(self, estado, cambios) -> None:
        # El contador baja DESPUÉS de emitir: un cambio que haga un receptor
        # durante esta entrega se encola detrás y no se adelanta a los pendientes.
        try:
            self.estado_cambio.emit(estado, cambios)
        finally:
            with self._lock_orden:
                self._en_cola = max(0, self._en_cola - 1)

    def cerrar(self) -> None:
        """Al salir de la app: detener todo y soltar la asistente y el bus."""
        self.detener()
        self._soltar_asistente()
        cancelar, self._cancelar_suscripcion = self._cancelar_suscripcion, None
        if cancelar:
            cancelar()
