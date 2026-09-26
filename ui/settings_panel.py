"""
settings_panel.py — Panel de Configuración General de Lune CD.
Gestiona APIs, modelos (nube, local y API compatible con OpenAI) y personalidad
(datos.json), además de las features, el avatar pack y la voz (config.json).

Voz de salida (corte 2): motor, voz de edge-tts por país, velocidad y tono de
−50 a +50, acento de gTTS y botón «Probar» (suena aunque la voz esté apagada).
Se guarda en config (`voz.edge_voz`, `edge_rate`, `edge_pitch`, `gtts_tld`) y,
si el personaje activo tiene voz propia en datos.json, también en ella (si no,
la del personaje ganaría y el cambio no se notaría).

Modelos 3D (corte 3): con «Avatar VRM 3D» elegido aparece el panel de modelos
VRM (ui/vrm_panel_nativo.py: importar, usar con el personaje, seguimiento del
cursor por modelo). Su señal `cambiado` sale como `vrm_cambiado` para que
main.py recargue la mascota 3D; al guardar se escribe lo pendiente del panel.

Escritorio (corte 4): el panel ui/escritorio_panel_nativo.PanelEscritorioNativo (tema,
modo juego, rendimiento, atajos globales y menú radial) guarda al momento y cada
apartado se aplica en caliente con los servicios del corte 4 que da main.py
(`servicios=`, o `usar_servicios` cuando se montan): ver aplicar_seccion_escritorio.

Alarmas, pantalla grande y baile (cortes 5/6): ui/panel_ocio_nativo.PanelOcioNativo
(`ocio_panel`) guarda al momento y aplica él mismo; recibe ServiciosCorte4.ocio con
usar_servicios y el «Guardar» escribe lo que tuviera pendiente.
"""
import re

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton,
    QLineEdit, QTextEdit, QCheckBox, QComboBox, QMessageBox, QSlider,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from servicios import actualizador

from nucleo import datos
from nucleo.personajes import voz_de

from servicios import ollama_client

from servicios import voz_entrada
from servicios import voces
from servicios.voice import listar_salidas

from lune_core.voz import kokoro_backend
from nucleo.config import Config
from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO
from ui import lune_face
from ui.vrm_panel_nativo import VrmPanelNativo

AJUSTE_VOZ_MAX = 50          # velocidad (%) y tono (Hz): de −50 a +50
MULTILINGUES = "Multilingües"


# ── Voz: funciones puras (se prueban sin ventana) ──────────────────────────────

def texto_rate(n) -> str:
    """Valor del deslizador → «+10%» (lo que entiende edge-tts)."""
    return f"{int(n):+d}%"


def texto_pitch(n) -> str:
    """Valor del deslizador → «-5Hz»."""
    return f"{int(n):+d}Hz"


def numero_ajuste(valor, sufijo: str) -> int:
    """«+10%» / «-5Hz» → entero limitado a ±AJUSTE_VOZ_MAX (0 si no vale)."""
    m = re.fullmatch(r"([+-]?\d+)" + re.escape(sufijo), str(valor or "").strip())
    n = int(m.group(1)) if m else 0
    return max(-AJUSTE_VOZ_MAX, min(AJUSTE_VOZ_MAX, n))


def items_voces(lista) -> list:
    """
    Voces de edge-tts → [(texto, id | None)] para el combo: una cabecera por
    país (id None, no seleccionable) con México primero, las multilingües al
    final, y cada voz como «Dalia (F) · es-MX-DaliaNeural».
    """
    grupos = {}
    for v in lista or ():
        if not isinstance(v, dict) or not v.get("id"):
            continue
        clave = MULTILINGUES if v.get("multilingue") else (v.get("pais") or "?")
        grupos.setdefault(clave, []).append(v)
    orden = sorted(grupos, key=lambda g: (g == MULTILINGUES, g != "México", g))
    salida = []
    for g in orden:
        salida.append((f"── {g} ──", None))
        for v in sorted(grupos[g], key=lambda x: (x.get("genero", ""), x.get("nombre", ""))):
            salida.append((f"{v.get('nombre') or v['id']} ({v.get('genero') or '?'}) · {v['id']}", v["id"]))
    return salida


def voz_para_personaje(actual: dict, motor: str, edge_voz: str, kokoro_voz: str,
                       rate: str, pitch: str, tld: str) -> dict:
    """La voz propia del personaje con lo elegido en el panel (motor 'auto' = sin motor fijo)."""
    nueva = dict(actual or {})
    if motor in ("", "auto"):
        nueva.pop("motor", None)
    else:
        nueva["motor"] = motor
    if motor in ("", "auto", "edge"):
        nueva["id"] = edge_voz
    elif motor == "kokoro":
        nueva["id"] = kokoro_voz
    nueva["rate"], nueva["pitch"], nueva["tld"] = rate, pitch, tld
    return nueva


class ProbarCompatWorker(QThread):
    """«Probar conexión» de la API compatible con lo escrito (aún sin guardar)."""
    listo = pyqtSignal(object)      # {ok, mensaje, modelos, url, ms}

    def __init__(self, url: str, clave: str, modelo: str):
        super().__init__()
        self.url, self.clave, self.modelo = url, clave, modelo

    def run(self):
        try:
            from servicios.ai_manager import CompatProvider
            self.listo.emit(CompatProvider(self.url, self.clave, self.modelo).probar())
        except Exception as e:
            self.listo.emit({"ok": False, "mensaje": f"No pude probar: {e}", "modelos": []})



class SondeoOllamaWorker(QThread):
    """Consulta /api/tags en segundo plano para no congelar la UI."""
    listo = pyqtSignal(bool, object, str)   # ok, modelos, mensaje

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        ok, modelos, mensaje = ollama_client.listar_modelos(self.url)
        self.listo.emit(ok, modelos, mensaje)


class EstadoGitWorker(QThread):
    """
    Lee el estado del repo fuera del hilo de UI.

    El panel de ajustes se construye al arrancar la app, así que llamar a git
    aquí de forma síncrona retrasaba el arranque (y, sin CREATE_NO_WINDOW,
    llenaba la pantalla de consolas parpadeando).
    """
    listo = pyqtSignal(object)

    def run(self):
        try:
            self.listo.emit(actualizador.estado())
        except Exception as e:
            self.listo.emit({"ok": False, "mensaje": f"No pude leer el estado: {e}"})


class GitWorker(QThread):
    """
    Consulta o aplica actualizaciones sin bloquear la UI.
    `git fetch` y `pip install` pueden tardar bastante.
    """
    progreso = pyqtSignal(str)
    listo = pyqtSignal(object)     # dict con el resultado

    def __init__(self, modo: str, rama: str = ""):
        super().__init__()
        self.modo = modo           # "comprobar" | "actualizar"
        self.rama = rama

    def run(self):
        try:
            if self.modo == "comprobar":
                self.listo.emit(actualizador.comprobar(self.rama or None))
            else:
                self.listo.emit(actualizador.actualizar(
                    self.rama or None, on_progreso=self.progreso.emit))
        except Exception as e:
            self.listo.emit({"ok": False, "mensaje": f"Algo falló: {e}"})


def _cfg(config, seccion: str, clave: str, defecto=None):
    try:
        return config.get(seccion, clave, defecto) if config is not None else defecto
    except Exception:
        return defecto


def aplicar_seccion_escritorio(seccion: str, servicios, config, claves=None) -> list:
    """Aplica en caliente un apartado que el panel de escritorio (corte 4,
    ui/escritorio_panel_nativo.py) acaba de escribir en config.json:

      tema        → ControlTema.recargar() (mascota, bandeja y radial; la ventana
                    nativa se recolorea al reiniciar)
      juego       → ControlModoJuego.recargar_config()
      atajos      → GestorAtajosQt.recargar() (activo, pausar en juegos, combos)
      rendimiento → mascota.set_fps_max / set_encima, recorte periódico
                    (juego.recargar_config) y la ventana en la barra de tareas
      radial      → nada (se lee al abrirlo)

    `servicios`: ServiciosCorte4 (o None: aún sin montar, no hay nada que aplicar).
    `claves`: las (sección, clave) escritas; con ellas solo se toca lo que cambió
    (quitar/poner la ventana de la barra de tareas la esconde y la vuelve a enseñar).
    Devuelve los métodos llamados («recargar», «set_fps_max»…)."""
    hechos: list = []
    if servicios is None:
        return hechos

    def llamar(obj, metodo, *args) -> bool:
        f = getattr(obj, metodo, None) if obj is not None else None
        if not callable(f):
            return False
        try:
            f(*args)
        except Exception as e:
            try:
                from nucleo.utils import log_error
                log_error(f"[ajustes] {metodo}: {e}")
            except Exception:
                pass
            return False
        hechos.append(metodo)
        return True

    def cambio(s: str, k: str) -> bool:
        return claves is None or (s, k) in claves

    if seccion == "tema":
        llamar(getattr(servicios, "tema", None), "recargar")
    elif seccion == "juego":
        llamar(getattr(servicios, "juego", None), "recargar_config")
    elif seccion == "atajos":
        llamar(getattr(servicios, "atajos", None), "recargar")
    elif seccion == "rendimiento":
        esc = getattr(servicios, "escritorio", None)
        m = getattr(esc, "mascota", None) if esc is not None else None
        if m is None:
            f = getattr(getattr(servicios, "anfitrion", None), "mascota", None)
            try:
                m = f() if callable(f) else None
            except Exception:
                m = None
        if m is not None and getattr(m, "cerrado", False) is True:
            m = None                                   # cerrada por el usuario: nada que tocar
        if cambio("avatar", "fps_max"):
            try:
                fps = int(_cfg(config, "avatar", "fps_max", 60) or 60)
            except (TypeError, ValueError):
                fps = 60
            if not llamar(m, "set_fps_max", fps):
                llamar(m, "aplicar_opciones")
        if cambio("avatar", "siempre_encima"):
            llamar(m, "set_encima", bool(_cfg(config, "avatar", "siempre_encima", True)))
        if cambio("sistema", "recorte_ram_auto"):
            llamar(getattr(servicios, "juego", None), "recargar_config")
        if cambio("interfaz", "en_barra_tareas"):
            llamar(getattr(servicios, "anfitrion", None), "set_en_barra",
                   bool(_cfg(config, "interfaz", "en_barra_tareas", True)))
    return hechos


def _liberar_memoria():
    """«Liberar memoria ahora» del panel de escritorio: gc + recorte del working set
    de los procesos de Lune (servicios/recorte_ram.py), en el hilo de Qt."""
    from servicios.recorte_ram import recortar
    return recortar()


