"""
ui/actualizacion_qt.py — El actualizador en las interfaces de ventanas (web y nativa).

La lógica (GitHub Releases, git, descargar con su SHA-256 y lanzar el instalador) vive sin
Qt en servicios/actualizador.py. Aquí va lo que la pone en marcha sin congelar la ventana:

  ControlActualizacion  el estado de la tarjeta «Actualizaciones»: la web (ui/web_bridge.py,
                        slots actualizacion_* y la señal `actualizacion`) y la nativa
                        (ui/settings_panel.py, instalada). Buscar, descargar con progreso (como
                        mucho ~4 avisos por segundo: en la web cada uno cruza el QWebChannel en
                        JSON), cancelar, omitir e instalar. «Instalar y reiniciar» descarga si
                        hace falta, lanza el Setup y me cierra con el «Salir» de la bandeja; desde
                        el código (git) es `git pull` + pip y reiniciar.
  AvisoInicio           el aviso de versión nueva al abrir Lune: ~45 s después, como mucho una
                        vez cada 24 h (actualizaciones.ultima_comprobacion), nunca en modo juego
                        (ni la búsqueda ni el aviso: espera a que acabe la partida). Lo programa
                        main() una vez por proceso, encima del GestorInterfaz: avisa a la
                        ventana que esté abierta entonces (avisar_actualizacion del puente web o
                        de la nativa), aunque hayas cambiado de interfaz en medio.

El trabajo lento (red, git, pip) va en un hilo normal (daemon) que avisa al hilo de Qt con una
señal en cola y un emisor que se calla cuando el QObject ya no existe: cerrar Lune a mitad de
una descarga no espera a la red ni deja un QThread vivo (se para con un Event y el .part que
quede lo borra la próxima descarga). ultima_comprobacion y omitir_version se escriben siempre
aquí, en el hilo de Qt.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, pyqtSignal

from servicios import actualizador

_log = logging.getLogger("lune.actualizacion")

RETRASO_AVISO_MS = 45_000          # el aviso al iniciar, cuando ya está todo abierto
REINTENTO_JUEGO_MS = 60_000        # con un juego delante, se vuelve a mirar cada minuto
INTERVALO_PROGRESO_S = 0.25        # como mucho ~4 avisos de progreso por segundo
ESPERA_SALIR_MS = 1500             # «Me cierro para instalarme…» se llega a leer
FASES = ("buscando", "hay", "al_dia", "descargando", "lista", "instalando", "error")
# Lo del resultado de buscar que viaja a la tarjeta (además de fase, bytes, total, pct…).
_CLAVES_RELEASE = ("version", "actual", "notas", "fecha", "pagina", "instalable", "omitida", "nueva",
                   "commits", "pendientes", "limpio", "modificados", "rama")


def _hilo(fn: Callable[[], Any]) -> None:
    threading.Thread(target=fn, name="lune-actualizar", daemon=True).start()


class _Emisor:
    """Lo que el hilo llama para pasar `fn(valor)` al hilo de Qt: emite la señal interna del
    dueño SOLO si el objeto de C++ sigue vivo, y cerrado no hace nada (como ui/minecraft_qt._Aviso).
    Nunca se guarda la señal ligada: emitirla con el QObject borrado revienta."""

    def __init__(self, dueno: QObject, senal: str):
        self._lock = threading.Lock()
        self._dueno: Optional[QObject] = dueno
        self._senal = senal

    def cerrar(self) -> None:
        with self._lock:
            self._dueno = None

    def __call__(self, fn: Callable[[Any], Any], valor: Any = None) -> None:
        with self._lock:
            d = self._dueno
            if d is None:
                return
            try:
                if sip.isdeleted(d):
                    self._dueno = None
                    return
                getattr(d, self._senal).emit(fn, valor)
            except (RuntimeError, AttributeError):
                self._dueno = None


class Limitador:
    """¿Toca avisar del progreso? El primero, el último (n >= total) y, entre medias, como
    mucho uno cada `intervalo` segundos."""

    def __init__(self, intervalo: float = INTERVALO_PROGRESO_S, reloj: Callable[[], float] = time.monotonic):
        self.intervalo = float(intervalo)
        self._reloj = reloj
        self._ultimo: Optional[float] = None

    def __call__(self, n: int, total: int) -> bool:
        ahora = self._reloj()
        if self._ultimo is None or (total and n >= total) or ahora - self._ultimo >= self.intervalo:
            self._ultimo = ahora
            return True
        return False


def salir_de_verdad_de(objeto: Any) -> Callable[[], None]:
    """El «Salir» de la bandeja de la ventana de `objeto` (suelta el bot, la asistente, la IA…
    y cierra la app); si no la encuentra subiendo por los padres, QApplication.quit()."""
    def salir() -> None:
        o = objeto
        for _ in range(64):
            if o is None:
                break
            fn = getattr(o, "salir_de_verdad", None)
            if callable(fn):
                fn()
                return
            padre = getattr(o, "parent", None)
            try:
                o = padre() if callable(padre) else None
            except Exception:
                o = None
        app = QCoreApplication.instance()
        if app is not None:
            app.quit()
    return salir


def en_juego(ventana: Any) -> bool:
    """¿Hay partida? (BusEstado.juego de los servicios de escritorio de la ventana, web o nativa)."""
    for obj in (getattr(ventana, "bridge", None), ventana):
        esc = getattr(obj, "escritorio", None)
        if esc is None:
            continue
        try:
            return bool(esc.estado.actual().juego)
        except Exception:
            continue
    return False


def destino_aviso(ventana: Any) -> Optional[Callable[[Dict], Any]]:
    """avisar_actualizacion(res) del puente web (window.lune) o de la ventana nativa."""
    for obj in (getattr(ventana, "bridge", None), ventana):
        fn = getattr(obj, "avisar_actualizacion", None)
        if callable(fn):
            return fn
    return None


def notificar(ventana: Any, texto: str) -> bool:
    """El aviso de siempre: ServiciosCorte4.avisar (globo de la bandeja con la ventana
    escondida; si se ve, el toast de la web o la barra de estado de la nativa). False si
    no hay con qué (quien llama usa su respaldo)."""
    fn = getattr(getattr(ventana, "_servicios_c4", None), "avisar", None)
    if not callable(fn):
        return False
    try:
        fn(str(texto))
        return True
    except Exception:
        _log.exception("actualizaciones: el aviso falló")
        return False


class ControlActualizacion(QObject):
    """El estado de la tarjeta «Actualizaciones» de una interfaz (ver la cabecera).

    `cambio(dict)`: {fase, modo, version, notas, bytes, total, pct, mensaje, …} con fase en FASES.
    `salir()`: cerrar Lune de verdad (salir_de_verdad_de(...)); `funciones` sustituye las de
    servicios/actualizador (buscar, descargar, instalar, actualizar, reiniciar) y `lanzar(fn)`
    cómo se corre el trabajo lento (por defecto un hilo daemon): son para los tests."""

    cambio = pyqtSignal(object)
    _de_hilo = pyqtSignal(object, object)       # interna: (fn, valor) → fn(valor) en el hilo de Qt

    def __init__(self, config, *, modo: Optional[str] = None, salir: Optional[Callable[[], Any]] = None,
                 funciones: Optional[Dict[str, Callable]] = None,
                 lanzar: Optional[Callable[[Callable[[], Any]], Any]] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._modo = modo or actualizador.modo()
        self._salir = salir
        self._f: Dict[str, Callable] = {
            "buscar": actualizador.buscar_novedades, "descargar": actualizador.descargar,
            "instalar": actualizador.instalar, "actualizar": actualizador.actualizar,
            "reiniciar": actualizador.reiniciar, **(funciones or {}),
        }
        self._lanzar = lanzar or _hilo
        self._cancelar = threading.Event()
        self._ocupado: Optional[str] = None     # "buscar" | "descargar" | "git"
        self._release: Optional[Dict] = None    # lo último que dio buscar (o el aviso al iniciar)
        self._ruta = ""                         # Setup descargado y comprobado
        self._git_listo = False                 # git pull hecho: falta reiniciar
        self._instalar_al_acabar = False        # «Instalar y reiniciar» antes de tener la descarga
        self._estado: Dict[str, Any] = {}
        self._emisor = _Emisor(self, "_de_hilo")
        self._de_hilo.connect(self._en_qt, Qt.ConnectionType.QueuedConnection)
        self._timer_salir = QTimer(self)
        self._timer_salir.setSingleShot(True)
        self._timer_salir.timeout.connect(self._salir_ya)

    # ── Estado ────────────────────────────────────────────────────────────────
    @property
    def modo(self) -> str:
        return self._modo

    @property
    def ocupado(self) -> bool:
        return self._ocupado is not None

    def _cfg(self, clave: str, defecto: Any = None) -> Any:
        try:
            return self.config.get("actualizaciones", clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def estado(self) -> Dict[str, Any]:
        return dict(self._estado)

    def info(self) -> Dict[str, Any]:
        """Lo que pinta la tarjeta al abrirse (síncrono y barato: sin red)."""
        return {
            "version": actualizador.version_actual(), "modo": self._modo,
            "al_iniciar": bool(self._cfg("comprobar_al_iniciar", True)),
            "ultima_comprobacion": str(self._cfg("ultima_comprobacion", "") or ""),
            "omitir_version": str(self._cfg("omitir_version", "") or ""),
            "pagina": str((self._release or {}).get("pagina") or actualizador.URL_RELEASES),
            "ocupado": self.ocupado, "descargado": bool(self._ruta), "estado": self.estado(),
        }

    def _fase(self, fase: str, base: Optional[Dict] = None, **datos) -> Dict[str, Any]:
        d: Dict[str, Any] = {"fase": fase, "modo": self._modo, "version": "", "notas": "",
                             "bytes": 0, "total": 0, "pct": 0, "mensaje": ""}
        for k in _CLAVES_RELEASE:
            if isinstance(base, dict) and base.get(k) is not None:
                d[k] = base[k]
        if isinstance(base, dict) and isinstance(base.get("asset"), dict):
            d["total"] = int(base["asset"].get("tamano") or 0)      # «~239 MB» antes de descargar
        d.update({k: v for k, v in datos.items() if v is not None})
        self._estado = d
        try:
            self.cambio.emit(dict(d))
        except RuntimeError:
            pass
        return d

    def _en_qt(self, fn, valor) -> None:
        try:
            fn(valor)
        except Exception:
            _log.exception("actualizaciones: fallo al recibir un resultado")

    # ── Buscar ────────────────────────────────────────────────────────────────
    def buscar(self) -> bool:
        """Mira si hay versión nueva (o commits, desde el código). False si ya hay algo en marcha."""
        if self._ocupado:
            return False
        self._ocupado = "buscar"
        donde = "el remoto de git" if self._modo == actualizador.MODO_GIT else "GitHub"
        self._fase("buscando", mensaje=f"Buscando en {donde}…")
        rama = str(self._cfg("rama", "master") or "master")
        buscar_fn, modo = self._f["buscar"], self._modo

        def trabajo():
            try:
                res = buscar_fn(modo, rama=rama)
            except Exception as e:
                res = {"ok": False, "hay_novedades": False, "mensaje": f"No pude buscar: {e}"}
            self._emisor(self._al_buscado, res)
        self._lanzar(trabajo)
        return True

    def _al_buscado(self, res: Dict) -> None:
        self._ocupado = None
        res = res if isinstance(res, dict) else {}
        actualizador.marcar_comprobacion(self.config)
        self._mostrar_resultado(res)

    def _mostrar_resultado(self, res: Dict) -> None:
        if not res.get("ok"):
            self._fase("error", res, mensaje=res.get("mensaje") or "No pude buscar actualizaciones.")
            return
        if self._modo != actualizador.MODO_GIT:
            anterior = (self._release or {}).get("version")
            self._release = dict(res)
            if anterior and not actualizador.misma_version(anterior, res.get("version")):
                self._ruta = ""                  # otra versión: lo descargado ya no vale
        self._fase("hay" if res.get("hay_novedades") else "al_dia", res,
                   mensaje=res.get("mensaje") or "")

    def recibir(self, res: Dict) -> None:
        """El aviso al iniciar encontró algo: la tarjeta lo enseña (y se resalta) al abrirse."""
        if self._ocupado or not isinstance(res, dict) or not res.get("ok"):
            return
        self._mostrar_resultado(res)

    # ── Descargar (instalada) o git pull (desde el código) ─────────────────────
    def descargar(self) -> bool:
        """Instalada: baja el Setup del último release (comprobando tamaño y SHA-256). Desde el
        código: `git pull` + pip (actualizador.actualizar). False si no toca o ya hay algo."""
        if self._ocupado:
            return False
        if self._modo == actualizador.MODO_GIT:
            return self._git_actualizar()
        if self._modo != actualizador.MODO_INSTALADA:
            return False
        rel = self._release or {}
        if not rel.get("instalable"):
            self._instalar_al_acabar = False
            self._fase("error", rel, mensaje=("Primero busco si hay una versión nueva." if not rel else
                                              rel.get("mensaje") if not rel.get("nueva") else
                                              "No puedo comprobar ese instalador (falta su SHA-256 en "
                                              "GitHub), así que no lo descargo."))
            return False
        self._ocupado = "descargar"
        self._cancelar.clear()
        total = int((rel.get("asset") or {}).get("tamano") or 0)
        self._fase("descargando", rel, bytes=0, total=total, pct=0, mensaje="Empiezo la descarga…")
        descargar_fn, cancelar, info = self._f["descargar"], self._cancelar, dict(rel)
        limite = Limitador()

        def progreso(n, t):
            if limite(n, t):
                self._emisor(self._al_progreso, (int(n), int(t)))

        def trabajo():
            try:
                res = descargar_fn(info, on_progreso=progreso, cancelar=cancelar)
            except Exception as e:
                res = {"ok": False, "mensaje": f"No pude descargarlo: {e}"}
            self._emisor(self._al_descargado, res)
        self._lanzar(trabajo)
        return True

    def _al_progreso(self, valor) -> None:
        if self._ocupado != "descargar":
            return
        n, t = valor
        pct = max(0, min(100, int(n * 100 / t))) if t else 0
        self._fase("descargando", self._release, bytes=n, total=t, pct=pct,
                   mensaje=f"Descargando {_mb(n)} de {_mb(t)} ({pct} %)…")

    def _al_descargado(self, res: Dict) -> None:
        self._ocupado = None
        res = res if isinstance(res, dict) else {}
        if res.get("ok"):
            self._ruta = str(res.get("ruta") or "")
            t = int(((self._release or {}).get("asset") or {}).get("tamano") or 0)
            self._fase("lista", self._release, bytes=t, total=t, pct=100,
                       mensaje=res.get("mensaje") or "Descargado y comprobado.")
            if self._instalar_al_acabar:
                self._instalar_al_acabar = False
                self.instalar()
            return
        self._instalar_al_acabar = False
        if res.get("cancelado"):
            self._fase("hay", self._release, mensaje="Cancelé la descarga. Cuando quieras, la retomo.")
            return
        self._fase("error", self._release, mensaje=res.get("mensaje") or "No pude descargarlo.")

    def _git_actualizar(self) -> bool:
        self._ocupado = "git"
        self._fase("descargando", self._estado if self._estado.get("fase") == "hay" else None,
                   mensaje="Trayendo cambios…")
        actualizar_fn = self._f["actualizar"]
        rama = str(self._cfg("rama", "master") or "master")

        def trabajo():
            try:
                res = actualizar_fn(rama, on_progreso=lambda m: self._emisor(self._al_progreso_git, m))
            except Exception as e:
                res = {"ok": False, "actualizado": False, "mensaje": f"Algo falló: {e}"}
            self._emisor(self._al_git, res)
        self._lanzar(trabajo)
        return True

    def _al_progreso_git(self, mensaje) -> None:
        if self._ocupado == "git":
            self._fase("descargando", mensaje=str(mensaje or ""))

    def _al_git(self, res: Dict) -> None:
        self._ocupado = None
        res = res if isinstance(res, dict) else {}
        if not res.get("ok"):
            self._instalar_al_acabar = False
            self._fase("error", mensaje=res.get("mensaje") or "No pude actualizar.")
            return
        if not res.get("actualizado"):
            self._instalar_al_acabar = False
            self._fase("al_dia", mensaje=res.get("mensaje") or "Ya estaba al día.")
            return
        self._git_listo = True
        mensaje = res.get("mensaje") or "Actualizada."
        if res.get("requisitos_ok") is False:
            mensaje += " Ojo: no pude instalar alguna dependencia."
        self._fase("lista", mensaje=mensaje)
        if self._instalar_al_acabar:
            self._instalar_al_acabar = False
            self.instalar()

    def cancelar(self) -> bool:
        """Corta la descarga en curso (el .part se borra). git pull no se corta a medias."""
        self._instalar_al_acabar = False
        if self._ocupado != "descargar":
            return False
        self._cancelar.set()
        return True

    # ── Instalar y reiniciar ──────────────────────────────────────────────────
    def instalar(self) -> bool:
        """«Instalar y reiniciar» (ya confirmado): si falta, descarga primero y sigue sola. Con el
        Setup listo lo lanza y me cierra con el «Salir» de verdad; desde el código, reinicia
        tras el git pull. False si no se puede (o en una copia sin git)."""
        if self._modo == actualizador.MODO_GIT:
            if self._git_listo and not self._ocupado:
                self._fase("instalando", mensaje="Me reinicio con lo nuevo…")
                self._timer_salir.start(ESPERA_SALIR_MS)
                return True
            if self._ocupado == "git":
                self._instalar_al_acabar = True
                return True
            if self._ocupado:
                return False
            self._instalar_al_acabar = True
            return self.descargar()
        if self._modo != actualizador.MODO_INSTALADA:
            return False
        if self._ocupado == "descargar":
            self._instalar_al_acabar = True
            return True
        if self._ocupado:
            return False
        if not self._ruta:
            self._instalar_al_acabar = True
            return self.descargar()
        sha = str((self._release or {}).get("sha256") or "")
        try:
            ok = bool(self._f["instalar"](self._ruta, sha256=sha))
        except Exception:
            ok = False
        if not ok:
            self._ruta = ""
            self._fase("error", self._release, mensaje="No pude abrir el instalador. Vuelve a intentarlo.")
            return False
        self._fase("instalando", self._release,
                   mensaje="Me cierro para instalarme. Vuelvo a abrirme sola en un momento.")
        self._timer_salir.start(ESPERA_SALIR_MS)
        return True

    def _salir_ya(self) -> None:
        if self._modo == actualizador.MODO_GIT:
            try:
                ok = self._f["reiniciar"](salir=lambda _codigo=0: self._cerrar_lune())
            except Exception:
                ok = False
            if ok is False:
                self._fase("error", mensaje="No pude reiniciarme. Ciérrame y vuelve a abrirme.")
            return
        self._cerrar_lune()

    def _cerrar_lune(self) -> None:
        fn = self._salir
        if fn is None:
            app = QCoreApplication.instance()
            fn = app.quit if app is not None else (lambda: None)
        fn()

    # ── Omitir y «Buscar al iniciar» ──────────────────────────────────────────
    def omitir(self, version: Any) -> bool:
        """Salta esa versión en el aviso al iniciar ("" = ya no saltar ninguna)."""
        v = actualizador.texto_version(version) if str(version or "").strip() else ""
        if str(version or "").strip() and not v:
            return False
        try:
            self.config.set("actualizaciones", "omitir_version", v)
        except Exception:
            return False
        rel = self._release
        if rel and self._estado.get("fase") in ("hay", "al_dia", "error") and rel.get("nueva"):
            rel["omitida"] = bool(v) and actualizador.misma_version(rel.get("version"), v)
            rel["hay_novedades"] = not rel["omitida"]
            if rel["omitida"]:
                rel["mensaje"] = f"Vale, me salto la {rel.get('version')}. Te aviso de la siguiente."
                self._fase("al_dia", rel, mensaje=rel["mensaje"])
            else:
                rel["mensaje"] = f"Hay una versión nueva de mí: la {rel.get('version')}."
                self._fase("hay", rel, mensaje=rel["mensaje"])
        return True

    def al_iniciar(self, on: Any) -> bool:
        try:
            self.config.set("actualizaciones", "comprobar_al_iniciar", bool(on))
        except Exception:
            return False
        return True

    def detener(self) -> None:
        """Al cerrar la ventana: corta la descarga y ya no avisa de nada."""
        self._instalar_al_acabar = False
        self._cancelar.set()
        self._emisor.cerrar()
        try:
            self._timer_salir.stop()
        except RuntimeError:
            pass


def _mb(n: int) -> str:
    return f"{(n or 0) / (1024 * 1024):.0f} MB"


class AvisoInicio(QObject):
    """El aviso de versión nueva al abrir Lune (ver la cabecera). `ventana()` da la ventana
    principal de ahora (la del GestorInterfaz); `buscar`, `lanzar` y `en_juego` son para los tests."""

    avisado = pyqtSignal(object)                # el resultado que se avisó
    _de_hilo = pyqtSignal(object, object)

    def __init__(self, config, *, ventana: Callable[[], Any], retraso_ms: int = RETRASO_AVISO_MS,
                 reintento_ms: int = REINTENTO_JUEGO_MS, buscar: Optional[Callable[..., Dict]] = None,
                 lanzar: Optional[Callable[[Callable[[], Any]], Any]] = None,
                 en_juego: Optional[Callable[[Any], bool]] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._ventana = ventana
        self.retraso_ms = max(0, int(retraso_ms))
        self.reintento_ms = max(1, int(reintento_ms))
        self._buscar = buscar or actualizador.buscar_novedades
        self._lanzar = lanzar or _hilo
        self._en_juego = en_juego or globals()["en_juego"]
        self._buscando = False
        self._pendiente: Optional[Dict] = None   # encontrado, esperando a que acabe la partida
        self._emisor = _Emisor(self, "_de_hilo")
        self._de_hilo.connect(self._en_qt, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tic)

    def iniciar(self) -> bool:
        """Programa la búsqueda si toca (Buscar al iniciar y 24 h desde la última)."""
        if not actualizador.toca_comprobar(self.config):
            return False
        self._timer.start(self.retraso_ms)
        return True

    def detener(self) -> None:
        self._timer.stop()
        self._emisor.cerrar()
        self._pendiente = None

    def _v(self):
        try:
            return self._ventana()
        except Exception:
            return None

    def _jugando(self, v) -> bool:
        try:
            return bool(self._en_juego(v))
        except Exception:
            return False

    def _en_qt(self, fn, valor) -> None:
        try:
            fn(valor)
        except Exception:
            _log.exception("actualizaciones: fallo en el aviso al iniciar")

    def _tic(self) -> None:
        if self._pendiente is not None:
            self._entregar()
            return
        if self._buscando:
            return
        v = self._v()
        if v is None or self._jugando(v):
            self._timer.start(self.reintento_ms)      # nunca en modo juego: después de la partida
            return
        if not actualizador.toca_comprobar(self.config):
            return                                    # lo apagaste, o ya miró otra ventana
        self._buscando = True
        buscar = self._buscar
        rama = "master"
        try:
            rama = str(self.config.get("actualizaciones", "rama", "master") or "master")
        except Exception:
            pass

        def trabajo():
            try:
                res = buscar(rama=rama)
            except Exception as e:
                res = {"ok": False, "hay_novedades": False, "mensaje": str(e)}
            self._emisor(self._al_buscado, res)
        self._lanzar(trabajo)

    def _al_buscado(self, res: Dict) -> None:
        self._buscando = False
        actualizador.marcar_comprobacion(self.config)
        if isinstance(res, dict) and res.get("ok") and res.get("hay_novedades"):
            self._pendiente = dict(res)
            self._entregar()

    def _entregar(self) -> None:
        v = self._v()
        if v is None or self._jugando(v):
            self._timer.start(self.reintento_ms)
            return
        res, self._pendiente = self._pendiente, None
        fn = destino_aviso(v)
        if fn is None:
            notificar(v, actualizador.texto_aviso(res))
        else:
            try:
                fn(res)
            except Exception:
                _log.exception("actualizaciones: la ventana no pudo avisar")
        try:
            self.avisado.emit(res)
        except RuntimeError:
            pass
