"""
ai_worker.py — Hilo que consulta a la IA (Ollama, OpenRouter o una API compatible
con OpenAI) sin congelar la UI. Inyecta el system prompt, el contexto de memoria
y las reglas de herramientas.

Las reglas de herramientas salen de lune_core/reglas_prompt.py: un único
formato (`<|CALL ["herramienta", {args}]|>`) y solo las herramientas que el
Ejecutor de este modo puede hacer de verdad (con handler y válidas en `modo`).

Origen del turno (crítica d, inyección hacia herramientas):
  · 'usuario'       lo escribió la persona en el chat.
  · 'no_confiable'  el prompt lleva texto de terceros (captura o título de
                    ventana, chat o log de Minecraft, Telegram, notas, adjuntos…).
  · 'remoto'        una orden desde Telegram (/pc) que llegó por el bot que
                    lanzó Lune. Se ofrecen las herramientas del modo como con
                    'usuario', pero el Ejecutor pide aprobación en el PC para
                    TODAS; en el historial cuenta como no confiable (taint).
En un turno no confiable solo se ofrecen las herramientas de LECTURA, y quien
procese la respuesta tiene que pasar el mismo `worker.origen` al Ejecutor,
que es quien de verdad lo hace cumplir.

CACHÉ DE PREFIJO (prueba real con Ollama, 2026-09: 37–48 s hasta el primer token
porque el prompt cambiaba en cada turno). El system prompt va por capas ESTABLES
(lune_core.prompt.construir_system_prompt): persona → regla de fecha → emociones
→ herramientas → anti-inyección → memoria AL FINAL (sin contadores que cambien en
cada mensaje). Lo que cambia en cada turno va en el mensaje:
  · la fecha y hora, como prefijo «[AAAA-MM-DD HH:MM] » (se guarda con él);
  · los datos de terceros de ESTE mensaje (adjuntos, notas), como `anexo` al final
    y sin guardarse, con su propia etiqueta (nunca bajo la de la memoria).
Si el chat no entiende `prefijo`/`anexo` (un adaptador viejo, el host remoto), el
mensaje va como antes y los datos externos, al final del system prompt.

COTEJO: si `ctx` es un dict, run() le deja el mensaje (`mensaje_usuario`) y la
hora del envío (`momento`): el Ejecutor coteja con ellos las duraciones y horas
que pide el modelo (lune_core.catalogo_herramientas.cotejar).
"""
import asyncio
import inspect
import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from ui.theme import COLORS, PROVIDER_META
from nucleo.utils import log_error
from lune_core.prompt import (ETIQUETA_EXTERNO, construir_system_prompt, prefijo_hora,
                              separar_contexto)
from lune_core.reglas_prompt import reglas_herramientas

ORIGEN_USUARIO = "usuario"
ORIGEN_NO_CONFIABLE = "no_confiable"
ORIGEN_REMOTO = "remoto"          # = lune_core.catalogo_herramientas.ORIGEN_REMOTO

# Proveedor 'compat' (LM Studio, Groq, OpenAI, Together, Mistral…): no está en
# ui/theme.PROVIDER_META, así que se describe aquí con el mismo formato.
META_COMPAT = {
    "label": "LUNE AI · API",
    "icon": "◈",
    "svg": "bolt",
    "color": COLORS["yellow"],
    "dark": COLORS["yellow_dark"],
    "desc": "API compatible con OpenAI",
}


def meta_proveedor(provider_id: str) -> dict:
    """Metadatos de pintado y system prompt de un proveedor (también de 'compat')."""
    meta = PROVIDER_META.get(provider_id)
    if meta is not None:
        return meta
    base = PROVIDER_META.get("ollama") or next(iter(PROVIDER_META.values()))
    if provider_id == "compat":
        return {**base, **META_COMPAT}
    return base


def normalizar_origen(origen) -> str:
    """'usuario' o 'remoto' solo si lo dice explícitamente; cualquier otra cosa es no confiable."""
    o = str(origen or "").strip().lower()
    return o if o in (ORIGEN_USUARIO, ORIGEN_REMOTO) else ORIGEN_NO_CONFIABLE


