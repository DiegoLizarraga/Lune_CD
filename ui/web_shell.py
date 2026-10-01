"""
ui/web_shell.py — La app de Lune con la piel web "Shibuya Punk".

Monta el diseño real (ui_web/ui_kits/lune-desktop/index.html) dentro de una
QWebEngineView y lo conecta al backend por QWebChannel (ver ui/web_bridge.py).
Se sirve por un http local para que las rutas relativas y el Babel-en-navegador
(que transpila los .jsx) funcionen igual que en el navegador.

Ejecutar en solitario para probar la Fase 1 (shell animado + chat real):
    python -m ui.web_shell

VRM en la barra lateral (corte 3): el .vrm que toca (nucleo.vrm.ruta_modelo:
personaje activo > avatar.vrm_archivo > el primero de modelo_vrm/) se publica en
el http local como /vrm/actual.vrm. Cuando el puente avisa de que el personaje,
el modelo o el render cambiaron (`modelo_vrm_cambio`), se republica y la página
recarga el avatar con `LuneVRMBarra.recargar('/vrm/actual.vrm', <versión>)`; si ya
no hay modelo, la ruta deja de servirse y la barra vuelve al vídeo. La
calibración del modelo actual llega con `vrm_params_cambio` → LuneVRMBarra.params.
Solo se recarga el avatar si cambian la URL o la versión del archivo: un cambio de
render (vrm → animado) solo avisa con el evento, sin volver a descargar el .vrm.

NAVEGACIÓN (revisión de seguridad S2): la página tiene `window.lune` (el puente,
con la configuración, las aprobaciones y el chat). Por eso `PaginaLune` solo deja
navegar el marco principal dentro del servidor local de Lune
(http://127.0.0.1:<puerto>/…); un enlace http(s) pulsado se abre en el navegador
del sistema y cualquier otra cosa (file:, data:, soltar un .html o un enlace en la
ventana…) se rechaza. Además NavigateOnDropEnabled = False.

CAMBIO DE MODO EN CALIENTE (ui/cambio_interfaz.py): la ventana cumple el contrato
de GestorInterfaz. Con `diferir_servicios=True` (la construye el gestor mientras
la vieja sigue viva) no pone su icono en la bandeja ni arranca los servicios de
escritorio (atajos globales…) hasta `iniciar_servicios(estado)`, que además
relanza la asistente y el bot de Telegram si estaban en marcha. Hereda el proveedor,
la voz y la conversación (`aplicar_estado`), se enseña cuando la página ya pintó
(`al_estar_lista`, con tope) y el fondo de la página es el de la app (sin destello
blanco). `cerrar_para_cambio()` la cierra de verdad SIN salir de la app: corta la
IA en curso sin ejecutar sus acciones, cierra las aprobaciones, calla la voz, cierra
la asistente, para el bot, suelta los servicios de escritorio, quita la bandeja y
para el servidor http. «Salir» (bandeja) suelta lo mismo antes de cerrar la app.

CORTES 5 Y 6 (alarmas, pantalla grande y salvapantallas, baile): los objetos `alarmas`
y `musica` del canal (ui/puentes_ocio.py) se registran también antes de setUrl; los
controladores llegan con el corte 4 (ServiciosCorte4.ocio, ui/montaje_ocio.py) y se
enlazan en _montar_servicios_c4; _liberar_todo los cierra una vez, antes de desmontar.

CORTES 7 Y 8 (sentarse, comida, Discord y arranque con Windows): el objeto `vida` del
canal (ui/puente_vida.py → window.luneVida), igual que los de ocio: registrado antes de
setUrl, enlazado con ServiciosCorte4.vida en _montar_servicios_c4 y cerrado una vez en
_liberar_todo.

CORTES 9 Y 10 (reproductor de bailes MMD/VRMA y Minecraft): el objeto `escenario` del
canal (ui/puente_escenario.py → window.luneEscenario), igual: antes de setUrl, enlazado
con ServiciosCorte4.escenario en _montar_servicios_c4 y cerrado una vez en _liberar_todo.
El bot de Minecraft conectado sigue conectado tras un cambio de interfaz en caliente:
estado_para_cambio lleva "minecraft_bot" e iniciar_servicios lo vuelve a conectar (la
ventana vieja lo paró al desmontar; nunca se instala solo).

TAREAS (10.9): el objeto `tareas` del canal (ui/puente_tareas.py → window.luneTareas, la vista
«tareas» estilo Microsoft To Do de extra/tareas.jsx y la entrada «Tareas» de la barra lateral), con la
MISMA memoria del puente (`self.bridge.memoria`): registrado antes de setUrl y cerrado una vez en
_liberar_todo (deja de escuchar la memoria). Si falla, se registra el error y la ventana sigue sin él.

CORTE 4 (bandeja única, menú radial, atajos globales, modo juego y tema): el segundo
objeto del canal, `escritorio` (ui/puente_escritorio.py → window.luneEscritorio), se
registra en __init__ ANTES de cargar la página (el JS solo ve lo registrado al crear su
QWebChannel), todavía sin servicios. `iniciar_servicios` monta los servicios
(ui/montaje_escritorio.montar_escritorio con ui/anfitrion_web.AnfitrionWeb) y se los da
al puente: en un cambio de interfaz en caliente la ventana vieja ya soltó su bandeja y
sus atajos (RegisterHotKey fallaría con 1409 si los dos vivieran a la vez). El icono de
la bandeja es SIEMPRE el de la bandeja única (`tray` lo lee de ella cada vez);
features.minimizar_a_bandeja solo decide si cerrar la ventana la oculta. Si el montaje
falla, queda la bandeja de siempre como respaldo. Al arrancar (no en un cambio de modo)
la última conversación sigue en el chat si chat.restaurar_ultima. El modo juego forzado a
mano (bandeja) pasa a la ventana nueva: estado_para_cambio lleva "juego_forzado"
(None|True|False) e iniciar_servicios lo vuelve a forzar.

LUNE EN REPOSO (11.2): en QtWebEngine dentro de un QWidget cada frame de Chromium pasa por
Qt, y con una sola animación infinita viva la ventana a la vista gastaba 1-3 núcleos sin que
nadie la usara. La ventana le dice a la página si es la activa (window.luneFoco(bool): en
changeEvent de ActivationChange/WindowStateChange, showEvent, hideEvent y al cargar) y la
página decide (ui_web/lune_reposo.js): sin foco 20 s o sin tocarla 90 s, body.lune-quieta
congela las animaciones y la barra pausa su vídeo y su avatar 3D. Opción efectos.pausar_sin_foco.

CARGA PEREZOSA (11.2): con `cargar_al_mostrar=True` (main.py, arranque con Windows a la bandeja o
con la asistente fuera: la ventana nace oculta) la página NO se pide hasta el primer showEvent.
Hasta entonces no hay proceso de render ni React ni Babel (unos 100 MB y el arranque de la
página), y la mayoría de las veces nadie abre la ventana. Todo lo demás arranca igual: el puente
y los objetos del canal se registran antes (setUrl llega después, en _cargar_pagina), los
servicios de escritorio y la bandeja también, y lo que se manda a la página mientras tanto
(_js) se pierde sin más: al cargar, la página lo pide todo (estado_inicial, vrm_barra, efectos…).
al_estar_lista espera a loadFinished con su tope, como siempre.
"""
from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QAction

