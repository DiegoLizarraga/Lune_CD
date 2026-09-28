"""
servicios/minecraft_terminal.py — Minecraft en el modo patata (corte 10).

Lo mismo que ui/minecraft_qt.ControlMinecraft, pero en la terminal y sin Qt:

    /mc                              estado (reacciones, registro del juego y bot)
    /mc log on|off                   reaccionar a tu partida (config minecraft.reaccionar)
    /mc bot on [host[:puerto]] | off conectar o desconectar el bot (host y puerto se guardan
                                     en datos.json, sección minecraft; solo servidores con
                                     online-mode=false, D2)
    /mc instalar                     instala el bot (npm ci con el lockfile, ~400 MB; D3: solo
                                     a mano, nunca una herramienta del modelo)
    /mc di <texto>                   el bot lo dice en el chat del juego
    /mc <orden>                      una orden de la lista blanca (sígueme, ven, para, mina 10
                                     hierro…: lune_core/minecraft.clasificar_orden)

REACCIONES (lune_core/minecraft_log + lune_core/minecraft): el latest.log se lee por
sondeo (abrir, leer lo nuevo, cerrar; nada de handles al juego) cada 1 s y se busca cada
10 s; los eventos del log y del bot (observador.js) se deduplican (5 s), pasan por
`Cadencia` y `reaccion` y salen como «Lune: …» con `consola.aviso` y una capa del título
(«minecraft», prioridad 30) mientras dura. Con `voz_reacciones`, también por la voz.
El texto del juego NUNCA entra en un turno del modelo; el chat de otros jugadores no se
imprime (es texto de terceros).

MODO JUEGO (D4, `en_juego()`): con el bot conectado y `decir_en_juego`, las muertes,
logros y peligros los dice el bot en el chat del juego; lo tuyo se apunta y, con
`resumen_al_salir`, al salir sale «Mientras jugabas: …». El cerebro autónomo del bot se
pausa mientras juegas (salvo `pensar_en_juego`); `pensando()` (Lune piensa una respuesta)
pausa su modelo (`pausa_llm`: comparten Ollama).

Nada corre con las reacciones apagadas y el bot desconectado: el hilo «lune-mc-terminal»
solo vive mientras hace falta. `detener()` corta una instalación en marcha (mata npm y sus
hijos) y para el bot (que no quede node huérfano). /mc instalar no va con el bot en marcha
(npm ci borra node_modules) ni si otra ventana de Lune ya está instalando (la marca de
minecraft-bot/). El registro soltado tras 10 min sin cambios, al volver a moverse el MISMO
archivo, sigue donde se quedó.
`registrar_herramientas(tools)`: minecraft_estado, minecraft_orden y minecraft_bot
(la aprobación la pide el Ejecutor, catalogo_herramientas).
"""
from __future__ import annotations

import collections
import logging
import re
import secrets
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from lune_core import minecraft as nm
from lune_core import minecraft_log as ml
from lune_core import minecraft_proceso as mp

_log = logging.getLogger("lune.minecraft_terminal")

AYUDA = ("/mc · /mc log on|off · /mc bot on [host[:puerto]]|off · /mc instalar · /mc di <texto> · "
         "/mc <orden> (sígueme, ven, para, mina 10 hierro…)")
INTERVALO_S = 1.0
DETECTAR_S = 10.0
SOLTAR_LOG_S = 600.0
RECIENTE_S = 60.0
DEDUP_S = 5.0
MAX_EVENTOS = 50
CAPA = "minecraft"
PRIORIDAD_TITULO = 30            # por encima del baile (20), por debajo del modo juego (50) y la alarma (60)
DECIR_EN_JUEGO = frozenset({"muerte", "logro", "peligro"})
_SI = {"on", "si", "sí", "1", "true", "activar", "encender", "conectar"}
_NO = {"off", "no", "0", "false", "desactivar", "apagar", "desconectar"}
_CONTROLES = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")
_COMANDOS = ("/mc", "/minecraft")


def _texto(v: Any, tope: int) -> str:
    """Texto de fuera en una línea, sin controles (ni ESC: nada de secuencias ANSI)."""
    t = _CONTROLES.sub(" ", str(v if isinstance(v, (str, int, float)) else ""))
    return re.sub(r"\s+", " ", t).strip()[:tope]


