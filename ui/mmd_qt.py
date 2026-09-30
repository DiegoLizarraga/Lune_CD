"""
ui/mmd_qt.py — `ControlMMD`: el reproductor de bailes MMD/VRMA (corte 9).

Controlador `mmd` de ServiciosEscritorio (ui/escritorio.py), actividad `mmd` de
la tabla de prioridades (40): cede ante juego, alarma, pantalla grande y
salvapantallas (se pausa y sigue al acabar) y le quita el sitio a la sentada, la
comida y el baile automático (que vuelven solos al acabar si procede).

La biblioteca es nucleo/bailes.Biblioteca y el orden, nucleo/bailes.Cola. El
camino depende de la asistente (`asistente.render`):

- `vrm` (con `asistente.mmd`): `asistente.mmd("cargar", {…tipo vmd|vrma…})`. La
  página hornea el VMD (o carga el .vrma), pone la canción en su `<audio>` y
  avisa con eventos `mmd` (cargando, listo, sonando, pausado, t, fin, parado,
  error) que llegan aquí por `evento_asistente`.
- `animado` (con `asistente.mmd`): D1, sin esqueleto. `asistente.mmd("cargar",
  {tipo:"audio", audio, bpm, fase0, …})`: la página pone la canción y baila el
  baile procedural al pulso analizado (Biblioteca.analizar_pulso, en un hilo).
- `sprites` (o cualquier asistente sin `mmd`): D1 en Python. La canción suena por
  el Mezclador (servicios/cancion_python.ReproductorCancion) y la asistente hace
  `bailar(True, {estilo…})` + `pulso(bpm, fase, 0.7)` a 2 Hz con la posición de
  la canción.
- Sin asistente: `despachador.ejecutar("asistente")` y el baile queda pendiente
  hasta el siguiente `set_asistente(v)` (12 s como mucho).
- Asistente ESCONDIDA (no cerrada): al pedir un baile (▶, el modelo, «siguiente» sin
  nada puesto) se saca como la acción «asistente»; si no se puede, se avisa. Oculta no
  lee su cola de eventos: el vigía («la asistente no respondió») no cuenta hasta que se
  la vea, y un «siguiente» a mitad espera a que vuelva (la página lo aplaza). Los
  sprites ocultos o cerrados pausan la canción (y el pulso) y al volver sigue.

Pausa (D5): en la VRM la página la lleva al reposo en 0.6 s y sigue desde el
mismo punto. `ceder` (juego, alarma, grande) = pausa; `reanudar` = sigue (si
no la había pausado la persona). `al_terminar` (config baile.al_terminar):
parar | siguiente | repetir (bucle en la página) | aleatorio.

La biblioteca: la lista, buscar, ▶, favoritos… miran la FOTO de la biblioteca
(nunca escanean en el hilo de Qt ni esperan a un escaneo o a un importar); el
escaneo va en un hilo (`refrescar`, al iniciar y al importar).

Órdenes a la asistente (contrato con ui/companion.py `mmd(orden, datos)`):
    cargar  {id, tipo, motion:[url], cara:[url], audio, offsetMs, enSitio, brazoGrados,
             volumen, bucle, autoplay, titulo}  (tipo "audio": audio, bpm, fase0 en vez de motion/cara)
    pausa {on}   parar None   volumen {volumen}   offset {offsetMs}   en_sitio {enSitio}   bucle {bucle}

Señales (JSON en texto, para el puente web):
    estado_cambio(str)      {fase, id, titulo, autor, autor_mmd, t, total, modo, al_terminar, volumen,
                             en_el_sitio, error, analizando, pausado, cedida, pendiente, modo_asistente,
                             sin_esqueleto, importando}
    biblioteca_cambio(str)  [{id, titulo, autor_cancion, autor_mmd, tipo, duracion, audio, favorito,
                              desactivado, problema, …}]
    importado(str)          {ok, texto, id}
    vista_pedida(str)       'bailes'
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from nucleo import baile as nb
from nucleo import bailes as nbl
from nucleo import estado_asistente as em
from nucleo.estado_asistente import BAILE_MMD

_log = logging.getLogger("lune.mmd")

FASES = ("parado", "cargando", "listo", "sonando", "pausado", "saliendo", "error")
PULSO_MS = 500                  # ≤ 2 Hz hacia la asistente (sprites)
ESPERA_ASISTENTE_MS = 12_000      # sin asistente: lo que se espera a que salga
VIGIA_PRIMERA_MS = 10_000       # tras «cargar», la página tiene que decir algo
VIGIA_CARGA_MS = 60_000         # y, cargando, acabar de cargar
ENERGIA_D1 = 0.7
DUCK = 0.35                     # la voz de Lune baja la canción (sprites; la página hace lo suyo)
T_MAX = 7200.0
FILTRO_DIALOGO = ("Bailes (*.vmd *.vrma *.mp3 *.ogg *.oga *.opus *.wav *.flac *.m4a *.aac *.wma);;"
                  "Todos los archivos (*)")
MOTIVOS_SIN_BAILE = ("no_encontrado", "sin_bailes", "problema")


AVISO_ESCONDIDA = "Estoy escondida: bailaré cuando me saques al escritorio."
AVISO_MIRANDO = "Aún estoy mirando tus bailes: prueba en un momento."


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) and f >= 0 else None


def _vivo(obj: Any) -> bool:
    """¿Existe aún (un QObject borrado —la asistente que se cierra— no se toca)?"""
    if obj is None:
        return False
    try:
        return not (isinstance(obj, sip.simplewrapper) and sip.isdeleted(obj))
    except Exception:
        return False


def dialogo_archivos(parent: Any = None) -> List[str]:
    """Los archivos que elige la persona (QFileDialog modal). Se crea en el montón y no con
    QFileDialog.getOpenFileNames: si la ventana padre se borra con el diálogo abierto (Salir
    desde la bandeja, cambio de interfaz), la estática revienta al volver (su diálogo en la
    pila ya lo borró el padre). Así Qt lo borra con el padre, exec() vuelve y se mira antes
    de tocarlo."""
    from PyQt6.QtWidgets import QFileDialog, QWidget
    padre = parent if isinstance(parent, QWidget) and _vivo(parent) else None
    dlg = QFileDialog(padre, "Importar un baile (movimiento y canción)", str(Path.home()), FILTRO_DIALOGO)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    try:
        aceptado = dlg.exec()
        if not _vivo(dlg):
            return []                                  # se fue con su padre: nada que importar
        return [str(p) for p in dlg.selectedFiles()] if aceptado else []
    finally:
        if _vivo(dlg):
            dlg.deleteLater()


class ControlMMD(QObject):
    """Reproductor de bailes (ver la cabecera del módulo)."""

    estado_cambio = pyqtSignal(str)
    biblioteca_cambio = pyqtSignal(str)
    importado = pyqtSignal(str)
    vista_pedida = pyqtSignal(str)

    # De los hilos (análisis, canción, escaneo, importar) al de Qt.
    _hecho_hilo = pyqtSignal(object)

    def __init__(self, escritorio: Any, config: Any, *, biblioteca: Any = None,
                 cancion: Optional[Callable[[], Any]] = None, anfitrion: Any = None,
                 en_ui: Optional[Callable] = None, reloj: Callable[[], float] = time.monotonic,
                 parent: Optional[QObject] = None, hilo: bool = True,
                 dialogo: Optional[Callable[[Any], List[str]]] = None,
                 abrir: Optional[Callable[[Path], Any]] = None, rng: Any = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.anfitrion = anfitrion
        self.biblioteca = biblioteca if biblioteca is not None else nbl.biblioteca_compartida(config)
        self.cola = nbl.Cola(self.biblioteca, rng=rng, fuente=self.biblioteca.foto)
        self._fab_cancion = cancion
        self._cancion: Any = None
        self._en_ui = en_ui
        self._reloj = reloj
        self._hilo = bool(hilo)
        self._dialogo = dialogo
        self._abrir = abrir
        self._asistente: Any = None
        self._iniciado = False
        self._bus_conectado = False
        # El baile en curso
        self._actual: Optional[nbl.Baile] = None
        self._ultimo_id = ""
        self._modo = ""                       # vrm | animado | sprites | ""
        self._fase = "parado"
        self._t = 0.0
        self._total = 0.0
        self._error = ""
        self._id_error = ""
        self._analizando = False
        self._pendiente = False               # esperando a que salga la asistente
        self._pausa_usuario = False
        self._cedida = False
        self._pausa_enviada = False
        self._prioridad_mia = False
        self._pulso: Dict[str, float] = {"bpm": nbl.BPM_DEFECTO, "fase0": 0.0, "confianza": 0.0}
        self._opciones: Dict[str, Any] = {}
        self._sprites_listo = False
        self._sprites_empezado = False
        self._ultimo_seg = -1
        self._importando = False
        self._oculta = False                  # sprites: la asistente no se ve → canción en pausa
        self._vigia_ms = 0                    # vigía pedido (con la asistente escondida, espera a verla)
        self._recien_sacada = False           # se sacó (o creó) para este baile: su página puede tardar
        self._gen = 0
        self._ultimo_estado = ""
        self.ultimo_motivo = ""
        self._t_pulso = QTimer(self)
        self._t_pulso.setInterval(PULSO_MS)
        self._t_pulso.timeout.connect(self._tic_pulso)
        self._t_vigia = QTimer(self)
        self._t_vigia.setSingleShot(True)
        self._t_vigia.timeout.connect(self._vigia_vencido)
        self._t_asistente = QTimer(self)
        self._t_asistente.setSingleShot(True)
        self._t_asistente.timeout.connect(self._asistente_no_llego)
        self._hecho_hilo.connect(self._on_hecho)

    # ── Acceso a lo compartido ───────────────────────────────────────────────────
    def _prioridad(self) -> Any:
        return getattr(self.escritorio, "prioridad", None)

    def _bus_actual(self) -> Any:
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _cfg(self, clave: str, defecto: Any) -> Any:
        try:
            return self.config.get("baile", clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def _cfg_set(self, clave: str, valor: Any) -> None:
        if self.config is None:
            return
        try:
            self.config.set("baile", clave, valor)
        except Exception:
            _log.exception("mmd: no pude guardar baile.%s", clave)

    def _al_terminar(self) -> str:
        v = str(self._cfg("al_terminar", nbl.AL_TERMINAR_DEFECTO) or "")
        return v if v in nbl.AL_TERMINAR else nbl.AL_TERMINAR_DEFECTO

    def _vol(self) -> float:
        try:
            v = float(self._cfg("volumen", 0.25))
        except (TypeError, ValueError):
            v = 0.25
        return max(0.0, min(1.0, v)) if math.isfinite(v) else 0.25

    def _vol_efectivo(self) -> float:
        est = self._bus_actual()
        hablando = bool(est is not None and getattr(est, "hablando", False))
        return self._vol() * (DUCK if hablando else 1.0)

    def _en_sitio_cfg(self) -> bool:
        return bool(self._cfg("en_el_sitio", True))

    def _en_sitio(self, b: nbl.Baile) -> bool:
        v = b.meta.get("en_el_sitio") if isinstance(b.meta, dict) else None
        return bool(v) if isinstance(v, bool) else self._en_sitio_cfg()

    def _pausada(self) -> bool:
        # Los sprites escondidos o cerrados no bailan: la canción espera (la VRM y la animada
        # se pausan solas al ocultarse, en ui/companion.py).
        return self._pausa_usuario or self._cedida or (self._modo == "sprites" and self._oculta)

    def _llamar_anfitrion(self, metodo: str, *args) -> Any:
        f = getattr(self.anfitrion, metodo, None) if self.anfitrion is not None else None
        if not callable(f):
            return None
        try:
            return f(*args)
        except Exception:
            _log.exception("mmd: anfitrion.%s falló", metodo)
            return None

    def _avisar(self, texto: str) -> None:
        self._llamar_anfitrion("aviso", texto)

    @property
    def activo(self) -> bool:
        """Hay un baile elegido (cargando, sonando, en pausa o esperando a la asistente)."""
        return self._actual is not None

    @property
    def actual(self) -> Optional[nbl.Baile]:
        return self._actual

    def _cancion_obj(self) -> Any:
        if self._cancion is None:
            if self._fab_cancion is not None:
                self._cancion = self._fab_cancion()
            else:
                from servicios.cancion_python import ReproductorCancion
                self._cancion = ReproductorCancion()
        return self._cancion

    # ── Ciclo de vida (contrato de ServiciosEscritorio) ─────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        try:
            self.biblioteca.asegurar_carpeta()
        except Exception:
            _log.exception("mmd: no pude crear la carpeta de bailes")
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and not self._bus_conectado:
            try:
                senal.connect(self._on_bus)
                self._bus_conectado = True
            except (TypeError, RuntimeError):
                pass
        self.refrescar()

    def detener(self) -> None:
        """Para lo que suene y suelta todo. Idempotente."""
        if self._actual is not None:
            self._terminar(enviar=True)
        self._gen += 1
        for t in (self._t_pulso, self._t_vigia, self._t_asistente):
            t.stop()
        self._vigia_ms = 0
        nbl.matar_procesos()                  # ningún ffmpeg (convertir, pulso, canción) sigue solo
        if self._bus_conectado:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._bus_conectado = False
        if self._cancion is not None:
            try:
                self._cancion.liberar()
            except Exception:
                pass
        self._iniciado = False

    def set_asistente(self, v: Any) -> None:
        if not _vivo(self):
            return                                     # (al salir: el reproductor ya se borró)
        anterior = self._asistente
        if self._actual is not None and not self._pendiente and v is not anterior:
            self._terminar(enviar=False)              # otra asistente (o ninguna): el baile acaba
        self._asistente = v
        if v is not None and self._actual is not None and self._pendiente:
            self._pendiente = False
            self._recien_sacada = True
            self._t_asistente.stop()
            self._despertar()
            self._arrancar()
            return
        self._emitir_estado()

    def ceder(self, c: Any) -> None:
        """Juego, alarma, pantalla grande o salvapantallas: pausa (VRM al reposo en 0.6 s)."""
        if self._actual is None:
            return
        self._cedida = True
        self._aplicar_pausa()
        self._emitir_estado()

    def reanudar(self, c: Any) -> None:
        """Acabó lo que la interrumpió (la tabla ya volvió a marcar `mmd`): sigue."""
        if self._actual is None or not self._prioridad_mia:
            pr = self._prioridad()
            if pr is not None:
                try:
                    pr.terminar("mmd")                # nada que reanudar: se suelta la actividad
                except Exception:
                    _log.exception("mmd: no pude soltar la actividad")
            return
        self._cedida = False
        self._aplicar_pausa()
        self._emitir_estado()

    def recargar_config(self) -> None:
        """Vuelve a aplicar volumen, bucle y en el sitio (tras guardar la config)."""
        if self._actual is not None:
            if self._modo in ("vrm", "animado"):
                self._enviar("volumen", {"volumen": self._vol()})
                self._enviar("bucle", {"bucle": self._al_terminar() == "repetir"})
                if self._modo == "vrm":
                    self._enviar("en_sitio", {"enSitio": self._en_sitio(self._actual)})
            elif self._modo == "sprites" and self._cancion is not None:
                self._cancion.volumen(self._vol_efectivo())
        self._emitir_estado()

    def evento_asistente(self, tipo: str, datos: Any) -> None:
        """Eventos `mmd` de la página: {fase, id, t, total, mensaje}."""
        if tipo != "mmd" or not isinstance(datos, dict) or self._actual is None:
            return
        if self._modo not in ("vrm", "animado") or self._pendiente:
            return
        id_ = datos.get("id")
        if id_ not in (None, "") and id_ != self._actual.id:
            return                                     # de un baile anterior
        fase = str(datos.get("fase") or "")
        t, total = _num(datos.get("t")), _num(datos.get("total"))
        if t is not None:
            self._t = min(t, T_MAX)
        if total is not None and total > 0:
            self._total = min(total, T_MAX)
        if fase == "cargando":
            self._fase = "cargando"
            self._armar_vigia(VIGIA_CARGA_MS)
        elif fase == "listo":
            self._parar_vigia()
            self._fase = "pausado" if self._pausada() else "listo"
        elif fase == "sonando":
            self._parar_vigia()
            if self._pausada():
                self._enviar("pausa", {"on": True})     # la página no se había enterado
                self._pausa_enviada = True
                self._fase = "pausado"
            else:
                self._fase = "sonando"
        elif fase == "pausado":
            self._fase = "pausado"
        elif fase == "saliendo":
            self._fase = "saliendo"
        elif fase == "fin":
            self._al_fin()
            return
        elif fase == "parado":
            self._terminar(enviar=False)
            return
        elif fase == "error":
            self._error_pagina(nbl.texto_limpio(datos.get("mensaje"), 200))
            return
        elif fase != "t":
            return
        self._emitir_estado()

    # ── Órdenes ──────────────────────────────────────────────────────────────────
    def reproducir(self, id_: Optional[str] = None, *, origen: str = "usuario") -> Tuple[bool, str]:
        """Pone un baile (sin id: sigue si estaba en pausa, o el último, o el primero). Con la
        asistente escondida, la saca."""
        if id_ is None or id_ == "":
            if self._actual is not None:
                self._sacar_si_escondida()
                if self._pausa_usuario:
                    self.pausa(False)
                    return True, "Sigo bailando."
                return True, f"Ya estoy bailando «{nbl.titulo_seguro(self._actual.titulo)}»."
            b = self.biblioteca.de_la_foto(self._ultimo_id) if self._ultimo_id else None
            if b is None or not b.jugable:
                nid = self.cola.siguiente(None, "siguiente", self._admite())
                b = self.biblioteca.de_la_foto(nid) if nid else None
            if b is None:
                self.ultimo_motivo = "sin_bailes"
                if not self.biblioteca.escaneada:
                    return False, AVISO_MIRANDO
                return False, "No tienes bailes todavía: mételos en la carpeta «bailes» o impórtalos."
            return self._reproducir(b, origen=origen, reiniciar=False)
        b = self.biblioteca.de_la_foto(id_)
        if b is None:
            self.ultimo_motivo = "no_encontrado"
            return False, AVISO_MIRANDO if not self.biblioteca.escaneada else "No encuentro ese baile."
        return self._reproducir(b, origen=origen, reiniciar=False)

    def reproducir_por_texto(self, texto: Any) -> Tuple[bool, str]:
        """Busca (título y autores, sin tildes) y pone el primero (favoritos antes)."""
        q = nbl.texto_limpio(texto, 80)
        if not q:
            return self.reproducir(None, origen="modelo")
        cands = [b for b in self.biblioteca.buscar_en_foto(q) if b.jugable]
        if not cands:
            self.ultimo_motivo = "no_encontrado"
            return False, f"No encontré «{nbl.titulo_seguro(q)}» en tus bailes."
        admite = self._admite()
        if admite is not None:
            cands = [b for b in cands if admite(b)] or cands
        nq = nbl.normalizar(q)
        cands.sort(key=lambda b: nbl.normalizar(b.titulo) != nq)     # estable: el título exacto antes
        return self._reproducir(cands[0], origen="modelo", reiniciar=False)

    def pausa(self, on: Optional[bool] = None) -> bool:
        """Pausa o sigue (sin argumento, alterna). False si no hay baile."""
        if self._actual is None:
            return False
        self._pausa_usuario = (not self._pausa_usuario) if on is None else bool(on)
        self._aplicar_pausa()
        self._emitir_estado()
        return True

    def parar(self) -> bool:
        """Para (la VRM vuelve al reposo) y reanuda lo que se cedió. True si bailaba."""
        if self._actual is None:
            return False
        self._terminar(enviar=True)
        return True

    def siguiente(self) -> Tuple[bool, str]:
        """El siguiente. A mitad de un baile con la asistente escondida, espera a que se la vea
        (no la saca); sin nada puesto es como ▶ (sí la saca)."""
        modo = "aleatorio" if self._al_terminar() == "aleatorio" else "siguiente"
        ref = self._actual.id if self._actual is not None else self._ultimo_id
        nid = self.cola.siguiente(ref or None, modo, self._admite())
        b = self.biblioteca.de_la_foto(nid) if nid else None
        if b is None:
            return False, "No hay más bailes."
        return self._reproducir(b, origen="usuario", reiniciar=True, sacar=self._actual is None)

    def anterior(self) -> Tuple[bool, str]:
        ref = self._actual.id if self._actual is not None else self._ultimo_id
        nid = self.cola.anterior(ref or None, self._admite())
        b = self.biblioteca.de_la_foto(nid) if nid else None
        if b is None:
            return False, "No hay más bailes."
        return self._reproducir(b, origen="usuario", reiniciar=True, sacar=self._actual is None)

    def volumen(self, v: float) -> None:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        if not math.isfinite(f):
            return
        f = max(0.0, min(1.0, f))
        self._cfg_set("volumen", round(f, 3))
        if self._actual is not None:
            if self._modo in ("vrm", "animado"):
                self._enviar("volumen", {"volumen": f})
            elif self._modo == "sprites" and self._cancion is not None:
                self._cancion.volumen(self._vol_efectivo())
        self._emitir_estado()

    def set_al_terminar(self, modo: str) -> bool:
        modo = str(modo or "")
        if modo not in nbl.AL_TERMINAR:
            return False
        self._cfg_set("al_terminar", modo)
        if self._actual is not None and self._modo in ("vrm", "animado"):
            self._enviar("bucle", {"bucle": modo == "repetir"})
        self._emitir_estado()
        return True

    def set_en_el_sitio(self, on: bool) -> None:
        self._cfg_set("en_el_sitio", bool(on))
        b = self._actual
        if b is not None and self._modo == "vrm" and not isinstance(b.meta.get("en_el_sitio"), bool):
            self._enviar("en_sitio", {"enSitio": bool(on)})
        self._emitir_estado()

    def pedir_vista(self) -> None:
        """Acción «bailes»: el panel de la biblioteca."""
        self.vista_pedida.emit("bailes")

    # ── Biblioteca ───────────────────────────────────────────────────────────────
    def lista(self, texto: str = "") -> List[Dict[str, Any]]:
        """Los bailes (filtrados por `texto`) como dicts para el panel y el modelo: de la FOTO,
        sin escanear ni esperar (va en el hilo de Qt; lo nuevo llega por `refrescar`)."""
        return [nbl.baile_a_dict(b) for b in self.biblioteca.buscar_en_foto(texto or "")]

    def refrescar(self) -> None:
        """Vuelve a mirar la carpeta (en un hilo) y emite `biblioteca_cambio`."""
        def trabajo():
            try:
                lista = [nbl.baile_a_dict(b) for b in self.biblioteca.escanear()]
            except Exception:
                _log.exception("mmd: no pude escanear los bailes")
                lista = []
            self._emitir_hilo(-1, "biblioteca", lista)
        self._lanzar(trabajo, "lune-bailes-escanear")

    def _emitir_biblioteca(self) -> None:
        try:
            lista = [nbl.baile_a_dict(b) for b in self.biblioteca.foto()]
        except Exception:
            _log.exception("mmd: no pude leer la biblioteca")
            lista = []
        self.biblioteca_cambio.emit(json.dumps(lista, ensure_ascii=False))

    def favorito(self, id_: str, on: bool) -> bool:
        try:
            self.biblioteca.favorito(id_, bool(on))
        except ValueError:
            return False
        self._emitir_biblioteca()
        return True

    def desactivar(self, id_: str, on: bool) -> bool:
        try:
            self.biblioteca.desactivar(id_, bool(on))
        except ValueError:
            return False
        self._emitir_biblioteca()
        return True

    def guardar_meta(self, id_: str, cambios: Dict[str, Any]) -> Tuple[bool, str]:
        """lune.json del baile (título, autores, offset, brazo, en el sitio, bpm)."""
        try:
            meta = self.biblioteca.guardar_meta(id_, cambios)
        except ValueError as e:
            return False, str(e)
        b = self._actual
        if b is not None and b.id == id_:
            self._actual = dataclasses.replace(b, meta=dict(meta),
                                               titulo=meta.get("titulo") or b.titulo)
            if self._modo in ("vrm", "animado"):
                self._enviar("offset", {"offsetMs": int(meta.get("offset_ms") or 0)})
            if self._modo == "vrm":
                self._enviar("en_sitio", {"enSitio": self._en_sitio(self._actual)})
            self._emitir_estado()
        self._emitir_biblioteca()
        return True, "Guardado."

    def quitar(self, id_: str) -> Tuple[bool, str]:
        """Mueve el baile a bailes/.quitados (si suena, primero lo para)."""
        if self._actual is not None and self._actual.id == id_:
            self.parar()
        try:
            ok, texto = self.biblioteca.quitar(id_)
        except Exception as e:                                   # noqa: BLE001
            ok, texto = False, f"No pude quitarlo: {e}"[:300]
        self._emitir_biblioteca()
        return ok, texto

    def abrir_carpeta(self) -> bool:
        """Abre bailes/ en el Explorador (la crea si no existe)."""
        try:
            self.biblioteca.asegurar_carpeta()
        except Exception:
            pass
        carpeta = Path(self.biblioteca.carpeta)
        try:
            if self._abrir is not None:
                self._abrir(carpeta)
                return True
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta))))
        except Exception:
            _log.exception("mmd: no pude abrir la carpeta de bailes")
            return False

    def importar_dialogo(self, parent: Any = None) -> None:
        """QFileDialog (movimiento y canción) → Biblioteca.importar en un hilo → `importado`.

        El diálogo es modal: mientras está abierto se puede «Salir» (bandeja) o cambiar de
        interfaz. Si al cerrarse ya no hay reproductor (detenido o borrado), no se importa."""
        try:
            if self._dialogo is not None:
                rutas = list(self._dialogo(parent) or [])
            else:
                rutas = dialogo_archivos(parent)
        except Exception:
            _log.exception("mmd: el diálogo de importar falló")
            return
        if not _vivo(self) or not self._iniciado:
            _log.info("mmd: el reproductor se cerró con el diálogo de importar abierto: no importo")
            return
        if rutas:
            self.importar(rutas)

    def importar(self, rutas: List[Any]) -> None:
        """Copia a la biblioteca en un hilo; el resultado sale por `importado`."""
        rutas = [str(r) for r in (rutas or [])][:64]
        self._importando = True
        self._emitir_estado()

        def trabajo():
            try:
                ok, texto, id_ = self.biblioteca.importar(rutas)
            except Exception as e:                               # noqa: BLE001
                _log.exception("mmd: importar falló")
                ok, texto, id_ = False, f"No pude importar: {e}"[:300], None
            try:
                lista = [nbl.baile_a_dict(b) for b in self.biblioteca.foto()]
            except Exception:
                lista = []
            self._emitir_hilo(-1, "importado", ({"ok": bool(ok), "texto": str(texto), "id": id_}, lista))
        self._lanzar(trabajo, "lune-bailes-importar")

    # ── Consultas ────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        b = self._actual
        modo_m = self._modo_de(self._asistente) if self._asistente is not None else ""
        return {
            "fase": self._fase,
            "id": b.id if b is not None else self._id_error,
            "titulo": nbl.texto_limpio(b.titulo) if b is not None else "",
            "autor": nbl.texto_limpio(b.meta.get("autor_cancion")) if b is not None else "",
            "autor_mmd": nbl.texto_limpio(b.meta.get("autor_mmd")) if b is not None else "",
            "t": round(self._t, 1) if b is not None else 0.0,
            "total": round(self._total, 1) if b is not None else 0.0,
            "modo": self._modo,
            "al_terminar": self._al_terminar(),
            "volumen": round(self._vol(), 3),
            "en_el_sitio": self._en_sitio_cfg(),
            "error": self._error,
            "analizando": self._analizando,
            "pausado": bool(b is not None and self._pausada()),
            "cedida": bool(b is not None and self._cedida),
            "pendiente": self._pendiente,
            "modo_asistente": modo_m,
            "sin_esqueleto": modo_m in ("animado", "sprites"),
            "importando": self._importando,
        }

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["mmd"] = self
        if self._en_ui is not None:
            base["en_ui"] = self._en_ui
        return base

    def herramientas(self) -> dict:
        """{"listar_bailes": fn(args, ctx)} (asistente_bailar y parar_baile son de ControlBaile,
        que ya mira ctx["mmd"])."""
        return {"listar_bailes": lambda args=None, ctx=None: nbl.herramienta_listar(args, self._ctx(ctx))}

    # ── Internos: empezar ────────────────────────────────────────────────────────
    def _admite(self) -> Optional[Callable[[nbl.Baile], bool]]:
        """Sin esqueleto (animada, sprites) solo sirven los que traen canción."""
        modo = self._modo_de(self._asistente) if self._asistente is not None else ""
        if modo in ("animado", "sprites"):
            return lambda b: b.audio is not None
        return None

    def _motivo_bloqueo(self) -> str:
        est = self._bus_actual()
        if est is None:
            return ""
        for a in em.actividades_activas(est):
            if a != "mmd" and em.PRIORIDAD[a] >= em.PRIORIDAD["mmd"]:
                return a
        return ""

    def _reproducir(self, b: nbl.Baile, *, origen: str, reiniciar: bool, sacar: bool = True) -> Tuple[bool, str]:
        """`sacar`: con la asistente escondida, sacarla (▶, el modelo); «siguiente» a mitad de un
        baile y el fin de la canción no la sacan: el baile espera a que se la vea."""
        titulo = nbl.titulo_seguro(b.titulo)
        if not b.jugable:
            self.ultimo_motivo = "problema"
            return False, f"«{titulo}» no se puede bailar: {b.problema or 'le falta el movimiento'}."
        if self._actual is not None and self._actual.id == b.id and not reiniciar \
                and self._fase not in ("error", "parado"):
            if sacar:
                self._sacar_si_escondida()
            return True, f"Ya estoy bailando «{titulo}»."
        if self._prioridad_mia:
            if self._cedida:
                motivo = self._motivo_bloqueo()
                self.ultimo_motivo = motivo
                return False, "Ahora no puedo bailar" + (f": {nb.motivo_legible(motivo)}." if motivo else ".")
        else:
            pr = self._prioridad()
            if pr is not None:
                r = pr.iniciar("mmd", BAILE_MMD)
                if not r:
                    self.ultimo_motivo = str(getattr(r, "motivo", "") or "")
                    self._emitir_estado()
                    motivo = nb.motivo_legible(self.ultimo_motivo)
                    return False, "Ahora no puedo bailar" + (f": {motivo}." if motivo else ".")
            self._prioridad_mia = True
        self.ultimo_motivo = ""
        _log.info("mmd: %s pone el baile %s", origen, b.id)
        self._empezar(b, sacar=sacar)
        if self._fase == "error":
            return False, self._error or f"No pude bailar «{titulo}»."
        texto = f"¡A bailar «{titulo}»!"
        if self._modo in ("animado", "sprites") or (self._pendiente and self._admite() is not None):
            texto += " En 2D mi figura no tiene esqueleto: bailo a mi manera."
        return True, texto

    def _empezar(self, b: nbl.Baile, *, sacar: bool = True) -> None:
        """Deja listo el estado para `b` y lo arranca (o espera a la asistente)."""
        self._gen += 1
        self._t_pulso.stop()
        self._parar_vigia()
        self._t_asistente.stop()
        if self._modo == "sprites":
            self._parar_sprites()
        self._actual = b
        self._ultimo_id = b.id
        self._modo = ""
        self._fase = "cargando"
        self._t = 0.0
        self._total = float(b.duracion or 0.0)
        self._error = ""
        self._id_error = ""
        self._analizando = False
        self._pausa_usuario = False
        self._pausa_enviada = False
        self._sprites_listo = False
        self._sprites_empezado = False
        self._oculta = False
        self._recien_sacada = False
        self._ultimo_seg = -1
        m = self._asistente
        if m is None or not _vivo(m) or getattr(m, "cerrado", False) is True:
            self._pendiente = True
            self._emitir_estado()
            self._sacar_asistente()
            if self._pendiente and self._actual is b:
                self._t_asistente.start(ESPERA_ASISTENTE_MS)
            return
        self._pendiente = False
        if sacar and not self._asistente_visible():
            # Escondida (no cerrada): se saca como la acción «asistente». Mientras, pendiente: si
            # en vez de enseñarla llega otra (set_asistente), arranca con esa.
            self._pendiente = True
            self._sacar_asistente()
            if not self._pendiente or self._actual is not b:
                return
            self._pendiente = False
            if self._asistente_visible():
                self._recien_sacada = True
            else:
                self._avisar(AVISO_ESCONDIDA)
        self._despertar()
        self._arrancar()

    def _arrancar(self) -> None:
        b = self._actual
        if b is None:
            return
        modo = self._modo_de(self._asistente)
        if not modo:
            self._fallar("Con esta figura no sé bailar.")
            return
        self._modo = modo
        self._fase = "cargando"
        self._oculta = modo == "sprites" and not self._asistente_visible()     # sonará al verla
        necesita_hilo = modo in ("animado", "sprites") or (b.audio is not None and b.audio_web is None)
        if modo in ("animado", "sprites") and b.audio is None:
            self._fallar("Este baile no trae canción y en 2D mi figura no tiene esqueleto: sin canción no "
                         "puedo bailarlo.")
            return
        if not necesita_hilo:
            self._cargar_en_pagina(b, None)
            return
        self._analizando = modo in ("animado", "sprites")
        self._emitir_estado()
        gen = self._gen
        self._lanzar(lambda: self._preparar(gen, b, modo), "lune-bailes-preparar")

    def _preparar(self, gen: int, b: nbl.Baile, modo: str) -> None:
        """En un hilo: pulso de la canción (D1) y conversión del audio si hace falta."""
        res: Dict[str, Any] = {"baile": b, "pulso": None, "error": ""}
        try:
            if modo in ("animado", "sprites"):
                res["pulso"] = self.biblioteca.analizar_pulso(b)
            if modo in ("vrm", "animado") and b.audio is not None and b.audio_web is None:
                ok, texto, ruta = self.biblioteca.convertir_audio(b)
                if ok and ruta is not None:
                    res["baile"] = dataclasses.replace(b, audio_web=Path(ruta))
                elif modo == "animado":
                    res["error"] = texto or "No pude convertir la canción."
                else:
                    _log.info("mmd: %s sin canción (%s)", b.id, texto)
        except Exception as e:                                   # noqa: BLE001
            _log.exception("mmd: no pude preparar el baile")
            res["error"] = f"No pude preparar el baile: {e}"[:300]
        self._emitir_hilo(gen, "preparado", res)

    def _preparado(self, res: Dict[str, Any]) -> None:
        if self._actual is None:
            return
        self._analizando = False
        if res.get("error"):
            self._fallar(res["error"])
            return
        b = res.get("baile") or self._actual
        self._actual = b
        if isinstance(res.get("pulso"), dict):
            p = res["pulso"]
            self._pulso = {"bpm": float(p.get("bpm") or nbl.BPM_DEFECTO), "fase0": float(p.get("fase0") or 0.0),
                           "confianza": float(p.get("confianza") or 0.0)}
        if self._modo == "sprites":
            gen = self._gen
            c = self._cancion_obj()
            c.cargar(b.audio, lambda ok, texto: self._emitir_hilo(gen, "cancion", (bool(ok), str(texto or ""))))
            self._emitir_estado()
            return
        self._cargar_en_pagina(b, self._pulso if self._modo == "animado" else None)

    def _cargar_en_pagina(self, b: nbl.Baile, pulso: Optional[Dict[str, float]]) -> None:
        payload = self._payload(b, pulso)
        if payload is None:
            self._fallar("Este baile no trae canción que pueda sonar aquí.")
            return
        self._pausa_enviada = False
        if not self._enviar("cargar", payload):
            self._fallar("Mi figura no aceptó el baile.")
            return
        if self._pausada():
            self._enviar("pausa", {"on": True})
            self._pausa_enviada = True
        # Recién sacada (o creada) su página puede estar recargando: más margen.
        self._armar_vigia(VIGIA_CARGA_MS if self._recien_sacada else VIGIA_PRIMERA_MS)
        self._recien_sacada = False
        self._emitir_estado()

    def _payload(self, b: nbl.Baile, pulso: Optional[Dict[str, float]]) -> Optional[Dict[str, Any]]:
        u = self.biblioteca.urls(b)
        meta = b.meta if isinstance(b.meta, dict) else {}
        comun = {
            "id": b.id,
            "offsetMs": int(meta.get("offset_ms") or 0),
            "volumen": round(self._vol(), 3),
            "bucle": self._al_terminar() == "repetir",
            "autoplay": True,
            "titulo": nbl.texto_limpio(b.titulo),
        }
        if pulso is not None:
            if not u["audio"]:
                return None
            return {**comun, "tipo": "audio", "audio": u["audio"],
                    "bpm": round(max(40.0, min(240.0, float(pulso.get("bpm") or nbl.BPM_DEFECTO))), 2),
                    "fase0": round(float(pulso.get("fase0") or 0.0) % 1.0, 4)}
        return {**comun, "tipo": b.tipo, "motion": list(u["motion"]), "cara": list(u["cara"]),
                "audio": u["audio"], "enSitio": self._en_sitio(b),
                "brazoGrados": round(float(meta.get("brazo_a_grados") or 35.0), 1)}

    # ── Internos: sprites (D1 en Python) ────────────────────────────────────────
    def _cancion_lista(self, ok: bool, texto: str) -> None:
        if self._actual is None or self._modo != "sprites":
            return
        if not ok:
            self._fallar(texto or "No pude cargar la canción.")
            return
        c = self._cancion_obj()
        try:
            dur = float(getattr(c, "duracion", 0.0) or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur > 0:
            self._total = dur
        self._sprites_listo = True
        if self._pausada():
            self._fase = "pausado"
            self._emitir_estado()
            return
        self._empezar_sprites()

    def _empezar_sprites(self) -> None:
        c = self._cancion_obj()
        if not c.reproducir(self._vol_efectivo()):
            self._fallar(getattr(c, "error", "") or "No pude poner la canción.")
            return
        self._sprites_empezado = True
        self._fase = "sonando"
        self._t = 0.0
        self._opciones = nb.opciones_pagina(self.config)
        self._asistente_bailar(True)
        self._t_pulso.start()
        self._tic_pulso()
        self._emitir_estado()

    def _parar_sprites(self, avisar_asistente: bool = True) -> None:
        """Fuera la canción y el pulso. `avisar_asistente` False: la asistente se cambió o se está
        borrando (set_asistente): no se le habla."""
        self._t_pulso.stop()
        if self._cancion is not None:
            try:
                self._cancion.liberar()
            except Exception:
                _log.debug("mmd: no pude soltar la canción", exc_info=True)
        if self._sprites_empezado and avisar_asistente:
            self._asistente_bailar(False)
        self._sprites_listo = False
        self._sprites_empezado = False

    def _tic_pulso(self) -> None:
        if self._actual is None or self._modo != "sprites" or not self._sprites_empezado or self._pausada():
            self._t_pulso.stop()                       # (en pausa o escondida: ni pulso ni fin)
            return
        c = self._cancion_obj()
        if c.terminado:
            self._al_fin()
            return
        pos = c.posicion()
        if pos is None:
            return
        self._t = min(float(pos), T_MAX)
        off = float(self._actual.meta.get("offset_ms") or 0) / 1000.0
        bpm = self._pulso["bpm"]
        fase = nbl.fase_en(self._t + off, bpm, self._pulso["fase0"])
        m = self._asistente
        f = getattr(m, "pulso", None) if _vivo(m) else None
        if callable(f):
            try:
                f(float(bpm), float(fase), ENERGIA_D1)
            except Exception:
                _log.debug("mmd: la asistente no aceptó el pulso", exc_info=True)
        seg = int(self._t)
        if seg != self._ultimo_seg:
            self._ultimo_seg = seg
            self._emitir_estado()

    # ── Internos: pausa, fin, error ──────────────────────────────────────────────
    def _aplicar_pausa(self) -> None:
        ef = self._pausada()
        if self._modo in ("vrm", "animado") and not self._pendiente:
            if ef != self._pausa_enviada:
                self._enviar("pausa", {"on": ef})
                self._pausa_enviada = ef
            if ef and self._fase in ("sonando", "listo"):
                self._fase = "pausado"
            elif not ef and self._fase == "pausado":
                self._fase = "sonando"
        elif self._modo == "sprites":
            c = self._cancion_obj()
            if ef:
                if self._sprites_empezado:
                    c.pausar(True)
                    self._asistente_bailar(False)
                self._t_pulso.stop()
                if self._fase in ("sonando", "listo"):
                    self._fase = "pausado"
            elif self._sprites_empezado:
                c.pausar(False)
                c.volumen(self._vol_efectivo())
                self._asistente_bailar(True)
                self._t_pulso.start()
                self._fase = "sonando"
                self._tic_pulso()
            elif self._sprites_listo:
                self._empezar_sprites()

    def _al_fin(self) -> None:
        """Acabó la canción (o el clip): según `al_terminar`."""
        b = self._actual
        if b is None:
            return
        modo = self._al_terminar()
        if modo == "repetir":
            if self._modo == "sprites":
                c = self._cancion_obj()
                if c.reproducir(self._vol_efectivo()):
                    self._t = 0.0
                    self._ultimo_seg = -1
                    self._emitir_estado()
                    return
            else:
                self._reproducir(b, origen="auto", reiniciar=True, sacar=False)
                return
        elif modo in ("siguiente", "aleatorio"):
            nid = self.cola.siguiente(b.id, modo, self._admite())
            nb_ = self.biblioteca.de_la_foto(nid) if nid else None
            if nb_ is not None:
                ok, _ = self._reproducir(nb_, origen="auto", reiniciar=True, sacar=False)
                if ok:
                    return
        self.parar()

    def _error_pagina(self, mensaje: str) -> None:
        if mensaje in ("recarga", "modelo"):
            _log.info("mmd: la página dejó el baile (%s)", mensaje)
            self._terminar(enviar=True)
            return
        titulo = nbl.titulo_seguro(self._actual.titulo) if self._actual is not None else ""
        self._fallar(f"No pude bailar «{titulo}»: {mensaje or 'algo falló en el escritorio'}")

    def _fallar(self, texto: str) -> None:
        texto = nbl.texto_limpio(texto, 300)
        self._avisar(texto)
        self._terminar(enviar=True, error=texto)

    def _vigia_vencido(self) -> None:
        if self._actual is None or self._fase != "cargando" or self._modo not in ("vrm", "animado"):
            self._vigia_ms = 0
            return
        if not self._asistente_visible():
            # Escondida no lee su cola de eventos: no cuenta. Vuelve a armarse entero al verla
            # (_on_visible); por si no llega ese aviso, se mira otra vez más tarde.
            self._t_vigia.start(max(1, self._vigia_ms or VIGIA_PRIMERA_MS))
            return
        self._vigia_ms = 0
        self._fallar("Mi figura no respondió al baile.")

    def _asistente_no_llego(self) -> None:
        if self._actual is not None and self._pendiente:
            self._fallar("No pude salir al escritorio para bailar.")

    def _armar_vigia(self, ms: int) -> None:
        """La página tiene `ms` para decir algo; con la asistente escondida no cuenta (se arma al
        verla: _on_visible)."""
        self._vigia_ms = int(ms)
        if self._asistente_visible():
            self._t_vigia.start(int(ms))
        else:
            self._t_vigia.stop()

    def _parar_vigia(self) -> None:
        self._vigia_ms = 0
        self._t_vigia.stop()

    def _terminar(self, *, enviar: bool, error: str = "") -> None:
        """Deja de bailar: la asistente al reposo, la canción fuera, la actividad suelta."""
        b = self._actual
        self._gen += 1
        for t in (self._t_pulso, self._t_vigia, self._t_asistente):
            t.stop()
        self._vigia_ms = 0
        if self._modo in ("vrm", "animado") and enviar and not self._pendiente:
            self._enviar("parar", None)
        if self._modo == "sprites":
            self._parar_sprites(avisar_asistente=enviar)
        elif self._cancion is not None:
            try:
                self._cancion.liberar()
            except Exception:
                pass
        self._actual = None
        self._modo = ""
        self._t = 0.0
        self._total = 0.0
        self._pendiente = False
        self._pausa_usuario = False
        self._cedida = False
        self._pausa_enviada = False
        self._analizando = False
        self._sprites_listo = False
        self._sprites_empezado = False
        self._oculta = False
        self._recien_sacada = False
        self._fase = "error" if error else "parado"
        self._error = error
        self._id_error = b.id if (error and b is not None) else ""
        self._soltar_prioridad()
        self._emitir_estado()

    def _soltar_prioridad(self) -> None:
        if not self._prioridad_mia:
            return
        self._prioridad_mia = False
        pr = self._prioridad()
        if pr is None:
            return
        try:
            pr.olvidar("mmd")                   # si estaba cedida, ya no hay que reanudarla
            pr.terminar("mmd")                  # y lo que cedió ella (sentada, baile) vuelve
        except Exception:
            _log.exception("mmd: no pude terminar la actividad")

    # ── Internos: asistente ────────────────────────────────────────────────────────
    @staticmethod
    def _modo_de(m: Any) -> str:
        if not _vivo(m):
            return ""                                  # (la que se está cerrando: nada que tocar)
        try:
            render = str(getattr(m, "render", "") or "")
            tiene_mmd = callable(getattr(m, "mmd", None))
            if render == "vrm" and tiene_mmd:
                return "vrm"
            if render == "animado" and tiene_mmd:
                return "animado"
            if callable(getattr(m, "bailar", None)):
                return "sprites"
        except RuntimeError:
            pass
        return ""

    def _asistente_visible(self) -> bool:
        """¿Se ve la asistente? (cerrada o borrada, no; una sin isVisible —los dobles— sí)."""
        m = self._asistente
        if not _vivo(m) or getattr(m, "cerrado", False) is True:
            return False
        f = getattr(m, "isVisible", None)
        if not callable(f):
            return True
        try:
            return bool(f())
        except Exception:
            return False

    def _sacar_si_escondida(self) -> None:
        """▶ con un baile puesto y la asistente escondida: se saca (como la acción «asistente»). Cedido
        (juego, alarma, pantalla grande…), no: la escondió o la tapa lo que manda ahora."""
        if self._asistente is None or self._pendiente or self._cedida or self._asistente_visible():
            return
        self._sacar_asistente()
        if not self._asistente_visible():
            self._avisar(AVISO_ESCONDIDA)

    def _enviar(self, orden: str, datos: Optional[Dict[str, Any]]) -> bool:
        m = self._asistente
        f = getattr(m, "mmd", None) if _vivo(m) else None
        if not callable(f):
            return False
        try:
            return f(orden, datos) is not False
        except Exception:
            _log.exception("mmd: la asistente no aceptó «%s»", orden)
            return False

    def _asistente_bailar(self, on: bool) -> None:
        m = self._asistente
        f = getattr(m, "bailar", None) if _vivo(m) else None
        if not callable(f):
            return
        try:
            if on:
                f(True, dict(self._opciones or nb.opciones_pagina(self.config)))
            else:
                f(False)
        except Exception:
            _log.debug("mmd: la asistente no pudo %s", "bailar" if on else "parar", exc_info=True)

    def _despertar(self) -> None:
        m = self._asistente
        f = getattr(m, "despertar", None) if _vivo(m) else None
        if callable(f):
            try:
                f()                                    # se lo han pedido: se despierta
            except Exception:
                pass

    def _sacar_asistente(self) -> None:
        desp = None
        obtener = getattr(self.escritorio, "obtener", None)
        if callable(obtener):
            try:
                desp = obtener("despachador")
            except Exception:
                desp = None
        try:
            if desp is not None and callable(getattr(desp, "tiene", None)) and desp.tiene("asistente"):
                desp.ejecutar("asistente")
                return
        except Exception:
            _log.exception("mmd: no pude sacar a la asistente con el despachador")
        self._llamar_anfitrion("alternar_asistente")

    def _on_bus(self, estado: Any = None, cambios: Any = None) -> None:
        """Del bus: `visible` (la asistente se esconde o vuelve) y `hablando` (la voz de Lune baja
        la canción en los sprites; la página ya lo hace sola)."""
        if not isinstance(cambios, dict):
            return
        if "visible" in cambios:
            self._on_visible()
        if "hablando" in cambios and self._modo == "sprites" and self._sprites_empezado \
                and self._cancion is not None:
            try:
                self._cancion.volumen(self._vol_efectivo())
            except Exception:
                pass

    def _on_visible(self) -> None:
        """La asistente se escondió (o se cerró) o volvió a verse, con un baile puesto.

        Sprites: escondidos no bailan → canción en pausa y sin pulso; al volver, sigue (si no
        la pausó la persona ni la cedió un juego). VRM/animada: se pausan solas en su página
        (ui/companion.py), pero oculta no lee su cola de eventos: el vigía se para y se arma
        de nuevo, entero, al verla."""
        if self._actual is None or self._pendiente:
            return
        vis = self._asistente_visible()
        if self._modo == "sprites":
            if self._oculta == vis:
                self._oculta = not vis
                self._aplicar_pausa()
                self._emitir_estado()
        elif self._modo in ("vrm", "animado") and self._vigia_ms:
            if vis:
                self._t_vigia.start(self._vigia_ms)
            else:
                self._t_vigia.stop()

    # ── Internos: hilos y señales ────────────────────────────────────────────────
    def _lanzar(self, fn: Callable[[], None], nombre: str) -> None:
        if self._hilo:
            threading.Thread(target=fn, name=nombre, daemon=True).start()
        else:
            fn()

    def _emitir_hilo(self, gen: int, clave: str, datos: Any) -> None:
        if not _vivo(self):
            return                                     # el reproductor ya no existe (salir, relevo)
        try:
            self._hecho_hilo.emit((gen, clave, datos))
        except (RuntimeError, AttributeError):
            pass                                       # se borró justo ahora

    def _on_hecho(self, obj: Any) -> None:
        try:
            gen, clave, datos = obj
        except (TypeError, ValueError):
            return
        if clave == "biblioteca":
            self.biblioteca_cambio.emit(json.dumps(datos, ensure_ascii=False))
            return
        if clave == "importado":
            res, lista = datos
            self._importando = False
            self.importado.emit(json.dumps(res, ensure_ascii=False))
            self.biblioteca_cambio.emit(json.dumps(lista, ensure_ascii=False))
            if not res.get("ok"):
                self._avisar(nbl.texto_limpio(res.get("texto"), 300))
            self._emitir_estado()
            return
        if gen != self._gen:
            return                                     # de un baile que ya no está
        if clave == "preparado":
            self._preparado(datos)
        elif clave == "cancion":
            ok, texto = datos
            self._cancion_lista(ok, texto)

    def _emitir_estado(self) -> None:
        txt = json.dumps(self.estado(), ensure_ascii=False, sort_keys=True)
        if txt != self._ultimo_estado:
            self._ultimo_estado = txt
            self.estado_cambio.emit(txt)


__all__ = ("ControlMMD", "FASES")
