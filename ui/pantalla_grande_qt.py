"""
ui/pantalla_grande_qt.py — Pantalla grande y salvapantallas en la app (Qt).

`ControlPantallaGrande` es un controlador de `ServiciosEscritorio`
(ui/escritorio.py): lo crea y registra ui/montaje_ocio.montar_ocio con las
actividades «grande» y «salvapantallas» de la tabla de prioridades. La lógica
pura está en nucleo/pantalla_grande.py (MaquinaGrande, ReglaSalvapantallas).

PANTALLA GRANDE CON LA MASCOTA (VRM o animada con la página lista, `soporta_grande`)
  1. `prioridad.iniciar("grande")` (o "salvapantallas") ANTES de tocar la ventana:
     así el detector de juegos ve `grande` y no toma a Lune por un vídeo a
     pantalla completa (ui/modo_juego_qt._lune_a_pantalla_completa).
  2. Se guarda `mascota.geometria()` y `grande_fase("glide", {ms: 400})`.
  3. A los 400 ms: `set_geometria(<monitor de mayor intersección>)` en px
     lógicos y `grande_fase("entrar", {ms: 500})`.
  4. Activa. La salida es la inversa: "salir" 500 ms → la geometría exacta de
     antes → "volver" 400 ms → "fin" → `prioridad.terminar(...)`.
SIN MASCOTA A LA VISTA
  - Pedida a mano (atajo, radial, bandeja, herramienta) con avatar.render vrm o
    animado y QtWebEngine: se saca la mascota (`anfitrion.alternar_mascota()`),
    se espera como mucho 6 s a que su página esté lista y se cierra al salir.
  - En cualquier otro caso (sprites, nativa sin VRM, alarma o salvapantallas con
    la mascota guardada — decisión D2): ui/ventana_reloj.VentanaReloj, que se
    cierra con un clic en modo «grande».
SALIDA de la grande manual: el atajo, el radial, la bandeja, la herramienta o
`minutos`. La mascota no recibe teclado: Esc no sirve.

SALVAPANTALLAS (salvapantallas.*)
  - QTimer de 1 s: `win_entrada.segundos_inactivo()`; un mando en uso cuenta
    como actividad; `ReglaSalvapantallas` decide (juego, grande, alarma,
    arrastrando, menú, hablando, llamada, pensando, bailando, pantalla pedida por
    un vídeo). La mascota dormida cuenta como reposo.
  - Al activarse: pantalla grande con motivo «salvapantallas» y
    `mascota.set_salvapantallas(True, fondo_oscuro=…, reloj=…)` (la duerme); sin
    mascota lista, VentanaReloj("salvapantallas").
  - Salida: QTimer de 33 ms con `DetectorEntrada` (clic, tecla o mando; mover el
    ratón NO cuenta). Con `clic_sale_de_todo` sale de todo; si no, se queda en
    pantalla grande manual y despierta.

PRIORIDADES (nucleo/estado_mascota.py)
  - Entra un juego: `ceder` → salida inmediata, sin animación.
  - Suena una alarma con el salvapantallas puesto: `ceder(salvapantallas)` con
    `alarma` en el bus → si la alarma va a usar la pantalla grande
    (alarmas.pantalla_grande), sigue en pantalla grande con motivo «alarma» y la
    despierta (la alarma y la grande coexisten); si no (burbuja), sale ya del
    salvapantallas: nadie la sacaría de la grande al apagarse.
  - La alarma la pide ella misma: `entrar("alarma")` + `mostrar_alarma(texto)` y
    al apagarse `salir("alarma")` (solo sale si la metió la alarma). Red de
    seguridad: si la alarma deja de sonar (el bus apaga `alarma`) con la grande
    aún en motivo «alarma», sale sola.
  - La mascota de la pantalla grande se esconde (guardada en la bandeja…): sale ya
    (no se queda activa e invisible con `grande` en el bus).
  (Estas dos, escuchando `escritorio.estado_cambio` entre iniciar() y detener().)

Señales: `cambio(activa, motivo)`; `pedir_apagar_alarma` / `pedir_posponer_alarma`
(los botones de VentanaReloj; montar_ocio los lleva a ControlAlarmasQt).
"""
from __future__ import annotations

import importlib.util
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt6.QtCore import QObject, QRect, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCursor, QGuiApplication

from nucleo import pantalla_grande as pg
from nucleo.pantalla_grande import MaquinaGrande, ReglaSalvapantallas
from servicios import win_entrada as we

_log = logging.getLogger("lune.grande")