class SettingsPanel(QFrame):
    saved = pyqtSignal()
    vrm_cambiado = pyqtSignal()     # el panel VRM importó, asignó o guardó el seguimiento
    escritorio_cambiado = pyqtSignal(str)   # un apartado del corte 4 se guardó (y se aplicó)

    def __init__(self, config: Config = None, parent=None, voice=None, servicios=None):
        """`servicios`: los del corte 4 (ServiciosCorte4) o una función que los da (la
        nativa los monta DESPUÉS de construir Ajustes, en iniciar_servicios); sirven
        para aplicar al momento lo que guarda el panel de escritorio."""
        super().__init__(parent)
        self.config = config or Config()
        self.voice = voice              # VoiceEngine de la app, para «Probar voz»
        self._servicios = servicios
        self.setStyleSheet("QFrame{background:transparent;}")
        self._sondeo = None
        self._prueba_compat = None
        self.datos_data = datos.cargar() or {
            "apis": {}, "modelos": {}, "bot": {"personaje_default": "Lune"}, "personajes": []
        }
        self._build()
        # El panel se construye UNA vez (al arrancar la app) y mientras tanto otros
        # escriben en datos.json/config (panel VRM, cambiar_voz, cambio de personaje…).
        # Al guardar se relee datos.json y solo se escribe lo que cambiaste aquí,
        # en el personaje que se estaba editando.
        self._nombre_editado = self._personaje_activo().get("nombre")
        self._inicial = self._valores_ui()

    # ── Personaje activo ───────────────────────────────────────────────────────
    def _indice_personaje_activo(self) -> int:
        """
        Índice del personaje activo dentro de datos.json.

        Antes se asumía siempre el 0, así que guardar la configuración con un
        personaje importado activo sobrescribía a Lune. Ahora se resuelve por
        nombre y solo se cae al 0 si no hay coincidencia.
        """
        personajes = self.datos_data.get("personajes") or []
        if not personajes:
            self.datos_data["personajes"] = [{}]
            return 0
        activo = (self.datos_data.get("bot", {}).get("personaje_default") or "").lower()
        for i, p in enumerate(personajes):
            if (p.get("nombre") or "").lower() == activo:
                return i
        return 0

    def _build(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }} QScrollBar:vertical {{ background: {COLORS['surface']}; width: 8px; border-radius: 4px; }} QScrollBar::handle:vertical {{ background: {COLORS['border2']}; border-radius: 4px; }}")

        content = QFrame()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 20, 40, 40); layout.setSpacing(25)

        title = QLabel("CONFIGURACIÓN GENERAL")
        title.setFont(QFont(FONT_DISPLAY, 18, QFont.Weight.Bold)); title.setStyleSheet(f"color:{COLORS['text']};letter-spacing:2px;")
        layout.addWidget(title)

        self.fields = {}
        modelos = self.datos_data.get("modelos", {})
        apis = self.datos_data.get("apis", {})

        # ── SECCIÓN 1: NUBE (OpenRouter) ──
        layout.addWidget(self._create_section_title("Red Neuronal · Nube (OpenRouter)"))
        frame_ia = self._create_group_frame()
        fl_ia = QVBoxLayout(frame_ia); fl_ia.setSpacing(10)
        self._add_input(fl_ia, "openrouter_api_key", "API Key de OpenRouter",
                        apis.get("openrouter_key", ""), True)
        self._add_input(fl_ia, "openrouter_model", "Modelo (openrouter/auto enruta solo)",
                        modelos.get("openrouter_model", "openrouter/auto"), False)
        layout.addWidget(frame_ia)

        # ── SECCIÓN 2: LOCAL (Ollama) ──
        layout.addWidget(self._create_section_title("Red Neuronal · Local (Ollama)"))
        layout.addWidget(self._build_ollama_group(modelos))

        # ── SECCIÓN 2a: API COMPATIBLE CON OPENAI (LM Studio, Groq…) ──
        layout.addWidget(self._create_section_title("Red Neuronal · API compatible con OpenAI"))
        layout.addWidget(self._build_compat_group(modelos, apis))

        # ── SECCIÓN 2b: NOTAS (memoria larga / RAG) ──
        layout.addWidget(self._create_section_title("Notas · memoria larga (RAG)"))
        layout.addWidget(self._build_notas_group())

        # ── SECCIÓN 3: TELEGRAM ──
        layout.addWidget(self._create_section_title("Integración Telegram"))
        frame_tg = self._create_group_frame()
        fl_tg = QVBoxLayout(frame_tg); fl_tg.setSpacing(10)
        self._add_input(fl_tg, "telegram_token", "Token del Bot de Telegram",
                        apis.get("telegram_token", ""), True)
        self._add_input(fl_tg, "telegram_admin_id", "Tu ID de Telegram (comparte memoria con la app)",
                        str(apis.get("telegram_admin_id", "")), False)
        # Órdenes desde Telegram (/pc): todo lo que se haga se aprueba en el PC.
        self.ordenes_tg_check = QCheckBox("Órdenes desde Telegram (con aprobación en el PC)")
        self.ordenes_tg_check.setChecked(bool(self.config.get("telegram", "ordenes_pc", False)))
        self.ordenes_tg_check.setFont(QFont("Segoe UI", 10))
        self.ordenes_tg_check.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
        fl_tg.addWidget(self.ordenes_tg_check)
        ayuda_tg = QLabel("Con /pc abre youtube desde tu Telegram, Lune lo hace aquí solo si lo apruebas "
                          "en el PC. Requiere tu ID de Telegram (escríbele /id al bot) y reiniciar el bot "
                          "para aplicarse.")
        ayuda_tg.setWordWrap(True); ayuda_tg.setFont(QFont("Segoe UI", 9))
        ayuda_tg.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_tg.addWidget(ayuda_tg)
        layout.addWidget(frame_tg)

        # ── SECCIÓN 4: PERSONALIDAD ──
        layout.addWidget(self._create_section_title("Personalidad y Comportamiento"))
        frame_pers = self._create_group_frame()
        fl_pers = QVBoxLayout(frame_pers); fl_pers.setSpacing(15)

        idx = self._indice_personaje_activo()
        personaje = self.datos_data["personajes"][idx]
        aviso = QLabel(f"Editando el personaje activo: «{personaje.get('nombre', 'Lune')}». "
                       "Los demás no se tocan.")
        aviso.setWordWrap(True); aviso.setFont(QFont("Segoe UI", 9))
        aviso.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_pers.addWidget(aviso)

        self._add_input(fl_pers, "bot_nombre", "Nombre del Asistente", personaje.get("nombre", "Lune"), False)
        self._add_textarea(fl_pers, "bot_system", "Instrucciones del Sistema (System Prompt)",
                           personaje.get("systemPrompt", "Eres Lune, una asistente virtual inteligente y amigable..."), 100)
        self._add_textarea(fl_pers, "bot_saludo", "Mensaje de Bienvenida",
                           personaje.get("fraseInicial", "Buenos días. ¿En qué te puedo ayudar hoy?"), 60)
        self._add_input(fl_pers, "max_historial", "Turnos de conversación que recuerda (menos = menos contexto)",
                        str(self.datos_data.get("bot", {}).get("max_historial", 20)), False)
        layout.addWidget(frame_pers)

        # ── SECCIÓN 5: RENDIMIENTO Y FUNCIONES ──
        layout.addWidget(self._create_section_title("Rendimiento y Funciones (activa/desactiva para optimizar)"))
        frame_feat = self._create_group_frame()
        fl_feat = QVBoxLayout(frame_feat); fl_feat.setSpacing(8)
        self.feature_checks = {}
        feats = [
            ("respuestas_predeterminadas", "Respuestas instantáneas (sin gastar IA en saludos comunes)"),
            ("streaming_tokens", "Mostrar respuesta letra por letra (streaming)"),
            ("animaciones_video", "Animaciones de video de Lune (consume más CPU/GPU)"),
            ("fondo_estrellas", "Fondo animado en la pantalla de inicio"),
            ("efectos_hover", "Microanimaciones y efectos visuales"),
            ("voz_auto", "Leer cada respuesta en voz alta al iniciar"),
            ("minimizar_a_bandeja", "Al cerrar, mantener Lune en la bandeja del sistema"),
            ("acciones_ia", "Permitir que la IA abra webs y lance apps por su cuenta"),
            ("markdown", "Formatear negritas, listas y bloques de código en el chat"),
            ("guardar_conversaciones", "Guardar el historial de conversaciones en disco"),
            ("contador_tokens", "Mostrar tokens y costo debajo de cada respuesta"),
        ]
        for clave, etiqueta in feats:
            chk = QCheckBox(etiqueta); chk.setChecked(self.config.feature(clave, True))
            chk.setFont(QFont("Segoe UI", 10))
            chk.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
            fl_feat.addWidget(chk); self.feature_checks[clave] = chk
        layout.addWidget(frame_feat)

        # ── SECCIÓN 6: APARIENCIA / MODELO (avatar pack) ──
        layout.addWidget(self._create_section_title("Modelo visual de Lune (avatar pack)"))
        frame_av = self._create_group_frame()
        fl_av = QVBoxLayout(frame_av); fl_av.setSpacing(8)
        info_av = QLabel("Elige el set de expresiones. Suelta nuevos packs en lune_face/packs/. "
                         "La mascota flotante (tile MASCOTA) usa estos packs.")
        info_av.setWordWrap(True); info_av.setFont(QFont("Segoe UI", 9)); info_av.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_av.addWidget(info_av)
        self.pack_combo = QComboBox()
        packs = lune_face.listar_packs()
        self.pack_combo.addItems(packs)
        actual = self.config.get("avatar", "pack", "default")
        if actual in packs:
            self.pack_combo.setCurrentText(actual)
        self.pack_combo.setStyleSheet(self._estilo_combo())
        fl_av.addWidget(self.pack_combo)

        # ── Cómo se dibuja la mascota flotante: sprites 2D o avatar VRM 3D ──
        lbl_r = QLabel("Mascota flotante")
        lbl_r.setFont(QFont("Segoe UI", 10)); lbl_r.setStyleSheet(f"color:{COLORS['text']};border:none;padding-top:6px;")
        self.render_combo = QComboBox()
        self.render_combo.addItem("Sprites 2D (los packs de arriba)", "sprites")
        self.render_combo.addItem("Avatar VRM 3D (modelo_vrm/, necesita WebEngine)", "vrm")
        # La interfaz completa usa "animado" (video); se conserva para no pisarlo desde aquí.
        self.render_combo.addItem("Imágenes animadas (interfaz completa)", "animado")
        idx_r = self.render_combo.findData(self.config.get("avatar", "render", "sprites"))
        self.render_combo.setCurrentIndex(idx_r if idx_r >= 0 else 0)
        self.render_combo.setStyleSheet(self._estilo_combo())
        fl_av.addWidget(lbl_r); fl_av.addWidget(self.render_combo)

        aviso_vrm = self._aviso_vrm()
        aviso_vrm.setWordWrap(True); aviso_vrm.setFont(QFont("Segoe UI", 9))
        fl_av.addWidget(aviso_vrm)
        layout.addWidget(frame_av)

        # Modelos 3D: biblioteca mínima y seguimiento del cursor por modelo. Va
        # fuera del marco del avatar (su estilo QFrame{padding} se heredaría) y
        # solo se ve con «Avatar VRM 3D» elegido.
        self.vrm_panel = VrmPanelNativo(self.config, self)
        self.vrm_panel.cambiado.connect(self.vrm_cambiado)
        layout.addWidget(self.vrm_panel)
        self.render_combo.currentIndexChanged.connect(self._visibilidad_vrm)
        self._visibilidad_vrm()

        # ── SECCIÓN 6a: ESCRITORIO (corte 4): tema, modo juego, rendimiento, atajos
        # globales y menú radial. Guarda al momento (300 ms) y se aplica en caliente
        # con los servicios del corte 4 (aplicar_seccion_escritorio).
        layout.addWidget(self._create_section_title(
            "Escritorio · tema, modo juego, rendimiento, atajos y menú radial"))
        from ui.escritorio_panel_nativo import PanelEscritorioNativo
        s = self.servicios_c4()
        self.escritorio_panel = PanelEscritorioNativo(
            self.config, self, atajos=getattr(s, "atajos", None),
            liberar_memoria=_liberar_memoria)
        self.escritorio_panel.cambiado.connect(self._escritorio_cambiado)
        layout.addWidget(self.escritorio_panel)

        # ── SECCIÓN 6a bis: ALARMAS, PANTALLA GRANDE Y BAILE (cortes 5/6). Guarda al
        # momento (300 ms) y aplica él mismo (recargar_config del controlador); los
        # controladores (ServiciosCorte4.ocio) llegan con usar_servicios.
        layout.addWidget(self._create_section_title(
            "Alarmas, pantalla grande, salvapantallas y baile"))
        from ui.panel_ocio_nativo import PanelOcioNativo
        self.ocio_panel = PanelOcioNativo(self.config, self)
        if s is not None and getattr(s, "ocio", None) is not None:
            self._enlazar_ocio(s)
        layout.addWidget(self.ocio_panel)

        # ── SECCIÓN 6b: RED DE LUNE (host y terminales) ──
        layout.addWidget(self._create_section_title("Red de Lune · host y terminales"))
        layout.addWidget(self._build_hub_group())

        # ── SECCIÓN 7: VOZ DE ENTRADA (dictado) ──
        layout.addWidget(self._create_section_title("Voz de entrada (dictado con Whisper)"))
        layout.addWidget(self._build_voz_group())

        # ── SECCIÓN 8: ACTUALIZACIONES Y DEPENDENCIAS ──
        layout.addWidget(self._create_section_title("Actualizaciones y dependencias"))
        layout.addWidget(self._build_update_group())

        # Botón Guardar
        save_btn = QPushButton("GUARDAR CONFIGURACIÓN")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor); save_btn.setFont(QFont(FONT_DISPLAY, 12, QFont.Weight.Bold)); save_btn.setFixedHeight(50)
        save_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['accent']},stop:1 {COLORS['accent2']});color:{COLORS['bg']};border:none;border-radius:3px;margin-top: 10px;letter-spacing:2px;}}QPushButton:hover{{background:{COLORS['accent2']};}}")
        save_btn.clicked.connect(self._save); layout.addWidget(save_btn); layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    # ── Grupo de Ollama ────────────────────────────────────────────────────────
    def _build_ollama_group(self, modelos: dict) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)

        info = QLabel(
            "Modelos que corren en tu propia máquina: sin costo, sin conexión y sin límites de tokens. "
            "Puedes apuntar a otro PC de la red (por ejemplo el equipo potente) poniendo su IP: "
            "http://192.168.1.50:11434 — en ese equipo Ollama debe arrancar con OLLAMA_HOST=0.0.0.0:11434."
        )
        info.setWordWrap(True); info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(info)

        # URL + botón de sondeo
        self._add_input(fl, "ollama_url", "Servidor de Ollama",
                        modelos.get("ollama_url", "http://localhost:11434"), False)

        fila = QHBoxLayout(); fila.setSpacing(8)
        self.btn_probar = QPushButton("BUSCAR MODELOS")
        self.btn_probar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probar.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_probar.setFixedHeight(36)
        self.btn_probar.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 16px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        self.btn_probar.clicked.connect(self._probar_ollama)
        self.lbl_ollama = QLabel("Pulsa «Buscar modelos» para ver qué hay instalado.")
        self.lbl_ollama.setWordWrap(True); self.lbl_ollama.setFont(QFont(FONT_MONO, 9))
        self.lbl_ollama.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fila.addWidget(self.btn_probar); fila.addWidget(self.lbl_ollama, 1)
        fl.addLayout(fila)

        # Modelo: combo editable (se rellena al sondear, pero puedes escribirlo)
        lbl_modelo = QLabel("Modelo local")
        lbl_modelo.setFont(QFont("Segoe UI", 10)); lbl_modelo.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.ollama_combo = QComboBox(); self.ollama_combo.setEditable(True)
        actual = modelos.get("ollama_model", "")
        if actual:
            self.ollama_combo.addItem(actual)
            self.ollama_combo.setCurrentText(actual)
        self.ollama_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_modelo); fl.addWidget(self.ollama_combo)

        # Parámetros de inferencia
        avanzado = QLabel("Ajustes de inferencia")
        avanzado.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        avanzado.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:6px;")
        fl.addWidget(avanzado)

        self._add_input(fl, "ollama_keep_alive",
                        "Mantener el modelo en VRAM (30m, 1h, -1 = para siempre)",
                        str(modelos.get("ollama_keep_alive", "30m")), False)
        self._add_input(fl, "ollama_num_ctx",
                        "Ventana de contexto en tokens (más = más RAM/VRAM)",
                        str(modelos.get("ollama_num_ctx", 8192)), False)
        self._add_input(fl, "ollama_timeout",
                        "Timeout en segundos (subir si el modelo tarda en cargar en frío)",
                        str(modelos.get("ollama_timeout", 300)), False)
        self._add_input(fl, "temperatura",
                        "Temperatura (0 = preciso, 1 = creativo)",
                        str(modelos.get("temperatura", 0.7)), False)
        return frame

    # ── Grupo de la API compatible con OpenAI ──────────────────────────────────
    def _build_compat_group(self, modelos: dict, apis: dict) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)
        info = QLabel(
            "Cualquier servidor con /v1/chat/completions: LM Studio, llama.cpp, Groq, OpenAI, "
            "Together, Mistral… Aparece como tercera pestaña en «Red neuronal». Deja la URL "
            "vacía para apagarlo. La clave es opcional (LM Studio no la pide) y el modelo "
            "también: sin él se usa el primero que ofrezca el servidor."
        )
        info.setWordWrap(True); info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(info)
        self._add_input(fl, "compat_url", "URL base (p. ej. http://localhost:1234/v1)",
                        str(modelos.get("compat_url", "") or ""), False)
        self._add_input(fl, "compat_key", "Clave de la API (opcional)",
                        str(modelos.get("compat_key", "") or apis.get("compat_key", "") or ""), True)
        self._add_input(fl, "compat_model", "Modelo (vacío = el primero que ofrezca)",
                        str(modelos.get("compat_model", "") or ""), False)
        fila = QHBoxLayout(); fila.setSpacing(8)
        self.btn_probar_compat = QPushButton("PROBAR CONEXIÓN")
        self.btn_probar_compat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probar_compat.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        self.btn_probar_compat.setFixedHeight(36)
        self.btn_probar_compat.setStyleSheet(self._estilo_boton())
        self.btn_probar_compat.clicked.connect(self._probar_compat)
        self.lbl_compat = QLabel("Prueba lo escrito aquí sin gastar tokens (solo pide /models).")
        self.lbl_compat.setWordWrap(True); self.lbl_compat.setFont(QFont(FONT_MONO, 9))
        self.lbl_compat.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fila.addWidget(self.btn_probar_compat); fila.addWidget(self.lbl_compat, 1)
        fl.addLayout(fila)
        return frame

    def _probar_compat(self):
        url = self.fields["compat_url"].text().strip().rstrip("/")
        if not url:
            self.lbl_compat.setText("Escribe primero la URL del servidor.")
            self.lbl_compat.setStyleSheet(f"color:{COLORS['warning']};border:none;")
            return
        if self._prueba_compat is not None and self._prueba_compat.isRunning():
            return
        self.btn_probar_compat.setEnabled(False)
        self.lbl_compat.setText(f"Probando {url}…")
        self.lbl_compat.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self._prueba_compat = ProbarCompatWorker(url, self.fields["compat_key"].text().strip(),
                                                 self.fields["compat_model"].text().strip())
        self._prueba_compat.listo.connect(self._on_compat_probado)
        self._prueba_compat.start()

    def _on_compat_probado(self, r):
        self.btn_probar_compat.setEnabled(True)
        r = r if isinstance(r, dict) else {}
        texto = str(r.get("mensaje") or ("Conectado." if r.get("ok") else "No respondió."))
        if r.get("ms") is not None:
            texto += f" ({r['ms']} ms)"
        modelos = [m if isinstance(m, str) else str((m or {}).get("id", "")) for m in (r.get("modelos") or [])]
        if modelos:
            texto += "\nModelos: " + ", ".join(modelos[:8]) + (" …" if len(modelos) > 8 else "")
        self.lbl_compat.setText(texto)
        self.lbl_compat.setStyleSheet(
            f"color:{COLORS['success'] if r.get('ok') else COLORS['warning']};border:none;")

    # ── Grupo de notas (RAG) ───────────────────────────────────────────────────
    def _build_notas_group(self) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)
        notas = self.config.config.get("notas", {})

        info = QLabel(
            "Lune puede recordar tus documentos: pon notas markdown en una carpeta y "
            "las consultará cuando vengan al caso, citándolas. Necesita un modelo de "
            "embeddings en Ollama (p. ej. «ollama pull nomic-embed-text»)."
        )
        info.setWordWrap(True); info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(info)

        self.notas_check = QCheckBox("Activar memoria larga sobre mis notas")
        self.notas_check.setChecked(bool(notas.get("activo", False)))
        self.notas_check.setFont(QFont("Segoe UI", 10))
        self.notas_check.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
        fl.addWidget(self.notas_check)

        self._add_input(fl, "notas_carpeta", "Carpeta de notas (.md)", str(notas.get("carpeta", "notas")), False)
        self._add_input(fl, "notas_modelo", "Modelo de embeddings", str(notas.get("modelo_embeddings", "nomic-embed-text")), False)
        self._add_input(fl, "notas_topk", "Trozos que inyecta por mensaje", str(notas.get("top_k", 3)), False)
        return frame

    # ── Grupo de red (hub) ─────────────────────────────────────────────────────
    def _build_hub_group(self) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)

        # ── Modo de interfaz: Completa (web) · Bajos recursos (esta nativa) ──
        # Desde aquí el usuario en bajos recursos puede volver a la interfaz completa.
        # Se aplica al instante AL GUARDAR (este panel es un formulario con un solo
        # «Guardar»: así lo pendiente se guarda antes de que la ventana cambie).
        lbl_ui = QLabel("Modo de interfaz (se aplica al instante al guardar)")
        lbl_ui.setFont(QFont("Segoe UI", 10)); lbl_ui.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.interfaz_combo = QComboBox()
        self.interfaz_combo.addItem("Completa (piel web, animada)", "web")
        self.interfaz_combo.addItem("Bajos recursos (nativa, ligera)", "nativo")
        self.interfaz_combo.addItem("Patata (solo terminal, sin imágenes)", "patata")
        modo_ui = str(self.config.config.get("interfaz", {}).get("modo", "web"))
        self.interfaz_combo.setCurrentIndex(max(0, self.interfaz_combo.findData(modo_ui)))
        self.interfaz_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_ui); fl.addWidget(self.interfaz_combo)

        # ── Calidad de vida: arrancar con Windows + instalador de componentes ──
        from servicios import autoinicio as _auto
        self.autoinicio_check = QCheckBox("Arrancar Lune junto con Windows")
        self.autoinicio_check.setChecked(_auto.activo())
        self.autoinicio_check.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
        fl.addWidget(self.autoinicio_check)
        btn_inst = QPushButton("INSTALAR COMPONENTES…")
        btn_inst.setToolTip("Abre el instalador: explica para qué sirve cada cosa (voz, dictado, interfaz animada…) y lo instala.")
        btn_inst.setCursor(Qt.CursorShape.PointingHandCursor); btn_inst.setFont(QFont(FONT_DISPLAY, 10, QFont.Weight.Bold)); btn_inst.setFixedHeight(36)
        btn_inst.setStyleSheet(f"QPushButton{{background:transparent;color:{COLORS['text_muted']};border:2px solid {COLORS['border']};border-radius:2px;letter-spacing:1px;}}QPushButton:hover{{color:{COLORS['accent']};border-color:{COLORS['cyan_dark']};}}")
        def _abrir_instalador():
            import subprocess, sys
            from pathlib import Path
            ruta = Path(__file__).resolve().parent.parent / "instalador.py"
            try: subprocess.Popen([sys.executable, str(ruta)], cwd=str(ruta.parent))
            except Exception as e: QMessageBox.warning(self, "Instalador", f"No pude abrir el instalador:\n{e}")
        btn_inst.clicked.connect(_abrir_instalador)
        fl.addWidget(btn_inst)

        hub = self.datos_data.get("hub", {})

        info = QLabel(
            "Un equipo potente hace de <b>host</b>: sirve la memoria compartida (y en versiones "
            "siguientes el modelo, la voz y las herramientas). Los demás equipos son <b>terminales</b> "
            "y ven la misma memoria. En modo <b>local</b> todo ocurre en este equipo, como siempre."
        )
        info.setWordWrap(True); info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(info)

        lbl = QLabel("Modo de este equipo")
        lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.hub_modo_combo = QComboBox()
        self.hub_modo_combo.addItem("local — todo en este equipo", "local")
        self.hub_modo_combo.addItem("host — este equipo sirve a los demás", "host")
        self.hub_modo_combo.addItem("terminal — me conecto al host", "terminal")
        modo = str(hub.get("modo") or "local")
        idx = max(0, self.hub_modo_combo.findData(modo))
        self.hub_modo_combo.setCurrentIndex(idx)
        self.hub_modo_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl); fl.addWidget(self.hub_modo_combo)

        self._add_input(fl, "hub_puerto", "Puerto del hub (modo host)", str(hub.get("puerto", 7777)), False)
        self._add_input(fl, "hub_url_host", "URL del host (modo terminal), p. ej. ws://192.168.1.50:7777",
                        str(hub.get("url_host", "")), False)
        self._add_input(fl, "hub_token", "Token del hub (igual en host y terminales)",
                        str(hub.get("token", "")), True)

        fila = QHBoxLayout(); fila.setSpacing(8)
        btn_tok = QPushButton("GENERAR TOKEN")
        btn_tok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tok.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); btn_tok.setFixedHeight(34)
        btn_tok.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 14px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}")
        btn_tok.clicked.connect(self._generar_token_hub)
        nota = QLabel("Genera el token en el host y cópialo a cada terminal. Se guarda en datos.json, que no se versiona.")
        nota.setWordWrap(True); nota.setFont(QFont(FONT_MONO, 8))
        nota.setStyleSheet(f"color:{COLORS['text_dim']};border:none;")
        fila.addWidget(btn_tok); fila.addWidget(nota, 1)
        fl.addLayout(fila)

        # ── Descubrimiento de dispositivos Lune en la red ──
        fl.addWidget(self._separador_red())
        rol_lbl = QLabel("Rol de este dispositivo")
        rol_lbl.setFont(QFont("Segoe UI", 10)); rol_lbl.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        from lune_core import descubrimiento as _D
        self.red_rol_combo = QComboBox()
        for r in _D.ROLES:
            self.red_rol_combo.addItem(_D.ETIQUETA_ROL[r], r)
        rol_actual = str(self.config.config.get("red", {}).get("rol", "hibrido"))
        self.red_rol_combo.setCurrentIndex(max(0, self.red_rol_combo.findData(rol_actual)))
        self.red_rol_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(rol_lbl); fl.addWidget(self.red_rol_combo)
        self._add_input(fl, "red_nombre", "Nombre visible de este equipo (vacío = nombre del sistema)",
                        str(self.config.config.get("red", {}).get("nombre", "")), False)

        fila2 = QHBoxLayout(); fila2.setSpacing(8)
        self.btn_buscar_disp = QPushButton("BUSCAR DISPOSITIVOS")
        self.btn_buscar_disp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar_disp.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_buscar_disp.setFixedHeight(34)
        self.btn_buscar_disp.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 14px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        self.btn_buscar_disp.clicked.connect(self._buscar_dispositivos)
        fila2.addWidget(self.btn_buscar_disp); fila2.addStretch()
        fl.addLayout(fila2)

        self.lista_disp = QVBoxLayout(); self.lista_disp.setSpacing(6)
        cont = QFrame(); cont.setLayout(self.lista_disp); cont.setStyleSheet("QFrame{border:none;background:transparent;}")
        fl.addWidget(cont)
        self.lbl_disp = QLabel("Pulsa «Buscar dispositivos» para ver los Lune de tu red y elegir el host.")
        self.lbl_disp.setWordWrap(True); self.lbl_disp.setFont(QFont(FONT_MONO, 8))
        self.lbl_disp.setStyleSheet(f"color:{COLORS['text_dim']};border:none;")
        self.lista_disp.addWidget(self.lbl_disp)
        return frame

    def _separador_red(self):
        s = QLabel("Dispositivos en la red")
        s.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        s.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:8px;")
        return s

    def _buscar_dispositivos(self):
        from lune_core import descubrimiento as _D
        if not _D.zeroconf_disponible():
            self.lbl_disp.setText("Instala zeroconf para descubrir dispositivos:  pip install zeroconf")
            self.lbl_disp.setStyleSheet(f"color:{COLORS['warning']};border:none;")
            return
        self.btn_buscar_disp.setEnabled(False); self.btn_buscar_disp.setText("BUSCANDO…")
        self.lbl_disp.setText("Escaneando la red (unos segundos)…")
        self.lbl_disp.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        from servicios.red_service import BuscarWorker
        self._buscador = BuscarWorker(3.0, datos.hub_puerto())
        self._buscador.listo.connect(self._mostrar_dispositivos)
        self._buscador.start()

    def _mostrar_dispositivos(self, dispositivos):
        self.btn_buscar_disp.setEnabled(True); self.btn_buscar_disp.setText("BUSCAR DISPOSITIVOS")
        while self.lista_disp.count():
            it = self.lista_disp.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not dispositivos:
            lbl = QLabel("No encontré otros Lune en la red. ¿Están abiertos y en la misma Wi-Fi?")
            lbl.setWordWrap(True); lbl.setFont(QFont(FONT_MONO, 8)); lbl.setStyleSheet(f"color:{COLORS['text_dim']};border:none;")
            self.lista_disp.addWidget(lbl); return
        for d in dispositivos:
            self.lista_disp.addWidget(self._tarjeta_dispositivo(d))

    def _tarjeta_dispositivo(self, d):
        card = QFrame()
        borde = COLORS["accent"] if d.aloja_modelo else COLORS["border"]
        card.setStyleSheet(f"QFrame{{background:{COLORS['surface2']};border:1px solid {borde};border-radius:3px;}}")
        cl = QHBoxLayout(card); cl.setContentsMargins(12, 8, 12, 8); cl.setSpacing(10)
        col = QVBoxLayout(); col.setSpacing(2)
        titulo = d.nombre + ("  (este equipo)" if d.es_este else "")
        n = QLabel(titulo); n.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        n.setStyleSheet(f"color:{COLORS['text']};border:none;background:transparent;")
        from lune_core import descubrimiento as _D
        det = _D.ETIQUETA_ROL.get(d.rol, d.rol) + (f" · {d.modelo}" if d.modelo else "") + f"  ·  {d.host}"
        dd = QLabel(det); dd.setFont(QFont(FONT_MONO, 8)); dd.setStyleSheet(f"color:{COLORS['text_muted']};border:none;background:transparent;")
        col.addWidget(n); col.addWidget(dd); cl.addLayout(col, 1)
        if d.aloja_modelo and not d.es_este:
            btn = QPushButton("USAR COMO HOST"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold)); btn.setFixedHeight(30)
            btn.setStyleSheet(f"QPushButton{{background:{COLORS['surface3']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:2px;padding:0 12px;letter-spacing:1px;}}QPushButton:hover{{border-color:{COLORS['accent']};}}")
            btn.clicked.connect(lambda _=False, disp=d: self._usar_host(disp))
            cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _usar_host(self, d):
        # Rellena URL y rol; el token hay que ponerlo (o generarlo en el host).
        self.fields["hub_url_host"].setText(d.url_hub)
        self.hub_modo_combo.setCurrentIndex(max(0, self.hub_modo_combo.findData("terminal")))
        self.red_rol_combo.setCurrentIndex(max(0, self.red_rol_combo.findData("interaccion")))
        QMessageBox.information(self, "Host elegido",
            f"Este equipo usará «{d.nombre}» ({d.host}) como host.\n\n"
            "Pon el TOKEN del host abajo y pulsa GUARDAR. El modelo correrá en ese equipo; "
            "aquí solo interactúas (chat y avatar).")

    def _generar_token_hub(self):
        from lune_core.protocolo import generar_token
        self.fields["hub_token"].setText(generar_token())

    # ── Grupo de voz de entrada ────────────────────────────────────────────────
    def _build_voz_group(self) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)

        faltan = voz_entrada.dependencias_faltantes()
        if faltan:
            aviso = QLabel(
                "El dictado necesita librerías que no tienes:\n"
                f"    pip install {' '.join(faltan)}\n\n"
                "La transcripción es 100% local: el audio no sale de tu equipo. "
                "En el PC con GPU podrás usar modelos más grandes."
            )
            aviso.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        else:
            hay_mic, detalle = voz_entrada.hay_microfono()
            aviso = QLabel(f"Listo para dictar. Micrófono: {detalle}" if hay_mic
                           else f"Whisper está instalado, pero {detalle}")
            aviso.setStyleSheet(
                f"color:{COLORS['success'] if hay_mic else COLORS['warning']};border:none;")
        aviso.setWordWrap(True); aviso.setFont(QFont("Segoe UI", 9))
        fl.addWidget(aviso)

        lbl = QLabel("Modelo de Whisper (más grande = mejor, pero más lento)")
        lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(voz_entrada.MODELOS)
        self.whisper_combo.setCurrentText(self.config.get("voz", "modelo_whisper", "base"))
        self.whisper_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl); fl.addWidget(self.whisper_combo)

        self._add_input(fl, "voz_idioma", "Idioma del dictado (es, en, fr… vacío = detectar)",
                        self.config.get("voz", "idioma", "es"), False)

        # ── Micrófono: cuál usar (por nombre; vacío = el del sistema) y probarlo ──
        lbl_mic = QLabel("Micrófono (dictado y modo llamada)")
        lbl_mic.setFont(QFont("Segoe UI", 10)); lbl_mic.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Por defecto del sistema", "")
        for e in voz_entrada.listar_entradas():
            self.mic_combo.addItem(e["nombre"] + (" (defecto)" if e["defecto"] else ""), e["nombre"])
        idx_mic = self.mic_combo.findData(self.config.get("voz", "dispositivo_entrada", "") or "")
        self.mic_combo.setCurrentIndex(idx_mic if idx_mic >= 0 else 0)
        self.mic_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_mic); fl.addWidget(self.mic_combo)

        fila_mic = QHBoxLayout(); fila_mic.setSpacing(8)
        self.btn_probar_mic = QPushButton("PROBAR MICRÓFONO")
        self.btn_probar_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probar_mic.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_probar_mic.setFixedHeight(32)
        self.btn_probar_mic.setStyleSheet(
            f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};"
            f"border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 14px;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}"
            f"QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}"
        )
        self.btn_probar_mic.clicked.connect(self._probar_microfono)
        self.lbl_mic_prueba = QLabel("Pulsa, habla 1.5 s y te digo si te oigo.")
        self.lbl_mic_prueba.setWordWrap(True); self.lbl_mic_prueba.setFont(QFont("Segoe UI", 9))
        self.lbl_mic_prueba.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fila_mic.addWidget(self.btn_probar_mic); fila_mic.addWidget(self.lbl_mic_prueba, 1)
        fl.addLayout(fila_mic)
        self._probador_mic = None

        # ── Salida: por dónde suena Lune (pygame/SDL; vacío = la del sistema) ──
        lbl_out = QLabel("Salida de audio (por dónde habla Lune)")
        lbl_out.setFont(QFont("Segoe UI", 10)); lbl_out.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.salida_combo = QComboBox()
        self.salida_combo.addItem("Por defecto del sistema", "")
        for nombre in listar_salidas():
            self.salida_combo.addItem(nombre, nombre)
        idx_out = self.salida_combo.findData(self.config.get("voz", "dispositivo_salida", "") or "")
        self.salida_combo.setCurrentIndex(idx_out if idx_out >= 0 else 0)
        self.salida_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_out); fl.addWidget(self.salida_combo)

        # ── Voz de SALIDA: cómo habla Lune ─────────────────────────────────────
        sep = QLabel("Voz de salida (cómo habla Lune)")
        sep.setFont(QFont(FONT_DISPLAY, 11)); sep.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:8px;")
        fl.addWidget(sep)

        lbl_m = QLabel("Motor de voz")
        lbl_m.setFont(QFont("Segoe UI", 10)); lbl_m.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.voz_motor_combo = QComboBox()
        for texto, valor in (("Automática (edge-tts)", "auto"),
                             ("edge-tts (la voz de abajo, necesita internet)", "edge"),
                             ("gTTS (Google, necesita internet)", "gtts"),
                             ("Kokoro (100% local, sin internet)", "kokoro")):
            self.voz_motor_combo.addItem(texto, valor)
        # El motor que manda: el de la voz propia del personaje o el de config.
        actual_m = (voz_de(self._personaje_activo()).get("motor")
                    or self.config.get("voz", "motor_salida", "auto"))
        idx = self.voz_motor_combo.findData(actual_m)
        self.voz_motor_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.voz_motor_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_m); fl.addWidget(self.voz_motor_combo)

        # Voz de edge-tts, velocidad, tono, acento de gTTS y «Probar».
        self._build_voz_salida(fl)

        carpeta_k = self.config.get("voz", "kokoro_carpeta", "modelos_voz")
        if kokoro_backend.disponible(carpeta_k):
            aviso_k = QLabel("Kokoro está listo: voz local, sin que el audio salga de tu equipo.")
            aviso_k.setStyleSheet(f"color:{COLORS['success']};border:none;")
        else:
            aviso_k = QLabel(kokoro_backend.mensaje_instalacion(carpeta_k))
            aviso_k.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        aviso_k.setWordWrap(True); aviso_k.setFont(QFont("Segoe UI", 9))
        fl.addWidget(aviso_k)

        lbl_v = QLabel("Voz de Kokoro")
        lbl_v.setFont(QFont("Segoe UI", 10)); lbl_v.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.kokoro_voz_combo = QComboBox()
        for clave, nombre in kokoro_backend.VOCES_ES.items():
            self.kokoro_voz_combo.addItem(nombre, clave)
        # La de Kokoro que suena: la del personaje si trae una; si no, la de config.
        try:
            kokoro_actual = voces.resolver_voz(self.config, self._personaje_activo(), motor="kokoro").id
        except Exception:
            kokoro_actual = self.config.get("voz", "kokoro_voz", "ef_dora")
        idx_v = self.kokoro_voz_combo.findData(kokoro_actual)
        self.kokoro_voz_combo.setCurrentIndex(idx_v if idx_v >= 0 else 0)
        self.kokoro_voz_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_v); fl.addWidget(self.kokoro_voz_combo)

        self._add_input(fl, "kokoro_velocidad", "Velocidad de Kokoro (1.0 = normal)",
                        str(self.config.get("voz", "kokoro_velocidad", 1.0)), False)

        # ── Conversión de voz (RVC), experimental ──────────────────────────────
        self.rvc_check = QCheckBox("Convertir la voz con un modelo RVC (experimental)")
        self.rvc_check.setChecked(bool(self.config.get("voz", "rvc_activo", False)))
        self.rvc_check.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
        fl.addWidget(self.rvc_check)
        self._add_input(fl, "rvc_modelo", "Modelo RVC (.pth) — déjalo vacío si no usas RVC",
                        self.config.get("voz", "rvc_modelo", ""), False)
        self._add_input(fl, "rvc_transpose", "RVC: tono en semitonos (0 = igual)",
                        str(self.config.get("voz", "rvc_transpose", 0)), False)
        return frame

    def _probar_microfono(self):
        """Graba 1.5 s del micrófono elegido (en un hilo) y dice si se oyó algo."""
        from ui.audio_prueba import ProbadorMic
        if self._probador_mic is not None and self._probador_mic.isRunning():
            return
        nombre = self.mic_combo.currentData() or ""
        idx = voz_entrada.resolver_entrada(nombre) if nombre else None
        if nombre and idx is None:
            self.lbl_mic_prueba.setText(f"No encuentro «{nombre}». ¿Está conectado?")
            return
        self.btn_probar_mic.setEnabled(False)
        self.lbl_mic_prueba.setText("Habla ahora…")
        self._probador_mic = ProbadorMic(idx, parent=self)
        self._probador_mic.listo.connect(self._on_mic_probado)
        self._probador_mic.start()

    def _on_mic_probado(self, payload: str):
        import json
        self.btn_probar_mic.setEnabled(True)
        try:
            r = json.loads(payload)
        except Exception:
            r = {"mensaje": "No pude probar el micrófono."}
        self.lbl_mic_prueba.setText(r.get("mensaje", ""))
        self.lbl_mic_prueba.setStyleSheet(
            f"color:{COLORS['success'] if r.get('ok') else COLORS['warning']};border:none;")

    # ── Voz de salida elegible (edge-tts, gTTS) ────────────────────────────────
    def _personaje_activo(self) -> dict:
        personajes = self.datos_data.get("personajes") or [{}]
        return personajes[self._indice_personaje_activo()]

    def _build_voz_salida(self, fl):
        """Voz de edge-tts por país, velocidad y tono (−50…+50), acento de gTTS y Probar."""
        personaje = self._personaje_activo()
        actual = voces.resolver_voz(self.config, personaje)
        propia = voz_de(personaje)
        if propia:
            nota = QLabel(f"«{personaje.get('nombre', 'Lune')}» tiene voz propia en datos.json: "
                          "lo que elijas aquí se guarda en su voz.")
            nota.setWordWrap(True); nota.setFont(QFont("Segoe UI", 9))
            nota.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
            fl.addWidget(nota)

        lbl = QLabel("Voz de edge-tts")
        lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.edge_voz_combo = QComboBox()
        self.edge_voz_combo.setStyleSheet(self._estilo_combo())
        # Sin red usa la lista embebida; si la caché está vieja, se renueva en un hilo.
        self._rellenar_voces(voces.listar_edge(), actual.id if voces.es_id_edge(actual.id)
                             else voces.resolver_voz(self.config, personaje, motor="edge").id)
        fl.addWidget(lbl); fl.addWidget(self.edge_voz_combo)

        self.voz_rate_slider, self.lbl_voz_rate = self._slider_voz(
            fl, "Velocidad", numero_ajuste(actual.rate, "%"), texto_rate)
        self.voz_pitch_slider, self.lbl_voz_pitch = self._slider_voz(
            fl, "Tono", numero_ajuste(actual.pitch, "Hz"), texto_pitch)

        lbl_t = QLabel("Acento de gTTS")
        lbl_t.setFont(QFont("Segoe UI", 10)); lbl_t.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.gtts_tld_combo = QComboBox()
        for tld, pais in voces.GTTS_TLD.items():
            self.gtts_tld_combo.addItem(f"{pais} ({tld})", tld)
        idx = self.gtts_tld_combo.findData(actual.tld)
        self.gtts_tld_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.gtts_tld_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_t); fl.addWidget(self.gtts_tld_combo)

        fila = QHBoxLayout(); fila.setSpacing(8)
        self.btn_probar_voz = QPushButton("PROBAR VOZ")
        self.btn_probar_voz.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probar_voz.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_probar_voz.setFixedHeight(32)
        self.btn_probar_voz.setStyleSheet(self._estilo_boton())
        self.btn_probar_voz.clicked.connect(self._probar_voz)
        self.lbl_probar_voz = QLabel("Suena aunque la voz esté apagada, con lo elegido aquí (sin guardar).")
        self.lbl_probar_voz.setWordWrap(True); self.lbl_probar_voz.setFont(QFont("Segoe UI", 9))
        self.lbl_probar_voz.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        if self.voice is None:
            self.btn_probar_voz.setEnabled(False)
            self.lbl_probar_voz.setText("Probar necesita el motor de voz de la app.")
        fila.addWidget(self.btn_probar_voz); fila.addWidget(self.lbl_probar_voz, 1)
        fl.addLayout(fila)

    def _rellenar_voces(self, lista, seleccion: str):
        combo = self.edge_voz_combo
        combo.clear()
        modelo = combo.model()
        for texto, vid in items_voces(lista):
            combo.addItem(texto, vid)
            if vid is None:                                   # cabecera de país
                item = modelo.item(combo.count() - 1) if hasattr(modelo, "item") else None
                if item is not None:
                    item.setEnabled(False)
        if seleccion and combo.findData(seleccion) < 0:       # voz fuera de la lista: se conserva
            combo.addItem(f"{seleccion} (personalizada)", seleccion)
        idx = combo.findData(seleccion or voces.VOZ_POR_DEFECTO)
        if idx < 0:
            idx = combo.findData(voces.VOZ_POR_DEFECTO)
        combo.setCurrentIndex(max(idx, 0))

    def _slider_voz(self, fl, titulo: str, valor: int, formato):
        lbl = QLabel(titulo)
        lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        fila = QHBoxLayout(); fila.setSpacing(10)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(-AJUSTE_VOZ_MAX, AJUSTE_VOZ_MAX); slider.setSingleStep(1); slider.setPageStep(10)
        slider.setValue(int(valor))
        valor_lbl = QLabel(formato(valor)); valor_lbl.setFixedWidth(60)
        valor_lbl.setFont(QFont(FONT_MONO, 9)); valor_lbl.setStyleSheet(f"color:{COLORS['accent']};border:none;")
        slider.valueChanged.connect(lambda v, l=valor_lbl, f=formato: l.setText(f(v)))
        fila.addWidget(slider, 1); fila.addWidget(valor_lbl)
        fl.addWidget(lbl); fl.addLayout(fila)
        return slider, valor_lbl

    def params_voz_ui(self) -> dict:
        """Lo elegido en el panel como {motor, id, rate, pitch, tld} (para Probar y guardar)."""
        motor = self.voz_motor_combo.currentData() or "auto"
        edge_voz = self.edge_voz_combo.currentData() or voces.VOZ_POR_DEFECTO
        if motor == "kokoro":
            vid = self.kokoro_voz_combo.currentData() or "ef_dora"
        elif motor == "gtts":
            vid = ""
        else:
            vid = edge_voz
        return {"motor": motor, "id": vid, "edge_voz": edge_voz,
                "rate": texto_rate(self.voz_rate_slider.value()),
                "pitch": texto_pitch(self.voz_pitch_slider.value()),
                "tld": self.gtts_tld_combo.currentData() or voces.TLD_POR_DEFECTO}

    def _probar_voz(self):
        if self.voice is None:
            return
        try:
            ok = self.voice.probar_voz(self.params_voz_ui())
        except Exception as e:
            ok, error = False, str(e)
        else:
            error = getattr(self.voice, "ultimo_error", "") or ""
        if ok:
            self.lbl_probar_voz.setText("Probando…")
            self.lbl_probar_voz.setStyleSheet(f"color:{COLORS['success']};border:none;")
        else:
            self.lbl_probar_voz.setText(error or "No pude probar la voz (sin motor o sin salida de audio).")
            self.lbl_probar_voz.setStyleSheet(f"color:{COLORS['warning']};border:none;")

    # ── Grupo de actualizaciones ───────────────────────────────────────────────
    def _build_update_group(self) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)

        # El estado real se rellena en cuanto responda el worker.
        self.lbl_repo = QLabel("Consultando el repositorio…")
        self.lbl_repo.setWordWrap(True); self.lbl_repo.setFont(QFont(FONT_MONO, 9))
        self.lbl_repo.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(self.lbl_repo)

        explicacion = QLabel(
            "«Actualizar» trae los cambios de git, instala lo que falte de "
            "requirements.txt y reinicia Lune. Si tienes trabajo sin commitear "
            "no toca nada y te avisa."
        )
        explicacion.setWordWrap(True); explicacion.setFont(QFont("Segoe UI", 9))
        explicacion.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(explicacion)

        fila = QHBoxLayout(); fila.setSpacing(8)
        self.btn_comprobar = QPushButton("BUSCAR ACTUALIZACIONES")
        self.btn_comprobar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_comprobar.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_comprobar.setFixedHeight(36)
        self.btn_comprobar.setStyleSheet(
            f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};"
            f"border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 14px;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}"
            f"QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}"
        )
        self.btn_comprobar.clicked.connect(self._comprobar_updates)
        self.btn_comprobar.setEnabled(False)   # se habilita al saber el estado

        self.btn_actualizar = QPushButton("ACTUALIZAR Y REINICIAR")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_actualizar.setFixedHeight(36)
        self.btn_actualizar.setStyleSheet(
            f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['cyan_dark']},"
            f"stop:1 {COLORS['accent']});color:{COLORS['bg']};border:none;border-radius:3px;"
            f"padding:0 14px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['accent']};}}"
            f"QPushButton:disabled{{background:{COLORS['surface3']};color:{COLORS['text_dim']};}}"
        )
        self.btn_actualizar.clicked.connect(self._aplicar_update)
        self.btn_actualizar.setEnabled(False)
        fila.addWidget(self.btn_comprobar); fila.addWidget(self.btn_actualizar); fila.addStretch()
        fl.addLayout(fila)

        self._estado_git = EstadoGitWorker()
        self._estado_git.listo.connect(self._on_estado_repo)
        self._estado_git.start()

        self.lbl_update = QLabel("")
        self.lbl_update.setWordWrap(True); self.lbl_update.setFont(QFont(FONT_MONO, 9))
        self.lbl_update.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(self.lbl_update)

        # Estado de las funciones opcionales
        titulo_dep = QLabel("Funciones opcionales")
        titulo_dep.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        titulo_dep.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:8px;")
        fl.addWidget(titulo_dep)

        for o in actualizador.estado_opcionales():
            if o["disponible"]:
                texto, color = f"OK   {o['funcion']}", COLORS["success"]
            else:
                texto, color = f"—    {o['funcion']}  →  {o['comando']}", COLORS["warning"]
            linea = QLabel(texto); linea.setFont(QFont(FONT_MONO, 9)); linea.setWordWrap(True)
            linea.setToolTip(o["nota"])
            linea.setStyleSheet(f"color:{color};border:none;")
            fl.addWidget(linea)

        return frame

    def _on_estado_repo(self, est):
        if est.get("ok"):
            if est["limpio"]:
                estado_local = "Sin cambios locales."
            else:
                estado_local = f"Tienes {len(est['modificados'])} archivo(s) sin guardar."
            self.lbl_repo.setText(
                f"Rama <b>{est['rama']}</b> · commit <b>{est['commit']}</b><br>{estado_local}")
            self.btn_comprobar.setEnabled(True)
            self.btn_actualizar.setEnabled(True)
        else:
            self.lbl_repo.setText(est.get("mensaje", "No pude leer el repositorio."))

    def _comprobar_updates(self):
        self.btn_comprobar.setEnabled(False); self.btn_comprobar.setText("BUSCANDO…")
        self.lbl_update.setText("Consultando el remoto…")
        self.lbl_update.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self._git = GitWorker("comprobar", self.config.get("actualizaciones", "rama", "master"))
        self._git.listo.connect(self._on_comprobado)
        self._git.start()

    def _on_comprobado(self, res):
        self.btn_comprobar.setEnabled(True); self.btn_comprobar.setText("BUSCAR ACTUALIZACIONES")
        mensaje = res.get("mensaje", "")
        if res.get("commits"):
            mensaje += "\n\n" + "\n".join(f"  · {c}" for c in res["commits"][:10])
        color = COLORS["success"] if res.get("ok") else COLORS["error"]
        if res.get("ok") and not res.get("hay_novedades"):
            color = COLORS["text_muted"]
        self.lbl_update.setText(mensaje)
        self.lbl_update.setStyleSheet(f"color:{color};border:none;")

    def _aplicar_update(self):
        r = QMessageBox.question(
            self, "Actualizar Lune",
            "Voy a traer los cambios de git, instalar lo que falte y reiniciar la app.\n\n"
            "¿Seguimos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        self.btn_actualizar.setEnabled(False); self.btn_comprobar.setEnabled(False)
        self.btn_actualizar.setText("ACTUALIZANDO…")
        self._git = GitWorker("actualizar", self.config.get("actualizaciones", "rama", "master"))
        self._git.progreso.connect(
            lambda m: (self.lbl_update.setText(m),
                       self.lbl_update.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")))
        self._git.listo.connect(self._on_actualizado)
        self._git.start()

    def _on_actualizado(self, res):
        self.btn_actualizar.setEnabled(True); self.btn_comprobar.setEnabled(True)
        self.btn_actualizar.setText("ACTUALIZAR Y REINICIAR")

        if not res.get("ok"):
            self.lbl_update.setText(res.get("mensaje", "No se pudo actualizar."))
            self.lbl_update.setStyleSheet(f"color:{COLORS['error']};border:none;")
            QMessageBox.warning(self, "No pude actualizar", res.get("mensaje", ""))
            return

        detalle = res.get("detalle", "")
        self.lbl_update.setText(res["mensaje"])
        self.lbl_update.setStyleSheet(f"color:{COLORS['success']};border:none;")

        if not res.get("actualizado"):
            QMessageBox.information(self, "Todo al día", res["mensaje"])
            return

        r = QMessageBox.question(
            self, "Reiniciar",
            f"{res['mensaje']}\n\n{detalle[:400]}\n\n¿Reinicio Lune ahora para aplicarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            actualizador.reiniciar()

    def _probar_ollama(self):
        url = self.fields["ollama_url"].text().strip()
        self.btn_probar.setEnabled(False); self.btn_probar.setText("BUSCANDO…")
        self.lbl_ollama.setText(f"Conectando con {ollama_client.normalizar_url(url)}…")
        self.lbl_ollama.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self._sondeo = SondeoOllamaWorker(url)
        self._sondeo.listo.connect(self._on_sondeo)
        self._sondeo.start()

    def _on_sondeo(self, ok, modelos, mensaje):
        self.btn_probar.setEnabled(True); self.btn_probar.setText("BUSCAR MODELOS")
        color = COLORS["success"] if ok else COLORS["error"]
        self.lbl_ollama.setText(mensaje)
        self.lbl_ollama.setStyleSheet(f"color:{color};border:none;")
        if not modelos:
            return
        # Conservamos lo que ya estaba escrito si sigue existiendo
        actual = self.ollama_combo.currentText().strip()
        self.ollama_combo.clear()
        self.ollama_combo.addItems(modelos)
        if actual in modelos:
            self.ollama_combo.setCurrentText(actual)

    # ── Escritorio (corte 4) ───────────────────────────────────────────────────
    def servicios_c4(self):
        """Los servicios del corte 4 ahora (None si aún no se montaron)."""
        s = self._servicios
        if callable(s) and not hasattr(s, "desmontar"):
            try:
                s = s()
            except Exception:
                s = None
        return s

    def usar_servicios(self, servicios) -> None:
        """La nativa montó el corte 4 (tras construir Ajustes): el panel de escritorio
        recibe el gestor de atajos («Detectar» los pausa; conflictos con otras apps)."""
        if not callable(self._servicios) or hasattr(self._servicios, "desmontar"):
            self._servicios = servicios
        panel = getattr(self, "escritorio_panel", None)
        if panel is not None:
            panel.set_atajos(getattr(servicios, "atajos", None))
        self._enlazar_ocio(servicios)

    def _enlazar_ocio(self, servicios) -> None:
        """Cortes 5/6: el panel de ocio recibe ServiciosCorte4.ocio (alarmas, pantalla
        grande y baile) y lo suelta cuando esos servicios se desmontan."""
        panel = getattr(self, "ocio_panel", None)
        if panel is None:
            return
        ocio = getattr(servicios, "ocio", None) if servicios is not None else None
        try:
            panel.enlazar(ocio)
        except Exception:
            return
        deshacer = getattr(servicios, "_deshacer", None) if ocio is not None else None
        if isinstance(deshacer, list):
            def soltar(ocio=ocio):
                if getattr(panel, "alarmas", None) is getattr(ocio, "alarmas", None) \
                        and getattr(panel, "baile", None) is getattr(ocio, "baile", None) \
                        and getattr(panel, "grande", None) is getattr(ocio, "grande", None):
                    try:
                        panel.enlazar(None)
                    except RuntimeError:
                        pass
            deshacer.append(soltar)

    def _escritorio_cambiado(self, seccion: str) -> None:
        panel = getattr(self, "escritorio_panel", None)
        claves = None
        if panel is not None:
            ultimo = getattr(panel, "ultimo_guardado", None)
            if isinstance(ultimo, dict) and seccion in ultimo:
                claves = set(ultimo[seccion])
        aplicar_seccion_escritorio(seccion, self.servicios_c4(), self.config, claves)
        self.escritorio_cambiado.emit(seccion)

    # ── Helpers de UI ──────────────────────────────────────────────────────────
    def _visibilidad_vrm(self, *_):
        """El panel de modelos 3D solo con «Avatar VRM 3D» en el combo."""
        panel = getattr(self, "vrm_panel", None)
        if panel is not None:
            panel.setVisible(self.render_combo.currentData() == "vrm")

    def _aviso_vrm(self) -> QLabel:
        """Estado del avatar 3D: WebEngine instalado y modelo .vrm presente."""
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
            webengine = True
        except Exception:
            webengine = False
        from pathlib import Path
        hay_vrm = Path("modelo_vrm").exists() and any(Path("modelo_vrm").glob("*.vrm"))
        if webengine and hay_vrm:
            lbl = QLabel("Avatar 3D listo: elige «Avatar VRM 3D» y saca a Lune con el tile MASCOTA. "
                         "Cada personaje puede traer su propio .vrm (campo «vrm» en datos.json).")
            lbl.setStyleSheet(f"color:{COLORS['success']};border:none;")
        elif not webengine:
            lbl = QLabel("El avatar 3D (VRM) necesita:\n    pip install PyQt6-WebEngine\n"
                         "(usa la versión que coincida con tu PyQt6). Mientras, se usan sprites.")
            lbl.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        else:
            lbl = QLabel("Falta un modelo: pon un archivo .vrm en la carpeta modelo_vrm/.")
            lbl.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        return lbl

    def _estilo_combo(self):
        return (f"QComboBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
                f"border-radius:3px;padding:8px 12px;color:{COLORS['text']};}}"
                f"QComboBox QAbstractItemView{{background:{COLORS['surface2']};color:{COLORS['text']};"
                f"selection-background-color:{COLORS['accent']};}}")

    def _estilo_boton(self):
        return (f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};"
                f"border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 14px;letter-spacing:1px;}}"
                f"QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}"
                f"QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")

    def _create_section_title(self, text):
        lbl = QLabel(text); lbl.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{COLORS['accent']}; margin-top: 10px; letter-spacing:1px;")
        return lbl

    def _create_group_frame(self):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {COLORS['surface']}; border-radius: 3px; border: 1px solid {COLORS['border']}; padding: 15px; }}")
        return f

    def _add_input(self, layout, key, label_text, default_val, is_password):
        lbl = QLabel(label_text); lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']}; border: none; padding: 0;")
        inp = QLineEdit(); inp.setText(default_val)
        inp.setEchoMode(QLineEdit.EchoMode.Password if is_password else QLineEdit.EchoMode.Normal)
        inp.setStyleSheet(f"QLineEdit{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;padding:10px 12px;color:{COLORS['text']};}}QLineEdit:focus{{border:1px solid {COLORS['accent']};}}")
        self.fields[key] = inp
        layout.addWidget(lbl); layout.addWidget(inp)

    def _add_textarea(self, layout, key, label_text, default_val, height):
        lbl = QLabel(label_text); lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']}; border: none; padding: 0;")
        txt = QTextEdit(); txt.setPlainText(default_val); txt.setFixedHeight(height)
        txt.setStyleSheet(f"QTextEdit{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;padding:10px;color:{COLORS['text']};font-family:'Segoe UI';}}QTextEdit:focus{{border:1px solid {COLORS['accent']};}}")
        self.fields[key] = txt
        layout.addWidget(lbl); layout.addWidget(txt)

    @staticmethod
    def _entero(texto, defecto):
        try:
            return int(float(str(texto).strip()))
        except (TypeError, ValueError):
            return defecto

    @staticmethod
    def _flotante(texto, defecto):
        try:
            return float(str(texto).strip().replace(",", "."))
        except (TypeError, ValueError):
            return defecto

    # ── Guardado ───────────────────────────────────────────────────────────────
    # Cada campo del panel es una clave de _valores_ui():
    #   ("datos", sección, clave)  → datos.json
    #   ("personaje", campo)       → el personaje que se estaba editando
    #   ("voz_salida", campo)      → su voz propia o, si no tiene, config.voz (A1)
    #   ("cfg", sección, clave)    → config.json
    #   ("autoinicio",)            → arrancar con Windows
    # Al guardar solo se escribe lo que cambió desde que se cargó (o desde el
    # último guardado): así no se deshace lo que otros escribieron mientras tanto.
    _VOZ_A_CONFIG = {"motor": "motor_salida", "edge_voz": "edge_voz", "kokoro_voz": "kokoro_voz",
                     "rate": "edge_rate", "pitch": "edge_pitch", "tld": "gtts_tld"}

    def _modo_hub_ui(self) -> str:
        """Modo del hub según el panel: el rol del dispositivo manda (host/interaccion/
        hibrido → host/terminal/local); sin combo de rol, el del combo de modo."""
        if hasattr(self, "red_rol_combo"):
            from servicios.red_service import rol_a_modo
            return rol_a_modo(self.red_rol_combo.currentData() or "hibrido")
        return self.hub_modo_combo.currentData() or "local"

    def _valores_ui(self) -> dict:
        f = self.fields
        pv = self.params_voz_ui()
        v = {
            ("datos", "apis", "openrouter_key"): f["openrouter_api_key"].text().strip(),
            ("datos", "apis", "telegram_token"): f["telegram_token"].text().strip(),
            ("datos", "apis", "telegram_admin_id"): f["telegram_admin_id"].text().strip(),
            ("datos", "modelos", "openrouter_model"): f["openrouter_model"].text().strip() or "openrouter/auto",
            ("datos", "modelos", "ollama_url"): ollama_client.normalizar_url(f["ollama_url"].text()),
            ("datos", "modelos", "ollama_model"): self.ollama_combo.currentText().strip(),
            ("datos", "modelos", "ollama_keep_alive"): f["ollama_keep_alive"].text().strip() or "30m",
            ("datos", "modelos", "ollama_num_ctx"): self._entero(f["ollama_num_ctx"].text(), 8192),
            ("datos", "modelos", "ollama_timeout"): self._entero(f["ollama_timeout"].text(), 300),
            ("datos", "modelos", "temperatura"): self._flotante(f["temperatura"].text(), 0.7),
            # API compatible con OpenAI (vacía = apagada; AIManager la quita)
            ("datos", "modelos", "compat_url"): f["compat_url"].text().strip().rstrip("/"),
            ("datos", "modelos", "compat_key"): f["compat_key"].text().strip(),
            ("datos", "modelos", "compat_model"): f["compat_model"].text().strip(),
            ("datos", "hub", "modo"): self._modo_hub_ui(),
            ("datos", "hub", "puerto"): self._entero(f["hub_puerto"].text(), 7777),
            ("datos", "hub", "url_host"): f["hub_url_host"].text().strip().rstrip("/"),
            ("datos", "hub", "token"): f["hub_token"].text().strip(),
            ("datos", "bot", "max_historial"): self._entero(f["max_historial"].text(), 20),
            # Personalidad: SOLO el personaje que se estaba editando
            ("personaje", "nombre"): f["bot_nombre"].text().strip() or "Lune",
            ("personaje", "systemPrompt"): f["bot_system"].toPlainText().strip(),
            ("personaje", "fraseInicial"): f["bot_saludo"].toPlainText().strip(),
            # Voz de salida (lo que suena: la del personaje si trae una; si no, la global)
            ("voz_salida", "motor"): pv["motor"],
            ("voz_salida", "edge_voz"): pv["edge_voz"],
            ("voz_salida", "kokoro_voz"): self.kokoro_voz_combo.currentData() or "ef_dora",
            ("voz_salida", "rate"): pv["rate"],
            ("voz_salida", "pitch"): pv["pitch"],
            ("voz_salida", "tld"): pv["tld"],
            # Notas (RAG)
            ("cfg", "notas", "activo"): self.notas_check.isChecked(),
            ("cfg", "notas", "carpeta"): f["notas_carpeta"].text().strip() or "notas",
            ("cfg", "notas", "modelo_embeddings"): f["notas_modelo"].text().strip() or "nomic-embed-text",
            ("cfg", "notas", "top_k"): self._entero(f["notas_topk"].text(), 3),
            # Avatar, voz de entrada y del motor, interfaz
            ("cfg", "avatar", "pack"): self.pack_combo.currentText(),
            ("cfg", "avatar", "render"): self.render_combo.currentData() or "sprites",
            ("cfg", "voz", "modelo_whisper"): self.whisper_combo.currentText(),
            ("cfg", "voz", "idioma"): f["voz_idioma"].text().strip(),
            ("cfg", "voz", "dispositivo_entrada"): self.mic_combo.currentData() or "",
            ("cfg", "voz", "dispositivo_salida"): self.salida_combo.currentData() or "",
            ("cfg", "voz", "kokoro_velocidad"): self._flotante(f["kokoro_velocidad"].text(), 1.0),
            ("cfg", "voz", "rvc_activo"): self.rvc_check.isChecked(),
            ("cfg", "voz", "rvc_modelo"): f["rvc_modelo"].text().strip(),
            ("cfg", "voz", "rvc_transpose"): self._entero(f["rvc_transpose"].text(), 0),
            ("cfg", "interfaz", "modo"): self.interfaz_combo.currentData() or "web",
            ("cfg", "telegram", "ordenes_pc"): self.ordenes_tg_check.isChecked(),
            ("autoinicio",): self.autoinicio_check.isChecked(),
        }
        for clave, chk in self.feature_checks.items():
            v[("cfg", "features", clave)] = chk.isChecked()
        if hasattr(self, "red_rol_combo"):
            v[("cfg", "red", "rol")] = self.red_rol_combo.currentData() or "hibrido"
            v[("cfg", "red", "nombre")] = f["red_nombre"].text().strip()
        return v

    @staticmethod
    def _buscar_personaje(d: dict, nombre) -> int:
        """Índice del personaje `nombre` en `d` (sin distinguir mayúsculas), o -1."""
        nl = str(nombre or "").lower()
        for i, p in enumerate(d.get("personajes") or []):
            if isinstance(p, dict) and nl and (p.get("nombre") or "").lower() == nl:
                return i
        return -1

    @staticmethod
    def _voz_con_cambios(actual: dict, cambios: dict, ui: dict) -> dict:
        """La voz propia del personaje con SOLO lo que se cambió en el panel. El id va
        con el motor: si cambió el motor o la voz de ese motor, se toma la del combo."""
        nueva = dict(actual or {})
        motor = ui.get("motor") or "auto"
        if "motor" in cambios:
            if motor in ("", "auto"):
                nueva.pop("motor", None)
            else:
                nueva["motor"] = motor
        if motor in ("", "auto", "edge") and ({"motor", "edge_voz"} & set(cambios)):
            nueva["id"] = ui["edge_voz"]
        elif motor == "kokoro" and ({"motor", "kokoro_voz"} & set(cambios)):
            nueva["id"] = ui["kokoro_voz"]
        for k in ("rate", "pitch", "tld"):
            if k in cambios:
                nueva[k] = ui[k]
        return nueva

    def _save(self):
        actual = self._valores_ui()
        cambios = {k: v for k, v in actual.items() if self._inicial.get(k, actual) != v}
        # datos.json FRESCO: lo que escribieron otros (el panel VRM, cambiar_voz,
        # patata, la otra interfaz…) no se pisa con la copia de cuando se abrió esto.
        d = datos.cargar() or {"apis": {}, "modelos": {}, "bot": {}, "personajes": []}
        for sec in ("apis", "modelos", "bot", "hub"):
            if not isinstance(d.get(sec), dict):
                d[sec] = {}
        for clave, valor in cambios.items():
            if clave[0] == "datos":
                d[clave[1]][clave[2]] = valor
        # Clave de la API compatible vaciada: fuera también el alias apis.compat_key
        # (si no, datos.compat_key() la seguiría usando).
        if ("datos", "modelos", "compat_key") in cambios and not actual[("datos", "modelos", "compat_key")]:
            d["apis"].pop("compat_key", None)

        # Personalidad y voz: el personaje que se estaba editando (aunque ya no sea el activo).
        del_personaje = {k[1]: v for k, v in cambios.items() if k[0] == "personaje"}
        de_voz = {k[1]: v for k, v in cambios.items() if k[0] == "voz_salida"}
        idx = self._buscar_personaje(d, self._nombre_editado)
        if idx < 0 and del_personaje and not self._nombre_editado and not d.get("personajes"):
            d["personajes"] = [{}]              # datos.json sin personajes: se crea el primero
            idx = 0
        personaje = d["personajes"][idx] if idx >= 0 else None
        if personaje is not None:
            viejo = personaje.get("nombre")
            for campo, valor in del_personaje.items():
                personaje[campo] = valor
            nuevo = personaje.get("nombre")
            activo = str(d["bot"].get("personaje_default") or "")
            if "nombre" in del_personaje and (not activo or activo.lower() == str(viejo or "").lower()):
                d["bot"]["personaje_default"] = nuevo      # renombrar el activo lo deja activo
            self._nombre_editado = nuevo

        # Voz de salida: si el personaje trae voz propia, el cambio va a ella y la
        # global no se toca (si no, la del personaje ganaría y no se notaría); si no,
        # a config.voz.
        propia = voz_de(personaje) if personaje is not None else {}
        cfg_voz = {}
        if de_voz:
            ui_voz = {k[1]: v for k, v in actual.items() if k[0] == "voz_salida"}
            if propia:
                personaje["voz"] = self._voz_con_cambios(propia, de_voz, ui_voz)
            else:
                cfg_voz = {self._VOZ_A_CONFIG[k]: v for k, v in de_voz.items()}

        datos.guardar(d)
        self.datos_data = d

        # Seguimiento del cursor que el panel VRM aún no escribió (espera 250 ms) y lo
        # de los paneles de escritorio (corte 4) y de ocio (cortes 5/6, 300 ms):
        # escrito ya y aplicado.
        for nombre in ("vrm_panel", "escritorio_panel", "ocio_panel"):
            panel = getattr(self, nombre, None)
            if panel is not None:
                try:
                    panel.guardar_ya()
                except Exception:
                    pass

        # Modo de interfaz: no se escribe aquí. Queda pedido y la ventana se lo pasa a
        # GestorInterfaz (ui/cambio_interfaz.py) tras «saved»: él lo guarda y, si el
        # cambio falla, vuelve el de antes (mostrar_modo_interfaz).
        self.modo_interfaz_pedido = cambios.pop(("cfg", "interfaz", "modo"), None)
        # config.json: solo lo cambiado (features, avatar, voz de entrada, notas, red…)
        for clave, valor in cambios.items():
            if clave[0] == "cfg":
                self.config.config.setdefault(clave[1], {})[clave[2]] = valor
        for clave, valor in cfg_voz.items():
            self.config.config.setdefault("voz", {})[clave] = valor
        # El rol manda sobre el modo del hub: el combo de modo lo refleja.
        self.hub_modo_combo.setCurrentIndex(
            max(0, self.hub_modo_combo.findData(actual[("datos", "hub", "modo")])))
        # Autoinicio con Windows (clave Run del usuario; ver servicios/autoinicio.py)
        if ("autoinicio",) in cambios:
            try:
                from servicios import autoinicio as _auto
                _auto.establecer(actual[("autoinicio",)])
            except Exception:
                pass
        self.config.save()
        self._inicial = actual

        # Aplicar cambios en caliente
        lune_face.set_anim_video(self.config.feature("animaciones_video", True))
        lune_face.set_active_pack(self.config.get("avatar", "pack", "default"))

        self.saved.emit()

    def mostrar_modo_interfaz(self, modo: str) -> None:
        """El combo vuelve a `modo` (p. ej. el cambio de interfaz falló) sin que cuente
        como un cambio pendiente al guardar."""
        combo = getattr(self, "interfaz_combo", None)
        if combo is None:
            return
        idx = combo.findData(str(modo or ""))
        if idx < 0:
            return
        combo.setCurrentIndex(idx)
        inicial = getattr(self, "_inicial", None)
        if isinstance(inicial, dict):
            inicial[("cfg", "interfaz", "modo")] = combo.currentData()
        self.modo_interfaz_pedido = None
