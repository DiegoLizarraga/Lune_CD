"""
avatar_overlay.py — Lune como mascota flotante ligera (sprites 2D) sobre el escritorio.

Ventana sin bordes, transparente, siempre encima y arrastrable que muestra los
PNG/MP4 de lune_face y reacciona a las emociones del modelo (<|ACT|>, ver
lune_core/marcadores). Se recorta a la SILUETA del personaje con una máscara por
chroma-key (el fondo oscuro del sprite se vuelve transparente y deja pasar los
clics fuera de la figura). Es la mascota de "bajos recursos": sin Chromium.

El avatar 3D (VRM) vive en ui/companion.py (render="vrm"): mismas llamadas
(set_estado / set_emocion / set_act / set_hablando / set_click_through, señal
`visibilidad`, atributo `cerrado`, dormir / despertar / durmiendo,
recargar_modelo, aplicar_params_vrm, aplicar_tamano), así que quien las use no
distingue una de otra.

Además hay un "modo fantasma" (click-through total): la ventana deja pasar TODOS
los clics. En Windows se hace con WS_EX_TRANSPARENT.

Mecánica de ventana portada de la mascota Electron de AIRI a Qt:
    FramelessWindowHint | WindowStaysOnTopHint | Tool  ≈ frameless/always-on-top/panel
    WA_TranslucentBackground                            ≈ transparent, sin sombra
    windowHandle().startSystemMove()                    ≈ arrastre nativo
    setMask(QRegion)                                     ≈ recorte a la silueta

Chat con la mascota (corte 2, igual que la animada/VRM; ui/chat_mascota.py):
doble clic (o la bandeja) → `abrir_chat()`, la cajita EntradaChat bajo ella; lo
escrito va a `on_chat(texto)` (lo pone quien lleva la app) y la respuesta sale en
una burbuja Qt (`burbuja_texto` / `burbuja_fin`). Para distinguir clic, doble
clic y arrastre, el arrastre nativo empieza al mover el ratón unos píxeles con
el botón pulsado (no al pulsar), y el clic simple (una reacción corta) espera el
intervalo de doble clic del sistema y se cancela si llega el segundo clic.

Movimiento (corte 3, ui/sprites_fx.py):
- Balanceo al arrastrar: `FisicaSpriteQt` vigila los Move de la ventana (con el
  arrastre nativo no llegan eventos de ratón; el ángulo sale de la velocidad real
  de la ventana) y pregunta al sondeo del botón izquierdo (servicios/win_entrada,
  sin hooks) si el arrastre sigue. Caras por velocidad (CARA_SPRITE), mareo al
  agitarla (cara mareada 2.5 s + frase) y cara de «soltar».
- Respiración: ±1–2 px (más lenta y honda dormida), solo visible.
- Crítica c.8: el sprite se compone girado/desplazado con `SpriteRotado` en un
  lienzo con margen (la ventana crece ese margen una vez, al crearla) y la
  máscara sale del alfa del fotograma compuesto: girar no recorta la silueta.
- Sin física ni respiración con el vídeo de lune_face a la vista (pensando,
  escribiendo) o con `set_habilitado_fisica(False)` (modo juego).
- Sueño (nucleo/sueno.ReglaSueno) tras avatar.dormir_min sin tocarla ni hablarle:
  cara dormida (lune_sleeping.png o la más cercana), oscurecida y respirando lento.
- Frases de la mascota (lune_core/frases_mascota.py) en la burbuja Qt: arrastre,
  soltar, mareo, dormir, despertar y aparecer, sin pisar una respuesta de la IA.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QSystemTrayIcon, QApplication, QStyle,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QRegion, QImage, QPixmap

from lune_core.frases_mascota import frases_para
from nucleo.sueno import ReglaSueno
from ui.chat_mascota import BurbujaQt, ChatMascota, DesambiguadorClic, ms_lectura
from ui.lune_face import LuneFaceWidget, estado_desde_emocion
from ui.sprites_fx import (
    CARA_SPRITE, PIVOTE, TOPE_GRADOS, FisicaSpriteQt, RespiracionSpriteQt, SpriteRotado,
    margen_lienzo,
)

# Suma R+G+B por debajo de la cual un píxel del sprite se considera "fondo" (negro).
UMBRAL_FONDO = 45

# Caja máxima del sprite en LuneFaceWidget (lo escala a 190×250) y lo que gira y
# respira SpriteRotado (sus valores por defecto): de ahí el margen de la ventana.
CAJA_SPRITE = (190, 250)
GIRO_MAX = TOPE_GRADOS * 1.25
RESP_PX = 2

MS_FRASE = 3500                  # lo que dura una frase de la mascota en la burbuja
MS_MAREO = 2500                  # cara mareada
MS_SOLTAR = 1500                 # cara de «soltar» (happy) al dejarla quieta
REINTENTO_SUENO_MS = 30_000      # la regla no deja dormir ahora: se vuelve a mirar
GRACIA_SUENO_S = 30.0            # «duérmete»: la respuesta no la desvela (ver companion.py)
PAUSA_VOLVER_A_DORMIR_MS = 1500
ATENUAR_DORMIDA = 0.25           # dormida, el sprite un poco más oscuro
MIN_VISIBLE_PX = 60              # al restaurar: trozo de la figura que tiene que verse
# Estados que son una ACTIVIDAD en curso (una emoción vieja cuenta como reposo).
ESTADOS_ACTIVIDAD = frozenset({"thinking", "typing", "working", "talking", "listening"})


def _boton_izquierdo():
    """Sondeo del botón izquierdo (GetAsyncKeyState; sin hooks), o None."""
    try:
        from servicios import win_entrada
        return win_entrada.api_defecto().boton_izquierdo
    except Exception:
        return None


class AvatarOverlay(QMainWindow):
    """Mascota flotante de sprites. `config` persiste su posición y el modo fantasma."""

    visibilidad = pyqtSignal(bool)       # se muestra / se oculta o cierra

    UMBRAL_ARRASTRE = 6                  # px: menos que esto es un CLIC, no arrastre

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.cerrado = False
        self.render = "sprites"
        # Chat con la mascota: on_chat(texto) -> bool lo pone quien lleva la app.
        self.on_chat = None
        self.proveedor_chat = None
        self._chat = ChatMascota(self)
        self._clic = DesambiguadorClic(self._clic_simple, self.abrir_chat, self)
        self._burbuja = None
        self._pulsado = None             # {"origen", "movido"} mientras el botón está abajo
        # La posición se guarda al acabar de moverla (el arrastre nativo no siempre
        # entrega el soltar): medio segundo después del último movimiento.
        self._t_guardar = QTimer(self)
        self._t_guardar.setSingleShot(True)
        self._t_guardar.setInterval(600)
        self._t_guardar.timeout.connect(self._guardar_posicion)

        # Corte 3: sueño, frases, cara y lo que la regla de sueño necesita saber.
        self._bus_estado = None          # nucleo.estado_mascota.BusEstado (opcional)
        self._regla = ReglaSueno.desde_config(config)
        self._frases = frases_para(reloj=time.monotonic)   # del personaje activo
        self._durmiendo = False
        self._hablando = False
        self._arrastrando = False        # la física dice que la están moviendo
        self._cara_arrastre = ""         # tranquila | preocupada | asustada ('' = ninguna)
        self._mareada = False
        self._base = ("normal", None)    # cara pedida (estado, monotonic de vuelta | None)
        self._sueno_pedido_t = None      # monotonic de lo último de un «duérmete» vigente
        self._burbuja_ia = False         # la IA está escribiendo en la burbuja…
        self._burbuja_ia_hasta = 0.0     # …y la deja a la vista hasta aquí
        self._burbuja_ultimo = ""
        self._fisica_permitida = True    # False en modo juego (set_habilitado_fisica)
        self._angulo = 0.0               # balanceo (grados de Qt)
        self._dy = 0                     # respiración (px)
        self._sr = None                  # SpriteRotado del sprite actual (None: vídeo/sin imagen)
        self._img_compuesta = None       # último fotograma puesto (evita repintar lo mismo)
        self._region_sprite = None       # su región de clic (coordenadas del fotograma)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool                 # fuera de la barra de tareas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        central = QWidget()
        central.setStyleSheet("background:transparent;")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)

        self.cara = LuneFaceWidget()
        # En el overlay el "escenario" es transparente, sin el marco neón.
        self.cara.setStyleSheet("LuneFaceWidget{background:transparent;border:none;}")
        self.cara.estado_cambiado.connect(self._on_cara_cambiada)
        lay.addWidget(self.cara)

        # Margen para girar y respirar sin salirse (crítica c.8): la cara y la
        # ventana crecen una vez; el sprite queda centrado igual que antes.
        mx, my = margen_lienzo(CAJA_SPRITE[0], CAJA_SPRITE[1], GIRO_MAX, PIVOTE)
        self._margen = (mx, my + RESP_PX)
        self.cara.setFixedSize(self.cara.minimumWidth() + 2 * self._margen[0],
                               self.cara.minimumHeight() + 2 * self._margen[1])
        self.resize(210 + 2 * self._margen[0], 280 + 2 * self._margen[1])
        # La etiqueta «月 EN LÍNEA» flota pegada a la figura (se coloca en
        # _colocar_etiqueta): la imagen usa todo el alto de la cara, así el lienzo
        # con margen cabe entero (sin recortar pies ni con la letra a 125-200 %) y el
        # sprite y el vídeo quedan centrados en el mismo sitio.
        self.cara.etiqueta_flotante()

        # Física (balanceo, caras por velocidad, mareo) y respiración.
        boton = _boton_izquierdo()
        self._fx = FisicaSpriteQt(self, boton=boton) if boton else FisicaSpriteQt(self)
        self._fx.angulo.connect(self._on_angulo)
        self._fx.movimiento.connect(self._on_movimiento)
        self._fx.cara.connect(self._on_cara_fisica)
        self._fx.mareo.connect(self._on_mareo)
        self._resp = RespiracionSpriteQt(self)
        self._resp.dy.connect(self._on_respiracion)

        self._timer_sueno = QTimer(self)
        self._timer_sueno.setSingleShot(True)
        self._timer_sueno.timeout.connect(self._sueno_vencido)
        self._timer_sueno_pedido = QTimer(self)
        self._timer_sueno_pedido.setSingleShot(True)
        self._timer_sueno_pedido.timeout.connect(self._volver_a_dormir)
        self._timer_mareo = QTimer(self)
        self._timer_mareo.setSingleShot(True)
        self._timer_mareo.timeout.connect(self._fin_mareo)

        self._restaurar_posicion()
        self._fx.vigilar(self)                   # tras colocarla: sin balanceo de arranque
        self._construir_bandeja()

        self._arrastrando_desde = None
        self._click_through = False
        self._on_cara_cambiada()                 # compone la cara inicial
        # Aplicar el modo fantasma inicial (config) una vez mostrada la ventana.
        if self.config and self.config.get("avatar", "click_through", False):
            QTimer.singleShot(300, self._fantasma_guardado)

    def _fantasma_guardado(self):
        """Modo fantasma guardado en config, ya con la ventana creada (método, no
        lambda: si la ventana ya no existe, Qt no lo llama)."""
        if not self.cerrado:
            self.set_click_through(True)

    # ── Estado compartido (BusEstado opcional) ─────────────────────────────────
    def set_bus_estado(self, bus):
        """Engancha (o suelta, con None) el BusEstado de ServiciosEscritorio."""
        self._bus_estado = bus
        self._estado_bus(render=self.render, visible=self.isVisible() and not self.cerrado,
                         durmiendo=self._durmiendo, arrastrando=self._arrastrando,
                         hablando=self._hablando)

    def _estado_bus(self, **campos):
        bus = self._bus_estado
        if bus is None:
            return
        try:
            bus.actualizar(**campos)
        except Exception:
            pass

    # ── Emoción ────────────────────────────────────────────────────────────────
    def set_emocion(self, emocion: str, ms: int = 6000):
        """Recibe una emoción canónica (<|ACT|>) y la muestra."""
        self._poner_cara(estado_desde_emocion(emocion), ms)

    def set_estado(self, estado: str, ms: int = 0):
        """Recibe un estado directo de lune_face (thinking, typing…)."""
        self._poner_cara(estado, ms)

    def set_act(self, act: dict, ms: int = 6000):
        """Recibe el ACT completo {emotion, intensity, motion} del modelo."""
        if not isinstance(act, dict):
            return
        self._poner_cara(estado_desde_emocion(str(act.get("emotion", "neutral"))), ms)

    def _poner_cara(self, estado: str, ms: int = 0):
        """La cara que pide la app (IA, estados). La despierta; si la están
        arrastrando o está mareada, se verá al acabar (esas caras mandan)."""
        estado = str(estado or "normal")
        if estado == "sleeping":
            self._dormir()
            return
        ms = max(0, int(ms or 0))
        self._base = (estado, time.monotonic() + ms / 1000.0 if ms > 0 else None)
        dormia = self._durmiendo
        self._despertar()                        # también rearma el sueño
        if not dormia and not (self._arrastrando or self._mareada):
            self.cara.set_state(estado, auto_revert_ms=ms)

    def _restaurar_cara(self, soltar: bool = False):
        """Vuelve a la cara de fondo tras arrastre, mareo o sueño (con lo que le
        quede de su vuelta a normal). `soltar`: en reposo, la de «soltar» un momento."""
        if self._durmiendo:
            self.cara.set_state("sleeping")
            return
        estado, fin = self._base
        ahora = time.monotonic()
        if fin is not None and ahora >= fin:
            estado, fin = "normal", None
            self._base = (estado, None)
        if soltar and estado == "normal":
            self.cara.set_state(CARA_SPRITE["soltar"], auto_revert_ms=MS_SOLTAR)
            return
        ms = max(1, int((fin - ahora) * 1000)) if fin is not None else 0
        self.cara.set_state(estado, auto_revert_ms=ms)

    def set_hablando(self, hablando: bool):
        """Los sprites no tienen boca animada; cuenta para el sueño (no se duerme
        hablando y la voz la despierta). Llega también oculta: si no, al ocultarla
        mientras habla se quedaría «hablando» para siempre."""
        hablando = bool(hablando)
        pedido = self._sueno_pedido_vigente()        # antes de apuntar que calló (ver companion)
        self._hablando = hablando
        if hablando:
            self._despertar()
        else:
            if pedido:
                self._sueno_pedido_t = time.monotonic()
                self._timer_sueno_pedido.start(PAUSA_VOLVER_A_DORMIR_MS)
            self._rearmar_sueno()
        self._estado_bus(hablando=self._hablando)

    # ── Máscara de silueta ─────────────────────────────────────────────────────
    def _actualizar_mascara(self, *args):
        """Recorta la ventana a la silueta del personaje (deja pasar clics fuera)."""
        if self.cara is None:
            return
        self._colocar_etiqueta()
        region = QRegion()
        # La etiqueta de estado (caja opaca, pegada a la figura) sigue clicable/arrastrable.
        tag = getattr(self.cara, "state_tag", None)
        if tag is not None and tag.isVisible():
            p = tag.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), tag.width(), tag.height()))
        # Silueta del sprite: la del fotograma compuesto (girado/respirando) o, sin
        # él, por chroma-key sobre el pixmap del estado. En el mismo sitio donde Qt
        # lo pinta (QStyle.alignedRect, como QLabel) y solo lo que cabe en la etiqueta.
        lbl = getattr(self.cara, "image_label", None)
        pm = getattr(self.cara, "_pixmap_actual", None)
        if lbl is not None and lbl.isVisible():
            mostrado = lbl.pixmap()
            if self._region_sprite is not None and mostrado is not None and not mostrado.isNull():
                r = self._rect_pintado(lbl, mostrado)
                region = region.united(self._region_sprite.translated(r.x(), r.y())
                                       .intersected(self._rect_etiqueta(lbl)))
            elif pm is not None and not pm.isNull():
                r = self._rect_pintado(lbl, pm)
                region = region.united(self._region_silueta(pm).translated(r.x(), r.y())
                                       .intersected(self._rect_etiqueta(lbl)))
        # Vídeo (thinking/typing): no se puede enmascarar por frame → rect completo.
        vw = getattr(self.cara, "video_widget", None)
        if vw is not None and vw.isVisible():
            p = vw.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), vw.width(), vw.height()))
        fb = getattr(self.cara, "_fallback_label", None)
        if fb is not None and fb.isVisible():
            p = fb.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), fb.width(), fb.height()))

        if region.isEmpty():
            self.clearMask()
        else:
            self.setMask(region)

    def _rect_etiqueta(self, lbl) -> QRect:
        """Rect del contenido de `lbl` en coordenadas de la ventana."""
        cr = lbl.contentsRect()
        return QRect(lbl.mapTo(self, cr.topLeft()), cr.size())

    def _rect_pintado(self, lbl, pm) -> QRect:
        """Dónde pinta QLabel el pixmap `pm` (coordenadas de la ventana): el mismo
        cálculo que Qt (QStyle.alignedRect sobre contentsRect, W/2 - w/2 truncando
        cada mitad y en píxeles independientes del DPI), no (W - w) // 2."""
        dpr = pm.devicePixelRatio() or 1.0
        tam = QSize(round(pm.width() / dpr), round(pm.height() / dpr))
        r = QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, lbl.alignment(), tam, lbl.contentsRect())
        return QRect(lbl.mapTo(self, r.topLeft()), r.size())

    def _rect_figura_en_cara(self):
        """El sprite recto (sin el margen de giro) en coordenadas de la cara, o None
        sin imagen (vídeo, texto de respaldo)."""
        lbl = getattr(self.cara, "image_label", None)
        pm = getattr(self.cara, "_pixmap_actual", None)
        if lbl is None or pm is None or pm.isNull() or lbl.isHidden():
            return None
        dpr = pm.devicePixelRatio() or 1.0
        tam = QSize(round(pm.width() / dpr), round(pm.height() / dpr))
        r = QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, lbl.alignment(), tam, lbl.contentsRect())
        return QRect(lbl.mapTo(self.cara, r.topLeft()), r.size())

    def _colocar_etiqueta(self):
        """«月 EN LÍNEA» justo encima de la esquina superior izquierda de la figura
        (como antes del margen de giro), no en la esquina de la ventana crecida. Con
        vídeo o sin imagen se queda donde estaba."""
        tag = getattr(self.cara, "state_tag", None)
        if tag is None or not getattr(self.cara, "_tag_flotante", False):
            return
        fig = self._rect_figura_en_cara()
        if fig is None:
            return
        tag.adjustSize()
        x = max(0, min(fig.left() - 2, self.cara.width() - tag.width()))
        y = max(0, fig.top() - tag.height() - 2)
        if (tag.x(), tag.y()) != (x, y):
            tag.move(x, y)
        tag.raise_()

    def _region_silueta(self, pixmap) -> QRegion:
        """QRegion del personaje: fondo oscuro fuera, con relleno por filas."""
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, h = img.width(), img.height()
        try:
            import numpy as np
            ptr = img.constBits()
            ptr.setsize(h * img.bytesPerLine())
            arr = np.frombuffer(ptr, np.uint8).reshape((h, img.bytesPerLine() // 4, 4))[:, :w, :]
            # ARGB32 en little-endian se guarda como BGRA.
            lum = arr[:, :, 0].astype(np.int16) + arr[:, :, 1] + arr[:, :, 2]
            fg = lum >= UMBRAL_FONDO
            region = QRegion()
            for y in range(h):
                cols = np.nonzero(fg[y])[0]
                if cols.size:
                    x0, x1 = int(cols[0]), int(cols[-1])
                    region = region.united(QRegion(x0, y, x1 - x0 + 1, 1))
            return region if not region.isEmpty() else QRegion(0, 0, w, h)
        except Exception:
            return QRegion(0, 0, w, h)

    # ── Sprite compuesto: giro, respiración y atenuado (crítica c.8) ───────────
    def _on_cara_cambiada(self, *args):
        """Cambió la cara: nuevo SpriteRotado (o ninguno si es vídeo o no hay imagen)."""
        self._sr = None
        self._img_compuesta = None
        self._region_sprite = None
        pm = getattr(self.cara, "_pixmap_actual", None)
        if pm is not None and not pm.isNull() and not self.cara.image_label.isHidden():
            try:
                self._sr = SpriteRotado(pm.toImage())
            except Exception:
                self._sr = None
        self._actualizar_fisica()
        self._componer()

    def _componer(self):
        """Pone el fotograma (ángulo, respiración, dormida) y su máscara."""
        sr = self._sr
        if sr is None:
            self._actualizar_mascara()
            return
        try:
            img, region = sr.componer(self._angulo, self._dy, False,
                                      ATENUAR_DORMIDA if self._durmiendo else 0.0)
        except Exception:
            self._sr = None
            self._actualizar_mascara()
            return
        if img is self._img_compuesta:
            return                                   # mismo fotograma (caché de SpriteRotado)
        self._img_compuesta = img
        self._region_sprite = region
        self.cara.set_pixmap_compuesto(QPixmap.fromImage(img))
        self._actualizar_mascara()

    def _on_angulo(self, grados: float):
        self._angulo = float(grados)
        if self._sr is not None:
            self._componer()

    def _on_respiracion(self, dy: int):
        self._dy = int(dy)
        if self._sr is not None:
            self._componer()

    def _actualizar_fisica(self):
        """Física solo si está permitida y no hay vídeo de lune_face a la vista."""
        video = False
        try:
            video = bool(self.cara.video_activo())
        except Exception:
            video = False
        self._fx.set_habilitado(self._fisica_permitida and not video)

    def set_habilitado_fisica(self, on: bool):
        """Modo juego (o ajuste): False = quieta y recta, sin balanceo ni respiración."""
        self._fisica_permitida = bool(on)
        self._actualizar_fisica()
        if self._fisica_permitida and self.isVisible() and not self.cerrado:
            self._resp.iniciar()
        elif not self._fisica_permitida:
            self._resp.detener()

    # ── Física: arrastre, caras por velocidad y mareo ──────────────────────────
    def _on_movimiento(self, on: bool):
        if on:
            self._arrastrando = True
            self._despertar(usuario=True)
            self._estado_bus(arrastrando=True)
            self._frase("arrastre")
            return
        self._arrastrando = False
        self._cara_arrastre = ""
        self._estado_bus(arrastrando=False)
        self._frase("soltar")
        if not self._mareada:
            self._restaurar_cara(soltar=True)
        self._rearmar_sueno()

    def _on_cara_fisica(self, cara: str):
        self._cara_arrastre = str(cara or "")
        if self._cara_arrastre and self._arrastrando and not self._mareada:
            self.cara.set_state(CARA_SPRITE.get(self._cara_arrastre, "normal"))

    def _on_mareo(self):
        """La agitaron: cara mareada MS_MAREO y su frase."""
        self._mareada = True
        self._despertar(usuario=True)
        self.cara.set_state(CARA_SPRITE["mareada"])
        self._timer_mareo.start(MS_MAREO)
        self._frase("mareo")

    def _fin_mareo(self):
        self._mareada = False
        if self._arrastrando and self._cara_arrastre:
            self.cara.set_state(CARA_SPRITE.get(self._cara_arrastre, "normal"))
        else:
            self._restaurar_cara()

    # ── Frases de la mascota (lune_core/frases_mascota.py) ─────────────────────
    def _burbuja_qt(self) -> BurbujaQt:
        if self._burbuja is None:
            self._burbuja = BurbujaQt(self)
        return self._burbuja

    def _burbuja_ocupada(self) -> bool:
        """¿La burbuja es de la IA ahora (respuesta en curso o a la vista)?"""
        return self._burbuja_ia or time.monotonic() < self._burbuja_ia_hasta

    def _frase(self, evento: str):
        """Tira el dado de `evento` y, si toca, la frase sale en la burbuja. No pisa
        una respuesta de la IA (y entonces ni tira el dado ni gasta el cooldown)."""
        if self.cerrado or not self.isVisible() or self._burbuja_ocupada():
            return None
        try:
            t = self._frases.elegir(evento)
        except Exception:
            return None
        if t:
            b = self._burbuja_qt()
            b.texto(t)
            b.fin(MS_FRASE)
        return t

    def _actualizar_frases(self):
        try:
            from nucleo import personajes
            self._frases.set_personaje(personajes.get_activo())
        except Exception:
            pass

    def recargar_modelo(self):
        """El personaje activo cambió: sus frases (los sprites no tienen modelo 3D)."""
        self._actualizar_frases()

    def aplicar_params_vrm(self):
        """Solo la mascota VRM tiene calibración por modelo: aquí no hace nada."""

    def aplicar_tamano(self, nombre: str):
        """Tamaños de la mascota 3D (herramienta mascota_tamano): los sprites no cambian."""

    def aplicar_opciones(self):
        """Ajustes cambiaron (avatar.dormir_min): rearma el sueño."""
        if not self._durmiendo:
            self._rearmar_sueno()

    # ── Sueño (nucleo/sueno.ReglaSueno) ────────────────────────────────────────
    @property
    def durmiendo(self) -> bool:
        """¿Está dormida? (lo consultan nucleo/sueno.herramienta_dormir/despertar)."""
        return self._durmiendo

    def dormir(self) -> bool:
        """Que se duerma YA (herramienta mascota_dormir). True si se durmió o ya
        dormía; False si ahora no puede (cerrada, arrastrándola, en llamada…). Si la
        voz está sonando se duerme al callar (y devuelve True)."""
        if self.cerrado:
            return False
        if self._durmiendo:
            self._sueno_pedido_t = time.monotonic()
            return True
        if self._motivo_no_dormir(forzado=True):
            return False
        self._sueno_pedido_t = time.monotonic()
        if self._hablando:
            return True
        self._dormir()
        return self._durmiendo

    def despertar(self) -> bool:
        """Que se despierte (herramienta mascota_despertar). True si está despierta."""
        if self.cerrado:
            return False
        self._despertar(usuario=True)
        return not self._durmiendo

    def _sueno_pedido_vigente(self) -> bool:
        """¿Hay un «duérmete» pendiente? No caduca mientras la voz suena."""
        t = self._sueno_pedido_t
        if t is None:
            return False
        return self._hablando or time.monotonic() - t < GRACIA_SUENO_S

    def _estado_regla(self, forzado: bool = False):
        """Lo que mira la ReglaSueno (ver CompanionFlotante._estado_regla)."""
        visual = self._base[0] if self._base[0] in ESTADOS_ACTIVIDAD else "normal"
        if forzado:
            visual = "normal"
        bus = self._bus_estado
        if bus is None:
            return visual
        try:
            est = dataclasses.asdict(bus.actual())
        except Exception:
            return visual
        est["emocion"] = "neutral" if visual == "normal" else visual
        est["durmiendo"] = False
        if forzado:
            est["hablando"] = False
        return est

    def _motivo_no_dormir(self, forzado: bool = False) -> str:
        if self.cerrado:
            return "la ventana está cerrada"
        arrastrando = self._arrastrando or bool(self._pulsado and self._pulsado.get("movido"))
        return self._regla.motivo_no(self._estado_regla(forzado), arrastrando=arrastrando,
                                     hablando=self._hablando and not forzado)

    def _rearmar_sueno(self, ms=None):
        """(Re)cuenta la inactividad desde ahora (avatar.dormir_min; 0 = nunca)."""
        self._timer_sueno.stop()
        self._regla = ReglaSueno.desde_config(self.config)
        if self.cerrado or self._durmiendo or not self.isVisible() or not self._regla.activa:
            return
        self._timer_sueno.start(int(ms) if ms is not None else int(self._regla.umbral_s * 1000))

    def _sueno_vencido(self):
        if self._durmiendo or self.cerrado or not self.isVisible():
            return
        if self._motivo_no_dormir():
            self._rearmar_sueno(REINTENTO_SUENO_MS)
            return
        self._dormir()

    def _volver_a_dormir(self):
        """Tras la respuesta a un «duérmete» (voz, emociones), vuelve a dormirse."""
        if not self._sueno_pedido_vigente():
            self._sueno_pedido_t = None
            return
        if self._durmiendo or self._hablando:
            return
        if self._motivo_no_dormir(forzado=True):
            self._sueno_pedido_t = None
            return
        self._dormir()

    def _dormir(self):
        if self._durmiendo or self.cerrado:
            return
        self._durmiendo = True
        self._timer_sueno.stop()
        self._resp.set_dormida(True)
        self._estado_bus(durmiendo=True)
        if not (self._arrastrando or self._mareada):
            self.cara.set_state("sleeping")
        self._componer()                             # oscurecida
        self._frase("dormir")

    def _despertar(self, usuario: bool = False):
        """Despierta (si dormía) y rearma el sueño. `usuario` (la toca, la arrastra,
        le escribe) olvida un «duérmete» pendiente; la IA (voz, emoción) con uno
        vigente la vuelve a dormir al acabar."""
        if usuario:
            self._sueno_pedido_t = None
            self._timer_sueno_pedido.stop()
        elif self._sueno_pedido_vigente():
            self._sueno_pedido_t = time.monotonic()
            self._timer_sueno_pedido.start(PAUSA_VOLVER_A_DORMIR_MS)
        if self._durmiendo:
            self._durmiendo = False
            self._resp.set_dormida(False)
            self._estado_bus(durmiendo=False)
            if not (self._arrastrando or self._mareada):
                self._restaurar_cara()
            self._componer()
            if not self._sueno_pedido_vigente():
                self._frase("despertar")
        self._rearmar_sueno()

    # ── Ciclo de vida ──────────────────────────────────────────────────────────
    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._actualizar_mascara)
        self.visibilidad.emit(True)
        self._estado_bus(visible=True)
        if self._fisica_permitida:
            self._resp.iniciar()
        self._despertar(usuario=True)
        self._frase("aparecer")

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._clic.cancelar()
        self._chat.cerrar()
        self._resp.detener()
        self._fx.detener()
        self._timer_sueno.stop()
        if self._burbuja is not None:
            self._burbuja.hide()
        self._burbuja_ia = False                     # lo que escribía la IA ya no se ve
        # Oculta no recibe caras del chat: una actividad a medias (escribiendo…) se
        # quedaría puesta al volver (y con ella el vídeo y sin dormirse nunca).
        if self._base[0] in ESTADOS_ACTIVIDAD and not self.cerrado:
            self._base = ("normal", None)
            if not (self._durmiendo or self._arrastrando or self._mareada):
                self.cara.set_state("normal")
        self.visibilidad.emit(False)
        self._estado_bus(visible=False)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._actualizar_mascara()

    # ── Modo fantasma (click-through total) ──────────────────────────────────────
    def set_click_through(self, activo: bool):
        self._click_through = bool(activo)
        if sys.platform == "win32":
            try:
                import win32gui, win32con
                hwnd = int(self.winId())
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if activo:
                    ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                else:
                    ex &= ~win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            except Exception:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)
        if self.config:
            self.config.set("avatar", "click_through", self._click_through)

    def _alternar_fantasma(self, checked):
        self.set_click_through(checked)

    # ── Clic, doble clic y arrastre (nativo) ───────────────────────────────────
    # El arrastre nativo del SO (startSystemMove) se come el «soltar», así que no
    # empieza al pulsar sino al pasar el umbral: sin moverse, pulsar y soltar es un
    # CLIC (reacción corta, tras el intervalo de doble clic) y dos seguidos, el chat.
    # El balanceo no depende de estos eventos: FisicaSpriteQt mira los Move.
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self._click_through:
            self._clic.cancelar()             # pulsar de nuevo: el clic anterior no cuenta solo
            self._pulsado = {"origen": ev.globalPosition().toPoint(), "movido": False}
            self._despertar(usuario=True)     # tocarla la despierta y rearma el sueño
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        p = self._pulsado
        if p is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            pos = ev.globalPosition().toPoint()
            if not p["movido"]:
                delta = pos - p["origen"]
                if abs(delta.x()) > self.UMBRAL_ARRASTRE or abs(delta.y()) > self.UMBRAL_ARRASTRE:
                    p["movido"] = True
                    self._clic.cancelar()
                    self._empezar_arrastre(pos, delta)
            elif self._arrastrando_desde is not None:
                # Respaldo por si startSystemMove no está disponible.
                self.move(pos - self._arrastrando_desde)
        super().mouseMoveEvent(ev)

    def _empezar_arrastre(self, pos, delta):
        self.move(self.pos() + delta)         # lo que ya se movió antes del umbral
        wh = self.windowHandle()
        if wh is not None and hasattr(wh, "startSystemMove"):
            try:
                if wh.startSystemMove():      # arrastre nativo del SO (Qt ≥ 5.15)
                    self._arrastrando_desde = None
                    return
            except Exception:
                pass
        self._arrastrando_desde = pos - self.frameGeometry().topLeft()

    def mouseReleaseEvent(self, ev):
        p, self._pulsado = self._pulsado, None
        self._arrastrando_desde = None
        if p is not None and ev.button() == Qt.MouseButton.LeftButton:
            if p["movido"]:
                self._guardar_posicion()
            else:
                self._clic.clic()             # ¿clic simple o el primero de un doble clic?
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self._click_through:
            self._pulsado = None
            self._arrastrando_desde = None
            self._clic.doble_clic()           # cancela el clic simple y abre el chat
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def moveEvent(self, ev):
        super().moveEvent(ev)
        if self.isVisible():
            self._t_guardar.start()
            if self._burbuja is not None and self._burbuja.isVisible():
                self._burbuja._colocar()      # la burbuja la sigue

    def _clic_simple(self):
        """Clic limpio: una reacción corta, solo si está tranquila (no pisa una emoción)."""
        if self.cerrado or not self.isVisible() or self.cara is None:
            return
        if getattr(self.cara, "_current_state", "normal") == "normal":
            self.cara.set_state("happy", auto_revert_ms=1500)

    # ── Chat con la mascota ────────────────────────────────────────────────────
    def abrir_chat(self):
        """Doble clic / bandeja: la cajita para escribirle, anclada bajo la mascota."""
        if self.cerrado:
            return
        self._clic.cancelar()
        self._despertar(usuario=True)
        self._chat.abrir()

    def burbuja_texto(self, texto: str, tipeado: bool = False):
        """La respuesta del chat en una burbuja sobre la mascota (texto plano)."""
        t = str(texto or "").strip()
        if self.cerrado or not t or not self.isVisible():
            return                                   # oculta: la burbuja no reaparece sola
        self._despertar()
        self._burbuja_ia, self._burbuja_ultimo = True, t   # las frases de la mascota esperan
        self._burbuja_qt().texto(texto)

    def burbuja_fin(self, ms: int | None = None):
        """La burbuja se oculta a los `ms` (sin ms: el tiempo de lectura)."""
        if self._burbuja is not None:
            self._burbuja.fin(ms)
        if self._burbuja_ia:
            vista = ms_lectura(self._burbuja_ultimo) if ms is None else max(0, int(ms))
            self._burbuja_ia = False
            self._burbuja_ia_hasta = max(self._burbuja_ia_hasta, time.monotonic() + vista / 1000.0)

    # ── Posición persistida ────────────────────────────────────────────────────
    def _mover_por_codigo(self, x: int, y: int):
        """Colocarla sin arrastre (restaurar, esquina): sin balanceo."""
        self.move(x, y)
        fx = getattr(self, "_fx", None)
        if fx is not None:
            fx.saltar(x, y)

    # overlay_x/overlay_y guardan la posición LÓGICA: la de la ventana sin el margen
    # de giro (= la ventana de antes del corte 3). Así una posición guardada por la
    # 10.2 cae en el mismo sitio (sin el salto de +30/+15) y el margen puede cambiar.
    def _restaurar_posicion(self):
        if not self.config:
            self._esquina_inferior_derecha()
            return
        x = self.config.get("avatar", "overlay_x", None)
        y = self.config.get("avatar", "overlay_y", None)
        if isinstance(x, int) and isinstance(y, int):
            wx, wy = x - self._margen[0], y - self._margen[1]
            if self._dentro_de_pantalla(wx, wy):
                self._mover_por_codigo(wx, wy)
                return
        self._esquina_inferior_derecha()

    def _guardar_posicion(self):
        if self.config:
            self.config.set("avatar", "overlay_x", self.x() + self._margen[0])
            self.config.set("avatar", "overlay_y", self.y() + self._margen[1])

    def _rect_figura(self, x: int, y: int) -> QRect:
        """La zona de la figura (la ventana sin el margen de giro) con la ventana en (x, y)."""
        mx, my = self._margen
        return QRect(x + mx, y + my, max(1, self.width() - 2 * mx), max(1, self.height() - 2 * my))

    def _dentro_de_pantalla(self, x, y) -> bool:
        """¿Con la ventana en (x, y) se ve un buen trozo de la figura (60×60 px) en
        algún monitor? Cuenta la figura, no la esquina de la ventana (transparente):
        con la cabeza en el borde de arriba o la figura en el izquierdo también vale."""
        fig = self._rect_figura(x, y)
        for s in QApplication.screens():
            inter = s.availableGeometry().intersected(fig)
            if inter.width() >= MIN_VISIBLE_PX and inter.height() >= MIN_VISIBLE_PX:
                return True
        return False

    def _esquina_inferior_derecha(self):
        """La figura (no la ventana con su margen) a 24 px de la esquina, como antes."""
        pantalla = self.screen() or QApplication.primaryScreen()
        if pantalla:
            g = pantalla.availableGeometry()
            mx, my = self._margen
            self._mover_por_codigo(g.right() - self.width() + mx - 24,
                                   g.bottom() - self.height() + my - 24)

    # ── Bandeja ────────────────────────────────────────────────────────────────
    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        icono = QIcon()
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "lune_icon.png")
        if os.path.exists(ruta):
            icono = QIcon(ruta)
        self.tray = QSystemTrayIcon(icono, self)
        self.tray.setToolTip("Lune · mascota")
        menu = QMenu()
        act_chat = QAction("Escribirle a Lune…", self)
        act_chat.triggered.connect(self.abrir_chat)
        menu.addAction(act_chat)
        act_mostrar = QAction("Mostrar / ocultar", self)
        act_mostrar.triggered.connect(self._alternar)
        act_centrar = QAction("Llevar a la esquina", self)
        act_centrar.triggered.connect(lambda: (self._esquina_inferior_derecha(), self._guardar_posicion()))
        self.act_fantasma = QAction("Modo fantasma (dejar pasar clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.setChecked(bool(self.config and self.config.get("avatar", "click_through", False)))
        self.act_fantasma.toggled.connect(self._alternar_fantasma)
        act_cerrar = QAction("Cerrar mascota", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_mostrar); menu.addAction(act_centrar)
        menu.addAction(self.act_fantasma)
        menu.addSeparator(); menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._alternar() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _alternar(self):
        self.hide() if self.isVisible() else (self.showNormal(), self.raise_())

    def closeEvent(self, ev):
        self.cerrado = True
        self._clic.cancelar()
        self._t_guardar.stop()
        self._timer_sueno.stop(); self._timer_sueno_pedido.stop(); self._timer_mareo.stop()
        self._resp.detener()
        self._fx.detener()
        self._fx.dejar()
        self._guardar_posicion()
        self._chat.destruir()
        if self._burbuja is not None:
            b, self._burbuja = self._burbuja, None
            try:
                b.close(); b.deleteLater()
            except RuntimeError:
                pass
        self._estado_bus(visible=False, arrastrando=False, hablando=False)
        if getattr(self, "tray", None):
            self.tray.hide()
        if self.cara is not None and getattr(self.cara, "_player", None):
            self.cara._player.stop()
        ev.accept()
