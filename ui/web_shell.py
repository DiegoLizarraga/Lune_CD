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
"""
from __future__ import annotations

import json
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QDesktopServices, QIcon, QAction

# El servidor http vive en ui/servidor_web.py (sin WebEngine) para que la
# mascota lo comparta; aquí se conservan los nombres antiguos por compatibilidad.
from ui.servidor_web import RAIZ, DIR_WEB, ServidorEstatico as _ServidorEstatico, HandlerSilencioso as _HandlerSilencioso  # noqa: F401

PAGINA = "ui_kits/lune-desktop/index.html"
RUTA_VRM = "/vrm/actual.vrm"          # la misma que RUTA_MODELO de vrm_barra.js
_SIN_MODELO = {"url": "", "v": "", "archivo": "", "params": ""}


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

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lune CD")
        self.resize(1280, 820)
        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = RAIZ / "assets" / f"lune_icon.{ext}"
            if ruta.exists():
                self._icono = QIcon(str(ruta))
                self.setWindowIcon(self._icono)
                break
        self._salir = False   # True solo cuando el usuario elige "Salir" en la bandeja

        self._servidor = _ServidorEstatico(DIR_WEB)
        if not self._servidor.iniciar():
            raise RuntimeError("No pude servir la UI web (ui_web/).")

        # Puente backend ↔ web
        from ui.web_bridge import LuneBridge
        self.bridge = LuneBridge(config=config, ai_manager=ai_manager,
                                 memoria=memoria, tools=tools, parent=self)
        self._canal = QWebChannel()
        self._canal.registerObject("lune", self.bridge)

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
        asegurar_pagina(self.web, url_pagina)
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # Sonidos de la interfaz (luneSfx: menús, alarmas) que se disparan desde el
        # puente o un temporizador, sin un clic justo antes: Chromium los bloquearía.
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        self.web.page().setWebChannel(self._canal)
        self.web.setUrl(url_pagina)
        self.setCentralWidget(self.web)

        # Quedarse en segundo plano (como Discord): al cerrar, se oculta en la
        # bandeja y sigue viva; se reabre desde la bandeja o relanzando el .vbs.
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self._construir_bandeja()

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

    def _salir_de_verdad(self):
        self._salir = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, ev):
        # Cerrar la ventana = ocultarla en la bandeja; solo "Salir" cierra de verdad.
        if not self._salir and getattr(self, "tray", None) is not None:
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
        self._servidor.detener()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        ev.accept()


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