# El servidor http vive en ui/servidor_web.py (sin WebEngine) para que la
# asistente lo comparta; aquí se conservan los nombres antiguos por compatibilidad.
from ui.servidor_web import RAIZ, DIR_WEB, ServidorEstatico as _ServidorEstatico, HandlerSilencioso as _HandlerSilencioso  # noqa: F401
from nucleo import rutas
from ui.cambio_interfaz import (PROVEEDOR_A_WEB, PROVEEDOR_DESDE_WEB, TOPE_CARGA_MS, bot_minecraft_de,
                                callar_voz, cerrar_asistente, desmontar_servicios_c4, detener_bot,
                                detener_hilo_ia, hilo_vivo, instantanea_sesion, ordenes_cortadas,
                                parar_temporizadores, quitar_bandeja, reconectar_bot_minecraft,
                                soltar_hilos)

PAGINA = "ui_kits/lune-desktop/index.html"
RUTA_VRM = "/vrm/actual.vrm"          # la misma que RUTA_MODELO de vrm_barra.js
_SIN_MODELO = {"url": "", "v": "", "archivo": "", "params": ""}

# Fondo de la página mientras carga: el de la app (--bg, ink-900 de
# ui_web/tokens/colors.css), no el blanco de Chromium.
COLOR_FONDO = "#080B16"
# ¿Ya pintó React? (.ln-app es la raíz de app.jsx.) Se sondea tras loadFinished.
JS_PAGINA_PINTADA = "!!document.querySelector('.ln-app')"
SONDEO_PINTADA_MS = 60
# Al salir de la app, lo que se espera como mucho a que corte el hilo de la IA.
ESPERA_IA_SALIR_MS = 1500


def js_foco(activa: bool) -> str:
    """JS que le dice a la página si la ventana es la activa (ui_web/lune_reposo.js: sin foco
    un rato, Lune se queda quieta y la ventana deja de gastar CPU)."""
    return f"window.luneFoco && window.luneFoco({'true' if activa else 'false'})"


def _log_error(msg: str) -> None:
    try:
        from nucleo.utils import log_error
        log_error(msg)
    except Exception:
        pass


def publicar_vrm(servidor, config) -> dict:
    """Publica en `servidor` el .vrm que toca enseñar en RUTA_VRM (o deja de servirlo
    si no hay ninguno). Devuelve {url, v, archivo, params}: url "" sin modelo; v cambia
    si cambia el archivo (mtime y tamaño: se salta la caché del navegador); params es
    el JSON de nucleo.vrm.params_modelo (calibración + seguimiento)."""
    from nucleo import vrm
    try:
        m = vrm.ruta_modelo(config)
    except Exception:
        m = None
    st = None
    if m is not None:
        try:
            st = m.stat()
        except OSError:
            m = None
    if m is None:
        extra = getattr(servidor, "rutas_extra", None)
        if isinstance(extra, dict):
            extra.pop(RUTA_VRM, None)            # la página pide el vídeo: sin 3D
        return dict(_SIN_MODELO)
    servidor.publicar(RUTA_VRM, m)
    try:
        params = vrm.params_modelo_json(str(m), config)
    except Exception:
        params = ""
    return {"url": RUTA_VRM, "v": f"{st.st_mtime_ns:x}-{st.st_size:x}", "archivo": m.name,
            "params": params}


def js_vrm_barra(info: dict, recargar: bool = True) -> str:
    """JS que avisa a la página del modelo nuevo: guarda window.__luneVrmBarra, pasa la
    calibración, recarga los avatares vivos (LuneVRMBarra.recargar) SOLO si `recargar`
    (cambió la URL o la versión del archivo) y lanza el evento 'lune-vrm-modelo' para
    que la barra lateral cambie a 3D o vuelva al vídeo."""
    datos = json.dumps(info, ensure_ascii=False).replace("</", "<\\/")
    return (
        "(function (i, r) {"
        " window.__luneVrmBarra = i; var n = 0;"
        " try { if (window.LuneVRMBarra && i.url) {"
        " if (i.params) window.LuneVRMBarra.params(i.params);"
        " if (r) n = window.LuneVRMBarra.recargar(i.url, i.v); } } catch (e) {}"
        " try { window.dispatchEvent(new CustomEvent('lune-vrm-modelo',"
        " { detail: Object.assign({ recargados: n }, i) })); } catch (e) {}"
        f"}})({datos}, {'true' if recargar else 'false'});"
    )


def js_vrm_params(params_json: str) -> str:
    """JS que aplica la calibración del modelo actual al avatar de la barra lateral."""
    datos = json.dumps(str(params_json or ""), ensure_ascii=False).replace("</", "<\\/")
    return (f"(function (p) {{ if (window.__luneVrmBarra) window.__luneVrmBarra.params = p;"
            f" try {{ window.LuneVRMBarra && window.LuneVRMBarra.params(p); }} catch (e) {{}} }})({datos});")


