"""
ui/cambio_interfaz.py — Cambiar de modo de interfaz en caliente, sin reiniciar.

Modos (config interfaz.modo): "web" (Completa, ui/web_shell.VentanaWeb),
"nativo" (Bajos recursos, main.LuneCDWindow) y "patata" (la terminal, patata.py).

`GestorInterfaz` lleva la ventana principal de la app (la que main() creó al
arrancar) y hace el relevo cuando pides otro modo en Ajustes:

  1. Guarda el modo nuevo en config (si algo falla, vuelve a poner el de antes).
  2. Construye la ventana nueva con la fábrica (inyectable) SIN sus servicios
     exclusivos (bandeja, atajos globales…): la vieja aún los tiene. Si la fábrica
     falla, se queda la vieja y se avisa.
  3. Le pasa el estado de la vieja (`estado_para_cambio`): geometría (posición,
     tamaño, maximizada, pantalla), proveedor, voz y la conversación en curso.
  4. Espera a que esté lista (la web, a que la página pinte; con un tope corto) y
     la enseña ENCIMA de la vieja con un fundido corto de opacidad.
  5. La vieja se cierra de verdad sin salir de la app (`cerrar_para_cambio`):
     suelta todo lo que la nueva vuelve a crear (IA en curso, aprobaciones, voz,
     mascota, bot de Telegram, hub, atajos, bandeja, temporizadores) y dice qué
     estaba en marcha.
  6. La nueva arranca sus servicios (`iniciar_servicios`) y relanza lo que estaba
     en marcha (mascota fuera, bot de Telegram). Nunca hay dos a la vez.

Patata: se abre la terminal (la fábrica no interviene: `lanzar_patata`) y, si se
abrió, la app Qt se cierra limpia (`salir_de_verdad` de la ventana y `salir`).

Contrato de una ventana (todo opcional salvo lo de Qt; duck typing, como
ui/escritorio.py):
    MODO_INTERFAZ = "web" | "nativo"
    cambio_interfaz_pedido  señal(str): la ventana pide otro modo (Ajustes)
    estado_para_cambio() -> dict      lo que la nueva debe heredar (ver ESTADO)
    aplicar_estado(dict)              antes de enseñarse: proveedor, voz, conversación…
    al_estar_lista(cb, tope_ms)       llama a cb() una vez, cuando ya se puede enseñar
    cerrar_para_cambio() -> dict|None suelta todo y se cierra SIN salir de la app;
                                      devuelve {"mascota_fuera": bool, "telegram": bool}
    iniciar_servicios(dict)           bandeja, atajos… y relanzar lo que estaba en marcha
    salir_de_verdad()                 cerrar la app entera (el «Salir» de la bandeja)
    aviso_cambio(texto)               un aviso no modal (si no, QMessageBox)
    cambio_fallido(modo, motivo)      el cambio no se hizo (p. ej. devolver el combo)

ESTADO (claves que entienden las dos ventanas):
    modo, geometria (capturar_geometria), proveedor ("ollama" | "openrouter" |
    "compat"), voz (bool), sesion (copia de la conversación de chats/, con su
    marca no_confiable por mensaje), mascota_fuera (bool), telegram (bool),
    juego_forzado (None | True | False: el modo juego puesto a mano en la bandeja).

Aquí también están los ayudantes que usan las dos ventanas para soltar sus
recursos (detener_hilo_ia, cerrar_mascota, detener_bot, quitar_bandeja…): así
la web y la nativa sueltan lo mismo de la misma manera.

Todo en el hilo de Qt. `pedir(modo)` difiere el cambio con QTimer.singleShot(0):
la página o el panel que lo pide termina su llamada antes de destruirse.

Espera anidada (revisión 4-5-6, RH3): «Probar conexión» o «Liberar memoria» esperan a su
hilo en un bucle de eventos anidado (web_bridge._esperar_en_hilo, `_esperando_hilo`).
Un relevo hecho DENTRO de ese bucle borraría la ventana y su puente con el slot aún en la
pila. Si la ventana está esperando así, el cambio (y el cierre de la vieja, si ya había
empezado) se aplaza hasta que salga de la espera (`en_espera_anidada`).
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import (QAbstractAnimation, QByteArray, QObject, QPropertyAnimation, QRect,
                          Qt, QTimer, pyqtSignal)

MODOS = ("web", "nativo", "patata")
_ALIAS = {
    "web": "web", "completa": "web", "completo": "web",
    "nativo": "nativo", "nativa": "nativo", "bajos": "nativo", "bajos_recursos": "nativo",
    "ligera": "nativo", "ligero": "nativo",
    "patata": "patata", "terminal": "patata",
}
NOMBRE_MODO = {"web": "completa", "nativo": "de bajos recursos", "patata": "de terminal (patata)"}

# Proveedor: id del backend (nativa, AIManager) ⇄ id de la página web.
PROVEEDOR_A_WEB = {"ollama": "local", "openrouter": "cloud", "compat": "compat"}
PROVEEDOR_DESDE_WEB = {v: k for k, v in PROVEEDOR_A_WEB.items()}

FUNDIDO_MS = 180          # fundido de entrada de la ventana nueva
TOPE_CARGA_MS = 2500      # la web se enseña al pintar la página o, como mucho, a los 2,5 s
_MARGEN_GUARDA_MS = 1500  # si una ventana nunca avisa de que está lista, el gestor no se queda colgado
SONDEO_ESPERA_MS = 100    # cada cuánto se mira si la ventana salió de su espera anidada
_TOPE_ESPERA_MS = 60000   # las esperas anidadas acaban solas (≤ 20 s); por si acaso, se sigue igual


def _log_info(msg: str) -> None:
    try:
        from nucleo.utils import log_info
        log_info(msg)
    except Exception:
        pass


def _log_error(msg: str) -> None:
    try:
        from nucleo.utils import log_error
        log_error(msg)
    except Exception:
        pass


def normalizar_modo(modo: Any) -> Optional[str]:
    """'web' | 'nativo' | 'patata' (con alias: completa, bajos, terminal…) o None."""
    return _ALIAS.get(str(modo or "").strip().lower().replace(" ", "_"))


def modo_de_ventana(ventana: Any) -> Optional[str]:
    return normalizar_modo(getattr(ventana, "MODO_INTERFAZ", None))


def en_espera_anidada(ventana: Any) -> bool:
    """¿La ventana (o su puente) está dentro del bucle anidado de _esperar_en_hilo
    (`_esperando_hilo` is True)? Entonces no se la puede relevar todavía."""
    if ventana is None:
        return False
    try:
        objetos = (ventana, getattr(ventana, "bridge", None))
        return any(o is not None and getattr(o, "_esperando_hilo", False) is True for o in objetos)
    except RuntimeError:                         # objeto de Qt ya borrado
        return False


# ── Geometría ────────────────────────────────────────────────────────────────────
def _rect(r) -> Optional[tuple]:
    try:
        if r is None or not r.isValid() or r.width() <= 0 or r.height() <= 0:
            return None
        return (int(r.x()), int(r.y()), int(r.width()), int(r.height()))
    except Exception:
        return None


def capturar_geometria(w: Any) -> Dict[str, Any]:
    """Posición, tamaño, estado (maximizada, pantalla completa) y pantalla de `w`.
    `qt` son los bytes de saveGeometry() (lo más fiable entre pantallas); `rect` es
    la geometría NORMAL (la de restaurar), para ventanas sin saveGeometry."""
    g: Dict[str, Any] = {}
    for clave, metodo in (("maximizada", "isMaximized"), ("pantalla_completa", "isFullScreen"),
                          ("minimizada", "isMinimized")):
        try:
            g[clave] = bool(getattr(w, metodo)())
        except Exception:
            g[clave] = False
    rect = None
    if g["maximizada"] or g["pantalla_completa"]:
        try:
            rect = _rect(w.normalGeometry())
        except Exception:
            rect = None
    if rect is None:
        try:
            rect = _rect(w.geometry())
        except Exception:
            rect = None
    if rect is not None:
        g["rect"] = rect
    try:
        g["qt"] = bytes(w.saveGeometry())
    except Exception:
        pass
    try:
        pantalla = w.screen()
        g["pantalla"] = pantalla.name() if pantalla is not None else ""
    except Exception:
        pass
    return g


def aplicar_geometria(w: Any, g: Optional[Dict[str, Any]]) -> None:
    """Deja `w` (aún sin enseñar) con la geometría NORMAL de la vieja (`rect`: la
    ventana está en el mismo escritorio, así que es exacta y cae en la misma
    pantalla); el estado (maximizada…) lo pone mostrar_segun_geometria. Sin `rect`,
    restoreGeometry con los bytes de saveGeometry."""
    if not g:
        return
    rect = g.get("rect")
    if rect:
        try:
            w.setGeometry(QRect(*rect))
            return
        except Exception:
            try:
                w.setGeometry(*rect)
                return
            except Exception:
                pass
    datos = g.get("qt")
    if datos and hasattr(w, "restoreGeometry"):
        try:
            w.restoreGeometry(QByteArray(bytes(datos)))
        except Exception:
            pass


def mostrar_segun_geometria(w: Any, g: Optional[Dict[str, Any]]) -> None:
    """Enseña `w` como estaba la vieja (maximizada, pantalla completa o normal; nunca
    minimizada: la pediste tú) y la trae delante."""
    g = g or {}
    try:
        if g.get("pantalla_completa") and hasattr(w, "showFullScreen"):
            w.showFullScreen()
        elif g.get("maximizada") and hasattr(w, "showMaximized"):
            w.showMaximized()
        else:
            w.show()
    except Exception:
        w.show()
    for metodo in ("raise_", "activateWindow"):
        try:
            getattr(w, metodo)()
        except Exception:
            pass


# ── Soltar recursos (lo usan la web y la nativa) ─────────────────────────────────
_retenidos: set = set()


def hilo_vivo(hilo: Any) -> bool:
    if hilo is None:
        return False
    try:
        return bool(hilo.isRunning())
    except (RuntimeError, AttributeError):
        return False


def retener_hasta_terminar(hilo: Any) -> bool:
    """Un QThread que sigue corriendo no puede destruirse con la ventana (Qt aborta
    el proceso): se suelta de su padre y se guarda aquí hasta que acabe. True si
    quedó retenido."""
    if not hilo_vivo(hilo):
        return False
    try:
        if hasattr(hilo, "setParent") and hilo.parent() is not None:
            hilo.setParent(None)
    except Exception:
        pass
    _retenidos.add(hilo)
    fin = getattr(hilo, "finished", None)
    if fin is not None and hasattr(fin, "connect"):
        try:
            fin.connect(lambda h=hilo: _retenidos.discard(h))
        except Exception:
            pass
    return True


def retenidos() -> int:
    """Cuántos hilos de ventanas ya cerradas siguen terminando (diagnóstico/tests)."""
    for h in list(_retenidos):
        if not hilo_vivo(h):
            _retenidos.discard(h)
    return len(_retenidos)


def _desconectar(obj: Any, *senales: str) -> None:
    for nombre in senales:
        s = getattr(obj, nombre, None)
        if s is None or not hasattr(s, "disconnect"):
            continue
        try:
            s.disconnect()
        except (TypeError, RuntimeError):
            pass


def detener_hilo_ia(worker: Any, proveedores: Any = None, espera_ms: int = 0) -> bool:
    """Corta el AIWorker en curso sin ejecutar nada de lo que traiga: pide el corte a
    los proveedores (cancel_flag), desconecta sus señales (ni se pinta la respuesta
    ni se ejecutan sus <|CALL|>) y lo retiene hasta que acabe. Con `espera_ms` > 0
    (salir de la app) espera como mucho eso. True si estaba corriendo."""
    vivo = hilo_vivo(worker)
    provs = proveedores.values() if isinstance(proveedores, dict) else (proveedores or ())
    if vivo:
        for p in list(provs):
            try:
                p.cancel_flag = True
            except Exception:
                pass
    if worker is None:
        return False
    _desconectar(worker, "token_received", "response_ready", "error_occurred")
    if vivo and espera_ms > 0:
        try:
            worker.wait(int(espera_ms))
        except Exception:
            pass
    retener_hasta_terminar(worker)
    return vivo


def soltar_hilos(*hilos: Any) -> None:
    """Hilos auxiliares (transcribir, sondeos, git…): sus resultados ya no le
    importan a nadie; se desconectan y se retienen si aún corren."""
    for h in hilos:
        if h is None:
            continue
        _desconectar(h, "listo", "fallo", "error", "progreso", "terminado", "transcrito", "estado")
        retener_hasta_terminar(h)


def cerrar_mascota(ov: Any) -> bool:
    """Cierra la mascota flotante (su closeEvent guarda la posición y quita su icono
    de la bandeja) y la borra. True si estaba fuera (a la vista)."""
    if ov is None:
        return False
    fuera = False
    try:
        fuera = (not getattr(ov, "cerrado", False)) and bool(ov.isVisible())
    except (RuntimeError, AttributeError):
        fuera = False
    _desconectar(ov, "visibilidad", "recrear")
    for metodo in ("close", "deleteLater"):
        try:
            getattr(ov, metodo)()
        except (RuntimeError, AttributeError):
            pass
    return fuera


def detener_bot(tg: Any, espera_ms: int = 3000) -> bool:
    """Para el bot de Telegram (el proceso hijo y su hilo; stop() cierra su stdin y
    el bot lanzado por Lune se cierra solo). Sus señales se desconectan antes:
    nadie las escucha ya (tampoco orden_recibida). True si estaba corriendo."""
    if tg is None:
        return False
    vivo = hilo_vivo(tg)
    _desconectar(tg, "log_signal", "stopped", "orden_recibida")
    if vivo:
        for metodo, args in (("stop", ()), ("requestInterruption", ()), ("wait", (int(espera_ms),))):
            try:
                getattr(tg, metodo)(*args)
            except Exception:
                pass
    retener_hasta_terminar(tg)
    return vivo


def ordenes_cortadas(turno: Any, worker_vivo: bool, pendientes: Any, ultima_orden: Any) -> list:
    """Ids de las órdenes de Telegram que se quedarían sin respuesta al cerrar la
    ventana: la que se está respondiendo (turno con «remoto» y la IA corriendo) y la
    última orden si tiene una aprobación pendiente (solo hay una orden a la vez:
    mientras una espera, las demás reciben «ocupada»)."""
    ids = []
    remoto = (turno or {}).get("remoto") if isinstance(turno, dict) else None
    if worker_vivo and remoto:
        ids.append(str(remoto))
    try:
        hay_pendiente = any(isinstance(p, dict) and p.get("remoto") for p in (pendientes or []))
    except Exception:
        hay_pendiente = False
    if hay_pendiente and ultima_orden and str(ultima_orden) not in ids:
        ids.append(str(ultima_orden))
    return ids


def desmontar_servicios_c4(*duenios: Any) -> None:
    """Gancho del corte 4 (bandeja única, atajos, detector de juego, radial): si un
    dueño tiene `_servicios_c4` (lo crea montar_escritorio), se llama a su
    desmontar() y se suelta. Tolerante: sin él, o si falla, no pasa nada."""
    for d in duenios:
        s = getattr(d, "_servicios_c4", None)
        if s is None:
            continue
        fn = getattr(s, "desmontar", None)
        if callable(fn):
            try:
                fn()
            except Exception as e:
                _log_error(f"[interfaz] desmontar servicios del corte 4: {e}")
        try:
            setattr(d, "_servicios_c4", None)
        except Exception:
            pass


def quitar_bandeja(tray: Any) -> None:
    """Quita el icono de la bandeja YA (hide) y lo borra (con su menú)."""
    if tray is None:
        return
    menu = None
    try:
        menu = tray.contextMenu()
    except Exception:
        menu = None
    for metodo in ("hide", "deleteLater"):
        try:
            getattr(tray, metodo)()
        except (RuntimeError, AttributeError):
            pass
    if menu is not None:
        try:
            menu.deleteLater()
        except (RuntimeError, AttributeError):
            pass


def parar_temporizadores(*timers: Any) -> None:
    for t in timers:
        if isinstance(t, (list, tuple)):
            parar_temporizadores(*t)
            continue
        if t is None:
            continue
        try:
            t.stop()
        except (RuntimeError, AttributeError):
            pass


def callar_voz(voice: Any) -> None:
    """Corta lo que suene y suelta los avisos de la voz (llegan del hilo de audio a
    una ventana que se va)."""
    if voice is None:
        return
    try:
        voice.cancelar()
    except Exception:
        pass
    for attr in ("al_hablar", "on_error"):
        try:
            setattr(voice, attr, None)
        except Exception:
            pass


# ── Conversación en curso ────────────────────────────────────────────────────────
def instantanea_sesion(chats: Any) -> Optional[dict]:
    """Copia de la conversación en curso de un GestorConversaciones (con la marca
    no_confiable de cada mensaje). None si no hay o está vacía."""
    if chats is None:
        return None
    fn = getattr(chats, "sesion_actual", None)
    try:
        s = fn() if callable(fn) else getattr(chats, "_sesion", None)
    except Exception:
        s = None
    if not isinstance(s, dict) or not s.get("mensajes"):
        return None
    return copy.deepcopy(s)


def retomar_sesion(chats: Any, sesion: Optional[dict]) -> bool:
    """El GestorConversaciones de la ventana nueva sigue la conversación `sesion`
    (misma id: los turnos nuevos van al mismo archivo de chats/). True si la tomó."""
    if chats is None or not isinstance(sesion, dict) or not sesion.get("mensajes"):
        return False
    fn = getattr(chats, "retomar", None)
    if callable(fn):
        try:
            return bool(fn(copy.deepcopy(sesion)))
        except Exception:
            return False
    try:
        chats._sesion = copy.deepcopy(sesion)       # GestorConversaciones sin retomar()
        return True
    except Exception:
        return False


# ── El gestor ────────────────────────────────────────────────────────────────────
def _animar_por_defecto(ventana: Any, ms: int, al_terminar: Callable[[], None]):
    """Fundido de entrada (windowOpacity 0 → 1). Sin QWidget o con ms <= 0, directo."""
    from PyQt6.QtWidgets import QWidget
    if ms <= 0 or not isinstance(ventana, QWidget):
        al_terminar()
        return None
    anim = QPropertyAnimation(ventana, b"windowOpacity", ventana)
    anim.setDuration(int(ms))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.finished.connect(al_terminar)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def _guardar_modo_por_defecto(modo: str) -> None:
    from nucleo.config import Config
    Config().set("interfaz", "modo", modo)


def _salir_por_defecto() -> None:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.quit()


def _avisar_por_defecto(ventana: Any, texto: str) -> None:
    fn = getattr(ventana, "aviso_cambio", None)
    if callable(fn):
        try:
            fn(texto)
            return
        except Exception:
            pass
    try:
        from PyQt6.QtWidgets import QMessageBox, QWidget
        QMessageBox.warning(ventana if isinstance(ventana, QWidget) else None, "Modo de interfaz", texto)
    except Exception:
        _log_error(f"[interfaz] {texto}")


class GestorInterfaz(QObject):
    """La ventana principal de la app y el relevo entre modos (ver la cabecera)."""

    cambio_hecho = pyqtSignal(str)          # modo nuevo (ya se ve la ventana nueva)
    cambio_fallido = pyqtSignal(str, str)   # (modo pedido, motivo): se quedó la vieja

    def __init__(self, fabrica: Callable[[str], Any], *,
                 guardar_modo: Optional[Callable[[str], None]] = None,
                 lanzar_patata: Optional[Callable[[], bool]] = None,
                 salir: Optional[Callable[[], None]] = None,
                 avisar: Optional[Callable[[Any, str], None]] = None,
                 animar: Optional[Callable[[Any, int, Callable[[], None]], Any]] = None,
                 fundido_ms: int = FUNDIDO_MS, tope_carga_ms: int = TOPE_CARGA_MS,
                 parent: Optional[QObject] = None):
        """
        fabrica(modo)     construye la ventana de "web" o "nativo" SIN arrancar sus
                          servicios exclusivos (p. ej. VentanaWeb(diferir_servicios=True));
                          si lanza o devuelve None, el cambio no se hace.
        guardar_modo(m)   escribe config interfaz.modo (por defecto, Config().set).
        lanzar_patata()   abre patata.py en una consola nueva; True si pudo.
        salir()           cierra la app Qt (por defecto QApplication.quit).
        avisar(v, texto)  aviso al usuario sobre la ventana v (por defecto aviso_cambio
                          de la ventana o un QMessageBox).
        animar(v, ms, fin) el fundido (por defecto QPropertyAnimation de windowOpacity).
        """
        super().__init__(parent)
        self._fabrica = fabrica
        self._guardar_modo = guardar_modo or _guardar_modo_por_defecto
        self._lanzar_patata = lanzar_patata
        self._salir = salir or _salir_por_defecto
        self._avisar = avisar or _avisar_por_defecto
        self._animar = animar or _animar_por_defecto
        self.fundido_ms = max(0, int(fundido_ms or 0))
        self.tope_carga_ms = max(0, int(tope_carga_ms or 0))
        self._ventana = None
        self._modo: Optional[str] = None
        self._cambiando = False
        self._pendiente: Optional[str] = None
        self._relevo_id = 0                  # cada cambio tiene el suyo: el relevo se hace una vez
        self._guarda: Optional[QTimer] = None
        self._espera: Optional[QTimer] = None    # aplazado hasta que la ventana salga de su espera
        self._anim = None
        self._cursor = False
        self._servidor = None

    # ── Estado ────────────────────────────────────────────────────────────────
    @property
    def ventana(self):
        return self._ventana

    @property
    def modo(self) -> Optional[str]:
        return self._modo

    @property
    def cambiando(self) -> bool:
        return self._cambiando

    def adoptar(self, ventana: Any, modo: Optional[str] = None) -> None:
        """La ventana que creó main() al arrancar (ya con sus servicios)."""
        self._ventana = ventana
        self._modo = normalizar_modo(modo) or modo_de_ventana(ventana)
        self._enganchar(ventana)

    def _enganchar(self, ventana: Any) -> None:
        senal = getattr(ventana, "cambio_interfaz_pedido", None)
        if senal is not None and hasattr(senal, "connect"):
            try:
                senal.connect(self.pedir)
            except (TypeError, RuntimeError):
                pass

    def _desenganchar(self, ventana: Any) -> None:
        senal = getattr(ventana, "cambio_interfaz_pedido", None)
        if senal is not None and hasattr(senal, "disconnect"):
            try:
                senal.disconnect(self.pedir)
            except (TypeError, RuntimeError):
                pass

    # ── Instancia única: abrir Lune otra vez → traer al frente la actual ──────
    def conectar_servidor(self, servidor: Any) -> None:
        """QLocalServer de la instancia única: cada conexión trae al frente la
        ventana ACTUAL (también después de un cambio de modo)."""
        if servidor is None or servidor is self._servidor:
            return
        self._servidor = servidor
        try:
            servidor.newConnection.connect(self.traer_al_frente)
        except (AttributeError, TypeError, RuntimeError):
            pass

    def traer_al_frente(self) -> None:
        srv = self._servidor
        if srv is not None:
            try:
                while srv.hasPendingConnections():
                    s = srv.nextPendingConnection()
                    if s is None:
                        break
                    s.deleteLater()
            except Exception:
                pass
        w = self._ventana
        if w is None:
            return
        try:
            estado = w.windowState()
            if estado & Qt.WindowState.WindowMinimized:
                w.setWindowState((estado & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        except Exception:
            pass
        for metodo in ("show", "raise_", "activateWindow"):
            try:
                getattr(w, metodo)()
            except Exception:
                pass

    # ── Pedir un cambio ───────────────────────────────────────────────────────
    def pedir(self, modo: Any) -> bool:
        """Desde un slot (la página, el panel de Ajustes): valida y hace el cambio en
        la siguiente vuelta del bucle de Qt (QTimer.singleShot(0)), cuando quien lo
        pidió ya terminó su llamada. False si se ignora (modo inválido, el actual o
        con otro cambio en marcha)."""
        m = normalizar_modo(modo)
        if not self._aceptable(m):
            return False
        self._pendiente = m
        QTimer.singleShot(0, lambda m=m: self._pedido(m))
        return True

    def _pedido(self, modo: str) -> None:
        if self._pendiente != modo:
            return
        self._pendiente = None
        self.cambiar(modo)

    def _aceptable(self, m: Optional[str]) -> bool:
        if m is None:
            _log_error("[interfaz] modo desconocido: se ignora")
            return False
        if self._cambiando or self._pendiente is not None:
            _log_info(f"[interfaz] ya hay un cambio en marcha: ignoro «{m}»")
            return False
        if m == self._modo:
            return False                        # el modo actual no se vuelve a «cambiar»
        return True

    def cambiar(self, modo: Any) -> bool:
        """Hace el cambio (ver la cabecera). Devuelve True si empezó (la web termina
        al pintar su página); False si se ignoró o falló (y se quedó la vieja)."""
        m = normalizar_modo(modo)
        if self._pendiente is not None and self._pendiente == m:
            self._pendiente = None
        if not self._aceptable(m):
            return False
        if en_espera_anidada(self._ventana):
            # La ventana espera a un hilo en un bucle anidado («Probar conexión»…): el
            # relevo la borraría con ese slot en la pila. Se hace cuando salga (RH3).
            _log_info(f"[interfaz] la ventana está esperando a una prueba: «{m}» al terminar")
            self._pendiente = m
            self._aplazar(self._ventana, lambda m=m: self._pedido(m))
            return True
        if m == "patata":
            return self._a_patata()
        vieja = self._ventana
        anterior = self._modo
        self._cambiando = True
        self._poner_cursor()
        _log_info(f"[interfaz] cambio {anterior or '?'} → {m}")
        estado = self._estado_de(vieja)
        self._guardar(m)                        # la ventana nueva lee config al construirse
        try:
            nueva = self._fabrica(m)
            if nueva is None:
                raise RuntimeError("no se creó la ventana")
        except Exception as e:
            self._fallo(vieja, anterior, m, f"No pude abrir la interfaz {NOMBRE_MODO.get(m, m)}: {e}")
            return False
        try:
            aplicar = getattr(nueva, "aplicar_estado", None)
            if callable(aplicar):
                aplicar(dict(estado))
            aplicar_geometria(nueva, estado.get("geometria"))
        except Exception as e:
            self._descartar(nueva)
            self._fallo(vieja, anterior, m, f"No pude preparar la interfaz {NOMBRE_MODO.get(m, m)}: {e}")
            return False
        self._habilitar(vieja, False)           # mientras carga la nueva, la vieja no admite nada
        self._relevo_id += 1
        rid = self._relevo_id

        def lista(r=rid):
            self._relevo(r, vieja, nueva, m, estado)

        esperar = getattr(nueva, "al_estar_lista", None)
        if callable(esperar):
            self._armar_guarda(lista)
            try:
                esperar(lista, self.tope_carga_ms)
            except Exception as e:
                _log_error(f"[interfaz] al_estar_lista: {e}")
                lista()
        else:
            lista()
        return True

    # ── Pasos ─────────────────────────────────────────────────────────────────
    def _estado_de(self, vieja: Any) -> Dict[str, Any]:
        estado: Dict[str, Any] = {}
        fn = getattr(vieja, "estado_para_cambio", None)
        if callable(fn):
            try:
                estado.update(fn() or {})
            except Exception as e:
                _log_error(f"[interfaz] estado_para_cambio: {e}")
        if vieja is not None and "geometria" not in estado:
            estado["geometria"] = capturar_geometria(vieja)
        estado.setdefault("modo", self._modo)
        return estado

    def _armar_guarda(self, lista: Callable[[], None]) -> None:
        self._parar_guarda()
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(lista)
        t.start(self.tope_carga_ms + _MARGEN_GUARDA_MS)
        self._guarda = t

    def _parar_guarda(self) -> None:
        t, self._guarda = self._guarda, None
        if t is not None:
            try:
                t.stop(); t.deleteLater()
            except RuntimeError:
                pass

    def _aplazar(self, ventana: Any, fn: Callable[[], None]) -> None:
        """fn() cuando `ventana` salga de su espera anidada (sondeo cada SONDEO_ESPERA_MS;
        el sondeo que la ve libre ya corre fuera de ese bucle: `_esperando_hilo` baja al
        volver de él, antes de que el slot termine)."""
        self._parar_espera()
        t = QTimer(self)
        t.setInterval(SONDEO_ESPERA_MS)
        vueltas = [0]
        tope = max(1, _TOPE_ESPERA_MS // SONDEO_ESPERA_MS)

        def tic(t=t):
            vueltas[0] += 1
            if en_espera_anidada(ventana) and vueltas[0] < tope:
                return
            if self._espera is t:
                self._parar_espera()
            fn()

        t.timeout.connect(tic)
        t.start()
        self._espera = t

    def _parar_espera(self) -> None:
        t, self._espera = self._espera, None
        if t is not None:
            try:
                t.stop(); t.deleteLater()
            except RuntimeError:
                pass

    def _relevo(self, rid: int, vieja: Any, nueva: Any, modo: str, estado: Dict[str, Any]) -> None:
        """La nueva ya se puede enseñar: encima de la vieja, con fundido."""
        if rid != self._relevo_id or not self._cambiando:
            return                                   # ya se hizo (o el cambio se abandonó)
        self._relevo_id += 1
        self._parar_guarda()
        try:
            if self.fundido_ms > 0 and hasattr(nueva, "setWindowOpacity"):
                nueva.setWindowOpacity(0.0)
            mostrar_segun_geometria(nueva, estado.get("geometria"))
        except Exception as e:
            self._descartar(nueva)
            self._fallo(vieja, self._modo, modo, f"No pude enseñar la interfaz {NOMBRE_MODO.get(modo, modo)}: {e}")
            return
        # Desde aquí la actual es la nueva (el servidor de instancia ya la trae al frente).
        self._desenganchar(vieja)
        self._ventana, self._modo = nueva, modo
        self._enganchar(nueva)
        fin = lambda: self._rematar(vieja, nueva, modo, estado)   # noqa: E731
        try:
            self._anim = self._animar(nueva, self.fundido_ms, fin)
        except Exception as e:
            _log_error(f"[interfaz] fundido: {e}")
            fin()

    def _rematar(self, vieja: Any, nueva: Any, modo: str, estado: Dict[str, Any]) -> None:
        """Tras el fundido: la vieja suelta todo y se va; la nueva arranca sus servicios."""
        if not self._cambiando:
            return
        if en_espera_anidada(vieja):
            # Empezó a esperar mientras cargaba la nueva: se cierra al salir de la espera.
            self._aplazar(vieja, lambda: self._rematar(vieja, nueva, modo, estado))
            return
        self._anim = None
        try:
            if hasattr(nueva, "setWindowOpacity"):
                nueva.setWindowOpacity(1.0)
        except Exception:
            pass
        en_marcha: Dict[str, Any] = {}
        if vieja is not None:
            fn = getattr(vieja, "cerrar_para_cambio", None)
            try:
                if callable(fn):
                    en_marcha = fn() or {}
                else:
                    for metodo in ("hide", "close"):
                        getattr(vieja, metodo, lambda: None)()
            except Exception as e:
                _log_error(f"[interfaz] cerrar_para_cambio: {e}")
            try:
                vieja.deleteLater()
            except (RuntimeError, AttributeError):
                pass
        servicios = dict(estado)
        servicios.update({k: v for k, v in (en_marcha or {}).items() if v is not None})
        fn = getattr(nueva, "iniciar_servicios", None)
        if callable(fn):
            try:
                fn(servicios)
            except Exception as e:
                _log_error(f"[interfaz] iniciar_servicios: {e}")
                self._avisar(nueva, f"La interfaz cambió, pero algo no arrancó: {e}")
        self._cambiando = False
        self._quitar_cursor()
        _log_info(f"[interfaz] ahora en modo {modo}")
        self.cambio_hecho.emit(modo)

    def _a_patata(self) -> bool:
        """Abre la terminal y, si se abrió, cierra la app Qt limpia."""
        vieja, anterior = self._ventana, self._modo
        self._cambiando = True
        ok, motivo = False, ""
        if self._lanzar_patata is None:
            motivo = "no sé abrir la terminal desde aquí"
        else:
            try:
                ok = bool(self._lanzar_patata())
            except Exception as e:
                motivo = str(e)
        if not ok:
            self._fallo(vieja, anterior, "patata",
                        "No pude abrir Lune en la terminal" + (f": {motivo}" if motivo else ".")
                        + " Sigo aquí.")
            return False
        self._guardar("patata")
        self._desenganchar(vieja)
        self._ventana, self._modo = None, "patata"
        try:
            if vieja is not None:
                fn = getattr(vieja, "salir_de_verdad", None)
                if callable(fn):
                    fn()
                else:
                    cerrar = getattr(vieja, "cerrar_para_cambio", None)
                    if callable(cerrar):
                        cerrar()
        except Exception as e:
            _log_error(f"[interfaz] cerrar para patata: {e}")
        finally:
            self._cambiando = False
            self.cambio_hecho.emit("patata")
            self._salir()
        return True

    def _fallo(self, vieja: Any, anterior: Optional[str], modo: str, motivo: str) -> None:
        """Se queda la vieja: config vuelve a su modo, se reactiva y se avisa."""
        _log_error(f"[interfaz] {motivo}")
        self._parar_guarda()
        self._relevo_id += 1
        if anterior:
            self._guardar(anterior)
        self._habilitar(vieja, True)
        self._cambiando = False
        self._quitar_cursor()
        fn = getattr(vieja, "cambio_fallido", None)
        if callable(fn):
            try:
                fn(modo, motivo)
            except Exception:
                pass
        try:
            self._avisar(vieja, motivo)
        except Exception:
            pass
        self.cambio_fallido.emit(modo, motivo)

    # ── Detalles ──────────────────────────────────────────────────────────────
    def _guardar(self, modo: str) -> None:
        try:
            self._guardar_modo(modo)
        except Exception as e:
            _log_error(f"[interfaz] no pude guardar interfaz.modo={modo}: {e}")

    @staticmethod
    def _habilitar(ventana: Any, si: bool) -> None:
        if ventana is None or not hasattr(ventana, "setEnabled"):
            return
        try:
            ventana.setEnabled(bool(si))
        except RuntimeError:
            pass

    @staticmethod
    def _descartar(ventana: Any) -> None:
        """Una ventana nueva que no llegó a enseñarse (no arrancó servicios)."""
        cerrar = getattr(ventana, "cerrar_para_cambio", None)
        for fn in ((cerrar,) if callable(cerrar) else ()) + (getattr(ventana, "deleteLater", None),):
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    def _poner_cursor(self) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None and not self._cursor:
                QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
                self._cursor = True
        except Exception:
            pass

    def _quitar_cursor(self) -> None:
        if not self._cursor:
            return
        self._cursor = False
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()
        except Exception:
            pass
