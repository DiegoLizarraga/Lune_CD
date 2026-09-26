"""
ui/montaje_escritorio.py — Monta los servicios de escritorio del corte 4 sobre
ServiciosEscritorio: Despachador, Tema, Atajos, Juego, Radial y Bandeja.

Web (ui/web_shell.py + web_bridge) y nativa (main.LuneCDWindow) solo aportan un
«anfitrión» (ui/anfitrion_web.AnfitrionWeb, ui/anfitrion_nativo.AnfitrionNativo)
y llaman una vez:

    servicios = montar_escritorio(bridge.escritorio, AnfitrionWeb(bridge, ventana),
                                  config, voice=bridge.voice, icono=icono)
    ...
    servicios.desmontar()        # cambio de interfaz en caliente o salir

Qué hace, en este orden:
 1. crea el Despachador y le registra los handlers de todas las acciones que
    este anfitrión sabe hacer (nucleo/acciones_ui.ACCIONES);
 2. crea ControlTema (ui/tema_qt, agente C), GestorAtajosQt, ControlModoJuego
    (ui/modo_juego_qt, agente A), ControlMenuRadial y BandejaLune — Tema y Juego
    se importan en diferido y si faltan o fallan el resto sigue (queda None);
 3. conecta: atajos.accion → despachador.ejecutar; juego.cambio →
    atajos.set_pausa, anfitrión.set_aburrimiento, cerrar el radial y el tooltip;
    tema.cambio → QSS de la bandeja y colores del radial; estado_cambio → tooltip;
 4. los registra en ServiciosEscritorio (despachador, tema, atajos, juego,
    radial, bandeja): arrancan ya si el escritorio estaba iniciado y reciben la
    mascota con set_mascota.

Todas las piezas son inyectables con `fabricas` (tests y la integración):
    despachador()                         → Despachador
    tema(config, parent)                  → ControlTema
    atajos(config, disponible=, parent=)  → GestorAtajosQt   · gestor_atajos: GestorAtajos falso
    juego(escritorio, config, voice=, parent=) → ControlModoJuego
    radial(desp, estado, config, contexto, colores=, sonar=, parent=) → ControlMenuRadial
    bandeja(desp, estado, contexto, config, icono=, parent=) → BandejaLune · tray: fábrica de QSystemTrayIcon
    autoinicio  (objeto con activo() y establecer(bool))  · recortar() → (MB antes, MB después)
    modelos_vrm() → lista de .vrm · sonar(nombre) · mezclador() · traer_al_frente(hwnd)
    ocio        dict de fábricas de ui/montaje_ocio.montar_ocio (grande, alarmas, baile,
                en_ui) · False = sin alarmas, pantalla grande ni baile

Cortes 5/6: al final monta `ServiciosCorte4.ocio` (ui/montaje_ocio.montar_ocio:
alarmas, pantalla grande y salvapantallas, baile), que se apunta en `_deshacer`.
"""
from __future__ import annotations

import gc
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from PyQt6.QtCore import QObject, pyqtSignal

from nucleo import acciones_ui
from nucleo.acciones_ui import Contexto, Despachador

_log = logging.getLogger("lune.montaje")

RAIZ = Path(__file__).resolve().parent.parent
DIR_SFX = RAIZ / "ui_web" / "assets" / "sfx"
ORDEN = ("despachador", "tema", "atajos", "juego", "radial", "bandeja")
# Actividades de la tabla de prioridades (nucleo/estado_mascota.PRIORIDAD) que hace
# físicamente cada controlador (recibe ceder/reanudar de ellas).
ACTIVIDADES = {"juego": ("juego",)}
EXPRESIONES_VALIDAS = frozenset(e[0] for e in acciones_ui.EXPRESIONES)
MS_EXPRESION = 4000


