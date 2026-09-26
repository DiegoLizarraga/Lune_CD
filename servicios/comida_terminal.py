"""
servicios/comida_terminal.py — La comida en el modo patata (terminal).

En patata no hay mascota ni cursor que seguir: dar de comer es una línea de
texto y el sonido del trago o del mordisco por el Mezclador (canal `sfx`, con
tono al azar), como en la app de ventanas.

    /comer [batido|pastel] [sabor]   Lune (^o^)~ *glup glup* (batido de mango)
    /comer on|off               enciende o apaga la comida (comida.activa)

- Sin comida en el argumento, una al azar; sin sabor (o con uno que no hay), uno
  al azar. Se entienden «tarta», «smoothie», «/comer batido de mango»…
- Con un juego delante (`en_juego()`) y `juego.silenciar`, sin sonido (el texto sí).
- Con `patata.caritas = kaomoji`, la cara en kaomoji: «(っ˘ω˘ς)».
- `registrar_herramientas(tools)`: `dar_de_comer` (nucleo.comida.herramienta)
  sobre este objeto: sonido y el texto para el modelo.

Sin Qt.
"""
from __future__ import annotations

import logging
import random
import threading
from typing import Any, Callable, Dict, Optional, Union

from nucleo import comida as nc

_log = logging.getLogger("lune.comida_terminal")

AYUDA = "/comer [batido|pastel] [sabor] · /comer on|off"
_SI = {"on", "si", "sí", "1", "true", "activar", "encender"}
_NO = {"off", "no", "0", "false", "desactivar", "apagar"}
_COMANDOS = ("/comer", "/comida")


def _ansi_color(hex_: str) -> str:
    """#RRGGBB → secuencia truecolor de primer plano."""
    h = str(hex_ or "").lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return ""
    return f"\x1b[38;2;{r};{g};{b}m"


class ComidaTerminal:
    """/comer y la herramienta `dar_de_comer` en patata (ver la cabecera)."""

    def __init__(self, consola: Any, config: Any, *, colores: Optional[Dict[str, str]] = None,
                 mezclador: Any = None, en_juego: Callable[[], bool] = lambda: False,
                 nombre: Union[str, Callable[[], str]] = "Lune", azar: Optional[random.Random] = None,
                 lanzar_sonido: Optional[Callable[[Callable[[], None]], Any]] = None):
        self.consola = consola
        self.config = config
        self.c = dict(colores) if colores else {}
        self._en_juego = en_juego
        self._nombre = nombre
        self._azar = azar if azar is not None else random.Random()
        self._lock = threading.RLock()
        self.gestor = nc.GestorComida(azar=self._azar)
        self.sonidos = nc.SonidosComida(config, mezclador=mezclador, lanzar=lanzar_sonido,
                                        en_juego=self._juego, azar=self._azar)
        self.ultimo_motivo = ""

    # ── Ciclo de vida (como los módulos de los cortes 5/6; aquí no hay nada que arrancar) ──
    def iniciar(self) -> None:
        pass

    def detener(self) -> None:
        pass

    # ── Utilidades ───────────────────────────────────────────────────────────────
    def _juego(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _nombre_actual(self) -> str:
        n = self._nombre
        try:
            n = n() if callable(n) else n
        except Exception:
            n = "Lune"
        return str(n or "Lune").strip() or "Lune"

    def _kaomoji(self) -> bool:
        try:
            v = self.config.get("patata", "caritas", "clasico") if self.config is not None else "clasico"
        except Exception:
            v = "clasico"
        return str(v or "").strip().lower() == "kaomoji"

    def _habilitada(self) -> bool:
        return nc.comida_habilitada(self.config)

    def _col(self, nombre: str) -> str:
        return self.c.get(nombre, "")

    # ── Comer ────────────────────────────────────────────────────────────────────
    def _reaccion(self, id_: Any, variante: Any = None) -> Optional[nc.Reaccion]:
        """La reacción con su sonido, o None (motivo en `ultimo_motivo`)."""
        with self._lock:
            n = nc.normalizar_id(id_)
            if n is None:
                self.ultimo_motivo = "desconocida"
                return None
            if not self._habilitada():
                self.ultimo_motivo = "desactivada"
                return None
            self.ultimo_motivo = ""
            r = self.gestor.reaccion(n, variante)          # sabor que no existe → al azar
        self.sonidos.reaccion(r)                  # callado solo en juego con juego.silenciar
        return r

    def comer_directo(self, id_: Any) -> str:
        """Para la herramienta: el texto («*glup glup* (batido de fresa)») o ""."""
        r = self._reaccion(id_)
        return r.texto if r is not None else ""

    def comer(self, id_: Any = None, variante: Any = None) -> str:
        """/comer: la línea para la terminal (con color si hay ANSI)."""
        n = nc.normalizar_id(id_) if id_ else self._azar.choice(tuple(nc.CATALOGO))
        if n is None:
            return f"No tengo «{str(id_).strip()[:30]}». Uso: {AYUDA}"
        r = self._reaccion(n, variante)
        if r is None:
            if self.ultimo_motivo == "desactivada":
                return "La comida está apagada. Enciéndela con /comer on."
            return f"Ahora no puedo comer ({nc.motivo_legible(self.ultimo_motivo)})."
        texto = nc.texto_terminal(r.id, r.variante, self._kaomoji(), nombre=self._nombre_actual())
        reset = self._col("reset")
        v = nc.variante_de(r.id, r.variante)
        if reset and v is not None:
            # La comida en su color: «… (batido de mango)».
            i = texto.rfind("(")
            color = _ansi_color(v.color)
            if i >= 0 and color:
                texto = texto[:i] + color + texto[i:] + reset
        return texto

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        """/comer […]. None si la línea no es suya."""
        texto = str(linea or "").strip()
        partes = texto.split()
        if not partes or partes[0].lower() not in _COMANDOS:
            return None
        args = partes[1:]
        if not args:
            return self.comer()
        a0 = args[0].lower()
        if a0 in _SI or a0 in _NO:
            return self._cmd_activa(a0 in _SI)
        if a0 in ("ayuda", "?", "-h", "--help"):
            return f"Uso: {AYUDA}"
        resto = [a for a in args[1:] if a.lower() != "de"]       # «/comer batido de mango»
        return self.comer(args[0], resto[0] if resto else None)

    def _cmd_activa(self, on: bool) -> str:
        if self.config is not None:
            try:
                if self._habilitada() != on:
                    self.config.set("comida", "activa", bool(on))
            except Exception:
                _log.exception("comida (patata): no pude guardar comida.activa")
                return "No pude guardar el cambio."
        return ("Comida encendida: /comer batido o /comer pastel." if on
                else "Comida apagada (/comer on para volver).")

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def registrar_herramientas(self, tools: Any) -> None:
        """`dar_de_comer` sobre este objeto (sonido + texto para el modelo)."""
        def dar_de_comer(args: Any = None, ctx: Any = None):
            return nc.herramienta(args, {"comida": self})
        try:
            tools.registrar_handler("dar_de_comer", dar_de_comer)
        except Exception:
            _log.exception("comida (patata): no pude registrar dar_de_comer")


__all__ = ("ComidaTerminal", "AYUDA")