def _llamar(obj: Any, metodo: str, *args) -> Any:
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("minecraft (patata): %s.%s falló", type(obj).__name__, metodo)
        return None


def servidor_de(texto: str) -> Tuple[Optional[str], Optional[int], str]:
    """«host[:puerto]» → (host, puerto | None, error). IPv6 entre corchetes: «[::1]:25565»."""
    t = str(texto or "").strip()
    if not t:
        return None, None, "Dime el servidor: /mc bot on host[:puerto]."
    host, puerto = t, None
    m = re.fullmatch(r"\[([0-9A-Fa-f:]+)\](?::(\d{1,5}))?", t)
    if m:
        host, puerto = m.group(1), m.group(2)
    elif t.count(":") == 1 and t.split(":", 1)[1].isdigit():
        host, puerto = t.split(":", 1)
    h = mp.validar_host(host)
    if not h:
        return None, None, "Ese servidor no es un nombre ni una IP válidos."
    if puerto is None or puerto == "":
        return h, None, ""
    if not str(puerto).isdigit() or not 1 <= int(puerto) <= 65535:
        return None, None, "El puerto tiene que estar entre 1 y 65535."
    return h, int(puerto), ""


class MinecraftTerminal:
    """/mc y las reacciones a Minecraft en patata (ver la cabecera del módulo)."""

    def __init__(self, consola: Any, config: Any, *, proceso: Any = None, lector: Any = None,
                 voice: Any = None, colores: Optional[dict] = None,
                 en_juego: Callable[[], bool] = lambda: False, pensando: Callable[[], bool] = lambda: False,
                 reloj: Callable[[], float] = time.monotonic, ahora: Callable[[], float] = time.time,
                 rng: Any = None, rutas: Optional[Callable[[], List[Any]]] = None,
                 datos_mc: Optional[Callable[[], dict]] = None, guardar_mc: Optional[Callable[[dict], Any]] = None,
                 personaje: Optional[Callable[[], dict]] = None, llm: Optional[Callable[[], Optional[dict]]] = None,
                 hilo: bool = True):
        self.consola = consola
        self.config = config
        self.voice = voice
        self.c = dict(colores) if colores else {}
        self._en_juego = en_juego
        self._pensando_fn = pensando
        self._reloj = reloj
        self._ahora = ahora
        self._rng = rng
        self._rutas = rutas or ml.rutas_candidatas
        self._datos_mc = datos_mc or self._datos_mc_defecto
        self._guardar_mc = guardar_mc or self._guardar_mc_defecto
        self._personaje_fn = personaje or self._personaje_defecto
        self._llm = llm or mp.config_llm
        self._con_hilo = bool(hilo)
        self._lock = threading.RLock()
        # Lector: una fábrica `lector(ruta)` o un lector ya hecho (con poll()).
        self._lector_fijo = lector if lector is not None and hasattr(lector, "poll") else None
        self._fab_lector = lector if callable(lector) and self._lector_fijo is None else None
        self._lector: Any = self._lector_fijo
        self._ruta_log = str(getattr(lector, "ruta", "") or "") if self._lector_fijo is not None else ""
        self._t_detectado = float("-inf")
        self._cadencia = nm.Cadencia(reloj, rng)
        self._resumen = nm.Resumen()
        self._recientes: Deque[dict] = collections.deque(maxlen=MAX_EVENTOS)
        self._dedup: Dict[tuple, float] = {}
        self._iniciado = False
        self._juego = False
        self._pensando = False
        self._titulo_hasta: Optional[float] = None
        self._bot: Dict[str, Any] = {"instalando": False, "conectando": False, "conectado": False, "servidor": "",
                                     "nick": "", "vida": None, "hambre": None, "dia": None, "lluvia": None,
                                     "error": ""}
        self._hilo: Optional[threading.Thread] = None
        self._despertar = threading.Event()
        self._foto_log: Optional[dict] = None        # dónde se quedó el lector soltado por inactividad
        self.proceso = proceso if proceso is not None else mp.ProcesoBot()
        for nombre, fn in (("on_evento", self._on_bot), ("on_log", self._on_log), ("on_fin", self._on_fin)):
            try:
                setattr(self.proceso, nombre, fn)
            except Exception:
                pass

    # ── Por defecto (inyectables en tests) ───────────────────────────────────────
    @staticmethod
    def _datos_mc_defecto() -> dict:
        from nucleo import datos
        return datos.minecraft()

    @staticmethod
    def _guardar_mc_defecto(cambios: dict) -> Any:
        from nucleo import datos
        return datos.guardar_minecraft(cambios)

    @staticmethod
    def _personaje_defecto() -> dict:
        try:
            from nucleo import personajes
            return personajes.get_activo() or {}
        except Exception:
            return {}

    def _cfg(self, clave: str, defecto: Any) -> Any:
        try:
            return self.config.get("minecraft", clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def _col(self, nombre: str) -> str:
        return self.c.get(nombre, "")

    def _juego_ahora(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _nombre(self) -> str:
        try:
            n = (self._personaje_fn() or {}).get("nombre")
        except Exception:
            n = None
        return _texto(n, 24) or "Lune"

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        with self._lock:
            self._iniciado = True
            self._juego = self._juego_ahora()
        self._asegurar_hilo()

    def detener(self) -> None:
        """Para el hilo, suelta el log y PARA el bot (esperando: que no quede node huérfano)."""
        with self._lock:
            self._iniciado = False
            self._lector = self._lector_fijo
        self._despertar.set()
        self._quitar_titulo()
        _llamar(self.proceso, "cancelar_instalacion")
        try:
            if getattr(self.proceso, "vivo", False):
                self.proceso.parar(espera_s=2.0)
        except Exception:
            _log.exception("minecraft (patata): parar el bot falló")
        self._bot.update(conectando=False, conectado=False)
        h = self._hilo
        if h is not None and h is not threading.current_thread():
            h.join(2.0)

    @property
    def reaccionando(self) -> bool:
        return bool(self._cfg("reaccionar", False))

    def _bot_vivo(self) -> bool:
        try:
            return bool(getattr(self.proceso, "vivo", False))
        except Exception:
            return False

    @property
    def bot_conectado(self) -> bool:
        return bool(self._bot.get("conectado"))

    def _necesita_hilo(self) -> bool:
        return self._iniciado and (self.reaccionando or self._bot_vivo() or bool(self._bot.get("instalando"))
                                   or self._titulo_hasta is not None)

    def _asegurar_hilo(self) -> None:
        if not self._con_hilo or not self._necesita_hilo():
            return
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._despertar.clear()
            self._hilo = threading.Thread(target=self._bucle, name="lune-mc-terminal", daemon=True)
            self._hilo.start()

    def _bucle(self) -> None:
        try:
            while self._necesita_hilo():
                try:
                    self.paso()
                except Exception:
                    _log.exception("minecraft (patata): fallo en el sondeo")
                self._despertar.wait(INTERVALO_S)
                self._despertar.clear()
        finally:
            with self._lock:
                if self._hilo is threading.current_thread():
                    self._hilo = None
            if not self._iniciado or self._titulo_hasta is None:
                self._quitar_titulo()

    # ── Un paso (el hilo, cada 1 s; los tests, a mano) ───────────────────────────
    def paso(self) -> None:
        t = self._reloj()
        self._mirar_bus()
        hasta = self._titulo_hasta
        if hasta is not None and t >= hasta:
            self._quitar_titulo()
        if not self.reaccionando:
            self._soltar_log()
            return
        if self._lector_fijo is None and (self._lector is None or t - self._t_detectado >= DETECTAR_S):
            self._detectar(t)
        self._leer()

    def _mirar_bus(self) -> None:
        """Modo juego y «pensando» de patata → pausa del cerebro del bot y resumen."""
        juego = self._juego_ahora()
        try:
            pensando = bool(self._pensando_fn())
        except Exception:
            pensando = False
        if pensando != self._pensando:
            self._pensando = pensando
            if self._bot_vivo():
                _llamar(self.proceso, "pausa_llm", pensando)
        if juego != self._juego:
            self._juego = juego
            if self._bot_vivo() and not bool(self._cfg("pensar_en_juego", False)):
                _llamar(self.proceso, "pausa_autonomo", juego)
            if juego:
                with self._lock:
                    self._resumen.reiniciar()         # el resumen es de ESTA partida
            else:
                self._decir_resumen()

    def _decir_resumen(self) -> bool:
        if not bool(self._cfg("resumen_al_salir", True)):
            self._resumen.reiniciar()
            return False
        texto = self._resumen.texto()
        self._resumen.reiniciar()
        if not texto:
            return False
        self._mostrar(texto, 9000)
        self._apuntar({"tipo": "resumen", "texto": texto, "fuente": "lune", "t": self._ahora()})
        return True

    # ── Log ──────────────────────────────────────────────────────────────────────
    def _detectar(self, t: float) -> None:
        self._t_detectado = t
        ruta_cfg = str(self._cfg("ruta_log", "") or "").strip()
        reciente = RECIENTE_S if bool(self._cfg("auto_con_juego", True)) else None
        try:
            if ruta_cfg:
                ruta = ml.elegir_log(ruta_cfg, [], ahora=self._ahora)
                if ruta is not None and reciente is not None:
                    ruta = ml.elegir_log("", [ruta], ahora=self._ahora, reciente_s=reciente)
            else:
                ruta = ml.elegir_log("", self._rutas(), ahora=self._ahora, reciente_s=reciente)
        except Exception:
            _log.exception("minecraft (patata): buscar latest.log falló")
            ruta = None
        if ruta is None:
            return                                   # se deja el que había (lo suelta _leer tras 10 min)
        if self._lector is None or str(getattr(self._lector, "ruta", "")) != str(ruta):
            fab = self._fab_lector or ml.LectorLog
            try:
                lector = fab(ruta)
            except Exception:
                _log.exception("minecraft (patata): no pude crear el lector del log")
                return
            try:
                lector.nombre_bot = str(self._bot.get("nick") or "")
                lector.otros = bool(self._cfg("reaccionar_otros", False))
            except Exception:
                pass
            # El mismo archivo que se soltó por inactividad: sigue donde se quedó.
            foto, self._foto_log = self._foto_log, None
            if foto is not None and foto.get("ruta") == str(ruta):
                _llamar(lector, "retomar", foto)
            with self._lock:
                self._lector = lector
                self._ruta_log = str(ruta)

    def _leer(self) -> None:
        lector = self._lector
        if lector is None:
            return
        try:
            eventos = lector.poll()
        except Exception:
            _log.exception("minecraft (patata): leer el log falló")
            eventos = []
        for ev in eventos or []:
            self._recibir(ev)
        if self._lector_fijo is None and lector is self._lector:
            inactivo = _llamar(lector, "inactivo_s")
            if isinstance(inactivo, (int, float)) and inactivo > SOLTAR_LOG_S:
                foto = _llamar(lector, "instantanea")
                self._soltar_log()
                self._foto_log = foto if isinstance(foto, dict) else None

    def _soltar_log(self) -> None:
        if self._lector_fijo is not None:
            return
        with self._lock:
            self._lector = None
            self._ruta_log = ""
            self._foto_log = None                    # soltado a propósito: la próxima vez, desde el final

    # ── Reacciones ───────────────────────────────────────────────────────────────
    def _clave_dedup(self, ev: Any) -> tuple:
        tipo = str(getattr(ev, "tipo", ""))
        jugador = str(getattr(ev, "jugador", "") or "").lower()
        if tipo in ("muerte", "logro", "conexion", "desconexion"):
            return (tipo, jugador)
        return (tipo, jugador, str(getattr(ev, "detalle", "") or "").lower())

    def _recibir(self, ev: Any) -> Optional[nm.Reaccion]:
        """Un evento (del log o del bot) → reacción según el modo."""
        tipo = str(getattr(ev, "tipo", "") or "")
        if tipo not in nm.EVENTOS:
            return None
        t = self._reloj()
        with self._lock:
            for k in [k for k, v in self._dedup.items() if t - v >= DEDUP_S]:
                del self._dedup[k]
            clave = self._clave_dedup(ev)
            if clave in self._dedup:
                return None
            self._dedup[clave] = t
            if getattr(ev, "fuente", "log") == "log" and not self.reaccionando:
                return None
            juego = self._juego
            if juego and bool(self._cfg("resumen_al_salir", True)):
                self._resumen.anotar(ev)
            if not self._cadencia.admite(tipo):
                return None
        r = nm.reaccion(ev, personaje=self._personaje_fn(), rng=self._rng)
        if r is None:
            return None
        if juego:
            dicho = False
            if tipo in DECIR_EN_JUEGO and self._bot.get("conectado") and bool(self._cfg("decir_en_juego", True)):
                dicho = bool(_llamar(self.proceso, "decir", r.texto))
            self._apuntar({"tipo": tipo, "texto": r.texto, "fuente": str(getattr(ev, "fuente", "log")),
                           "t": self._ahora(), "entregado": dicho})
            return r
        self._mostrar(r.texto, r.ms)
        if bool(self._cfg("voz_reacciones", False)) and self.voice is not None:
            _llamar(self.voice, "speak", r.texto)
        self._apuntar({"tipo": tipo, "texto": r.texto, "fuente": str(getattr(ev, "fuente", "log")),
                       "t": self._ahora(), "entregado": True})
        return r

    def _mostrar(self, texto: str, ms: int) -> None:
        """«Lune: …» en su línea y en el título un rato."""
        t = _texto(texto, 240)
        if not t:
            return
        cy, rst = self._col("cyan"), self._col("reset")
        nombre = self._nombre()
        _llamar(self.consola, "aviso", f"{cy}{nombre}:{rst} {t}")
        capa = getattr(self.consola, "titulo_capa", None)
        if callable(capa):
            try:
                capa(CAPA, f"{nombre}: {t}"[:120], PRIORIDAD_TITULO)
                self._titulo_hasta = self._reloj() + max(1.0, float(ms) / 1000.0)
            except Exception:
                _log.debug("minecraft (patata): no pude poner el título", exc_info=True)
        self._asegurar_hilo()                        # el hilo quita la capa al vencer

    def _quitar_titulo(self) -> None:
        if self._titulo_hasta is None:
            return
        self._titulo_hasta = None
        capa = getattr(self.consola, "titulo_capa", None)
        if callable(capa):
            try:
                capa(CAPA, None, PRIORIDAD_TITULO)
            except Exception:
                pass

    def _apuntar(self, d: dict) -> None:
        with self._lock:
            self._recientes.append(d)

    def eventos_recientes(self, n: int = 50) -> List[dict]:
        n = max(0, min(MAX_EVENTOS, int(n)))
        with self._lock:
            return list(self._recientes)[-n:] if n else []

    def alternar_reacciones(self) -> bool:
        return self.set_reacciones(not self.reaccionando)

    def set_reacciones(self, on: bool) -> bool:
        try:
            self.config.set("minecraft", "reaccionar", bool(on))
        except Exception:
            _log.exception("minecraft (patata): no pude guardar minecraft.reaccionar")
        if not on:
            self._soltar_log()
        else:
            self._t_detectado = float("-inf")
            self._asegurar_hilo()
        return bool(on)

    # ── Bot ──────────────────────────────────────────────────────────────────────
    def requisitos(self, refrescar: bool = False) -> dict:
        """Node, npm e instalado (ProcesoBot lo cachea; `refrescar` lo vuelve a mirar: node --version)."""
        try:
            return dict(self.proceso.requisitos(refrescar=refrescar))
        except TypeError:
            return dict(self.proceso.requisitos())
        except Exception:
            _log.exception("minecraft (patata): requisitos del bot")
            return {"node": None, "node_ok": False, "npm": False, "instalado": False}

    def _instalando(self) -> bool:
        """Esta terminal instala, u otra ventana de Lune (la marca de minecraft-bot/)."""
        if self._bot.get("instalando"):
            return True
        try:
            return bool(getattr(self.proceso, "instalando", False))
        except Exception:
            return False

    def instalar_bot(self) -> str:
        """/mc instalar (D3: solo a mano). En un hilo; el resultado sale con un aviso."""
        if self._instalando():
            return "Ya se está instalando el bot."
        if self._bot_vivo():
            return mp.AVISO_BOT_VIVO.replace("Desconecta el bot", "Desconecta el bot (/mc bot off)")
        req = self.requisitos(refrescar=True)
        if not req.get("node_ok"):
            return mp.AVISO_SIN_NODE
        self._bot["instalando"] = True
        self._bot["error"] = ""

        def trabajo():
            try:
                ok, texto = self.proceso.instalar()
            except Exception as e:                       # noqa: BLE001
                ok, texto = False, f"No pude instalar el bot: {e}"[:300]
            self._bot["instalando"] = False
            self._bot["error"] = "" if ok else _texto(texto, 400)
            _llamar(self.consola, "aviso", ("♪ " if ok else "") + _texto(texto, 400))

        if self._con_hilo:
            threading.Thread(target=trabajo, name="lune-mc-instalar", daemon=True).start()
            return "Instalando el bot de Minecraft (~400 MB, puede tardar unos minutos)…"
        trabajo()
        return "Instalación terminada."

    def conectar_bot(self, servidor: str = "") -> Tuple[bool, str]:
        if self._bot_vivo():
            return False, "El bot ya está conectado."
        if self._instalando():
            return False, "Espera a que termine la instalación."
        if servidor:
            host, puerto, error = servidor_de(servidor)
            if error:
                return False, error
            cambios: Dict[str, Any] = {"host": host}
            if puerto is not None:
                cambios["port"] = puerto
            try:
                self._guardar_mc(cambios)
            except ValueError as e:
                return False, str(e)
            except Exception as e:                       # noqa: BLE001
                return False, f"No pude guardar el servidor: {e}"[:200]
        req = self.requisitos(refrescar=True)
        if not req.get("node_ok"):
            return False, mp.AVISO_SIN_NODE
        if not req.get("instalado"):
            return False, "Instala el bot antes con /mc instalar (descarga ~400 MB)."
        try:
            cfg = mp.config_bot(self._datos_mc(), self._personaje_fn(), self._llm())
        except ValueError as e:
            self._bot["error"] = str(e)
            return False, str(e).replace("en Ajustes → Minecraft", "en datos.json (sección minecraft)")
        cfg["pausa_autonomo"] = bool(self._juego and not self._cfg("pensar_en_juego", False))
        cfg["pausa_llm"] = bool(self._pensando)
        try:
            ok, texto = self.proceso.arrancar(cfg)
        except Exception as e:                           # noqa: BLE001
            ok, texto = False, f"No pude lanzar el bot: {e}"[:300]
        if not ok:
            self._bot["error"] = str(texto)
            return False, str(texto)
        self._bot.update(conectando=True, conectado=False, error="", servidor=f"{cfg['host']}:{cfg['port']}",
                         nick=cfg["nick"], vida=None, hambre=None, dia=None, lluvia=None)
        if self._lector is not None:
            try:
                self._lector.nombre_bot = cfg["nick"]
            except Exception:
                pass
        self._asegurar_hilo()
        return True, f"Conectando el bot a {cfg['host']}:{cfg['port']} como {cfg['nick']}…"

    def desconectar_bot(self) -> bool:
        if not self._bot_vivo():
            self._bot.update(conectando=False, conectado=False)
            return False
        self._bot["conectando"] = False

        def parar():
            try:
                self.proceso.parar()
            except Exception:
                _log.exception("minecraft (patata): parar el bot falló")
        if self._con_hilo:
            threading.Thread(target=parar, name="lune-mc-parar", daemon=True).start()
        else:
            parar()
        return True

    def orden(self, texto: str, *, origen: str = "usuario") -> Tuple[bool, str]:
        orden = nm.clasificar_orden(texto)
        if orden is None:
            return False, f"El bot no entiende esa orden. Puede: {nm.AYUDA_ORDENES}."
        if not self._bot.get("conectado"):
            return False, "El bot no está conectado (/mc bot on)."
        id_ = secrets.token_hex(4)
        if not _llamar(self.proceso, "orden", id_, orden):
            return False, "No pude mandarle la orden al bot."
        self._apuntar({"tipo": "orden", "texto": orden, "fuente": str(origen)[:12], "t": self._ahora(), "id": id_})
        return True, "Se lo he mandado al bot."

    def decir(self, texto: str) -> Tuple[bool, str]:
        t = _texto(texto, 100).lstrip("/\\ ").strip()
        if not t:
            return False, "¿Qué digo? /mc di <texto>."
        if not self._bot.get("conectado"):
            return False, "El bot no está conectado (/mc bot on)."
        if not _llamar(self.proceso, "decir", t):
            return False, "No pude mandárselo al bot."
        return True, "Dicho."

    # ── Mensajes del bot (desde su hilo lector) ──────────────────────────────────
    def _on_bot(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        tipo = msg.get("tipo")
        if tipo == "conectado":
            nick = mp.nick_valido(msg.get("nick")) or self._bot.get("nick") or ""
            self._bot.update(conectando=False, conectado=True, error="", nick=nick)
            if self._lector is not None:
                try:
                    self._lector.nombre_bot = nick
                except Exception:
                    pass
            self._recibir(ml.Evento("bot_conectado", nick, fuente="bot", t=self._ahora()))
        elif tipo == "desconectado":
            estaba = bool(self._bot.get("conectado"))
            self._bot.update(conectando=False, conectado=False, error=_texto(msg.get("motivo"), 200))
            if estaba:
                self._recibir(ml.Evento("bot_desconectado", fuente="bot", t=self._ahora()))
            elif self._bot["error"]:
                _llamar(self.consola, "aviso", f"{self._col('dim')}Minecraft: el bot no pudo entrar "
                                               f"({self._bot['error']}).{self._col('reset')}")
        elif tipo == "estado":
            for clave in ("vida", "hambre"):
                v = msg.get(clave)
                self._bot[clave] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 40 else None
            for clave in ("dia", "lluvia"):
                v = msg.get(clave)
                self._bot[clave] = v if isinstance(v, bool) else None
        elif tipo == "evento":
            self._evento_del_bot(msg)
        elif tipo == "respuesta":
            texto = _texto(msg.get("texto"), 300)
            if texto:
                self._apuntar({"tipo": "respuesta", "texto": texto, "fuente": "bot", "t": self._ahora()})
                _llamar(self.consola, "aviso", f"{self._col('dim')}bot:{self._col('reset')} {texto}")
        elif tipo == "error":
            self._bot["error"] = _texto(msg.get("mensaje"), 300)
            if msg.get("fatal"):
                self._bot["conectando"] = False
        # «chat» (otros jugadores) no se imprime: texto de terceros

    def _evento_del_bot(self, msg: dict) -> None:
        tipo = str(msg.get("evento") or "")
        if tipo not in nm.EVENTOS or tipo in ("sesion_inicio", "sesion_fin", "conexion", "desconexion",
                                              "bot_conectado", "bot_desconectado"):
            return
        jugador = mp.nick_valido(msg.get("jugador")) or ""
        detalle = _texto(msg.get("detalle"), 64)
        try:
            dueno = str((self._datos_mc() or {}).get("dueno") or "")
        except Exception:
            dueno = ""
        propio = bool(jugador) and jugador.lower() == dueno.lower()
        if tipo in ("muerte", "logro") and not propio and not bool(self._cfg("reaccionar_otros", False)):
            return
        self._recibir(ml.Evento(tipo, jugador, detalle, t=self._ahora(), fuente="bot", propio=propio))

    def _on_log(self, linea: Any) -> None:
        _log.debug("minecraft (bot): %s", _texto(linea, 300))

    def _on_fin(self, codigo: Any) -> None:
        estaba = bool(self._bot.get("conectado"))
        self._bot.update(conectando=False, conectado=False)
        if isinstance(codigo, int) and codigo not in (0, None) and not self._bot.get("error"):
            self._bot["error"] = f"El bot se cerró (código {codigo})."
        if estaba:
            self._recibir(ml.Evento("bot_desconectado", fuente="bot", t=self._ahora()))

    # ── Estado ───────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        req = self.requisitos()
        try:
            instalado = bool(self.proceso.instalado())
        except Exception:
            instalado = bool(req.get("instalado"))
        bot = dict(self._bot)
        bot["instalado"] = instalado
        bot["instalando"] = self._instalando()
        bot["conectando"] = bool(bot.get("conectando")) and self._bot_vivo()
        lector = self._lector
        return {
            "reaccionar": self.reaccionando,
            "log": {"ruta": self._ruta_log if lector is not None else "", "activo": lector is not None,
                    "yo": (mp.nick_valido(getattr(lector, "yo", "")) or "") if lector is not None else ""},
            "bot": bot,
            "requisitos": {"node": req.get("node"), "node_ok": bool(req.get("node_ok")), "npm": bool(req.get("npm"))},
            "juego": bool(self._juego),
            "pensando": bool(self._pensando),
        }

    def texto_estado(self) -> str:
        e = self.estado()
        lineas = [nm.texto_estado(e)]
        log = e["log"]
        if e["reaccionar"]:
            if log["activo"]:
                lineas.append(f"Registro: {log['ruta']}" + (f" (juegas como {log['yo']})" if log["yo"] else ""))
            else:
                lineas.append("Registro: no encuentro un latest.log reciente (¿Minecraft abierto?).")
        bot = e["bot"]
        if bot.get("conectado") and bot.get("servidor"):
            lineas.append(f"Servidor: {bot['servidor']}")
        if bot.get("error") and not bot.get("conectado"):
            lineas.append(f"Último error del bot: {_texto(bot['error'], 200)}")
        lineas.append(f"Uso: {AYUDA}")
        return "\n".join(lineas)

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        """/mc … . None si la línea no es suya."""
        texto = str(linea or "").strip()
        partes = texto.split(maxsplit=1)
        if not partes or partes[0].lower() not in _COMANDOS:
            return None
        resto = partes[1].strip() if len(partes) > 1 else ""
        if not resto:
            return self.texto_estado()
        args = resto.split()
        a0 = args[0].lower()
        if a0 in ("ayuda", "?", "-h", "--help"):
            return f"Uso: {AYUDA}\nÓrdenes: {nm.AYUDA_ORDENES}."
        if a0 in ("estado", "info"):
            return self.texto_estado()
        if a0 in ("log", "reacciones", "reaccionar"):
            if len(args) < 2:
                return f"Reacciones a tu partida: {'sí' if self.reaccionando else 'no'}. /mc log on|off."
            v = args[1].lower()
            if v in _SI:
                self.set_reacciones(True)
                return "♪ Vale: miro tu partida de Minecraft (el registro del juego, nada más)."
            if v in _NO:
                self.set_reacciones(False)
                return "Vale: ya no miro tu partida."
            return "Usa /mc log on o /mc log off."
        if a0 == "bot":
            if len(args) < 2:
                return "Usa /mc bot on [host[:puerto]] o /mc bot off."
            v = args[1].lower()
            if v in _SI:
                ok, t = self.conectar_bot(" ".join(args[2:]))
                return t
            if v in _NO:
                return "Desconecto el bot." if self.desconectar_bot() else "El bot no estaba conectado."
            return "Usa /mc bot on [host[:puerto]] o /mc bot off."
        if a0 == "instalar":
            return self.instalar_bot()
        if a0 in ("di", "dile", "decir"):
            ok, t = self.decir(resto[len(args[0]):].strip())
            return t
        ok, t = self.orden(resto, origen="usuario")
        return t

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["minecraft"] = self
        return base

    def herramientas(self) -> dict:
        return {
            "minecraft_estado": lambda args=None, ctx=None: nm.herramienta_estado(args, self._ctx(ctx)),
            "minecraft_orden": lambda args=None, ctx=None: nm.herramienta_orden(args, self._ctx(ctx)),
            "minecraft_bot": lambda args=None, ctx=None: nm.herramienta_bot(args, self._ctx(ctx)),
        }

    def registrar_herramientas(self, tools: Any) -> None:
        for nombre, fn in self.herramientas().items():
            try:
                tools.registrar_handler(nombre, fn)
            except Exception:
                _log.exception("minecraft (patata): no pude registrar %s", nombre)


__all__ = ("MinecraftTerminal", "AYUDA", "servidor_de", "CAPA", "PRIORIDAD_TITULO")