class Anfitrion(Protocol):
    """Lo que web y nativa aportan (ver AnfitrionWeb / AnfitrionNativo)."""
    modo: str                                   # "normal" | "br"

    def mostrar_ventana(self) -> None: ...
    def mascota(self) -> Any: ...
    def alternar_mascota(self) -> bool: ...
    def voz_on(self) -> bool: ...
    def alternar_voz(self) -> bool: ...
    def llamada_on(self) -> bool: ...
    def alternar_llamada(self) -> bool: ...
    def abrir_ajustes(self, seccion: str = "") -> None: ...
    def salir(self) -> None: ...
    def aviso(self, texto: str) -> None: ...
    def set_aburrimiento(self, activo: bool) -> None: ...
    def en_barra_on(self) -> bool: ...
    def set_en_barra(self, on: bool) -> None: ...
    # Opcionales: comentar() -> bool, ventana_visible() -> bool, soporta_llamada: bool,
    # mascota_barra() -> bool y expresion_barra(arg, ms) (Lune en la barra lateral de la web)


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("montaje: %s.%s falló", type(obj).__name__, metodo)
        return None


def _cfg(config: Any, seccion: str, clave: str, defecto: Any = None) -> Any:
    try:
        if hasattr(config, "get") and not isinstance(config, dict):
            return config.get(seccion, clave, defecto)
        return (config or {}).get(seccion, {}).get(clave, defecto)
    except Exception:
        return defecto


def _cfg_set(config: Any, seccion: str, clave: str, valor: Any) -> None:
    try:
        if hasattr(config, "set") and not isinstance(config, dict):
            config.set(seccion, clave, valor)
        elif isinstance(config, dict):
            config.setdefault(seccion, {})[clave] = valor
    except Exception:
        _log.exception("montaje: no pude guardar %s.%s", seccion, clave)


def _visible(w: Any) -> bool:
    if w is None or getattr(w, "cerrado", False):
        return False
    try:
        return bool(w.isVisible())
    except Exception:
        return False


class _Avisos(QObject):
    """Lleva al hilo de Qt los avisos que terminan en otro hilo (liberar memoria) y
    avisa de las claves de config que cambió una acción (bandeja, radial, atajo)."""
    texto = pyqtSignal(str)
    config = pyqtSignal(str, str)          # (sección, clave) escrita por una acción


@dataclass
class ServiciosCorte4:
    """Lo montado por montar_escritorio. `desmontar()` lo para y lo suelta todo."""
    despachador: Despachador
    tema: Any = None
    atajos: Any = None
    juego: Any = None
    radial: Any = None
    bandeja: Any = None
    escritorio: Any = None
    anfitrion: Any = None
    contexto: Optional[Callable[[], Contexto]] = None
    sonar: Optional[Callable[[str], None]] = None
    avisar: Optional[Callable[[str], None]] = None
    # Cortes 5/6 (ui/montaje_ocio.ServiciosOcio: alarmas, pantalla grande y baile). Se
    # desmonta con esto (su desmontar va el último en _deshacer: se hace el primero).
    ocio: Any = None
    # Señal (sección, clave): una acción de la bandeja, el radial o un atajo escribió esa
    # clave de config (siempre encima, barra de tareas). Los Ajustes abiertos la releen.
    config_cambio: Any = None
    _deshacer: List[Callable[[], None]] = field(default_factory=list, repr=False)
    _desmontado: bool = field(default=False, repr=False)

    @property
    def desmontado(self) -> bool:
        return self._desmontado

    def desmontar(self) -> None:
        """Para y libera todo: radial cerrado, bandeja oculta y borrada, atajos
        soltados (hilo parado), detector de juegos parado (restaura lo que
        cambió), tema y despachador fuera del escritorio. Idempotente."""
        if self._desmontado:
            return
        self._desmontado = True
        for f in reversed(self._deshacer):
            try:
                f()
            except Exception:
                pass
        self._deshacer.clear()
        juego_activo = bool(_llamar(self.juego, "activo")) if self.juego is not None else False
        esc = self.escritorio
        for nombre in reversed(ORDEN):
            ctl = getattr(self, nombre, None)
            if ctl is None:
                continue
            quitado = False
            if esc is not None:
                try:
                    if esc.obtener(nombre) is ctl:
                        quitado = bool(esc.quitar(nombre)) and bool(getattr(esc, "iniciado", False))
                except Exception:
                    _log.exception("montaje: no pude quitar %s del escritorio", nombre)
            if not quitado:
                _llamar(ctl, "detener")
            if nombre == "despachador":
                continue
            if isinstance(ctl, QObject):
                try:
                    ctl.deleteLater()
                except RuntimeError:
                    pass
        if juego_activo:
            _llamar(self.anfitrion, "set_aburrimiento", True)
        try:
            if esc is not None and getattr(esc.estado.actual(), "menu_abierto", False):
                esc.estado.actualizar(menu_abierto=False)
        except Exception:
            pass

    # Alias: el contrato de controlador de ServiciosEscritorio habla de detener().
    detener = desmontar


