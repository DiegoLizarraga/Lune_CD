"""
servicios/sistema_terminal.py — Discord y el arranque con Windows en el modo patata.

Comandos (devuelven el texto a imprimir; None si la línea no es suya):
- `/discord` · `/discord estado`: si publica, como quién y QUÉ ve Discord.
- `/discord on|off`: guarda `discord.activo` y enciende o apaga la presencia.
- `/discord id <número>` · `/discord id borrar`: el Application ID (en patata no
  hay tarjeta donde pegarlo).
- `/autoinicio` · `/autoinicio estado|on|off`: la entrada Run en su variante
  patata (consola minimizada, sin PyQt6: servicios/autoinicio.py).
- `/autoinicio como bandeja|mascota|ventana` y `/autoinicio espera N` (0–120 s):
  cómo arranca la app de ventanas (se guarda aunque ahora estés en patata).
- `/sentarse`: eso lo hace la mascota de las ventanas.

La presencia de patata es propia (servicios/discord_presencia.Presencia) y solo
publica «Lune CD · Terminal» con «En la terminal», «Pensando…» o nada (null)
con un juego delante (`en_juego()`). El mutex `Local\\LuneDiscordRPC` evita
que la app y patata publiquen a la vez. Sin Qt.

    s = SistemaTerminal(consola, config, en_juego=lambda: patata._juego_activo,
                        pensando=lambda: patata._pensando)
    s.iniciar() ... s.comando("/discord estado") ... s.detener()
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from nucleo import arranque

_log = logging.getLogger("lune.sistema_terminal")

AYUDA = ("/discord on|off|estado · /discord id <número> · "
         "/autoinicio [on|off|estado|como bandeja|mascota|ventana|espera N]")
ESPERA_MAX_S = 120
_SI = {"on", "si", "sí", "1", "true", "activar", "encender"}
_NO = {"off", "no", "0", "false", "desactivar", "apagar"}
_BORRAR = {"borrar", "quitar", "-", "ninguno", "vacio", "vacío"}
_COMO_TXT = {"bandeja": "en la bandeja", "mascota": "con la mascota fuera", "ventana": "con la ventana abierta"}


class SistemaTerminal:
    """/discord y /autoinicio de patata (ver el docstring del módulo)."""

    def __init__(self, consola: Any, config: Any, *, en_juego: Callable[[], bool] = lambda: False,
                 pensando: Callable[[], bool] = lambda: False, presencia: Any = None,
                 autoinicio: Any = None):
        self.consola = consola
        self.config = config
        self._en_juego = en_juego
        self._pensando = pensando
        self._presencia = presencia
        self._autoinicio = autoinicio
        self._iniciado = False

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        p = self._presencia_o_crear()
        if p is not None:
            p.habilitar(self._discord_activo())

    def detener(self) -> None:
        self._iniciado = False
        p = self._presencia
        if p is not None:
            try:
                p.cerrar(timeout=1.0)
            except Exception:
                _log.exception("patata: no pude cerrar la presencia de Discord")

    def actualizar(self) -> None:
        """Algo cambió (empezó o acabó de pensar, un juego): que Discord lo vea ya."""
        p = self._presencia
        if p is not None and self._iniciado:
            try:
                p.actualizar()
            except Exception:
                pass

    @property
    def discord_activo(self) -> bool:
        """`marcado` de la acción «discord» del /menu de patata."""
        return self._discord_activo()

    def alternar_discord(self) -> str:
        """La acción «discord» del /menu: enciende o apaga. → el texto a imprimir."""
        return self._discord_on(not self._discord_activo())

    def foto(self) -> dict:
        """El estado de patata para la presencia (nada más que esto se mira)."""
        return {"modo": "patata", "render": "", "visible": False,
                "juego": _seguro(self._en_juego), "pensando": _seguro(self._pensando)}

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        texto = str(linea or "").strip()
        partes = texto.split()
        if not partes:
            return None
        cmd = partes[0].lower()
        args = partes[1:]
        if cmd == "/discord":
            return self._cmd_discord(args)
        if cmd == "/autoinicio":
            return self._cmd_autoinicio(args)
        if cmd in ("/sentarse", "/sientate", "/siéntate"):
            return ("Sentarse es cosa de la mascota de las ventanas: aquí, en la terminal, "
                    "no tengo barra ni ventanas donde sentarme.")
        return None

    # ── /discord ─────────────────────────────────────────────────────────────────
    def _cmd_discord(self, args) -> str:
        if not args or args[0].lower() in ("estado", "info", "?"):
            return self.texto_discord()
        a0 = args[0].lower()
        if a0 in _SI:
            return self._discord_on(True)
        if a0 in _NO:
            return self._discord_on(False)
        if a0 == "id":
            return self._discord_id(" ".join(args[1:]))
        return f"Uso: {AYUDA}"

    def _discord_on(self, on: bool) -> str:
        self._guardar("discord", "activo", bool(on))
        p = self._presencia_o_crear()
        if p is not None and self._iniciado:
            p.habilitar(bool(on))
        if not on:
            return "Vale: ya no salgo en Discord."
        if not self._client_id():
            return ("Discord activado, pero falta el Application ID de Lune: pégalo con "
                    "/discord id <número> (discord.com/developers → tu aplicación → Application ID).")
        return ("Vale: Discord verá que estoy en la terminal (solo eso: nunca lo que hablamos "
                "ni tus ventanas). /discord estado para ver qué publica.")

    def _discord_id(self, valor: str) -> str:
        from servicios.discord_ipc import ID_OK
        v = str(valor or "").strip()
        if not v:
            actual = self._client_id()
            return (f"Application ID: {actual}" if actual
                    else "Sin Application ID. Pégalo con /discord id <número>.")
        if v.lower() in _BORRAR:
            self._guardar("discord", "client_id", "")
            self.actualizar()
            return "Application ID borrado: no publico nada hasta que pongas otro."
        if not ID_OK.match(v):
            return "Eso no parece un Application ID (son 17–20 cifras)."
        self._guardar("discord", "client_id", v)
        self.actualizar()
        extra = "" if self._discord_activo() else " Actívalo con /discord on."
        return f"Application ID guardado.{extra}"

    def texto_discord(self) -> str:
        if not self._discord_activo():
            return "Discord: apagado. Actívalo con /discord on (solo publico el modo y un estado fijo)."
        if not self._client_id():
            return "Discord: activado, pero falta el Application ID (/discord id <número>)."
        p = self._presencia
        e = {}
        if p is not None:
            try:
                e = dict(p.estado())
            except Exception:
                e = {}
        if e.get("conectado"):
            quien = f" como {e['usuario']}" if e.get("usuario") else ""
            pub = e.get("publicando")
            if isinstance(pub, dict):
                ve = f"«{pub.get('details', '')} — {pub.get('state', '')}»"
            elif _seguro(self._en_juego):
                ve = "nada (hay un juego delante)"
            else:
                ve = "enseguida lo actualizo"
            return f"Discord: conectada{quien}. Discord ve: {ve}."
        error = str(e.get("error") or "").strip()
        return f"Discord: sin conectar{f' ({error})' if error else ' (esperando a Discord)'}."

    # ── /autoinicio ──────────────────────────────────────────────────────────────
    def _cmd_autoinicio(self, args) -> str:
        m = self._mod_autoinicio()
        if not args or args[0].lower() in ("estado", "info", "?"):
            return self.texto_autoinicio()
        a0 = args[0].lower()
        if a0 in _SI or a0 in _NO:
            if m is None:
                return "No sé arrancar con Windows desde aquí."
            quiere = a0 in _SI
            try:
                nuevo = bool(m.establecer(quiere, "patata"))
            except Exception as e:
                return f"No pude cambiarlo: {e}"
            self._guardar("sistema", "autoinicio", nuevo)
            if quiere and not nuevo:
                return "No pude activarlo (¿no es Windows, o no encuentro iniciar_lune.vbs?)."
            return ("Lune arrancará con Windows (aquí, en la terminal, minimizada)." if nuevo
                    else "Lune ya no arranca con Windows.")
        if a0 == "como":
            c = args[1].lower() if len(args) > 1 else ""
            if c not in arranque.COMOS:
                return "Usa /autoinicio como bandeja, /autoinicio como mascota o /autoinicio como ventana."
            self._guardar("sistema", "autoinicio_como", c)
            return (f"Hecho: con la interfaz de ventanas arrancaré {_COMO_TXT[c]}. "
                    "(En patata se abre esta terminal, minimizada.)")
        if a0 in ("espera", "retraso"):
            try:
                n = int(args[1])
            except (IndexError, ValueError):
                return f"Usa /autoinicio espera N (0–{ESPERA_MAX_S} segundos)."
            if not 0 <= n <= ESPERA_MAX_S:
                return f"La espera va de 0 a {ESPERA_MAX_S} segundos."
            self._guardar("sistema", "autoinicio_retraso_s", n)
            return f"Hecho: al arrancar con Windows esperaré {n} s antes de abrir la interfaz de ventanas."
        return f"Uso: {AYUDA}"

    def texto_autoinicio(self) -> str:
        m = self._mod_autoinicio()
        e: dict = {}
        if m is not None:
            try:
                e = dict(m.estado("patata"))
            except Exception:
                e = {}
        if e.get("activo"):
            linea = "Arranque con Windows: sí (esta terminal, minimizada)."
            if not e.get("modo_ok", True):
                linea += " La entrada apunta a otra variante: se corrige sola al arrancar."
        elif e.get("registrado") and not e.get("aprobado", True):
            linea = ("Arranque con Windows: desactivado desde el Administrador de tareas (pestaña Inicio). "
                     "Reactívalo allí o con /autoinicio on.")
        else:
            linea = "Arranque con Windows: no. Actívalo con /autoinicio on."
        c = arranque.como(self.config)
        n = arranque.retraso_s(self.config)
        return f"{linea}\nCon la interfaz de ventanas: {_COMO_TXT[c]}, tras {n} s."

    # ── Internos ─────────────────────────────────────────────────────────────────
    def _presencia_o_crear(self) -> Any:
        if self._presencia is None:
            try:
                from servicios.discord_presencia import Presencia
                self._presencia = Presencia(self.config, self.foto)
            except Exception:
                _log.exception("patata: no pude crear la presencia de Discord")
                self._presencia = None
        return self._presencia

    def _mod_autoinicio(self) -> Any:
        if self._autoinicio is None:
            try:
                from servicios import autoinicio
                self._autoinicio = autoinicio
            except Exception:
                self._autoinicio = False
        return self._autoinicio or None

    def _cfg(self, seccion: str, clave: str, defecto: Any) -> Any:
        try:
            if isinstance(self.config, dict):
                return (self.config.get(seccion) or {}).get(clave, defecto)
            return self.config.get(seccion, clave, defecto)
        except Exception:
            return defecto

    def _guardar(self, seccion: str, clave: str, valor: Any) -> bool:
        if self.config is None:
            return False
        try:
            if isinstance(self.config, dict):
                self.config.setdefault(seccion, {})[clave] = valor
            else:
                self.config.set(seccion, clave, valor)
            return True
        except Exception:
            _log.exception("patata: no pude guardar %s.%s", seccion, clave)
            return False

    def _discord_activo(self) -> bool:
        return bool(self._cfg("discord", "activo", False))

    def _client_id(self) -> str:
        return str(self._cfg("discord", "client_id", "") or "").strip()


def _seguro(fn: Callable[[], Any]) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


__all__ = ("SistemaTerminal", "AYUDA", "ESPERA_MAX_S")
