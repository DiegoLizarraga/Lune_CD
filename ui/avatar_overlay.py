"""
avatar_overlay.py — Lune como asistente flotante ligera (sprites 2D) sobre el escritorio.

Ventana sin bordes, transparente, siempre encima y arrastrable que muestra los
PNG/MP4 de lune_face y reacciona a las emociones del modelo (<|ACT|>, ver
lune_core/marcadores). Se recorta a la SILUETA del personaje con una máscara por
chroma-key (el fondo oscuro del sprite se vuelve transparente y deja pasar los
clics fuera de la figura). Es la asistente de "bajos recursos": sin Chromium.

El avatar 3D (VRM) vive en ui/companion.py (render="vrm"): mismas llamadas
(set_estado / set_emocion / set_act / set_hablando / set_click_through, señal
`visibilidad`, atributo `cerrado`, dormir / despertar / durmiendo,
recargar_modelo, aplicar_params_vrm, aplicar_tamano), así que quien las use no
distingue una de otra.

Además hay un "modo fantasma" (click-through total): la ventana deja pasar TODOS
los clics. En Windows se hace con WS_EX_TRANSPARENT.

Mecánica de ventana portada del avatar flotante Electron de AIRI a Qt:
    FramelessWindowHint | WindowStaysOnTopHint | Tool  ≈ frameless/always-on-top/panel
    WA_TranslucentBackground                            ≈ transparent, sin sombra
    windowHandle().startSystemMove()                    ≈ arrastre nativo
    setMask(QRegion)                                     ≈ recorte a la silueta

Chat con la asistente (corte 2, igual que la animada/VRM; ui/chat_asistente.py):
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
- Frases de la asistente (lune_core/frases_asistente.py) en la burbuja Qt: arrastre,
  soltar, mareo, dormir, despertar y aparecer, sin pisar una respuesta de la IA.

Corte 4 (el mismo contrato que ui/companion.py): `bandeja=False` y
`quitar_bandeja()`; clic derecho al soltar → `menu_pedido('principal', QPoint)`;
`ancla_menu(cb)` (por geometría: los sprites no tienen luneCabeza);
`set_menu_abierto(on)` (sin arrastre ni sueño); `aplicar_plan_juego(plan|None)`
(ocultar, o sin «siempre encima», y sin física ni respiración); `aplicar_tema`
(tiñe el borde de la burbuja); `set_encima`, `set_fps_max` (se guarda: los
sprites no tienen bucle de render), `set_comentarios_auto` (no comenta la
pantalla: no hace nada), `llevar_a_esquina`, `comentarios_auto`, `click_through`.

Cortes 5 y 6 (lo que aplica del contrato de ui/companion.py):
- `bailar(on, opciones)` / `pulso(bpm, fase, energia)`: baile con la música
  (ui/sprites_baile.BaileSpriteQt): giro de ±4° y saltitos de pocos píxeles al
  pulso, cara feliz, sin respiración mientras baila; el arrastre lo corta y al
  soltarla vuelve. El lienzo tiene margen para los saltitos (LIENZO_DY_PX).
- `mostrar_alarma(texto, retraso_ms)` / `ocultar_alarma()`: burbuja roja
  (#FF4826) a los 3 s, escrita a 35 c/s; mientras suena, el clic no reacciona y
  ni las frases ni el chat la tapan.
- `soporta_grande = False`: la pantalla grande y el salvapantallas de los sprites
  son ui/ventana_reloj.VentanaReloj (decisión D2).

Cortes 7 y 8 (lo que aplica del contrato de ui/companion.py; ui/asiento_qt.ControlAsiento
y ui/comida_qt.ControlComida):
- `arrastre_cambio(bool)`: el arrastre es el NATIVO del SO (startSystemMove), así que sale
  de `nativeEvent` con WM_ENTERSIZEMOVE (True) / WM_EXITSIZEMOVE (False) de SU ventana
  (solo lee el mensaje y devuelve (False, 0): Windows lo procesa igual); con el arrastre
  de respaldo (sin startSystemMove), al pasar el umbral y al soltar. SIN
  `set_arrastre_delegado` (así ControlAsiento sabe que el arrastre es nativo: encaja al
  soltar).
- `antes_de_colocar()`: la emite `llevar_a_esquina()` antes de moverla (como en companion).
- `hwnd()`, `punto_asiento(cb)` SÍNCRONO (asiento = sonda = centro de abajo de la
  figura), `asiento(on, modo, variante, cb=)`: sentada «de pie sobre el borde» (D2): cara
  `sitting` si el pack trae lune_sitting.png (si no, la de siempre), sin balanceo de la
  física (la ventana la mueve ControlAsiento) y con respiración; frases «sentarse» y
  «bajar». Mientras `sentada` no se toca su orden Z salvo `restaurar_orden_z()`.
  Puede dormirse sentada (D5).
- clic CENTRAL soltado sobre ella → `menu_pedido('secundario', QPoint)`.
- `cabeza(cb)` síncrono: la figura (35 % del alto, r = 0.22·ancho) en px lógicos
  globales; `comer(tipo, ms)` → cara happy, frase «comer» y la despierta;
  `set_comida_activa(on)`: sin reacción al clic, sin chat con doble clic y sin sueño.

Cortes 9 y 10 (lo que aplica del contrato de ui/companion.py):
- SIN `mmd`: los sprites no tienen página ni esqueleto. Con un baile de la biblioteca,
  ui/mmd_qt.ControlMMD pone la canción por el Mezclador y usa `bailar`/`pulso` (D1).
- `decir_reaccion(texto, estado, ms)` (ui/minecraft_qt.ControlMinecraft): la reacción a la
  partida en la burbuja nativa con su cara durante `ms`. False (no la dice) cerrada u
  oculta, con una alarma, el menú abierto, arrastrándola o con la IA en la burbuja.
"""
from __future__ import annotations

import ctypes
import dataclasses
import json
import os
import re
import sys
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QSystemTrayIcon, QApplication, QStyle,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QRegion, QImage, QPixmap