def _conectar(deshacer: List[Callable[[], None]], senal: Any, slot: Callable) -> None:
    if senal is None or not hasattr(senal, "connect"):
        return
    try:
        senal.connect(slot)
    except (TypeError, RuntimeError):
        return

    def quitar():
        try:
            senal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    deshacer.append(quitar)


# ── Fábricas por defecto (importación diferida) ──────────────────────────────────

def _tema_defecto(config, parent):
    from ui.tema_qt import ControlTema                   # corte 4, agente C
    try:
        return ControlTema(config, parent=parent)
    except TypeError:
        return ControlTema(config)


def _juego_defecto(escritorio, config, *, voice=None, parent=None):
    from ui.modo_juego_qt import ControlModoJuego         # corte 4, agente A
    return ControlModoJuego(escritorio, config, voice=voice, parent=parent)


def _traer_defecto():
    try:
        from servicios.win_ventana import traer_al_frente   # corte 4, agente A
        return traer_al_frente
    except Exception:
        return None


def _modelos_defecto() -> List[str]:
    try:
        from nucleo import vrm
        return list(vrm.listar_modelos())
    except Exception:
        return []


def _recortar_defecto():
    """Corre en el hilo de «Liberar memoria»: el gc.collect ya se hizo en el de Qt."""
    try:
        from servicios.recorte_ram import recortar          # corte 4, agente A
    except Exception:
        return None
    return recortar()


def _autoinicio_defecto():
    from servicios import autoinicio
    return autoinicio


def _crear(nombre: str, fabrica: Callable[[], Any]) -> Any:
    try:
        return fabrica()
    except Exception:
        _log.exception("montaje: no pude crear %s (sigue sin él)", nombre)
        return None


# ── Montaje ──────────────────────────────────────────────────────────────────────

