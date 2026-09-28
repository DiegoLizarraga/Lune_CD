"""
ui/puente_escenario.py — objeto `escenario` del QWebChannel (window.luneEscenario),
cortes 9 y 10: el reproductor de bailes MMD/VRMA y Minecraft.

Lo usa la piel web normal: extra/bailes_mmd.jsx (vista «bailes»: BailesPanel, y la tarjeta
BailesCard de Ajustes) y extra/minecraft.jsx (vista «minecraft»: MinecraftPanel, y la
tarjeta MinecraftCard).

Se registra SIEMPRE en `VentanaWeb.__init__`, antes de `setUrl` (el JS solo ve lo que
estaba registrado al crear su QWebChannel), y recibe los controladores tarde:
`enlazar(servicios_c4)` toma `ServiciosCorte4.escenario` (ui/montaje_escenario.
ServiciosEscenario), un ServiciosEscenario directamente o, si falta alguno, el registrado
en el escritorio («mmd», «minecraft»). Sin ellos, cada ranura devuelve un estado por
defecto y lo que es solo config (baile.*, minecraft.* y la sección minecraft de
datos.json) se lee y se guarda igual. `enlazar` se apunta en `servicios._deshacer`: al
desmontar (cambio de interfaz en caliente, salir) suelta los controladores antes de que
ServiciosEscenario los borre.

SEGURIDAD. Todo lo que entra de la página se valida (JSON ≤ 16 KB, claves conocidas, tipos
estrictos, enums y rangos). La página NUNCA manda rutas: los bailes se nombran por su id de
la biblioteca (12 hex), importar abre el diálogo de archivos de Qt (lo elige la persona) y la
ruta del latest.log solo puede ser «automática» o una de las que encuentra «Detectar»
(minecraft_log.rutas_candidatas). Todo lo que sale hacia ella se normaliza (lista blanca de
campos, textos sin controles y recortados); el chat de Minecraft NO es confiable: sale solo
como texto (la página lo pinta como texto, nunca como HTML).

Ranuras (JS: el resultado llega por callback, `luneEscenario.x(args…, cb)`):
  Bailes (ControlMMD, ui/mmd_qt.py)
    bailes_lista(texto) → str         {bailes: [{id, titulo, tipo, autor_cancion, autor_mmd, duracion, audio,
                                       favorito, desactivado, problema, aviso, offset_ms, brazo_a_grados,
                                       en_el_sitio, bpm}], servicio}          texto ≤ 60 (se recorta)
                                      de la FOTO de la biblioteca: no escanea ni espera a un
                                      escaneo o a un importar (lo nuevo llega por bailes_cambio)
    bailes_refrescar() → bool         vuelve a mirar la carpeta (en un hilo) → bailes_cambio
    mmd_estado_json() → str           {fase, id, titulo, autor, autor_mmd, t, total, modo, al_terminar, volumen,
                                       en_el_sitio, error, analizando, pausado, cedida, pendiente, modo_mascota,
                                       sin_esqueleto, importando, servicio}
    mmd_reproducir(id) → str          {ok, texto, estado}     id: 12 hex, o "" = seguir / el último / el primero
    mmd_pausa() → str                 {ok, estado}            alterna (D5: al reposo y sigue desde el mismo punto)
    mmd_parar() → str                 {ok, estado}
    mmd_siguiente() / mmd_anterior() → str   {ok, texto, estado}
    mmd_config_guardar(json) → str    {ok, error, estado}     {volumen?: 0–1, al_terminar?: parar|siguiente|repetir|
                                                               aleatorio, en_el_sitio?: bool}
    baile_meta_guardar(id, json) → str {ok, texto}            {titulo?, autor_cancion?, autor_mmd? (≤ 80),
                                       offset_ms?: −500..500 (entero), brazo_a_grados?: 25–45,
                                       en_el_sitio?: bool|null, bpm?: 40–240|null}
    baile_favorito(id, bool) / baile_desactivar(id, bool) → bool
    bailes_importar() → bool          abre el diálogo de archivos (diferido) → mmd_importado
    baile_quitar(id) → str            {ok, texto}             lo mueve a bailes/.quitados (reversible)
    bailes_abrir_carpeta() → bool
  Minecraft (ControlMinecraft, ui/minecraft_qt.py; datos.json con nucleo.datos.guardar_minecraft)
    mc_estado_json() → str            {reaccionar, log: {ruta, activo, yo}, bot: {instalado, instalando, conectando,
                                       conectado, servidor, nick, vida, hambre, dia, lluvia, error},
                                       requisitos: {node, node_ok, npm} (None = comprobando), juego, pensando,
                                       servicio}
    mc_config() → str                 {config: {reaccionar, ruta_log, voz_reacciones, auto_con_juego, decir_en_juego,
                                       resumen_al_salir, pensar_en_juego, reaccionar_otros},
                                       bot: {host, port, version, usuario, dueno, pensar_cada_s, defender,
                                       solo_dueno, estilo_frases}, error}
    mc_config_guardar(json) → str     {ok, error, config}     claves de config (bool; ruta_log "" o una detectada)
                                       y del bot (tipos estrictos; el resto lo valida guardar_minecraft)
    mc_bot_instalar() → str           {ok, texto, estado}     D3: solo este botón instala (~400 MB)
    mc_bot_conectar() → str           {ok, texto, estado}
    mc_bot_desconectar() → bool
    mc_orden(texto) → str             {ok, texto}             ≤ 200; la lista blanca la aplica ControlMinecraft
    mc_decir(texto) → str             {ok, texto}             ≤ 100
    mc_log_detectar() → str           {ok, rutas: [..≤64], sugerida, actual}   (solo stat de archivos)
    mc_eventos() → str                [{tipo, texto, estado, fuente, t, entregado}] (≤ 50)
Señales:
    bailes_cambio(str)   {bailes, servicio}      mmd_estado(str)   JSON de mmd_estado_json()
    mmd_importado(str)   {ok, texto, id}         vista_pedida(str) 'bailes' | 'minecraft'
    mc_estado(str)       JSON de mc_estado_json()
    mc_evento(str)       {tipo, texto, estado, fuente, t, entregado}
    mc_chat(str)         {de, texto, t}  (NO CONFIABLE: solo texto)
    mc_log(str)          una línea del bot (≤ 300)

    puente = registrar_puente_escenario(canal, config, servicios_c4=None)
    puente.enlazar(servicios_c4)      # en _montar_servicios_c4
    puente.cerrar()                   # en _liberar_todo
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from ui.puentes_ocio import PuenteOcioBase, dump, entero, es_bool, leer_json, llamar, numero, texto_limpio

_log = logging.getLogger("lune.puente_escenario")

# ── Bailes ───────────────────────────────────────────────────────────────────────
FASES_MMD = ("parado", "cargando", "listo", "sonando", "pausado", "saliendo", "error")
MODOS_MMD = ("vrm", "animado", "sprites")
TIPOS_BAILE = ("vmd", "vrma")
AL_TERMINAR = ("parar", "siguiente", "repetir", "aleatorio")
AL_TERMINAR_DEFECTO = "parar"
VISTAS = ("bailes", "minecraft")
ID_BAILE = re.compile(r"^[0-9a-f]{12}$")
T_MAX = 7200.0
MAX_BAILES = 500
MAX_BUSQUEDA = 60
MAX_TITULO = 80
META_TEXTOS = ("titulo", "autor_cancion", "autor_mmd")
META_CLAVES = META_TEXTOS + ("offset_ms", "brazo_a_grados", "en_el_sitio", "bpm")
SIN_SERVICIO_BAILES = "Los bailes necesitan la app abierta (servicios de escritorio)."

# ── Minecraft ────────────────────────────────────────────────────────────────────
CONFIG_MC_BOOL = ("reaccionar", "voz_reacciones", "auto_con_juego", "decir_en_juego", "resumen_al_salir",
                  "pensar_en_juego", "reaccionar_otros")
CONFIG_MC_DEFECTO: Dict[str, Any] = {
    "reaccionar": False, "ruta_log": "", "voz_reacciones": False, "auto_con_juego": True,
    "decir_en_juego": True, "resumen_al_salir": True, "pensar_en_juego": False, "reaccionar_otros": False,
}
BOT_CLAVES = ("host", "port", "version", "usuario", "dueno", "pensar_cada_s", "defender", "solo_dueno",
              "estilo_frases")
BOT_DEFECTO: Dict[str, Any] = {
    "host": "localhost", "port": 25565, "version": "", "usuario": "", "dueno": "", "pensar_cada_s": 45,
    "defender": True, "solo_dueno": True, "estilo_frases": "personaje",
}
ESTILOS = ("personaje", "sobrio")
NICK = re.compile(r"^[A-Za-z0-9_]{3,16}$")
VERSION_NODE = re.compile(r"^v?\d{1,3}\.\d{1,4}\.\d{1,5}$")
_PALABRA = re.compile(r"^[a-z_]{1,24}$")
FUENTES = ("log", "bot", "lune", "usuario", "modelo")
MAX_EVENTOS = 50
MAX_RUTA = 1024
MAX_RUTAS = 64
MAX_ORDEN = 200
MAX_DECIR = 100
SIN_SERVICIO_MC = "Minecraft necesita la app abierta (servicios de escritorio)."


# ── Normalización (pura; la usa también el panel nativo) ─────────────────────────

def _finito(v: Any, lo: float, hi: float) -> Optional[float]:
    f = numero(v)
    return f if f is not None and lo <= f <= hi else None


def _bool_o_none(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


def id_baile(v: Any) -> bool:
    return isinstance(v, str) and bool(ID_BAILE.match(v))


def baile_para_pagina(d: Any) -> Optional[Dict[str, Any]]:
    """Un baile de ControlMMD.lista() (nucleo/bailes.baile_a_dict) → lo que ve la página, o None."""
    if not isinstance(d, dict) or not id_baile(d.get("id")):
        return None
    dur = _finito(d.get("duracion"), 0.0, T_MAX)
    off = entero(d.get("offset_ms"))
    brazo = _finito(d.get("brazo_a_grados"), 25.0, 45.0)
    bpm = _finito(d.get("bpm"), 40.0, 240.0)
    return {
        "id": d["id"],
        "titulo": texto_limpio(d.get("titulo"), MAX_TITULO) or d["id"],
        "tipo": d.get("tipo") if d.get("tipo") in TIPOS_BAILE else "",
        "autor_cancion": texto_limpio(d.get("autor_cancion"), MAX_TITULO),
        "autor_mmd": texto_limpio(d.get("autor_mmd"), MAX_TITULO),
        "duracion": round(dur, 1) if dur is not None else None,
        "audio": d.get("audio") is True,
        "favorito": d.get("favorito") is True,
        "desactivado": d.get("desactivado") is True,
        "problema": texto_limpio(d.get("problema"), 200),
        "aviso": texto_limpio(d.get("aviso"), 200),
        "offset_ms": off if off is not None and -500 <= off <= 500 else 0,
        "brazo_a_grados": round(brazo, 1) if brazo is not None else 35.0,
        "en_el_sitio": _bool_o_none(d.get("en_el_sitio")),
        "bpm": round(bpm, 2) if bpm is not None else None,
    }


def lista_bailes(lista: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    vistos = set()
    for d in lista if isinstance(lista, list) else []:
        b = baile_para_pagina(d)
        if b is None or b["id"] in vistos:
            continue
        vistos.add(b["id"])
        out.append(b)
        if len(out) >= MAX_BAILES:
            break
    return out


def estado_mmd(e: Any, *, al_terminar: str = AL_TERMINAR_DEFECTO, volumen: float = 0.25,
               en_el_sitio: bool = True, servicio: bool = False) -> Dict[str, Any]:
    """ControlMMD.estado() → lo que ve la página (los defectos salen de la config)."""
    e = e if isinstance(e, dict) else {}
    t = _finito(e.get("t"), 0.0, T_MAX)
    total = _finito(e.get("total"), 0.0, T_MAX)
    vol = _finito(e.get("volumen"), 0.0, 1.0)
    modo_m = e.get("modo_mascota") if e.get("modo_mascota") in MODOS_MMD else ""
    return {
        "fase": e.get("fase") if e.get("fase") in FASES_MMD else "parado",
        "id": e.get("id") if id_baile(e.get("id")) else "",
        "titulo": texto_limpio(e.get("titulo"), MAX_TITULO),
        "autor": texto_limpio(e.get("autor"), MAX_TITULO),
        "autor_mmd": texto_limpio(e.get("autor_mmd"), MAX_TITULO),
        "t": round(t, 1) if t is not None else 0.0,
        "total": round(total, 1) if total is not None else 0.0,
        "modo": e.get("modo") if e.get("modo") in MODOS_MMD else "",
        "al_terminar": e.get("al_terminar") if e.get("al_terminar") in AL_TERMINAR else al_terminar,
        "volumen": round(vol if vol is not None else volumen, 3),
        "en_el_sitio": e.get("en_el_sitio") if isinstance(e.get("en_el_sitio"), bool) else en_el_sitio,
        "error": texto_limpio(e.get("error"), 300),
        "analizando": e.get("analizando") is True,
        "pausado": e.get("pausado") is True,
        "cedida": e.get("cedida") is True,
        "pendiente": e.get("pendiente") is True,
        "modo_mascota": modo_m,
        "sin_esqueleto": e.get("sin_esqueleto") is True or modo_m in ("animado", "sprites"),
        "importando": e.get("importando") is True,
        "servicio": servicio,
    }


def _nick(v: Any) -> str:
    return v if isinstance(v, str) and NICK.match(v) else ""


def _0_40(v: Any) -> Optional[int]:
    n = entero(v)
    return n if n is not None and 0 <= n <= 40 else None


def estado_mc(e: Any, *, reaccionar: bool = False, servicio: bool = False) -> Dict[str, Any]:
    """ControlMinecraft.estado() → lo que ve la página."""
    e = e if isinstance(e, dict) else {}
    log = e.get("log") if isinstance(e.get("log"), dict) else {}
    bot = e.get("bot") if isinstance(e.get("bot"), dict) else {}
    req = e.get("requisitos") if isinstance(e.get("requisitos"), dict) else {}
    node = req.get("node")
    activo = log.get("activo") is True
    return {
        "reaccionar": e.get("reaccionar") is True if "reaccionar" in e else reaccionar,
        "log": {"ruta": texto_limpio(log.get("ruta"), 300) if activo else "", "activo": activo,
                "yo": _nick(log.get("yo")) if activo else ""},
        "bot": {
            "instalado": bot.get("instalado") is True,
            "instalando": bot.get("instalando") is True,
            "conectando": bot.get("conectando") is True,
            "conectado": bot.get("conectado") is True,
            "servidor": texto_limpio(bot.get("servidor"), 260),
            "nick": _nick(bot.get("nick")),
            "vida": _0_40(bot.get("vida")),
            "hambre": _0_40(bot.get("hambre")),
            "dia": _bool_o_none(bot.get("dia")),
            "lluvia": _bool_o_none(bot.get("lluvia")),
            "error": texto_limpio(bot.get("error"), 300),
        },
        # None = aún comprobándolo (ControlMinecraft lo mira en un hilo).
        "requisitos": {"node": node if isinstance(node, str) and VERSION_NODE.match(node) else None,
                       "node_ok": _bool_o_none(req.get("node_ok")), "npm": _bool_o_none(req.get("npm"))},
        "juego": e.get("juego") is True,
        "pensando": e.get("pensando") is True,
        "servicio": servicio,
    }


def evento_mc(d: Any) -> Optional[Dict[str, Any]]:
    """Un evento de ControlMinecraft (lo que Lune dijo o apuntó) → página, o None."""
    if not isinstance(d, dict) or not isinstance(d.get("tipo"), str) or not _PALABRA.match(d["tipo"]):
        return None
    t = _finito(d.get("t"), 0.0, 1e11)
    estado = d.get("estado") if isinstance(d.get("estado"), str) and _PALABRA.match(d.get("estado") or "") else ""
    return {
        "tipo": d["tipo"],
        "texto": texto_limpio(d.get("texto"), 400),
        "estado": estado,
        "fuente": d.get("fuente") if d.get("fuente") in FUENTES else "",
        "t": round(t, 3) if t is not None else 0.0,
        "entregado": d.get("entregado") is True,
    }


def chat_mc(d: Any) -> Optional[Dict[str, Any]]:
    """Chat del juego (NO CONFIABLE) → {de, texto, t} solo si el nick es válido y hay texto."""
    if not isinstance(d, dict):
        return None
    de, texto = _nick(d.get("de")), texto_limpio(d.get("texto"), 256)
    if not de or not texto:
        return None
    t = _finito(d.get("t"), 0.0, 1e11)
    return {"de": de, "texto": texto, "t": round(t, 3) if t is not None else 0.0}


def controladores_escenario(servicios: Any) -> Dict[str, Any]:
    """{mmd, minecraft} de lo que se le dé a `enlazar`:
      · ServiciosCorte4 con `.escenario` (ServiciosEscenario de montar_escenario);
      · un ServiciosEscenario directamente (con .mmd/.minecraft);
      · si falta alguno, el registrado en el escritorio (`escritorio.obtener(nombre)`).
    Lo que no esté es None."""
    out: Dict[str, Any] = {"mmd": None, "minecraft": None}
    if servicios is None:
        return out
    esc = getattr(servicios, "escenario", None)
    base = esc if esc is not None else servicios
    for n in out:
        out[n] = getattr(base, n, None)
    escritorio = getattr(servicios, "escritorio", None)
    obtener = getattr(escritorio, "obtener", None) if escritorio is not None else None
    if callable(obtener):
        for n in out:
            if out[n] is None:
                try:
                    out[n] = obtener(n)
                except Exception:
                    out[n] = None
    return out


def _tupla_ok(r: Any, defecto: str = "") -> Tuple[bool, str]:
    if isinstance(r, tuple) and len(r) == 2:
        return r[0] is True, texto_limpio(r[1], 300)
    return (r is True), defecto


class PuenteEscenario(PuenteOcioBase):
    """Objeto `escenario` del QWebChannel (window.luneEscenario)."""

    NOMBRE = "puente_escenario"

    bailes_cambio = pyqtSignal(str)
    mmd_estado = pyqtSignal(str)
    mmd_importado = pyqtSignal(str)
    vista_pedida = pyqtSignal(str)
    mc_estado = pyqtSignal(str)
    mc_evento = pyqtSignal(str)
    mc_chat = pyqtSignal(str)
    mc_log = pyqtSignal(str)

    def __init__(self, config: Any = None, *, datos: Any = None, rutas_log: Optional[Callable[[], List[Any]]] = None,
                 ventana: Any = None, diferir: Optional[Callable[[Callable[[], None]], None]] = None,
                 parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._mmd: Any = None
        self._mc: Any = None
        self._servicios: Any = None
        self._enganchados: List[Any] = []
        self._datos = datos
        self._rutas_log = rutas_log
        self._ventana = ventana
        self._diferir = diferir or self._diferir_hijo
        self._dialogo_abierto = False

    def _diferir_hijo(self, fn: Callable[[], None]) -> None:
        """`fn` en la siguiente vuelta del bucle con un QTimer HIJO (no singleShot con un cierre
        sobre el puente): si el puente se borra antes (salir, cambio de interfaz), el
        temporizador se va con él y `fn` no llega a correr."""
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(fn)
        t.timeout.connect(t.deleteLater)
        t.start(0)

    # ── Servicios ──────────────────────────────────────────────────────────────
    @property
    def mmd(self) -> Any:
        return self._mmd

    @property
    def minecraft(self) -> Any:
        return self._mc

    def enlazar(self, servicios: Any = None) -> None:
        """Da al puente los controladores de los cortes 9/10 (o los suelta con None).

        Acepta ServiciosCorte4 (usa su `.escenario`), un ServiciosEscenario o None. Reconecta
        las señales y, si algo cambió, manda el estado nuevo a la página."""
        if self._cerrado:
            servicios = None
        c = controladores_escenario(servicios)
        antes = (self._mmd, self._mc)
        self._desconectar_todo()
        self._servicios = servicios
        self._mmd, self._mc = c["mmd"], c["minecraft"]
        self._conectar(self._mmd, "estado_cambio", self._on_mmd_estado)
        self._conectar(self._mmd, "biblioteca_cambio", self._on_bailes)
        self._conectar(self._mmd, "importado", self._on_importado)
        self._conectar(self._mmd, "vista_pedida", self._on_vista)
        self._conectar(self._mc, "estado_cambio", self._on_mc_estado)
        self._conectar(self._mc, "evento", self._on_mc_evento)
        self._conectar(self._mc, "chat", self._on_mc_chat)
        self._conectar(self._mc, "log_bot", self._on_mc_log)
        if self._cerrado:
            return
        if antes != (self._mmd, self._mc):
            self.mmd_estado.emit(dump(self._estado_mmd()))
            self.mc_estado.emit(dump(self._estado_mc()))
        deshacer = getattr(servicios, "_deshacer", None) if servicios is not None else None
        if isinstance(deshacer, list) and not any(s is servicios for s in self._enganchados):
            self._enganchados.append(servicios)

            def soltar(s=servicios) -> None:
                if self._servicios is s:
                    self.enlazar(None)
            deshacer.append(soltar)

    def cerrar(self) -> None:
        """Suelta controladores, señales y el registro en el canal. Idempotente."""
        self._mmd = self._mc = None
        self._servicios = None
        self._enganchados.clear()
        super().cerrar()

    # ── Señales de los controladores ───────────────────────────────────────────
    @staticmethod
    def _obj(payload: Any, tipo: type = dict) -> Any:
        """JSON de un CONTROLADOR (Python, no la página): hasta 4 MB (la biblioteca entera) y
        sin rechazar NaN/Infinity aquí; la normalización descarta lo que no sea finito."""
        if isinstance(payload, str):
            return _leer_controlador(payload, tipo)
        return payload if isinstance(payload, tipo) else None

    def _on_mmd_estado(self, *_: Any) -> None:
        self.mmd_estado.emit(dump(self._estado_mmd()))

    def _on_bailes(self, payload: Any = None) -> None:
        lista = self._obj(payload, list)
        self.bailes_cambio.emit(dump({"bailes": lista_bailes(lista), "servicio": self._mmd is not None}))

    def _on_importado(self, payload: Any = None) -> None:
        o = self._obj(payload)
        if not isinstance(o, dict):
            return
        id_ = o.get("id") if id_baile(o.get("id")) else None
        self.mmd_importado.emit(dump({"ok": o.get("ok") is True, "texto": texto_limpio(o.get("texto"), 300),
                                      "id": id_}))

    def _on_vista(self, vista: Any = None) -> None:
        if isinstance(vista, str) and vista in VISTAS:
            self.vista_pedida.emit(vista)

    def _on_mc_estado(self, *_: Any) -> None:
        self.mc_estado.emit(dump(self._estado_mc()))

    def _on_mc_evento(self, payload: Any = None) -> None:
        e = evento_mc(self._obj(payload))
        if e is not None:
            self.mc_evento.emit(dump(e))

    def _on_mc_chat(self, payload: Any = None) -> None:
        c = chat_mc(self._obj(payload))
        if c is not None:
            self.mc_chat.emit(dump(c))

    def _on_mc_log(self, linea: Any = None) -> None:
        t = texto_limpio(linea, 300)
        if t:
            self.mc_log.emit(t)

    # ═══ Bailes (corte 9) ═════════════════════════════════════════════════════
    def _cfg_baile(self) -> Dict[str, Any]:
        al = self._cfg("baile", "al_terminar", AL_TERMINAR_DEFECTO)
        vol = _finito(self._cfg("baile", "volumen", 0.25), 0.0, 1.0)
        return {"al_terminar": al if al in AL_TERMINAR else AL_TERMINAR_DEFECTO,
                "volumen": vol if vol is not None else 0.25,
                "en_el_sitio": self._cfg("baile", "en_el_sitio", True) is not False}

    def _estado_mmd(self) -> Dict[str, Any]:
        e = llamar(self._mmd, "estado") if self._mmd is not None else None
        return estado_mmd(e, servicio=self._mmd is not None, **self._cfg_baile())

    def _sin_mmd(self, **extra: Any) -> str:
        return dump({"ok": False, "texto": SIN_SERVICIO_BAILES, **extra})

    @pyqtSlot(str, result=str)
    def bailes_lista(self, texto: str) -> str:
        q = texto_limpio(texto, MAX_BUSQUEDA) if isinstance(texto, str) else ""
        if self._mmd is None:
            return dump({"bailes": [], "servicio": False})
        return dump({"bailes": lista_bailes(llamar(self._mmd, "lista", q)), "servicio": True})

    @pyqtSlot(result=bool)
    def bailes_refrescar(self) -> bool:
        if self._mmd is None:
            return False
        llamar(self._mmd, "refrescar")
        return True

    @pyqtSlot(result=str)
    def mmd_estado_json(self) -> str:
        return dump(self._estado_mmd())

    @pyqtSlot(str, result=str)
    def mmd_reproducir(self, id_: str) -> str:
        if not isinstance(id_, str) or (id_ and not id_baile(id_)):
            return dump({"ok": False, "texto": "Ese baile no existe.", "estado": self._estado_mmd()})
        if self._mmd is None:
            return self._sin_mmd(estado=self._estado_mmd())
        ok, texto = _tupla_ok(llamar(self._mmd, "reproducir", id_ or None, origen="usuario"), "No pude bailarlo.")
        return dump({"ok": ok, "texto": texto, "estado": self._estado_mmd()})

    @pyqtSlot(result=str)
    def mmd_pausa(self) -> str:
        ok = llamar(self._mmd, "pausa") is True if self._mmd is not None else False
        return dump({"ok": ok, "estado": self._estado_mmd()})

    @pyqtSlot(result=str)
    def mmd_parar(self) -> str:
        ok = llamar(self._mmd, "parar") is True if self._mmd is not None else False
        return dump({"ok": ok, "estado": self._estado_mmd()})

    def _paso(self, metodo: str) -> str:
        if self._mmd is None:
            return self._sin_mmd(estado=self._estado_mmd())
        ok, texto = _tupla_ok(llamar(self._mmd, metodo), "No hay más bailes.")
        return dump({"ok": ok, "texto": texto, "estado": self._estado_mmd()})

    @pyqtSlot(result=str)
    def mmd_siguiente(self) -> str:
        return self._paso("siguiente")

    @pyqtSlot(result=str)
    def mmd_anterior(self) -> str:
        return self._paso("anterior")

    @pyqtSlot(str, result=str)
    def mmd_config_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._estado_mmd()})

        if not obj or any(k not in ("volumen", "al_terminar", "en_el_sitio") for k in obj):
            return falla("Ajustes de los bailes no válidos.")
        cambios: Dict[str, Any] = {}
        if "volumen" in obj:
            v = _finito(obj["volumen"], 0.0, 1.0)
            if v is None:
                return falla("El volumen va de 0 a 1.")
            cambios["volumen"] = round(v, 3)
        if "al_terminar" in obj:
            if obj["al_terminar"] not in AL_TERMINAR:
                return falla("Al terminar: parar, siguiente, repetir o aleatorio.")
            cambios["al_terminar"] = obj["al_terminar"]
        if "en_el_sitio" in obj:
            if not es_bool(obj["en_el_sitio"]):
                return falla("«En el sitio» tiene que ser sí o no.")
            cambios["en_el_sitio"] = obj["en_el_sitio"]
        m = self._mmd
        if m is not None:
            if "volumen" in cambios:
                llamar(m, "volumen", cambios["volumen"])
            if "al_terminar" in cambios:
                llamar(m, "set_al_terminar", cambios["al_terminar"])
            if "en_el_sitio" in cambios:
                llamar(m, "set_en_el_sitio", cambios["en_el_sitio"])
            ok = all(self._cfg("baile", k, None) == v for k, v in cambios.items())
            if not ok:                                    # un controlador viejo que no guardó
                ok = self._guardar_cambios("baile", cambios)
        else:
            ok = self._guardar_cambios("baile", cambios)
        estado = self._estado_mmd()
        self.mmd_estado.emit(dump(estado))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": estado})

    @pyqtSlot(str, str, result=str)
    def baile_meta_guardar(self, id_: str, payload: str) -> str:
        if not id_baile(id_):
            return dump({"ok": False, "texto": "Ese baile no existe."})
        obj = leer_json(payload)
        if not obj or any(k not in META_CLAVES for k in obj):
            return dump({"ok": False, "texto": "Datos del baile no válidos."})
        cambios: Dict[str, Any] = {}
        for k in META_TEXTOS:
            if k in obj:
                if not isinstance(obj[k], str) or len(obj[k]) > 4 * MAX_TITULO:
                    return dump({"ok": False, "texto": f"«{k}» tiene que ser un texto corto."})
                cambios[k] = texto_limpio(obj[k], MAX_TITULO)
        if "offset_ms" in obj:
            off = entero(obj["offset_ms"])
            if off is None or not -500 <= off <= 500:
                return dump({"ok": False, "texto": "La sincronía va de −500 a 500 ms."})
            cambios["offset_ms"] = off
        if "brazo_a_grados" in obj:
            b = _finito(obj["brazo_a_grados"], 25.0, 45.0)
            if b is None:
                return dump({"ok": False, "texto": "El ángulo de los brazos va de 25 a 45°."})
            cambios["brazo_a_grados"] = round(b, 1)
        if "en_el_sitio" in obj:
            if obj["en_el_sitio"] is not None and not es_bool(obj["en_el_sitio"]):
                return dump({"ok": False, "texto": "«En el sitio» tiene que ser sí, no o como en Ajustes."})
            cambios["en_el_sitio"] = obj["en_el_sitio"]
        if "bpm" in obj:
            if obj["bpm"] is None:
                cambios["bpm"] = None
            else:
                bpm = _finito(obj["bpm"], 40.0, 240.0)
                if bpm is None:
                    return dump({"ok": False, "texto": "El pulso va de 40 a 240 BPM (o vacío)."})
                cambios["bpm"] = round(bpm, 2)
        if self._mmd is None:
            return self._sin_mmd()
        ok, texto = _tupla_ok(llamar(self._mmd, "guardar_meta", id_, cambios), "No pude guardarlo.")
        return dump({"ok": ok, "texto": texto})

    def _marca(self, metodo: str, id_: Any, on: Any) -> bool:
        if not id_baile(id_) or not es_bool(on) or self._mmd is None:
            return False
        return llamar(self._mmd, metodo, id_, on) is True

    @pyqtSlot(str, bool, result=bool)
    def baile_favorito(self, id_: str, on: bool) -> bool:
        return self._marca("favorito", id_, on)

    @pyqtSlot(str, bool, result=bool)
    def baile_desactivar(self, id_: str, on: bool) -> bool:
        return self._marca("desactivar", id_, on)

    @pyqtSlot(result=bool)
    def bailes_importar(self) -> bool:
        """El diálogo de archivos de Qt (lo elige la persona; la página no manda rutas). Se abre
        diferido para que la ranura vuelva ya; el resultado llega por `mmd_importado`."""
        m = self._mmd
        if m is None or self._dialogo_abierto:
            return False
        self._dialogo_abierto = True

        def abrir() -> None:
            try:
                v = self._ventana() if callable(self._ventana) else self._ventana
                if self._mmd is m:
                    llamar(m, "importar_dialogo", v)
            finally:
                self._dialogo_abierto = False
        try:
            self._diferir(abrir)
        except Exception:
            self._dialogo_abierto = False
            _log.exception("puente escenario: no pude abrir el diálogo de importar")
            return False
        return True

    @pyqtSlot(str, result=str)
    def baile_quitar(self, id_: str) -> str:
        if not id_baile(id_):
            return dump({"ok": False, "texto": "Ese baile no existe."})
        if self._mmd is None:
            return self._sin_mmd()
        ok, texto = _tupla_ok(llamar(self._mmd, "quitar", id_), "No pude quitarlo.")
        return dump({"ok": ok, "texto": texto})

    @pyqtSlot(result=bool)
    def bailes_abrir_carpeta(self) -> bool:
        return llamar(self._mmd, "abrir_carpeta") is True if self._mmd is not None else False

    # ═══ Minecraft (corte 10) ═════════════════════════════════════════════════
    def _estado_mc(self) -> Dict[str, Any]:
        e = llamar(self._mc, "estado") if self._mc is not None else None
        return estado_mc(e, reaccionar=self._cfg("minecraft", "reaccionar", False) is True,
                         servicio=self._mc is not None)

    def _mod_datos(self) -> Any:
        if self._datos is None:
            try:
                from nucleo import datos
                self._datos = datos
            except Exception:
                _log.exception("puente escenario: nucleo.datos")
                return None
        return self._datos

    def _config_mc(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k in CONFIG_MC_BOOL:
            v = self._cfg("minecraft", k, CONFIG_MC_DEFECTO[k])
            out[k] = v if isinstance(v, bool) else CONFIG_MC_DEFECTO[k]
        ruta = self._cfg("minecraft", "ruta_log", "")
        out["ruta_log"] = ruta if isinstance(ruta, str) and len(ruta) <= MAX_RUTA else ""
        return out

    def _bot_mc(self) -> Tuple[Dict[str, Any], str]:
        mod = self._mod_datos()
        crudo = None
        try:
            crudo = mod.minecraft() if mod is not None else None
        except Exception:
            _log.exception("puente escenario: leer datos.json (minecraft)")
        if not isinstance(crudo, dict):
            return dict(BOT_DEFECTO), "No pude leer los datos del bot (datos.json)."
        return bot_para_pagina(crudo), ""

    def _config_completa(self) -> Dict[str, Any]:
        bot, error = self._bot_mc()
        return {"config": self._config_mc(), "bot": bot, "error": error}

    @pyqtSlot(result=str)
    def mc_estado_json(self) -> str:
        return dump(self._estado_mc())

    @pyqtSlot(result=str)
    def mc_config(self) -> str:
        return dump(self._config_completa())

    def _rutas(self) -> List[str]:
        f = self._rutas_log
        if f is None:
            try:
                from lune_core.minecraft_log import rutas_candidatas
                f = rutas_candidatas
            except Exception:
                return []
        try:
            rutas = list(f() or [])[:MAX_RUTAS]
        except Exception:
            _log.exception("puente escenario: buscar latest.log")
            return []
        return [str(r) for r in rutas if len(str(r)) <= MAX_RUTA]

    @pyqtSlot(str, result=str)
    def mc_config_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "config": self._config_completa()})

        if not obj or any(k not in CONFIG_MC_BOOL + ("ruta_log",) + BOT_CLAVES for k in obj):
            return falla("Ajustes de Minecraft no válidos.")
        cfg: Dict[str, Any] = {}
        for k in CONFIG_MC_BOOL:
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cfg[k] = obj[k]
        if "ruta_log" in obj:
            r = obj["ruta_log"]
            if not isinstance(r, str) or len(r) > MAX_RUTA:
                return falla("Esa ruta del registro no vale.")
            if r:
                # Nunca una ruta escrita por la página: solo una de las que encuentra «Detectar».
                validas = {x.casefold(): x for x in self._rutas()}
                real = validas.get(r.casefold())
                if real is None or not _ruta_log_valida(real):
                    return falla("Esa ruta no es un latest.log de Minecraft encontrado aquí: usa «Detectar».")
                r = real
            cfg["ruta_log"] = r
        bot: Dict[str, Any] = {}
        for k in BOT_CLAVES:
            if k not in obj:
                continue
            v = obj[k]
            if k in ("port", "pensar_cada_s"):
                n = entero(v)
                if n is None:
                    return falla("El puerto y «pensar cada» son números enteros.")
                bot[k] = n
            elif k in ("defender", "solo_dueno"):
                if not es_bool(v):
                    return falla(f"«{k}» tiene que ser sí o no.")
                bot[k] = v
            elif k == "estilo_frases":
                if v not in ESTILOS:
                    return falla("El estilo de frases es «personaje» o «sobrio».")
                bot[k] = v
            else:
                if not isinstance(v, str) or len(v) > 253:
                    return falla(f"«{k}» tiene que ser un texto.")
                bot[k] = v.strip()
        if bot:
            mod = self._mod_datos()
            f = getattr(mod, "guardar_minecraft", None) if mod is not None else None
            if not callable(f):
                return falla("No puedo guardar los datos del bot en esta versión.")
            try:
                f(bot)
            except ValueError as e:
                return falla(texto_limpio(str(e), 300) or "Datos del bot no válidos.")
            except Exception:
                _log.exception("puente escenario: guardar datos.json (minecraft)")
                return falla("No pude guardar los datos del bot (datos.json).")
        ok = self._guardar_cambios("minecraft", cfg) if cfg else True
        llamar(self._mc, "recargar_config")
        self.mc_estado.emit(dump(self._estado_mc()))
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "config": self._config_completa()})

    @pyqtSlot(result=str)
    def mc_bot_instalar(self) -> str:
        """D3: la instalación (~400 MB) solo la dispara este botón; nunca una herramienta."""
        if self._mc is None:
            return dump({"ok": False, "texto": SIN_SERVICIO_MC, "estado": self._estado_mc()})
        e = self._estado_mc()
        if e["bot"]["instalando"]:
            return dump({"ok": False, "texto": "Ya se está instalando.", "estado": e})
        llamar(self._mc, "instalar_bot")
        return dump({"ok": True, "texto": "Instalando el bot (~400 MB). Tarda unos minutos.",
                     "estado": self._estado_mc()})

    @pyqtSlot(result=str)
    def mc_bot_conectar(self) -> str:
        if self._mc is None:
            return dump({"ok": False, "texto": SIN_SERVICIO_MC, "estado": self._estado_mc()})
        ok, texto = _tupla_ok(llamar(self._mc, "conectar_bot"), "No pude conectar el bot.")
        return dump({"ok": ok, "texto": texto, "estado": self._estado_mc()})

    @pyqtSlot(result=bool)
    def mc_bot_desconectar(self) -> bool:
        return llamar(self._mc, "desconectar_bot") is True if self._mc is not None else False

    @pyqtSlot(str, result=str)
    def mc_orden(self, texto: str) -> str:
        if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_ORDEN:
            return dump({"ok": False, "texto": "Escribe una orden corta (sígueme, ven, para…)."})
        if self._mc is None:
            return dump({"ok": False, "texto": SIN_SERVICIO_MC})
        ok, t = _tupla_ok(llamar(self._mc, "orden", texto, origen="usuario"), "No pude mandarle la orden.")
        return dump({"ok": ok, "texto": t})

    @pyqtSlot(str, result=str)
    def mc_decir(self, texto: str) -> str:
        if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_DECIR:
            return dump({"ok": False, "texto": f"Escribe algo (como mucho {MAX_DECIR} letras)."})
        if self._mc is None:
            return dump({"ok": False, "texto": SIN_SERVICIO_MC})
        ok, t = _tupla_ok(llamar(self._mc, "decir", texto), "No pude mandárselo al bot.")
        return dump({"ok": ok, "texto": t})

    @pyqtSlot(result=str)
    def mc_log_detectar(self) -> str:
        """Los latest.log de los sitios de siempre (.minecraft, Prism/MultiMC, CurseForge…),
        con el más reciente como sugerencia. Solo mira fechas de archivos."""
        rutas = self._rutas()
        sugerida = ""
        if rutas:
            try:
                from lune_core.minecraft_log import elegir_log
                p = elegir_log("", rutas, reciente_s=None)
                sugerida = str(p) if p is not None else ""
            except Exception:
                _log.exception("puente escenario: elegir latest.log")
        if sugerida not in rutas:
            sugerida = rutas[0] if rutas else ""
        actual = self._config_mc()["ruta_log"]
        return dump({"ok": bool(rutas), "rutas": rutas, "sugerida": sugerida, "actual": actual})

    @pyqtSlot(result=str)
    def mc_eventos(self) -> str:
        lista = llamar(self._mc, "eventos_recientes", MAX_EVENTOS) if self._mc is not None else None
        out = [e for e in (evento_mc(d) for d in (lista if isinstance(lista, list) else [])) if e is not None]
        return dump(out[-MAX_EVENTOS:])


def bot_para_pagina(crudo: Any) -> Dict[str, Any]:
    """nucleo.datos.minecraft() → solo las claves del bot, con tipos seguros (sin `visor`)."""
    c = crudo if isinstance(crudo, dict) else {}
    out = dict(BOT_DEFECTO)
    host = c.get("host")
    if isinstance(host, str) and 0 < len(host.strip()) <= 253:
        out["host"] = texto_limpio(host, 253)
    port = entero(c.get("port"))
    if port is not None and 1 <= port <= 65535:
        out["port"] = port
    for k in ("version", "usuario", "dueno"):
        v = c.get(k)
        out[k] = texto_limpio(v, 32) if isinstance(v, str) else ""
    pensar = entero(c.get("pensar_cada_s"))
    if pensar is not None and 10 <= pensar <= 3600:
        out["pensar_cada_s"] = pensar
    for k in ("defender", "solo_dueno"):
        if isinstance(c.get(k), bool):
            out[k] = c[k]
    if c.get("estilo_frases") in ESTILOS:
        out["estilo_frases"] = c["estilo_frases"]
    return out


def _ruta_log_valida(ruta: str) -> bool:
    try:
        from lune_core.minecraft_log import ruta_valida
    except Exception:
        return ruta.lower().endswith("latest.log") and not ruta.startswith(("\\\\", "//"))
    return ruta_valida(ruta) is not None


def _leer_controlador(texto: str, tipo: type) -> Any:
    """JSON de los controladores (la biblioteca entera puede pasar de 16 KB): de Python, no de
    la página; hasta 4 MB."""
    if len(texto) > 4 * 1024 * 1024:
        return None
    try:
        obj = json.loads(texto)
    except (ValueError, TypeError, RecursionError):
        return None
    return obj if isinstance(obj, tipo) else None


def registrar_puente_escenario(canal: Any, config: Any, servicios_c4: Any = None, **kw) -> PuenteEscenario:
    """Crea `PuenteEscenario`, lo registra en `canal` (QWebChannel) como «escenario» y, si ya
    hay servicios, lo enlaza. Hay que llamarlo antes de que la página cree su QWebChannel
    (antes de setUrl). Queda como hijo del canal. `kw` (keyword-only): `ventana` (padre del
    diálogo de importar: un widget o un callable que lo da) y, para los tests, `datos`
    (con minecraft() y guardar_minecraft()), `rutas_log` y `diferir`."""
    padre = canal if isinstance(canal, QObject) else None
    puente = PuenteEscenario(config=config, parent=padre,
                             **{k: kw[k] for k in ("datos", "rutas_log", "ventana", "diferir") if k in kw})
    reg = getattr(canal, "registerObject", None)
    if callable(reg):
        try:
            reg("escenario", puente)
            puente._canal = canal
        except Exception:
            _log.exception("puente escenario: no pude registrar «escenario» en el canal")
    if servicios_c4 is not None:
        puente.enlazar(servicios_c4)
    return puente


__all__ = ("PuenteEscenario", "registrar_puente_escenario", "controladores_escenario", "estado_mmd",
           "lista_bailes", "baile_para_pagina", "estado_mc", "evento_mc", "chat_mc", "bot_para_pagina",
           "AL_TERMINAR", "VISTAS", "CONFIG_MC_DEFECTO", "BOT_DEFECTO", "BOT_CLAVES", "CONFIG_MC_BOOL")
