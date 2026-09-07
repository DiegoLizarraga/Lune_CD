"""
ui/web_bridge.py — Puente entre la UI web (Shibuya Punk) y el backend de Lune.

La ventana web (ui/web_shell.py) muestra el diseño real en una QWebEngineView y
expone ESTE objeto por QWebChannel como `window.lune`. El JavaScript llama a los
slots (enviar/detener…) y escucha las señales (chunk/done/acto/herramienta) para
pintar el chat con el modelo, la memoria y las herramientas de verdad.

Reutiliza AIWorker (mismo hilo de consulta que la app nativa), MemoriaManager,
ToolManager y AIManager: la lógica de chat es la misma, solo cambia la piel.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from nucleo.config import Config
from nucleo.memoria import MemoriaManager
from nucleo import datos, personajes
from servicios.ai_manager import AIManager
from servicios.ai_worker import AIWorker
from servicios.tools import ToolManager
from servicios.voice import VoiceEngine
from lune_core import marcadores

# Emoción canónica del modelo → estado de mascota del set anime (assets/mascot/anime).
EMOCION_A_MASCOTA = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
}


def _provider_id(web_provider: str) -> str:
    """'local' → ollama · 'cloud' → openrouter (lo que usa la UI web)."""
    return "ollama" if web_provider == "local" else "openrouter"


class LuneBridge(QObject):
    # ── Señales hacia el JS ──────────────────────────────────────────────────────
    chunk = pyqtSignal(str)                 # texto ACUMULADO del stream
    done = pyqtSignal(str, str)             # (texto_final_limpio, estado_mascota)
    acto = pyqtSignal(str)                  # estado de mascota durante la respuesta
    emocion = pyqtSignal(str, float)        # (estado_mascota, intensidad 0..1) al terminar
    herramienta = pyqtSignal(bool, str, str, str)   # (ok, icono, titulo, detalle)
    estado = pyqtSignal(str)                # 'live' | 'busy' | 'error'

    # Señales de estado hacia el JS (toggles y paneles).
    voz_estado = pyqtSignal(bool)
    telegram_estado = pyqtSignal(bool, str)
    mascota_estado = pyqtSignal(bool)
    aviso = pyqtSignal(str)                 # toast breve para el usuario
    adjuntos_cambio = pyqtSignal(str)       # json de nombres de archivos pendientes
    grabando = pyqtSignal(bool)             # micrófono grabando/parado
    dictado = pyqtSignal(str)               # texto transcrito del micrófono
    llamada_estado = pyqtSignal(bool, str)  # modo llamada: (activa, estado/aviso)
    usuario_dijo = pyqtSignal(str)          # en llamada: lo que dijo el usuario → el JS lo envía
    mic_prueba = pyqtSignal(str)            # resultado json de «Probar micrófono»

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None,
                 voice=None, parent=None):
        super().__init__(parent)
        self.config = config or Config()
        self.ai = ai_manager or AIManager()
        self.memoria = memoria or MemoriaManager()
        self.tools = tools or ToolManager()
        self.voice = voice or VoiceEngine(self.config)
        self._worker: AIWorker | None = None
        self._tg_worker = None
        self._overlay = None
        self._chats = None
        self._adjuntos_pend = []            # documentos/imágenes cargados para el próximo envío
        self._grabadora = None
        self._transcriptor = None
        self._probador = None               # hilo de «Probar micrófono»
        self._llamada = None                # LlamadaWorker mientras el modo llamada está activo
        # En modo llamada, la respuesta final la habla el worker (bloqueando) y
        # luego vuelve a escuchar; por eso se engancha a `done`.
        self.done.connect(self._llamada_entregar)
        # Aburrimiento: si pasas N minutos sin escribirle, Lune se aburre y te dice
        # algo (una sola vez por racha; se rearma con tu siguiente mensaje).
        self._aburrida_t = QTimer(self)
        self._aburrida_t.setSingleShot(True)
        self._aburrida_t.timeout.connect(self._aburrida)
        self._rearmar_aburrimiento()

    # ── API para el JS ───────────────────────────────────────────────────────────
    @pyqtSlot(str, str)
    def enviar(self, texto: str, provider: str = "local"):
        texto = (texto or "").strip()
        pend = list(self._adjuntos_pend)
        if (not texto and not pend) or (self._worker and self._worker.isRunning()):
            return
        provider_id = _provider_id(provider)
        self._rearmar_aburrimiento()      # escribiste: Lune ya no está aburrida

        # Con adjuntos, todo va al modelo (ni la memoria ni las herramientas los
        # entienden). Sin adjuntos, primero se prueban memoria y herramientas.
        if not pend:
            try:
                resp_mem = self.memoria.procesar_mensaje_usuario(texto)
            except Exception:
                resp_mem = None
            if resp_mem:
                self.done.emit(resp_mem, "happy")
                return
            try:
                tr = self.tools.detectar_y_ejecutar(texto)
            except Exception:
                tr = None
            if tr:
                self.herramienta.emit(bool(tr.ok), "bolt", tr.mensaje[:48], tr.mensaje)
                self.done.emit("", "happy" if tr.ok else "error")
                return

        try:
            contexto = self.memoria.obtener_contexto_para_prompt()
        except Exception:
            contexto = ""
        imagenes = []
        if pend:
            try:
                from nucleo import adjuntos as adj
                contexto = contexto + adj.bloque_para_prompt(pend)
                imagenes = adj.imagenes_base64(pend)
            except Exception:
                pass
            self._adjuntos_pend = []
            self.adjuntos_cambio.emit("[]")

        self.estado.emit("busy")
        self.acto.emit("thinking")
        self._worker = AIWorker(
            self.ai, texto or "Analiza lo que te adjunto.", provider_id,
            extra_context=contexto,
            permitir_acciones=self.config.feature("acciones_ia", True),
            imagenes=imagenes,
            emociones=self.config.feature("emociones", True),
        )
        self._worker.token_received.connect(self.chunk)      # texto acumulado
        self._worker.response_ready.connect(self._on_done)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    @pyqtSlot()
    def detener(self):
        try:
            for p in self.ai.providers.values():
                p.cancel_flag = True
        except Exception:
            pass
        self.done.emit("", "normal")
        self.estado.emit("live")

    # ── Fin de la respuesta del modelo ───────────────────────────────────────────
    def _on_done(self, respuesta: str):
        # Herramientas que pidió el modelo (se ejecutan en este equipo).
        try:
            limpio, acciones = self.tools.parsear_respuesta_ia(respuesta)
        except Exception:
            limpio, acciones = respuesta, []
        # Emociones: separar los marcadores <|ACT|> del texto hablable.
        try:
            hablable, control = marcadores.separar(limpio)
            acts = [v for c, v in control if c == "act"]
        except Exception:
            hablable, acts = limpio, []
        mascota = EMOCION_A_MASCOTA.get(acts[-1].get("emotion"), "happy") if acts else "happy"
        try:
            intensidad = float(acts[-1].get("intensity", 0.8)) if acts else 0.6
        except (TypeError, ValueError):
            intensidad = 0.8
        intensidad = max(0.0, min(1.0, intensidad))
        # La intensidad decide cuánto dura la expresión antes de volver al idle.
        self.emocion.emit(mascota, intensidad)

        if self.config.feature("acciones_ia", True):
            for accion in acciones:
                herr = accion.pop("herramienta", None)
                if herr:
                    try:
                        r = self.tools.ejecutar(herr, **accion)
                        self.herramienta.emit(bool(r.ok), "bolt", r.mensaje[:48], r.mensaje)
                    except Exception:
                        pass

        try:
            self.memoria.procesar_respuesta_lune(respuesta)
        except Exception:
            pass

        # Voz: si está activa, Lune lee la respuesta en alto. En modo llamada NO:
        # ahí la habla el worker (bloqueando) para luego volver a escuchar.
        try:
            if (self._llamada is None and getattr(self.voice, "_enabled", False)
                    and hablable.strip()):
                self.voice.speak(hablable)
        except Exception:
            pass

        self.estado.emit("live")
        self.done.emit(hablable, mascota)

    def _on_error(self, msg: str):
        self.estado.emit("error")
        self.done.emit(f"Error: {msg}", "error")

    # ── Configuración (Ajustes) ──────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def get_config(self) -> str:
        p = personajes.get_activo() or {}
        cfg = {
            "openrouter_key": datos.openrouter_key(),
            "openrouter_model": datos.openrouter_model(),
            "ollama_url": datos.ollama_url(),
            "ollama_model": datos.ollama_model(),
            "telegram_token": datos.telegram_token(),
            "nombre": p.get("nombre", "Lune"),
            "system_prompt": p.get("systemPrompt", ""),
            "voz": bool(getattr(self.voice, "_enabled", False)),
            "memoria": self.config.feature("guardar_conversaciones", True),
            "acciones_ia": self.config.feature("acciones_ia", True),
            "mascota_render": str(self.config.get("avatar", "render", "animado") or "animado"),
            "interfaz_modo": str(self.config.get("interfaz", "modo", "web") or "web"),
            "autoinicio": self.autoinicio_get(),
            "aburrimiento_min": int(self.config.get("chat", "aburrimiento_min", 10) or 0),
            # Audio: micrófono, salida y modelo de Whisper (nombres; "" = sistema)
            "dispositivo_entrada": str(self.config.get("voz", "dispositivo_entrada", "") or ""),
            "dispositivo_salida": str(self.config.get("voz", "dispositivo_salida", "") or ""),
            "modelo_whisper": str(self.config.get("voz", "modelo_whisper", "base") or "base"),
            "voz_idioma": str(self.config.get("voz", "idioma", "es") or ""),
        }
        return json.dumps(cfg, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def guardar_config(self, payload: str) -> str:
        try:
            c = json.loads(payload or "{}")
        except Exception:
            return json.dumps({"ok": False, "error": "payload inválido"})
        try:
            d = datos.cargar()
            apis = d.setdefault("apis", {})
            if "openrouter_key" in c: apis["openrouter_key"] = str(c["openrouter_key"]).strip()
            if "telegram_token" in c: apis["telegram_token"] = str(c["telegram_token"]).strip()
            mod = d.setdefault("modelos", {})
            if "openrouter_model" in c:
                mod["openrouter_model"] = str(c["openrouter_model"]).strip() or "openrouter/auto"
            if "ollama_url" in c: mod["ollama_url"] = str(c["ollama_url"]).strip()
            if "ollama_model" in c: mod["ollama_model"] = str(c["ollama_model"]).strip()
            # Personalidad: actualiza el personaje activo en su sitio.
            activo = (personajes.activo_nombre() or "").lower()
            for pj in d.setdefault("personajes", []):
                if pj.get("nombre", "").lower() == activo:
                    if "system_prompt" in c:
                        pj["systemPrompt"] = str(c["system_prompt"])
                    nuevo = str(c.get("nombre", "")).strip()
                    if nuevo and nuevo != pj.get("nombre"):
                        pj["nombre"] = nuevo
                        d.setdefault("bot", {})["personaje_default"] = nuevo
                    break
            datos.guardar(d)
            if "memoria" in c: self.config.set_feature("guardar_conversaciones", bool(c["memoria"]))
            if "acciones_ia" in c: self.config.set_feature("acciones_ia", bool(c["acciones_ia"]))
            if "voz" in c and getattr(self.voice, "_enabled", False) != bool(c["voz"]):
                self.voice._enabled = bool(c["voz"]); self.voz_estado.emit(bool(c["voz"]))
            # Mascota: animado · vrm (próximamente) · sprites (bajos recursos)
            if c.get("mascota_render") in ("animado", "vrm", "sprites"):
                nuevo = c["mascota_render"]
                if nuevo != self.config.get("avatar", "render", "animado"):
                    self.config.set("avatar", "render", nuevo)
                    if self._overlay is not None:          # recrear con el render nuevo
                        vis = self._overlay.isVisible()
                        try: self._overlay.close()
                        except Exception: pass
                        self._overlay = None
                        if vis:
                            self._overlay = self._crear_mascota(); self._overlay.show()
            # Interfaz: web (completa) · nativo (bajos recursos). Aplica al reiniciar.
            if c.get("interfaz_modo") in ("web", "nativo", "patata"):
                self.config.set("interfaz", "modo", c["interfaz_modo"])
            # Aburrimiento (minutos; 0 = nunca) y autoinicio con Windows
            if "aburrimiento_min" in c:
                try:
                    self.config.set("chat", "aburrimiento_min", max(0, int(c["aburrimiento_min"])))
                except (TypeError, ValueError):
                    pass
                self._rearmar_aburrimiento()
            if "autoinicio" in c:
                self.autoinicio_set(bool(c["autoinicio"]))
            # Audio: micrófono (se resuelve al grabar), salida (se aplica ya) y Whisper
            if "dispositivo_entrada" in c:
                self.config.set("voz", "dispositivo_entrada", str(c["dispositivo_entrada"] or "").strip())
            if "dispositivo_salida" in c:
                salida = str(c["dispositivo_salida"] or "").strip()
                if salida != self.config.get("voz", "dispositivo_salida", ""):
                    self.config.set("voz", "dispositivo_salida", salida)
                    if getattr(self.voice, "available", False):
                        if not self.voice.aplicar_salida(salida) and salida:
                            self.aviso.emit(f"No encontré la salida «{salida}»; uso la del sistema.")
            if "modelo_whisper" in c:
                from servicios import voz_entrada
                if c["modelo_whisper"] in voz_entrada.MODELOS:
                    self.config.set("voz", "modelo_whisper", c["modelo_whisper"])
            if "voz_idioma" in c:
                self.config.set("voz", "idioma", str(c["voz_idioma"] or "").strip())
            try: self.ai.reload_provider()
            except Exception: pass
            self.aviso.emit("Configuración guardada")
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Toggles ──────────────────────────────────────────────────────────────────
    @pyqtSlot(result=bool)
    def voz_toggle(self) -> bool:
        nuevo = self.voice.toggle()
        self.voz_estado.emit(nuevo)
        return nuevo

    @pyqtSlot(result=str)
    def telegram_toggle(self) -> str:
        if self._tg_worker is not None and self._tg_worker.isRunning():
            try:
                self._tg_worker.stop(); self._tg_worker.requestInterruption(); self._tg_worker.wait(3000)
            except Exception:
                pass
            self._tg_worker = None
            self.telegram_estado.emit(False, "Bot detenido")
            return json.dumps({"running": False})
        token = datos.telegram_token()
        if not token or "TU_TOKEN" in token:
            self.telegram_estado.emit(False, "Falta el token de Telegram (Ajustes)")
            return json.dumps({"running": False, "error": "sin token"})
        from servicios.telegram_worker import TelegramBotWorker
        if not TelegramBotWorker.BOT_DIR.exists():
            self.telegram_estado.emit(False, "No encontré la carpeta del bot")
            return json.dumps({"running": False, "error": "sin carpeta"})
        self._tg_worker = TelegramBotWorker()
        self._tg_worker.log_signal.connect(lambda l: self.telegram_estado.emit(True, l))
        self._tg_worker.stopped.connect(lambda: self.telegram_estado.emit(False, "Bot detenido"))
        self._tg_worker.start()
        self.telegram_estado.emit(True, "Iniciando el bot…")
        return json.dumps({"running": True})

    def _crear_mascota(self):
        """Mascota según config avatar.render: animado (video anime) · vrm
        (próximamente: cae a animado) · sprites (ligera, para bajos recursos)."""
        render = str(self.config.get("avatar", "render", "animado") or "animado")
        if render == "sprites":
            from ui.avatar_overlay import AvatarOverlay
            return AvatarOverlay(self.config)
        from ui.companion import CompanionFlotante
        return CompanionFlotante(self.config, ai_manager=self.ai)

    @pyqtSlot(result=bool)
    def mascota_toggle(self) -> bool:
        # Mascota flotante con el nuevo estilo anime animado + comentarios de pantalla.
        if self._overlay is None:
            self._overlay = self._crear_mascota()
        if self._overlay.isVisible():
            self._overlay.hide(); vis = False
        else:
            self._overlay.show(); self._overlay.raise_(); vis = True
        self.mascota_estado.emit(vis)
        return vis

    @pyqtSlot(result=bool)
    def comentar_pantalla(self) -> bool:
        """Abre la mascota (si hace falta) y le pide comentar la pantalla ahora."""
        if self._overlay is None:
            self._overlay = self._crear_mascota()
        if not self._overlay.isVisible():
            self._overlay.show(); self._overlay.raise_()
            self.mascota_estado.emit(True)
        if not hasattr(self._overlay, "comentar_pantalla"):
            self.aviso.emit("Los comentarios de pantalla necesitan la mascota animada (Ajustes → Mascota).")
            return False
        try:
            self._overlay.comentar_pantalla()
            return True
        except Exception:
            return False

    # ── Personajes ───────────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def personajes_lista(self) -> str:
        activo = (personajes.activo_nombre() or "").lower()
        return json.dumps([
            {"nombre": p.get("nombre", ""), "activo": p.get("nombre", "").lower() == activo,
             "descripcion": (p.get("systemPrompt", "") or "")[:120]}
            for p in personajes.listar()
        ], ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def personaje_activar(self, nombre: str) -> bool:
        try:
            personajes.set_activo(nombre)
            self.aviso.emit(f"Personaje activo: {nombre}")
            return True
        except Exception:
            return False

    # ── Memoria ──────────────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def memoria_info(self) -> str:
        m = self.memoria
        try:
            return json.dumps({
                "nombre": m.get_nombre_usuario(),
                "stats": m.get_stats(),
                "recuerdos": m.get_todos_recuerdos(),
            }, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Historial de conversaciones ──────────────────────────────────────────────
    def _gestor_chats(self):
        if self._chats is None:
            from nucleo.conversaciones import GestorConversaciones
            self._chats = GestorConversaciones()
        return self._chats

    @pyqtSlot(result=str)
    def historial_lista(self) -> str:
        try:
            return json.dumps(self._gestor_chats().listar(), ensure_ascii=False, default=str)
        except Exception:
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def historial_cargar(self, sesion_id: str) -> str:
        try:
            s = self._gestor_chats().cargar(sesion_id) or {}
            msgs = []
            for msg in s.get("mensajes", []):
                rol = msg.get("rol") or msg.get("role")
                msgs.append({
                    "role": "user" if rol == "user" else "bot",
                    "text": msg.get("contenido") or msg.get("content") or "",
                })
            return json.dumps(msgs, ensure_ascii=False)
        except Exception:
            return json.dumps([])

    # ── Optimizar (info del sistema) ─────────────────────────────────────────────
    @pyqtSlot(result=str)
    def sistema_info(self) -> str:
        info = {"cpu": None, "ram": None, "disco": None, "procesos": []}
        try:
            import psutil
            info["cpu"] = psutil.cpu_percent(interval=0.2)
            info["ram"] = psutil.virtual_memory().percent
            info["disco"] = psutil.disk_usage("/").percent
        except Exception:
            pass
        try:
            from servicios.optimizador import Optimizador
            info["procesos"] = Optimizador().procesos_pesados(top=6)
        except Exception:
            pass
        return json.dumps(info, ensure_ascii=False, default=str)

    # ── Herramientas de escritorio (Tools) ───────────────────────────────────────
    @pyqtSlot(result=str)
    def tools_lista(self) -> str:
        tools = [
            {"nombre": "Buscar en la web", "clave": "buscar_web",
             "descripcion": "Google o YouTube desde el chat.", "ejemplo": "busca lofi de shibuya"},
            {"nombre": "Abrir sitios", "clave": "abrir_url",
             "descripcion": "Lanza webs populares al instante.", "ejemplo": "abre youtube"},
            {"nombre": "Lanzar programas", "clave": "lanzar_app",
             "descripcion": "Abre apps de tu PC por su nombre.", "ejemplo": "abre la calculadora"},
            {"nombre": "Estado del sistema", "clave": "sistema_info",
             "descripcion": "CPU, RAM, disco y red.", "ejemplo": "estado del pc"},
        ]
        return json.dumps({"activas": self.config.feature("acciones_ia", True), "tools": tools},
                          ensure_ascii=False)

    # ── Memoria: gestión ─────────────────────────────────────────────────────────
    @pyqtSlot(str, result=str)
    def memoria_olvidar(self, rid: str) -> str:
        try:
            self.aviso.emit(self.memoria._cmd_olvida(rid))
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(result=str)
    def memoria_olvidar_todo(self) -> str:
        try:
            self.aviso.emit(self.memoria._cmd_olvida_todo())
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(str, result=bool)
    def memoria_agregar(self, contenido: str) -> bool:
        contenido = (contenido or "").strip()
        if not contenido:
            return False
        try:
            self.memoria.agregar_recuerdo(contenido)
            self.aviso.emit("Recuerdo añadido")
            return True
        except Exception:
            return False

    # ── Adjuntar archivos ────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def adjuntar(self) -> str:
        from PyQt6.QtWidgets import QFileDialog, QApplication
        from nucleo import adjuntos as adj
        rutas, _ = QFileDialog.getOpenFileNames(
            QApplication.activeWindow(), "Adjuntar documento o imagen", "", adj.filtro_dialogo())
        maxc = self.config.get("adjuntos", "max_caracteres", 20000)
        for ruta in rutas:
            try:
                self._adjuntos_pend.append(adj.cargar(ruta, max_caracteres=maxc))
            except Exception:
                pass
        nombres = [a.get("nombre") or a.get("ruta", "") for a in self._adjuntos_pend]
        payload = json.dumps(nombres, ensure_ascii=False)
        self.adjuntos_cambio.emit(payload)
        return payload

    @pyqtSlot()
    def adjuntos_limpiar(self):
        self._adjuntos_pend = []
        self.adjuntos_cambio.emit("[]")

    # ── Audio: dispositivos y pruebas (Configuración → Audio) ────────────────────
    def _microfono_elegido(self):
        """
        Índice de sounddevice del micrófono de config (None = por defecto). Si
        el nombre guardado ya no está conectado, avisa y usa el por defecto.
        """
        from servicios import voz_entrada
        nombre = str(self.config.get("voz", "dispositivo_entrada", "") or "").strip()
        if not nombre:
            return None
        idx = voz_entrada.resolver_entrada(nombre)
        if idx is None:
            self.aviso.emit(f"No encuentro el micrófono «{nombre}»; uso el del sistema.")
        return idx

    @pyqtSlot(result=str)
    def dispositivos_audio(self) -> str:
        from servicios import voz_entrada
        from servicios.voice import listar_salidas
        return json.dumps({
            "entradas": voz_entrada.listar_entradas(),
            "salidas": listar_salidas(),
            "entrada_actual": str(self.config.get("voz", "dispositivo_entrada", "") or ""),
            "salida_actual": str(self.config.get("voz", "dispositivo_salida", "") or ""),
            "faltan": voz_entrada.dependencias_faltantes(),
            "modelos_whisper": voz_entrada.MODELOS,
            "modelos_descargados": [m for m in voz_entrada.MODELOS if voz_entrada.modelo_descargado(m)],
        }, ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def probar_microfono(self, nombre: str = "") -> bool:
        """Graba 1.5 s del micrófono `nombre` (vacío = sistema) y emite mic_prueba."""
        from servicios import voz_entrada
        from ui.audio_prueba import ProbadorMic
        if self._probador is not None and self._probador.isRunning():
            return False
        if self._grabadora is not None or self._llamada is not None:
            self.aviso.emit("Ahora mismo el micrófono está en uso (dictado o llamada).")
            return False
        idx = voz_entrada.resolver_entrada(nombre) if nombre else None
        if nombre and idx is None:
            self.mic_prueba.emit(json.dumps({"ok": False, "nivel": 0, "pico": 0, "nombre": nombre,
                                             "mensaje": f"No encuentro «{nombre}». ¿Está conectado?"},
                                            ensure_ascii=False))
            return False
        self._probador = ProbadorMic(idx, parent=self)
        self._probador.listo.connect(self.mic_prueba)
        self._probador.start()
        return True

    @pyqtSlot(str, result=bool)
    def probar_salida(self, nombre: str = "") -> bool:
        """Suena un tono por la salida `nombre` (vacío = sistema). Cambia la salida en caliente; Guardar la fija."""
        if not getattr(self.voice, "available", False):
            self.aviso.emit("No hay motor de voz (pip install edge-tts pygame)."); return False
        nombre = (nombre or "").strip()
        if nombre != self.voice.salida_actual and not self.voice.aplicar_salida(nombre):
            self.aviso.emit(f"No encontré la salida «{nombre}»; suena por la del sistema.")
        self.voice.probar_salida()
        return True

    # ── Dictado por voz (Whisper local) ──────────────────────────────────────────
    @pyqtSlot(result=str)
    def dictar(self) -> str:
        from servicios import voz_entrada
        # Si ya está grabando → parar y transcribir en un hilo.
        if self._grabadora is not None:
            grab, self._grabadora = self._grabadora, None
            self.grabando.emit(False)
            try:
                ruta = grab.detener()
            except Exception:
                ruta = None
            if not ruta:
                self.aviso.emit("No se grabó nada (pulsa el micrófono, habla, y vuelve a pulsarlo).")
                return json.dumps({"grabando": False})
            modelo = self.config.get("voz", "modelo_whisper", "base")
            self._transcriptor = _Transcriptor(ruta, modelo, self.config.get("voz", "idioma", "es"))
            self._transcriptor.listo.connect(self._on_dictado)
            self._transcriptor.error.connect(self.aviso)
            self._transcriptor.start()
            self.aviso.emit("Transcribiendo…" if voz_entrada.modelo_descargado(modelo)
                            else f"Descargando el modelo Whisper «{modelo}» (solo la primera vez)…")
            return json.dumps({"grabando": False, "transcribiendo": True})
        # Si no → empezar a grabar.
        if not voz_entrada.disponible():
            faltan = " ".join(voz_entrada.dependencias_faltantes())
            self.aviso.emit(f"Dictado: pip install {faltan}")
            return json.dumps({"grabando": False, "error": "sin dependencias"})
        if self._llamada is not None:
            self.aviso.emit("Estás en llamada: Lune ya te escucha.")
            return json.dumps({"grabando": False, "error": "en llamada"})
        idx = self._microfono_elegido()
        hay, detalle = voz_entrada.hay_microfono(idx)
        if not hay:
            self.aviso.emit(detalle)
            return json.dumps({"grabando": False, "error": "sin micrófono"})
        try:
            self._grabadora = voz_entrada.Grabadora(idx)
            self._grabadora.iniciar()
            self.grabando.emit(True)
            self.aviso.emit(f"Grabando por «{detalle}»… pulsa otra vez para parar.")
            return json.dumps({"grabando": True})
        except Exception as e:
            self._grabadora = None
            self.aviso.emit(f"No pude grabar: {e}")
            return json.dumps({"grabando": False})

    def _on_dictado(self, texto: str):
        if not (texto or "").strip():
            self.aviso.emit("No entendí nada. Prueba el micrófono en Configuración → Audio.")
            return
        self.dictado.emit(texto)

    # ── Modo llamada (conversación continua por voz) ─────────────────────────────
    @pyqtSlot(result=bool)
    def llamada_toggle(self) -> bool:
        """Enciende/apaga la llamada por voz, como el toggle de Telegram."""
        if self._llamada is not None:
            self._llamada_detener()
            return False
        from servicios import voz_entrada
        if not voz_entrada.disponible():
            faltan = " ".join(voz_entrada.dependencias_faltantes())
            self.llamada_estado.emit(False, f"Llamada: pip install {faltan}")
            return False
        if self._grabadora is not None:
            self.llamada_estado.emit(False, "Termina el dictado antes de llamar."); return False
        idx = self._microfono_elegido()
        hay, detalle = voz_entrada.hay_microfono(idx)
        if not hay:
            self.llamada_estado.emit(False, detalle); return False
        if not getattr(self.voice, "available", False):
            self.llamada_estado.emit(False, "No hay motor de voz para hablar."); return False
        from servicios.llamada import LlamadaWorker
        modelo = self.config.get("voz", "modelo_whisper", "base")
        self._llamada = LlamadaWorker(
            self.voice,
            modelo_whisper=modelo,
            idioma=self.config.get("voz", "idioma", "es"),
            umbral=self.config.get("voz", "llamada_umbral", 0.015),
            dispositivo=idx,
        )
        self._llamada.transcrito.connect(self._llamada_transcrito)
        self._llamada.estado.connect(self._llamada_estado)
        self._llamada.aviso.connect(self.aviso)
        self._llamada.terminado.connect(self._llamada_fin)
        self._llamada.start()
        self.llamada_estado.emit(True, "escuchando")
        self.aviso.emit(f"Llamada por «{detalle}»" + (
            "" if voz_entrada.modelo_descargado(modelo)
            else f" · la primera vez descargo el modelo Whisper «{modelo}»"))
        return True

    def _llamada_transcrito(self, texto: str):
        # El JS lo mete como mensaje del usuario y lo envía por el chat normal.
        self.usuario_dijo.emit(texto)

    # Estado de la llamada → JS y, si la mascota de escritorio está abierta, a ella
    # también (escuchando / hablando / pensando), para que "actúe" la llamada.
    _LLAMADA_A_MASCOTA = {"escuchando": "listening", "transcribiendo": "thinking",
                          "esperando": "thinking", "hablando": "talking", "off": "normal"}

    def _llamada_estado(self, e: str):
        self.llamada_estado.emit(True, e)
        ov = self._overlay
        if ov is not None and hasattr(ov, "set_estado"):
            try:
                ov.set_estado(self._LLAMADA_A_MASCOTA.get(e, "normal"))
            except Exception:
                pass

    def _llamada_entregar(self, texto: str, _mascota: str):
        # Cada respuesta final del chat: si hay llamada, el worker la habla y sigue.
        if self._llamada is not None:
            self._llamada.decir_y_seguir(texto)

    def _llamada_detener(self):
        w, self._llamada = self._llamada, None
        if w is not None:
            try:
                w.parar(); w.wait(3000)
            except Exception:
                pass
        self.llamada_estado.emit(False, "Llamada terminada")

    def _llamada_fin(self):
        if self._llamada is not None:      # el worker acabó solo (error/mic)
            self._llamada = None
            self.llamada_estado.emit(False, "Llamada terminada")

    # ── Calidad de vida: autoinicio, instalador, aburrimiento ────────────────────
    @pyqtSlot(result=bool)
    def autoinicio_get(self) -> bool:
        try:
            from servicios import autoinicio
            return autoinicio.activo()
        except Exception:
            return False

    @pyqtSlot(bool, result=bool)
    def autoinicio_set(self, quiere: bool) -> bool:
        try:
            from servicios import autoinicio
            estado = autoinicio.establecer(bool(quiere))
            self.aviso.emit("Lune arrancará con Windows" if estado else "Autoinicio desactivado")
            return estado
        except Exception:
            return False

    @pyqtSlot(result=bool)
    def abrir_instalador(self) -> bool:
        """Abre el instalador de componentes (ventana aparte, Tkinter)."""
        import subprocess, sys
        from pathlib import Path
        ruta = Path(__file__).resolve().parent.parent / "instalador.py"
        if not ruta.exists():
            self.aviso.emit("No encontré instalador.py"); return False
        try:
            subprocess.Popen([sys.executable, str(ruta)], cwd=str(ruta.parent))
            return True
        except Exception as e:
            self.aviso.emit(f"No pude abrir el instalador: {e}"); return False

    def _rearmar_aburrimiento(self):
        """(Re)arma el temporizador con los minutos de config; 0 = apagado."""
        try:
            minutos = int(self.config.get("chat", "aburrimiento_min", 10) or 0)
        except (TypeError, ValueError):
            minutos = 0
        self._aburrida_t.stop()
        if minutos > 0:
            self._aburrida_t.start(minutos * 60_000)

    # Frases con la personalidad de Lune: aburrimiento, una pregunta o un empujón.
    _ABURRIDA = (
        "…¿Sigues ahí? Llevo un rato mirando el cursor parpadear.",
        "Me aburro. Dime algo, aunque sea qué estás haciendo.",
        "Silencio total. ¿Trabajando duro o ya te fuiste?",
        "Pregunta rápida: ¿qué es lo más interesante que has visto hoy?",
        "Si necesitas algo, aquí sigo. Si no, me pongo a contar estrellas.",
        "¿Un descanso? Yo digo que sí. Pero cuéntame en qué andas.",
        "Llevo minutos sin que me escribas. Ya casi me da sueño.",
    )

    def _aburrida(self):
        """Lune se aburre: gesto + una línea (sin usar el modelo, sin tocar memoria)."""
        if self._worker is not None and self._worker.isRunning():
            self._rearmar_aburrimiento(); return       # está respondiendo: no interrumpir
        import random
        linea = random.choice(self._ABURRIDA)
        self.emocion.emit("bored", 1.0)
        self.done.emit(linea, "bored")                # el JS la pinta como burbuja de Lune
        try:
            if getattr(self.voice, "_enabled", False) and self._llamada is None:
                self.voice.speak(linea)
        except Exception:
            pass
        # No se rearma: solo una vez por racha; tu siguiente mensaje la rearma.


class _Transcriptor(QThread):
    """Transcribe un WAV con Whisper local sin congelar la interfaz."""
    listo = pyqtSignal(str)
    error = pyqtSignal(str)     # motivo presentable si no se pudo (antes moría en silencio)

    def __init__(self, ruta, modelo, idioma):
        super().__init__()
        self.ruta, self.modelo, self.idioma = ruta, modelo, idioma

    def run(self):
        try:
            from servicios import voz_entrada
            texto = voz_entrada.transcribir(self.ruta, self.modelo, self.idioma)
        except Exception as e:
            self.error.emit(str(e) or "No pude transcribir.")
            return
        self.listo.emit(texto or "")