from lune_core.frases_asistente import frases_para
from nucleo.sueno import ReglaSueno
from ui.chat_asistente import BurbujaQt, ChatAsistente, DesambiguadorClic, ms_lectura
from ui.lune_face import LuneFaceWidget, estado_desde_emocion, tiene_cara
from ui.sprites_baile import DY_MAX as BAILE_DY_MAX, BaileSpriteQt
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
LIENZO_DY_PX = max(RESP_PX, BAILE_DY_MAX)   # hueco vertical del lienzo: respiración y saltitos del baile

# Alarma (corte 5): burbuja roja como la de Mate-Engine (AvatarBigScreenTimer.cs).
COLOR_ALARMA = "#FF4826"
ALARMA_CPS = 35                  # caracteres por segundo al escribirla
ALARMA_ANCHO_MAX = 600
ALARMA_RETRASO_MS = 3000

MS_FRASE = 3500                  # lo que dura una frase de la asistente en la burbuja
MS_MAREO = 2500                  # cara mareada
MS_SOLTAR = 1500                 # cara de «soltar» (happy) al dejarla quieta
REINTENTO_SUENO_MS = 30_000      # la regla no deja dormir ahora: se vuelve a mirar
GRACIA_SUENO_S = 30.0            # «duérmete»: la respuesta no la desvela (ver companion.py)
PAUSA_VOLVER_A_DORMIR_MS = 1500
ATENUAR_DORMIDA = 0.25           # dormida, el sprite un poco más oscuro
MIN_VISIBLE_PX = 60              # al restaurar: trozo de la figura que tiene que verse
# Estados que son una ACTIVIDAD en curso (una emoción vieja cuenta como reposo).
ESTADOS_ACTIVIDAD = frozenset({"thinking", "typing", "working", "talking", "listening"})
ALTO_CABEZA = 0.35               # ancla del menú radial: la cabeza, al 35 % de la figura
FPS_MIN, FPS_MAX = 15, 144
_RE_HEX = re.compile(r"#[0-9a-fA-F]{6}")

# Cortes 7 y 8: sentarse (arrastre nativo) y comida.
WM_ENTERSIZEMOVE = 0x0231        # empieza el bucle modal de mover (startSystemMove)
WM_EXITSIZEMOVE = 0x0232         # …y acaba al soltar
MODOS_ASIENTO = ("ventana", "barra")
RADIO_CABEZA = 0.22              # radio de la cabeza (comida) = 0.22 · ancho de la figura
MS_COMER = 2500

# Corte 10: reacciones a Minecraft en la burbuja (como ui/companion.py decir_reaccion).
MS_REACCION = 8000
MS_REACCION_MIN, MS_REACCION_MAX = 1500, 20_000
MAX_TEXTO_REACCION = 300


def _offset_mensaje() -> int:
    """Desplazamiento del campo `message` en MSG (8 en 64 bits: detrás del HWND)."""
    try:
        from ctypes import wintypes
        return int(wintypes.MSG.message.offset)
    except Exception:                                # noqa: BLE001
        return ctypes.sizeof(ctypes.c_void_p)


_OFFSET_MSG = _offset_mensaje()


def mensaje_win(mensaje) -> int | None:
    """El `message` (WM_…) de un MSG de Windows en la dirección `mensaje` (nativeEvent)."""
    try:
        direccion = int(mensaje)
    except (TypeError, ValueError):
        return None
    if not direccion:
        return None
    return int(ctypes.c_uint.from_address(direccion + _OFFSET_MSG).value)


def _acento_de(css_json):
    """--cyan-500 del tema (nucleo/tema.css_json) o None (cian de serie). Lanza
    ValueError si no es un JSON de tema."""
    if css_json is None:
        return None
    datos = css_json
    if isinstance(css_json, (str, bytes)):
        try:
            datos = json.loads(css_json)
        except ValueError as e:
            raise ValueError(f"tema no es JSON: {e}") from None
    if datos is None:
        return None
    if not isinstance(datos, dict):
        raise ValueError("el tema tiene que ser un objeto o null")
    v = datos.get("--cyan-500")
    return v if isinstance(v, str) and _RE_HEX.fullmatch(v) else None


def _ventana_nativa() -> bool:
    """¿Las ventanas de Qt son HWND de verdad? (no con QT_QPA_PLATFORM=offscreen)."""
    if sys.platform != "win32":
        return False
    try:
        return QApplication.platformName() == "windows"
    except Exception:
        return False


def _boton_izquierdo():
    """Sondeo del botón izquierdo (GetAsyncKeyState; sin hooks), o None."""
    try:
        from servicios import win_entrada
        return win_entrada.api_defecto().boton_izquierdo
    except Exception:
        return None