def kwargs_chat(chat, **opciones) -> dict:
    """
    Las `opciones` (origen, efimero…) que acepta `chat` (AIManager.chat o algo con
    su forma, como lune_core.chat_remota.ChatRemoto o un falso de los tests). Lo
    que no acepta se omite: un adaptador viejo sigue funcionando sin romperse.
    """
    try:
        params = inspect.signature(chat).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(opciones)
    return {k: v for k, v in opciones.items() if k in params}


def reglas_para(ejecutor=None, modo=None, origen: str = ORIGEN_USUARIO, ctx=None,
                disponibles=None, *, con_titulo: bool = True, con_emociones: bool = True) -> str:
    """
    Bloque de herramientas para el system prompt. Sin Ejecutor ni `disponibles`
    no se ofrece ninguna (el modelo no puede pedir lo que nadie va a ejecutar).
    """
    if ejecutor is None and disponibles is None:
        return ""
    registro = getattr(ejecutor, "registro", None)
    if disponibles is None:
        disponibles = set(getattr(ejecutor, "handlers", {}) or {})
    try:
        o = normalizar_origen(origen)
        if o == ORIGEN_REMOTO:
            # Todas las del modo, marcadas «(pide permiso)»: el Ejecutor las pregunta todas.
            base = dict(ctx) if isinstance(ctx, dict) else {}
            ctx = {**base, "origen": ORIGEN_REMOTO}
        return reglas_herramientas(registro, modo, set(disponibles),
                                   solo_lectura=o == ORIGEN_NO_CONFIABLE, ctx=ctx,
                                   con_titulo=con_titulo, con_emociones=con_emociones)
    except Exception as e:
        log_error(f"AIWorker: no pude armar las reglas de herramientas: {e}")
        return ""


