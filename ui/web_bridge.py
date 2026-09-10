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
from nucleo import datos, personajes, vrm
from servicios.ai_manager import AIManager
from servicios.ai_worker import AIWorker
from servicios.tools import ToolManager
from servicios.voice import VoiceEngine
from lune_core import marcadores, expresiones

# Emoción canónica del modelo → estado de mascota del set anime (assets/mascot/anime).
EMOCION_A_MASCOTA = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
    # v10.1
    "laughing": "laughing", "bored": "bored",
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
    _hablando = pyqtSignal(bool)            # interna: la voz suena (desde el hilo de audio)
    _acto_voz = pyqtSignal(str)             # interna: empieza a sonar un tramo con esta expresión

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
        # La voz avisa cuándo suena (hilo de audio) → señal → boca del avatar VRM.
        self._hablando.connect(self._on_hablando)
        try:
            self.voice.al_hablar = self._hablando.emit
        except Exception:
            pass
        # Expresiones: hasta tres por respuesta; con voz cambian al ritmo de la voz,
        # sin voz según llega el texto (o al ritmo de lectura). La última se queda.
        self._acto_voz.connect(self._expresar)
        self._seguidor = None               # SeguidorActs del stream en curso
        self._stream_iniciado = False
        self._expresado_en_stream = False
        self._timers_plan = []              # expresiones programadas (sin voz, sin stream)
        self._gen = 0                       # generación del envío: ignora señales de workers viejos
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
        self._cancelar_plan()             # expresiones pendientes de la respuesta anterior…
        try:
            self.voice.cancelar()         # …y su voz, si aún sonaba
        except Exception:
            pass

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
        self._mascota_estado("thinking")
        self._seguidor = expresiones.SeguidorActs()
        self._stream_iniciado = False
        self._expresado_en_stream = False
        # Un Detener anterior deja cancel_flag levantado: si no se baja, el proveedor
        # corta en el primer token y todo sale "Sin respuesta".
        try:
            self.ai.providers[provider_id].cancel_flag = False
        except Exception:
            pass
        self._gen += 1
        gen = self._gen
        self._worker = AIWorker(
            self.ai, texto or "Analiza lo que te adjunto.", provider_id,
            extra_context=contexto,
            permitir_acciones=self.config.feature("acciones_ia", True),
            imagenes=imagenes,
            emociones=self.config.feature("emociones", True),
        )
        # Las señales llevan la generación: tras Detener (o un envío nuevo) las del
        # worker viejo se ignoran, en vez de pintar su respuesta parcial.
        self._worker.token_received.connect(lambda t, g=gen: self._on_chunk(t, g))
        self._worker.response_ready.connect(lambda r, g=gen: self._on_done(r, g))
        self._worker.error_occurred.connect(lambda m, g=gen: self._on_error(m, g))
        self._worker.start()

    @pyqtSlot()
    def detener(self):
        try:
            for p in self.ai.providers.values():
                p.cancel_flag = True
        except Exception:
            pass
        self._gen += 1                      # lo que emita el worker en curso ya no cuenta
        self._cancelar_plan()
        try:
            self.voice.cancelar()
        except Exception:
            pass
        self.done.emit("", "normal")
        self._mascota_estado("normal")
        self.estado.emit("live")

    # ── Expresiones ──────────────────────────────────────────────────────────────
    def _voz_lee_al_final(self) -> bool:
        """¿La voz va a leer la respuesta cuando termine? (entonces la cara sigue a la voz)."""
        return bool(self._llamada is None and getattr(self.voice, "_enabled", False)
                    and getattr(self.voice, "available", False))

    def _expresar(self, estado: str):
        """Cambia la cara de la barra lateral y de la mascota de escritorio (se queda)."""
        if not estado:
            return
        self.acto.emit(estado)
        self._mascota_estado(estado)

    def _on_chunk(self, acumulado: str, gen=None):
        if gen is not None and gen != self._gen:
            return
        if not self._stream_iniciado:
            self._stream_iniciado = True
            self._expresar("typing")
        if self._seguidor is not None and not self._voz_lee_al_final():
            for act in self._seguidor.nuevos(acumulado):
                self._expresado_en_stream = True
                self._expresar(EMOCION_A_MASCOTA.get(act.get("emotion"), "happy"))
        self.chunk.emit(acumulado)

    def _al_segmento_voz(self, _i: int, etiqueta: str, gen=None):
        # Desde el hilo de audio: la señal lo lleva al hilo de Qt. Los avisos de una
        # respuesta anterior (generación vieja) se ignoran.
        if etiqueta and (gen is None or gen == self._gen):
            self._acto_voz.emit(etiqueta)

    def _al_terminar_voz(self, estado_final: str, gen=None):
        # Al acabar de hablar, la cara se queda con la última expresión (aunque su
        # tramo no tuviera texto que leer, o la respuesta no trajera marcadores).
        if estado_final and (gen is None or gen == self._gen):
            self._acto_voz.emit(estado_final)

    def _cancelar_plan(self):
        for t in self._timers_plan:
            try: t.stop(); t.deleteLater()
            except Exception: pass
        self._timers_plan = []

    def _programar_plan(self, plan):
        """Sin voz y sin streaming: las expresiones al ritmo de lectura (la 1ª ya se puso)."""
        self._cancelar_plan()
        for t_s, emocion, _ in expresiones.horario(plan)[1:]:
            tm = QTimer(self); tm.setSingleShot(True)
            tm.timeout.connect(lambda e=emocion, t=tm: (self._expresar(EMOCION_A_MASCOTA.get(e, "happy")), t.deleteLater()))
            tm.start(int(t_s * 1000))
            self._timers_plan.append(tm)

    # ── Fin de la respuesta del modelo ───────────────────────────────────────────
    def _on_done(self, respuesta: str, gen=None):
        if gen is not None and gen != self._gen:
            return                                   # respuesta (parcial) de un envío ya detenido
        # Herramientas que pidió el modelo (se ejecutan en este equipo).
        try:
            limpio, acciones = self.tools.parsear_respuesta_ia(respuesta)
        except Exception:
            limpio, acciones = respuesta, []
        # Emociones: el plan de expresiones de la respuesta (hasta tres tramos con
        # su texto). La última es con la que se queda.
        try:
            plan = expresiones.planificar(limpio)
        except Exception:
            plan = [expresiones.Tramo("", 1.0, limpio)]
        hablable = expresiones.hablable(plan)
        mascota = EMOCION_A_MASCOTA.get(expresiones.final(plan), "happy")
        try:
            intensidad = max(0.0, min(1.0, float(plan[-1].intensidad)))
        except (TypeError, ValueError):
            intensidad = 0.8
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

        # Voz: si está activa, Lune lee la respuesta por tramos y la cara cambia
        # cuando empieza a sonar cada uno. En modo llamada NO: ahí la habla el
        # worker (bloqueando) para luego volver a escuchar.
        con_voz = False
        con_emociones = bool(expresiones.emociones(plan))
        try:
            if (self._llamada is None and getattr(self.voice, "_enabled", False)
                    and hablable.strip()):
                # Sin marcadores, el tramo va como "talking"; al acabar, la cara final.
                segs = expresiones.segmentos_voz(plan, lambda e: EMOCION_A_MASCOTA.get(e, "happy"))
                segs = [(et or "talking", tx) for et, tx in segs]
                con_voz = bool(self.voice.speak_segmentos(
                    segs,
                    al_segmento=lambda i, e, g=gen: self._al_segmento_voz(i, e, g),
                    al_terminar=lambda g=gen, est=mascota: self._al_terminar_voz(est, g)))
        except Exception:
            con_voz = False

        self.estado.emit("live")
        if con_voz:
            self.done.emit(hablable, "")              # la cara la lleva la voz, tramo a tramo
        elif self._expresado_en_stream or self._llamada is not None or not con_emociones:
            # Ya cambió con el texto (o en llamada la lleva el worker, o no hay
            # marcadores): se queda con la última.
            self.done.emit(hablable, mascota)
            self._mascota_estado(mascota)
        else:
            # Llegó de golpe: la 1ª ya, las demás al ritmo de lectura.
            primera = EMOCION_A_MASCOTA.get(plan[0].emocion, mascota)
            self.done.emit(hablable, primera)
            self._mascota_estado(primera)
            self._programar_plan(plan)

    def _on_error(self, msg: str, gen=None):
        if gen is not None and gen != self._gen:
            return
        self.estado.emit("error")
        self.done.emit(f"Error: {msg}", "error")
        self._mascota_estado("nervous", 6000)

    # ── Mascota de escritorio: recibe lo mismo que la mascota de la barra lateral ──
    def _mascota_estado(self, estado: str, ms: int = 0):
        ov = self._overlay
        if ov is None or getattr(ov, "cerrado", False) or not ov.isVisible():
            return
        try:
            ov.set_estado(estado, ms)
        except Exception:
            pass

    def _on_hablando(self, activo: bool):
        ov = self._overlay
        if ov is None or getattr(ov, "cerrado", False) or not ov.isVisible():
            return
        try:
            if hasattr(ov, "set_hablando"):
                ov.set_hablando(bool(activo))
        except Exception:
            pass

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
            # Mascota 3D (VRM): qué hay instalado y cómo se muestra
            "vrm_webengine": vrm.webengine_disponible(),
            "vrm_modelos": vrm.listar_modelos(),
            "vrm_archivo": str(self.config.get("avatar", "vrm_archivo", "") or ""),
            "vrm_tamano": str(self.config.get("avatar", "vrm_tamano", "normal") or "normal"),
            "vrm_encuadre": str(self.config.get("avatar", "vrm_encuadre", "retrato") or "retrato"),
            "vrm_fantasma_auto": bool(self.config.get("avatar", "vrm_fantasma_auto", True)),
            "dormir_min": int(self.config.get("avatar", "dormir_min", 10) or 0),
            "mascota_fuera": self.mascota_visible(),
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
            # Mascota: animado · vrm (avatar 3D) · sprites (bajos recursos), y las
            # opciones del VRM. Si cambia algo que la página no aplica en caliente,
            # se recrea la mascota con lo nuevo (solo si estaba abierta).
            recrear = False
            ov = self._overlay if (self._overlay is not None and not getattr(self._overlay, "cerrado", False)) else None
            if c.get("mascota_render") in ("animado", "vrm", "sprites"):
                nuevo = c["mascota_render"]
                if nuevo != self.config.get("avatar", "render", "animado"):
                    self.config.set("avatar", "render", nuevo); recrear = True
            if "vrm_archivo" in c:
                v = str(c["vrm_archivo"] or "").strip()
                if v and vrm.resolver(v) is None:
                    self.aviso.emit(f"No encuentro el modelo «{v}»; sigo con el anterior.")
                elif v != str(self.config.get("avatar", "vrm_archivo", "") or ""):
                    self.config.set("avatar", "vrm_archivo", v)
                    # el modelo por defecto solo cuenta si el personaje no trae el suyo
                    if ov is not None and hasattr(ov, "recargar_modelo"):
                        ov.recargar_modelo()
            # Tamaño y encuadre se aplican en caliente (la ventana ya sabe hacerlo).
            for clave, valido, aplicar in (("vrm_tamano", ("pequeno", "normal", "grande"), "aplicar_tamano"),
                                           ("vrm_encuadre", ("retrato", "cuerpo"), "aplicar_encuadre")):
                if clave in c:
                    v = str(c[clave] or "").strip()
                    if v not in valido or v == str(self.config.get("avatar", clave, "") or ""):
                        continue
                    if ov is not None and getattr(ov, "render", "") == "vrm" and hasattr(ov, aplicar):
                        getattr(ov, aplicar)(v)           # también guarda la clave
                    else:
                        self.config.set("avatar", clave, v)
            if "vrm_fantasma_auto" in c:
                self.config.set("avatar", "vrm_fantasma_auto", bool(c["vrm_fantasma_auto"]))
            if "dormir_min" in c:
                try:
                    self.config.set("avatar", "dormir_min", max(0, int(c["dormir_min"])))
                except (TypeError, ValueError):
                    pass
            if ov is not None and hasattr(ov, "aplicar_opciones"):
                try: ov.aplicar_opciones()
                except Exception: pass
            if recrear and self._overlay is not None:
                self._mascota_recrear()
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
        (avatar 3D; si no hay .vrm cae a animado) · sprites (ligera, bajos recursos).
        Su señal `visibilidad` es la que le dice a la UI que Lune está fuera (y
        entonces la barra lateral deja de dibujarla, para no verla doble)."""
        render = str(self.config.get("avatar", "render", "animado") or "animado")
        if render == "sprites":
            from ui.avatar_overlay import AvatarOverlay
            ov = AvatarOverlay(self.config)
        else:
            from ui.companion import CompanionFlotante
            ov = CompanionFlotante(self.config, ai_manager=self.ai, render=render)
        try:
            ov.visibilidad.connect(self.mascota_estado)
        except Exception:
            pass
        try:
            ov.recrear.connect(self._mascota_recrear)     # arrancó en vídeo y ya hay .vrm
        except Exception:
            pass
        return ov

    def _mascota_recrear(self):
        """Cierra la mascota y la vuelve a crear con la config actual (si estaba a la vista)."""
        ov = self._overlay
        vis = ov is not None and not getattr(ov, "cerrado", False) and ov.isVisible()
        if ov is not None:
            try: ov.close()
            except Exception: pass
        self._overlay = None
        if vis:
            self._overlay = self._crear_mascota(); self._overlay.show()
            self.mascota_estado.emit(True)

    def _mascota(self):
        """La mascota viva, creándola si no existe o si el usuario la cerró."""
        if self._overlay is None or getattr(self._overlay, "cerrado", False):
            self._overlay = self._crear_mascota()
        return self._overlay

    @pyqtSlot(result=bool)
    def mascota_visible(self) -> bool:
        ov = self._overlay
        return bool(ov is not None and not getattr(ov, "cerrado", False) and ov.isVisible())

    @pyqtSlot(result=bool)
    def mascota_toggle(self) -> bool:
        # Mascota flotante (video anime o avatar VRM) + comentarios de pantalla.
        ov = self._mascota()
        if ov.isVisible():
            ov.hide(); vis = False
        else:
            ov.show(); ov.raise_(); vis = True
        self.mascota_estado.emit(vis)
        return vis

    @pyqtSlot(result=bool)
    def comentar_pantalla(self) -> bool:
        """Abre la mascota (si hace falta) y le pide comentar la pantalla ahora."""
        self._mascota()
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
             "descripcion": (p.get("systemPrompt", "") or "")[:120],
             "vrm": str(p.get("vrm", "") or "")}
            for p in personajes.listar()
        ], ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def personaje_activar(self, nombre: str) -> bool:
        try:
            personajes.set_activo(nombre)
            datos.invalidar()
            self.aviso.emit(f"Personaje activo: {nombre}")
            self._mascota_recargar_modelo()
            return True
        except Exception:
            return False

    def _mascota_recargar_modelo(self):
        """Si la mascota 3D está abierta y el personaje activo tiene otro .vrm, cámbialo."""
        ov = self._overlay
        if ov is not None and not getattr(ov, "cerrado", False) and hasattr(ov, "recargar_modelo"):
            try:
                ov.recargar_modelo()
            except Exception:
                pass

    # ── Modelos 3D (VRM) ─────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def vrm_modelos(self) -> str:
        return json.dumps({"webengine": vrm.webengine_disponible(), "modelos": vrm.listar_modelos(),
                           "carpeta": str(vrm.CARPETA)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def vrm_importar(self) -> str:
        """Elige un .vrm con el diálogo del sistema y lo copia a modelo_vrm/."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            ruta, _ = QFileDialog.getOpenFileName(None, "Elegir un modelo VRM", "",
                                                  "Modelos VRM (*.vrm);;Todos (*.*)")
            if not ruta:
                return json.dumps({"ok": False, "cancelado": True})
            nombre = vrm.importar_modelo(ruta)
            self.aviso.emit(f"Modelo «{nombre}» listo en modelo_vrm/")
            self._mascota_recargar_modelo()
            return json.dumps({"ok": True, "archivo": nombre, "modelos": vrm.listar_modelos()}, ensure_ascii=False)
        except Exception as e:
            self.aviso.emit(f"No pude importar el modelo: {e}")
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, str, result=str)
    def personaje_vrm(self, nombre: str, archivo: str) -> str:
        """Asigna (o quita, con archivo vacío) el modelo 3D de un personaje."""
        try:
            vrm.asignar_a_personaje(nombre, archivo)
        except Exception as e:
            self.aviso.emit(f"No pude asignar el modelo: {e}")
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if (personajes.activo_nombre() or "").lower() == (nombre or "").lower():
            self._mascota_recargar_modelo()
        return json.dumps({"ok": True})

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
        self._mascota_estado("bored")                 # y se queda aburrida hasta que le escribas
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