def juego_forzado_de(servicios) -> "bool | None":
    """El forzado del modo juego de ServiciosCorte4 (`juego.forzado`; si no lo expone,
    su estado()): True/False si está puesto a mano (bandeja), None si detecta solo o no
    hay modo juego. Va en estado_para_cambio (VS6)."""
    juego = getattr(servicios, "juego", None) if servicios is not None else None
    if juego is None:
        return None
    try:
        v = getattr(juego, "forzado", None)
        if v is None and callable(getattr(juego, "estado", None)):
            v = (juego.estado() or {}).get("forzado")
    except Exception:
        return None
    return v if isinstance(v, bool) else None


# ── Navegación: solo el servidor local de Lune ─────────────────────────────────
PERMITIR, EXTERNO, RECHAZAR = "permitir", "externo", "rechazar"
_ESQUEMAS_EXTERNOS = ("http", "https")


def mismo_origen(url: QUrl, origen: QUrl) -> bool:
    """¿`url` es del servidor local de Lune (mismo esquema http, host y puerto)?"""
    if not url.isValid() or not origen.isValid():
        return False
    return (url.scheme().lower() == origen.scheme().lower() == "http"
            and url.host().lower() == origen.host().lower()
            and url.port() == origen.port() and url.port() > 0)


def decidir_navegacion(url: QUrl, tipo, marco_principal: bool, origen: QUrl) -> str:
    """
    PERMITIR: el marco principal se queda en el servidor local (o es un iframe:
    esos no reciben el canal). EXTERNO: enlace http(s) pulsado → navegador del
    sistema. RECHAZAR: todo lo demás (file:, data:, soltar algo en la ventana,
    redirecciones o formularios hacia fuera…).
    """
    if not marco_principal:
        return PERMITIR
    if mismo_origen(url, origen):
        return PERMITIR
    if (tipo == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
            and url.scheme().lower() in _ESQUEMAS_EXTERNOS and url.host()):
        return EXTERNO
    return RECHAZAR


class _PaginaAlNavegador(QWebEnginePage):
    """Página de usar y tirar para target=_blank / window.open: un enlace http(s)
    pulsado va al navegador del sistema; aquí nunca se carga nada."""

    def __init__(self, abrir_fuera, parent=None):
        super().__init__(parent)
        self._abrir_fuera = abrir_fuera

    def acceptNavigationRequest(self, url, tipo, marco_principal):
        if (tipo == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
                and url.scheme().lower() in _ESQUEMAS_EXTERNOS and url.host()):
            try:
                self._abrir_fuera(QUrl(url))
            except Exception:
                pass
        self.deleteLater()
        return False


class PaginaLune(QWebEnginePage):
    """QWebEnginePage de la ventana principal: el marco principal (el que tiene
    `window.lune`) solo navega dentro de `origen` (el servidor local de Lune)."""

    def __init__(self, origen: QUrl, parent=None, abrir_fuera=None):
        super().__init__(parent)
        self.origen = QUrl(origen)
        self._abrir_fuera = abrir_fuera or QDesktopServices.openUrl
        self.rechazadas = []                          # (url, motivo) para diagnóstico

    def acceptNavigationRequest(self, url, tipo, marco_principal):
        decision = decidir_navegacion(url, tipo, marco_principal, self.origen)
        if decision == PERMITIR:
            return True
        if decision == EXTERNO:
            try:
                self._abrir_fuera(QUrl(url))
            except Exception:
                pass
        self.rechazadas.append((url.toString()[:200], decision))
        del self.rechazadas[:-20]
        return False

    def createWindow(self, tipo):
        return _PaginaAlNavegador(self._abrir_fuera, self)


def asegurar_pagina(web: QWebEngineView, origen: QUrl, abrir_fuera=None) -> PaginaLune:
    """Pone en `web` una PaginaLune (guarda de navegación) y apaga NavigateOnDrop."""
    pagina = PaginaLune(origen, web, abrir_fuera)
    web.setPage(pagina)
    atributo = getattr(QWebEngineSettings.WebAttribute, "NavigateOnDropEnabled", None)
    if atributo is not None:                          # Qt ≥ 6.4
        pagina.settings().setAttribute(atributo, False)
    return pagina


