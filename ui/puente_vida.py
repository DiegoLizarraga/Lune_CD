"""
ui/puente_vida.py — objeto `vida` del QWebChannel (window.luneVida), cortes 7 y 8.

Lo usa la piel web normal (ui_web/ui_kits/lune-desktop/extra/vida.jsx): las tarjetas
SentarseCard, ComidaCard, DiscordCard y AutoinicioOpciones, y `ComidaWeb`, la comida
que sigue al ratón dentro de la ventana cuando la asistente flotante no está fuera.

Se registra SIEMPRE en `VentanaWeb.__init__`, antes de `setUrl` (el JS solo ve lo que
estaba registrado al crear su QWebChannel), y recibe los controladores tarde:
`enlazar(servicios_c4)` toma `ServiciosCorte4.vida` (ui/montaje_vida.ServiciosVida), un
ServiciosVida directamente o, si falta alguno, el registrado en el escritorio. Sin ellos,
cada ranura devuelve un estado por defecto y lo que es solo config se lee y se guarda
igual. `enlazar` se apunta en `servicios._deshacer`: al desmontar (cambio de interfaz en
caliente, salir) suelta los controladores antes de que ServiciosVida los borre.

Todo lo que entra de la página se valida (JSON ≤ 16 KB, tipos estrictos, enums, rangos)
y todo lo que sale hacia ella se normaliza. PRIVACIDAD de Discord: la línea «Discord ve:
…» solo lleva textos de la lista fija de servicios/discord_presencia (detalles «Lune CD ·
…» y los estados de ESTADOS); nunca títulos de ventana, nombres de programa, el chat ni
nada que no esté en esa lista (lo desconocido se descarta).

Ranuras (JS: el resultado llega por callback, `luneVida.x(args…, cb)`):
    asiento_estado() → str            {sentada (""|barra|ventana), variante, ventanas, barra, offset,
                                       servicio, asistente, juego, arrastrando, cedida}
    asiento_config_guardar(json) → str {ok, error, estado}   {ventanas?, barra?: bool, offset?: −64..64}
    asiento_sentar(sitio) → str       {ok, texto, estado}     sitio: barra | ventana
    asiento_bajar() → bool
    comida_estado() → str             {activa, id, variante, color, tipo, nombre, vista (""|escritorio|web),
                                       disponible (comida.activa), servicio,
                                       catalogo: [{id, nombre, tipo, variantes: [{id, nombre, color}]}]}
    comida_alternar(id) → str         {ok, accion (aparece|guarda|cambia|""), motivo, texto, estado}
    comida_guardar() → bool
    comida_evento(id) → bool          ComidaWeb acertó en la cabeza de la barra (enfriamiento 0.35 s)
    comida_config_guardar(json) → str {ok, error, estado}   {activa: bool}
    discord_estado() → str            {activo, conectado, usuario, error, client_id_ok, sin_id, publicando,
                                       vista_previa ({details, state} | null), servicio,
                                       config: {client_id, mostrar_modelo, boton_url}}
    discord_alternar() → bool         el estado nuevo
    discord_config_guardar(json) → str {ok, error, estado}  {activo?, mostrar_modelo?: bool,
                                       client_id?: "" | 17–20 cifras, boton_url?: "" | https ≤ 512 B}
    autoinicio_estado() → str         {activo, registrado, aprobado, ruta_ok, modo_ok, como, retraso_s,
                                       disponible (hay registro: Windows)}
    autoinicio_opciones(json) → str   {ok, error, estado}   {como?: bandeja|asistente|ventana, retraso_s?: 0–120}
Señales:
    asiento_cambio(str)     JSON de asiento_estado()
    comida_cambio(str)      JSON de comida_estado() sin el catálogo
    comida_web(str)         {accion: aparece|guarda|cambia, id, variante, color, tipo, nombre} (color, tipo y
                            nombre salen del catálogo, no del emisor)
    discord_cambio(str)     JSON de discord_estado()
    autoinicio_cambio(str)  JSON de autoinicio_estado() (tras guardar opciones)

    puente = registrar_puente_vida(canal, config, servicios_c4=None)
    puente.enlazar(servicios_c4)      # en _montar_servicios_c4
    puente.cerrar()                   # en _liberar_todo
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from nucleo import comida as nc
from ui.puentes_ocio import PuenteOcioBase, dump, entero, es_bool, leer_json, llamar, texto_limpio

_log = logging.getLogger("lune.puente_vida")

SITIOS = ("barra", "ventana")
OFFSET_MAX = 64
RETRASO_MAX = 120                      # como /autoinicio espera N de patata
COMOS = ("bandeja", "asistente", "ventana")
ID_DISCORD = re.compile(r"^\d{17,20}$")
MAX_URL = 512
VISTAS_COMIDA = ("escritorio", "web")
ACCIONES_COMIDA = ("aparece", "guarda", "cambia")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MOTIVO = re.compile(r"^[a-z_]{1,24}$")

# Privacidad: lo único que puede salir en «Discord ve: …» (servicios/discord_presencia).
DETALLES_DISCORD = ("Escritorio · 3D", "Escritorio · animación", "Escritorio · sprites", "Ventana", "Terminal")
_ESTADOS_DISCORD = (
    "Con una alarma sonando", "En pantalla grande", "Durmiendo en el salvapantallas", "En una llamada",
    "Paseando por la pantalla", "Bailando ♪", "Merendando", "Echando una siesta sentada",
    "Durmiendo (-_-) zzZ", "Sentada en la barra de tareas", "Sentada en una ventana", "Pensando…",
    "Hablando", "En el escritorio", "Charlando", "En la terminal",
)
TEXTO_SIN_SERVICIO_ASIENTO = "Para sentarme necesito la app abierta (servicios de escritorio)."


def estados_discord() -> frozenset:
    """Los textos fijos de `state` (los de discord_presencia.ESTADOS si se puede importar)."""
    try:
        from servicios.discord_presencia import ESTADOS
        return frozenset(t for _, t in ESTADOS)
    except Exception:
        return frozenset(_ESTADOS_DISCORD)


def publicacion_segura(p: Any) -> Optional[Dict[str, str]]:
    """{details, state} si los dos son textos de la lista fija; si no, None (no se enseña)."""
    if not isinstance(p, dict):
        return None
    details, state = p.get("details"), p.get("state")
    if not isinstance(details, str) or not isinstance(state, str):
        return None
    prefijo = "Lune CD · "
    if not details.startswith(prefijo) or details[len(prefijo):] not in DETALLES_DISCORD:
        return None
    if state not in estados_discord():
        return None
    return {"details": details, "state": state}


def url_boton_valida(url: Any) -> bool:
    """https con host y ≤ 512 B, sin espacios ni caracteres raros (como discord_presencia.url_boton)."""
    if not isinstance(url, str):
        return False
    try:
        from servicios.discord_presencia import url_boton
        return bool(url) and url_boton(url) == url
    except Exception:
        pass
    u = url
    if not u or len(u.encode("utf-8")) > MAX_URL or u != u.strip():
        return False
    if any(c.isspace() or ord(c) < 32 or c in "<>\"'`\\" for c in u):
        return False
    try:
        partes = urlsplit(u)
    except ValueError:
        return False
    return partes.scheme == "https" and bool(partes.hostname) and "." in (partes.hostname or "")


def controladores_vida(servicios: Any) -> Dict[str, Any]:
    """{asiento, comida, discord} de lo que se le dé a `enlazar`:
      · ServiciosCorte4 con `.vida` (ServiciosVida de montar_vida);
      · un ServiciosVida directamente (con .asiento/.comida/.discord);
      · si falta alguno, el registrado en el escritorio (`escritorio.obtener(nombre)`).
    Lo que no esté es None."""
    out: Dict[str, Any] = {"asiento": None, "comida": None, "discord": None}
    if servicios is None:
        return out
    vida = getattr(servicios, "vida", None)
    base = vida if vida is not None else servicios
    for n in out:
        out[n] = getattr(base, n, None)
    esc = getattr(servicios, "escritorio", None)
    obtener = getattr(esc, "obtener", None) if esc is not None else None
    if callable(obtener):
        for n in out:
            if out[n] is None:
                try:
                    out[n] = obtener(n)
                except Exception:
                    out[n] = None
    return out


def _catalogo() -> List[Dict[str, Any]]:
    try:
        return nc.catalogo_para_web()
    except Exception:
        _log.exception("puente vida: catálogo de la comida")
        return []


def _comida_exacta(id_: Any) -> Optional[str]:
    """Solo ids exactos del catálogo (ni alias ni mayúsculas: la página manda los ids)."""
    return id_ if isinstance(id_, str) and id_ in nc.CATALOGO else None


def _variante(id_: str, variante: Any) -> Any:
    """La variante exacta de la comida `id_` (Variante) o None."""
    c = nc.CATALOGO.get(id_)
    if c is None or not isinstance(variante, str):
        return None
    return next((v for v in c.variantes if v.id == variante), None)


class PuenteVida(PuenteOcioBase):
    """Objeto `vida` del QWebChannel (window.luneVida)."""

    NOMBRE = "puente_vida"

    asiento_cambio = pyqtSignal(str)
    comida_cambio = pyqtSignal(str)
    comida_web = pyqtSignal(str)
    discord_cambio = pyqtSignal(str)
    autoinicio_cambio = pyqtSignal(str)

    def __init__(self, config: Any = None, *, autoinicio: Any = None, arranque: Any = None,
                 parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._asiento: Any = None
        self._comida: Any = None
        self._discord: Any = None
        self._servicios: Any = None
        self._enganchados: List[Any] = []
        self._autoinicio = autoinicio
        self._autoinicio_inyectado = autoinicio is not None       # tests: como en Windows
        self._arranque = arranque

    # ── Servicios ──────────────────────────────────────────────────────────────
    @property
    def asiento(self) -> Any:
        return self._asiento

    @property
    def comida(self) -> Any:
        return self._comida

    @property
    def discord(self) -> Any:
        return self._discord

    def enlazar(self, servicios: Any = None) -> None:
        """Da al puente los controladores de los cortes 7/8 (o los suelta con None).

        Acepta ServiciosCorte4 (usa su `.vida`), un ServiciosVida o None. Reconecta las
        señales y, si algo cambió, manda el estado nuevo a la página."""
        if self._cerrado:
            servicios = None
        c = controladores_vida(servicios)
        antes = (self._asiento, self._comida, self._discord)
        self._desconectar_todo()
        self._servicios = servicios
        self._asiento, self._comida, self._discord = c["asiento"], c["comida"], c["discord"]
        self._conectar(self._asiento, "cambio", self._on_asiento)
        self._conectar(self._comida, "cambio", self._on_comida)
        self._conectar(self._comida, "comida_web", self._on_comida_web)
        self._conectar(self._discord, "estado_cambio", self._on_discord)
        if self._cerrado:
            return
        if antes != (self._asiento, self._comida, self._discord):
            self.asiento_cambio.emit(dump(self._estado_asiento()))
            self.comida_cambio.emit(dump(self._estado_comida()))
            self.discord_cambio.emit(dump(self._estado_discord()))
        deshacer = getattr(servicios, "_deshacer", None) if servicios is not None else None
        if isinstance(deshacer, list) and not any(s is servicios for s in self._enganchados):
            self._enganchados.append(servicios)

            def soltar(s=servicios) -> None:
                if self._servicios is s:
                    self.enlazar(None)
            deshacer.append(soltar)

    def cerrar(self) -> None:
        """Suelta controladores, señales y el registro en el canal. Idempotente."""
        self._asiento = self._comida = self._discord = None
        self._servicios = None
        self._enganchados.clear()
        super().cerrar()

    # ── Señales de los controladores ───────────────────────────────────────────
    def _on_asiento(self, *_: Any) -> None:
        self.asiento_cambio.emit(dump(self._estado_asiento()))

    def _on_comida(self, *_: Any) -> None:
        self.comida_cambio.emit(dump(self._estado_comida()))

    def _on_comida_web(self, payload: Any = None) -> None:
        obj = leer_json(payload) if isinstance(payload, str) else payload
        datos = self._normalizar_web(obj)
        if datos is not None:
            self.comida_web.emit(dump(datos))

    def _on_discord(self, *_: Any) -> None:
        self.discord_cambio.emit(dump(self._estado_discord()))

    # ═══ Sentarse (corte 7) ═══════════════════════════════════════════════════
    def _config_asiento(self) -> Dict[str, Any]:
        off = entero(self._cfg("avatar", "sentarse_offset_px", 0))
        return {
            "ventanas": self._cfg("avatar", "sentarse_ventanas", False) is True,
            "barra": self._cfg("avatar", "sentarse_barra", True) is not False,
            "offset": max(-OFFSET_MAX, min(OFFSET_MAX, off if off is not None else 0)),
        }

    def _estado_asiento(self) -> Dict[str, Any]:
        e = llamar(self._asiento, "estado") if self._asiento is not None else None
        e = e if isinstance(e, dict) else {}
        sentada = e.get("sentada") if e.get("sentada") in SITIOS else ""
        variante = entero(e.get("variante"))
        return {
            "sentada": sentada,
            "variante": max(0, min(7, variante)) if sentada and variante is not None else 0,
            **self._config_asiento(),
            "servicio": self._asiento is not None,
            "asistente": e.get("disponible") is True,
            "juego": e.get("juego") is True,
            "arrastrando": e.get("arrastrando") is True,
            "cedida": e.get("cedida") is True,
        }

    @pyqtSlot(result=str)
    def asiento_estado(self) -> str:
        return dump(self._estado_asiento())

    @pyqtSlot(str, result=str)
    def asiento_config_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._estado_asiento()})

        if not obj or any(k not in ("ventanas", "barra", "offset") for k in obj):
            return falla("Ajustes de sentarse no válidos.")
        cambios: Dict[str, Any] = {}
        for k, clave in (("ventanas", "sentarse_ventanas"), ("barra", "sentarse_barra")):
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios[clave] = obj[k]
        if "offset" in obj:
            off = entero(obj["offset"])
            if off is None or not -OFFSET_MAX <= off <= OFFSET_MAX:
                return falla(f"El ajuste de altura va de −{OFFSET_MAX} a {OFFSET_MAX} px.")
            cambios["sentarse_offset_px"] = off
        ok = self._guardar_cambios("avatar", cambios)
        llamar(self._asiento, "recargar_config")
        estado = self._estado_asiento()
        self.asiento_cambio.emit(dump(estado))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": estado})

    @pyqtSlot(str, result=str)
    def asiento_sentar(self, sitio: str) -> str:
        if not isinstance(sitio, str) or sitio not in SITIOS:
            return dump({"ok": False, "texto": "¿Dónde me siento? En la barra o en una ventana.",
                         "estado": self._estado_asiento()})
        if self._asiento is None:
            return dump({"ok": False, "texto": TEXTO_SIN_SERVICIO_ASIENTO, "estado": self._estado_asiento()})
        r = llamar(self._asiento, "sentar", sitio)
        ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (False, ""))
        return dump({"ok": ok is True, "texto": texto_limpio(texto), "estado": self._estado_asiento()})

    @pyqtSlot(result=bool)
    def asiento_bajar(self) -> bool:
        return llamar(self._asiento, "bajar") is True

    # ═══ Comida (corte 8) ═════════════════════════════════════════════════════
    def _habilitada(self) -> bool:
        return self._cfg("comida", "activa", True) is not False

    def _estado_comida(self, *, catalogo: bool = False) -> Dict[str, Any]:
        e = llamar(self._comida, "estado") if self._comida is not None else None
        e = e if isinstance(e, dict) else {}
        id_ = _comida_exacta(e.get("id")) if e.get("activa") is True else None
        v = _variante(id_, e.get("variante")) if id_ else None
        c = nc.CATALOGO.get(id_) if id_ else None
        activa = c is not None and v is not None
        out: Dict[str, Any] = {
            "activa": activa,
            "id": c.id if activa else "",
            "variante": v.id if activa else "",
            "color": v.color if activa and _COLOR.match(v.color or "") else "",
            "tipo": c.tipo if activa else "",
            "nombre": c.nombre if activa else "",
            "vista": e.get("vista") if activa and e.get("vista") in VISTAS_COMIDA else "",
            "disponible": self._habilitada(),
            "servicio": self._comida is not None,
        }
        if catalogo:
            out["catalogo"] = _catalogo()
        return out

    def _normalizar_web(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Payload de ControlComida.comida_web → lo que la página dibuja (del catálogo)."""
        if not isinstance(obj, dict) or obj.get("accion") not in ACCIONES_COMIDA:
            return None
        id_ = _comida_exacta(obj.get("id"))
        if id_ is None:
            return None
        c = nc.CATALOGO[id_]
        v = _variante(id_, obj.get("variante")) or c.variantes[0]
        return {"accion": obj["accion"], "id": id_, "variante": v.id,
                "color": v.color if _COLOR.match(v.color or "") else "#FFFFFF",
                "tipo": c.tipo, "nombre": c.nombre}

    @pyqtSlot(result=str)
    def comida_estado(self) -> str:
        return dump(self._estado_comida(catalogo=True))

    @pyqtSlot(str, result=str)
    def comida_alternar(self, id_: str) -> str:
        n = _comida_exacta(id_)
        if n is None:
            return dump({"ok": False, "accion": "", "motivo": "desconocida", "texto": "Esa comida no existe.",
                         "estado": self._estado_comida()})
        if self._comida is None:
            return dump({"ok": False, "accion": "", "motivo": "sin_servicio",
                         "texto": "La comida necesita la app (servicios de escritorio).",
                         "estado": self._estado_comida()})
        r = llamar(self._comida, "alternar", n)
        accion = r if r in ACCIONES_COMIDA else ""
        motivo = ""
        texto = ""
        if not accion:
            m = getattr(self._comida, "ultimo_motivo", "")
            motivo = m if isinstance(m, str) and _MOTIVO.match(m) else ""
            if motivo == "desactivada":
                texto = "La comida está desactivada."
            elif motivo:
                legible = texto_limpio(nc.motivo_legible(motivo), 80)
                texto = "Ahora no puedo comer" + (f": {legible}." if legible else ".")
            else:
                texto = "Ahora no puedo comer."
        return dump({"ok": bool(accion), "accion": accion, "motivo": motivo, "texto": texto,
                     "estado": self._estado_comida()})

    @pyqtSlot(result=bool)
    def comida_guardar(self) -> bool:
        return llamar(self._comida, "guardar") is True

    @pyqtSlot(str, result=bool)
    def comida_evento(self, id_: str) -> bool:
        n = _comida_exacta(id_)
        if n is None:
            return False
        return llamar(self._comida, "acierto_web", n) is True

    @pyqtSlot(str, result=str)
    def comida_config_guardar(self, payload: str) -> str:
        obj = leer_json(payload)
        if not obj or any(k != "activa" for k in obj) or not es_bool(obj.get("activa")):
            return dump({"ok": False, "error": "Ajustes de la comida no válidos.", "estado": self._estado_comida()})
        ok = self._guardar_cambios("comida", {"activa": obj["activa"]})
        llamar(self._comida, "recargar_config")
        estado = self._estado_comida()
        self.comida_cambio.emit(dump(estado))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": estado})

    # ═══ Discord (corte 8) ════════════════════════════════════════════════════
    def _config_discord(self) -> Dict[str, Any]:
        cid = str(self._cfg("discord", "client_id", "") or "").strip()
        url = self._cfg("discord", "boton_url", "")
        return {
            "client_id": cid if ID_DISCORD.match(cid) else "",
            "mostrar_modelo": self._cfg("discord", "mostrar_modelo", False) is True,
            "boton_url": url if url_boton_valida(url) else "",
        }

    def _estado_discord(self) -> Dict[str, Any]:
        d = self._discord
        e = llamar(d, "estado") if d is not None else None
        e = e if isinstance(e, dict) else {}
        activo = (e.get("activo") is True) if "activo" in e else self._cfg("discord", "activo", False) is True
        cfg = self._config_discord()
        cid_crudo = str(self._cfg("discord", "client_id", "") or "").strip()
        conectado = e.get("conectado") is True
        return {
            "activo": activo,
            "conectado": conectado,
            "usuario": texto_limpio(e.get("usuario"), 40) if conectado else "",
            "error": texto_limpio(e.get("error"), 160),
            "client_id_ok": bool(ID_DISCORD.match(cid_crudo)),
            "sin_id": bool(activo and not cid_crudo),
            "publicando": publicacion_segura(e.get("publicando")) if conectado else None,
            "vista_previa": publicacion_segura(e.get("vista_previa")),
            "servicio": d is not None,
            "config": cfg,
        }

    @pyqtSlot(result=str)
    def discord_estado(self) -> str:
        return dump(self._estado_discord())

    @pyqtSlot(result=bool)
    def discord_alternar(self) -> bool:
        if self._discord is not None:
            r = llamar(self._discord, "alternar")
            nuevo = r if isinstance(r, bool) else self._cfg("discord", "activo", False) is True
        else:
            nuevo = not (self._cfg("discord", "activo", False) is True)
            self._cfg_set("discord", "activo", nuevo)
        self.discord_cambio.emit(dump(self._estado_discord()))
        return nuevo

    @pyqtSlot(str, result=str)
    def discord_config_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._estado_discord()})

        if not obj or any(k not in ("activo", "client_id", "mostrar_modelo", "boton_url") for k in obj):
            return falla("Ajustes de Discord no válidos.")
        cambios: Dict[str, Any] = {}
        for k in ("activo", "mostrar_modelo"):
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios[k] = obj[k]
        if "client_id" in obj:
            cid = obj["client_id"]
            if not isinstance(cid, str):
                return falla("El Application ID son solo cifras.")
            cid = cid.strip()
            if cid and not ID_DISCORD.match(cid):
                return falla("El Application ID son de 17 a 20 cifras (Discord Developer Portal → tu app).")
            cambios["client_id"] = cid
        if "boton_url" in obj:
            url = obj["boton_url"]
            if not isinstance(url, str):
                return falla("El enlace del botón no vale.")
            url = url.strip()
            if url and not url_boton_valida(url):
                return falla(f"El enlace del botón tiene que ser https:// (como mucho {MAX_URL} bytes).")
            cambios["boton_url"] = url
        ok = self._guardar_cambios("discord", cambios)
        llamar(self._discord, "recargar_config")
        estado = self._estado_discord()
        self.discord_cambio.emit(dump(estado))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": estado})

    # ═══ Arrancar con Windows (corte 8) ═══════════════════════════════════════
    def _mod_autoinicio(self) -> Any:
        if self._autoinicio is None:
            try:
                from servicios import autoinicio
                self._autoinicio = autoinicio
            except Exception:
                _log.exception("puente vida: servicios.autoinicio")
                return None
        return self._autoinicio

    def _mod_arranque(self) -> Any:
        if self._arranque is None:
            try:
                from nucleo import arranque
                self._arranque = arranque
            except Exception:
                _log.exception("puente vida: nucleo.arranque")
                return None
        return self._arranque

    def _estado_autoinicio(self) -> Dict[str, Any]:
        mod = self._mod_autoinicio()
        modo = str(self._cfg("interfaz", "modo", "web") or "web")
        e = llamar(mod, "estado", modo) if mod is not None else None
        e = e if isinstance(e, dict) else {}
        arr = self._mod_arranque()
        como = llamar(arr, "como", self.config) if arr is not None else None
        retraso = entero(llamar(arr, "retraso_s", self.config)) if arr is not None else None
        if como not in COMOS:
            c = self._cfg("sistema", "autoinicio_como", "bandeja")
            como = c if c in COMOS else "bandeja"
        if retraso is None:
            r = entero(self._cfg("sistema", "autoinicio_retraso_s", 20))
            retraso = r if r is not None and 0 <= r <= 300 else 20
        return {
            "activo": e.get("activo") is True,
            "registrado": e.get("registrado") is True,
            "aprobado": e.get("aprobado") is True,
            "ruta_ok": e.get("ruta_ok") is True,
            "modo_ok": e.get("modo_ok") is True,
            "como": como,
            "retraso_s": max(0, min(300, retraso)),
            "disponible": mod is not None and (self._autoinicio_inyectado or sys.platform == "win32"),
        }

    @pyqtSlot(result=str)
    def autoinicio_estado(self) -> str:
        return dump(self._estado_autoinicio())

    @pyqtSlot(str, result=str)
    def autoinicio_opciones(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._estado_autoinicio()})

        if not obj or any(k not in ("como", "retraso_s") for k in obj):
            return falla("Opciones de arranque no válidas.")
        cambios: Dict[str, Any] = {}
        if "como" in obj:
            if obj["como"] not in COMOS:
                return falla("Al arrancar: en la bandeja, con la asistente en escritorio o con la ventana.")
            cambios["autoinicio_como"] = obj["como"]
        if "retraso_s" in obj:
            r = entero(obj["retraso_s"])
            if r is None or not 0 <= r <= RETRASO_MAX:
                return falla(f"La espera va de 0 a {RETRASO_MAX} segundos.")
            cambios["autoinicio_retraso_s"] = r
        ok = self._guardar_cambios("sistema", cambios)
        estado = self._estado_autoinicio()
        self.autoinicio_cambio.emit(dump(estado))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": estado})


def registrar_puente_vida(canal: Any, config: Any, servicios_c4: Any = None, **kw) -> PuenteVida:
    """Crea `PuenteVida`, lo registra en `canal` (QWebChannel) como «vida» y, si ya hay
    servicios, lo enlaza. Hay que llamarlo antes de que la página cree su QWebChannel
    (antes de setUrl). Queda como hijo del canal. `kw` (keyword-only, para los tests):
    `autoinicio` y `arranque` (módulos o dobles con la misma API)."""
    padre = canal if isinstance(canal, QObject) else None
    puente = PuenteVida(config=config, parent=padre,
                        **{k: kw[k] for k in ("autoinicio", "arranque") if k in kw})
    reg = getattr(canal, "registerObject", None)
    if callable(reg):
        try:
            reg("vida", puente)
            puente._canal = canal
        except Exception:
            _log.exception("puente vida: no pude registrar «vida» en el canal")
    if servicios_c4 is not None:
        puente.enlazar(servicios_c4)
    return puente


__all__ = ("PuenteVida", "registrar_puente_vida", "controladores_vida", "publicacion_segura",
           "url_boton_valida", "estados_discord", "SITIOS", "COMOS", "OFFSET_MAX", "RETRASO_MAX")
