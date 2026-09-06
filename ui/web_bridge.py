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

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

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
    "happy": "happy", "sad": "nervous", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "reading", "neutral": "normal",
}


def _provider_id(web_provider: str) -> str:
    """'local' → ollama · 'cloud' → openrouter (lo que usa la UI web)."""
    return "ollama" if web_provider == "local" else "openrouter"


class LuneBridge(QObject):
    # ── Señales hacia el JS ──────────────────────────────────────────────────────
    chunk = pyqtSignal(str)                 # texto ACUMULADO del stream
    done = pyqtSignal(str, str)             # (texto_final_limpio, estado_mascota)
    acto = pyqtSignal(str)                  # estado de mascota durante la respuesta
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

    # ── API para el JS ───────────────────────────────────────────────────────────
    @pyqtSlot(str, str)
    def enviar(self, texto: str, provider: str = "local"):
        texto = (texto or "").strip()
        pend = list(self._adjuntos_pend)
        if (not texto and not pend) or (self._worker and self._worker.isRunning()):
            return
        provider_id = _provider_id(provider)

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

        # Voz: si está activa, Lune lee la respuesta en alto.
        try:
            if getattr(self.voice, "_enabled", False) and hablable.strip():
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

    @pyqtSlot(result=bool)
    def mascota_toggle(self) -> bool:
        from ui.avatar_overlay import AvatarOverlay
        if self._overlay is None:
            self._overlay = AvatarOverlay(self.config)
        if self._overlay.isVisible():
            self._overlay.hide(); vis = False
        else:
            self._overlay.show(); self._overlay.raise_(); vis = True
        self.mascota_estado.emit(vis)
        return vis

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
                self.aviso.emit("No se grabó nada.")
                return json.dumps({"grabando": False})
            self._transcriptor = _Transcriptor(
                ruta, self.config.get("voz", "modelo_whisper", "base"),
                self.config.get("voz", "idioma", "es"))
            self._transcriptor.listo.connect(self._on_dictado)
            self._transcriptor.start()
            self.aviso.emit("Transcribiendo…")
            return json.dumps({"grabando": False, "transcribiendo": True})
        # Si no → empezar a grabar.
        if not voz_entrada.disponible():
            faltan = " ".join(voz_entrada.dependencias_faltantes())
            self.aviso.emit(f"Dictado: pip install {faltan}")
            return json.dumps({"grabando": False, "error": "sin dependencias"})
        hay, detalle = voz_entrada.hay_microfono()
        if not hay:
            self.aviso.emit(detalle)
            return json.dumps({"grabando": False, "error": "sin micrófono"})
        try:
            self._grabadora = voz_entrada.Grabadora()
            self._grabadora.iniciar()
            self.grabando.emit(True)
            return json.dumps({"grabando": True})
        except Exception as e:
            self._grabadora = None
            self.aviso.emit(f"No pude grabar: {e}")
            return json.dumps({"grabando": False})

    def _on_dictado(self, texto: str):
        self.dictado.emit(texto or "")


class _Transcriptor(QThread):
    """Transcribe un WAV con Whisper local sin congelar la interfaz."""
    listo = pyqtSignal(str)

    def __init__(self, ruta, modelo, idioma):
        super().__init__()
        self.ruta, self.modelo, self.idioma = ruta, modelo, idioma

    def run(self):
        try:
            from servicios import voz_entrada
            texto = voz_entrada.transcribir(self.ruta, self.modelo, self.idioma)
        except Exception:
            texto = ""
        self.listo.emit(texto or "")
