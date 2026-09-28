"""
lune_core/servicio_chat.py — El chat de Lune, servido por el host (el "agente").

Hasta ahora cada terminal (la app, el bot, el navegador) llamaba a Ollama por su
cuenta. Con esto, el HOST corre el modelo una sola vez y sirve la conversación a
todos por el hub: reciben el mismo cerebro, la misma memoria (solo los terminales
de la persona: el bot de Telegram no, ver «Memoria» abajo) y —si el host las tiene
activadas— las mismas herramientas de escritorio (9.5).

Atiende:
    input:text {text, images?, provider?, session_id?, origen?}
      → output:chat:delta {text}     (varias veces, streaming)
      → output:chat:act   {emotion, intensity, motion?}   (por cada <|ACT|>)
      → output:chat:done  {text, usage, acts, tools}
    tool:approval:response {id, approved}   (solo del terminal al que se preguntó)

Herramientas (corte 2 de Mate-Engine): el modelo las pide con
`<|CALL ["herramienta", {args}]|>` y las procesa un Ejecutor
(lune_core/acciones.py) por terminal, con su presupuesto y su auditoría. El
formato antiguo (`ABRIR_URL:`/`TOOL:`) ya no se ejecuta.
  · Origen del turno: 'usuario' solo si el terminal es de la persona (app, web,
    overlay), no trae imágenes, no se le añadieron notas (RAG) y no se declaró
    `origen` distinto. El bot de Telegram (kind «bot»), un kind desconocido o
    texto de terceros → 'no_confiable': solo herramientas de LECTURA.
  · Aprobaciones: tool:approval:request va SOLO al terminal que preguntó, y
    solo si anunció que emite tool:approval:response. Solo cuenta su respuesta.
    Sin canal de aprobación, lo que la necesita se rechaza con un mensaje claro
    y al modelo ni se le ofrece (reglas del prompt sin esas herramientas).
    Sin respuesta en 60 s, rechazada (tool:approval:close). La petición, el
    cierre y el tool:result llevan como parent_id el input:text de SU turno
    (no el último), para que el terminal los enrute aunque ya escribiera otro.
  · Taint (revisión S1): el AIManager es UNO para todos los terminales, así que
    lo que entra por un turno no confiable (el bot de Telegram, notas, imágenes)
    queda marcado en el historial y contamina los turnos de los demás mientras
    siga en la ventana: ahí todo lo que no sea de LECTURA pide permiso, y en un
    terminal que no puede aprobar se rechaza (y el prompt solo ofrece lectura).
  · Memoria (revisión final, SN1): el «CONTEXTO DE MEMORIA DEL USUARIO» solo va
    en el system prompt de los terminales de la persona (KINDS_USUARIO). El hub no
    sabe quién escribe por el bot de Telegram (solo que el peer es kind «bot»), así
    que a esos turnos no se les inyecta: nada de lo que recuerdas sale hacia un chat
    que no se puede verificar como tuyo.
  · Los resultados inmediatos van en output:chat:done.tools; los que llegan
    tras una aprobación, en tool:result. Los fallos y rechazos inmediatos se
    cuentan también en el texto del done (los terminales descartan `tools`).
  · Un session_id distinto del anterior del mismo terminal = conversación nueva
    (presupuesto repuesto).

Reutiliza el AIManager de la app (mismos proveedores y ajustes), la memoria del
host (para el contexto y para persistir) y, opcionalmente, el ToolManager y el
servicio de notas (RAG). Es el equivalente de ServicioMemoria para el chat.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .hub import Hub, Peer
from .protocolo import Evento, Tipo, nuevo_evento
from . import marcadores
from .acciones import Ejecutor, ResultadoAccion, RECHAZADA, limpiar_texto
from .catalogo_herramientas import ORIGEN_NO_CONFIABLE, ORIGEN_USUARIO
from .herramientas import Riesgo, Sesion, registro_por_defecto
from .prompt import ETIQUETA_EXTERNO, bloque_contexto, construir_system_prompt, prefijo_hora
from .reglas_prompt import reglas_herramientas

# Kinds de terminal que escribe la propia persona. El resto (bot de Telegram,
# desconocidos) es texto de terceros.
KINDS_USUARIO = frozenset({"app", "web", "overlay"})
# Ejecutores por terminal que se recuerdan (los peers cambian de id al reconectar).
MAX_TERMINALES = 16


def _kwargs_chat(chat, **opciones) -> dict:
    """Las `opciones` (origen, efimero) que acepta `chat`; un adaptador viejo no las recibe."""
    try:
        params = inspect.signature(chat).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(opciones)
    return {k: v for k, v in opciones.items() if k in params}


@dataclass
class _Terminal:
    """Un terminal con su Ejecutor, su conversación y sus aprobaciones abiertas."""
    peer: Peer
    loop: Optional[asyncio.AbstractEventLoop] = None
    ejecutor: Optional[Ejecutor] = None
    session_id: str = ""
    ev_id: Optional[str] = None                       # último input:text (parent_id)
    pendientes: Dict[str, Callable[[bool], None]] = field(default_factory=dict)
    turno_de: Dict[str, str] = field(default_factory=dict)   # id de aprobación → input:text
    # ids rechazados por no poder preguntar → ¿era por contexto contaminado?
    sin_canal: Dict[str, bool] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class ServicioChat:
    def __init__(self, hub: Hub, ai_manager, memoria=None, tools=None, notas=None,
                 provider_por_defecto: str = "ollama", persona=None, *, modo: str = "normal"):
        self.hub = hub
        self.ai = ai_manager
        self.memoria = memoria
        self.tools = tools
        self.notas = notas
        self.provider_por_defecto = provider_por_defecto
        self.modo = modo                 # modo del catálogo de herramientas en el host
        self._persona = persona          # str o callable → persona base del system prompt
        self._terminales: "OrderedDict[str, _Terminal]" = OrderedDict()
        self._local = threading.local()
        hub.registrar(Tipo.INPUT_TEXT, self._on_input)
        hub.registrar(Tipo.TOOL_APPROVAL_RESPONSE, self._on_aprobacion)

    # ── System prompt (persona + memoria + herramientas + emociones + RAG) ──────
    def _fragmentos_notas(self, texto_usuario: str) -> list:
        if self.notas is None or not getattr(self.notas, "activo", False):
            return []
        try:
            return list(self.notas.contexto_para(texto_usuario) or [])
        except Exception:
            return []

    @staticmethod
    def _sin_aprobacion(ejecutor: Ejecutor) -> set:
        """Herramientas con handler que NO piden aprobación (para quien no puede darla)."""
        registro = ejecutor.registro
        fuera = set()
        for nombre in ejecutor.handlers:
            d = registro.get(nombre) if registro is not None else None
            if d is not None and not d.requiere_aprobacion and d.riesgo != Riesgo.DESTRUCTIVO:
                fuera.add(nombre)
        return fuera

    def _contaminado(self, provider: str) -> bool:
        fn = getattr(self.ai, "contexto_contaminado", None)
        try:
            return bool(fn(provider)) if callable(fn) else False
        except Exception:
            return True

    def _system(self, texto_usuario: str, *, origen: str = ORIGEN_USUARIO,
                ejecutor: Optional[Ejecutor] = None, ctx: Optional[dict] = None,
                fragmentos: Optional[list] = None, puede_aprobar: bool = True,
                contaminado: bool = False, con_memoria: bool = True,
                con_fecha: bool = False, notas_en_mensaje: bool = False) -> str:
        """
        Como la app (lune_core.prompt.construir_system_prompt): persona → fecha →
        emociones → herramientas → anti-inyección → memoria al final. Estable de un
        turno a otro para que el modelo local reuse su caché.

        puede_aprobar  False: el terminal no contesta aprobaciones → no se le
                       ofrecen herramientas que las piden (se rechazarían).
        contaminado    el historial lleva texto de terceros: sin poder aprobar,
                       solo lectura (lo demás pediría permiso).
        con_memoria    False: sin el contexto de memoria del usuario (turnos de
                       un terminal que no es de la persona: ver ve_la_memoria).
        con_fecha      la hora llega como prefijo del mensaje: la regla que lo explica.
        notas_en_mensaje  las notas (RAG) van en el mensaje (`_anexo_notas`); si el
                       chat no lo admite, aquí, antes de la memoria.
        """
        base = self._persona() if callable(self._persona) else (self._persona or "")
        try:
            ctx_mem = (self.memoria.obtener_contexto_para_prompt()
                       if self.memoria and con_memoria else "")
        except Exception:
            ctx_mem = ""
        reglas = ""
        if ejecutor is not None:
            try:
                disponibles = (set(ejecutor.handlers) if puede_aprobar
                               else self._sin_aprobacion(ejecutor))
                solo_lectura = origen != ORIGEN_USUARIO or (contaminado and not puede_aprobar)
                reglas = reglas_herramientas(ejecutor.registro, self.modo, disponibles,
                                             con_titulo=False, solo_lectura=solo_lectura, ctx=ctx)
            except Exception:
                reglas = ""
        frags = self._fragmentos_notas(texto_usuario) if fragmentos is None else fragmentos
        notas = "" if notas_en_mensaje else self._anexo_notas(frags)
        return construir_system_prompt(str(base or ""), herramientas=reglas, extra=notas,
                                       con_fecha=con_fecha, memoria=ctx_mem or "")

    @staticmethod
    def _anexo_notas(frags) -> str:
        """Las notas (RAG) de este mensaje, envueltas, neutralizadas y con su etiqueta."""
        if not frags:
            return ""
        try:
            return f"{ETIQUETA_EXTERNO}\n{bloque_contexto(frags)}"
        except Exception:
            return ""

    def _provider(self, pedido: Optional[str]) -> str:
        """Usa el proveedor pedido si el host lo tiene disponible; si no, el suyo."""
        try:
            provs = getattr(self.ai, "providers", {})
            if pedido and pedido in provs and provs[pedido].is_available():
                return pedido
        except Exception:
            pass
        return self.provider_por_defecto

    def _ctx(self, provider: str, turno: Optional[str] = None) -> dict:
        """ctx del Ejecutor: modo, proveedor y su URL (para saber si es la nube), el
        AIManager (el Ejecutor mira al ejecutar si el contexto está contaminado) y
        el id del input:text del turno (parent_id de sus aprobaciones)."""
        url = ""
        try:
            p = (getattr(self.ai, "providers", None) or {}).get(provider)
            url = str(getattr(p, "base_url", "") or getattr(p, "url", "") or "")
        except Exception:
            pass
        ctx = {"modo": self.modo, "proveedor": provider or "", "url": url, "ai": self.ai}
        if turno:
            ctx["turno"] = turno
        return ctx

    @staticmethod
    def origen_de(ev: Evento, peer: Peer, *, con_notas: bool = False, imagenes=None) -> str:
        """'usuario' o 'no_confiable' para este turno (ver la cabecera)."""
        if str(getattr(peer, "kind", "") or "").strip().lower() not in KINDS_USUARIO:
            return ORIGEN_NO_CONFIABLE
        if str(ev.data.get("origen") or ORIGEN_USUARIO).strip().lower() != ORIGEN_USUARIO:
            return ORIGEN_NO_CONFIABLE
        if con_notas or imagenes:
            return ORIGEN_NO_CONFIABLE
        return ORIGEN_USUARIO

    @staticmethod
    def ve_la_memoria(peer: Peer) -> bool:
        """¿Lleva este terminal la memoria del usuario en el system prompt? Solo los de
        la persona (app, web, overlay). El bot de Telegram (kind «bot») o un kind
        desconocido, no: el hub no puede verificar que quien escribe sea el dueño."""
        return str(getattr(peer, "kind", "") or "").strip().lower() in KINDS_USUARIO

    # ── Un Ejecutor por terminal ────────────────────────────────────────────────
    def _terminal(self, peer: Peer, loop) -> Optional[_Terminal]:
        if self.tools is None:
            return None
        t = self._terminales.get(peer.id)
        if t is None:
            t = _Terminal(peer=peer, loop=loop)
            try:
                t.ejecutor = self._crear_ejecutor(t)
            except Exception:
                return None
            self._terminales[peer.id] = t
            while len(self._terminales) > MAX_TERMINALES:
                _, viejo = self._terminales.popitem(last=False)
                if viejo.ejecutor is not None:
                    viejo.ejecutor.nueva_conversacion()
        else:
            self._terminales.move_to_end(peer.id)
        t.peer, t.loop = peer, loop
        return t

    def _crear_ejecutor(self, t: _Terminal) -> Ejecutor:
        kw = dict(pedir_aprobacion=lambda p, r: self._pedir(t, p, r),
                  despachar=self._despachar,
                  cerrar_aprobacion=lambda pid: self._cerrar(t, pid))
        crear = getattr(self.tools, "crear_ejecutor", None)
        if callable(crear):
            return crear(**kw)
        registro = registro_por_defecto()
        handlers = getattr(self.tools, "handlers", None) or {}
        return Ejecutor(registro, Sesion(registro), handlers=dict(handlers), **kw)

    def _despachar(self, fn: Callable[[], None]) -> None:
        """
        Lo que pasa tras una aprobación (handler incluido) va fuera del bucle del
        hub, en un hilo propio. Si ya estamos en el hilo que ejecuta las llamadas
        de este turno (p. ej. un rechazo inmediato por no tener a quién
        preguntar), se hace en línea: así ese resultado entra en el done.
        """
        if getattr(self._local, "ejecutando", False):
            fn()
            return
        threading.Thread(target=fn, name="lune-accion", daemon=True).start()

    def _ejecutar_turno(self, ejecutor: Ejecutor, llamadas, origen: str, ctx: dict,
                        al_resultado) -> None:
        self._local.ejecutando = True
        try:
            ejecutor.ejecutar_llamadas(llamadas, origen, ctx, al_resultado)
        finally:
            self._local.ejecutando = False

    @staticmethod
    def puede_aprobar(peer: Peer) -> bool:
        """¿Anunció este terminal que sabe contestar aprobaciones?"""
        return Tipo.TOOL_APPROVAL_RESPONSE.value in (getattr(peer, "events", None) or [])

    def _enviar(self, t: _Terminal, tipo: Tipo, data: dict, parent_id: Optional[str] = None) -> None:
        """Envía al terminal desde cualquier hilo (el bucle es el del hub). parent_id:
        el input:text del turno al que pertenece (por defecto, el último)."""
        loop = t.loop
        if loop is None or loop.is_closed():
            return
        ev = nuevo_evento(tipo, data, self.hub.fuente, parent_id=parent_id or t.ev_id)
        try:
            asyncio.run_coroutine_threadsafe(self.hub.enviar_a(t.peer, ev), loop)
        except RuntimeError:
            pass                                         # el bucle ya se cerró

    def _pedir(self, t: _Terminal, pendiente: dict, responder: Callable[[bool], None]) -> None:
        pendiente = dict(pendiente)
        pid = str(pendiente.get("id") or "")
        turno = pendiente.pop("turno", None) or t.ev_id
        if not self.puede_aprobar(t.peer) or t.peer.id not in self.hub.peers:
            with t.lock:
                t.sin_canal[pid] = bool(pendiente.get("contaminado"))
            raise RuntimeError("este terminal no puede pedir permiso")
        with t.lock:
            t.pendientes[pid] = responder
            if turno:
                t.turno_de[pid] = turno
        why = pendiente.get("resumen", "")
        if pendiente.get("contaminado"):
            why = f"{why}. {pendiente.get('motivo', '')}".strip(". ")
        datos = {**pendiente, "tool": pendiente.get("herramienta", ""),
                 "why": why, "risk": pendiente.get("riesgo", "")}
        self._enviar(t, Tipo.TOOL_APPROVAL_REQUEST, datos, parent_id=turno)

    def _cerrar(self, t: _Terminal, pid: str) -> None:
        with t.lock:
            t.pendientes.pop(pid, None)
            turno = t.turno_de.pop(pid, None)
        self._enviar(t, Tipo.TOOL_APPROVAL_CLOSE, {"id": pid, "motivo": "sin respuesta o cancelada"},
                     parent_id=turno)

    async def _on_aprobacion(self, ev: Evento, peer: Peer):
        """Respuesta humana del terminal al que se preguntó (las de otros se ignoran)."""
        pid = str(ev.data.get("id") or "")
        t = self._terminales.get(peer.id)
        if t is None or not pid:
            return
        with t.lock:
            responder = t.pendientes.pop(pid, None)
            t.turno_de.pop(pid, None)
        if responder is not None:
            responder(ev.data.get("approved") is True)

    def _resultado(self, t: _Terminal, res: ResultadoAccion) -> dict:
        d = res.a_dict()
        with t.lock:
            sin_canal = res.pendiente_id in t.sin_canal
            contaminado = t.sin_canal.pop(res.pendiente_id, False)
        if res.estado == RECHAZADA and sin_canal:
            porque = (" porque la conversación contiene contenido externo (p. ej. mensajes de "
                      "Telegram)," if contaminado else "")
            d["mensaje"] = (f"«{res.herramienta}» necesita tu permiso{porque} y este terminal "
                            "no puede pedírtelo: pídelo desde la app de Lune en el equipo host.")
        return d

    def _sin_claves(self, error) -> str:
        """Un error sin claves (puede traer «Bearer <clave>»)."""
        redactar = getattr(self.ai, "redactar", None)
        try:
            if callable(redactar):
                return str(redactar(error))
        except Exception:
            pass
        try:
            from servicios.ai_manager import redactar_secretos
            return redactar_secretos(error)
        except Exception:
            return "error interno"

    # ── Manejo del chat ─────────────────────────────────────────────────────────
    async def _on_input(self, ev: Evento, peer: Peer):
        text = str(ev.data.get("text") or "")
        if not text.strip():
            await self.hub.responder(peer, Tipo.OUTPUT_DONE, {"text": "", "usage": {}}, ev)
            return
        imagenes = ev.data.get("images") or []
        provider = self._provider(ev.data.get("provider"))
        loop = asyncio.get_running_loop()

        term = self._terminal(peer, loop)
        ejecutor = term.ejecutor if term is not None else None
        turno = ev.meta.id
        if term is not None:
            term.ev_id = turno
            sesion = str(ev.data.get("session_id") or "")
            if sesion and term.session_id and sesion != term.session_id:
                ejecutor.nueva_conversacion()
            if sesion:
                term.session_id = sesion
        frags = self._fragmentos_notas(text)
        origen = self.origen_de(ev, peer, con_notas=bool(frags), imagenes=imagenes)
        efimero = ev.data.get("efimero") is True        # p. ej. comentario de pantalla
        ctx = self._ctx(provider, turno)
        # Caché del modelo: la hora y las notas van en el mensaje (si el chat lo admite),
        # no en el system. Mensaje y hora quedan en ctx para el cotejo del Ejecutor.
        momento = datetime.now()
        ctx["mensaje_usuario"], ctx["momento"] = text, momento
        acepta = _kwargs_chat(self.ai.chat, prefijo="x", anexo="x")
        system = self._system(text, origen=origen, ejecutor=ejecutor, ctx=ctx, fragmentos=frags,
                              puede_aprobar=self.puede_aprobar(peer),
                              contaminado=self._contaminado(provider),
                              con_memoria=self.ve_la_memoria(peer),
                              con_fecha="prefijo" in acepta, notas_en_mensaje="anexo" in acepta)

        self.hub.estado_extra["busy"] = True
        await self.hub.publicar(Tipo.HOST_STATUS, self.hub.estado())

        # Streaming con batching: agrupa tokens para no saturar la red con
        # un mensaje por carácter. El modelo escupe desde un hilo del executor,
        # así que se agenda el envío en el bucle del hub de forma segura.
        pend = {"buf": "", "last": time.monotonic()}

        def on_token(tok: str):
            pend["buf"] += tok
            ahora = time.monotonic()
            if len(pend["buf"]) >= 24 or (ahora - pend["last"]) > 0.12:
                chunk, pend["buf"], pend["last"] = pend["buf"], "", ahora
                asyncio.run_coroutine_threadsafe(
                    self.hub.responder(peer, Tipo.OUTPUT_DELTA, {"text": chunk}, ev), loop)

        # El origen va al historial (taint); un turno efímero no se guarda.
        opciones = {"origen": origen, "efimero": efimero}
        if "prefijo" in acepta:
            opciones["prefijo"] = prefijo_hora(momento)
        anexo = self._anexo_notas(frags) if "anexo" in acepta else ""
        if anexo:
            opciones["anexo"] = anexo
        extra = _kwargs_chat(self.ai.chat, **opciones)
        try:
            texto = await self.ai.chat(text, system, provider=provider,
                                       on_token=on_token, imagenes=imagenes, **extra)
        except Exception as e:
            texto = f"Error del host al generar la respuesta: {self._sin_claves(e)}"
        texto = texto or ""

        if pend["buf"]:      # lo que quedó sin enviar
            await self.hub.responder(peer, Tipo.OUTPUT_DELTA, {"text": pend["buf"]}, ev)

        # Herramientas: el Ejecutor saca las <|CALL|> ANTES de separar las
        # emociones (el parser de marcadores también se come las CALL).
        llamadas = []
        if ejecutor is not None:
            try:
                sin_calls, llamadas = ejecutor.procesar(texto, origen, ctx)
            except Exception:
                sin_calls, llamadas = limpiar_texto(texto), []
        else:
            sin_calls = limpiar_texto(texto)

        # Emociones: separa marcadores y emite un ACT por cada uno.
        hablable, control = marcadores.separar(sin_calls)
        acts = [v for c, v in control if c == "act"]
        for a in acts:
            await self.hub.responder(peer, Tipo.OUTPUT_ACT, a, ev)

        # Acciones EN EL HOST, fuera del bucle del hub. Lo que se resuelve ya va
        # en el done; lo que espera aprobación llega luego como tool:result.
        resultados_tools: List[dict] = []
        if ejecutor is not None and llamadas:
            caja = {"done": False, "lista": []}
            cerrojo = threading.Lock()

            def al_resultado(res: ResultadoAccion, t=term):
                d = self._resultado(t, res)
                with cerrojo:
                    if not caja["done"]:
                        caja["lista"].append(d)
                        return
                self._enviar(t, Tipo.TOOL_RESULT, d, parent_id=turno)

            try:
                await loop.run_in_executor(
                    None, lambda: self._ejecutar_turno(ejecutor, llamadas, origen, ctx, al_resultado))
            except Exception:
                pass
            with cerrojo:
                caja["done"] = True
                resultados_tools = list(caja["lista"])

        # Lo que no se hizo se cuenta en el texto: los terminales no enseñan `tools`
        # y el modelo pudo decir «te la abro».
        avisos = [str(d.get("mensaje") or "") for d in resultados_tools if not d.get("ok")]
        avisos = [a for a in avisos if a]
        if avisos:
            hablable = (hablable.rstrip() + "\n\n" if hablable.strip() else "") + "\n".join(avisos)

        # Persistir en la memoria del host (sesión, resumen…). Un turno efímero no.
        try:
            if self.memoria and not efimero:
                self.memoria.procesar_respuesta_lune(sin_calls)
        except Exception:
            pass

        try:
            usage = self.ai.uso(provider)
        except Exception:
            usage = {}

        self.hub.estado_extra["busy"] = False
        await self.hub.publicar(Tipo.HOST_STATUS, self.hub.estado())
        await self.hub.responder(peer, Tipo.OUTPUT_DONE,
                                 {"text": hablable, "usage": usage,
                                  "acts": acts, "tools": resultados_tools}, ev)