def montar_escritorio(escritorio, anfitrion, config, *, voice=None, icono=None,
                      fabricas: Optional[Dict[str, Any]] = None) -> ServiciosCorte4:
    """Crea, conecta y registra los servicios del corte 4 (ver el docstring del módulo)."""
    fab = dict(fabricas or {})
    parent = escritorio if isinstance(escritorio, QObject) else None
    bus = escritorio.estado

    desp = fab.get("despachador", Despachador)()
    s = ServiciosCorte4(despachador=desp, escritorio=escritorio, anfitrion=anfitrion)
    autoinicio = fab.get("autoinicio") or _crear("autoinicio", _autoinicio_defecto)
    modelos = fab.get("modelos_vrm", _modelos_defecto)
    recortar = fab.get("recortar", _recortar_defecto)
    avisos = _Avisos(parent)

    # ── Utilidades que usan los handlers ───────────────────────────────────
    def mascota():
        m = getattr(escritorio, "mascota", None)
        if m is None or getattr(m, "cerrado", False):
            m = _llamar(anfitrion, "mascota")
        return None if m is None or getattr(m, "cerrado", False) else m

    def mascota_a_la_vista():
        m = mascota()
        return m if _visible(m) else None

    def sacar_mascota():
        if mascota_a_la_vista() is None:
            anfitrion.alternar_mascota()
        return mascota_a_la_vista()

    def ventana_visible() -> bool:
        f = getattr(anfitrion, "ventana_visible", None)
        if callable(f):
            try:
                return bool(f())
            except Exception:
                return True
        return True

    def avisar(texto: str) -> None:
        texto = str(texto)
        if not ventana_visible() and s.bandeja is not None:
            if s.bandeja.mostrar_aviso("Lune CD", texto):
                return
        _llamar(anfitrion, "aviso", texto)

    avisos.texto.connect(avisar)
    s.avisar = avisar
    s.config_cambio = avisos.config

    def fantasma_on(m) -> bool:
        v = getattr(m, "click_through", None) if m is not None else None
        if isinstance(v, bool):
            return v
        if m is not None and isinstance(getattr(m, "_click_through", None), bool):
            return m._click_through
        return bool(_cfg(config, "avatar", "click_through", False))

    def comentarios_on(m) -> bool:
        v = getattr(m, "comentarios_auto", None) if m is not None else None
        if isinstance(v, bool):
            return v
        try:
            return int(_cfg(config, "avatar", "comentarios_cada_min", 0) or 0) > 0
        except (TypeError, ValueError):
            return False

    def estado_juego() -> dict:
        if s.juego is None:
            return {}
        e = _llamar(s.juego, "estado")
        return e if isinstance(e, dict) else {}

    def autoinicio_on() -> bool:
        try:
            return bool(autoinicio.activo()) if autoinicio is not None else False
        except Exception:
            return False

    def preset_tema() -> str:
        # El del ControlTema (lo que se ve, aunque el guardado vaya diferido) o el de la config.
        t = _llamar(s.tema, "actual") if s.tema is not None else None
        p = t.get("preset") if isinstance(t, dict) else None
        return str(p or _cfg(config, "tema", "preset", "cian") or "cian")

    def contexto() -> Contexto:
        est = bus.actual()
        m = mascota()
        vis = _visible(m)
        render = est.render or ""
        if not render and m is not None:
            render = str(getattr(m, "render", "") or "")
        je = estado_juego()
        try:
            varios = len(modelos()) > 1
        except Exception:
            varios = False

        def b(metodo, defecto=False):
            v = _llamar(anfitrion, metodo)
            return defecto if v is None else bool(v)
        return Contexto(
            modo=str(getattr(anfitrion, "modo", "normal") or "normal"),
            render=render, mascota_visible=vis,
            # Web con la flotante guardada: Lune en la barra lateral (AnfitrionWeb).
            mascota_barra=(not vis) and b("mascota_barra"),
            voz_on=b("voz_on"), llamada_on=b("llamada_on"),
            fantasma_on=fantasma_on(m), comentarios_auto_on=comentarios_on(m),
            siempre_encima=bool(_cfg(config, "avatar", "siempre_encima", True)),
            juego_forzado=je.get("forzado"), autoinicio_on=autoinicio_on(),
            en_barra_on=b("en_barra_on", True), varios_vrm=varios,
            tema_preset=preset_tema(),
            juego_activo=bool(je.get("activo", False)), juego_motivo=str(je.get("motivo") or ""),
            tamano=str(_cfg(config, "avatar", "vrm_tamano", "normal") or "normal"),
            encuadre=str(_cfg(config, "avatar", "vrm_encuadre", "retrato") or "retrato"),
        )
    s.contexto = contexto

    # ── Sonidos de menú (por el Mezclador, en un hilo: abrir el dispositivo tarda) ──
    def sonar(nombre: str) -> None:
        if not _cfg(config, "menu", "sonidos", True):
            return
        try:
            if bus.actual().juego and _cfg(config, "juego", "silenciar", True):
                return
        except Exception:
            pass
        ruta = DIR_SFX / f"{nombre}.wav"
        if not ruta.is_file():
            return
        try:
            vol = min(max(float(_cfg(config, "menu", "volumen", 0.6)), 0.0), 1.0)
        except (TypeError, ValueError):
            vol = 0.6
        if vol <= 0:
            return
        fabrica_mez = fab.get("mezclador")

        def tocar():
            try:
                if fabrica_mez is not None:
                    mez = fabrica_mez()
                else:
                    from servicios.mezclador import Mezclador
                    mez = Mezclador.instancia()
                mez.reproducir(mez.cargar_wav(ruta), vol=vol, canal="menu")
            except Exception:
                _log.debug("montaje: sonido %s falló", nombre, exc_info=True)
        threading.Thread(target=tocar, name="LuneSfxMenu", daemon=True).start()

    sonar_fn = fab.get("sonar", sonar)
    s.sonar = sonar_fn

    # ── Piezas ─────────────────────────────────────────────────────────────
    s.tema = _crear("tema", lambda: fab.get("tema", _tema_defecto)(config, parent))
    modo = str(getattr(anfitrion, "modo", "normal") or "normal")

    def disponible_atajo(id_: str) -> bool:
        return desp.tiene(id_) and acciones_ui.en_modo(id_, modo)

    def crear_atajos():
        f = fab.get("atajos")
        if f is not None:
            return f(config, disponible=disponible_atajo, parent=parent)
        from ui.atajos_qt import GestorAtajosQt
        return GestorAtajosQt(config, disponible=disponible_atajo, gestor=fab.get("gestor_atajos"),
                              parent=parent)
    s.atajos = _crear("atajos", crear_atajos)
    s.juego = _crear("juego", lambda: fab.get("juego", _juego_defecto)(
        escritorio, config, voice=voice, parent=parent))

    colores = _llamar(s.tema, "colores_radial") if s.tema is not None else None

    def crear_radial():
        f = fab.get("radial")
        if f is not None:
            return f(desp, bus, config, contexto, colores=colores, sonar=sonar_fn, parent=parent)
        from ui.menu_radial import ControlMenuRadial
        traer = fab["traer_al_frente"] if "traer_al_frente" in fab else _traer_defecto()
        return ControlMenuRadial(desp, bus, config, contexto, colores=colores, sonar=sonar_fn,
                                 parent=parent, traer_al_frente=traer)
    s.radial = _crear("radial", crear_radial)

    def crear_bandeja():
        f = fab.get("bandeja")
        if f is not None:
            return f(desp, bus, contexto, config, icono=icono, parent=parent)
        from ui.bandeja import BandejaLune
        extra = {"fabrica_tray": fab["tray"]} if "tray" in fab else {}
        return BandejaLune(desp, bus, contexto, config, icono=icono, parent=parent, **extra)
    s.bandeja = _crear("bandeja", crear_bandeja)

    # ── Handlers del Despachador ───────────────────────────────────────────
    _registrar_acciones(s, desp, anfitrion, config, mascota, mascota_a_la_vista, sacar_mascota,
                        fantasma_on, comentarios_on, estado_juego, autoinicio, recortar, avisar, avisos)

    # ── Conexiones ─────────────────────────────────────────────────────────
    d = s._deshacer
    if s.atajos is not None:
        def al_atajo(id_: str) -> None:
            if _cfg(config, "atajos", "sonido", False):
                sonar_fn("menu_boton")
            desp.ejecutar(str(id_), origen="atajo")
        _conectar(d, getattr(s.atajos, "accion", None), al_atajo)

    if s.juego is not None:
        def al_juego(activo: bool, motivo: str = "") -> None:
            activo = bool(activo)
            _llamar(s.atajos, "set_pausa", activo)
            _llamar(anfitrion, "set_aburrimiento", not activo)
            if activo and s.radial is not None and _llamar(s.radial, "abierto"):
                _llamar(s.radial, "cerrar")
            _llamar(s.bandeja, "refrescar_tooltip")
        _conectar(d, getattr(s.juego, "cambio", None), al_juego)

    def aplicar_tema(*_):
        if s.tema is None:
            return
        qss = _llamar(s.tema, "qss_menu")
        if isinstance(qss, str):
            _llamar(s.bandeja, "aplicar_qss", qss)
        cols = _llamar(s.tema, "colores_radial")
        if isinstance(cols, dict):
            _llamar(s.radial, "set_colores", cols)
    if s.tema is not None:
        _conectar(d, getattr(s.tema, "cambio", None), aplicar_tema)
        aplicar_tema()

    if s.bandeja is not None:
        _conectar(d, getattr(escritorio, "estado_cambio", None),
                  lambda *_: _llamar(s.bandeja, "refrescar_tooltip"))

    # ── Registro en ServiciosEscritorio (arrancan si ya estaba iniciado) ───
    for nombre in ORDEN:
        ctl = getattr(s, nombre)
        if ctl is None:
            continue
        try:
            actividades = ACTIVIDADES.get(nombre, ())
            if actividades:
                try:
                    escritorio.registrar(nombre, ctl, actividades=actividades)
                except TypeError:                   # un escritorio sin tabla de actividades
                    escritorio.registrar(nombre, ctl)
            else:
                escritorio.registrar(nombre, ctl)
        except Exception:
            _log.exception("montaje: no pude registrar %s", nombre)

    # La ventana fuera de la barra de tareas si así se guardó.
    try:
        if not anfitrion.en_barra_on():
            anfitrion.set_en_barra(False)
    except Exception:
        _log.debug("montaje: en_barra al arrancar falló", exc_info=True)

    # Cortes 5/6: alarmas y temporizadores, pantalla grande y salvapantallas, baile.
    # Se apunta en s._deshacer: el cambio de interfaz en caliente lo desmonta solo.
    # fabricas["ocio"]: dict de fábricas de montar_ocio (tests), o False = sin ellos.
    fab_ocio = fab.get("ocio")
    if fab_ocio is not False:
        try:
            from ui.montaje_ocio import montar_ocio
            s.ocio = montar_ocio(s, config, voice=voice, fabricas=fab_ocio or None)
        except Exception:
            _log.exception("montaje: no pude montar alarmas, pantalla grande y baile (sigue sin ellos)")
    return s


