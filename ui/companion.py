"""
ui/companion.py — Lune como companion flotante de escritorio (v10.1).

Ventana pequeña, sin bordes, siempre encima y arrastrable con una burbuja donde
Lune comenta lo que ve en tu pantalla. Dos formas de dibujarla (config avatar.render):

    "animado"  los clips webm de la piel web en un mini-stage con marco neón
               (ui_web/companion.html).
    "vrm"      un avatar 3D VRM (ui_web/companion_vrm.html + ui_web/vrm/lune_vrm.js,
               three.js + @pixiv/three-vrm empaquetados en ui_web/vendor). El .vrm
               se elige por personaje (nucleo/vrm.py) y se sirve por el http local.

Comportamientos de mascota (modo VRM), portados de Mate-Engine a procedural:
  - sigue el cursor con cabeza, ojos y torso aunque esté fuera de la ventana
    (Python le manda la posición global a ~30 Hz);
  - al arrastrarla se balancea según la velocidad y rebota al soltarla;
  - mueve la boca mientras suena la voz (VoiceEngine.al_hablar);
  - calibración por modelo (luz, altura, pesos de seguimiento, invertir ejes):
    `aplicar_params_vrm()` → window.luneParams(nucleo/vrm.params_modelo_json) al
    cargar la página, al cambiar de modelo y al guardar Ajustes;
  - "fantasma automático": los clics pasan al escritorio donde NO hay avatar
    (la página dice si el cursor está sobre el modelo y aquí se conmuta
    WS_EX_TRANSPARENT), además del modo fantasma total de la bandeja.

En los dos renders (corte 3):
  - se duerme tras avatar.dormir_min minutos sin tocarla ni hablarle, si la
    regla lo permite (nucleo/sueno.ReglaSueno: nunca arrastrándola, hablando,
    en llamada ni a mitad de una actividad) — la animada tiene window.luneSleep;
    `dormir()` / `despertar()` / `durmiendo` para las herramientas del modelo
    (nucleo/sueno.herramienta_dormir/despertar). Un «duérmete» no lo deshace la
    propia respuesta: la voz y las emociones de esa respuesta la despiertan un
    momento y vuelve a dormirse al acabar;
  - frases cortas sin pasar por el modelo (lune_core/frases_mascota.py) cuando la
    arrastras, la sueltas, la acaricias, se marea, se duerme, se despierta o
    aparece: los eventos llegan por window.luneEventos y la frase sale en la
    burbuja con window.comentar(t, 3500), sin pisar una respuesta de la IA.

Comentarios de pantalla: captura la pantalla, se la manda al modelo (visión) y
muestra un comentario breve en la burbuja. Manual (clic sobre ella / bandeja) o
periódico opcional (avatar.comentarios_cada_min; 0 = apagado). Con Ollama es 100%
local; el manual, con un modelo local sin visión, puede usar la nube con la captura
(avisando una vez); el AUTOMÁTICO nunca sube la captura a la nube (comenta por la
ventana activa, en texto). Si Ollama responde y ve se pregunta en un hilo aparte
(con Ollama apagado tardaba 3 + 3 s con la mascota congelada). El intercambio es
efímero: no entra en el historial que comparte con el chat.

Canal de eventos página → Python (v10.3, en los dos renders): la página encola lo
que pasa (caricia, arrastre, dormir, despertar, estado, error…) en
window.luneEventos (ui_web/lune_eventos.js) y aquí un QTimer propio a 12 Hz la
vacía con runJavaScript y emite `evento_js(tipo, datos)` por cada evento. Va
aparte del sondeo del cursor, que se salta cuando el cursor está quieto fuera de
la ventana. Se para al ocultarla o cerrarla y vuelve al mostrarla.

Estado compartido: si se le pasa un nucleo.estado_mascota.BusEstado
(`bus_estado=` o `set_bus_estado()`), lo mantiene al día (visible, arrastrando,
durmiendo, pensando, hablando, emoción). Sin bus no cambia nada.

Chat con la mascota (corte 2, ui/chat_mascota.py): doble clic (o la bandeja) →
`abrir_chat()` con la cajita EntradaChat anclada bajo ella. El clic simple (que
comenta la pantalla) se retrasa el intervalo de doble clic del sistema y se
cancela si llega el segundo. Lo escrito va a `on_chat(texto)`, que ponen quien
lleva la app (web_bridge.enviar_desde_mascota / main._chat_desde_mascota), y la
respuesta llega con `burbuja_texto(texto)` / `burbuja_fin(ms)` (lune_burbuja.js).
Al cargar la página se carga el pack de sonidos de reacción (luneSonidos,
ui_web/lune_packs.js, que las dos páginas cargan con <script src>).

Seguridad (crítica d): el comentario de pantalla lleva texto de terceros (la
captura o el título de la ventana activa), así que su turno va con origen
'no_confiable', sin herramientas, y el título pasa por neutralizar_marcadores.

Navegación (revisión 4-5-6, SB4): Python le empuja a la página cada respuesta de la
IA (window.comentar), las frases y las alarmas, y lee lo que dice (luneEventos,
luneCabeza). Por eso su vista lleva la misma guarda que la ventana principal
(ui/web_shell.asegurar_pagina): el marco principal solo navega dentro del servidor
local de la mascota; un enlace pulsado va al navegador del sistema; soltar un enlace
o un archivo sobre ella (en grande, todo el monitor), file:, data:… se rechazan.

Corte 4 (contrato de la mascota, igual en ui/avatar_overlay.py):
  - `bandeja=False` al crearla: sin icono propio (la bandeja única es
    ui/bandeja.BandejaLune); `quitar_bandeja()` quita uno ya creado.
  - clic derecho (al SOLTAR, sin menú contextual de Chromium: NoContextMenu) →
    señal `menu_pedido('principal', QPoint global)` para el menú radial;
    `ancla_menu(cb)` da el punto de la cabeza (window.luneCabeza() de la página o,
    si no lo tiene o no responde, el 35 % del alto de la ventana);
    `set_menu_abierto(on)`: con el menú abierto no se arrastra, no se acaricia,
    no se duerme sola y no deja pasar los clics.
  - `aplicar_plan_juego(plan | None)` (ui/modo_juego_qt): ocultar / al fondo /
    nada, FPS del juego, sin comentarios automáticos ni capturas. Solo vuelve a
    mostrarse si la ocultó el modo juego; si el usuario la saca a mano, gana él.
  - `aplicar_tema(css_json)` → window.luneTema (se reaplica al recargar),
    `set_encima(on)` (reafirmado al mostrarse), `set_fps_max(n)` (en vez del 60
    fijo), `set_comentarios_auto(on)`, `llevar_a_esquina()`, propiedades
    `comentarios_auto` y `click_through`.

Cortes 5 y 6 (contrato de la mascota; los controladores son ui/pantalla_grande_qt,
ui/alarmas_qt y ui/baile_qt):
  - `soporta_grande` (página cargada), `geometria()` / `set_geometria(QRect)` (sin
    guardar la posición ni devolverla a la pantalla) y `grande_fase(fase, opciones)`
    con fase glide · entrar · salir · volver · fin → luneGrande de la página. Desde
    el primer glide hasta fin: sin rueda, sin arrastre, sin comentar con el clic,
    sin chat con el doble clic, sin sueño ni comentarios automáticos y sin fantasma
    automático; el clic izquierdo MANTENIDO aparta el pelo (luneHold, solo VRM), el
    cursor se mide desde el 50 % del alto y va a 30 fps (fin → avatar.fps_max).
  - `set_salvapantallas(on, fondo_oscuro=, reloj=)` → luneSalvapantallas y la
    duerme directamente (la regla del sueño bloquea en grande) o la despierta.
  - `mostrar_alarma(texto, retraso_ms=3000)` / `ocultar_alarma()` → luneAlarma
    (burbuja roja a 35 c/s); con una alarma a la vista el clic no comenta.
  - `bailar(on, opciones)` → luneBailar (la animada pone el clip happy con una capa
    de emoción mientras baila) y `pulso(bpm, fase, energia)` → lunePulso. Bailando
    no se duerme sola.
  Si la página recarga, se le vuelve a pedir lo que estaba a la vista.

Cortes 7 y 8 (contrato de la mascota; los controladores son ui/asiento_qt.ControlAsiento y
ui/comida_qt.ControlComida):
  - señal `arrastre_cambio(bool)`: True al pasar el umbral del arrastre (antes del
    delegado en ese mismo MouseMove), False al soltar ANTES de devolverla a la pantalla
    y de guardar la posición (y si el arrastre se corta: menú, pantalla grande, ocultarla).
  - señal `antes_de_colocar()`: la emite `llevar_a_esquina()` antes de moverla (su propio
    menú no pasa por el Despachador); ui/montaje_vida la conecta a asiento.bajar("usuario").
  - `set_arrastre_delegado(fn | None)`: fn() en cada MouseMove del arrastre; si devuelve
    True ya movió la ventana (px físicos) y aquí no se hace `move` (luneDrag sigue).
  - `hwnd()`, `punto_asiento(cb)` → luneSeatPx: cb({"asiento": [x, y], "sonda": [x, y]} |
    None) en px lógicos de la ventana; `asiento(on, modo, variante, cb=)` → luneSentar
    (VRM: pose sentada y encuadre de cuerpo entero; animada: apoyada en el borde) con la
    frase «sentarse»/«bajar»; `sentada` ('' | 'barra' | 'ventana'): mientras está sentada
    no se devuelve a la pantalla ni se toca su orden Z (lo lleva ControlAsiento), salvo
    `restaurar_orden_z()`. Arrastrándola sentada, la página no se balancea (velocidad 0).
  - clic CENTRAL soltado sobre ella → `menu_pedido('secundario', QPoint)` (batido, pastel…).
  - `cabeza(cb)` → cb((cx, cy, r) | None) en px lógicos GLOBALES (luneCabeza(0.1));
    `comer(tipo, ms)` → luneComer + frase «comer» (y la despierta); `set_comida_activa(on)`
    → luneComidaActiva (sin caricia): con comida en la mano el clic no comenta, el doble
    clic no abre el chat y no se duerme.
  Se repite si la página recarga (como lo de los cortes 5 y 6).

Cortes 9 y 10 (contrato de la mascota; los controladores son ui/mmd_qt.ControlMMD y
ui/minecraft_qt.ControlMinecraft):
  - `mmd(orden, datos)` → window.luneMMD(orden, datos) con orden cargar · pausa · parar ·
    volumen · offset · en_sitio · bucle. «cargar» pasa por `datos_mmd_seguros()` (id de 12
    hex, tipo vmd|vrma en la VRM y «audio» en la animada, URL solo de /bailes/ o
    /bailes_cache/ ya codificadas, números en rango): si no vale devuelve False (error). La
    primera vez publica bailes/ y cache/bailes/ en el servidor local (nunca file://).
    Mientras hay un baile (`mmd_activo`) no se duerme sola ni se libera su página oculta;
    oculta, el baile se pausa y sigue al volver a verla. Si la página aún no cargó, lo
    pedido se guarda y se repite en _on_cargado; si RECARGA con un baile en marcha →
    evento_js('mmd', {fase:'error', mensaje:'recarga'}) (ControlMMD para sin avisar).
  - `decir_reaccion(texto, estado, ms)`: la reacción a la partida de Minecraft en la
    burbuja (a máquina, 35 c/s) con su cara. False (no la dice) cerrada u oculta, en
    pantalla grande o salvapantallas, con una alarma o con algo de la IA en la burbuja.
"""
from __future__ import annotations

import base64
import dataclasses
import io
import json
import math
import re
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QPoint, QRect, QTimer, QEvent, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QActionGroup, QColor, QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

from ui.servidor_web import ServidorEstatico, DIR_WEB, RAIZ
from ui.chat_mascota import ChatMascota, DesambiguadorClic, ms_lectura
from nucleo import datos
from nucleo.sueno import ReglaSueno
from lune_core import marcadores
from lune_core.acciones import limpiar_texto
from lune_core.frases_mascota import frases_para
from lune_core.prompt import neutralizar_marcadores
from nucleo.respuestas import AVISO_MASCOTA_SIN_NUBE, COMENTARIO_VACIO

PAGINAS = {"animado": "companion.html", "vrm": "companion_vrm.html"}
RUTA_MODELO = "/vrm/actual.vrm"          # el .vrm activo, publicado por el http local

# Tamaño de la ventana (px) por modo de render y tamaño elegido.
TAMANOS_VRM = {"pequeno": (210, 330), "normal": (290, 460), "grande": (390, 620)}
TAMANO_ANIMADO = (240, 430)
ENCUADRES = ("retrato", "cuerpo")

# Emoción canónica del modelo → estado de la mascota (mismo vocabulario en las
# dos páginas: companion.html lo mapea a clips y companion_vrm.html a expresiones).
EMOCION_A_ESTADO = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
    # v10.1
    "laughing": "laughing", "bored": "bored",
}
# Al revés, para el BusEstado (que guarda la emoción canónica): si un estado es
# también una emoción ("nervous"), se queda tal cual; si no, la primera que lo da.
_ESTADO_A_EMOCION = {e: e for e, s in EMOCION_A_ESTADO.items() if e == s}
for _e, _s in EMOCION_A_ESTADO.items():
    _ESTADO_A_EMOCION.setdefault(_s, _e)
del _e, _s

EVENTOS_JS = "window.luneEventos ? window.luneEventos() : '[]'"

# Frases de la mascota (lune_core/frases_mascota.py) en la burbuja: lo que duran.
MS_FRASE = 3500
# Sueño (nucleo/sueno.ReglaSueno): si al vencer la regla no deja dormir (hablando,
# arrastrándola, pensando…), se vuelve a mirar a los REINTENTO_SUENO_MS.
REINTENTO_SUENO_MS = 30_000
# «Duérmete» (herramienta mascota_dormir): la propia respuesta (su voz, sus
# emociones) la despierta en la página; durante GRACIA_SUENO_S desde lo último de
# esa respuesta vuelve a dormirse PAUSA_VOLVER_A_DORMIR_MS después de callar.
GRACIA_SUENO_S = 30.0
PAUSA_VOLVER_A_DORMIR_MS = 1500
# Mascota 3D oculta este rato (Lune de vuelta en la ventana, donde la barra lateral
# tiene su propio VRM): se descarta su página para no tener dos contextos WebGL.
LIBERAR_OCULTA_MS = 60_000
# Estados visuales que son una ACTIVIDAD en curso. Las emociones (happy, sad…) se
# quedan puestas (la animada repite el clip; main.py las pone sin vuelta): cuando
# vence el sueño —y toda emoción lo rearma— una emoción vieja cuenta como reposo.
ESTADOS_ACTIVIDAD = frozenset({"thinking", "typing", "working", "talking", "listening"})

# Pack de sonidos de reacción → luneSonidos (ui_web/lune_packs.js, que las dos
# páginas cargan con <script src> junto a lune_sfx.js). Si la página no lo trae,
# no suena nada: lo pedido queda anotado en __lunePackPendiente.
_JS_PACK = """(function (w, pack, vol) {
  var s = w.luneSonidos;
  if (!s) { w.__lunePackPendiente = { pack: pack, vol: vol }; return; }
  w.__lunePackPendiente = null;
  try { if (s.setVolumen) s.setVolumen(vol); if (pack && s.cargar) s.cargar(pack); } catch (e) {}
})(window, __PACK__, __VOL__)"""
# Llamada a luneSonidos solo si ya está cargado (tecleo, voz TTS sonando…).
_JS_SONIDOS = "(function (w) { var s = w.luneSonidos; if (s && s.__METODO__) s.__METODO__(__ARG__); })(window)"


def _js_sonidos(metodo: str, arg: str) -> str:
    return _JS_SONIDOS.replace("__METODO__", metodo).replace("__ARG__", arg)


# ── Corte 4: FPS, menú radial y tema ──────────────────────────────────────────
FPS_MIN, FPS_MAX = 15, 144          # avatar.fps_max (el limitador de Mate-Engine)
ALTO_CABEZA = 0.35                  # sin luneCabeza: la cabeza, al 35 % del alto
ANCLA_TIMEOUT_MS = 300              # la página no contesta a luneCabeza: geometría
MS_AVISO_JUEGO = 3500
_AVISO_JUEGO = "En modo juego no miro la pantalla."
# luneCabeza() (ui_web/tema.js del corte 4) → '{"x":…,"y":…,"r":…}' en px de la página.
_JS_CABEZA = ("(function () { try { var r = window.luneCabeza ? window.luneCabeza() : null;"
              " return (r && typeof r === 'object') ? JSON.stringify(r) : r; } catch (e) { return null; } })()")
_SIN_TEMA = object()                # aún no se ha pedido ningún tema
_RE_VAR_CSS = re.compile(r"--[a-z0-9-]{1,40}")
_RE_VALOR_CSS = re.compile(r"[#0-9a-zA-Z .,%()/-]{1,64}")