class AIWorker(QThread):
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    # Refresco máximo del texto en pantalla. El modelo puede escupir cientos de
    # tokens por segundo (sobre todo en local) y repintar el QLabel en cada uno
    # hacía que la UI se arrastrara en respuestas largas.
    INTERVALO_UI = 0.06   # segundos

    def __init__(self, ai_manager, message: str, provider_id: str,
                 extra_context: str = "", permitir_acciones: bool = True,
                 imagenes=None, emociones: bool = True, *,
                 origen: str = ORIGEN_USUARIO, ejecutor=None, modo=None, ctx=None,
                 disponibles=None, efimero: bool = False, contexto_externo: str = "",
                 con_hora: bool = True):
        """
        origen       'usuario' | 'no_confiable' | 'remoto' (ver la cabecera). Se expone en
                     `self.origen` para pasárselo al Ejecutor con la respuesta.
                     Un turno no confiable queda MARCADO en el historial (prompt
                     y respuesta): mientras siga en la ventana, las acciones que
                     no sean de lectura piden permiso (AIManager.contexto_contaminado).
        efimero      True: el intercambio (prompt y respuesta) NO se guarda en el
                     historial de la conversación (p. ej. el comentario de
                     pantalla de la mascota). El modelo sí ve la conversación.
        ejecutor     lune_core.acciones.Ejecutor de este modo: de él salen el
                     registro y las herramientas con handler.
        modo         'normal' | 'patata' | 'br' | 'mascota' | 'vrm'.
        ctx          {proveedor, url, …}: marca «(pide permiso)» según la
                     aprobación dinámica (p. ej. la captura con la nube).
        disponibles  nombres con handler, si no hay Ejecutor a mano.
        extra_context     la memoria del usuario (y, de llamadores viejos, también
                          adjuntos y notas: se separan con separar_contexto).
        contexto_externo  datos de terceros de ESTE mensaje (adjuntos, notas): van
                          al final del mensaje, no bajo la memoria.
        con_hora     antepone «[AAAA-MM-DD HH:MM] » al mensaje (si el chat lo admite).
        """
        super().__init__()
        self.ai_manager        = ai_manager
        self.message           = message
        self.provider_id       = provider_id
        self.extra_context     = extra_context
        self.permitir_acciones = permitir_acciones
        self.emociones         = emociones
        self.imagenes          = imagenes or []
        self.origen            = normalizar_origen(origen)
        self.ejecutor          = ejecutor
        self.modo              = modo
        self.ctx               = ctx
        self.disponibles       = disponibles
        self.efimero           = bool(efimero)
        self.contexto_externo  = contexto_externo or ""
        self.con_hora          = bool(con_hora)
        self._buffer           = ""
        self._ultimo_emit      = 0.0

    def _acepta(self, opcion: str) -> bool:
        """¿El chat de este turno entiende `opcion` (prefijo, anexo…)?"""
        return opcion in kwargs_chat(self.ai_manager.chat, **{opcion: "x"})

    def partes_contexto(self):
        """(memoria, datos externos de este mensaje)."""
        memoria, externo = separar_contexto(self.extra_context)
        propio = str(self.contexto_externo or "").strip()
        return memoria, "\n\n".join(x for x in (externo, propio) if x)

    def anexo(self) -> str:
        """Los datos externos de este mensaje, con su etiqueta ("" si no hay)."""
        _, externo = self.partes_contexto()
        return f"{ETIQUETA_EXTERNO}\n{externo}" if externo else ""

    def construir_system_prompt(self, externo_en_mensaje=None) -> str:
        """
        Persona → fecha → emociones → herramientas → anti-inyección → memoria (sin
        llamar al modelo). Estable de un turno a otro. `externo_en_mensaje`: si los
        datos externos van en el mensaje (None: si el chat admite `anexo`); si no,
        van aquí, con su etiqueta, antes de la memoria.
        """
        sys_val = meta_proveedor(self.provider_id)["system"]
        persona = sys_val() if callable(sys_val) else sys_val
        memoria, externo = self.partes_contexto()
        if externo_en_mensaje is None:
            externo_en_mensaje = self._acepta("anexo")

        # Si el usuario desactivó las acciones automáticas, ni le contamos
        # al modelo que existen: así no las sugiere ni las intenta.
        reglas = ""
        if self.permitir_acciones:
            reglas = reglas_para(self.ejecutor, self.modo, self.origen, self.ctx, self.disponibles,
                                 con_titulo=False, con_emociones=self.emociones)
        extra = "" if (externo_en_mensaje or not externo) else self.anexo()
        return construir_system_prompt(
            str(persona or ""), con_emociones=self.emociones, herramientas=reglas, extra=extra,
            con_fecha=self.con_hora and self._acepta("prefijo"), memoria=memoria)

    def opciones_envio(self, momento=None) -> dict:
        """Los kwargs del chat de este turno (solo los que el chat entiende)."""
        opciones = {"origen": self.origen, "efimero": self.efimero}
        if self.con_hora:
            opciones["prefijo"] = prefijo_hora(momento)
        anexo = self.anexo()
        if anexo:
            opciones["anexo"] = anexo
        return kwargs_chat(self.ai_manager.chat, **opciones)

    def run(self):
        try:
            momento = datetime.now()
            # Para el cotejo del Ejecutor (quien procesa la respuesta usa este mismo ctx).
            if isinstance(self.ctx, dict):
                self.ctx["mensaje_usuario"] = self.message
                self.ctx["momento"] = momento
            system_prompt = self.construir_system_prompt()

            def on_token(token):
                self._buffer += token
                ahora = time.monotonic()
                if ahora - self._ultimo_emit >= self.INTERVALO_UI:
                    self._ultimo_emit = ahora
                    self.token_received.emit(self._buffer)

            # origen, efimero, prefijo y anexo solo si el chat los entiende (AIManager
            # sí; un adaptador viejo no): así el historial sabe qué turno era de terceros.
            extra = self.opciones_envio(momento)
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    self.ai_manager.chat(self.message, system_prompt,
                                         provider=self.provider_id, on_token=on_token,
                                         imagenes=self.imagenes, **extra)
                )
            finally:
                loop.close()

            self.response_ready.emit(response or "Sin respuesta")
        except Exception as e:
            texto = self._sin_claves(e)
            log_error(f"AIWorker error: {texto}"); self.error_occurred.emit(texto)

    def _sin_claves(self, error) -> str:
        """El error sin claves (un fallo de red puede llevar «Bearer <clave>»)."""
        from servicios.ai_manager import redactar_secretos
        redactar = getattr(self.ai_manager, "redactar", None)
        try:
            return str(redactar(error)) if callable(redactar) else redactar_secretos(error)
        except Exception:
            return redactar_secretos(error)