TIC_MAQUINA_MS = 30
TIC_INACTIVIDAD_MS = 1000
TIC_ENTRADA_MS = 33
TIC_ESPERA_MS = 100
ESPERA_MASCOTA_S = 6.0
GRACIA_ENTRADA_S = 1.0          # la entrada que lo abrió (soltar el clic de «Probar») no lo cierra
IGNORAR_CLIC_S = 0.6
RENDERS_PAGINA = ("vrm", "animado")

TEXTO_MOTIVO = {
    "juego": "hay un juego delante",
    "alarma": "hay una alarma sonando",
    "grande": "ya está en pantalla grande",
    "salvapantallas": "está puesto el salvapantallas",
    "arrastrando": "la están arrastrando",
    "menu_abierto": "hay un menú abierto",
    "hablando": "está hablando",
    "llamada": "está en una llamada",
}


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("pantalla grande: %s.%s falló", type(obj).__name__, metodo)
        return None


def _log_info(msg: str) -> None:
    try:
        from nucleo.utils import log_info
        log_info(msg)
    except Exception:
        _log.info(msg)


def webengine_disponible() -> bool:
    """¿Está QtWebEngine instalado? (sin importarlo: pesa y arranca Chromium)."""
    try:
        return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None
    except Exception:
        return False


def indice_mayor_interseccion(rect: QRect, pantallas: Sequence[QRect]) -> int:
    """Índice de la pantalla que más área comparte con `rect`; si ninguna, la que
    contiene su centro; si tampoco, 0 (Mate-Engine, AvatarBigScreenHandler :274-293)."""
    mejor, area_mejor = -1, 0
    for i, p in enumerate(pantallas):
        inter = rect.intersected(p)
        area = max(0, inter.width()) * max(0, inter.height()) if not inter.isEmpty() else 0
        if area > area_mejor:
            mejor, area_mejor = i, area
    if mejor >= 0:
        return mejor
    centro = rect.center()
    for i, p in enumerate(pantallas):
        if p.contains(centro):
            return i
    return 0


def _visible(w: Any) -> bool:
    if w is None or getattr(w, "cerrado", False):
        return False
    try:
        return bool(w.isVisible())
    except Exception:
        return False


def _soporta(m: Any) -> bool:
    v = getattr(m, "soporta_grande", False)
    if callable(v):
        try:
            v = v()
        except Exception:
            return False
    return bool(v)