class AvatarOverlay(QMainWindow):
    """Asistente flotante de sprites. `config` persiste su posición y el modo fantasma."""

    visibilidad = pyqtSignal(bool)       # se muestra / se oculta o cierra
    menu_pedido = pyqtSignal(str, object)  # ('principal'|'secundario', QPoint global): menú radial
    arrastre_cambio = pyqtSignal(bool)   # cortes 7/8: WM_ENTERSIZEMOVE (True) / WM_EXITSIZEMOVE (False)
    antes_de_colocar = pyqtSignal()      # cortes 7/8: la va a colocar el código (su menú «Llevar a la
                                         # esquina»): quien la tiene sentada la baja antes (montaje_vida)

    UMBRAL_ARRASTRE = 6                  # px: menos que esto es un CLIC, no arrastre

    def __init__(self, config=None, parent=None, bandeja: bool = True):
        super().__init__(parent)
        self.config = config
        self.cerrado = False
        self.render = "sprites"
        # Corte 4: menú radial, modo juego, orden Z y tema.
        self.tray = None
        self.act_fantasma = None
        self._menu_bandeja = None
        self._menu_abierto = False
        self._der_pulsado = False
        self._plan_juego = None
        self._oculta_por_juego = False
        self._juego_mostrada_a_mano = False
        self._mostrando_por_juego = False
        self._fisica_previa = True       # set_habilitado_fisica de antes de la partida
        self._encima = bool(config.get("avatar", "siempre_encima", True)) if config else True
        self._fps_max = self._fps_de_config()
        self._acento_tema = None         # borde de la burbuja (--cyan-500 del tema)
        # Chat con la asistente: on_chat(texto) -> bool lo pone quien lleva la app.
        self.on_chat = None
        self.proveedor_chat = None
        self._chat = ChatAsistente(self)
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
        self._bus_estado = None          # nucleo.estado_asistente.BusEstado (opcional)
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
        # Cortes 5 y 6: baile y alarma.
        self._bailando = False           # ControlBaile pidió bailar (aunque ahora esté oculta)
        self._baile_opciones = {}
        self._baile_cuadro = (0.0, 0)    # (grados, dy) del último cuadro del baile
        self._alarma_texto = None        # texto de la alarma que suena (None: ninguna)
        self._alarma_mostrada = ""       # lo ya escrito en la burbuja
        self._estilo_rojo = False        # la burbuja lleva ahora el estilo de alarma
        # Cortes 7 y 8: sentarse y comida.
        self._sentada = ""               # '' | 'barra' | 'ventana'
        self._asiento_var = 0
        self._arrastre_senal = False     # último arrastre_cambio emitido
        self._comida_activa = False
        self._medio_pulsado = False      # clic central pulsado (menú secundario al soltar)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool                 # fuera de la barra de tareas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Al volver tras el modo juego (o al sacarla) no le roba el foco al juego.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Clic derecho = menú radial (al soltar), sin menú contextual de Qt.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

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
        self._margen = (mx, my + LIENZO_DY_PX)
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
        # Baile (corte 6): cuadros (grados, dy) a 30 Hz solo mientras baila.
        self._baile = BaileSpriteQt(self)
        self._baile.cuadro.connect(self._on_cuadro_baile)
        # Alarma (corte 5): la burbuja roja sale a los retraso_ms y se escribe a 35 c/s.
        self._t_alarma = QTimer(self)
        self._t_alarma.setSingleShot(True)
        self._t_alarma.timeout.connect(self._empezar_alarma)
        self._t_tipeo = QTimer(self)
        self._t_tipeo.setInterval(max(1, round(1000 / ALARMA_CPS)))
        self._t_tipeo.timeout.connect(self._tipear_alarma)

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
        if bandeja:
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
            self.cara.set_state(self._cara_de(estado), auto_revert_ms=ms)

    def _cara_reposo(self) -> str:
        """La cara de reposo: `sitting` sentada si el pack la trae; si no, `normal`."""
        return "sitting" if self._sentada and tiene_cara("sitting") else "normal"

    def _cara_de(self, estado: str) -> str:
        """El estado de la app → la cara (el reposo, sentada, es `sitting`)."""
        return self._cara_reposo() if estado == "normal" else estado

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
        if self._bailando and estado == "normal":
            self.cara.set_state("happy")                 # bailando: cara feliz
            return
        if soltar and estado == "normal":
            self.cara.set_state(CARA_SPRITE["soltar"], auto_revert_ms=MS_SOLTAR)
            return
        ms = max(1, int((fin - ahora) * 1000)) if fin is not None else 0
        self.cara.set_state(self._cara_de(estado), auto_revert_ms=ms)

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
                self._sr = SpriteRotado(pm.toImage(), resp_px=LIENZO_DY_PX)
            except Exception:
                self._sr = None
        self._actualizar_fisica()
        self._componer()

    def _pose(self):
        """(grados, dy) del fotograma: el balanceo más el baile mientras baila (y
        no la arrastran; arrastrándola manda la física), o balanceo y respiración."""
        baile = getattr(self, "_baile", None)
        if baile is not None and baile.activo and not self._arrastrando:
            g, dy = self._baile_cuadro
            return self._angulo + g, dy
        return self._angulo, self._dy

    def _componer(self):
        """Pone el fotograma (ángulo, respiración o baile, dormida) y su máscara."""
        sr = self._sr
        if sr is None:
            self._actualizar_mascara()
            return
        angulo, dy = self._pose()
        try:
            img, region = sr.componer(angulo, dy, False,
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
        """Física solo si está permitida, no hay vídeo de lune_face a la vista y no está
        sentada (sentada, la ventana la mueve ControlAsiento: nada de balanceo)."""
        video = False
        try:
            video = bool(self.cara.video_activo())
        except Exception:
            video = False
        antes = self._fx.habilitado
        on = self._fisica_permitida and not video and not self._sentada
        self._fx.set_habilitado(on)
        if on and not antes:
            self._fx.saltar(self.x(), self.y())      # sin el salto de lo que se movió apagada

    def set_habilitado_fisica(self, on: bool):
        """Modo juego (o ajuste): False = quieta y recta, sin balanceo ni respiración."""
        self._fisica_permitida = bool(on)
        self._actualizar_fisica()
        if self._fisica_permitida and self.isVisible() and not self.cerrado and not self._bailando:
            self._resp.iniciar()
        elif not self._fisica_permitida:
            self._resp.detener()

    # ── Física: arrastre, caras por velocidad y mareo ──────────────────────────
    def _on_movimiento(self, on: bool):
        self._baile.set_arrastre(on)                 # arrastrarla corta el baile; al soltar vuelve
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

    # ── Frases de la asistente (lune_core/frases_asistente.py) ─────────────────────
    def _burbuja_qt(self) -> BurbujaQt:
        if self._burbuja is None:
            self._burbuja = BurbujaQt(self)
            if self._acento_tema:
                self._estilo_burbuja()
        return self._burbuja

    def _estilo_burbuja(self):
        """Borde de la burbuja con el acento del tema (o el de serie); con una
        alarma a la vista, la burbuja roja."""
        b = self._burbuja
        if b is None:
            return
        try:
            from ui.theme import COLORS, FONT_BODY
            self._estilo_rojo = self._alarma_en_burbuja()
            if self._estilo_rojo:
                b.setStyleSheet(
                    f"QLabel{{background:{COLOR_ALARMA};color:#FFFFFF;"
                    f"border:2px solid #FFFFFF;border-radius:12px;padding:10px 14px;"
                    f"font-family:'{FONT_BODY}';font-size:16px;font-weight:bold;}}")
                return
            borde = self._acento_tema or COLORS["accent"]
            b.setStyleSheet(
                f"QLabel{{background:{COLORS['surface']};color:{COLORS['text']};"
                f"border:2px solid {borde};border-radius:10px;padding:8px 10px;"
                f"font-family:'{FONT_BODY}';font-size:12px;}}")
        except Exception:  # noqa: BLE001
            pass

    def _alarma_en_burbuja(self) -> bool:
        return self._alarma_texto is not None and bool(self._alarma_mostrada)

    def _burbuja_ocupada(self) -> bool:
        """¿La burbuja es de la IA ahora (respuesta en curso o a la vista) o de una alarma?"""
        if self._alarma_texto is not None:
            return True
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
        """Solo la asistente VRM tiene calibración por modelo: aquí no hace nada."""

    def aplicar_tamano(self, nombre: str):
        """Tamaños de la asistente 3D (herramienta asistente_tamano): los sprites no cambian."""

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
        """Que se duerma YA (herramienta asistente_dormir). True si se durmió o ya
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
        """Que se despierte (herramienta asistente_despertar). True si está despierta."""
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
        if self._menu_abierto and not forzado:
            return "el menú está abierto"
        if self._alarma_texto is not None:
            return "hay una alarma sonando"
        if self._bailando:
            return "está bailando"
        if self._comida_activa:
            return "está comiendo"
        arrastrando = self._arrastrando or bool(self._pulsado and self._pulsado.get("movido"))
        return self._regla.motivo_no(self._estado_regla(forzado), arrastrando=arrastrando,
                                     hablando=self._hablando and not forzado)

    def _rearmar_sueno(self, ms=None):
        """(Re)cuenta la inactividad desde ahora (avatar.dormir_min; 0 = nunca)."""
        self._timer_sueno.stop()
        self._regla = ReglaSueno.desde_config(self.config)
        if self.cerrado or self._durmiendo or not self.isVisible() or not self._regla.activa:
            return
        if self._comida_activa:
            return                                   # con comida en la mano no se duerme sola
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
        if self._plan_juego is not None and not self._mostrando_por_juego:
            self._juego_mostrada_a_mano = True       # la sacan en plena partida: gana el usuario
            self._oculta_por_juego = False
        QTimer.singleShot(0, self._actualizar_mascara)
        self._aplicar_encima()                       # reafirmar el orden Z al mostrarse
        self.visibilidad.emit(True)
        self._estado_bus(visible=True)
        if self._bailando:
            self._resp.detener()
            self._baile.bailar(True, self._baile_opciones)   # vuelve a bailar donde lo dejó
        elif self._fisica_permitida:
            self._resp.iniciar()
        self._despertar(usuario=True)
        if self._alarma_en_burbuja():
            self._burbuja_alarma(self._alarma_mostrada)
        self._frase("aparecer")

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._clic.cancelar()
        self._chat.cerrar()
        self._resp.detener()
        self._fx.detener()
        self._baile.detener()                        # oculta no baila (sigue pedido: vuelve al mostrarse)
        self._timer_sueno.stop()
        if self._burbuja is not None:
            self._burbuja.hide()
        self._burbuja_ia = False                     # lo que escribía la IA ya no se ve
        # Oculta no recibe caras del chat: una actividad a medias (escribiendo…) se
        # quedaría puesta al volver (y con ella el vídeo y sin dormirse nunca).
        if self._base[0] in ESTADOS_ACTIVIDAD and not self.cerrado:
            self._base = ("normal", None)
            if not (self._durmiendo or self._arrastrando or self._mareada):
                self.cara.set_state(self._cara_reposo())
        self._medio_pulsado = self._der_pulsado = False
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
        act = getattr(self, "act_fantasma", None)
        if act is not None and act.isChecked() != self._click_through:
            act.setChecked(self._click_through)

    @property
    def click_through(self) -> bool:
        """¿Modo fantasma total (deja pasar todos los clics)?"""
        return self._click_through

    def _alternar_fantasma(self, checked):
        self.set_click_through(checked)

    # ── Clic, doble clic y arrastre (nativo) ───────────────────────────────────
    # El arrastre nativo del SO (startSystemMove) se come el «soltar», así que no
    # empieza al pulsar sino al pasar el umbral: sin moverse, pulsar y soltar es un
    # CLIC (reacción corta, tras el intervalo de doble clic) y dos seguidos, el chat.
    # El balanceo no depende de estos eventos: FisicaSpriteQt mira los Move.
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            # Menú radial: se abre al SOLTAR.
            self._der_pulsado = not self._click_through and not self._menu_abierto
        elif ev.button() == Qt.MouseButton.MiddleButton:
            # Menú secundario (comida…): también al soltar.
            self._medio_pulsado = not self._click_through and not self._menu_abierto
        elif ev.button() == Qt.MouseButton.LeftButton and not self._click_through and not self._menu_abierto:
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
                    return                    # arrastre_cambio: WM_ENTERSIZEMOVE/EXITSIZEMOVE (nativeEvent)
            except Exception:
                pass
        self._arrastrando_desde = pos - self.frameGeometry().topLeft()
        self._emitir_arrastre(True)           # arrastre de respaldo (sin bucle modal del SO)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            pulsado, self._der_pulsado = self._der_pulsado, False
            if pulsado:
                self._pedir_menu(ev.globalPosition().toPoint())
            super().mouseReleaseEvent(ev)
            return                            # no toca un arrastre izquierdo en curso
        if ev.button() == Qt.MouseButton.MiddleButton:
            pulsado, self._medio_pulsado = self._medio_pulsado, False
            if pulsado:
                self._pedir_menu(ev.globalPosition().toPoint(), "secundario")
            super().mouseReleaseEvent(ev)
            return
        p, self._pulsado = self._pulsado, None
        respaldo, self._arrastrando_desde = self._arrastrando_desde, None
        if p is not None and ev.button() == Qt.MouseButton.LeftButton:
            if p["movido"]:
                if respaldo is not None:
                    self._emitir_arrastre(False)   # antes de guardar (ControlAsiento encaja aquí)
                self._guardar_posicion()
            else:
                self._clic.clic()             # ¿clic simple o el primero de un doble clic?
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self._click_through and not self._menu_abierto:
            self._pulsado = None
            if self._arrastrando_desde is not None:
                self._arrastrando_desde = None
                self._emitir_arrastre(False)
            if self._comida_activa:
                self._clic.cancelar()         # con comida en la mano, ni chat ni reacción
            else:
                self._clic.doble_clic()       # cancela el clic simple y abre el chat
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def nativeEvent(self, tipo, mensaje):
        """Arrastre nativo (startSystemMove): el bucle modal de Windows avisa con
        WM_ENTERSIZEMOVE / WM_EXITSIZEMOVE a ESTA ventana → arrastre_cambio. Solo se lee
        el mensaje; Windows lo procesa igual (False, 0)."""
        try:
            if bytes(tipo) == b"windows_generic_MSG":
                m = mensaje_win(mensaje)
                if m == WM_ENTERSIZEMOVE:
                    self._emitir_arrastre(True)
                elif m == WM_EXITSIZEMOVE:
                    self._emitir_arrastre(False)
        except Exception:                             # noqa: BLE001 — nunca romper el bucle de mensajes
            pass
        return False, 0

    def moveEvent(self, ev):
        super().moveEvent(ev)
        if self.isVisible():
            self._t_guardar.start()
            if self._burbuja is not None and self._burbuja.isVisible():
                self._burbuja._colocar()      # la burbuja la sigue

    # ── Menú radial (corte 4: ui/menu_radial.ControlMenuRadial) ────────────────
    def _pedir_menu(self, punto: QPoint, tipo: str = "principal"):
        """Clic derecho (principal) o central (secundario: la comida) soltado sobre
        ella → menu_pedido (no arrastrándola, ni en modo fantasma, ni con el menú ya
        abierto)."""
        if self.cerrado or self._click_through or self._menu_abierto:
            return
        if self._arrastrando or (self._pulsado is not None and self._pulsado.get("movido")):
            return
        if not self.frameGeometry().contains(punto):
            return                            # soltó fuera de ella: se arrepintió
        self._clic.cancelar()
        self.menu_pedido.emit(tipo, QPoint(punto))

    def set_menu_abierto(self, on: bool):
        """El menú radial se abre (True) o se cierra: abierto, sin arrastre ni sueño
        (no la despierta: el radial ofrece «Despertar» si duerme)."""
        on = bool(on)
        if on == self._menu_abierto:
            return
        self._menu_abierto = on
        if on:
            self._clic.cancelar()
            self._pulsado = None
            self._arrastrando_desde = None
            self._timer_sueno.stop()
        else:
            self._rearmar_sueno()

    def ancla_menu(self, callback):
        """`callback(QPoint global)` con la cabeza: el 35 % del alto de la ventana sin su
        margen (los sprites no tienen luneCabeza). Se llama en el acto."""
        if not callable(callback):
            return
        fig = self._rect_figura(self.x(), self.y())
        punto = QPoint(fig.x() + fig.width() // 2, fig.y() + round(fig.height() * ALTO_CABEZA))
        try:
            callback(punto)
        except Exception:
            pass

    # ── Modo juego (corte 4: ui/modo_juego_qt.ControlModoJuego) ────────────────
    def aplicar_plan_juego(self, plan):
        """Plan del modo juego o None al acabar. ocultar → se oculta (y vuelve solo
        si la ocultó esto) · fondo → sin «siempre encima» · nada → se queda. En
        partida, quieta: sin física ni respiración. Si el usuario la saca a mano
        durante la partida, gana él."""
        antes = self._plan_juego
        if plan is None:
            if antes is None:
                return
            self._plan_juego = None
            self._juego_mostrada_a_mano = False
            if not self.cerrado:
                self.set_habilitado_fisica(self._fisica_previa)
            volver, self._oculta_por_juego = self._oculta_por_juego, False
            if volver and not self.cerrado and not self.isVisible():
                self._mostrar_por_juego()
            elif self.isVisible() and not self.cerrado:
                self._aplicar_encima()
            return
        self._plan_juego = plan
        if antes is None:
            self._fisica_previa = self._fisica_permitida
            self._oculta_por_juego = False
            self._juego_mostrada_a_mano = False
        if self.cerrado:
            return
        self.set_habilitado_fisica(False)
        if plan.accion == "ocultar":
            if self.isVisible() and not self._juego_mostrada_a_mano:
                self._oculta_por_juego = True
                self.hide()
        else:
            if self._oculta_por_juego and not self.isVisible():
                self._oculta_por_juego = False
                self._mostrar_por_juego()
            elif self.isVisible():
                self._aplicar_encima()

    def _mostrar_por_juego(self):
        self._mostrando_por_juego = True
        try:
            self.show()
        finally:
            self._mostrando_por_juego = False

    # ── Orden Z, FPS, tema y comentarios (corte 4) ─────────────────────────────
    @property
    def siempre_encima(self) -> bool:
        return self._encima

    def set_encima(self, on: bool):
        """Siempre encima (avatar.siempre_encima); se reafirma al mostrarse."""
        on = bool(on)
        self._encima = on
        if self.config and bool(self.config.get("avatar", "siempre_encima", True)) != on:
            self.config.set("avatar", "siempre_encima", on)
        if self.isVisible() and not self.cerrado:
            self._aplicar_encima()

    def _aplicar_encima(self, forzar: bool = False):
        """Siempre encima o no (o sin «siempre encima» en modo juego «fondo»). Sentada,
        el orden Z lo lleva ControlAsiento: no se toca salvo `forzar` (restaurar_orden_z)."""
        if self._sentada and not forzar:
            return
        if not _ventana_nativa():
            return
        try:
            from servicios import win_ventana
            plan = self._plan_juego
            fondo = plan is not None and plan.accion == "fondo" and not self._juego_mostrada_a_mano
            win_ventana.set_encima(int(self.winId()), False if fondo else self._encima)
        except Exception:
            pass

    def _fps_de_config(self) -> int:
        try:
            n = int(self.config.get("avatar", "fps_max", 60)) if self.config else 60
        except (TypeError, ValueError):
            n = 60
        return max(FPS_MIN, min(FPS_MAX, n))

    def set_fps_max(self, n: int):
        """avatar.fps_max: se guarda (lo usa la asistente web, animada o 3D); los sprites no tienen
        bucle de render que limitar."""
        try:
            n = max(FPS_MIN, min(FPS_MAX, int(n)))
        except (TypeError, ValueError):
            return
        self._fps_max = n
        if self.config and self._fps_de_config() != n:
            self.config.set("avatar", "fps_max", n)

    def set_comentarios_auto(self, on: bool):
        """Los sprites no comentan la pantalla: no hace nada."""

    @property
    def comentarios_auto(self) -> bool:
        return False

    def aplicar_tema(self, css_json):
        """Tema de color: el borde de la burbuja con su --cyan-500 (None = de serie).
        Un JSON que no es un tema se ignora."""
        try:
            acento = _acento_de(css_json)
        except ValueError:
            return
        if acento == self._acento_tema:
            return
        self._acento_tema = acento
        self._estilo_burbuja()

    def llevar_a_esquina(self):
        """A la esquina inferior derecha de su monitor (y se guarda la posición). Sentada,
        `antes_de_colocar` deja que la baje quien la sentó (si no, la volvería a clavar)."""
        if self.cerrado:
            return
        self.antes_de_colocar.emit()
        self._esquina_inferior_derecha()
        self._guardar_posicion()

    def _clic_simple(self):
        """Clic limpio: una reacción corta, solo si está tranquila (no pisa una emoción)."""
        if self.cerrado or not self.isVisible() or self.cara is None:
            return
        if self._alarma_texto is not None:
            return                                   # con una alarma sonando el clic la apaga (fuera)
        if self._comida_activa:
            return                                   # con comida en la mano el clic no reacciona
        if getattr(self.cara, "_current_state", "normal") in ("normal", "sitting"):
            self.cara.set_state("happy", auto_revert_ms=1500)

    # ── Chat con la asistente ────────────────────────────────────────────────────
    def abrir_chat(self):
        """Doble clic / bandeja: la cajita para escribirle, anclada bajo la asistente."""
        if self.cerrado:
            return
        self._clic.cancelar()
        self._despertar(usuario=True)
        self._chat.abrir()

    def burbuja_texto(self, texto: str, tipeado: bool = False):
        """La respuesta del chat en una burbuja sobre la asistente (texto plano)."""
        t = str(texto or "").strip()
        if self.cerrado or not t or not self.isVisible():
            return                                   # oculta: la burbuja no reaparece sola
        if self._alarma_texto is not None:
            return                                   # la alarma manda en la burbuja
        self._despertar()
        self._burbuja_ia, self._burbuja_ultimo = True, t   # las frases de la asistente esperan
        self._burbuja_qt().texto(texto)

    def burbuja_fin(self, ms: int | None = None):
        """La burbuja se oculta a los `ms` (sin ms: el tiempo de lectura)."""
        if self._alarma_texto is not None:
            self._burbuja_ia = False                 # no toca la burbuja de la alarma
            return
        if self._burbuja is not None:
            self._burbuja.fin(ms)
        if self._burbuja_ia:
            vista = ms_lectura(self._burbuja_ultimo) if ms is None else max(0, int(ms))
            self._burbuja_ia = False
            self._burbuja_ia_hasta = max(self._burbuja_ia_hasta, time.monotonic() + vista / 1000.0)

    # ── Minecraft (corte 10: ui/minecraft_qt.ControlMinecraft) ─────────────────
    def decir_reaccion(self, texto: str, estado: str = "happy", ms: int = MS_REACCION) -> bool:
        """La reacción a la partida en la burbuja nativa, con la cara de `estado` durante
        `ms`. False si no la dice: cerrada u oculta, con una alarma, el menú abierto,
        arrastrándola o con algo de la IA en la burbuja (esa burbuja manda)."""
        t = " ".join(str(texto or "").split())[:MAX_TEXTO_REACCION]
        if not t or self.cerrado or not self.isVisible():
            return False
        if self._burbuja_ocupada():                  # respuesta de la IA o alarma
            return False
        if self._menu_abierto or self._arrastrando or bool(self._pulsado and self._pulsado.get("movido")):
            return False
        try:
            n = int(float(ms))
        except (TypeError, ValueError):
            n = MS_REACCION
        n = max(MS_REACCION_MIN, min(MS_REACCION_MAX, n))
        self._poner_cara(estado_desde_emocion(str(estado or "neutral")), n)
        b = self._burbuja_qt()
        b.texto(t)
        b.fin(n)
        return True

    # ── Baile (corte 6: ui/baile_qt.ControlBaile) ──────────────────────────────
    @property
    def soporta_grande(self) -> bool:
        """Los sprites no hacen pantalla grande ni salvapantallas: VentanaReloj (D2)."""
        return False

    @property
    def bailando(self) -> bool:
        return self._bailando

    def bailar(self, on: bool, opciones: dict | None = None):
        """Baila (True, con {estilo, cambiar, cambiarS, particulas}) o para (False,
        con fundido). Cara feliz y sin respiración mientras baila; oculta no baila,
        pero al volver a mostrarse sigue."""
        if self.cerrado:
            return
        if on:
            self._bailando = True
            self._baile_opciones = dict(opciones) if isinstance(opciones, dict) else {}
            if self._durmiendo:
                self._despertar()
            self._timer_sueno.stop()
            self._resp.detener()
            if not (self._arrastrando or self._mareada or self._durmiendo) \
                    and self._base[0] not in ESTADOS_ACTIVIDAD:
                self.cara.set_state("happy")
            if self.isVisible():
                self._baile.bailar(True, self._baile_opciones)
            return
        if not self._bailando:
            return
        self._bailando = False
        self._baile.bailar(False)                    # fundido de salida; al acabar, respira otra vez
        if not self._baile.activo:
            self._fin_baile()
        if not (self._arrastrando or self._mareada or self._durmiendo):
            self._restaurar_cara()
        self._rearmar_sueno()

    def pulso(self, bpm: float, fase: float, energia: float):
        """Pulso de la música (≤ 2 Hz): el baile lo extrapola con su reloj."""
        self._baile.pulso(bpm, fase, energia)

    def _on_cuadro_baile(self, grados: float, dy: int):
        self._baile_cuadro = (float(grados), int(dy))
        if not self._baile.activo and not self._bailando:
            self._fin_baile()
        if self._sr is not None and not self._arrastrando:
            self._componer()

    def _fin_baile(self):
        """Acabó el fundido de salida: vuelve la respiración."""
        self._baile_cuadro = (0.0, 0)
        if self._fisica_permitida and self.isVisible() and not self.cerrado:
            self._resp.iniciar()

    # ── Alarma (corte 5: ui/alarmas_qt.ControlAlarmasQt) ───────────────────────
    def mostrar_alarma(self, texto: str, retraso_ms: int = ALARMA_RETRASO_MS):
        """Alarma sonando: la despierta y, a los `retraso_ms`, la burbuja roja con
        `texto` escrito a 35 c/s. Se queda hasta `ocultar_alarma()`."""
        if self.cerrado:
            return
        t = str(texto or "").strip() or "⏰"
        self._t_alarma.stop()
        self._t_tipeo.stop()
        self._alarma_texto = t[:BurbujaQt.MAX_CARACTERES]
        self._alarma_mostrada = ""
        self._burbuja_ia = False
        if self._burbuja is not None:
            self._burbuja.hide()                     # lo que dijera antes deja sitio a la alarma
        self._despertar(usuario=True)
        self._timer_sueno.stop()
        try:
            ms = max(0, int(retraso_ms))
        except (TypeError, ValueError):
            ms = ALARMA_RETRASO_MS
        self._t_alarma.start(ms)

    def ocultar_alarma(self):
        """La alarma se apagó: fuera la burbuja roja (vuelve el estilo normal)."""
        self._t_alarma.stop()
        self._t_tipeo.stop()
        habia = self._alarma_texto is not None
        self._alarma_texto = None
        self._alarma_mostrada = ""
        if not habia:
            return
        b = self._burbuja
        if b is not None:
            try:
                b.hide()
                b.setMaximumWidth(BurbujaQt.ANCHO_MAX)
            except RuntimeError:
                pass
            self._estilo_burbuja()
        self._rearmar_sueno()

    @property
    def alarma(self) -> str | None:
        """El texto de la alarma que se enseña (None: ninguna)."""
        return self._alarma_texto

    def _empezar_alarma(self):
        if self._alarma_texto is None or self.cerrado:
            return
        self._alarma_mostrada = ""
        self._t_tipeo.start()
        self._tipear_alarma()

    def _tipear_alarma(self):
        texto = self._alarma_texto
        if texto is None or self.cerrado:
            self._t_tipeo.stop()
            return
        self._alarma_mostrada = texto[:len(self._alarma_mostrada) + 1]
        if len(self._alarma_mostrada) >= len(texto):
            self._t_tipeo.stop()
        if self.isVisible():
            self._burbuja_alarma(self._alarma_mostrada)

    def _burbuja_alarma(self, texto: str):
        b = self._burbuja_qt()
        t_fin = getattr(b, "_t_fin", None)
        if t_fin is not None:
            t_fin.stop()                             # la burbuja de la alarma no se va sola
        ancho = ALARMA_ANCHO_MAX
        pantalla = self.screen() or QApplication.primaryScreen()
        if pantalla is not None:
            ancho = min(ancho, int(pantalla.availableGeometry().width() * 0.92))
        if b.maximumWidth() != ancho:
            b.setMaximumWidth(ancho)
        if not self._estilo_rojo:
            self._estilo_burbuja()
        b.texto(texto)

    # ── Sentarse y comida (cortes 7 y 8: ui/asiento_qt y ui/comida_qt) ─────────
    # Sin set_arrastre_delegado A PROPÓSITO: el arrastre de los sprites es nativo y
    # ControlAsiento lo detecta por eso (encaja al soltar, WM_EXITSIZEMOVE).
    def hwnd(self) -> int:
        """HWND de la ventana (0 si está cerrada)."""
        if self.cerrado:
            return 0
        try:
            return int(self.winId())
        except Exception:                            # noqa: BLE001
            return 0

    @property
    def sentada(self) -> str:
        """'' | 'barra' | 'ventana' (lo último pedido con `asiento`)."""
        return self._sentada

    def _emitir_arrastre(self, on: bool):
        """arrastre_cambio(on) solo en los cambios (ENTER/EXIT repetidos no cuentan dos veces)."""
        on = bool(on)
        if on == self._arrastre_senal:
            return
        self._arrastre_senal = on
        try:
            self.arrastre_cambio.emit(on)
        except Exception:                            # noqa: BLE001
            pass

    def _rect_figura_ventana(self) -> QRect:
        """El sprite recto (sin giro ni respiración) en coordenadas de la ventana; sin
        imagen (vídeo), la ventana sin el margen de giro."""
        r = self._rect_figura_en_cara()
        if r is not None and self.cara is not None:
            try:
                return QRect(self.cara.mapTo(self, r.topLeft()), r.size())
            except Exception:                        # noqa: BLE001
                pass
        return self._rect_figura(0, 0)

    def _punto_asiento(self) -> dict:
        """asiento = sonda = centro de abajo de la figura (px lógicos de la ventana)."""
        fig = self._rect_figura_ventana()
        p = [fig.x() + fig.width() / 2.0, float(fig.y() + fig.height())]
        return {"asiento": list(p), "sonda": list(p)}

    def punto_asiento(self, cb):
        """cb({"asiento": [x, y], "sonda": [x, y]}): SÍNCRONO (ControlAsiento lo usa al soltar)."""
        if not callable(cb):
            return
        try:
            cb(None if self.cerrado else self._punto_asiento())
        except Exception:                            # noqa: BLE001
            pass

    def asiento(self, on: bool, modo: str = "", variante: int = 0, cb=None):
        """Sentada «de pie sobre el borde» (D2): cara `sitting` si el pack la trae, sin
        balanceo (la ventana la mueve ControlAsiento) y con respiración; frases «sentarse»
        y «bajar». cb(punto) síncrono, ya con la cara nueva."""
        if self.cerrado:
            if callable(cb):
                try:
                    cb(None)
                except Exception:                    # noqa: BLE001
                    pass
            return
        antes = self._sentada
        if on:
            m = str(modo or "").strip().lower()
            m = m if m in MODOS_ASIENTO else "ventana"
            try:
                v = max(0, min(3, int(variante)))
            except (TypeError, ValueError):
                v = 0
            self._sentada, self._asiento_var = m, (0 if m == "barra" else v)
        else:
            self._sentada, self._asiento_var = "", 0
        if bool(antes) != bool(self._sentada):
            self._actualizar_fisica()                # sentada: sin balanceo
            self.cara.set_reposo(self._cara_reposo())
            if not (self._durmiendo or self._arrastrando or self._mareada) \
                    and getattr(self.cara, "_current_state", "normal") in ("normal", "sitting"):
                self._restaurar_cara()
            self._frase("sentarse" if self._sentada else "bajar")
        if callable(cb):
            try:
                cb(self._punto_asiento() if self._sentada else None)
            except Exception:                        # noqa: BLE001
                pass

    def restaurar_orden_z(self):
        """Vuelve el orden Z de siempre (avatar.siempre_encima o el plan del modo juego)."""
        if self.cerrado or not self.isVisible():
            return
        self._aplicar_encima(forzar=True)

    def cabeza(self, cb):
        """cb((cx, cy, r)) SÍNCRONO en px lógicos globales: la cabeza al 35 % del alto de
        la figura y r = 0.22·ancho (ControlComida)."""
        if not callable(cb):
            return
        res = None
        if not self.cerrado:
            fig = self._rect_figura_ventana()
            o = self.mapToGlobal(QPoint(0, 0))
            res = (o.x() + fig.x() + fig.width() / 2.0,
                   o.y() + fig.y() + fig.height() * ALTO_CABEZA,
                   max(1.0, RADIO_CABEZA * fig.width()))
        try:
            cb(res)
        except Exception:                            # noqa: BLE001
            pass

    def comer(self, tipo: str, ms: int = MS_COMER):
        """Le pasaron la comida por la cabeza: la despierta, cara feliz `ms` y frase «comer»."""
        if self.cerrado:
            return
        try:
            ms = max(100, min(10_000, int(ms)))
        except (TypeError, ValueError):
            ms = MS_COMER
        self._despertar(usuario=True)
        self._poner_cara("happy", ms)
        self._frase("comer")

    def set_comida_activa(self, on: bool):
        """Comida en el cursor: sin reacción al clic, sin chat con doble clic y sin sueño."""
        if self.cerrado:
            return
        self._comida_activa = bool(on)
        if self._comida_activa:
            self._clic.cancelar()
            self._timer_sueno.stop()
        else:
            self._rearmar_sueno()

    @property
    def comida_activa(self) -> bool:
        return self._comida_activa

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
        self.tray.setToolTip("Lune · asistente en escritorio")
        menu = self._menu_bandeja = QMenu()
        act_chat = QAction("Escribirle a Lune…", self)
        act_chat.triggered.connect(self.abrir_chat)
        menu.addAction(act_chat)
        act_mostrar = QAction("Mostrar / ocultar", self)
        act_mostrar.triggered.connect(self._alternar)
        act_centrar = QAction("Llevar a la esquina", self)
        act_centrar.triggered.connect(self.llevar_a_esquina)
        self.act_fantasma = QAction("Modo fantasma (dejar pasar clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.setChecked(bool(self.config and self.config.get("avatar", "click_through", False)))
        self.act_fantasma.toggled.connect(self._alternar_fantasma)
        act_cerrar = QAction("Cerrar la asistente en escritorio", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_mostrar); menu.addAction(act_centrar)
        menu.addAction(self.act_fantasma)
        menu.addSeparator(); menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activado)
        self.tray.show()

    def _on_tray_activado(self, razon):
        if razon == QSystemTrayIcon.ActivationReason.Trigger:
            self._alternar()

    def quitar_bandeja(self):
        """Quita su icono de bandeja (la app tiene una sola: ui/bandeja.BandejaLune)."""
        tray, self.tray = getattr(self, "tray", None), None
        menu, self._menu_bandeja = getattr(self, "_menu_bandeja", None), None
        self.act_fantasma = None
        if tray is not None:
            try:
                tray.hide()
                tray.deleteLater()
            except RuntimeError:
                pass
        if menu is not None:
            try:
                menu.deleteLater()
            except RuntimeError:
                pass

    def _alternar(self):
        self.hide() if self.isVisible() else (self.showNormal(), self.raise_())

    def closeEvent(self, ev):
        self.cerrado = True
        self._clic.cancelar()
        self._arrastrando_desde = None
        self._emitir_arrastre(False)                 # cerrada a mitad de un arrastre: se acabó
        self._t_guardar.stop()
        self._timer_sueno.stop(); self._timer_sueno_pedido.stop(); self._timer_mareo.stop()
        self._t_alarma.stop(); self._t_tipeo.stop()
        self._baile.detener()
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
        self.quitar_bandeja()
        if self.cara is not None and getattr(self.cara, "_player", None):
            self.cara._player.stop()
        ev.accept()
