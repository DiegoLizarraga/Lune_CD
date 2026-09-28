"""
ui/alarmas_qt.py — Alarmas y temporizadores en la app (web y nativa).

`ControlAlarmasQt` es un controlador de `ServiciosEscritorio` (ui/escritorio.py)
con la actividad «alarma»: lo crea `montar_ocio` (ui/montaje_ocio.py) y recibe
`iniciar`, `detener`, `set_mascota`, `ceder` y `reanudar` como los demás.

CADA SEGUNDO (`_tic`)
- Si es dueño del mutex `Local\\Lune_CD_Alarmas` (se reintenta cada 10 s):
  al serlo, `Programador.recuperar_sonando` (lo que quedó sonando al cerrar o
  al cambiar de interfaz); después `Programador.tick` → `ControlAviso.disparar`;
  las `Perdida` van a `avisar` y a la señal `perdidas`.
- Si no es dueño (patata u otra app programan), solo vigila alarmas.json y
  emite `cambio` cuando otro lo edita.
- La app es la dueña PREFERENTE: mientras está en marcha tiene además el mutex
  `Local\\Lune_CD_Alarmas_app`; si patata era la dueña, lo ve y le cede las
  alarmas en cuanto no suene nada (servicios/alarmas_patata.py).
- Si el tic falla, una traza en el log y silencio mientras falle igual.
- `ControlAviso.tick()`: corte a los 15 min y pospuestas.

AL SONAR (`on_mostrar`)
- `prioridad.iniciar("alarma")`. Si no se permite (hay un juego): `discreto`
  (sonido + aviso de bandeja; D3: suena aunque juego.silenciar esté activado).
- Si no, la despierta y según `elegir_visual`:
  · `grande`: `grande.entrar("alarma")` + `grande.mostrar_alarma(texto)` (la
    mascota o la VentanaReloj; eso es de ControlPantallaGrande);
  · `burbuja` (alarmas.pantalla_grande desactivado, o sin pantalla grande):
    `mascota.mostrar_alarma(texto)` + la tarjeta `DialogoAlarma`;
  · `discreto`: `avisar("⏰ texto")`.
- Siempre emite `sonando(json)` (el banner de la web lo usa).
- Mientras suena, un QTimer de 33 ms mira `DetectorEntrada.poll()` (flanco de
  clic o tecla sin mover el cursor, o mando). Tras el bloqueo apaga (con
  `retraso_entrada_ms` para que un clic en «Posponer» gane al apagado); durante
  el bloqueo la entrada se consume sin efecto.

AL APAGAR (`on_ocultar`): fuera la burbuja, `grande.salir("alarma")` (solo sale
si la metió la alarma), cierra la tarjeta, `prioridad.terminar("alarma")`, emite
`apagada` y, si `alarmas.decir_texto`, `voice.speak(texto)`.

`ceder(c)` (entra un juego): quita lo visual, SIGUE SONANDO y avisa por la bandeja.

Las herramientas del modelo (`herramientas()`) van directas al Almacen (sin
hilo de Qt): el tic siguiente, o `_refresco`, emite `cambio`. Su `al_cambiar` pasa por un
`PuenteHilo` (ui/escritorio.py), no el `emit` ligado de `_refresco`: una herramienta
en curso en el Ejecutor durante un cambio de interfaz lo llamaba sobre el
controlador ya borrado.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from nucleo import alarmas as al
from nucleo.alarmas import Almacen, Disparo, Programador, texto_visible
from servicios.alarmas_aviso import SONIDOS, ControlAviso, elegir_visual
from ui.escritorio import PuenteHilo

_log = logging.getLogger("lune.alarmas")

REINTENTO_MUTEX_S = 10.0
ENTRADA_MS = 33
RETRASO_ENTRADA_MS = 300
_ID = al._ID


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("alarmas: %s.%s falló", type(obj).__name__, metodo)
        return None


class ControlAlarmasQt(QObject):
    """Programador + aviso + visual de las alarmas en la app."""

    sonando = pyqtSignal(str)       # {texto, tipo, atraso_s, programado, apagar_en_ms, cola, …}
    apagada = pyqtSignal()
    cambio = pyqtSignal(str)        # listar() en JSON
    perdidas = pyqtSignal(str)      # [{origen, texto, tipo, cuando, mensaje}]

    _refresco = pyqtSignal()        # desde otros hilos (herramientas del modelo)

    def __init__(self, escritorio, config, *, voice=None, grande=None, avisar=None, en_ui=None,
                 almacen=None, aviso=None, mutex=None, entrada=None, parent=None, mutex_app=None,
                 ahora: Optional[Callable[[], datetime]] = None, epoch: Optional[Callable[[], float]] = None,
                 reloj: Callable[[], float] = time.monotonic, dialogo: Optional[Callable[..., Any]] = None,
                 intervalo_ms: int = 1000, retraso_entrada_ms: int = RETRASO_ENTRADA_MS):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.voice = voice
        self.grande = grande
        self._avisar = avisar
        self._en_ui = en_ui
        self._ahora = ahora or datetime.now
        self._epoch = epoch or time.time
        self._reloj = reloj
        self._fabrica_dialogo = dialogo
        self._retraso_entrada_ms = max(0, int(retraso_entrada_ms))
        self.almacen: Almacen = almacen if almacen is not None else Almacen(al.RUTA)
        self.programador = Programador(self.almacen, recuperar_min=self._cfg("recuperar_min", al.RECUPERAR_MIN))
        if aviso is None:
            aviso = ControlAviso(almacen=self.almacen, reloj=reloj, epoch=self._epoch)
        self.aviso = aviso
        for nombre, fn in (("on_mostrar", self._on_mostrar), ("on_ocultar", self._on_ocultar),
                           ("on_voz", self._on_voz)):
            try:
                setattr(aviso, nombre, fn)
            except Exception:
                pass
        self._mutex = mutex
        # Presencia de la app (dueña preferente). Con un mutex de dueño inyectado (tests) y
        # sin `mutex_app`, no se usa: nada de mutex reales en los tests.
        self._mutex_app = mutex_app
        self._mutex_app_auto = mutex_app is None and mutex is None
        self._presente = False
        self._ultimo_intento_app: Optional[float] = None
        self._fallo_tic = ""                           # el último fallo del tic ya trazado
        self._entrada = entrada
        self._mascota = getattr(escritorio, "mascota", None)
        self._iniciado = False
        self._dueno = False
        self._recien_dueno = False
        self._ultimo_intento: Optional[float] = None
        self._activo_prev: Optional[bool] = None
        # Lo que se enseña de la alarma actual
        self._mostrando = False
        self._visual = ""
        self._prio_mia = False
        self._grande_mio = False
        self._dialogo = None
        self._editor = None
        self._pendiente: Optional[Disparo] = None     # apagado por entrada esperando

        self._timer = QTimer(self)
        self._timer.setInterval(max(20, int(intervalo_ms)))
        self._timer.timeout.connect(self._tic)
        self._timer_entrada = QTimer(self)
        self._timer_entrada.setInterval(ENTRADA_MS)
        self._timer_entrada.timeout.connect(self._tic_entrada)
        # Ranura propia (no una lambda): si el controlador se borra (cambio de interfaz)
        # con un refresco en cola, Qt lo descarta en vez de llamar a un objeto borrado.
        self._refresco.connect(self._al_refresco, Qt.ConnectionType.QueuedConnection)
        # Lo que las herramientas llaman desde el hilo del Ejecutor (nunca el emit ligado).
        self._puente_refresco = PuenteHilo(self, "_refresco")

    @pyqtSlot()
    def _al_refresco(self) -> None:
        self._emitir_cambio(True)

    # ── Config ──────────────────────────────────────────────────────────────────
    def _cfg(self, clave: str, defecto: Any = None, seccion: str = "alarmas") -> Any:
        try:
            v = self.config.get(seccion, clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto
        return defecto if v is None else v

    def _num(self, clave: str, defecto: float, lo: float, hi: float) -> float:
        try:
            v = float(self._cfg(clave, defecto))
        except (TypeError, ValueError):
            return defecto
        return min(max(v, lo), hi)

    def _activo(self) -> bool:
        return bool(self._cfg("activo", True))

    def recargar_config(self) -> None:
        """Relee alarmas.* (y voz.dispositivo_salida). Al reactivar las alarmas no
        se recupera nada de lo que pasó mientras estaban apagadas."""
        self.programador.recuperar_min = self._num("recuperar_min", al.RECUPERAR_MIN, 0, 24 * 60)
        a = self.aviso
        for attr, valor in (("bloqueo_s", self._num("bloqueo_s", 5, 0, 60)),
                            ("volumen", self._num("volumen", 0.8, 0, 1)),
                            ("posponer_min", self._num("posponer_min", 5, 1, 120))):
            try:
                setattr(a, attr, valor)
            except Exception:
                pass
        sonido = str(self._cfg("sonido", "azar") or "azar")
        try:
            a.sonido = sonido if sonido in SONIDOS else "azar"
            dispositivo = self._cfg("dispositivo_salida", None, seccion="voz")
            a.dispositivo = str(dispositivo) if dispositivo is not None else None
        except Exception:
            pass
        activo = self._activo()
        previo, self._activo_prev = self._activo_prev, activo
        if previo is False and activo:
            try:
                self.almacen.marcar_visto(self._epoch())
            except Exception:
                _log.exception("alarmas: no pude marcar visto_hasta")
            self.programador.reiniciar()
        elif previo and not activo:
            self._apagar_todo()

    # ── Contrato de controlador ────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        if not self._puente_refresco.abierto:
            self._puente_refresco = PuenteHilo(self, "_refresco")
        self.recargar_config()
        self._asegurar_presencia()
        self._timer.start()

    def detener(self) -> None:
        """Para los relojes y calla. Lo que sonaba se queda en alarmas.json
        (`sonando`) para que lo recupere quien arranque después."""
        self._iniciado = False
        self._puente_refresco.cerrar()               # el montaje lo borra justo después
        self._timer.stop()
        self._timer_entrada.stop()
        _llamar(self.aviso, "detener")
        if self._mostrando:
            self._quitar_visual()
            self._mostrando = False
            self.apagada.emit()
        if self._mutex is not None and self._dueno:
            _llamar(self._mutex, "liberar")
        if self._mutex_app is not None and self._presente:
            _llamar(self._mutex_app, "liberar")
        self._dueno = False
        self._recien_dueno = False
        self._ultimo_intento = None
        self._presente = False
        self._ultimo_intento_app = None
        self.programador.reiniciar()
        # Tarjeta y editor no tienen padre: sin deleteLater quedaban huérfanos en cada cambio
        # de interfaz (revisión 4-5-6, VS8).
        for w in (self._dialogo, self._editor):
            if w is not None:
                _llamar(w, "close")
                _llamar(w, "deleteLater")
        self._dialogo = None
        self._editor = None

    def set_mascota(self, v) -> None:
        if v is self._mascota:
            return
        self._mascota = v
        if self._mostrando and self._visual == "burbuja" and v is not None and self.aviso.sonando:
            _llamar(v, "mostrar_alarma", texto_visible(self.aviso.sonando))

    def ceder(self, c) -> None:
        """Entra algo de más prioridad (un juego): fuera lo visual, sigue sonando."""
        if getattr(c, "actividad", "") != "alarma":
            return
        self._prio_mia = False                     # la tabla ya apagó `alarma` en el bus
        d = self.aviso.sonando
        if not self._mostrando or d is None:
            return
        if self._visual != "discreto":
            self._grande_mio = False               # la pantalla grande cede sola ante el juego
            self._quitar_visual(terminar=False)
            self._visual = "discreto"
            self._notificar(f"⏰ {texto_visible(d)} (sigue sonando)")
            self._emitir_sonando(d)

    def reanudar(self, c) -> None:
        if getattr(c, "actividad", "") != "alarma" or self.aviso.sonando is None:
            return
        self._mostrando = False
        self._on_mostrar(self.aviso.sonando)

    # ── Mutex del dueño ────────────────────────────────────────────────────────
    def _mutex_real(self):
        if self._mutex is None:
            from servicios.mutex_win import MutexNombrado
            self._mutex = MutexNombrado(al.nombre_mutex_dueno(self.almacen.ruta))
        return self._mutex

    def _asegurar_dueno(self) -> bool:
        m = self._mutex_real()
        if self._dueno:
            if bool(getattr(m, "es_dueno", True)):
                return True
            self._dueno = False
            self._ultimo_intento = None
        ahora = self._reloj()
        if self._ultimo_intento is not None and ahora - self._ultimo_intento < REINTENTO_MUTEX_S:
            return False
        self._ultimo_intento = ahora
        try:
            ok = bool(m.adquirir())
        except Exception:
            _log.exception("alarmas: no pude pedir el mutex")
            ok = False
        if ok:
            self._dueno = True
            self._recien_dueno = True
        return ok

    @property
    def dueno(self) -> bool:
        return self._dueno

    def _mutex_app_real(self):
        if self._mutex_app is None and self._mutex_app_auto:
            from servicios.mutex_win import MutexNombrado
            self._mutex_app = MutexNombrado(al.nombre_mutex_app(self.almacen.ruta))
        return self._mutex_app

    def _asegurar_presencia(self) -> None:
        """Tiene el mutex `…_app` mientras está en marcha (se reintenta cada 10 s): así
        patata sabe que la app está abierta y le cede las alarmas."""
        m = self._mutex_app_real()
        if m is None:
            return
        if self._presente and bool(getattr(m, "es_dueno", True)):
            return
        ahora = self._reloj()
        if self._ultimo_intento_app is not None and ahora - self._ultimo_intento_app < REINTENTO_MUTEX_S:
            return
        self._ultimo_intento_app = ahora
        try:
            self._presente = bool(m.adquirir())
        except Exception:
            _log.debug("alarmas: no pude pedir el mutex de la app", exc_info=True)
            self._presente = False

    # ── Tic ────────────────────────────────────────────────────────────────────
    def _tic(self) -> None:
        if not self._iniciado:
            return
        try:
            self.recargar_config()           # barato; así lo que guarden el puente o el panel vale ya
            self._asegurar_presencia()
            activo = bool(self._activo_prev)
            if activo and self._asegurar_dueno():
                epoch = self._epoch()
                if self._recien_dueno:
                    self._recien_dueno = False
                    self.programador.reiniciar()
                    for d in self.programador.recuperar_sonando(epoch):
                        self._disparar(d)
                disparos, perdidas = self.programador.tick(self._ahora(), epoch)
                for d in disparos:
                    self._disparar(d)
                if perdidas:
                    self._avisar_perdidas(perdidas)
            self.aviso.tick()
            self._emitir_cambio(False)
        except Exception as e:
            # Una traza y silencio mientras falle igual (antes: una traza por segundo, p. ej.
            # con un alarmas.json imposible).
            fallo = f"{type(e).__name__}: {e}"
            if fallo != self._fallo_tic:
                self._fallo_tic = fallo
                _log.exception("alarmas: el tic falló (no se repite mientras falle igual)")
            return
        self._fallo_tic = ""

    def _disparar(self, d: Disparo) -> None:
        """Suena ya o espera su turno; si espera, se reenvía la que suena para que
        el banner y la tarjeta enseñen «+N en espera»."""
        if self.aviso.disparar(d) or d not in self.aviso.cola:
            return
        actual = self.aviso.sonando
        if actual is not None and self._mostrando:
            if self._visual == "burbuja" and self._dialogo is not None:
                self._mostrar_dialogo(actual, texto_visible(actual))
            self._emitir_sonando(actual)

    def _avisar_perdidas(self, perdidas) -> None:
        ahora = self._ahora()
        lista = []
        for p in perdidas:
            msg = al.texto_perdida(p, ahora)
            self._notificar(msg)
            lista.append({"origen": p.origen, "texto": p.texto, "tipo": p.tipo,
                          "cuando": p.cuando.strftime("%H:%M"), "fecha": p.cuando.date().isoformat(),
                          "mensaje": msg})
        self.perdidas.emit(json.dumps(lista, ensure_ascii=False))

    def _emitir_cambio(self, forzar: bool = False) -> None:
        try:
            hay = self.almacen.cambio()
        except Exception:
            hay = False
        if hay or forzar:
            self.cambio.emit(json.dumps(self.listar(), ensure_ascii=False))

    # ── Entrada global (apagar con un clic o una tecla) ─────────────────────────
    def _detector(self):
        if self._entrada is None:
            from servicios.win_entrada import DetectorEntrada
            self._entrada = DetectorEntrada(con_mando=True)
        return self._entrada

    def _armar_entrada(self) -> None:
        self._pendiente = None
        _llamar(self._detector(), "reiniciar")
        if not self._timer_entrada.isActive():
            self._timer_entrada.start()

    def _tic_entrada(self) -> None:
        d = self.aviso.sonando
        if d is None:
            self._timer_entrada.stop()
            return
        try:
            hubo = bool(self._detector().poll())
        except Exception:
            return
        if not hubo or self._pendiente is not None:
            return
        if not self.aviso.puede_apagar():
            return                                 # durante el bloqueo se consume sin efecto
        self._pendiente = d
        if self._retraso_entrada_ms <= 0:
            self._apagar_por_entrada(d)
        else:
            QTimer.singleShot(self._retraso_entrada_ms, lambda: self._apagar_por_entrada(d))

    def _apagar_por_entrada(self, d: Disparo) -> None:
        self._pendiente = None
        if self.aviso.sonando is d:
            self.aviso.apagar()

    # ── Callbacks de ControlAviso ──────────────────────────────────────────────
    def _estado_bus(self):
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _mascota_actual(self):
        m = getattr(self.escritorio, "mascota", None)
        return m if m is not None else self._mascota

    def _on_mostrar(self, d: Disparo) -> None:
        texto = texto_visible(d)
        if not self._mostrando:
            self._mostrando = True
            self._grande_mio = False
            prio = getattr(self.escritorio, "prioridad", None)
            permitido = True
            if prio is not None:
                try:
                    permitido = bool(prio.iniciar("alarma"))
                except Exception:
                    _log.exception("alarmas: prioridad.iniciar falló")
                    permitido = True
            self._prio_mia = bool(permitido and prio is not None)
            est = self._estado_bus()
            if not permitido:
                self._visual = "discreto"
            else:
                m = self._mascota_actual()
                if m is not None and (est is None or getattr(est, "durmiendo", False)):
                    _llamar(m, "despertar")
                self._visual = elegir_visual(
                    juego=bool(getattr(est, "juego", False)),
                    pantalla_grande=bool(self._cfg("pantalla_grande", True)),
                    render=str(getattr(est, "render", "") or ""),
                    mascota_visible=bool(getattr(est, "visible", False)))
            if self._visual == "grande":
                ok = _llamar(self.grande, "entrar", "alarma") if self.grande is not None else False
                if ok is False or ok is None:
                    self._visual = "burbuja"
                else:
                    self._grande_mio = True
        self._pintar(d, texto)
        self._emitir_sonando(d)
        self._armar_entrada()

    def _pintar(self, d: Disparo, texto: str) -> None:
        if self._visual == "grande":
            _llamar(self.grande, "mostrar_alarma", texto)
        elif self._visual == "burbuja":
            est = self._estado_bus()
            m = self._mascota_actual()
            if m is not None and (est is None or getattr(est, "visible", True)):
                _llamar(m, "mostrar_alarma", texto)
            self._mostrar_dialogo(d, texto)
        else:
            self._notificar(f"⏰ {texto}")

    def _mostrar_dialogo(self, d: Disparo, texto: str) -> None:
        if self._dialogo is None:
            try:
                if self._fabrica_dialogo is not None:
                    self._dialogo = self._fabrica_dialogo()
                else:
                    from ui.alarmas_dialogo import DialogoAlarma
                    self._dialogo = DialogoAlarma()
                self._dialogo.apagar.connect(lambda: self.apagar())
                self._dialogo.posponer.connect(lambda: self.posponer())
            except Exception:
                _log.exception("alarmas: no pude crear la tarjeta de la alarma")
                self._dialogo = None
                return
        _llamar(self._dialogo, "set_disparo", texto, tipo=d.tipo, programado=d.programado,
                bloqueo_ms=int(self.aviso.restante_bloqueo() * 1000),
                posponer_min=getattr(self.aviso, "posponer_min", 5), cola=len(self.aviso.cola))
        _llamar(self._dialogo, "mostrar")

    def _quitar_visual(self, terminar: bool = True) -> None:
        """Quita burbuja, pantalla grande y tarjeta. Con `terminar`, además deja de
        mirar la entrada y suelta la actividad «alarma» del bus."""
        if terminar:
            self._timer_entrada.stop()
        _llamar(self._mascota_actual(), "ocultar_alarma")
        if self._grande_mio:
            _llamar(self.grande, "salir", "alarma")
            self._grande_mio = False
        if self._dialogo is not None:
            _llamar(self._dialogo, "cerrar")
        if terminar and self._prio_mia:
            prio = getattr(self.escritorio, "prioridad", None)
            _llamar(prio, "terminar", "alarma")
            self._prio_mia = False

    def _on_ocultar(self, d: Disparo) -> None:
        self._pendiente = None
        self._timer_entrada.stop()
        self._quitar_visual()
        self._mostrando = False
        self._visual = ""
        self.apagada.emit()

    def _on_voz(self, d: Disparo) -> None:
        if self.voice is None or not self._cfg("decir_texto", True):
            return
        if d.texto:
            _llamar(self.voice, "speak", d.texto)

    def _notificar(self, texto: str) -> None:
        if callable(self._avisar):
            try:
                self._avisar(texto)
            except Exception:
                _log.exception("alarmas: avisar falló")
        else:
            _log.info("alarmas: %s", texto)

    def _payload(self, d: Disparo) -> dict:
        return {"texto": texto_visible(d), "texto_base": d.texto, "tipo": d.tipo, "origen": d.origen,
                "atraso_s": round(float(d.atraso_s), 1), "programado": d.programado,
                "apagar_en_ms": int(self.aviso.restante_bloqueo() * 1000), "cola": len(self.aviso.cola),
                "visual": self._visual, "posponer_min": getattr(self.aviso, "posponer_min", 5)}

    def _emitir_sonando(self, d: Disparo) -> None:
        self.sonando.emit(json.dumps(self._payload(d), ensure_ascii=False))

    def _apagar_todo(self) -> None:
        """Alarmas desactivadas: calla todo, vacía la cola y lo quita de `sonando`."""
        d = self.aviso.sonando
        pendientes = ([d] if d is not None else []) + list(self.aviso.cola)
        _llamar(self.aviso, "detener")
        for x in pendientes:
            try:
                self.almacen.quitar_sonando(x)
            except Exception:
                pass
        if self._mostrando and d is not None:
            self._on_ocultar(d)

    # ── API (puente web, panel nativo, bandeja) ────────────────────────────────
    def listar(self) -> dict:
        ahora, epoch = self._ahora(), self._epoch()
        alarmas = []
        for a in self.almacen.alarmas():
            o = al.ocurrencia_siguiente(a, ahora)
            alarmas.append({
                "id": a.id, "hora": a.hhmm, "h": a.hora, "m": a.minuto, "minuto": a.minuto,
                "dias": al.letras_dias(a.dias),
                "dias_mask": a.dias, "dias_texto": al.texto_dias(a.dias), "una_vez": a.una_vez,
                "fecha": a.fecha, "texto": a.texto, "activa": a.activa,
                "descripcion": al.texto_alarma(a, ahora),
                "proxima": _epoch_de(o, ahora, epoch) if o is not None else None,
            })
        temps = []
        for t in self.almacen.temporizadores():
            temps.append({
                "id": t.id, "duracion_s": t.duracion_s, "texto": t.texto, "objetivo": t.objetivo,
                "restante_s": t.restante_s, "activo": t.activo, "corriendo": t.corriendo,
                "una_vez": t.una_vez, "pospuesta": t.pospuesta, "falta_s": t.falta(epoch),
            })
        proxima = None
        p = self.almacen.proxima(ahora)
        if p is not None:
            o, obj = p
            proxima = {"id": obj.id, "tipo": "alarma" if isinstance(obj, al.Alarma) else "temporizador",
                       "texto": obj.texto, "cuando": _epoch_de(o, ahora, epoch),
                       "cuando_texto": al._cuando_proxima(o, ahora)}
        d = self.aviso.sonando
        return {"activo": self._activo(), "dueno": self._dueno, "alarmas": alarmas,
                "temporizadores": temps, "proxima": proxima,
                "sonando": self._payload(d) if d is not None else None,
                "cola": len(self.aviso.cola), "ahora": epoch, "sonidos": ["azar", *SONIDOS]}

    def _resultado(self, ok: bool, error: str = "", **extra) -> dict:
        if ok:
            self._emitir_cambio(True)
        r = {"ok": bool(ok), "error": str(error or "")}
        r.update(extra)
        r["estado"] = self.listar()
        return r

    def guardar_alarma(self, d: dict) -> dict:
        """Crea (sin id o con uno que no existe) o actualiza una alarma.
        {id?, hora: "HH:MM", dias: "lmxjv" | máscara, una_vez, texto, activa, fecha}.
        Solo cambia lo que viene. → {ok, error, id, estado}."""
        if not isinstance(d, dict):
            return self._resultado(False, "datos no válidos")
        try:
            campos: Dict[str, Any] = {}
            hora = d.get("hora")
            if isinstance(hora, int) and not isinstance(hora, bool):
                # {hora: 7, minuto: 30} (así lo manda ui/puente_alarmas.py)
                campos["hora"], campos["minuto"] = int(hora), int(d.get("minuto", 0) or 0)
            elif "hora" in d:
                h, m = al.parsear_hora(hora)
                campos["hora"], campos["minuto"] = h, m
            elif "h" in d or "m" in d:
                campos["hora"], campos["minuto"] = int(d.get("h", 0)), int(d.get("m", 0))
            if "dias" in d:
                campos["dias"] = al.parsear_dias(d.get("dias"))
            for k in ("una_vez", "activa"):
                if k in d:
                    campos[k] = bool(d.get(k))
            if "texto" in d:
                campos["texto"] = al.limpiar_texto(d.get("texto"))
            if "fecha" in d:
                campos["fecha"] = str(d.get("fecha") or "")
            id_ = str(d.get("id") or "").strip()
            if id_ and not _ID.fullmatch(id_):
                return self._resultado(False, "id no válido")
            if id_ and isinstance(self.almacen.obtener(id_), al.Alarma):
                if not self.almacen.actualizar(id_, **campos):
                    return self._resultado(False, "no existe esa alarma")
            else:
                if "hora" not in campos:
                    return self._resultado(False, "falta la hora")
                a = self.almacen.crear_alarma(campos["hora"], campos["minuto"], campos.get("dias", 0),
                                              campos.get("una_vez", False), campos.get("texto", ""),
                                              fecha=campos.get("fecha", ""), activa=campos.get("activa", True))
                id_ = a.id
        except (TypeError, ValueError) as e:
            return self._resultado(False, str(e))
        return self._resultado(True, id=id_)

    def crear_temporizador(self, d: dict) -> dict:
        """{segundos | duracion_s | h, m, s; texto; iniciar=True; una_vez=False} → {ok, error, id, estado}."""
        if not isinstance(d, dict):
            return self._resultado(False, "datos no válidos")
        try:
            if d.get("segundos") is not None or d.get("duracion_s") is not None:
                seg = int(d.get("segundos") if d.get("segundos") is not None else d.get("duracion_s"))
            elif d.get("duracion") is not None:
                seg = al.parsear_duracion(d.get("duracion"))
            else:
                seg = int(d.get("h", 0) or 0) * 3600 + int(d.get("m", 0) or 0) * 60 + int(d.get("s", 0) or 0)
            t = self.almacen.crear_temporizador(seg, al.limpiar_texto(d.get("texto")),
                                                iniciar=bool(d.get("iniciar", True)),
                                                una_vez=bool(d.get("una_vez", False)))
        except (TypeError, ValueError) as e:
            return self._resultado(False, str(e))
        return self._resultado(True, id=t.id)

    def borrar(self, id_: str) -> bool:
        id_ = str(id_ or "")
        if not _ID.fullmatch(id_):
            return False
        ok = self.almacen.borrar(id_)
        if ok:
            self._emitir_cambio(True)
        return ok

    def temporizador_accion(self, id_: str, accion: str) -> bool:
        id_ = str(id_ or "")
        if not _ID.fullmatch(id_):
            return False
        ok = self.almacen.temporizador(id_, str(accion or ""))
        if ok:
            self._emitir_cambio(True)
        return ok

    def apagar(self, forzar: bool = False) -> bool:
        return bool(self.aviso.apagar(forzar))

    def posponer(self) -> bool:
        ok = bool(self.aviso.posponer())
        if ok:
            self._emitir_cambio(True)
        return ok

    def probar(self) -> bool:
        """Hace sonar una alarma de prueba (con todo lo visual)."""
        ahora = self._ahora()
        d = Disparo("prueba", "Prueba de alarma", "prueba", 0.0, ahora.strftime("%H:%M"), self._epoch())
        self._disparar(d)
        return True

    def rapido(self, minutos: int = 5) -> dict:
        """Temporizador rápido de `minutos` (se borra al sonar)."""
        try:
            minutos = int(minutos)
        except (TypeError, ValueError):
            minutos = 5
        minutos = min(max(minutos, 1), 24 * 60)
        try:
            t = self.almacen.crear_temporizador(minutos * 60, "", iniciar=True, una_vez=True)
        except ValueError as e:
            return self._resultado(False, str(e))
        return self._resultado(True, id=t.id)

    def abrir_dialogo(self, parent=None):
        """Editor de alarmas de la nativa (DialogoAlarmas); uno solo a la vez."""
        from ui.alarmas_dialogo import DialogoAlarmas
        ed = self._editor
        try:
            if ed is not None and ed.isVisible():
                ed.raise_()
                ed.activateWindow()
                return ed
        except RuntimeError:
            ed = None
        self._editor = DialogoAlarmas(self, parent)
        self._editor.show()
        return self._editor

    def herramientas(self) -> Dict[str, Callable]:
        """temporizador, alarma, cancelar_alarma y listar_alarmas sobre este almacén."""
        return al.handlers(self.almacen, self.config, al_cambiar=self._pedir_refresco)

    def _pedir_refresco(self) -> None:
        """`al_cambiar` de las herramientas (hilo del Ejecutor), por el puente de ahora:
        cerrado tras `detener` o si el controlador ya se borró, no hace nada."""
        self._puente_refresco()


def _epoch_de(o: datetime, ahora: datetime, epoch: float) -> float:
    return float(epoch) + (o - ahora).total_seconds()


__all__ = ("ControlAlarmasQt",)