class ControlPantallaGrande(QObject):
    """Pantalla grande (manual, herramienta, alarma) y salvapantallas."""

    cambio = pyqtSignal(bool, str)                  # (activa, motivo)
    pedir_apagar_alarma = pyqtSignal()
    pedir_posponer_alarma = pyqtSignal()

    def __init__(self, escritorio, config, *, anfitrion=None, en_ui=None, entrada=None, api_entrada=None,
                 fabrica_reloj: Optional[Callable[[], Any]] = None,
                 reloj: Callable[[], float] = time.monotonic,
                 hay_webengine: Optional[Callable[[], bool]] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.anfitrion = anfitrion
        self._en_ui = en_ui
        self._entrada = entrada
        self._api = api_entrada
        self._fabrica_reloj = fabrica_reloj
        self._reloj = reloj
        self._hay_webengine = hay_webengine if hay_webengine is not None else webengine_disponible
        self._maquina = MaquinaGrande()
        self._regla = ReglaSalvapantallas.desde_config(config)
        self._mascota = getattr(escritorio, "mascota", None)
        self._m_grande: Any = None                 # la mascota en pantalla grande
        self._geom: Optional[QRect] = None
        self._vista = ""                           # "mascota" · "reloj" · ""
        self._actividad: Optional[str] = None      # "grande" · "salvapantallas" (la del BusEstado)
        self._cedida = False
        self._motivo = ""
        self._temporal = False
        self._salva_en_mascota = False
        self._alarma_texto: Optional[str] = None
        self._esperando = False
        self._espera_temporal = False
        self._espera_hasta = 0.0
        self._minutos_pend: Optional[int] = None
        self._fin_minutos: Optional[float] = None
        self._ventana: Any = None
        self._iniciado = False
        self._bus_conectado = False
        self._ultima_actividad = reloj()
        self._gracia_hasta = 0.0
        self._ignorar_clic_hasta = 0.0
        self.ultimo_error = ""

        self._t_maquina = self._timer(TIC_MAQUINA_MS, self._tic_maquina)
        self._t_inactividad = self._timer(TIC_INACTIVIDAD_MS, self._tic_inactividad)
        self._t_entrada = self._timer(TIC_ENTRADA_MS, self._tic_entrada)
        self._t_espera = self._timer(TIC_ESPERA_MS, self._comprobar_espera)
        self._t_minutos = QTimer(self)
        self._t_minutos.setSingleShot(True)
        self._t_minutos.timeout.connect(self._vencen_minutos)

    def _timer(self, ms: int, slot) -> QTimer:
        t = QTimer(self)
        t.setInterval(ms)
        t.timeout.connect(slot)
        return t

    # ── Contrato de controlador (ui/escritorio.py) ─────────────────────────────
    def iniciar(self) -> None:
        self._iniciado = True
        self._ultima_actividad = self._reloj()
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and hasattr(senal, "connect") and not self._bus_conectado:
            try:
                senal.connect(self._on_bus)
                self._bus_conectado = True
            except (TypeError, RuntimeError):
                pass
        self.recargar_config()

    def detener(self) -> None:
        self._iniciado = False
        self._t_inactividad.stop()
        if self._bus_conectado:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._bus_conectado = False
        if self.activo or self._maquina.estado is not None:
            self.salir(inmediato=True)
        for t in (self._t_maquina, self._t_entrada, self._t_espera, self._t_minutos):
            t.stop()
        if self._ventana is not None:
            # Ventana de nivel superior sin padre: se borra (no queda huérfana tras un
            # cambio de interfaz); si vuelve a hacer falta, se crea otra.
            v, self._ventana = self._ventana, None
            _llamar(v, "ocultar", 0)
            _llamar(v, "deleteLater")

    def set_mascota(self, v) -> None:
        self._mascota = v
        if self._vista == "mascota" and self._m_grande is not None and v is not self._m_grande:
            # La mascota de la pantalla grande se fue (cerrada o recreada): se acaba
            # ya, sin tocar una ventana que ya no está.
            self._m_grande = None
            self._temporal = False
            self._salva_en_mascota = False
            self._maquina.abortar()
            self._t_maquina.stop()
            self._terminar()
        if self._esperando:
            self._comprobar_espera()

    def ceder(self, c) -> None:
        act = getattr(c, "actividad", "")
        if act not in ("grande", "salvapantallas") or act != self._actividad:
            return
        if act == "salvapantallas" and self._bus_campo("alarma") and self._alarma_usa_grande():
            self._salvapantallas_a("alarma")
            return
        # Un juego, o una alarma que se enseña en burbuja (alarmas.pantalla_grande
        # apagado): nadie la sacaría luego de una grande con motivo «alarma».
        self._cedida = True                         # el bus ya la quitó: no hay que terminarla
        self.salir(inmediato=True)

    def _alarma_usa_grande(self) -> bool:
        """¿La alarma se enseña en la pantalla grande? (el mismo criterio que
        servicios/alarmas_aviso.elegir_visual en la app: alarmas.pantalla_grande)."""
        return bool(self._cfg("alarmas", "pantalla_grande", True))

    def reanudar(self, c) -> None:
        """«grande» y «salvapantallas» no son reanudables: nada que hacer."""

    @pyqtSlot(object, object)
    def _on_bus(self, estado: Any = None, cambios: Any = None) -> None:
        """escritorio.estado_cambio (hilo de Qt): la mascota de la pantalla grande se
        escondió → fuera ya; la alarma dejó de sonar con la grande aún en su motivo
        (nadie llamó a salir("alarma")) → fuera."""
        cambios = cambios if isinstance(cambios, dict) else {}
        if "visible" in cambios and self._vista == "mascota" and self._m_grande is not None \
                and self._maquina.estado is not None and not _visible(self._m_grande):
            _log_info("[grande] la mascota se escondió: sale de la pantalla grande")
            self.salir(inmediato=True)
            return
        if "alarma" in cambios and self.motivo == "alarma" and not self._bus_campo("alarma") \
                and self._bus_campo("grande"):
            # Con un juego el bus ya quitó `grande` a la vez: eso lo hace ceder().
            self.salir("alarma")

    def evento_mascota(self, tipo: str, datos: dict) -> None:
        if tipo == "grande_fase":
            _log.debug("pantalla grande: la página dice %s", datos)

    def recargar_config(self) -> None:
        self._regla = ReglaSalvapantallas.desde_config(self.config)
        if self._iniciado and self._regla.activo:
            if not self._t_inactividad.isActive():
                self._ultima_actividad = self._reloj()
                self._t_inactividad.start()
        else:
            self._t_inactividad.stop()
        if self._vista == "reloj" and self._motivo == "salvapantallas" and self._ventana is not None:
            self._mostrar_reloj("salvapantallas")      # fondo y reloj al momento

    # ── API ─────────────────────────────────────────────────────────────────────
    @property
    def activo(self) -> bool:
        return bool(self._esperando or self._vista == "reloj"
                    or self._maquina.estado in ("entrando", "activa")
                    or self._maquina.encolado is not None)

    @property
    def motivo(self) -> str:
        """El motivo actual; durante una salida con una entrada encolada, el de esa."""
        if self._maquina.estado == "saliendo" and self._maquina.encolado:
            return self._maquina.encolado
        if self.activo or self._maquina.estado is not None:
            return self._motivo
        return ""

    def entrar(self, motivo: str = "manual", minutos: Optional[int] = None) -> bool:
        """Pantalla grande con `motivo` (manual, herramienta, alarma, salvapantallas).
        True si entra (o ya estaba). False con `ultimo_error` si la tabla de
        prioridades no la deja (juego…)."""
        motivo = motivo if motivo in pg.MOTIVOS else "manual"
        self.ultimo_error = ""
        if self.activo:
            if minutos and self._motivo in ("manual", "herramienta"):
                self._programar_minutos(minutos)
            return True
        if self._maquina.estado == "saliendo":
            self._maquina.pedir_entrar(motivo, self._reloj())
            self._minutos_pend = minutos
            self._t_maquina.start()
            return True
        m = self._mascota_lista()
        if m is not None:
            return self._entrar_con_mascota(m, motivo, minutos)
        if motivo in ("manual", "herramienta"):
            if self._mascota_cargando() is not None:
                return self._esperar_mascota(motivo, minutos, sacar=False)
            if self._mascota_visible() is None and self._puede_sacar_mascota():
                return self._esperar_mascota(motivo, minutos, sacar=True)
        return self._entrar_con_reloj(motivo, minutos)

    def salir(self, motivo: Optional[str] = None, inmediato: bool = False) -> bool:
        """Sale de la pantalla grande (animado; `inmediato` sin animación). Con
        `motivo`, solo si es el actual: `salir("alarma")` no quita la grande manual
        (pero sí la burbuja de la alarma)."""
        if motivo is not None and motivo != self._motivo:
            if motivo == "alarma":
                self.mostrar_alarma(None)
            self._maquina.pedir_salir(self._reloj(), motivo)      # anula una entrada encolada
            return False
        self._t_minutos.stop()
        self._t_entrada.stop()
        if self._esperando:
            self._t_espera.stop()
            self._esperando = False
            if self._espera_temporal:
                self._temporal = True
                self._m_grande = self._mascota_visible()
            self._terminar()
            return True
        if self._vista == "reloj":
            if self._ventana is not None:
                _llamar(self._ventana, "ocultar", 0 if inmediato else pg.FADE_MS)
            self._terminar()
            return True
        if self._vista == "mascota" and self._maquina.estado is not None:
            if self._salva_en_mascota:
                self._salva_en_mascota = False
                _llamar(self._m_grande, "set_salvapantallas", False)
            t = self._reloj()
            acciones = self._maquina.salir_ya(t) if inmediato else self._maquina.pedir_salir(t)
            self._aplicar(acciones)
            if self._maquina.en_transicion:
                self._t_maquina.start()
            else:
                self._t_maquina.stop()
            return True
        return False

    def alternar(self) -> bool:
        """Atajo, radial y bandeja. Durante una transición no hace nada. → activo."""
        if self._esperando or self._maquina.en_transicion:
            return self.activo
        if self.activo:
            self.salir()
            return False
        return self.entrar("manual")

    def estado(self) -> dict:
        restante = None
        if self._t_minutos.isActive() and self._fin_minutos is not None:
            restante = max(0, int(round(self._fin_minutos - self._reloj())))
        fase = self._maquina.estado or ("esperando" if self._esperando else
                                        ("activa" if self._vista == "reloj" else ""))
        r = self._regla
        return {
            "activo": self.activo,
            "motivo": self.motivo,
            "fase": fase,
            "vista": self._vista,
            "temporal": self._temporal or (self._esperando and self._espera_temporal),
            "restante_s": restante,
            "salvapantallas_puesto": self._actividad == "salvapantallas",
            "salvapantallas": {
                "activo": r.activo, "paso": r.paso, "etiqueta": r.etiqueta, "segundos": r.umbral_s,
                "clic_sale_de_todo": bool(self._cfg("salvapantallas", "clic_sale_de_todo", True)),
                "fondo_oscuro": bool(self._cfg("salvapantallas", "fondo_oscuro", True)),
                "reloj": bool(self._cfg("salvapantallas", "reloj", True)),
            },
            "error": self.ultimo_error,
        }

    def mostrar_alarma(self, texto: Optional[str]) -> bool:
        """La burbuja de la alarma en la mascota (luneAlarma) o en VentanaReloj.
        None la quita. False si no hay pantalla grande donde enseñarla."""
        self._alarma_texto = None if texto is None else str(texto)
        if self._vista == "mascota" and self._m_grande is not None:
            if texto is None:
                _llamar(self._m_grande, "ocultar_alarma")
            else:
                _llamar(self._m_grande, "mostrar_alarma", str(texto))
            return True
        if self._vista == "reloj" and self._ventana is not None:
            v = self._ventana
            if texto is None:
                _llamar(v, "set_alarma", None)
                if self._motivo != "alarma" and getattr(v, "modo", "") == "alarma":
                    self._mostrar_reloj(self._motivo)
            else:
                if getattr(v, "modo", "") != "alarma":
                    self._mostrar_reloj("alarma")
                else:
                    self._poner_alarma_reloj()
            return True
        return self._esperando and texto is not None

    def probar_salvapantallas(self) -> bool:
        """«Probar» de los ajustes: el salvapantallas ya, sin esperar."""
        return self._activar_salvapantallas()

    def herramientas(self) -> Dict[str, Callable]:
        return {"mascota_pantalla_grande": self._herramienta}

    def _herramienta(self, args, ctx=None):
        c = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        c["grande"] = self
        if self._en_ui is not None:
            c["en_ui"] = self._en_ui
        return pg.herramienta(args, c)

    # ── Entrar ──────────────────────────────────────────────────────────────────
    def _iniciar_actividad(self, motivo: str) -> bool:
        act = "salvapantallas" if motivo == "salvapantallas" else "grande"
        pri = getattr(self.escritorio, "prioridad", None)
        if pri is not None:
            try:
                r = pri.iniciar(act)
            except Exception:
                _log.exception("pantalla grande: la tabla de prioridades falló")
                return False
            if not r:
                self.ultimo_error = TEXTO_MOTIVO.get(getattr(r, "motivo", ""), str(getattr(r, "motivo", "")))
                return False
        self._actividad = act
        self._cedida = False
        self._motivo = motivo
        _log_info(f"[grande] entra: {motivo}")
        self.cambio.emit(True, motivo)
        return True

    def _entrar_con_mascota(self, m, motivo: str, minutos: Optional[int]) -> bool:
        if not self._iniciar_actividad(motivo):
            return False
        self._empezar_mascota(m, motivo, minutos)
        return True

    def _empezar_mascota(self, m, motivo: str, minutos: Optional[int]) -> None:
        self._m_grande = m
        self._vista = "mascota"
        if motivo in ("manual", "herramienta") and getattr(m, "durmiendo", False) is True:
            _llamar(m, "despertar")
        if motivo == "salvapantallas":
            _llamar(m, "set_salvapantallas", True,
                    fondo_oscuro=bool(self._cfg("salvapantallas", "fondo_oscuro", True)),
                    reloj=bool(self._cfg("salvapantallas", "reloj", True)))
            self._salva_en_mascota = True
        self._aplicar(self._maquina.pedir_entrar(motivo, self._reloj()))
        self._t_maquina.start()
        self._programar_minutos(minutos)
        if self._alarma_texto is not None:
            _llamar(m, "mostrar_alarma", self._alarma_texto)

    def _entrar_con_reloj(self, motivo: str, minutos: Optional[int]) -> bool:
        if not self._iniciar_actividad(motivo):
            return False
        self._mostrar_reloj(motivo)
        self._programar_minutos(minutos)
        return True

    def _esperar_mascota(self, motivo: str, minutos: Optional[int], *, sacar: bool) -> bool:
        if not self._iniciar_actividad(motivo):
            return False
        self._esperando = True
        self._espera_temporal = sacar
        self._espera_hasta = self._reloj() + ESPERA_MASCOTA_S
        self._minutos_pend = minutos
        if sacar:
            _llamar(self.anfitrion, "alternar_mascota")
        if self._esperando:                             # set_mascota pudo resolverlo ya
            self._t_espera.start()
            self._comprobar_espera()
        return True

    def _comprobar_espera(self) -> None:
        if not self._esperando:
            self._t_espera.stop()
            return
        m = self._mascota_lista()
        if m is not None:
            self._t_espera.stop()
            self._esperando = False
            self._temporal = self._espera_temporal
            self._empezar_mascota(m, self._motivo, self._minutos_pend)
            return
        if self._reloj() >= self._espera_hasta:
            self._t_espera.stop()
            self._esperando = False
            _log_info("[grande] la mascota no estuvo lista a tiempo: reloj")
            if self._espera_temporal:
                self._cerrar_temporal(self._mascota_visible())
            self._mostrar_reloj(self._motivo)
            self._programar_minutos(self._minutos_pend)

    def _activar_salvapantallas(self) -> bool:
        if self.activo or self._maquina.estado is not None:
            return False
        self.ultimo_error = ""
        m = self._mascota_lista()
        ok = (self._entrar_con_mascota(m, "salvapantallas", None) if m is not None
              else self._entrar_con_reloj("salvapantallas", None))
        if ok:
            self._armar_entrada()
        return ok

    # ── Máquina ─────────────────────────────────────────────────────────────────
    def _tic_maquina(self) -> None:
        acciones = self._maquina.avanzar(self._reloj())
        if acciones:
            self._aplicar(acciones)
        if not self._maquina.en_transicion:
            self._t_maquina.stop()

    def _aplicar(self, acciones: List) -> None:
        m_fin = None                                    # la mascota de la salida que acaba de terminar
        for i, (nombre, datos) in enumerate(acciones):
            m = self._m_grande
            if nombre == "guardar_geom":
                if self._actividad is None:
                    # Entrada encolada durante la salida: la actividad se pide ahora.
                    motivo = str(datos.get("motivo") or "manual")
                    nueva = self._mascota_lista()
                    if nueva is None or not self._iniciar_actividad(motivo):
                        self._maquina.abortar()
                        if nueva is None and self._actividad is None:
                            self._entrar_con_reloj(motivo, self._minutos_pend)   # con la burbuja, si la hay
                        if not self.activo:
                            self._alarma_texto = None
                        break
                    self._m_grande = m = nueva
                    self._vista = "mascota"
                    self._programar_minutos(self._minutos_pend)
                    if self._alarma_texto is not None and nueva is not m_fin:
                        _llamar(m_fin, "ocultar_alarma")
                        _llamar(nueva, "mostrar_alarma", self._alarma_texto)
                g = _llamar(m, "geometria")
                self._geom = QRect(g) if isinstance(g, QRect) else None
            elif nombre == "fase":
                opciones = {k: v for k, v in datos.items() if k != "fase"}
                _llamar(m, "grande_fase", str(datos.get("fase")), opciones)
            elif nombre == "geom_monitor":
                r = self._rect_monitor(self._geom)
                if r is not None:
                    _llamar(m, "set_geometria", r)
            elif nombre == "restaurar_geom":
                if self._geom is not None and m is not None:
                    _llamar(m, "set_geometria", QRect(self._geom))
            elif nombre == "activa":
                _log.debug("pantalla grande activa (%s)", datos.get("motivo"))
            elif nombre == "fin":
                # Si detrás viene una entrada encolada (una alarma que sonó durante la
                # salida), su burbuja se conserva para la entrada nueva.
                m_fin = m
                self._terminar(conservar_alarma=any(n == "guardar_geom" for n, _ in acciones[i + 1:]))

    # ── Salir ───────────────────────────────────────────────────────────────────
    def _terminar(self, conservar_alarma: bool = False) -> None:
        """Fin de la pantalla grande: soltar la mascota temporal, la actividad del
        bus y avisar. Idempotente. `conservar_alarma`: vuelve a entrar ya (entrada
        encolada) y la burbuja de la alarma sigue."""
        for t in (self._t_minutos, self._t_entrada, self._t_espera):
            t.stop()
        m = self._m_grande
        if self._salva_en_mascota:
            self._salva_en_mascota = False
            _llamar(m, "set_salvapantallas", False)
        if self._alarma_texto is not None and self._vista == "mascota" and not conservar_alarma:
            _llamar(m, "ocultar_alarma")
        if self._temporal:
            self._cerrar_temporal(m)
        if self._vista == "reloj" and self._ventana is not None and _visible(self._ventana) \
                and not getattr(self._ventana, "ocultandose", False):
            _llamar(self._ventana, "ocultar", 0)
        act, self._actividad = self._actividad, None
        motivo, self._motivo = self._motivo, ""
        self._vista = ""
        self._m_grande = None
        self._geom = None
        self._temporal = False
        self._esperando = False
        if not conservar_alarma:
            self._alarma_texto = None
        self._fin_minutos = None
        self._ultima_actividad = self._reloj()
        cedida, self._cedida = self._cedida, False
        if act and not cedida:
            pri = getattr(self.escritorio, "prioridad", None)
            if pri is not None:
                try:
                    pri.terminar(act)
                except Exception:
                    _log.exception("pantalla grande: no pude terminar %s", act)
        if act:
            _log_info(f"[grande] sale: {motivo}")
            self.cambio.emit(False, motivo)

    def _cerrar_temporal(self, m) -> None:
        """La mascota que se sacó para la pantalla grande se cierra al salir."""
        if m is None or getattr(m, "cerrado", False):
            return
        _llamar(m, "close")

    def _vencen_minutos(self) -> None:
        if self._motivo in ("manual", "herramienta"):
            self.salir()

    def _programar_minutos(self, minutos: Optional[int]) -> None:
        self._minutos_pend = None
        if not minutos or self._motivo not in ("manual", "herramienta"):
            return
        try:
            m = min(max(int(minutos), 1), pg.MINUTOS_MAX)
        except (TypeError, ValueError):
            return
        self._t_minutos.start(m * 60_000)
        self._fin_minutos = self._reloj() + m * 60

    # ── Salvapantallas ──────────────────────────────────────────────────────────
    def _tic_inactividad(self) -> None:
        if not self._regla.activo or self.activo or self._maquina.estado is not None:
            return
        ahora = self._reloj()
        if self._mando():
            self._ultima_actividad = ahora
        inactivo = min(self._segundos_inactivo(), max(0.0, ahora - self._ultima_actividad))
        if inactivo < self._regla.umbral_s:
            return
        est = self._estado_bus()
        if self._regla.debe_activar(inactivo, est, pantalla_requerida=self._pantalla_requerida()):
            self._activar_salvapantallas()

    def _armar_entrada(self) -> None:
        det = self._detector()
        try:
            det.reiniciar()
            det.poll()                                  # línea base ya
        except Exception:
            _log.debug("pantalla grande: el detector de entrada falló", exc_info=True)
        self._gracia_hasta = self._reloj() + GRACIA_ENTRADA_S
        self._t_entrada.start()

    def _tic_entrada(self) -> None:
        if self._actividad != "salvapantallas":
            self._t_entrada.stop()
            return
        try:
            hubo = bool(self._detector().poll())
        except Exception:
            hubo = False
        if not hubo or self._reloj() < self._gracia_hasta:
            return
        self._ultima_actividad = self._reloj()
        self._t_entrada.stop()
        if self._cfg("salvapantallas", "clic_sale_de_todo", True):
            self.salir()
        else:
            self._ignorar_clic_hasta = self._reloj() + IGNORAR_CLIC_S
            self._salvapantallas_a("manual")

    def _salvapantallas_a(self, motivo: str) -> None:
        """Del salvapantallas a la pantalla grande despierta: con la alarma (que la
        cedió) o manual (un clic con `clic_sale_de_todo` apagado)."""
        self._t_entrada.stop()
        if self._salva_en_mascota:
            self._salva_en_mascota = False
            _llamar(self._m_grande, "set_salvapantallas", False)     # la despierta
        if motivo == "alarma":
            self._actividad = None                      # el bus ya apagó el salvapantallas
            ok = self._iniciar_actividad("alarma")      # «grande»: coexiste con la alarma
        else:
            ok = self._cambiar_a_grande()
        if not ok:
            self._cedida = self._actividad is None
            self.salir(inmediato=True)
            return
        self._motivo = motivo
        self._maquina.cambiar_motivo(motivo)
        if self._vista == "reloj":
            self._mostrar_reloj(motivo)
        elif self._vista == "mascota" and getattr(self._m_grande, "durmiendo", False) is True:
            _llamar(self._m_grande, "despertar")
        self.cambio.emit(True, motivo)

    def _cambiar_a_grande(self) -> bool:
        """«salvapantallas» → «grande» en el bus sin perder lo pendiente de reanudar
        (se reanudará al acabar la pantalla grande)."""
        bus = getattr(self.escritorio, "estado", None)
        pri = getattr(self.escritorio, "prioridad", None)
        if bus is None or pri is None:
            self._actividad = "grande"
            return True
        try:
            pendientes = bus.terminar_actividad("salvapantallas")
            r = pri.iniciar("grande")
        except Exception:
            _log.exception("pantalla grande: no pude pasar del salvapantallas a la grande")
            return False
        por = "grande" if r else getattr(r, "motivo", "")
        for c in pendientes:
            try:
                bus.reanudar_despues(c, por)
            except Exception:
                pass
        if not r:
            self._actividad = None
            return False
        self._actividad = "grande"
        self._cedida = False
        return True

    # ── VentanaReloj ────────────────────────────────────────────────────────────
    def _ventana_reloj(self):
        if self._ventana is None:
            if self._fabrica_reloj is not None:
                v = self._fabrica_reloj()
            else:
                from ui.ventana_reloj import VentanaReloj
                v = VentanaReloj()
            for senal, slot in (("apagar", self.pedir_apagar_alarma.emit),
                                ("posponer", self.pedir_posponer_alarma.emit),
                                ("cerrar_pedido", self._clic_reloj)):
                s = getattr(v, senal, None)
                if s is not None and hasattr(s, "connect"):
                    s.connect(slot)
            self._ventana = v
        return self._ventana

    def _mostrar_reloj(self, motivo: str) -> None:
        v = self._ventana_reloj()
        modo = motivo if motivo in ("salvapantallas", "alarma") else "grande"
        salva = modo == "salvapantallas"
        fondo = bool(self._cfg("salvapantallas", "fondo_oscuro", True)) if salva else True
        con_reloj = bool(self._cfg("salvapantallas", "reloj", True)) if salva else True
        _llamar(v, "mostrar", modo, pantalla=self._pantalla(), fondo_oscuro=fondo, reloj=con_reloj)
        self._vista = "reloj"
        if modo == "alarma" and self._alarma_texto is not None:
            self._poner_alarma_reloj()

    def _poner_alarma_reloj(self) -> None:
        try:
            bloqueo = int(float(self._cfg("alarmas", "bloqueo_s", 5)) * 1000)
        except (TypeError, ValueError):
            bloqueo = 5000
        _llamar(self._ventana, "set_alarma", self._alarma_texto, bloqueo_ms=max(0, bloqueo))

    def _clic_reloj(self) -> None:
        """Clic en VentanaReloj: en modo «grande» sale. El salvapantallas lo cierra el
        detector de entrada (el mismo clic) y la alarma, ControlAlarmasQt."""
        if self._reloj() < self._ignorar_clic_hasta:
            return
        v = self._ventana
        if self._vista == "reloj" and getattr(v, "modo", "") == "grande":
            self.salir()

    # ── Mascota y pantallas ─────────────────────────────────────────────────────
    def _mascota_actual(self):
        m = self._mascota
        if m is None or getattr(m, "cerrado", False):
            m = _llamar(self.anfitrion, "mascota")
        return None if m is None or getattr(m, "cerrado", False) else m

    def _mascota_visible(self):
        m = self._mascota_actual()
        return m if _visible(m) else None

    def _mascota_lista(self):
        m = self._mascota_visible()
        return m if m is not None and _soporta(m) else None

    def _mascota_cargando(self):
        """La mascota de página (VRM o animada) a la vista pero aún sin su página lista."""
        m = self._mascota_visible()
        if m is None or _soporta(m):
            return None
        return m if str(getattr(m, "render", "") or "") in RENDERS_PAGINA else None

    def _puede_sacar_mascota(self) -> bool:
        if not callable(getattr(self.anfitrion, "alternar_mascota", None)):
            return False
        render = str(self._cfg("avatar", "render", "animado") or "animado")
        modo = str(getattr(self.anfitrion, "modo", "normal") or "normal")
        permitidos = ("vrm",) if modo == "br" else RENDERS_PAGINA       # la nativa anima con sprites
        if render not in permitidos:
            return False
        try:
            return bool(self._hay_webengine())
        except Exception:
            return False

    @staticmethod
    def _rect_de(m) -> Optional[QRect]:
        for metodo in ("geometria", "geometry", "frameGeometry"):
            g = _llamar(m, metodo)
            if isinstance(g, QRect):
                return g
        return None

    def _rect_monitor(self, geom: Optional[QRect]) -> Optional[QRect]:
        pantallas = QGuiApplication.screens()
        if not pantallas:
            return None
        if geom is None:
            scr = QGuiApplication.primaryScreen() or pantallas[0]
            return QRect(scr.geometry())
        i = indice_mayor_interseccion(geom, [p.geometry() for p in pantallas])
        return QRect(pantallas[i].geometry())

    def _pantalla(self):
        pantallas = QGuiApplication.screens()
        if not pantallas:
            return None
        m = self._m_grande or self._mascota_visible()
        g = self._rect_de(m) if m is not None else None
        if g is not None:
            return pantallas[indice_mayor_interseccion(g, [p.geometry() for p in pantallas])]
        try:
            scr = QGuiApplication.screenAt(QCursor.pos())
        except Exception:
            scr = None
        return scr or QGuiApplication.primaryScreen() or pantallas[0]

    # ── Entrada y estado ────────────────────────────────────────────────────────
    def _detector(self):
        if self._entrada is None:
            self._entrada = we.DetectorEntrada(self._api, con_mando=True)
        return self._entrada

    def _segundos_inactivo(self) -> float:
        try:
            return float(we.segundos_inactivo(self._api))
        except Exception:
            return 0.0

    def _mando(self) -> bool:
        try:
            return bool(we.mando_activo(self._api))
        except Exception:
            return False

    def _pantalla_requerida(self) -> bool:
        try:
            return bool(we.pantalla_requerida(self._api))
        except Exception:
            return False

    def _estado_bus(self):
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _bus_campo(self, campo: str) -> bool:
        return bool(getattr(self._estado_bus(), campo, False))

    def _cfg(self, seccion: str, clave: str, defecto: Any) -> Any:
        try:
            if self.config is None:
                return defecto
            if isinstance(self.config, dict):
                return self.config.get(seccion, {}).get(clave, defecto)
            return self.config.get(seccion, clave, defecto)
        except Exception:
            return defecto


__all__ = ("ControlPantallaGrande", "webengine_disponible", "indice_mayor_interseccion", "ESPERA_MASCOTA_S")