def _registrar_acciones(s: ServiciosCorte4, desp: Despachador, anfitrion, config, mascota,
                        mascota_a_la_vista, sacar_mascota, fantasma_on, comentarios_on,
                        estado_juego, autoinicio, recortar, avisar, avisos) -> None:
    reg = desp.registrar

    # Lune
    reg("mostrar_lune", lambda: anfitrion.mostrar_ventana())
    reg("ajustes", lambda arg="": anfitrion.abrir_ajustes(arg))
    reg("salir", lambda: anfitrion.salir())

    # Mascota
    reg("mascota", lambda: anfitrion.alternar_mascota())

    def chat():
        m = sacar_mascota()
        _llamar(m, "abrir_chat")
    reg("chat", chat)

    def comentar():
        if callable(getattr(anfitrion, "comentar", None)):
            anfitrion.comentar()
            return
        m = sacar_mascota()
        if m is not None and callable(getattr(m, "comentar_pantalla", None)):
            m.comentar_pantalla()
        else:
            avisar("Comentar la pantalla necesita la mascota animada o 3D.")
    reg("comentar", comentar)

    def fantasma():
        m = mascota()
        nuevo = not fantasma_on(m)
        if m is not None and callable(getattr(m, "set_click_through", None)):
            m.set_click_through(nuevo)            # guarda avatar.click_through
        else:
            _cfg_set(config, "avatar", "click_through", nuevo)
    reg("fantasma", fantasma)

    def comentarios_auto():
        m = mascota()
        nuevo = not comentarios_on(m)
        if m is not None and callable(getattr(m, "set_comentarios_auto", None)):
            m.set_comentarios_auto(nuevo)
            return
        _cfg_set(config, "avatar", "comentarios_cada_min", 3 if nuevo else 0)
        _llamar(m, "aplicar_opciones")
    reg("comentarios_auto", comentarios_auto)

    def config_cambiada(seccion: str, clave: str) -> None:
        try:
            avisos.config.emit(seccion, clave)
        except RuntimeError:                       # ya desmontado
            pass

    def siempre_encima():
        nuevo = not bool(_cfg(config, "avatar", "siempre_encima", True))
        _cfg_set(config, "avatar", "siempre_encima", nuevo)
        _llamar(mascota(), "set_encima", nuevo)
        config_cambiada("avatar", "siempre_encima")
    reg("siempre_encima", siempre_encima)

    def dormir():
        m = mascota_a_la_vista()
        if m is None:
            return
        if getattr(m, "durmiendo", False):
            _llamar(m, "despertar")
        else:
            _llamar(m, "dormir")
    reg("dormir", dormir)

    def tamano(arg: str = ""):
        claves = [k for k, _ in acciones_ui.TAMANOS]
        if arg not in claves:
            actual = str(_cfg(config, "avatar", "vrm_tamano", "normal") or "normal")
            arg = claves[(claves.index(actual) + 1) % len(claves)] if actual in claves else "normal"
        _llamar(mascota_a_la_vista(), "aplicar_tamano", arg)
    reg("tamano", tamano)

    def encuadre(arg: str = ""):
        claves = [k for k, _ in acciones_ui.ENCUADRES]
        if arg not in claves:
            actual = str(_cfg(config, "avatar", "vrm_encuadre", "retrato") or "retrato")
            arg = "cuerpo" if actual == "retrato" else "retrato"
        _llamar(mascota_a_la_vista(), "aplicar_encuadre", arg)
    reg("encuadre", encuadre)

    def esquina():
        m = mascota_a_la_vista()
        if m is None:
            return
        if callable(getattr(m, "llevar_a_esquina", None)):
            m.llevar_a_esquina()
        elif callable(getattr(m, "_esquina_inferior_derecha", None)):   # antes del corte 4
            m._esquina_inferior_derecha()
            _llamar(m, "_guardar_posicion")
    reg("esquina", esquina)

    reg("cerrar_mascota", lambda: _llamar(mascota(), "close"))

    def expresion(arg: str = ""):
        if arg not in EXPRESIONES_VALIDAS:
            return
        m = mascota_a_la_vista()
        if m is not None:
            _llamar(m, "set_estado", arg, MS_EXPRESION)
        elif _llamar(anfitrion, "mascota_barra"):
            # Web con la flotante guardada: la pone Lune en la barra lateral.
            _llamar(anfitrion, "expresion_barra", arg, MS_EXPRESION)
    reg("expresion", expresion)

    if s.radial is not None:
        reg("expresiones", lambda: s.radial.abrir("expresiones"))
        reg("menu_radial", lambda: s.radial.abrir("principal"))

    # Voz y llamada
    reg("voz", lambda: anfitrion.alternar_voz())
    if getattr(anfitrion, "soporta_llamada", True) and callable(getattr(anfitrion, "alternar_llamada", None)):
        reg("llamada", lambda: anfitrion.alternar_llamada())

    # Modo juego
    if s.juego is not None:
        def forzar_juego(arg: str = ""):
            a = str(arg or "").strip().lower()
            if a in ("on", "1", "si", "sí", "true"):
                s.juego.forzar(True)
            elif a in ("off", "0", "no", "false"):
                s.juego.forzar(False)
            elif a in ("auto", "-1", "none"):
                s.juego.forzar(None)
            else:                       # alternar: forzado → auto; activo → apagar; si no → encender
                e = estado_juego()
                if e.get("forzado") is not None:
                    s.juego.forzar(None)
                elif e.get("activo"):
                    s.juego.forzar(False)
                else:
                    s.juego.forzar(True)
        reg("modo_juego_forzar", forzar_juego)

    # Tema
    if s.tema is not None:
        def tema(arg: str = ""):
            if arg:
                s.tema.aplicar_preset(str(arg))
        reg("tema", tema)

    # Sistema
    if autoinicio is not None:
        def alternar_autoinicio():
            try:
                nuevo = bool(autoinicio.establecer(not bool(autoinicio.activo())))
            except Exception:
                _log.exception("montaje: autoinicio falló")
                return
            _cfg_set(config, "sistema", "autoinicio", nuevo)
            avisar("Lune arrancará con Windows." if nuevo else "Lune ya no arranca con Windows.")
        reg("autoinicio", alternar_autoinicio)

    def liberar_memoria():
        # gc.collect aquí, en el hilo de Qt (recolectar en otro hilo podría destruir
        # objetos de Qt fuera del suyo); EmptyWorkingSet, en un hilo aparte (como
        # ui/modo_juego_qt._recortar_ahora).
        try:
            gc.collect()
        except Exception:
            pass

        def trabajo():
            try:
                r = recortar()
            except Exception:
                _log.exception("montaje: liberar memoria falló")
                r = None
            if isinstance(r, (tuple, list)) and len(r) == 2:
                try:
                    antes, despues = float(r[0]), float(r[1])
                    texto = f"Memoria liberada: {antes:.0f} MB → {despues:.0f} MB."
                except (TypeError, ValueError):
                    texto = "Memoria liberada."
            else:
                texto = "Memoria liberada."
            try:
                avisos.texto.emit(texto)
            except RuntimeError:
                pass
        threading.Thread(target=trabajo, name="LuneLiberarMemoria", daemon=True).start()
    reg("liberar_memoria", liberar_memoria)

    def en_barra_tareas():
        anfitrion.set_en_barra(not bool(anfitrion.en_barra_on()))
        config_cambiada("interfaz", "en_barra_tareas")
    reg("en_barra_tareas", en_barra_tareas)

    def quitar_avisos():
        try:
            avisos.texto.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            avisos.deleteLater()
        except RuntimeError:
            pass
    s._deshacer.append(quitar_avisos)