# ── Cortes 5 y 6: pantalla grande, salvapantallas, alarma y baile ──────────────
FASES_GRANDE = ("glide", "entrar", "salir", "volver", "fin")
FPS_GRANDE = 30                     # ventana translúcida del tamaño del monitor
ALTO_CURSOR_GRANDE = 0.5            # en pantalla grande la cara está en el centro
RETRASO_ALARMA_MS = 3000            # la burbuja de la alarma sale a los 3 s…
CPS_ALARMA = 35                     # …y se escribe a 35 caracteres por segundo
MAX_TEXTO_ALARMA = 500
HOLD_HZ = 30                        # luneHold mientras se arrastra con el botón pulsado
BPM_MIN, BPM_MAX = 40.0, 240.0
_RE_CLAVE_OPCION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")


def opciones_seguras(opciones) -> dict:
    """Opciones para la página (luneGrande, luneBailar…) → dict plano y seguro:
    claves identificador, valores bool/None/números finitos/texto corto. Lo demás
    (listas, objetos, NaN) se descarta."""
    if not isinstance(opciones, dict):
        return {}
    res = {}
    for k, v in list(opciones.items())[:32]:
        if not isinstance(k, str) or not _RE_CLAVE_OPCION.fullmatch(k):
            continue
        if v is None or isinstance(v, bool):
            res[k] = v
        elif isinstance(v, (int, float)):
            if math.isfinite(float(v)):
                res[k] = v
        elif isinstance(v, str):
            res[k] = v[:80]
    return res


def _js_opciones(opciones) -> str:
    return json.dumps(opciones_seguras(opciones), ensure_ascii=True, sort_keys=True)