class VentanaWeb(QMainWindow):
    """Ventana principal con la UI web y el puente al backend."""

    MODO_INTERFAZ = "web"
    # Ajustes pidió otro modo de interfaz (lo hace GestorInterfaz, ui/cambio_interfaz.py).
    cambio_interfaz_pedido = pyqtSignal(str)
    # Fábricas de montar_escritorio (ui/montaje_escritorio.py): None = las de verdad (tests).
    FABRICAS_C4 = None

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None, parent=None,
                 *, diferir_servicios: bool = False, cargar_al_mostrar: bool = False):
        super().__init__(parent)
        self._servicios_c4 = None     # corte 4 (montar_escritorio): en iniciar_servicios
        self._anfitrion = None        # ui/anfitrion_web.AnfitrionWeb
        self._puente_esc = None       # ui/puente_escritorio.PuenteEscritorio («escritorio»)
        self._puentes_ocio = None     # ui/puentes_ocio.PuentesOcio («alarmas» y «musica»)
        self._puente_vida = None      # ui/puente_vida.PuenteVida («vida», cortes 7/8)
        self._puente_escenario = None  # ui/puente_escenario.PuenteEscenario («escenario», cortes 9/10)
        self._puente_tareas = None    # ui/puente_tareas.PuenteTareas («tareas», 10.9)
        self.setWindowTitle("Lune CD")
        self.resize(1280, 820)
        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = rutas.recurso("assets", f"lune_icon.{ext}")
            if ruta.exists():
                self._icono = QIcon(str(ruta))
                self.setWindowIcon(self._icono)
                break
        self._salir = False   # True solo cuando el usuario elige "Salir" en la bandeja
        self._relevada = False        # cerrada por un cambio de modo: sin bandeja ni quit
        self._liberada = False        # ya soltó sus recursos (cambio de modo o salir)
        self._en_marcha = {}          # lo que estaba en marcha al soltarlos
        self._servicios = False       # bandeja y servicios de escritorio arrancados
        self._pagina_cargada = False
        self._al_cargar_pend = []     # al_estar_lista esperando a loadFinished
        self._url_pagina = None       # la de la página (setUrl en _cargar_pagina)
        self._pagina_pedida = False   # setUrl ya hecho (una vez)
        self._carga_pendiente = False  # carga perezosa: setUrl al primer showEvent
        self.tray = None

        self._servidor = _ServidorEstatico(DIR_WEB)
        if not self._servidor.iniciar():
            raise RuntimeError("No pude servir la UI web (ui_web/).")

        # Puente backend ↔ web. La conversación se guarda en chats/ (como la nativa)
        # y, construida por el gestor, sin arrancar aún los servicios de escritorio.
        from ui.web_bridge import LuneBridge
        self.bridge = LuneBridge(config=config, ai_manager=ai_manager,
                                 memoria=memoria, tools=tools, parent=self,
                                 persistir_chats=True, diferir_servicios=diferir_servicios)
        if not diferir_servicios:
            # Al arrancar: la última conversación (un cambio de modo trae la suya con
            # aplicar_estado). La página la pinta al cargar (estado_inicial).
            restaurar = getattr(self.bridge, "restaurar_ultima", None)
            if callable(restaurar):
                try:
                    restaurar()
                except Exception as e:
                    _log_error(f"[chats] no pude retomar la última conversación: {e}")
        self._canal = QWebChannel()
        self._canal.registerObject("lune", self.bridge)
        # Corte 4: `escritorio` (window.luneEscritorio) también ANTES de setUrl.
        self._registrar_puente_escritorio()
        # Cortes 5/6: `alarmas` y `musica` (window.luneAlarmas / luneMusica), igual: antes
        # de setUrl y sin servicios (los enlaza _montar_servicios_c4).
        self._registrar_puentes_ocio()
        # Cortes 7/8: `vida` (window.luneVida: sentarse, comida, Discord y arranque con
        # Windows), igual: antes de setUrl y sin servicios.
        self._registrar_puente_vida()
        # Cortes 9/10: `escenario` (window.luneEscenario: bailes MMD/VRMA y Minecraft), igual.
        self._registrar_puente_escenario()
        # 10.9: `tareas` (window.luneTareas: la lista estilo To Do sobre la memoria del puente), igual.
        self._registrar_puente_tareas()
        # Ajustes → «Modo de interfaz»: el puente lo pide y el gestor hace el cambio.
        senal = getattr(self.bridge, "interfaz_pedida", None)
        if senal is not None and hasattr(senal, "connect"):
            senal.connect(self.cambio_interfaz_pedido)

        # VRM de la barra lateral: /vrm/actual.vrm desde ya (la página lo pide al
        # cargar con vrm_barra()) y republicado cuando cambie personaje o modelo.
        self._vrm_info = None
        self.web = None
        self._publicar_vrm()
        self.bridge.modelo_vrm_cambio.connect(self._publicar_vrm)
        self.bridge.vrm_params_cambio.connect(self._vrm_params)

        self.web = QWebEngineView()
        # Guarda de navegación ANTES de dar el canal: solo el servidor local de Lune.
        url_pagina = QUrl(self._servidor.url(PAGINA))
        pagina = asegurar_pagina(self.web, url_pagina)
        try:
            pagina.setBackgroundColor(QColor(COLOR_FONDO))     # sin destello blanco al cargar
        except Exception:
            pass
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # Sonidos de la interfaz (luneSfx: menús, alarmas) que se disparan desde el
        # puente o un temporizador, sin un clic justo antes: Chromium los bloquearía.
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        self.web.page().setWebChannel(self._canal)
        self.web.loadFinished.connect(self._al_cargar)
        self._url_pagina = url_pagina
        # Nace oculta (arranque con Windows a la bandeja o con la asistente fuera): la página,
        # al primer showEvent. Si no, ya.
        self._carga_pendiente = bool(cargar_al_mostrar)
        if not self._carga_pendiente:
            self._cargar_pagina()
        self.setCentralWidget(self.web)

        # Quedarse en segundo plano (como Discord): al cerrar, se oculta en la
        # bandeja y sigue viva; se reabre desde la bandeja o relanzando el .vbs.
        QApplication.instance().setQuitOnLastWindowClosed(False)
        if diferir_servicios:
            # La construye GestorInterfaz con la ventana anterior aún viva: la
            # bandeja y los servicios de escritorio (atajos globales) son suyos
            # hasta que se cierre; iniciar_servicios() los arranca después.
            self._pausar_escritorio()
        else:
            self.iniciar_servicios()

    # ── Servicios exclusivos (bandeja, escritorio) ──────────────────────────────
    def iniciar_servicios(self, estado=None):
        """Bandeja y servicios de escritorio (atajos globales, controladores) y lo que
        estaba en marcha en la ventana anterior (asistente fuera, bot de Telegram). Una
        sola vez; al arrancar normal, desde el constructor."""
        if self._servicios:
            return
        self._servicios = True
        estado = estado if isinstance(estado, dict) else {}
        # Corte 4: bandeja única, atajos, radial, modo juego y tema. Aquí y no en
        # __init__: en un cambio en caliente la ventana vieja ya los soltó.
        montar = getattr(self, "_montar_servicios_c4", None)
        if callable(montar) and getattr(self, "_servicios_c4", None) is None:
            montar()
        if (getattr(getattr(self, "_servicios_c4", None), "bandeja", None) is None
                and getattr(self, "tray", None) is None):
            self._construir_bandeja()                # respaldo: sin la bandeja única
        b = getattr(self, "bridge", None)
        esc = getattr(b, "escritorio", None)
        if esc is not None:
            try:
                esc.iniciar()
            except Exception as e:
                _log_error(f"[interfaz] servicios de escritorio: {e}")
        if b is None:
            return
        if estado.get("asistente_fuera"):
            try:
                if not b.asistente_visible():
                    b.asistente_toggle()
            except Exception as e:
                _log_error(f"[interfaz] no pude volver a sacar a la asistente: {e}")
        # El modo juego forzado a mano en la ventana anterior sigue forzado (VS6).
        forzado = estado.get("juego_forzado")
        juego = getattr(getattr(self, "_servicios_c4", None), "juego", None)
        if isinstance(forzado, bool) and juego is not None:
            try:
                juego.forzar(forzado)
            except Exception as e:
                _log_error(f"[interfaz] no pude volver a forzar el modo juego: {e}")
        if estado.get("telegram"):
            try:
                if not hilo_vivo(getattr(b, "_tg_worker", None)):
                    b.telegram_toggle()
            except Exception as e:
                _log_error(f"[interfaz] no pude relanzar el bot de Telegram: {e}")
        # Cortes 9/10: el bot de Minecraft que estaba conectado se vuelve a conectar (la
        # ventana vieja lo paró al desmontar; nunca se instala solo).
        if estado.get("minecraft_bot"):
            ok, texto = reconectar_bot_minecraft(getattr(self, "_servicios_c4", None))
            if not ok and texto:
                _log_error(f"[interfaz] no pude volver a conectar el bot de Minecraft: {texto}")

    # ── Corte 4: puente `escritorio`, montaje y bandeja única ───────────────────
    def _registrar_puente_escritorio(self):
        """El objeto `escritorio` del canal (window.luneEscritorio), registrado en
        __init__ ANTES de cargar la página (el JS solo ve lo registrado al crear su
        QWebChannel). Sin servicios todavía: se los da _montar_servicios_c4."""
        try:
            from ui.anfitrion_web import AnfitrionWeb
            from ui.puente_escritorio import registrar_en_canal
            if self._anfitrion is None:
                self._anfitrion = AnfitrionWeb(self.bridge, self)
            self._puente_esc = registrar_en_canal(self._canal, None, self.bridge.escritorio,
                                                  self.bridge.config, anfitrion=self._anfitrion)
        except Exception as e:
            self._puente_esc = None
            _log_error(f"[corte4] no pude registrar el puente de escritorio: {e}")
        return self._puente_esc

    def _registrar_puentes_ocio(self):
        """Los objetos `alarmas` y `musica` del canal (cortes 5/6: window.luneAlarmas y
        window.luneMusica), registrados en __init__ ANTES de cargar la página, sin
        servicios: _montar_servicios_c4 les da ServiciosCorte4.ocio con enlazar()."""
        try:
            from ui.puentes_ocio import registrar_puentes_ocio
            self._puentes_ocio = registrar_puentes_ocio(self._canal, self.bridge.config,
                                                        getattr(self, "_servicios_c4", None))
        except Exception as e:
            self._puentes_ocio = None
            _log_error(f"[ocio] no pude registrar los puentes de alarmas y música: {e}")
        return self._puentes_ocio

    def _registrar_puente_vida(self):
        """El objeto `vida` del canal (cortes 7/8: window.luneVida), registrado en
        __init__ ANTES de cargar la página, sin servicios: _montar_servicios_c4 le da
        ServiciosCorte4 (con su `.vida`) con enlazar(). Lo que es solo config (tarjetas,
        opciones del arranque con Windows) funciona igual sin ellos."""
        try:
            from ui.puente_vida import registrar_puente_vida
            self._puente_vida = registrar_puente_vida(self._canal, self.bridge.config,
                                                      getattr(self, "_servicios_c4", None))
        except Exception as e:
            self._puente_vida = None
            _log_error(f"[vida] no pude registrar el puente de sentarse, comida y Discord: {e}")
        return self._puente_vida

    def _registrar_puente_escenario(self):
        """El objeto `escenario` del canal (cortes 9/10: window.luneEscenario, bailes MMD/VRMA y
        Minecraft), registrado en __init__ ANTES de cargar la página, sin servicios:
        _montar_servicios_c4 le da ServiciosCorte4 (con su `.escenario`) con enlazar(). Lo que es
        solo config (tarjetas de Ajustes, datos del bot) funciona igual sin ellos. La ventana es
        el padre del diálogo de importar bailes."""
        try:
            from ui.puente_escenario import registrar_puente_escenario
            self._puente_escenario = registrar_puente_escenario(
                self._canal, self.bridge.config, getattr(self, "_servicios_c4", None), ventana=self)
        except Exception as e:
            self._puente_escenario = None
            _log_error(f"[escenario] no pude registrar el puente de bailes y Minecraft: {e}")
        return self._puente_escenario

    def _registrar_puente_tareas(self):
        """El objeto `tareas` del canal (10.9: window.luneTareas, ui/puente_tareas.py), registrado en
        __init__ ANTES de cargar la página, con la MISMA memoria del puente web (nunca otra instancia:
        cada una reescribiría memoria.json entera). No necesita servicios. Si falla, la app sigue."""
        try:
            from ui.puente_tareas import registrar_puente_tareas
            self._puente_tareas = registrar_puente_tareas(self._canal, getattr(self.bridge, "memoria", None))
        except Exception as e:
            self._puente_tareas = None
            _log_error(f"[tareas] no pude registrar el puente de tareas: {e}")
        return self._puente_tareas

    def _montar_servicios_c4(self):
        """Bandeja única, atajos globales, menú radial, modo juego y tema
        (ui/montaje_escritorio.montar_escritorio) sobre los servicios de escritorio del
        puente, y al puente `escritorio` de la página. Si falla, la ventana sigue con
        la bandeja de siempre (respaldo). Devuelve ServiciosCorte4 o None. Con ellos
        vienen los de los cortes 5/6 (ServiciosCorte4.ocio) para los puentes de ocio."""
        b = self.bridge
        try:
            from ui.montaje_escritorio import montar_escritorio
            if self._anfitrion is None:
                from ui.anfitrion_web import AnfitrionWeb
                self._anfitrion = AnfitrionWeb(b, self)
            s = montar_escritorio(b.escritorio, self._anfitrion, b.config, voice=b.voice,
                                  icono=self._icono, fabricas=self.FABRICAS_C4)
        except Exception as e:
            _log_error(f"[corte4] no pude montar bandeja/atajos/radial/modo juego: {e}")
            return None
        self._servicios_c4 = s
        try:
            b._servicios_c4 = s                      # desmontar_servicios_c4(ventana, puente)
        except Exception:
            pass
        puente = self._puente_esc
        if puente is not None:
            try:
                puente.usar_servicios(s, anfitrion=self._anfitrion, contexto=s.contexto)
            except Exception as e:
                _log_error(f"[corte4] el puente de escritorio no tomó los servicios: {e}")
        po = getattr(self, "_puentes_ocio", None)
        if po is not None:
            try:
                po.enlazar(s)                        # se suelta solo al desmontar (s._deshacer)
            except Exception as e:
                _log_error(f"[ocio] los puentes de alarmas y música no tomaron los servicios: {e}")
        pv = getattr(self, "_puente_vida", None)
        if pv is not None:
            try:
                pv.enlazar(s)                        # cortes 7/8; se suelta solo con s._deshacer
            except Exception as e:
                _log_error(f"[vida] el puente de sentarse, comida y Discord no tomó los servicios: {e}")
        pe = getattr(self, "_puente_escenario", None)
        if pe is not None:
            try:
                pe.enlazar(s)                        # cortes 9/10; se suelta solo con s._deshacer
            except Exception as e:
                _log_error(f"[escenario] el puente de bailes y Minecraft no tomó los servicios: {e}")
        return s

    @property
    def tray(self):
        """El icono de la bandeja: el de la bandeja única (corte 4) si está montada y
        en marcha; si no, el de respaldo (_construir_bandeja). Se lee cada vez: tras
        detener/iniciar los servicios de escritorio el icono es otro."""
        s = getattr(self, "_servicios_c4", None)
        t = getattr(getattr(s, "bandeja", None), "icono_tray", None) if s is not None else None
        return t if t is not None else getattr(self, "_tray_respaldo", None)

    @tray.setter
    def tray(self, valor):
        self._tray_respaldo = valor

    def _pausar_escritorio(self):
        esc = getattr(getattr(self, "bridge", None), "escritorio", None)
        if esc is not None and getattr(esc, "iniciado", False):
            try:
                esc.detener()
            except Exception:
                pass

    # ── Cambio de modo (GestorInterfaz) ─────────────────────────────────────────
    def estado_para_cambio(self) -> dict:
        """Lo que hereda la ventana del modo nuevo (la geometría la toma el gestor)."""
        b = self.bridge
        estado = {"modo": self.MODO_INTERFAZ}
        prov = PROVEEDOR_DESDE_WEB.get(str(getattr(b, "_provider_web", "") or ""))
        if prov:
            estado["proveedor"] = prov
        estado["voz"] = bool(getattr(getattr(b, "voice", None), "_enabled", False))
        estado["sesion"] = instantanea_sesion(getattr(b, "chats", None))
        try:
            estado["asistente_fuera"] = bool(b.asistente_visible())
        except Exception:
            estado["asistente_fuera"] = False
        estado["telegram"] = hilo_vivo(getattr(b, "_tg_worker", None))
        # Modo juego forzado desde la bandeja (VS6): True/False a mano, None = detectar.
        estado["juego_forzado"] = juego_forzado_de(getattr(self, "_servicios_c4", None))
        # Cortes 9/10: el bot de Minecraft conectado (o conectándose) se reconecta en la nueva.
        estado["minecraft_bot"] = bot_minecraft_de(getattr(self, "_servicios_c4", None))
        return estado

    def aplicar_estado(self, estado: dict) -> None:
        """Antes de enseñarse: el proveedor, la voz y la conversación de la ventana
        anterior (el puente la retoma en su historial de chats/ y en el del modelo,
        con la marca de texto de terceros)."""
        estado = estado if isinstance(estado, dict) else {}
        b = self.bridge
        web = PROVEEDOR_A_WEB.get(str(estado.get("proveedor") or ""))
        if web:
            try:
                b.proveedor_elegido(web)
            except Exception:
                pass
        voz = getattr(b, "voice", None)
        if "voz" in estado and voz is not None:
            quiere = bool(estado.get("voz")) and bool(getattr(voz, "available", False))
            if bool(getattr(voz, "_enabled", False)) != quiere:
                voz._enabled = quiere
                try:
                    b.voz_estado.emit(quiere)
                except Exception:
                    pass
        retomar = getattr(b, "retomar_sesion", None)
        if estado.get("sesion") and callable(retomar):
            retomar(estado["sesion"])

    def _cargar_pagina(self) -> bool:
        """setUrl de la página, UNA vez (al construir o, con la carga perezosa, al primer
        showEvent). Los objetos del canal ya están registrados. → True si la pidió ahora."""
        web, url = getattr(self, "web", None), getattr(self, "_url_pagina", None)
        if getattr(self, "_pagina_pedida", False) or web is None or url is None:
            return False
        self._pagina_pedida = True
        self._carga_pendiente = False
        web.setUrl(url)
        return True

    def _al_cargar(self, _ok=True):
        self._pagina_cargada = True
        avisar = getattr(self, "_avisar_foco", None)  # la página recién cargada no sabe si tiene el foco
        if callable(avisar):
            avisar(forzar=True)
        pend, self._al_cargar_pend = self._al_cargar_pend, []
        for fn in pend:
            try:
                fn()
            except Exception:
                pass

    def al_estar_lista(self, callback, tope_ms=TOPE_CARGA_MS):
        """Llama a callback() UNA vez: cuando la página cargó y React ya pintó
        (.ln-app), o a los `tope_ms` pase lo que pase (nunca se queda sin enseñar)."""
        hecho = [False]

        def listo(*_):
            if hecho[0]:
                return
            hecho[0] = True
            try:
                callback()
            except Exception as e:
                _log_error(f"[interfaz] al enseñar la ventana web: {e}")

        QTimer.singleShot(max(0, int(tope_ms)), listo)

        def sondear():
            if hecho[0]:
                return

            def resultado(pintada):
                if hecho[0]:
                    return
                if pintada:
                    listo()
                else:
                    QTimer.singleShot(SONDEO_PINTADA_MS, sondear)
            try:
                self.web.page().runJavaScript(JS_PAGINA_PINTADA, resultado)
            except Exception:
                listo()

        if self._pagina_cargada:
            sondear()
        else:
            self._al_cargar_pend.append(sondear)

    def aviso_cambio(self, texto: str) -> None:
        """Aviso no modal (el toast de la página)."""
        try:
            self.bridge.aviso.emit(str(texto))
        except Exception:
            _log_error(f"[interfaz] {texto}")

    def cerrar_para_cambio(self) -> dict:
        """Cambio de modo: suelta todo lo que la ventana nueva vuelve a crear y se
        cierra de verdad SIN salir de la app. Devuelve lo que estaba en marcha."""
        en_marcha = self._liberar_todo()
        self._relevada = True
        for metodo in ("hide", "close"):
            try:
                getattr(self, metodo)()
            except (RuntimeError, AttributeError):
                pass
        return en_marcha

    def _liberar_todo(self, espera_ia_ms: int = 0) -> dict:
        """Suelta lo que tiene la ventana (una vez): IA en curso (sin ejecutar sus
        acciones), aprobaciones, voz, llamada y dictado, temporizadores, asistente,
        bot, servicios de escritorio, bandeja, servidor http y página."""
        if getattr(self, "_liberada", False):
            return dict(getattr(self, "_en_marcha", {}) or {})
        self._liberada = True
        en_marcha = {"asistente_fuera": False, "telegram": False}
        b = getattr(self, "bridge", None)
        # Puentes de ocio (cortes 5/6) fuera del canal antes de desmontar sus
        # controladores (alarmas, pantalla grande, baile: van con el corte 4).
        po = getattr(self, "_puentes_ocio", None)
        if po is not None:
            try:
                po.cerrar()                          # idempotente
            except Exception:
                pass
            self._puentes_ocio = None
        pv = getattr(self, "_puente_vida", None)      # cortes 7/8, igual
        if pv is not None:
            try:
                pv.cerrar()                          # idempotente
            except Exception:
                pass
            self._puente_vida = None
        pe = getattr(self, "_puente_escenario", None)  # cortes 9/10, igual
        if pe is not None:
            try:
                pe.cerrar()                          # idempotente
            except Exception:
                pass
            self._puente_escenario = None
        pt = getattr(self, "_puente_tareas", None)     # 10.9: deja de escuchar la memoria
        if pt is not None:
            try:
                pt.cerrar()                          # idempotente
            except Exception:
                pass
            self._puente_tareas = None
        # Corte 4 lo primero (bandeja única, atajos, detector de juego, radial, tema y
        # el puente `escritorio`), una sola vez: el modo juego devuelve lo que cambió
        # (prioridad, voz, la asistente que escondió: cuenta como «fuera») antes de que
        # se suelte el resto, y la bandeja propia de respaldo se quita después.
        desmontar_servicios_c4(self, b)
        puente = getattr(self, "_puente_esc", None)
        if puente is not None:
            try:
                puente.cerrar()                      # idempotente: sin servicios, lo desregistra aquí
            except Exception:
                pass
            self._puente_esc = None
        if b is not None:
            guardar = getattr(b, "guardar_conversacion", None)
            if callable(guardar):
                try:
                    guardar()
                except Exception as e:
                    _log_error(f"[interfaz] no pude guardar la conversación: {e}")
            # Órdenes de Telegram a medio responder o esperando tu permiso: que allí
            # no se queden esperando (antes de cortar la IA y de parar el bot).
            acc = getattr(b, "acciones", None)
            self._avisar_ordenes_cortadas(b, acc)
            # Lo que emita el worker en curso ya no cuenta (generación) y sus
            # señales se desconectan: ni se pinta ni se ejecutan sus <|CALL|>.
            try:
                b._gen = int(getattr(b, "_gen", 0) or 0) + 1
            except Exception:
                pass
            detener_hilo_ia(getattr(b, "_worker", None),
                            getattr(getattr(b, "ai", None), "providers", None), espera_ia_ms)
            b._worker = None
            if acc is not None:
                try:
                    acc.cerrar()                     # «¿Lo hago?» abiertas: se cierran sin hacer nada
                except Exception:
                    pass
            if getattr(b, "_llamada", None) is not None:
                try:
                    b._llamada_detener()
                except Exception:
                    pass
            grab, b._grabadora = getattr(b, "_grabadora", None), None
            if grab is not None:
                for metodo in ("cancelar", "detener"):
                    fn = getattr(grab, metodo, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            pass
                        break
            soltar_hilos(getattr(b, "_transcriptor", None), getattr(b, "_probador", None))
            parar_temporizadores(getattr(b, "_aburrida_t", None))
            cancelar_plan = getattr(b, "_cancelar_plan", None)
            if callable(cancelar_plan):
                try:
                    cancelar_plan()
                except Exception:
                    pass
            callar_voz(getattr(b, "voice", None))
            # Asistente y bot: la ventana nueva los relanza si estaban en marcha.
            en_marcha["asistente_fuera"] = cerrar_asistente(getattr(b, "_overlay", None))
            b._overlay = None
            en_marcha["telegram"] = detener_bot(getattr(b, "_tg_worker", None))
            b._tg_worker = None
            # Servicios de escritorio (atajos globales, controladores) y su BusEstado.
            cerrar = getattr(b, "cerrar_escritorio", None)
            if callable(cerrar):
                try:
                    cerrar()
                except Exception:
                    pass
        # La bandeja de respaldo (la única ya se quitó con el corte 4, al principio).
        quitar_bandeja(getattr(self, "tray", None))
        self.tray = None
        srv = getattr(self, "_servidor", None)
        if srv is not None:
            try:
                srv.detener()
            except Exception:
                pass
        web = getattr(self, "web", None)
        if web is not None:
            try:
                pagina = web.page()
                pagina.setAudioMuted(True)
                pagina.setWebChannel(None)           # la página ya no llega al puente que se va
            except Exception:
                pass
        self._en_marcha = dict(en_marcha)
        return en_marcha

    @staticmethod
    def _avisar_ordenes_cortadas(b, acc) -> list:
        """«Se detuvo…» a las órdenes de Telegram que se quedarían sin respuesta."""
        try:
            pend = acc.pendientes() if acc is not None else []
        except Exception:
            pend = []
        ids = ordenes_cortadas(getattr(b, "_turno", None), hilo_vivo(getattr(b, "_worker", None)),
                               pend, getattr(b, "_ultima_orden_tg", ""))
        responder = getattr(b, "_responder_telegram", None)
        if not ids or not callable(responder):
            return []
        try:
            from servicios.telegram_worker import AVISO_TG_DETENIDA as texto
        except Exception:
            texto = "Se detuvo la respuesta en el PC."
        for oid in ids:
            try:
                responder(oid, texto)
            except Exception:
                pass
        return ids

    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self._icono, self)
        self.tray.setToolTip("Lune CD")
        menu = QMenu()
        act_abrir = QAction("Abrir Lune", self)
        act_abrir.triggered.connect(self._mostrar)
        act_salir = QAction("Salir", self)
        act_salir.triggered.connect(self._salir_de_verdad)
        menu.addAction(act_abrir)
        menu.addSeparator()
        menu.addAction(act_salir)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._mostrar() if r in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.show()

    # ── VRM de la barra lateral ─────────────────────────────────────────────────
    def _publicar_vrm(self):
        """(Re)publica /vrm/actual.vrm con el modelo que toca y, si cambió algo,
        avisa a la página (recargar el avatar o volver al vídeo)."""
        try:
            config = self.bridge.config
        except AttributeError:
            config = None
        info = publicar_vrm(self._servidor, config)
        try:
            info["render"] = str(config.get("avatar", "render", "animado") or "animado")
        except Exception:
            info["render"] = "animado"
        anterior = self._vrm_info if isinstance(self._vrm_info, dict) else {}
        cambio = info != self._vrm_info
        # Recargar el .vrm solo si cambió el archivo (URL o versión); un cambio de
        # render o de calibración solo se avisa (revisión funcional E #1).
        recargar = (info.get("url"), info.get("v")) != (anterior.get("url"), anterior.get("v"))
        self._vrm_info = dict(info)
        try:
            self.bridge.vrm_barra_info = dict(info)
        except AttributeError:
            pass
        if cambio:
            self._js(js_vrm_barra(info, recargar=recargar))
        return info

    def _vrm_params(self, params_json: str):
        """Calibración del modelo actual (vrm_ajustes, seguir el cursor) → barra lateral."""
        if isinstance(self._vrm_info, dict):
            self._vrm_info["params"] = params_json
            try:
                self.bridge.vrm_barra_info = dict(self._vrm_info)
            except AttributeError:
                pass
        self._js(js_vrm_params(params_json))

    def _js(self, codigo: str):
        web = getattr(self, "web", None)
        if web is None:
            return                                   # la página aún no existe: la pide al cargar
        try:
            web.page().runJavaScript(codigo)
        except Exception:
            pass

    def _mostrar(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    # ── Lune en reposo (11.2): la página sabe si la ventana es la activa ──────────
    def _ventana_activa(self) -> bool:
        try:
            return bool(self.isVisible() and not self.isMinimized() and self.isActiveWindow())
        except RuntimeError:
            return False

    def _avisar_foco(self, forzar: bool = False):
        """window.luneFoco(activa) si cambió (o si `forzar`: la página acaba de cargar). Con
        efectos.pausar_sin_foco la página decide sola cuándo quedarse quieta
        (ui_web/lune_reposo.js); aquí solo se le cuenta."""
        activa = self._ventana_activa()
        if not forzar and activa == getattr(self, "_foco_avisado", None):
            return
        self._foco_avisado = activa
        self._js(js_foco(activa))

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            self._avisar_foco()

    def showEvent(self, ev):
        if getattr(self, "_carga_pendiente", False):
            self._cargar_pagina()                    # carga perezosa: la primera vez que se ve
        super().showEvent(ev)
        self._avisar_foco()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._avisar_foco()

    def salir_de_verdad(self):
        """«Salir»: suelta todo (bot, asistente, IA en curso…) y cierra la app."""
        self._salir = True
        self._liberar_todo(espera_ia_ms=ESPERA_IA_SALIR_MS)
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _salir_de_verdad(self):
        self.salir_de_verdad()

    def closeEvent(self, ev):
        if getattr(self, "_relevada", False):
            ev.accept()                              # cambio de modo: ya soltó todo
            return
        # Cerrar la ventana = ocultarla en la bandeja (features.minimizar_a_bandeja, sí
        # por defecto); solo "Salir" cierra de verdad. El icono está siempre.
        cfg = getattr(getattr(self, "bridge", None), "config", None)
        try:
            minimizar = bool(cfg.feature("minimizar_a_bandeja", True)) if cfg is not None else True
        except Exception:
            minimizar = True
        if not self._salir and minimizar and getattr(self, "tray", None) is not None:
            self.hide()
            if not getattr(self, "_aviso_bandeja", False):
                self._aviso_bandeja = True
                try:
                    self.tray.showMessage("Lune sigue aquí",
                                          "Sigo en segundo plano. Ábreme desde la bandeja.",
                                          self._icono, 4000)
                except Exception:
                    pass
            ev.ignore()
            return
        salir = not self._salir                      # sin bandeja, cerrar es salir
        self._liberar_todo(espera_ia_ms=ESPERA_IA_SALIR_MS)
        ev.accept()
        if salir:
            self._salir = True
            app = QApplication.instance()
            if app is not None:
                app.quit()


def main() -> int:
    # QtWebEngine necesita compartir el contexto OpenGL antes de crear QApplication.
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")
    ventana = VentanaWeb()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