def _finito(v, defecto=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return defecto
    return f if math.isfinite(f) else defecto


# ── Cortes 7 y 8: sentarse y comida ─────────────────────────────────────────────
MODOS_ASIENTO = ("ventana", "barra")
VARIANTES_ASIENTO = 4                # poses de ventana (la barra tiene una)
MS_COMER = 2500
MS_COMER_MAX = 10_000
# luneCabeza(0.1): la cabeza + 0.1 m (como la comida de Mate-Engine) en px de la página.
_JS_CABEZA_COMIDA = ("(function () { try { var r = window.luneCabeza ? window.luneCabeza(0.1) : null;"
                     " return (r && typeof r === 'object') ? JSON.stringify(r) : r; } catch (e) { return null; } })()")
_JS_SEAT = "(function () { try { return window.luneSeatPx ? window.luneSeatPx() : null; } catch (e) { return null; } })()"


# ── Cortes 9 y 10: reproductor de bailes (MMD/VRMA) y reacciones a Minecraft ─────
ORDENES_MMD = ("cargar", "pausa", "parar", "volumen", "offset", "en_sitio", "bucle")
TIPOS_MMD = ("vmd", "vrma", "audio")
MAX_URL_MMD = 1024
MAX_MOTION_MMD = 3
MAX_CARA_MMD = 2
MAX_TITULO_MMD = 80
# /bailes/ o /bailes_cache/ + la ruta YA codificada (quote(…, safe="/")): solo letras y
# números ASCII, «._~-», «/» y %XX. Nada de «..», «//», «\», query ni fragmento.
_RE_URL_MMD = re.compile(r"/(?:bailes|bailes_cache)/[A-Za-z0-9._~%/-]+")
_RE_PCT_MMD = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PCT_PROHIBIDOS = ("%2e%2e", "%2f", "%5c", "%00", "%25")
_RE_ID_MMD = re.compile(r"[0-9a-f]{12}")
# (clave, mínimo, máximo): números de «cargar»; fuera de rango → no se acepta.
_RANGOS_MMD = (("offsetMs", -500.0, 500.0), ("brazoGrados", 25.0, 45.0), ("volumen", 0.0, 1.0),
               ("bpm", 40.0, 240.0), ("fase0", 0.0, 1.0))
_BOOLS_MMD = ("enSitio", "bucle", "autoplay")
AVISO_SIN_ESQUELETO = "Esta mascota no tiene esqueleto: baila a su manera."
MS_AVISO_SIN_ESQUELETO = 5000
CPS_REACCION = 35                    # la burbuja de Minecraft se escribe a 35 c/s (Mate-Engine)
MS_REACCION = 8000
MS_REACCION_MIN, MS_REACCION_MAX = 1500, 20_000
MAX_TEXTO_REACCION = 300


def url_mmd_segura(url) -> str | None:
    """Una URL de la biblioteca de bailes para la página, o None: empieza por /bailes/ o
    /bailes_cache/, ASCII ya codificado con %, ≤1024, sin '..', '//', '\\', query ni hash
    (ni esas cosas escondidas con %)."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_MMD:
        return None
    if not _RE_URL_MMD.fullmatch(url) or _RE_PCT_MMD.search(url):
        return None
    if ".." in url or "//" in url:
        return None
    bajo = url.lower()
    if any(p in bajo for p in _PCT_PROHIBIDOS):
        return None
    return url


def _urls_mmd(datos: dict, clave: str, maximo: int):
    """La lista `clave` ([url]) o los planos clave0..clave{n-1} → lista de URL válidas, o
    None si alguna no vale o hay demasiadas."""
    crudo = datos.get(clave)
    if crudo is None:
        crudo = [datos.get(f"{clave}{i}") for i in range(maximo)]
        crudo = [u for u in crudo if u not in (None, "")]
    elif not isinstance(crudo, (list, tuple)):
        return None
    if len(crudo) > maximo:
        return None
    urls = [url_mmd_segura(u) for u in crudo]
    return None if any(u is None for u in urls) else urls


def datos_mmd_seguros(datos) -> dict | None:
    """Los datos de `mmd("cargar", …)` para la página → dict limpio o None si no valen.

    id ^[0-9a-f]{12}$; tipo vmd|vrma (motion 1..3 —el .vrma, 1—, cara ≤2, audio opcional)
    o audio (la mascota animada: audio obligatorio y sin motion/cara); URL con
    `url_mmd_segura`; offsetMs −500..500, brazoGrados 25..45, volumen 0..1, bpm 40..240,
    fase0 0..1 (fuera de rango → None); enSitio/bucle/autoplay bool; titulo ≤80 sin
    controles. Las claves que no son del contrato se descartan."""
    if not isinstance(datos, dict):
        return None
    id_ = datos.get("id")
    tipo = datos.get("tipo")
    if not isinstance(id_, str) or not _RE_ID_MMD.fullmatch(id_) or tipo not in TIPOS_MMD:
        return None
    motion = _urls_mmd(datos, "motion", MAX_MOTION_MMD)
    cara = _urls_mmd(datos, "cara", MAX_CARA_MMD)
    if motion is None or cara is None:
        return None
    audio = datos.get("audio")
    if audio in (None, ""):
        audio = None
    else:
        audio = url_mmd_segura(audio)
        if audio is None:
            return None
    if tipo == "audio":
        if motion or cara or audio is None:
            return None
    elif not motion or (tipo == "vrma" and len(motion) != 1):
        return None
    res = {"id": id_, "tipo": tipo, "audio": audio}
    if tipo != "audio":
        res["motion"], res["cara"] = motion, cara
    for clave, lo, hi in _RANGOS_MMD:
        v = datos.get(clave)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            return None
        if not lo <= float(v) <= hi:
            return None
        res[clave] = v
    for clave in _BOOLS_MMD:
        v = datos.get(clave)
        if v is None:
            continue
        if not isinstance(v, bool):
            return None
        res[clave] = v
    titulo = datos.get("titulo")
    if titulo is not None:
        if not isinstance(titulo, str):
            return None
        t = "".join(ch if ch.isprintable() else " " for ch in titulo)
        res["titulo"] = " ".join(t.split())[:MAX_TITULO_MMD]
    return res


def _js_mmd(orden: str, arg) -> str:
    """La llamada a window.luneMMD con el argumento como literal JSON (ASCII)."""
    a = "null" if arg is None else json.dumps(arg, ensure_ascii=True, sort_keys=True)
    return f"window.luneMMD && window.luneMMD({json.dumps(orden)}, {a})"


def _par_finito(v):
    """{x, y} o [x, y] con números finitos → (x, y) o None."""
    if isinstance(v, dict):
        x, y = _finito(v.get("x")), _finito(v.get("y"))
    elif isinstance(v, (list, tuple)) and len(v) >= 2:
        x, y = _finito(v[0]), _finito(v[1])
    else:
        return None
    return (x, y) if x is not None and y is not None else None


def punto_de_pagina(resultado) -> dict | None:
    """Respuesta de luneSentar/luneSeatPx ('{"asiento":{x,y},"sonda":{x,y}}', 'null', un
    dict o basura) → {"asiento": [x, y], "sonda": [x, y]} en px de la página, o None."""
    datos = resultado
    if isinstance(datos, (str, bytes)):
        try:
            datos = json.loads(datos)
        except ValueError:
            return None
    if not isinstance(datos, dict):
        return None
    a = _par_finito(datos.get("asiento"))
    if a is None:
        return None
    s = _par_finito(datos.get("sonda")) or a
    return {"asiento": [a[0], a[1]], "sonda": [s[0], s[1]]}


def _llamar_cb(cb, valor):
    """Llama al callback de un controlador sin dejar que un fallo suyo tumbe la mascota."""
    if not callable(cb):
        return
    try:
        cb(valor)
    except Exception as e:                           # noqa: BLE001
        _log(f"[companion] un callback de la mascota falló: {e}")


def mapa_tema(css_json):
    """css_json de nucleo/tema.css_json ("null", '{"--cyan-500": "#…", …}', un dict
    o None) → dict saneado (solo --variables con valores de color) o None.
    Lanza ValueError si no es un JSON de tema (y entonces no se aplica nada)."""
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
    return {k: v for k, v in datos.items()
            if isinstance(k, str) and isinstance(v, str)
            and _RE_VAR_CSS.fullmatch(k) and _RE_VALOR_CSS.fullmatch(v)}


def _js_tema(mapa) -> str:
    """La llamada a window.luneTema con el mapa (o null) como literal JSON."""
    arg = "null" if mapa is None else json.dumps(mapa, ensure_ascii=True, sort_keys=True)
    return f"window.luneTema && window.luneTema({arg})"


def _ventana_nativa() -> bool:
    """¿Las ventanas de Qt son HWND de verdad? (no con QT_QPA_PLATFORM=offscreen)."""
    if sys.platform != "win32":
        return False
    try:
        return QApplication.platformName() == "windows"
    except Exception:
        return False


def _parsear_eventos(resultado) -> list:
    """Respuesta de luneEventos() → [(tipo, datos: dict)]. Tolera None y basura.

    Cada evento de la página es {t, d, ts}; si `d` no es un objeto se envuelve
    como {"valor": d} (o {} si es null) para que la señal lleve siempre un dict.
    """
    if not resultado:
        return []
    if isinstance(resultado, str):
        try:
            resultado = json.loads(resultado)
        except ValueError:
            return []
    if not isinstance(resultado, list):
        return []
    eventos = []
    for ev in resultado:
        if not isinstance(ev, dict):
            continue
        tipo = ev.get("t")
        if not isinstance(tipo, str) or not tipo:
            continue
        d = ev.get("d")
        datos = d if isinstance(d, dict) else ({} if d is None else {"valor": d})
        eventos.append((tipo, datos))
    return eventos

_PROMPT_PANTALLA = (
    "Esta es una captura de la pantalla del usuario. Haz UN comentario BREVE "
    "(una sola frase), con tu personalidad: directa, curiosa, con filo y sin relleno "
    "ni emoji. No describas literalmente lo que ves: coméntalo como lo haría una "
    "compañera ingeniosa. Si no hay nada interesante, suelta algo ligero."
)
# Sin visión (modelo local de solo texto): se le cuenta qué ventana tiene delante.
_PROMPT_VENTANA = (
    "No puedes ver la pantalla, pero sabes qué tiene delante el usuario ahora mismo: "
    "{contexto}. Haz UN comentario BREVE (una sola frase), con tu personalidad: directa, "
    "curiosa, con filo y sin relleno ni emoji. No lo describas literalmente: coméntalo "
    "como lo haría una compañera ingeniosa. Si no da para mucho, suelta algo ligero."
)
_PREFIJOS_ERROR = ("Error Ollama:", "Error OpenRouter:", "Error:")
# 10.9: la mascota comenta solo con la nube. La primera vez que un comentario manual
# sube la captura, se avisa (los automáticos nunca la suben: van por el título).
_AVISO_CAPTURA_NUBE = "Para mirar tu pantalla mando una captura a la nube (OpenRouter)."
_AVISO_SIN_VISION_NUBE = "Tu modelo local no ve imágenes; para la pantalla uso la nube."
_AVISO_SIN_VISION_TEXTO = ("Tu modelo local no ve imágenes: comento por la ventana activa. "
                           "Con «ollama pull llava» (u otro con visión) vería la pantalla.")


def _es_error(texto: str) -> bool:
    """Los proveedores devuelven sus fallos como texto; no son un comentario."""
    return str(texto or "").lstrip().startswith(_PREFIJOS_ERROR)


def _parece_sin_vision(msg: str) -> bool:
    m = str(msg or "").lower()
    return "400" in m or "image" in m or "imagen" in m or "vision" in m or "does not support" in m


def _texto_externo(texto: str, maximo: int) -> str:
    """Texto de terceros (título de ventana, nombre de proceso) apto para un prompt:
    en una línea, recortado y con los marcadores <|ACT|>/<|CALL|> neutralizados."""
    return neutralizar_marcadores(" ".join(str(texto or "").split())[:maximo])


def _contexto_ventana() -> str:
    """Qué tiene el usuario delante, sin captura: título de la ventana activa y programa.
    Lo escribe OTRO programa (una web puede poner lo que quiera en su título): va
    neutralizado y el turno que lo usa es no confiable (sin herramientas)."""
    titulo, proceso = "", ""
    if sys.platform == "win32":
        try:
            import win32gui, win32process
            h = win32gui.GetForegroundWindow()
            titulo = (win32gui.GetWindowText(h) or "").strip()
            try:
                import psutil
                _, pid = win32process.GetWindowThreadProcessId(h)
                proceso = psutil.Process(pid).name()
            except Exception:
                proceso = ""
        except Exception:
            pass
    titulo, proceso = _texto_externo(titulo, 120), _texto_externo(proceso, 60)
    partes = []
    if titulo:
        partes.append(f"la ventana «{titulo}»")
    if proceso:
        partes.append(f"del programa {proceso}")
    return " ".join(partes)


def _js_str(texto: str) -> str:
    return json.dumps(texto or "", ensure_ascii=False)


def _log(msg: str):
    try:
        from nucleo.utils import log_info
        log_info(msg)
    except Exception:
        pass


class CompanionFlotante(QMainWindow):
    """Mascota flotante (video anime o avatar VRM) + burbuja de comentarios."""

    visibilidad = pyqtSignal(bool)       # se muestra / se oculta o cierra
    recrear = pyqtSignal()               # "ya puedo ser VRM": quien me creó debe recrearme
    evento_js = pyqtSignal(str, dict)    # evento de la página (tipo, datos), vía luneEventos()
    menu_pedido = pyqtSignal(str, object)  # ('principal'|'secundario', QPoint global): menú radial
    arrastre_cambio = pyqtSignal(bool)   # cortes 7/8: empieza (True) o acaba (False) el arrastre
    antes_de_colocar = pyqtSignal()      # cortes 7/8: la va a colocar el código (su menú «Llevar a la
                                         # esquina»): quien la tiene sentada la baja antes (montaje_vida)
    _sondeo_listo = pyqtSignal(object)   # interna: el sondeo de Ollama (hilo aparte) terminó

    UMBRAL_ARRASTRE = 6                  # px: menos que esto es un CLIC, no arrastre
    CURSOR_HZ = 30                       # frecuencia con la que se le manda el cursor
    EVENTOS_HZ = 12                      # frecuencia con la que se vacía la cola de eventos

    def __init__(self, config=None, ai_manager=None, render: str | None = None, parent=None,
                 bus_estado=None, bandeja: bool = True):
        super().__init__(parent)
        self.config = config
        self._bus_estado = bus_estado    # nucleo.estado_mascota.BusEstado (opcional)
        # Corte 4: menú radial, modo juego, orden Z, FPS y tema.
        self.tray = None
        self.act_auto = None
        self.act_fantasma = None
        self._menu_bandeja = None
        self._menu_abierto = False       # el menú radial está abierto sobre ella
        self._der_pulsado = False        # clic derecho pulsado sobre ella (se abre al soltar)
        self._plan_juego = None          # servicios.modo_juego.PlanJuego mientras hay partida
        self._oculta_por_juego = False   # la ocultó el modo juego (y solo entonces vuelve sola)
        self._juego_mostrada_a_mano = False   # el usuario la sacó durante la partida: gana él
        self._mostrando_por_juego = False
        self._encima = self._cfg_bool("siempre_encima", True)
        self._fps_max = self._fps_de_config()
        self._min_auto = 0               # avatar.comentarios_cada_min vigente
        self._tema = _SIN_TEMA           # mapa de tema aplicado (dict | None)
        self._ancla_cb = None
        self._ancla_token = 0
        # Cortes 5 y 6: pantalla grande, salvapantallas, alarma y baile.
        self._grande_fase = None         # glide|entrar|salir|volver mientras dura (None = normal)
        self._geom_normal = None         # geometría de antes de la pantalla grande
        self._hold = False               # clic izquierdo mantenido en grande (luneHold)
        self._hold_envio = 0.0
        self._salvapantallas = False
        self._salva_opts = {"fondo": True, "reloj": True}
        self._alarma_texto = None        # alarma a la vista (mostrar_alarma)
        self._bailando = False
        self._baile_opts = {}
        # Cortes 7 y 8: sentarse (ControlAsiento) y comida (ControlComida).
        self._sentada = ""               # '' | 'barra' | 'ventana'
        self._asiento_var = 0
        self._delegado_arrastre = None   # fn() → bool en cada MouseMove del arrastre
        self._arrastre_senal = False     # último arrastre_cambio emitido
        self._comida_activa = False
        self._medio_pulsado = False      # clic central pulsado sobre ella (menú secundario al soltar)
        # Cortes 9 y 10: reproductor de bailes (ControlMMD → mmd) y Minecraft (decir_reaccion).
        self._mmd_activo = False         # hay un baile pedido (de «cargar» a parar/parado/error)
        self._mmd_id = ""
        self._mmd_en_pagina = False      # el «cargar» llegó a una página cargada (si recarga, se pierde)
        self._mmd_pendiente = []         # [(orden, arg)] pedidos antes de que cargara la página
        self._mmd_pausa_pedida = False   # lo último que pidió el controlador: en pausa
        self._mmd_pausa_oculta = False   # en pausa porque la ventana está oculta (sigue al mostrarla)
        self._bailes_publicados = False
        self._aviso_d1_dado = False
        self._ai = ai_manager
        self._worker = None
        self._pensando = False
        self._click_through = False      # modo fantasma TOTAL (bandeja)
        self._fantasma_auto = False      # ahora mismo dejando pasar clics (auto)
        self._sobre_modelo = True        # última respuesta de la página
        self._arrastre = None
        self._durmiendo = False
        self._revert_token = 0
        self.cerrado = False
        self.modelo: Path | None = None
        # Chat con la mascota: quien lleva la app pone on_chat(texto) -> bool y,
        # opcional, proveedor_chat() -> 'ollama'|… (para precalentar el modelo local).
        self.on_chat = None
        self.proveedor_chat = None
        self._chat = ChatMascota(self)
        self._clic = DesambiguadorClic(self._clic_simple, self.abrir_chat, self)
        self._sonidos_publicados = False
        # Corte 3: regla de sueño, frases y lo que la regla necesita saber.
        self._regla = ReglaSueno.desde_config(self.config)
        self._frases = frases_para(reloj=time.monotonic)   # del personaje activo
        self._pagina_lista = False       # loadFinished(True): ya hay burbuja y luneSleep
        self._estado_visual = "normal"   # lo último pedido a la página (o que ella avisó)
        self._estado_gen = 0             # sube con cada cara pedida desde aquí (setEmocion)
        self._lote_viejo = False         # el lote de eventos en curso es de antes de la última cara
        self._hablando = False           # la voz TTS está sonando
        self._b64 = None                 # captura del comentario de pantalla en curso
        self._automatico = False         # el comentario en curso lo lanzó el temporizador
        self._liberada = False           # página descartada (VRM oculta un rato): se recarga al volver
        self._sueno_pedido_t = None      # monotonic de lo último de un «duérmete» vigente
        self._burbuja_ia = False         # la IA está escribiendo en la burbuja…
        self._burbuja_ia_hasta = 0.0     # …y la deja a la vista hasta aquí (monotonic)
        self._burbuja_ultimo = ""
        self._aparecer_pendiente = True  # la frase de «aparecer», al estar visible y cargada

        self.render_pedido = render or (str(self.config.get("avatar", "render", "animado")) if self.config else "animado")
        self.render = self._elegir_render(render)

        self.setWindowTitle("Lune")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus   # nunca roba el foco a lo que usas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._escala = self._escala_obj = self._cfg_float("vrm_escala", 1.0)
        self.resize(*self._tamano_ventana())

        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = RAIZ / "assets" / f"lune_icon.{ext}"
            if ruta.exists():
                self._icono = QIcon(str(ruta)); self.setWindowIcon(self._icono); break

        rutas_extra = {RUTA_MODELO: self.modelo} if self.modelo else {}
        self._servidor = ServidorEstatico(DIR_WEB, rutas_extra=rutas_extra)
        self._servidor.iniciar()

        self.web = QWebEngineView()
        # Guarda de navegación ANTES de cargar nada (y antes de tocar la página y sus
        # ajustes: setPage la cambia): solo el servidor local de la mascota.
        self._asegurar_navegacion()
        self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Clic derecho = menú radial (al soltar): nada de menú contextual de Chromium.
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        try:
            self.web.page().setBackgroundColor(QColor(0, 0, 0, 0))
            s = self.web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
            # El audio de la página (luneSfx, alarmas, bailes) lo arranca Python con
            # runJavaScript, sin un clic del usuario: sin esto Chromium lo bloquea.
            s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        self.web.loadFinished.connect(self._on_cargado)
        self.web.setUrl(QUrl(self._url_pagina()))
        self.setCentralWidget(self.web)

        self._restaurar_posicion()
        if bandeja:
            self._construir_bandeja()

        # Menú radial: si la página no contesta a luneCabeza, se ancla por geometría.
        self._timer_ancla = QTimer(self)
        self._timer_ancla.setSingleShot(True)
        self._timer_ancla.timeout.connect(self._ancla_vencida)

        # Comentarios automáticos de pantalla (opcional, apagado por defecto).
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._comentar_auto)
        self._sondeo_listo.connect(self._on_sondeo)
        self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))

        # Solo VRM: cursor global → la página.
        self._timer_cursor = QTimer(self)
        self._timer_cursor.setInterval(int(1000 / self.CURSOR_HZ))
        self._timer_cursor.timeout.connect(self._enviar_cursor)
        # Los dos renders: sueño por inactividad (ReglaSueno) y la vuelta a dormirse
        # tras la respuesta a un «duérmete».
        self._timer_sueno = QTimer(self)
        self._timer_sueno.setSingleShot(True)
        self._timer_sueno.timeout.connect(self._sueno_vencido)
        self._timer_sueno_pedido = QTimer(self)
        self._timer_sueno_pedido.setSingleShot(True)
        self._timer_sueno_pedido.timeout.connect(self._volver_a_dormir)
        # VRM oculta un rato → se libera su página (WebGL) hasta que vuelva a verse.
        self._timer_liberar = QTimer(self)
        self._timer_liberar.setSingleShot(True)
        self._timer_liberar.timeout.connect(self._liberar_pagina)
        # Vuelta a normal de un estado con ms (set_estado(…, ms)).
        self._timer_revertir = QTimer(self)
        self._timer_revertir.setSingleShot(True)
        self._timer_revertir.timeout.connect(self._revertir)
        self._ultimo_cursor = (None, None)
        # Escala con la rueda del ratón (se materializa como tamaño de ventana).
        self._timer_escala = QTimer(self)
        self._timer_escala.setInterval(16)
        self._timer_escala.timeout.connect(self._paso_escala)
        self._t_escala = 0.0

        # Los dos renders: cola de eventos de la página → evento_js (independiente
        # del cursor; ver docstring del módulo).
        self._timer_eventos = QTimer(self)
        self._timer_eventos.setInterval(int(1000 / self.EVENTOS_HZ))
        self._timer_eventos.timeout.connect(self._vaciar_eventos)
        self._eventos_en_vuelo = 0.0     # monotonic de la petición sin respuesta (0 = ninguna)
        # Lo que pasa en la página → frases, sueño y estado visual (y a quien escuche).
        self.evento_js.connect(self._on_evento_mascota)

        # Modo fantasma total guardado (como la mascota de sprites): se aplica ya mostrada.
        if self._cfg_bool("click_through", False):
            QTimer.singleShot(300, self._fantasma_guardado)
        self._estado_bus(render=self.render, visible=False)

    def _fantasma_guardado(self):
        """Modo fantasma total guardado en config, ya con la ventana creada."""
        if not self.cerrado:
            self.set_click_through(True)

    # ── Render, modelo y página ──────────────────────────────────────────────────
    def _asegurar_navegacion(self):
        """PaginaLune en la vista (ui/web_shell.asegurar_pagina) con el origen del
        servidor local de la mascota y NavigateOnDropEnabled apagado. Devuelve la
        página o None si no se pudo (queda registrado)."""
        if not callable(getattr(self.web, "setPage", None)):
            _log("[companion] la vista no admite otra página: sin guarda de navegación")
            return None
        try:
            from ui.web_shell import asegurar_pagina
            return asegurar_pagina(self.web, QUrl(self._servidor.url(PAGINAS[self.render])))
        except Exception as e:                       # noqa: BLE001 — la mascota sigue igual
            _log(f"[companion] no pude poner la guarda de navegación: {e}")
            return None

    def _elegir_render(self, render: str | None) -> str:
        r = render or (str(self.config.get("avatar", "render", "animado")) if self.config else "animado")
        if r != "vrm":
            return "animado"
        from nucleo import vrm
        self.modelo = vrm.ruta_modelo(self.config)
        if self.modelo is None:
            _log("[companion] modo VRM pedido pero no hay ningún .vrm (modelo_vrm/): uso el animado")
            return "animado"
        return "vrm"

    def _tamano_ventana(self):
        if self.render != "vrm":
            return TAMANO_ANIMADO
        w, h = TAMANOS_VRM.get(self._cfg_str("vrm_tamano", "normal"), TAMANOS_VRM["normal"])
        return max(120, round(w * self._escala)), max(180, round(h * self._escala))

    def _url_pagina(self) -> str:
        pagina = PAGINAS[self.render]
        if self.render != "vrm":
            return self._servidor.url(pagina)
        try:
            v = int(self.modelo.stat().st_mtime)
        except OSError:
            v = 0
        enc = self._cfg_str("vrm_encuadre", "retrato")
        return (self._servidor.url(pagina)
                + f"?src={RUTA_MODELO}&v={v}&enc={enc if enc in ENCUADRES else 'retrato'}")

    def recargar_modelo(self):
        """El personaje activo cambió: sus frases de mascota y, si tiene otro .vrm, el
        modelo (sin cerrar la ventana) con su calibración (`aplicar_params_vrm`).
        Si esta ventana arrancó degradada a vídeo por falta de modelo y ahora ya hay
        uno, pide que la recreen (la página de vídeo no puede volverse 3D)."""
        self._actualizar_frases()
        from nucleo import vrm
        if self.render != "vrm":
            if self.render_pedido == "vrm" and vrm.ruta_modelo(self.config) is not None:
                self.recrear.emit()
            return
        nuevo = vrm.ruta_modelo(self.config)
        if nuevo is None:
            # Ya no queda ningún .vrm (se borró el que enseñaba): no se queda con un
            # modelo borrado (/vrm/actual.vrm daría 404 al recargar). Quien la creó la
            # recrea con la config actual, que sin modelo cae a la animada.
            _log("[companion] el modelo 3D ya no existe y no hay otro: vuelvo a la animada")
            self.recrear.emit()
            return
        if nuevo == self.modelo:
            return
        self.modelo = nuevo
        self._servidor.publicar(RUTA_MODELO, nuevo)
        try:
            v = int(nuevo.stat().st_mtime)
        except OSError:
            v = 0
        self._js(f"window.luneCargarModelo && window.luneCargarModelo({_js_str(f'{RUTA_MODELO}?v={v}')})")
        self.aplicar_params_vrm()

    def _actualizar_frases(self):
        """Las frases de la mascota del personaje activo (el cooldown se conserva)."""
        try:
            from nucleo import personajes
            self._frases.set_personaje(personajes.get_activo())
        except Exception as e:
            _log(f"[companion] no pude cargar las frases del personaje: {e}")

    def aplicar_params_vrm(self):
        """Calibración del modelo actual (modelo_vrm/<modelo>.lune.json) + pesos de
        seguimiento de config → window.luneParams. Solo en render VRM (no-op en la
        animada). La página guarda la llamada si su módulo aún no cargó."""
        if self.render != "vrm" or self.cerrado or self.modelo is None:
            return
        try:
            from nucleo import vrm
            params = vrm.params_modelo_json(self.modelo.name, self.config)
        except Exception as e:
            _log(f"[companion] no pude leer la calibración del modelo: {e}")
            return
        self._js(f"window.luneParams && window.luneParams({_js_str(params)})")

    # ── Puente Python → JS ───────────────────────────────────────────────────────
    def _js(self, codigo: str, callback=None):
        try:
            if callback is None:
                self.web.page().runJavaScript(codigo)
            else:
                self.web.page().runJavaScript(codigo, callback)
        except Exception:
            pass

    def _on_cargado(self, ok):
        try:
            fp = self.web.focusProxy()
            if fp is not None:
                fp.installEventFilter(self)   # arrastrar pinchando sobre la mascota
        except Exception:
            pass
        if not ok:
            return
        self._pagina_lista = True
        if self.render == "vrm":
            self._timer_cursor.start()
            self.aplicar_params_vrm()
        if self._durmiendo:                          # la página se recargó dormida: que siga así
            self._js("window.luneSleep && window.luneSleep(true)")
        elif self._estado_visual != "normal":        # la cara pedida antes de cargar (o de recargar)
            self._js(f"window.setEmocion && window.setEmocion({_js_str(self._estado_visual)})")
        if self._hablando:
            self._js_hablando()
        self._rearmar_sueno()
        if self.isVisible():
            self._timer_eventos.start()
            self._aplicar_fps()                      # avatar.fps_max (o el del modo juego)
        self._reaplicar_tema()                       # la página recargada vuelve al cian
        self._reaplicar_ocio()                       # pantalla grande, alarma, baile…
        self._reaplicar_vida()                       # sentada, comida en la mano
        self.cargar_pack_sonidos()
        self._aparecer()
        self._reaplicar_mmd()                        # el baile pedido antes de cargar (o perdido al recargar)

    # ── Pack de sonidos de reacción (nucleo/packs_sonido.py → luneSonidos) ────────
    def cargar_pack_sonidos(self):
        """Carga en la página el pack de avatar.pack_sonidos (o el de por defecto) con
        el volumen avatar.volumen_sfx. También al cambiarlos en Ajustes."""
        try:
            from nucleo import packs_sonido as ps
            if not self._sonidos_publicados and self._servidor is not None:
                # Los packs propios viven en sonidos/ (el de por defecto, en ui_web/assets/sfx).
                self._servidor.publicar_carpeta(ps.PREFIJO_WEB, ps.CARPETA_SONIDOS)
                self._sonidos_publicados = True
            pack = ps.obtener_pack(self._cfg_str("pack_sonidos", ps.PACK_DEFECTO)) or ps.pack_por_defecto()
            web = ps.pack_para_web(pack) if pack is not None else None
        except Exception as e:
            _log(f"[companion] no pude preparar el pack de sonidos: {e}")
            web = None
        vol = max(0.0, min(1.0, self._cfg_float("volumen_sfx", 0.7)))
        # El JSON del pack va el último: nada de lo que traiga (nombres…) se reemplaza.
        self._js(_JS_PACK.replace("__VOL__", f"{vol:.3f}")
                 .replace("__PACK__", json.dumps(web, ensure_ascii=False)))

    # ── Estado compartido (BusEstado opcional) ───────────────────────────────────
    def set_bus_estado(self, bus):
        """Engancha (o suelta, con None) el BusEstado de ServiciosEscritorio y le
        vuelca el estado actual de esta ventana."""
        self._bus_estado = bus
        self._estado_bus(render=self.render, visible=self.isVisible() and not self.cerrado,
                         durmiendo=self._durmiendo, pensando=self._pensando,
                         arrastrando=bool(self._arrastre and self._arrastre.get("movido")))

    def _estado_bus(self, **campos):
        bus = getattr(self, "_bus_estado", None)
        if bus is None:
            return
        try:
            bus.actualizar(**campos)
        except Exception as e:
            _log(f"[companion] no pude actualizar el estado compartido: {e}")

    # ── Estado / emoción ─────────────────────────────────────────────────────────
    def set_estado(self, estado: str, ms: int = 0):
        """Estado visual ('happy', 'thinking', …). Con ms > 0 vuelve solo al idle.
        'sleeping' la duerme (como la herramienta, sin la regla de inactividad)."""
        if estado == "sleeping":
            self._dormir()
            return
        self._aplicar_estado(estado, ms, _ESTADO_A_EMOCION.get(estado, estado))

    def _aplicar_estado(self, estado: str, ms: int, emocion: str):
        self._despertar()
        self._estado_visual = str(estado or "normal")
        self._estado_gen += 1                # los avisos 'estado' ya en vuelo son más viejos
        self._js(f"window.setEmocion && window.setEmocion({_js_str(estado)})")
        self._estado_bus(emocion=str(emocion or "neutral"))
        self._revert_token += 1
        # Vuelta a normal con un temporizador HIJO (no un singleShot con lambda: si la
        # ventana se destruye antes, se va con ella en vez de tocar un objeto borrado).
        if ms and ms > 0 and estado != "normal":
            self._timer_revertir.start(int(ms))
        else:
            self._timer_revertir.stop()

    def _revertir(self, token: int | None = None):
        if token is not None and token != self._revert_token:
            return
        if not self._pensando:
            self._estado_visual = "normal"
            self._estado_gen += 1
            self._js("window.setEmocion && window.setEmocion('normal')")
            self._estado_bus(emocion="neutral")

    def set_emocion(self, emocion: str, ms: int = 0):
        e = (emocion or "").lower()
        estado = EMOCION_A_ESTADO.get(e, "normal")
        self._aplicar_estado(estado, ms, e if e in EMOCION_A_ESTADO else "neutral")

    def set_act(self, act: dict, ms: int = 0):
        if isinstance(act, dict):
            self.set_emocion(str(act.get("emotion", "neutral")), ms)

    def set_hablando(self, hablando: bool):
        """La voz está sonando: el avatar VRM mueve la boca (no-op en animado).
        Hablar la despierta; al callar, la inactividad cuenta desde ahí (y si le
        acababan de pedir que se durmiera, vuelve a dormirse). Llega también con la
        ventana oculta (si no, se quedaría «hablando» para siempre); la página lo
        recibe igual y al mostrarse/recargarse se le vuelve a decir."""
        hablando = bool(hablando)
        # Un «duérmete» sigue vigente mientras la voz suena: se mira ANTES de apuntar
        # que calló, o un tramo de voz de más de GRACIA_SUENO_S lo daría por caducado.
        pedido = self._sueno_pedido_vigente()
        self._hablando = hablando
        if hablando:
            self._despertar()
        else:
            if pedido:
                self._sueno_pedido_t = time.monotonic()
                self._timer_sueno_pedido.start(PAUSA_VOLVER_A_DORMIR_MS)
            self._rearmar_sueno()
        self._estado_bus(hablando=hablando)
        self._js_hablando()

    def _js_hablando(self):
        """Boca del VRM y sonidos de reacción según la voz (también para resincronizar
        la página al mostrarse o recargarse)."""
        on = "true" if self._hablando else "false"
        self._js(f"window.luneSpeak && window.luneSpeak({on})")
        # La voz TTS manda: calla la «voz» de reacción del pack y el tecleo.
        self._js(_js_sonidos("hablando", on))

    # ── Chat con la mascota: burbuja y cajita (ui/chat_mascota.py) ───────────────
    def burbuja_texto(self, texto: str, tipeado: bool = False):
        """Texto en la burbuja (sin programar el cierre). En streaming se llama con el
        texto acumulado; `tipeado` = escribirlo letra a letra (respuesta de golpe)."""
        t = str(texto or "").strip()
        if not t or self.cerrado:
            return
        self._despertar()
        self._burbuja_ia, self._burbuja_ultimo = True, t   # las frases de la mascota esperan
        s = _js_str(t)
        fn = "comentarTipeado" if tipeado else "burbujaTexto"
        self._js(f"window.{fn} ? window.{fn}({s}) : (window.comentar && window.comentar({s}))")
        self._tecleo(True)

    def burbuja_fin(self, ms: int | None = None):
        """La burbuja se oculta a los `ms` (sin ms: el tiempo de lectura de la página)."""
        if self.cerrado:
            return
        arg = "" if ms is None else str(max(0, int(ms)))
        self._js(f"window.burbujaFin && window.burbujaFin({arg})")
        self._tecleo(False)
        if self._burbuja_ia:
            vista = ms_lectura(self._burbuja_ultimo) if ms is None else max(0, int(ms))
            self._burbuja_ia = False
            self._burbuja_ia_hasta = max(self._burbuja_ia_hasta, time.monotonic() + vista / 1000.0)

    def _tecleo(self, on: bool):
        """Blips de tecleo mientras la burbuja escribe (features.sonido_tecleo)."""
        try:
            activo = bool(self.config and self.config.feature("sonido_tecleo", False))
        except Exception:
            activo = False
        if activo or not on:
            self._js(_js_sonidos("tecleo", "true" if (on and activo) else "false"))

    def abrir_chat(self):
        """Doble clic / bandeja: la cajita para escribirle, anclada bajo la mascota."""
        if self.cerrado:
            return
        self._clic.cancelar()
        self._despertar(usuario=True)
        self._chat.abrir()

    def _clic_simple(self):
        """Clic limpio (sin doble clic detrás): comenta la pantalla. No con una alarma
        a la vista (ese clic es para apagarla), en pantalla grande ni con comida en la mano."""
        if self._alarma_texto is not None or self._grande_fase is not None or self._comida_activa:
            return
        if not self.cerrado and self.isVisible():
            self.comentar_pantalla()

    # ── Cola de eventos de la página → evento_js (los dos renders) ───────────────
    def _vaciar_eventos(self):
        if self.web is None or self.cerrado:
            return
        ahora = time.monotonic()
        # Una petición a la vez; si la respuesta no llega (recarga de la página), a
        # los 1 s se vuelve a pedir.
        if self._eventos_en_vuelo and ahora - self._eventos_en_vuelo < 1.0:
            return
        self._eventos_en_vuelo = ahora
        gen = self._estado_gen
        self._js(EVENTOS_JS, lambda r, g=gen: self._on_eventos_js(r, g))

    def _on_eventos_js(self, resultado, gen=None):
        """Lote de luneEventos(). `gen`: _estado_gen cuando se pidió; si desde entonces
        Python pidió otra cara (setEmocion), los 'estado' de este lote son de antes y
        no la pisan (su propio aviso llega en el lote siguiente)."""
        self._eventos_en_vuelo = 0.0
        self._lote_viejo = gen is not None and gen != self._estado_gen
        try:
            for tipo, datos in _parsear_eventos(resultado):
                try:
                    self.evento_js.emit(tipo, datos)
                except Exception as e:               # un receptor roto no corta el resto
                    _log(f"[companion] evento {tipo} falló en un receptor: {e}")
        finally:
            self._lote_viejo = False

    def _on_evento_mascota(self, tipo: str, datos: dict):
        """Lo que avisa la página (lune_vrm.js / lune_anim_fisica.js): frases de la
        mascota, sueño y estado visual. El resto de eventos (bailes…) es de otros."""
        if self.cerrado:
            return
        datos = datos if isinstance(datos, dict) else {}
        if tipo == "arrastre":
            self._frase("arrastre" if datos.get("on") else "soltar")
        elif tipo in ("caricia", "mareo"):
            self._frase(tipo)
        elif tipo == "dormir":
            if not self._durmiendo:
                self._durmiendo = True
                self._estado_bus(durmiendo=True)
            self._timer_sueno.stop()
            self._frase("dormir")
        elif tipo == "despertar":
            # La página solo lo avisa en un cambio de verdad (también si la despertó
            # Python con luneSleep(false), que ya puso _durmiendo a False).
            self._durmiendo = False
            self._estado_bus(durmiendo=False)
            if self._sueno_pedido_vigente():
                # La respuesta a un «duérmete» (su voz, una emoción) la despertó en la
                # página: se vuelve a dormir al acabar, sin frase de despertar.
                self._timer_sueno_pedido.start(PAUSA_VOLVER_A_DORMIR_MS)
            else:
                self._frase("despertar")
            self._rearmar_sueno()
        elif tipo == "estado":
            nombre = str(datos.get("nombre") or datos.get("valor") or "").strip().lower()
            if nombre and not self._lote_viejo:
                self._estado_visual = nombre
                if nombre == "normal":               # acabó el gesto: vuelve al reposo
                    self._estado_bus(emocion="neutral")
        elif tipo == "grande_fase":                  # cortes 5 y 6: solo para el log
            _log(f"[companion] pantalla grande: {str(datos.get('fase'))[:20]}")
        elif tipo == "baile":
            _log(f"[companion] baile {'on' if datos.get('on') else 'off'} ({str(datos.get('estilo'))[:20]})")
        elif tipo == "mmd":                          # cortes 9 y 10: fin del baile en la página
            fase = str(datos.get("fase") or "")
            id_ = datos.get("id")
            if fase in ("parado", "error") and self._mmd_activo and id_ in (None, "", self._mmd_id):
                if fase == "error":
                    _log(f"[companion] baile: {str(datos.get('mensaje') or '')[:120]}")
                self._mmd_reset()

    # ── Frases de la mascota (lune_core/frases_mascota.py) ───────────────────────
    def _burbuja_ocupada(self) -> bool:
        """¿La burbuja es de la IA ahora (respuesta, comentario de pantalla…)?"""
        return self._pensando or self._burbuja_ia or time.monotonic() < self._burbuja_ia_hasta

    def _frase(self, evento: str) -> str | None:
        """Tira el dado de `evento` y, si toca, la frase sale en la burbuja. No pisa
        una respuesta de la IA (y entonces ni tira el dado ni gasta el cooldown)."""
        if self.cerrado or not self._pagina_lista or not self.isVisible() or self._burbuja_ocupada():
            return None
        if self._salvapantallas:
            return None                              # durmiendo en el salvapantallas: callada
        try:
            t = self._frases.elegir(evento)
        except Exception as e:
            _log(f"[companion] frase de {evento} falló: {e}")
            return None
        if t:
            self._js(f"window.comentar && window.comentar({_js_str(t)}, {MS_FRASE})")
        return t

    def _aparecer(self):
        """Frase de «aparecer» una vez por aparición (visible y con la página cargada)."""
        if self._aparecer_pendiente and self._pagina_lista and self.isVisible() and not self.cerrado:
            self._aparecer_pendiente = False
            self._frase("aparecer")

    # ── Cursor global → cabeza/ojos/torso, y fantasma automático ─────────────────
    def _enviar_cursor(self):
        if not self.isVisible() or self.web is None:
            return
        c = QCursor.pos()
        g = self.geometry()
        pantalla = self.screen() or QApplication.primaryScreen()
        sg = pantalla.geometry() if pantalla else g
        # Normalizado respecto al centro de la cara (≈ 35 % desde arriba en retrato)
        # y a media pantalla: -1..1 dentro del monitor, más allá si se sale.
        cx = g.left() + g.width() / 2
        cy = g.top() + g.height() * (ALTO_CURSOR_GRANDE if self._grande_fase is not None else 0.35)
        nx = (c.x() - cx) / max(1.0, sg.width() / 2)
        ny = (cy - c.y()) / max(1.0, sg.height() / 2)
        nx = max(-1.6, min(1.6, nx)); ny = max(-1.6, min(1.6, ny))
        dentro = g.contains(c)
        px = c.x() - g.left(); py = c.y() - g.top()
        ux, uy = self._ultimo_cursor
        if ux is not None and abs(nx - ux) < 0.002 and abs(ny - uy) < 0.002 and not dentro:
            return
        self._ultimo_cursor = (nx, ny)
        self._js(f"window.luneCursor ? window.luneCursor({nx:.4f}, {ny:.4f}, {int(px)}, {int(py)}, {'true' if dentro else 'false'}) : null",
                 self._on_cursor_respuesta if dentro else None)
        if not dentro and self._fantasma_auto and not self._click_through:
            # Fuera de la ventana no hace falta dejar pasar clics: volver a normal
            # para que al entrar sobre el avatar responda al primer clic.
            self._aplicar_transparente(False)

    def _on_cursor_respuesta(self, sobre_modelo):
        """La página dice si el cursor está sobre el avatar (píxel con alfa)."""
        if sobre_modelo is None or self._click_through or self._arrastre or self._menu_abierto:
            return
        if self._grande_fase is not None:
            return                                   # en grande recibe los clics (sin fantasma automático)
        sobre = bool(sobre_modelo)
        if sobre == self._sobre_modelo:
            return
        self._sobre_modelo = sobre
        if self._cfg_bool("vrm_fantasma_auto", True):
            self._aplicar_transparente(not sobre)

    def _aplicar_transparente(self, activo: bool):
        """WS_EX_TRANSPARENT (Windows) o WA_TransparentForMouseEvents: deja pasar los clics."""
        activo = bool(activo)
        if self._fantasma_auto == activo and not self._click_through:
            return
        self._fantasma_auto = activo
        if sys.platform == "win32":
            try:
                import win32gui, win32con
                hwnd = int(self.winId())
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                ex = (ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT) if activo \
                    else (ex & ~win32con.WS_EX_TRANSPARENT)
                # WS_EX_TRANSPARENT solo afecta al hit-test: no hace falta SWP_FRAMECHANGED
                # (forzaría un repintado de la ventana translúcida = parpadeo al cruzar el borde).
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
                return
            except Exception:
                pass
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)

    def event(self, ev):
        # Si la ventana llega a activarse (Alt-Tab, bandeja) no puede quedarse
        # "fantasma": vuelve a recibir clics hasta el siguiente sondeo del cursor.
        if ev.type() == QEvent.Type.WindowActivate and not self._click_through and self._fantasma_auto:
            self._sobre_modelo = True
            self._aplicar_transparente(False)
        return super().event(ev)

    # ── Escala con la rueda (Mate-Engine: ±0.1 por muesca, con suavizado) ────────
    ESCALA_MIN, ESCALA_MAX, ESCALA_PASO = 0.6, 1.5, 0.1

    def _rueda(self, ev) -> bool:
        if self._grande_fase is not None:
            return True                              # en pantalla grande no escala (ni hace zoom)
        if self.render != "vrm" or self._arrastre or self._click_through:
            return False
        muescas = ev.angleDelta().y() / 120.0
        if not muescas:
            return False
        self._despertar(usuario=True)
        self._escala_obj = max(self.ESCALA_MIN, min(self.ESCALA_MAX, self._escala_obj + muescas * self.ESCALA_PASO))
        if not self._timer_escala.isActive():
            self._t_escala = time.monotonic()
            self._timer_escala.start()
        return True

    def _paso_escala(self):
        ahora = time.monotonic()
        dt = max(1e-3, min(0.05, ahora - self._t_escala)); self._t_escala = ahora
        f = 1 - (1 - 0.3) ** (dt * 60)              # lerp exponencial normalizado a 60 fps
        self._escala += (self._escala_obj - self._escala) * f
        llegado = abs(self._escala_obj - self._escala) < 0.003
        if llegado:
            self._escala = self._escala_obj
            self._timer_escala.stop()
        w, h = self._tamano_ventana()
        if (w, h) != (self.width(), self.height()):
            g = self.geometry()                     # crece desde los pies, centrada
            self.setGeometry(g.center().x() - w // 2, g.bottom() - h, w, h)
        if llegado:                                 # config.json se escribe UNA vez, al final
            self._asegurar_en_pantalla()
            if self.config:
                self.config.set("avatar", "vrm_escala", round(self._escala, 3))
            self._guardar_posicion()

    def wheelEvent(self, ev):
        if not self._rueda(ev):
            super().wheelEvent(ev)

    # ── Sueño (los dos renders; nucleo/sueno.ReglaSueno) ─────────────────────────
    @property
    def durmiendo(self) -> bool:
        """¿Está dormida? (lo consultan nucleo/sueno.herramienta_dormir/despertar)."""
        return self._durmiendo

    def dormir(self) -> bool:
        """Que se duerma YA (herramienta mascota_dormir, menús). True si se durmió o ya
        dormía; False si ahora no puede (cerrada, arrastrándola, pensando un
        comentario, en llamada, con alarma…). Aquí no cuenta la lista blanca de
        estados de la regla (se lo han pedido), pero sí lo que la ocupa. Si la voz
        está sonando se duerme al callar (y devuelve True: se va a dormir)."""
        if self.cerrado:
            return False
        if self._durmiendo:
            self._sueno_pedido_t = time.monotonic()
            return True
        if self._motivo_no_dormir(forzado=True):
            return False
        self._sueno_pedido_t = time.monotonic()
        if self._hablando:
            return True                          # set_hablando(False) → _volver_a_dormir
        self._dormir()
        return self._durmiendo

    def despertar(self) -> bool:
        """Que se despierte (herramienta mascota_despertar). True si está despierta
        (ya lo estaba o se despertó); False si la ventana está cerrada."""
        if self.cerrado:
            return False
        self._despertar(usuario=True)
        return not self._durmiendo

    def _sueno_pedido_vigente(self) -> bool:
        """¿Hay un «duérmete» pendiente? Mientras la voz suena no caduca (un tramo
        largo no cuenta); callada, dura GRACIA_SUENO_S desde lo último de la respuesta."""
        t = self._sueno_pedido_t
        if t is None:
            return False
        return self._hablando or time.monotonic() - t < GRACIA_SUENO_S

    def _estado_regla(self, forzado: bool = False):
        """Lo que mira la ReglaSueno: el EstadoMascota del bus (con sus banderas:
        llamada, alarma, pantalla grande…) o, sin bus, el estado visual. Una emoción
        vieja cuenta como reposo; una actividad (thinking, talking…) no. Con
        `forzado` (la herramienta) solo cuentan las banderas, y la voz tampoco
        (dormir() la espera)."""
        visual = self._estado_visual if self._estado_visual in ESTADOS_ACTIVIDAD else "normal"
        if forzado:
            visual = "normal"
        bus = getattr(self, "_bus_estado", None)
        if bus is None:
            return visual
        try:
            est = dataclasses.asdict(bus.actual())
        except Exception:
            return visual
        est["emocion"] = "neutral" if visual == "normal" else visual
        est["durmiendo"] = False                 # manda self._durmiendo
        if forzado:
            est["hablando"] = False
        return est

    def _motivo_no_dormir(self, forzado: bool = False) -> str:
        """Por qué no puede dormirse ahora ('' si puede)."""
        if self.cerrado:
            return "la ventana está cerrada"
        if self._pensando:
            return "está pensando un comentario"
        if self._menu_abierto and not forzado:
            return "el menú está abierto"
        if self._grande_fase is not None and not forzado:
            return "está en pantalla grande"
        if self._bailando and not forzado:
            return "está bailando"
        if self._mmd_activo:                         # un baile de la biblioteca: ni pidiéndoselo
            return "está bailando"
        if self._comida_activa:
            return "está comiendo"
        return self._regla.motivo_no(
            self._estado_regla(forzado),
            arrastrando=bool(self._arrastre and self._arrastre.get("movido")),
            hablando=self._hablando and not forzado)

    def _rearmar_sueno(self, ms: int | None = None):
        """(Re)cuenta la inactividad desde ahora: avatar.dormir_min (0 = nunca). Solo
        con la página cargada (sin ella no hay luneSleep) y despierta."""
        self._timer_sueno.stop()
        self._regla = ReglaSueno.desde_config(self.config)
        if self.cerrado or self._durmiendo or not self._pagina_lista or not self._regla.activa:
            return
        if self._grande_fase is not None or self._comida_activa or self._mmd_activo:
            return                                   # en pantalla grande, con comida o con un baile no se duerme sola
        self._timer_sueno.start(int(ms) if ms is not None else int(self._regla.umbral_s * 1000))

    def _sueno_vencido(self):
        """Pasó avatar.dormir_min sin tocarla ni hablarle: se duerme si la regla deja
        (si no —hablando, arrastrándola, pensando…—, se vuelve a mirar en un rato)."""
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
            return                               # al callar se vuelve a armar
        if self._motivo_no_dormir(forzado=True):
            self._sueno_pedido_t = None
            return
        self._dormir()

    def _dormir(self):
        """Se duerme (luneSleep en las dos páginas). La frase y lo demás llegan con el
        evento 'dormir' de la página."""
        if self._durmiendo or self._pensando or self.cerrado:
            return
        self._durmiendo = True
        self._timer_sueno.stop()
        self._estado_bus(durmiendo=True)
        self._js("window.luneSleep && window.luneSleep(true)")

    def _despertar(self, usuario: bool = False):
        """Despierta (si dormía) y rearma el sueño. `usuario`: la ha tocado o le
        escribe → se olvida un «duérmete» pendiente. Si no (voz, emoción de la IA) y
        hay uno vigente, se vuelve a dormir cuando acabe la respuesta."""
        if usuario:
            self._sueno_pedido_t = None
            self._timer_sueno_pedido.stop()
        elif self._sueno_pedido_vigente():
            self._sueno_pedido_t = time.monotonic()
            self._timer_sueno_pedido.start(PAUSA_VOLVER_A_DORMIR_MS)
        if self._durmiendo:
            self._durmiendo = False
            self._estado_bus(durmiendo=False)
            self._js("window.luneSleep && window.luneSleep(false)")
        self._rearmar_sueno()

    # ── Comentario de pantalla ───────────────────────────────────────────────────
    def comentar_pantalla(self):
        """Comentario MANUAL (clic, bandeja, botón de la ventana): con un modelo local
        sin visión puede usar la nube con la captura (avisando una vez)."""
        self._comentar(automatico=False)

    def _comentar_auto(self):
        """Comentario AUTOMÁTICO (avatar.comentarios_cada_min): nadie lo pidió en ese
        momento, así que la captura nunca sale a la nube; sin visión local, comenta
        por la ventana activa (texto)."""
        if self._grande_fase is not None:
            return
        self._comentar(automatico=True)

    def _comentar(self, automatico: bool):
        if self._pensando or self._ai is None or self.cerrado:
            return
        if self._en_juego():
            # Modo juego: ni captura ni comentario (anticheat y rendimiento). Al manual
            # se le contesta en la burbuja si se la ve.
            if not automatico and self.isVisible() and self._pagina_lista and not self._burbuja_ocupada():
                self._js(f"window.comentar && window.comentar({_js_str(_AVISO_JUEGO)}, {MS_AVISO_JUEGO})")
            return
        if not str(datos.openrouter_key() or "").strip():
            # Solo nube (10.9): sin clave, el manual lo dice (y dónde ponerla); el
            # automático calla para no insistir cada pocos minutos. Nunca el modelo local.
            if not automatico:
                self._decir(AVISO_MASCOTA_SIN_NUBE, "thinking")
            return
        self._despertar()
        # La captura, antes de ponerse a «pensar» (que no salga en ella); si al final
        # el comentario va sin imagen, se tira aquí mismo.
        self._b64 = self._capturar()
        self._automatico = bool(automatico)
        self._pensando = True
        self._estado_bus(pensando=True)
        self._reintentado = False
        self._js("window.pensando && window.pensando()")
        self.set_estado("thinking")
        self._sondear()

    def _sondear(self):
        """10.9: la mascota comenta solo con la nube, así que ya no se sondea Ollama
        (con él apagado eran hasta 3 + 3 s de espera): sigue directo en _on_sondeo.
        `_sondear_ollama` queda por si vuelve a hacer falta."""
        self._on_sondeo({"local": False})

    def _sondear_ollama(self):
        """(Sin uso desde 10.9.) ¿Ollama responde y su modelo ve imágenes? En un hilo."""
        modelo = datos.ollama_model()
        if not modelo:
            self._on_sondeo({"local": False})
            return
        url = datos.ollama_url()

        def sondear():
            r = {"local": True, "ok": False, "vision": None}
            try:
                from servicios import ollama_client
                r["ok"] = bool(ollama_client.listar_modelos(url, timeout=3)[0])
                if r["ok"]:
                    try:
                        r["vision"] = ollama_client.soporta_vision(url, modelo, timeout=3)
                    except Exception:
                        r["vision"] = None
            except Exception:
                r["ok"] = False
            try:
                self._sondeo_listo.emit(r)
            except RuntimeError:
                pass                                 # la ventana ya no existe

        threading.Thread(target=sondear, name="lune-sondeo-pantalla", daemon=True).start()

    def _on_sondeo(self, sondeo):
        """Respuesta del sondeo (hilo de Qt): elige proveedor y lanza el comentario."""
        if self.cerrado:
            if self._pensando:                       # cerrada mientras sondeaba: deja de pensar
                self._pensando = False
                self._estado_bus(pensando=False)
            return
        if not self._pensando:
            return
        proveedor, con_imagen = self._elegir_proveedor(sondeo, self._automatico)
        if con_imagen and not self._b64:
            self._pensando = False
            self._estado_bus(pensando=False)
            self._decir("No pude ver la pantalla.", "nervous")
            return
        if not con_imagen:
            self._b64 = None                         # sin imagen: la captura no sale de aquí
        self._lanzar(proveedor, con_imagen)

    # ── Proveedor con fallback ───────────────────────────────────────────────────
    def _elegir_proveedor(self, sondeo=None, automatico: bool = False):
        """
        10.9 (Diego): la mascota responde SOLO con la nube. El manual manda la captura
        (avisando la primera vez); el automático, nunca: solo el título de la ventana.
        """
        if not automatico:
            self._avisar_una_vez(_AVISO_CAPTURA_NUBE)
        return "openrouter", not automatico

    def _elegir_proveedor_local(self, sondeo=None, automatico: bool = False):
        """
        (Sin uso desde 10.9.) (proveedor, con_imagen) según el sondeo de Ollama ({local, ok, vision}):
          · Ollama responde y su modelo VE imágenes → Ollama con captura (100 % local).
          · Ollama responde pero el modelo es de solo texto → manual: la nube con
            captura si hay clave (avisando una vez); si no —o si es automático—,
            Ollama en modo texto (le contamos qué ventana hay delante).
          · Ollama no responde → la nube si hay clave (automático: sin captura, solo
            el texto de la ventana); si no, se intenta igual.
          · Sin modelo local → la nube (automático: sin captura).
        """
        hay_nube = bool(datos.openrouter_key())
        sondeo = sondeo if isinstance(sondeo, dict) else {}
        if sondeo.get("local"):
            if sondeo.get("ok"):
                if sondeo.get("vision") is False:
                    if hay_nube and not automatico:
                        self._avisar_una_vez(_AVISO_SIN_VISION_NUBE)
                        return "openrouter", True
                    self._avisar_una_vez(_AVISO_SIN_VISION_TEXTO)
                    return "ollama", False
                return "ollama", True
            if hay_nube:
                if not automatico:
                    self._js("window.comentar && window.comentar("
                             + _js_str("Ollama no responde; uso la nube un momento.") + ")")
                return "openrouter", not automatico
            return "ollama", True    # sin nube: se intenta igual y se avisa si falla
        return "openrouter", not automatico

    def _avisar_una_vez(self, texto: str):
        dados = getattr(self, "_avisos_dados", None)
        if dados is None:
            dados = self._avisos_dados = set()
        if texto in dados:
            return
        dados.add(texto)
        self._js(f"window.comentar && window.comentar({_js_str(texto)}, 9000)")
        self._reservar_burbuja(9000)

    def _lanzar(self, provider: str, con_imagen: bool = True):
        from servicios.ai_worker import AIWorker, ORIGEN_NO_CONFIABLE
        self._provider_actual = provider
        # Un comentario automático nunca sube la captura a la nube (solo a Ollama).
        if self._automatico and provider != "ollama":
            con_imagen = False
        self._con_imagen = bool(con_imagen and self._b64)
        if self._con_imagen:
            prompt, imagenes = _PROMPT_PANTALLA, [self._b64]
        else:
            prompt = _PROMPT_VENTANA.format(contexto=_contexto_ventana() or "algo sin título")
            imagenes = []
        # La captura y el título de la ventana los escribe otro: turno NO confiable,
        # sin herramientas (y lo que el modelo pida con <|CALL|> no se ejecuta aquí).
        # Efímero: ni el prompt ni la respuesta entran en el historial que comparte
        # con el chat (un título con instrucciones no contamina tu siguiente turno).
        self._retener_worker()
        self._worker = AIWorker(self._ai, prompt, provider,
                                imagenes=imagenes, permitir_acciones=False, emociones=True,
                                origen=ORIGEN_NO_CONFIABLE, efimero=True)
        self._worker.response_ready.connect(self._on_comentario)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _retener_worker(self):
        """El worker anterior (el que acaba de fallar puede estar terminando su run())
        se guarda hasta que acabe: soltar un QThread en marcha tumba la app."""
        viejos = [w for w in getattr(self, "_workers_viejos", []) if self._corre(w)]
        if self._corre(self._worker):
            viejos.append(self._worker)
        self._workers_viejos = viejos

    @staticmethod
    def _corre(w) -> bool:
        try:
            return w is not None and bool(w.isRunning())
        except (RuntimeError, AttributeError):
            return False

    def _en_juego(self) -> bool:
        """¿Hay partida? (plan del modo juego aplicado o BusEstado.juego)."""
        if self._plan_juego is not None:
            return True
        bus = getattr(self, "_bus_estado", None)
        if bus is None:
            return False
        try:
            return bool(bus.actual().juego)
        except Exception:
            return False

    def _capturar(self):
        if self._en_juego():
            return None                              # nunca capturas con un juego delante
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            w, h = img.size
            if w > 1280:
                img = img.resize((1280, max(1, int(h * 1280 / w))))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

    def _on_comentario(self, respuesta: str):
        # Los proveedores devuelven sus fallos como texto: no van a la burbuja tal cual.
        if _es_error(respuesta):
            self._fallo(respuesta)
            return
        self._pensando = False
        self._estado_bus(pensando=False)
        self._reintentado = False      # el próximo fallo puede volver a intentar la nube
        try:
            # Sin CALL ni formato antiguo (ABRIR_URL:…): aquí nunca se ejecutan ni se ven.
            hablable, control = marcadores.separar(limpiar_texto(respuesta))
            acts = [v for c, v in control if c == "act"]
        except Exception:
            hablable, acts = respuesta, []
        estado = EMOCION_A_ESTADO.get(acts[-1].get("emotion"), "happy") if acts else "happy"
        texto = (hablable or "").strip()
        if texto.strip(" .…") == "":
            texto, estado = COMENTARIO_VACIO, "thinking"
        self._decir(texto, estado)

    def _on_error(self, msg):
        self._fallo(str(msg or ""))

    def _fallo(self, msg: str):
        """Un comentario falló. Se reintenta UNA vez con la mejor alternativa:
        Ollama rechazó la captura (modelo sin visión) → nube con captura, o Ollama en
        modo texto; Ollama caído → nube. Si no hay más, Lune lo dice con gracia."""
        _log(f"[companion] comentario de pantalla falló ({getattr(self, '_provider_actual', '?')}): {msg[:200]}")
        proveedor = getattr(self, "_provider_actual", "")
        reintentado = getattr(self, "_reintentado", False)
        if proveedor == "ollama" and not reintentado:
            self._reintentado = True
            if getattr(self, "_con_imagen", False) and _parece_sin_vision(msg):
                try:
                    from servicios import ollama_client
                    ollama_client.marcar_sin_vision(datos.ollama_url(), datos.ollama_model())
                except Exception:
                    pass
                if datos.openrouter_key() and not self._automatico:
                    self._avisar_una_vez(_AVISO_SIN_VISION_NUBE)
                    self._lanzar("openrouter", True)
                else:
                    self._avisar_una_vez(_AVISO_SIN_VISION_TEXTO)
                    self._lanzar("ollama", False)
                return
            if datos.openrouter_key():
                # (automático: _lanzar le quita la imagen; va solo el texto de la ventana)
                self._lanzar("openrouter", bool(self._b64))
                return
        self._reintentado = False
        self._pensando = False
        self._estado_bus(pensando=False)
        self._decir("Uf, algo falló al mirar la pantalla.", "nervous")

    def _decir(self, texto: str, estado: str = "happy"):
        self.set_estado(estado, 9000)
        self._js(f"window.comentar && window.comentar({_js_str(texto)})")
        self._reservar_burbuja(14_000)                # comentar() la deja 14 s a la vista

    def _reservar_burbuja(self, ms: int):
        """La burbuja muestra algo de la IA durante `ms`: las frases esperan."""
        self._burbuja_ia_hasta = max(self._burbuja_ia_hasta, time.monotonic() + ms / 1000.0)

    # ── Comentarios automáticos ──────────────────────────────────────────────────
    def _aplicar_intervalo(self, minutos: int):
        try:
            minutos = int(minutos)
        except (TypeError, ValueError):
            minutos = 0
        self._min_auto = max(0, minutos)
        plan = self._plan_juego
        if minutos > 0 and not (plan is not None and plan.parar_comentarios) and self._grande_fase is None:
            self._timer.start(minutos * 60_000)
        else:
            self._timer.stop()                       # apagados, o parados en modo juego o en grande

    def _alternar_auto(self, activo: bool):
        # Al encenderlos se conserva el intervalo que hubiera (3 min si no había).
        actual = self._cfg_int("comentarios_cada_min", 0)
        minutos = (actual if actual > 0 else 3) if activo else 0
        if self.config and actual != minutos:
            self.config.set("avatar", "comentarios_cada_min", minutos)
        self._aplicar_intervalo(minutos)

    def set_comentarios_auto(self, on: bool):
        """Comentarios automáticos de pantalla sí/no (bandeja, radial, atajos)."""
        on = bool(on)
        self._alternar_auto(on)
        act = getattr(self, "act_auto", None)
        if act is not None and act.isChecked() != on:
            act.setChecked(on)

    @property
    def comentarios_auto(self) -> bool:
        """¿Están puestos los comentarios automáticos? (aunque el modo juego los pare)."""
        return self._min_auto > 0

    @property
    def click_through(self) -> bool:
        """¿Modo fantasma total (deja pasar todos los clics)?"""
        return self._click_through

    # ── Modo fantasma total (click-through) ──────────────────────────────────────
    def set_click_through(self, activo: bool):
        self._click_through = bool(activo)
        self._fantasma_auto = None            # fuerza a reaplicar
        self._aplicar_transparente(self._click_through)
        if not self._click_through:
            self._sobre_modelo = True         # que el siguiente sondeo decida
        if self.config and self.config.get("avatar", "click_through", False) != self._click_through:
            self.config.set("avatar", "click_through", self._click_through)
        act = getattr(self, "act_fantasma", None)
        if act is not None and act.isChecked() != self._click_through:
            act.setChecked(self._click_through)

    def aplicar_opciones(self):
        """Ajustes cambiaron (dormir_min, vrm_fantasma_auto, comentarios, pesos de
        seguimiento, siempre encima, fps_max): aplicar en caliente."""
        self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))
        if getattr(self, "act_auto", None) is not None:
            self.act_auto.setChecked(self._cfg_int("comentarios_cada_min", 0) > 0)
        if not self._durmiendo:
            self._rearmar_sueno()                     # dormir_min nuevo (0 = nunca)
        self._encima = self._cfg_bool("siempre_encima", True)
        self._fps_max = self._fps_de_config()
        if self.isVisible() and not self.cerrado:
            self._aplicar_encima()
            self._aplicar_fps()
        if self.render != "vrm":
            return
        self.aplicar_params_vrm()                     # avatar.peso_*/seguir_cursor
        if not self._cfg_bool("vrm_fantasma_auto", True) and not self._click_through:
            self._sobre_modelo = True
            self._aplicar_transparente(False)

    # ── Tamaño y encuadre (VRM) ──────────────────────────────────────────────────
    def aplicar_tamano(self, nombre: str):
        if self.render != "vrm" or nombre not in TAMANOS_VRM:
            return
        if self.config:
            self.config.set("avatar", "vrm_tamano", nombre)
        if self._grande_fase is not None:
            return                                   # la ventana es la del monitor: al volver
        # Crece hacia arriba/izquierda para que los pies se queden donde estaban.
        w, h = self._tamano_ventana()
        g = self.geometry()
        self.setGeometry(g.right() - w, g.bottom() - h, w, h)
        self._asegurar_en_pantalla()
        self._guardar_posicion()

    def aplicar_encuadre(self, nombre: str):
        if self.render != "vrm" or nombre not in ENCUADRES:
            return
        if self.config:
            self.config.set("avatar", "vrm_encuadre", nombre)
        self._js(f"window.luneEncuadre && window.luneEncuadre({_js_str(nombre)})")

    # ── Arrastre y clic ──────────────────────────────────────────────────────────
    # Arrastre manual (no startSystemMove) para poder distinguir un CLIC de un
    # arrastre: si sueltas sin moverte, Lune comenta la pantalla… salvo que llegue
    # un segundo clic dentro del intervalo de doble clic: entonces se abre el chat
    # (DesambiguadorClic). Mientras se arrastra, el avatar VRM recibe la velocidad
    # para balancearse.
    def _raton_press(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            # Menú radial: se abre al SOLTAR (así el soltar no cae en el propio menú).
            self._der_pulsado = not self._click_through and not self._menu_abierto
            return
        if ev.button() == Qt.MouseButton.MiddleButton:
            # Menú secundario (comida…): también al soltar.
            self._medio_pulsado = not self._click_through and not self._menu_abierto
            return
        if ev.button() != Qt.MouseButton.LeftButton or self._click_through or self._menu_abierto:
            return
        if self._grande_fase is not None:
            self._empezar_hold(ev)                   # en grande: sujetar el pelo, nada de arrastre
            return
        self._despertar(usuario=True)                # tocarla la despierta y rearma el sueño
        self._clic.cancelar()                        # pulsar de nuevo: el clic anterior no cuenta solo
        self._arrastre = {
            "origen": ev.globalPosition().toPoint(),
            "ventana": self.pos(),
            "movido": False,
            "t": time.monotonic(),
            "ultimo": ev.globalPosition().toPoint(),
            "envio": 0.0,
        }

    def _raton_move(self, ev):
        if self._hold:
            if ev.buttons() & Qt.MouseButton.LeftButton:
                self._mover_hold(ev)
            else:
                self._soltar_hold()
            return
        a = self._arrastre
        if not a or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        p = ev.globalPosition().toPoint()
        delta = p - a["origen"]
        if not a["movido"] and (abs(delta.x()) > self.UMBRAL_ARRASTRE or abs(delta.y()) > self.UMBRAL_ARRASTRE):
            a["movido"] = True
            self._estado_bus(arrastrando=True)       # el arrastre empieza al pasar el umbral, no al pulsar
            self._js("window.luneDrag && window.luneDrag(true, 0, 0)")
            self._emitir_arrastre(True)              # cortes 7/8: antes del delegado de este mismo movimiento
        if a["movido"]:
            if not self._mover_por_delegado():       # ControlAsiento ya movió la ventana (o no hay delegado)
                self.move(a["ventana"] + delta)
            ahora = time.monotonic()
            dt = max(1e-3, ahora - a["t"])
            v = p - a["ultimo"]
            a["t"], a["ultimo"] = ahora, p
            if ahora - a["envio"] >= 1 / 60:          # px/ms, para la página
                a["envio"] = ahora
                # Sentada se desliza por el borde: sin balanceo (velocidad 0).
                vx, vy = (0.0, 0.0) if self._sentada else (v.x() / dt / 1000, v.y() / dt / 1000)
                self._js(f"window.luneDrag && window.luneDrag(true, {vx:.3f}, {vy:.3f})")

    def _raton_release(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            pulsado, self._der_pulsado = self._der_pulsado, False
            if pulsado:
                self._pedir_menu(ev.globalPosition().toPoint())
            return                                   # no toca un arrastre izquierdo en curso
        if ev.button() == Qt.MouseButton.MiddleButton:
            pulsado, self._medio_pulsado = self._medio_pulsado, False
            if pulsado:
                self._pedir_menu(ev.globalPosition().toPoint(), "secundario")
            return
        if self._hold and ev.button() == Qt.MouseButton.LeftButton:
            self._soltar_hold()
            return
        a = self._arrastre
        self._arrastre = None
        if a:
            self._estado_bus(arrastrando=False)
        if not a or ev.button() != Qt.MouseButton.LeftButton:
            return
        if a["movido"]:
            self._js("window.luneDrag && window.luneDrag(false, 0, 0)")
            # Cortes 7/8: ANTES de devolverla a la pantalla y de guardar (ControlAsiento
            # decide aquí si queda sentada; sentada no se devuelve a la pantalla).
            self._emitir_arrastre(False)
            self._asegurar_en_pantalla()
            self._guardar_posicion()
        else:
            self._js("window.luneTouch && window.luneTouch()")
            # Clic limpio → comenta la pantalla, pero tras el intervalo de doble clic:
            # si llega el segundo clic, se cancela y se abre el chat.
            self._clic.clic()

    def _raton_doble(self, ev):
        """Doble clic sobre Lune → la cajita de chat (y nada de comentar la pantalla)."""
        if ev.button() != Qt.MouseButton.LeftButton or self._click_through or self._menu_abierto:
            return
        if self._grande_fase is not None:
            return                                   # en pantalla grande no se abre el chat
        self._cortar_arrastre()
        if self._comida_activa:
            self._clic.cancelar()                    # con comida en la mano, ni chat ni comentario
            return
        self._clic.doble_clic()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self._raton_press(ev)
            if ev.button() == Qt.MouseButton.MiddleButton:
                return True                          # el central es del menú: nada de autoscroll
        elif t == QEvent.Type.MouseMove:
            self._raton_move(ev)
        elif t == QEvent.Type.MouseButtonRelease:
            self._raton_release(ev)
            if ev.button() == Qt.MouseButton.MiddleButton:
                return True
        elif t == QEvent.Type.MouseButtonDblClick:
            self._raton_doble(ev)
        elif t == QEvent.Type.Wheel:
            if self._rueda(ev):
                return True                          # la página no debe hacer scroll
        return super().eventFilter(obj, ev)

    def mousePressEvent(self, ev):
        self._raton_press(ev); super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        self._raton_move(ev); super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._raton_release(ev); super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self._raton_doble(ev); ev.accept()

    # ── Menú radial (corte 4: ui/menu_radial.ControlMenuRadial) ──────────────────
    def _pedir_menu(self, punto: QPoint, tipo: str = "principal"):
        """Clic derecho (menú principal) o central (secundario: la comida) soltado
        sobre ella → menu_pedido. Arrastrándola, en modo fantasma o con el menú ya
        abierto, no."""
        if self.cerrado or self._click_through or self._menu_abierto:
            return
        if self._arrastre and self._arrastre.get("movido"):
            return
        if not self.frameGeometry().contains(punto):
            return                                   # soltó fuera de ella: se arrepintió
        self._clic.cancelar()                        # un clic izquierdo pendiente ya no comenta
        self.menu_pedido.emit(tipo, QPoint(punto))

    def set_menu_abierto(self, on: bool):
        """El menú radial se abre (True) o se cierra sobre ella. Abierto: sin
        arrastre, sin caricia, sin dormirse sola y recibiendo clics (sin fantasma
        automático). No la despierta: el radial ofrece «Despertar» si duerme."""
        on = bool(on)
        if on == self._menu_abierto:
            return
        self._menu_abierto = on
        if on:
            self._clic.cancelar()
            self._cortar_arrastre()
            self._timer_sueno.stop()
            if not self._click_through:
                self._sobre_modelo = True
                self._aplicar_transparente(False)
        else:
            self._rearmar_sueno()

    def ancla_menu(self, callback):
        """Llama a `callback(QPoint global)` con el centro de la cabeza: el de
        window.luneCabeza() si la página lo tiene (VRM: el hueso proyectado); si no,
        o si no contesta en ANCLA_TIMEOUT_MS, el 35 % del alto de la ventana."""
        if not callable(callback):
            return
        self._ancla_token += 1
        token = self._ancla_token
        self._ancla_cb = callback
        if self.cerrado or not self._pagina_lista or self.web is None:
            self._resolver_ancla(token, None)
            return
        self._timer_ancla.start(ANCLA_TIMEOUT_MS)
        self._js(_JS_CABEZA, lambda r, t=token: self._resolver_ancla(t, r))

    def _ancla_vencida(self):
        self._resolver_ancla(self._ancla_token, None)

    def _resolver_ancla(self, token: int, respuesta):
        if token != self._ancla_token or self._ancla_cb is None:
            return                                   # respuesta vieja o ya resuelta
        cb, self._ancla_cb = self._ancla_cb, None
        self._timer_ancla.stop()
        punto = None
        if not self.cerrado:
            punto = self._punto_cabeza(respuesta)
        if punto is None:
            punto = self._punto_geometria()
        try:
            cb(punto)
        except Exception as e:                       # noqa: BLE001 — un receptor roto no tumba la mascota
            _log(f"[companion] el ancla del menú falló en el receptor: {e}")

    def _punto_cabeza(self, respuesta):
        """'{"x":…,"y":…,"r":…}' (px de la página) → QPoint global, o None."""
        datos = respuesta
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except ValueError:
                return None
        if not isinstance(datos, dict):
            return None
        try:
            x, y = float(datos.get("x")), float(datos.get("y"))
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        w, h = max(1, self.web.width()), max(1, self.web.height())
        x = min(max(x, 0.0), w - 1.0)
        y = min(max(y, 0.0), h - 1.0)
        try:
            return self.web.mapToGlobal(QPoint(round(x), round(y)))
        except Exception:
            return None

    def _punto_geometria(self) -> QPoint:
        g = self.geometry()
        return QPoint(g.x() + g.width() // 2, g.y() + round(g.height() * ALTO_CABEZA))

    # ── Modo juego (corte 4: ui/modo_juego_qt.ControlModoJuego) ──────────────────
    def aplicar_plan_juego(self, plan):
        """Plan del modo juego (servicios.modo_juego.PlanJuego) o None al acabar.
        ocultar → se oculta (y vuelve al acabar solo si la ocultó esto) · fondo →
        sin «siempre encima» y detrás de todo · nada → se queda. FPS del juego
        (0 = pausada), sin comentarios automáticos ni capturas. Si el usuario la
        saca a mano durante la partida, gana él (FPS y orden Z normales)."""
        antes = self._plan_juego
        if plan is None:
            if antes is None:
                return
            self._plan_juego = None
            self._juego_mostrada_a_mano = False
            self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))
            volver, self._oculta_por_juego = self._oculta_por_juego, False
            if volver and not self.cerrado and not self.isVisible():
                self._mostrar_por_juego()
            elif self.isVisible() and not self.cerrado:
                self._aplicar_encima()
                self._aplicar_fps()
            return
        self._plan_juego = plan
        if antes is None:
            self._oculta_por_juego = False
            self._juego_mostrada_a_mano = False
        if getattr(plan, "parar_comentarios", True):
            self._timer.stop()
        if self.cerrado:
            return
        if plan.accion == "ocultar":
            if self.isVisible() and not self._juego_mostrada_a_mano:
                self._oculta_por_juego = True
                self.hide()
        else:
            if self._oculta_por_juego and not self.isVisible():
                self._oculta_por_juego = False       # el plan dejó de ser «ocultar»
                self._mostrar_por_juego()
            elif self.isVisible():
                self._aplicar_encima()
                self._aplicar_fps()

    def _mostrar_por_juego(self):
        self._mostrando_por_juego = True
        try:
            self.show()
        finally:
            self._mostrando_por_juego = False

    # ── Pantalla grande (cortes 5 y 6: ui/pantalla_grande_qt.ControlPantallaGrande) ──
    @property
    def soporta_grande(self) -> bool:
        """¿Puede ponerse en pantalla grande? (VRM o animada con la página cargada)."""
        return not self.cerrado and self._pagina_lista and self.web is not None

    @property
    def en_grande(self) -> bool:
        """¿Está en pantalla grande (de glide a fin)?"""
        return self._grande_fase is not None

    def geometria(self) -> QRect:
        """Geometría de la ventana (px lógicos) para guardarla y restaurarla."""
        return QRect(self.geometry())

    def set_geometria(self, r):
        """Pone la ventana en `r` (QRect, px lógicos) TAL CUAL: sin guardar la posición
        en la config ni devolverla a la pantalla (la pantalla grande la mueve y la
        restaura)."""
        if self.cerrado or r is None:
            return
        try:
            rect = QRect(r)
        except TypeError:
            return
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.setGeometry(rect)

    def grande_fase(self, fase: str, opciones: dict | None = None):
        """Fase de la pantalla grande (glide · entrar · salir · volver · fin) →
        luneGrande(fase, opciones) de la página. La ventana la mueve quien llama
        (set_geometria). Desde la primera fase hasta «fin», el modo grande (ver el
        docstring del módulo); «fin» vale en cualquier momento (salida inmediata)."""
        fase = str(fase or "").strip().lower()
        if fase not in FASES_GRANDE or self.cerrado:
            return
        if fase == "fin":
            self._salir_de_grande()
        else:
            nuevo = self._grande_fase is None
            self._grande_fase = fase
            if nuevo:
                self._entrar_en_grande()
        self._js(f"window.luneGrande && window.luneGrande({json.dumps(fase)}, {_js_opciones(opciones)})")
        if fase == "fin":
            self._aplicar_fps()                      # después del fin de la página: vuelve a fps_max

    def _entrar_en_grande(self):
        self._geom_normal = QRect(self.geometry())
        self._clic.cancelar()
        self._cortar_arrastre()
        if self._timer_escala.isActive():
            self._timer_escala.stop()
            self._escala_obj = self._escala
        self._chat.cerrar()
        self._timer.stop()                           # sin comentarios automáticos
        self._timer_sueno.stop()                     # ni sueño automático
        if not self._click_through:
            self._sobre_modelo = True
            self._aplicar_transparente(False)        # recibe los clics (el pelo, el salvapantallas)
        self._aplicar_fps()

    def _salir_de_grande(self):
        estaba = self._grande_fase is not None
        self._soltar_hold()
        self._grande_fase = None
        self._geom_normal = None
        if estaba:
            self._sobre_modelo = True
            self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))
            self._rearmar_sueno()

    def _pos_pagina(self, ev):
        try:
            p = self.web.mapFromGlobal(ev.globalPosition().toPoint())
            return int(p.x()), int(p.y())
        except Exception:
            return 0, 0

    def _empezar_hold(self, ev):
        self._clic.cancelar()
        self._hold = True
        self._hold_envio = time.monotonic()
        px, py = self._pos_pagina(ev)
        self._js(f"window.luneHold && window.luneHold(true, {px}, {py})")

    def _mover_hold(self, ev):
        ahora = time.monotonic()
        if ahora - self._hold_envio < 1.0 / HOLD_HZ:
            return
        self._hold_envio = ahora
        px, py = self._pos_pagina(ev)
        self._js(f"window.luneHold && window.luneHold(true, {px}, {py})")

    def _soltar_hold(self):
        if not self._hold:
            return
        self._hold = False
        self._js("window.luneHold && window.luneHold(false, 0, 0)")

    # ── Salvapantallas, alarma y baile (cortes 5 y 6) ────────────────────────────
    def set_salvapantallas(self, on: bool, *, fondo_oscuro: bool = True, reloj: bool = True):
        """Salvapantallas (ui/pantalla_grande_qt): la página oscurece el escritorio y
        pone la hora (luneSalvapantallas) y Lune se duerme ya, sin la regla del sueño
        (que bloquea en pantalla grande). Al quitarlo, se despierta."""
        if self.cerrado:
            return
        on = bool(on)
        self._salvapantallas = on
        self._salva_opts = {"fondo": bool(fondo_oscuro), "reloj": bool(reloj)}
        self._js(f"window.luneSalvapantallas && window.luneSalvapantallas("
                 f"{'true' if on else 'false'}, {json.dumps(self._salva_opts, sort_keys=True)})")
        if on:
            self._sueno_pedido_t = None
            self._timer_sueno_pedido.stop()
            self._dormir()
        else:
            self._despertar(usuario=True)

    @property
    def salvapantallas(self) -> bool:
        return self._salvapantallas

    def mostrar_alarma(self, texto: str, retraso_ms: int = RETRASO_ALARMA_MS):
        """Burbuja roja de la alarma en la página (luneAlarma: sale a los `retraso_ms`
        y se escribe a 35 c/s). La despierta; mientras se ve, el clic no comenta."""
        if self.cerrado:
            return
        t = " ".join(str(texto or "").split())[:MAX_TEXTO_ALARMA] or "Alarma"
        ms = _finito(retraso_ms, RETRASO_ALARMA_MS)
        ms = int(max(0.0, min(60_000.0, ms)))
        self._alarma_texto = t
        self._clic.cancelar()
        self._despertar(usuario=True)
        self._js_alarma(ms)

    def _js_alarma(self, retraso_ms: int):
        op = json.dumps({"cps": CPS_ALARMA, "retrasoMs": int(retraso_ms)}, sort_keys=True)
        self._js(f"window.luneAlarma && window.luneAlarma({_js_str(self._alarma_texto)}, {op})")

    def ocultar_alarma(self):
        """Quita la burbuja de la alarma (apagada o pospuesta)."""
        if self.cerrado:
            return
        self._alarma_texto = None
        self._js("window.luneAlarma && window.luneAlarma(null)")

    @property
    def alarma_visible(self) -> bool:
        return self._alarma_texto is not None

    def bailar(self, on: bool, opciones: dict | None = None):
        """Baile procedural (ui/baile_qt.ControlBaile) → luneBailar(on, opciones) con
        {estilo, cambiar, cambiarS, particulas}. En la animada la página pone el clip
        happy mientras baila. Bailando no se duerme sola."""
        if self.cerrado:
            return
        on = bool(on)
        self._bailando = on
        self._baile_opts = opciones_seguras(opciones) if on else {}
        if on:
            self._timer_sueno.stop()
            self._js(f"window.luneBailar && window.luneBailar(true, {_js_opciones(self._baile_opts)})")
        else:
            self._js("window.luneBailar && window.luneBailar(false)")
            self._rearmar_sueno()

    @property
    def bailando(self) -> bool:
        return self._bailando

    def pulso(self, bpm: float, fase: float, energia: float):
        """Pulso de la música (nucleo/pulso.py, como mucho 2 Hz) → lunePulso. La página
        extrapola entre medias. bpm 40–240, fase 0..1 del pulso, energía 0..1."""
        if self.cerrado or not self._pagina_lista:
            return
        b = _finito(bpm)
        if b is None or b <= 0:
            return
        b = max(BPM_MIN, min(BPM_MAX, b))
        f = _finito(fase, 0.0) % 1.0
        e = max(0.0, min(1.0, _finito(energia, 0.5)))
        self._js(f"window.lunePulso && window.lunePulso({b:.2f}, {f:.4f}, {e:.3f})")

    def _reaplicar_ocio(self):
        """La página recargó: vuelve a pedirle lo que estaba a la vista."""
        if self._grande_fase is not None:
            self._js(f"window.luneGrande && window.luneGrande({json.dumps(self._grande_fase)}, {_js_opciones({'ms': 0})})")
        if self._salvapantallas:
            self._js(f"window.luneSalvapantallas && window.luneSalvapantallas(true, "
                     f"{json.dumps(self._salva_opts, sort_keys=True)})")
        if self._alarma_texto is not None:
            self._js_alarma(0)
        if self._bailando:
            self._js(f"window.luneBailar && window.luneBailar(true, {_js_opciones(self._baile_opts)})")

    # ── Sentarse y comida (cortes 7 y 8: ui/asiento_qt y ui/comida_qt) ───────────
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
        """arrastre_cambio(on) solo en los cambios (un arrastre cortado no se cierra dos veces)."""
        on = bool(on)
        if on == self._arrastre_senal:
            return
        self._arrastre_senal = on
        try:
            self.arrastre_cambio.emit(on)
        except Exception as e:                       # noqa: BLE001 — un receptor roto no corta el arrastre
            _log(f"[companion] arrastre_cambio({on}) falló en un receptor: {e}")

    def _cortar_arrastre(self):
        """El arrastre izquierdo se corta sin soltar (menú, pantalla grande, doble clic,
        ocultarla): la página y ControlAsiento se enteran de que acabó."""
        a, self._arrastre = self._arrastre, None
        if a:
            self._estado_bus(arrastrando=False)
            if a.get("movido"):
                self._js("window.luneDrag && window.luneDrag(false, 0, 0)")
                self._emitir_arrastre(False)
        return a

    def set_arrastre_delegado(self, fn):
        """fn() → bool en cada MouseMove del arrastre (ControlAsiento). True = ya movió
        la ventana (px físicos) y aquí no se hace move; None lo quita."""
        self._delegado_arrastre = fn if callable(fn) else None

    def _mover_por_delegado(self) -> bool:
        fn = self._delegado_arrastre
        if fn is None:
            return False
        try:
            return bool(fn())
        except Exception as e:                       # noqa: BLE001 — sin delegado, el arrastre de siempre
            _log(f"[companion] el delegado del arrastre falló: {e}")
            return False

    def punto_asiento(self, cb):
        """cb({"asiento": [x, y], "sonda": [x, y]} | None): px lógicos relativos a la
        ventana (luneSeatPx: VRM con la pose que tenga; animada, el centro de abajo del
        #stage). Asíncrono."""
        if not callable(cb):
            return
        if self.cerrado or not self._pagina_lista or self.web is None:
            _llamar_cb(cb, None)
            return
        self._js(_JS_SEAT, lambda r: _llamar_cb(cb, None if self.cerrado else punto_de_pagina(r)))

    def asiento(self, on: bool, modo: str = "", variante: int = 0, cb=None):
        """Sentada (ControlAsiento): luneSentar(modo, variante) → cb(punto con la pose
        sentada completa y el encuadre de cuerpo entero | None). off → luneSentar(null).
        Frases «sentarse» y «bajar» al cambiar. Se puede llamar varias veces seguidas."""
        if self.cerrado:
            _llamar_cb(cb, None)
            return
        if not on:
            antes, self._sentada = self._sentada, ""
            self._asiento_var = 0
            if antes:
                self._js("window.luneSentar && window.luneSentar(null)")
                self._frase("bajar")
            _llamar_cb(cb, None)
            return
        m = str(modo or "").strip().lower()
        if m not in MODOS_ASIENTO:
            m = "ventana"
        try:
            v = int(variante)
        except (TypeError, ValueError):
            v = 0
        v = 0 if m == "barra" else max(0, min(VARIANTES_ASIENTO - 1, v))
        antes = self._sentada
        self._sentada, self._asiento_var = m, v
        codigo = f"window.luneSentar ? window.luneSentar({json.dumps(m)}, {v}) : null"
        if callable(cb):
            if self._pagina_lista and self.web is not None:
                self._js(codigo, lambda r: _llamar_cb(cb, None if self.cerrado else punto_de_pagina(r)))
            else:
                self._js(codigo)                     # se repite al cargar (_reaplicar_vida)
                _llamar_cb(cb, None)
        else:
            self._js(codigo)
        if not antes:
            self._frase("sentarse")

    def restaurar_orden_z(self):
        """Vuelve el orden Z de siempre (avatar.siempre_encima o el plan del modo juego)."""
        if self.cerrado or not self.isVisible():
            return
        self._aplicar_encima(forzar=True)

    def cabeza(self, cb):
        """cb((cx, cy, r) | None): la cabeza + 0.1 m (luneCabeza(0.1)) en px lógicos
        GLOBALES, el mismo espacio que QCursor.pos() (ControlComida)."""
        if not callable(cb):
            return
        if self.cerrado or not self._pagina_lista or self.web is None:
            _llamar_cb(cb, None)
            return
        self._js(_JS_CABEZA_COMIDA, lambda r: _llamar_cb(cb, self._cabeza_global(r)))

    def _cabeza_global(self, respuesta):
        if self.cerrado:
            return None
        datos = respuesta
        if isinstance(datos, (str, bytes)):
            try:
                datos = json.loads(datos)
            except ValueError:
                return None
        if not isinstance(datos, dict):
            return None
        x, y, r = _finito(datos.get("x")), _finito(datos.get("y")), _finito(datos.get("r"))
        if x is None or y is None or r is None or r <= 0:
            return None
        try:
            o = self.web.mapToGlobal(QPoint(0, 0))
        except Exception:                            # noqa: BLE001
            return None
        return (o.x() + x, o.y() + y, r)

    def comer(self, tipo: str, ms: int = MS_COMER):
        """Le pasaron la comida por la cabeza (ControlComida): luneComer(tipo, ms) (VRM:
        boca, cabeceos y happy; animada: clip happy y un rebote), frase «comer» y la
        despierta."""
        if self.cerrado:
            return
        t = "beber" if str(tipo or "").strip().lower() == "beber" else "comer"
        n = _finito(ms, MS_COMER)
        n = int(max(100.0, min(float(MS_COMER_MAX), n)))
        self._despertar(usuario=True)
        self._js(f"window.luneComer && window.luneComer({json.dumps(t)}, {n})")
        self._frase("comer")

    def set_comida_activa(self, on: bool):
        """Comida en el cursor (ControlComida): luneComidaActiva (sin caricia) y, mientras
        dure, el clic no comenta, el doble clic no abre el chat y no se duerme sola."""
        if self.cerrado:
            return
        on = bool(on)
        self._comida_activa = on
        self._js(f"window.luneComidaActiva && window.luneComidaActiva({'true' if on else 'false'})")
        if on:
            self._clic.cancelar()
            self._timer_sueno.stop()
        else:
            self._rearmar_sueno()

    @property
    def comida_activa(self) -> bool:
        return self._comida_activa

    def _reaplicar_vida(self):
        """La página recargó: vuelve a sentarla y a decirle que hay comida en la mano."""
        if self._sentada:
            self._js(f"window.luneSentar && window.luneSentar({json.dumps(self._sentada)}, {int(self._asiento_var)})")
        if self._comida_activa:
            self._js("window.luneComidaActiva && window.luneComidaActiva(true)")

    # ── Reproductor de bailes (corte 9: ui/mmd_qt.ControlMMD) ────────────────────
    @property
    def mmd_activo(self) -> bool:
        """¿Hay un baile de la biblioteca pedido a la página (de «cargar» a parar/fin)?"""
        return self._mmd_activo

    def mmd(self, orden: str, datos: dict | None = None) -> bool:
        """Orden del reproductor de bailes → window.luneMMD(orden, datos) (ver el
        docstring del módulo). False si no se acepta (cerrada, orden o datos que no
        valen, o un «cargar» que no es de esta mascota: la VRM baila vmd/vrma y la
        animada «audio»)."""
        if self.cerrado or self.web is None:
            return False
        orden = str(orden or "").strip().lower()
        if orden not in ORDENES_MMD:
            return False
        d = datos if isinstance(datos, dict) else {}
        if orden == "cargar":
            arg = datos_mmd_seguros(datos)
            if arg is None:
                _log("[companion] baile rechazado: datos que no valen")
                return False
            if (arg["tipo"] == "audio") != (self.render != "vrm"):
                _log(f"[companion] baile rechazado: un «{arg['tipo']}» no es para la mascota {self.render}")
                return False
            self._publicar_bailes()
            self._mmd_activo, self._mmd_id = True, arg["id"]
            self._mmd_en_pagina = False
            self._mmd_pausa_pedida = False
            self._mmd_pausa_oculta = False
            self._mmd_pendiente = []
            self._timer_sueno.stop()                 # bailando no se duerme sola
            self._timer_liberar.stop()
            self._mandar_mmd("cargar", arg)
            if not self.isVisible():                 # oculta: queda en pausa hasta que se la vea
                self._mmd_pausa_oculta = True
                self._mandar_mmd("pausa", {"on": True})
            if arg["tipo"] == "audio":
                self._aviso_sin_esqueleto()
            return True
        if orden == "parar":
            self._mmd_reset()
            self._mandar_mmd("parar", None)
            return True
        if orden == "pausa":
            on = d.get("on") if isinstance(datos, dict) else datos
            if on is not None and not isinstance(on, bool):
                return False
            if on is None:
                on = not self._mmd_pausa_pedida
            self._mmd_pausa_pedida = on
            if not on and not self.isVisible() and self._mmd_activo:
                self._mmd_pausa_oculta = True        # sigue al volver a verla
                return True
            if on:
                self._mmd_pausa_oculta = False       # ya no es por estar oculta
            self._mandar_mmd("pausa", {"on": on})
            return True
        clave, lo, hi = {"volumen": ("volumen", 0.0, 1.0), "offset": ("offsetMs", -500.0, 500.0),
                         "en_sitio": ("enSitio", None, None), "bucle": ("bucle", None, None)}[orden]
        v = d.get(clave) if isinstance(datos, dict) else datos
        if lo is None:
            if not isinstance(v, bool):
                return False
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) \
                or not lo <= float(v) <= hi:
            return False
        self._mandar_mmd(orden, {clave: v})
        return True

    def _mandar_mmd(self, orden: str, arg):
        """A la página si ya cargó; si no, se guarda (el último «cargar» y sus banderas) y
        se repite en _on_cargado."""
        if not self._pagina_lista:
            if orden in ("cargar", "parar"):
                self._mmd_pendiente = [] if orden == "parar" else [(orden, arg)]
            else:
                self._mmd_pendiente = [(o, a) for o, a in self._mmd_pendiente if o != orden] + [(orden, arg)]
            return
        if orden == "cargar":
            self._mmd_en_pagina = True
        self._js(_js_mmd(orden, arg))

    def _reaplicar_mmd(self):
        """Página cargada: lo pedido antes se repite; si recargó con un baile en marcha, el
        baile se perdió → evento 'mmd' error «recarga» (ControlMMD para sin avisar)."""
        if self._mmd_activo and self._mmd_en_pagina:
            id_ = self._mmd_id
            self._mmd_reset()
            self.evento_js.emit("mmd", {"fase": "error", "id": id_, "mensaje": "recarga"})
            return
        pendientes, self._mmd_pendiente = self._mmd_pendiente, []
        for orden, arg in pendientes:
            self._mandar_mmd(orden, arg)

    def _mmd_reset(self):
        """El baile acabó (parado, error, parar o recarga): vuelve el sueño y, oculta y
        VRM, el temporizador que libera la página."""
        estaba = self._mmd_activo
        self._mmd_activo = False
        self._mmd_id = ""
        self._mmd_en_pagina = False
        self._mmd_pendiente = []
        self._mmd_pausa_pedida = False
        self._mmd_pausa_oculta = False
        if estaba and not self.cerrado:
            self._rearmar_sueno()
            if self.render == "vrm" and not self.isVisible() and not self._liberada:
                self._timer_liberar.start(LIBERAR_OCULTA_MS)

    def _publicar_bailes(self):
        """bailes/ y cache/bailes/ en el servidor local de la mascota (una vez). Solo se
        sirve lo que hay DENTRO (ui/servidor_web: nada de salir con '..' ni de enlaces)."""
        if self._bailes_publicados or self._servidor is None:
            return
        try:
            from nucleo import bailes as nbl
            carpetas = ((nbl.PREFIJO_WEB, nbl.CARPETA), (nbl.PREFIJO_CACHE, nbl.CACHE))
        except Exception:                            # noqa: BLE001 — sin la biblioteca, sus rutas de siempre
            carpetas = (("/bailes/", RAIZ / "bailes"), ("/bailes_cache/", RAIZ / "cache" / "bailes"))
        try:
            for prefijo, carpeta in carpetas:
                self._servidor.publicar_carpeta(prefijo, carpeta)
            self._bailes_publicados = True
        except Exception as e:                       # noqa: BLE001 — la página dará error al pedirlos
            _log(f"[companion] no pude publicar la carpeta de bailes: {e}")

    def _aviso_sin_esqueleto(self):
        """D1: la animada no tiene esqueleto; lo dice una vez (si la burbuja está libre)."""
        if self._aviso_d1_dado or not self._pagina_lista or not self.isVisible() or self._burbuja_ocupada():
            return
        self._aviso_d1_dado = True
        self._js(f"window.comentar && window.comentar({_js_str(AVISO_SIN_ESQUELETO)}, {MS_AVISO_SIN_ESQUELETO})")

    def _mmd_al_ocultarse(self):
        """Oculta con un baile sonando: en pausa hasta que se la vuelva a ver (la canción
        suena donde se ve y, oculta, la página no dibuja)."""
        if self._mmd_activo and not self._mmd_pausa_pedida and not self._mmd_pausa_oculta:
            self._mmd_pausa_oculta = True
            self._mandar_mmd("pausa", {"on": True})

    def _mmd_al_mostrarse(self):
        if not self._mmd_pausa_oculta:
            return
        self._mmd_pausa_oculta = False
        if self._mmd_activo and not self._mmd_pausa_pedida:
            self._mandar_mmd("pausa", {"on": False})

    # ── Minecraft (corte 10: ui/minecraft_qt.ControlMinecraft) ───────────────────
    def decir_reaccion(self, texto: str, estado: str = "happy", ms: int = MS_REACCION) -> bool:
        """Una reacción a la partida en la burbuja (a máquina, 35 c/s) con su cara durante
        `ms`. False si no la dice: cerrada, oculta o sin página; en pantalla grande o
        salvapantallas; con una alarma, el menú abierto, arrastrándola, o con algo de la
        IA en la burbuja (pensando, respondiendo o aún a la vista): esa burbuja manda."""
        t = " ".join(str(texto or "").split())[:MAX_TEXTO_REACCION]
        if not t or self.cerrado or not self._pagina_lista or not self.isVisible():
            return False
        if self._grande_fase is not None or self._salvapantallas or self._alarma_texto is not None:
            return False
        if self._menu_abierto or (self._arrastre and self._arrastre.get("movido")):
            return False
        if self._burbuja_ocupada():
            return False
        n = _finito(ms, MS_REACCION)
        n = int(max(float(MS_REACCION_MIN), min(float(MS_REACCION_MAX), n)))
        self.set_emocion(str(estado or "neutral"), n)
        s = _js_str(t)
        self._js(f"window.comentarTipeado ? window.comentarTipeado({s}, {CPS_REACCION}, {n})"
                 f" : (window.comentar && window.comentar({s}, {n}))")
        return True

    # ── Orden Z, FPS y tema (corte 4) ────────────────────────────────────────────
    @property
    def siempre_encima(self) -> bool:
        return self._encima

    def set_encima(self, on: bool):
        """Siempre encima (avatar.siempre_encima). Se reafirma al mostrarse; con el
        modo juego «fondo» se aplica al acabar la partida."""
        on = bool(on)
        self._encima = on
        if self.config and self._cfg_bool("siempre_encima", True) != on:
            self.config.set("avatar", "siempre_encima", on)
        if self.isVisible() and not self.cerrado:
            self._aplicar_encima()

    def _aplicar_encima(self, forzar: bool = False):
        """HWND_TOPMOST / NOTOPMOST (o al fondo en modo juego) sobre ESTA ventana.
        Sentada, el orden Z lo lleva ControlAsiento (justo encima de su ventana o sobre
        la barra): aquí no se toca salvo `forzar` (restaurar_orden_z)."""
        if self._sentada and not forzar:
            return
        if not _ventana_nativa():
            return
        try:
            from servicios import win_ventana
            hwnd = int(self.winId())
            plan = self._plan_juego
            if plan is not None and plan.accion == "fondo" and not self._juego_mostrada_a_mano:
                win_ventana.al_fondo(hwnd)
            else:
                win_ventana.set_encima(hwnd, self._encima)
        except Exception as e:                       # noqa: BLE001
            _log(f"[companion] no pude cambiar el orden de la ventana: {e}")

    def _fps_de_config(self) -> int:
        return max(FPS_MIN, min(FPS_MAX, self._cfg_int("fps_max", 60)))

    def set_fps_max(self, n: int):
        """Tope de FPS de la página (avatar.fps_max, 15–144; en reposo la página
        baja a min(n, 30))."""
        try:
            n = max(FPS_MIN, min(FPS_MAX, int(n)))
        except (TypeError, ValueError):
            return
        self._fps_max = n
        if self.config and self._cfg_int("fps_max", 60) != n:
            self.config.set("avatar", "fps_max", n)
        if self.isVisible() and not self.cerrado:
            self._aplicar_fps()

    def _fps_efectivo(self) -> int:
        plan = self._plan_juego
        if plan is not None and not self._juego_mostrada_a_mano:
            return max(0, int(plan.fps))
        if self._grande_fase is not None:
            return min(FPS_GRANDE, self._fps_max)
        return self._fps_max

    def _aplicar_fps(self):
        """luneSetFPS con el tope vigente; con 0 (modo juego pausado) tampoco se
        manda el cursor a la página."""
        n = self._fps_efectivo() if self.isVisible() else 0
        self._js(f"window.luneSetFPS && window.luneSetFPS({n})")
        if self.render == "vrm" and self._pagina_lista and not self.cerrado:
            if n > 0:
                if not self._timer_cursor.isActive():
                    self._timer_cursor.start()
            else:
                self._timer_cursor.stop()

    def aplicar_tema(self, css_json):
        """Tema de color (nucleo/tema.css_json: mapa de variables CSS o "null") →
        window.luneTema de la página. Se guarda y se reaplica si la página recarga.
        Un JSON que no es un tema se ignora."""
        try:
            self._tema = mapa_tema(css_json)
        except ValueError as e:
            _log(f"[companion] tema ignorado: {e}")
            return
        self._reaplicar_tema()

    def _reaplicar_tema(self):
        if self._tema is _SIN_TEMA or not self._pagina_lista or self.cerrado:
            return
        self._js(_js_tema(self._tema))

    def llevar_a_esquina(self):
        """A la esquina inferior derecha de su monitor (y se guarda la posición). Sentada,
        `antes_de_colocar` deja que la baje quien la sentó (si no, la volvería a clavar)."""
        if self.cerrado or self._grande_fase is not None:
            return
        self.antes_de_colocar.emit()
        self._esquina_inferior_derecha()
        self._guardar_posicion()

    # ── Posición ─────────────────────────────────────────────────────────────────
    def _cfg_int(self, clave, default):
        try:
            return int(self.config.get("avatar", clave, default)) if self.config else default
        except (TypeError, ValueError):
            return default

    def _cfg_str(self, clave, default):
        try:
            return str(self.config.get("avatar", clave, default) or default) if self.config else default
        except Exception:
            return default

    def _cfg_float(self, clave, default):
        try:
            return float(self.config.get("avatar", clave, default)) if self.config else default
        except (TypeError, ValueError):
            return default

    def _cfg_bool(self, clave, default):
        try:
            return bool(self.config.get("avatar", clave, default)) if self.config else default
        except Exception:
            return default

    def _restaurar_posicion(self):
        x = self.config.get("avatar", "companion_x", None) if self.config else None
        y = self.config.get("avatar", "companion_y", None) if self.config else None
        if isinstance(x, int) and isinstance(y, int) and self._dentro_de_pantalla(x, y):
            self.move(x, y)
        else:
            self._esquina_inferior_derecha()

    def _dentro_de_pantalla(self, x, y) -> bool:
        for s in QApplication.screens():
            if s.availableGeometry().contains(QPoint(x + 20, y + 20)):
                return True
        return False

    def _esquina_inferior_derecha(self):
        p = self.screen() or QApplication.primaryScreen()
        if p:
            g = p.availableGeometry()
            self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)

    def _asegurar_en_pantalla(self):
        """Que al soltarla o crecer no quede fuera del monitor (Mate-Engine la devuelve).
        Sentada no: la ventana la clava ControlAsiento en el borde."""
        if self._sentada:
            return
        p = self.screen() or QApplication.primaryScreen()
        if not p:
            return
        g = p.availableGeometry()
        x = min(max(self.x(), g.left() - self.width() // 3), g.right() - self.width() * 2 // 3)
        y = min(max(self.y(), g.top()), g.bottom() - self.height() // 2)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def _guardar_posicion(self):
        if self.config:
            g = self._geom_normal if self._grande_fase is not None else None
            x, y = (g.x(), g.y()) if g is not None else (self.x(), self.y())
            self.config.set("avatar", "companion_x", x)
            self.config.set("avatar", "companion_y", y)

    # ── Bandeja ──────────────────────────────────────────────────────────────────
    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self._icono, self)
        self.tray.setToolTip("Lune · mascota 3D" if self.render == "vrm" else "Lune · companion")
        menu = self._menu_bandeja = QMenu()
        act_chat = QAction("Escribirle a Lune…", self)
        act_chat.triggered.connect(self.abrir_chat)
        menu.addAction(act_chat)
        act_com = QAction("Comentar la pantalla ahora", self)
        act_com.triggered.connect(self.comentar_pantalla)
        self.act_auto = QAction("Comentarios automáticos", self)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(self._cfg_int("comentarios_cada_min", 0) > 0)
        self.act_auto.toggled.connect(self._alternar_auto)
        self.act_fantasma = QAction("Modo fantasma (dejar pasar todos los clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.setChecked(self._cfg_bool("click_through", False))
        self.act_fantasma.toggled.connect(self.set_click_through)
        menu.addAction(act_com)
        menu.addAction(self.act_auto)
        menu.addAction(self.act_fantasma)
        if self.render == "vrm":
            menu.addSeparator()
            self._submenu_opciones(menu, "Tamaño", (("pequeno", "Pequeña"), ("normal", "Normal"), ("grande", "Grande")),
                                   self._cfg_str("vrm_tamano", "normal"), self.aplicar_tamano)
            self._submenu_opciones(menu, "Encuadre", (("retrato", "Retrato (cara y torso)"), ("cuerpo", "Cuerpo entero")),
                                   self._cfg_str("vrm_encuadre", "retrato"), self.aplicar_encuadre)
            act_esq = QAction("Llevar a la esquina", self)
            act_esq.triggered.connect(self.llevar_a_esquina)
            menu.addAction(act_esq)
        menu.addSeparator()
        act_cerrar = QAction("Cerrar mascota", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def quitar_bandeja(self):
        """Quita su icono de bandeja (la app tiene una sola: ui/bandeja.BandejaLune)."""
        tray, self.tray = getattr(self, "tray", None), None
        menu, self._menu_bandeja = getattr(self, "_menu_bandeja", None), None
        self.act_auto = None
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

    def _submenu_opciones(self, menu, titulo, opciones, actual, aplicar):
        sub = menu.addMenu(titulo)
        grupo = QActionGroup(self); grupo.setExclusive(True)
        for clave, etiqueta in opciones:
            a = QAction(etiqueta, self); a.setCheckable(True); a.setChecked(clave == actual)
            a.triggered.connect(lambda _=False, k=clave: aplicar(k))
            grupo.addAction(a); sub.addAction(a)

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def showEvent(self, ev):
        super().showEvent(ev)
        if self._plan_juego is not None and not self._mostrando_por_juego:
            # La sacan a mano en plena partida: gana el usuario (no se vuelve a
            # ocultar y va con sus FPS y su orden Z de siempre).
            self._juego_mostrada_a_mano = True
            self._oculta_por_juego = False
        self._timer_liberar.stop()
        self._reactivar_pagina()                     # si se liberó oculta, se recarga
        self.visibilidad.emit(True)
        self._estado_bus(visible=True)
        self._aplicar_fps()                          # oculta no renderiza; visible, a fps_max
        self._aplicar_encima()                       # Qt puede haber rehecho el orden Z
        self._js_hablando()                          # la voz pudo empezar o acabar oculta
        self._despertar(usuario=True)
        if not self.cerrado:
            self._eventos_en_vuelo = 0.0
            self._timer_eventos.start()
            self._aparecer()
            self._mmd_al_mostrarse()                 # el baile que se pausó al ocultarla sigue

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._timer_eventos.stop()
        self._clic.cancelar()
        self._chat.cerrar()
        self._soltar_hold()
        self._cortar_arrastre()                      # oculta a mitad de un arrastre: se acabó
        self._der_pulsado = self._medio_pulsado = False
        self._aparecer_pendiente = True              # al volver a mostrarse, «aparecer»
        # Oculta no recibe caras del chat: una actividad a medias (escribiendo una
        # respuesta…) se quedaría puesta al volver y no la dejaría dormirse nunca.
        if self._estado_visual in ESTADOS_ACTIVIDAD and not self._pensando:
            self._estado_visual = "normal"
            self._estado_gen += 1
            self._revert_token += 1
            self._timer_revertir.stop()
            self._js("window.setEmocion && window.setEmocion('normal')")
            self._estado_bus(emocion="neutral")
        # Lo que la IA escribía en la burbuja ya no se ve: las frases no esperan por ello.
        self._burbuja_ia = False
        self.visibilidad.emit(False)
        self._estado_bus(visible=False)
        if not self.cerrado:
            self._mmd_al_ocultarse()                 # oculta no baila: en pausa hasta que vuelva
        self._js("window.luneSetFPS && window.luneSetFPS(0)")
        if self.render == "vrm" and not self.cerrado and not self._mmd_activo:
            self._timer_liberar.start(LIBERAR_OCULTA_MS)

    # ── VRM oculta un rato: se libera su WebGL (la barra lateral ya dibuja a Lune) ──
    def _liberar_pagina(self):
        """Lleva un rato oculta (Lune de vuelta en la ventana): la página se descarta
        (QWebEnginePage Discarded: fuera el contexto WebGL y el modelo de la GPU) y
        se recarga sola al volver a mostrarla. Si Qt no deja, sigue como estaba."""
        if self.cerrado or self.isVisible() or self._liberada or self.render != "vrm":
            return
        if self._mmd_activo:
            return                                   # con un baile (en pausa) se conserva; al acabar se rearma
        try:
            pagina = self.web.page()
            pagina.setLifecycleState(pagina.LifecycleState.Discarded)
            self._liberada = pagina.lifecycleState() == pagina.LifecycleState.Discarded
        except Exception as e:                       # noqa: BLE001 — sin soporte: no pasa nada
            _log(f"[companion] no pude liberar la página oculta: {e}")
            self._liberada = False
        if self._liberada:
            self._pagina_lista = False               # hasta que recargue (loadFinished)
            self._timer_cursor.stop()
            self._timer_sueno.stop()
            _log("[companion] mascota 3D oculta: página liberada (se recarga al mostrarla)")

    def _reactivar_pagina(self):
        if not self._liberada:
            return
        self._liberada = False
        try:
            pagina = self.web.page()
            if pagina.lifecycleState() != pagina.LifecycleState.Active:
                pagina.setLifecycleState(pagina.LifecycleState.Active)   # recarga → _on_cargado
        except Exception as e:                       # noqa: BLE001
            _log(f"[companion] no pude reactivar la página: {e}")
            self.web.setUrl(QUrl(self._url_pagina()))

    def closeEvent(self, ev):
        self.cerrado = True
        self._guardar_posicion()
        self._timer.stop(); self._timer_cursor.stop(); self._timer_sueno.stop(); self._timer_escala.stop()
        self._timer_eventos.stop(); self._timer_sueno_pedido.stop(); self._timer_liberar.stop()
        self._timer_revertir.stop(); self._timer_ancla.stop()
        self._ancla_cb = None
        self._cortar_arrastre()
        self._delegado_arrastre = None
        self._mmd_activo = False                     # la página se va con el baile (ControlMMD lo ve por set_mascota)
        self._mmd_pendiente = []
        self._clic.cancelar()
        self._chat.destruir()
        # Un «Comentar pantalla» a medias se va con ella: si no, `pensando` se quedaba
        # pegado en el bus (bot de Minecraft en pausa, Discord «Pensando…», sin sueño).
        self._pensando = False
        self._estado_bus(visible=False, arrastrando=False, hablando=False, pensando=False)
        self.quitar_bandeja()
        if self._servidor is not None:
            self._servidor.detener()
        ev.accept()
