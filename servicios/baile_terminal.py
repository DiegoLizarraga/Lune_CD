"""
servicios/baile_terminal.py — Lune baila en la terminal (modo patata).

En patata no hay mascota: el baile es texto.

- Con música en una app permitida (el mismo detector que la app de ventanas,
  servicios/musica_detector.py, en su hilo), el TÍTULO de la ventana baila: una
  capa del título (`consola.titulo_capa("baile", …, 20)`) con kaomoji a 2
  cuadros por golpe: «ヽ(^o^)ﾉ ♪ Spotify · 124 BPM». Una alarma (60) o el modo
  juego (50) se ven por encima; el salvapantallas (10), por debajo.
- `/bailar [seg]` (o «baila» en el chat): baile a mano de N s (sin música, a
  120 BPM). Con ANSI pinta además la línea viva en el prompt de un reclamo de la
  consola, que se repinta sola:
      ♪ \\o/  Spotify · 124 BPM ▮▮▯ 0:42  (Enter para)
  y un Enter en vacío la para (lo que escribas sigue yendo al chat). Sin ANSI,
  solo el título.
- `/bailar auto on|off`, `/bailar apps`, `/bailar permitir X`, `/bailar quitar X`
  (se guardan en config: baile.auto, baile.apps) y `/parar`.
- Con un juego delante (`en_juego()`) no baila ni el detector llama a COM.
- Corte 9 (pulso de FUERA): `bailar_con(pulso_fn, titulo, duracion_fn, posicion_fn,
  al_parar=)` baila con el pulso que da otro (la canción de un baile de la biblioteca:
  servicios/bailes_terminal.BailesTerminal): «ヽ(^o^)ﾉ ♪ Senbonzakura · 154 BPM» y la línea
  viva con «0:42/3:15». Manda sobre el baile automático y el manual (que no lo pisan);
  Enter, /parar o el modo juego lo paran y avisan con `al_parar()`; `parar_externo()` es
  el dueño parándolo (sin aviso).

`paso(t)` es un paso de la animación (el hilo lo llama ~12 veces por segundo;
los tests, a mano). Sin Qt.
"""
from __future__ import annotations

import logging
import math
import shutil
import threading
import time
from typing import Any, Callable, Optional

from nucleo import baile as nb
from nucleo.consola import ancho_visible
from nucleo.pulso import Pulso, metronomo
from servicios.musica_detector import DetectorMusica, leer_config, normalizar_nombre_app

_log = logging.getLogger("lune.baile_terminal")

CAPA = "baile"
PRIORIDAD_TITULO = 20
PRIORIDAD_RECLAMO = -10        # una alarma o una aprobación se quedan antes el Enter
HZ_ANIM = 12
CONF_MIN = 0.3
VIGENCIA_PULSO_S = 12.0
SALTO_GOLPE = 0.25             # la fase que retrocede más que esto es un golpe nuevo
_SI = {"on", "si", "sí", "1", "true", "activar", "encender"}
_NO = {"off", "no", "0", "false", "desactivar", "apagar"}
AYUDA = ("/bailar [segundos] · /bailar auto on|off · /bailar apps · "
         "/bailar permitir <app> · /bailar quitar <app> · /parar")


def _mmss(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


class BaileTerminal:
    """El baile de patata (ver la cabecera del módulo)."""

    def __init__(self, consola: Any, config: Any, *, colores: Optional[dict] = None,
                 en_juego: Callable[[], bool] = lambda: False, detector: Any = None,
                 reloj: Callable[[], float] = time.monotonic):
        self.consola = consola
        self.config = config
        self.c = dict(colores) if colores else {}
        self._en_juego = en_juego
        self._detector = detector
        self._reloj = reloj
        self._lock = threading.RLock()
        self._iniciado = False
        self._bailando = False
        self._origen = ""
        self._t0 = 0.0
        self._t_fin: Optional[float] = None
        self._musica = False
        self._app = ""
        self._pausado = False
        self._pulso_det: Optional[Pulso] = None
        self._pulso_ref: Optional[Pulso] = None
        self._metro: Callable[[float], Pulso] = metronomo(120.0, reloj())
        self._golpes = 0
        self._fase_ant: Optional[float] = None
        self._cancelar: Any = None                 # reclamo de la línea viva (baile a mano con ANSI)
        self._ultima_linea: Optional[str] = None
        self._ultimo_titulo: Optional[str] = None
        self._kaomoji_linea = nb.es_windows_terminal()
        self._hilo: Optional[threading.Thread] = None
        self._despertar = threading.Event()
        self._externo: Optional[dict] = None       # corte 9: {pulso, titulo, duracion, posicion, al_parar}

    def _col(self, nombre: str) -> str:
        return self.c.get(nombre, "")

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        with self._lock:
            if self._iniciado:
                return
            self._iniciado = True
            if self._detector is None:
                self._detector = DetectorMusica(self.config, en_juego=self._juego)
            d = self._detector
        d.on_cambio = self._on_cambio
        d.on_pulso = self._on_pulso
        try:
            d.iniciar()
        except Exception:
            _log.exception("baile (patata): no pude arrancar el detector de música")

    def detener(self) -> None:
        with self._lock:
            self._iniciado = False
            d = self._detector
        self._parar_baile(silenciar=False)
        if d is not None:
            d.on_cambio = d.on_pulso = None
            try:
                d.detener()
            except Exception:
                pass
        h = self._hilo
        self._despertar.set()
        if h is not None and h is not threading.current_thread():
            h.join(1.0)

    @property
    def bailando(self) -> bool:
        return self._bailando

    @property
    def origen(self) -> str:
        return self._origen if self._bailando else ""

    @property
    def externo(self) -> bool:
        """¿Baila con un pulso de fuera (bailar_con)?"""
        return self._bailando and self._origen == "externo"

    # ── Del detector (su hilo) ───────────────────────────────────────────────────
    def _juego(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _on_cambio(self, activa: bool, app: str) -> None:
        arrancar = False
        parar = False
        with self._lock:
            self._musica = bool(activa)
            self._app = str(app or "") if activa else ""
            if not activa:
                self._pausado = False
                self._pulso_ref = None
                parar = self._bailando and self._origen == "auto"
            elif (not self._bailando and not self._pausado and self._iniciado
                  and leer_config(self.config)["auto"] and not self._juego()):
                arrancar = True
        if parar:
            self._parar_baile(silenciar=False)
        elif arrancar:
            self._empezar("auto")

    def _on_pulso(self, p: Any) -> None:
        if not isinstance(p, Pulso):
            return
        with self._lock:
            self._pulso_det = p
            if p.confianza >= CONF_MIN:
                self._pulso_ref = p

    # ── Baile ────────────────────────────────────────────────────────────────────
    def bailar(self, segundos: Any = None) -> str:
        """Baile a mano de N s. Devuelve el texto para la terminal."""
        if self._juego():
            return "En modo juego no bailo (luego sí)."
        with self._lock:
            ext = self._externo if self._bailando and self._origen == "externo" else None
        if ext is not None:
            return f"♪ Ya estoy bailando «{ext['titulo']}» (Enter o /parar para)."
        seg = nb.segundos_validos(segundos)
        self._empezar("manual", seg)
        if self._ansi():
            return f"♪ A bailar {seg} s. Enter (en vacío) o /parar para."
        return f"♪ Bailando {seg} s: mira el título de la ventana. /parar para."

    def parar(self, silenciar_auto: bool = True) -> bool:
        """Para. `silenciar_auto`: no vuelve a bailar sola hasta que la música se calle."""
        return self._parar_baile(silenciar=silenciar_auto)

    # ── Corte 9: pulso de fuera (la canción de un baile de la biblioteca) ─────────
    def bailar_con(self, pulso_fn: Callable[[], Any], titulo: str,
                   duracion_fn: Optional[Callable[[], Optional[float]]] = None,
                   posicion_fn: Optional[Callable[[], Optional[float]]] = None, *,
                   al_parar: Optional[Callable[[], Any]] = None) -> bool:
        """Baila con el pulso de `pulso_fn()` (Pulso, (bpm, fase[, energía]), {bpm, fase,
        energia} o None → metrónomo) y `titulo` en el título. `duracion_fn()` y
        `posicion_fn()` (s o None) ponen el reloj de la línea viva. `al_parar()` avisa si lo
        para la persona (Enter, /parar) o el modo juego. False en modo juego. Llamarlo otra
        vez cambia la canción sin cortar el baile. Las funciones se llaman desde el hilo de
        la animación con el cerrojo de este objeto: que no llamen a este objeto."""
        if self._juego():
            return False
        t = self._reloj()
        limpio = " ".join("".join(ch if ch.isprintable() else " " for ch in str(titulo or "")).split())[:48]
        with self._lock:
            if not self._bailando:
                self._bailando = True
                self._t0 = t
                self._golpes = 0
                self._fase_ant = None
                self._ultima_linea = None
            self._origen = "externo"
            self._t_fin = None
            self._externo = {"pulso": pulso_fn, "titulo": limpio or "♪", "duracion": duracion_fn,
                             "posicion": posicion_fn, "al_parar": al_parar}
            self._ultimo_titulo = None
            d = self._detector
        if d is not None:
            try:
                d.forzar_pulso(False)              # el pulso lo da la canción, no el detector
            except Exception:
                pass
        self._reclamar_linea(t)
        self.paso(t)
        self._arrancar_hilo()
        return True

    def parar_externo(self) -> bool:
        """El dueño del pulso de fuera lo para (fin de la canción, otra canción, /bailes
        parar): sin llamar a `al_parar`. False si no bailaba con él."""
        with self._lock:
            if not (self._bailando and self._origen == "externo"):
                self._externo = None
                return False
        return self._parar_baile(silenciar=False, avisar=False)

    def _ansi(self) -> bool:
        return bool(getattr(self.consola, "ansi", False))

    def _empezar(self, origen: str, segundos: Optional[int] = None) -> None:
        t = self._reloj()
        with self._lock:
            if not self._bailando:
                self._bailando = True
                self._t0 = t
                self._golpes = 0
                self._fase_ant = None
                ref = self._pulso_ref
                self._metro = metronomo(ref.bpm if ref else 120.0, t)
                self._ultimo_titulo = None
                self._ultima_linea = None
            if origen == "manual":
                self._origen = "manual"
                self._pausado = False
                self._t_fin = t + nb.segundos_validos(segundos)
            elif not self._origen:
                self._origen = "auto"
                self._t_fin = None
            d = self._detector
            manual = self._origen == "manual"
        if d is not None:
            try:
                d.forzar_pulso(manual)
            except Exception:
                pass
        if manual:
            self._reclamar_linea(t)
        self.paso(t)
        self._arrancar_hilo()

    def _parar_baile(self, silenciar: bool, avisar: bool = True) -> bool:
        with self._lock:
            estaba = self._bailando
            externo = self._externo if (estaba and self._origen == "externo") else None
            self._externo = None
            if silenciar and self._musica:
                self._pausado = True
            self._bailando = False
            self._origen = ""
            self._t_fin = None
            cancelar, self._cancelar = self._cancelar, None
            d = self._detector
            musica = self._musica
        if d is not None:
            try:
                d.forzar_pulso(False)
                if silenciar and musica:
                    d.silenciar_hasta_silencio()
            except Exception:
                pass
        if cancelar is not None:
            try:
                cancelar()
            except Exception:
                pass
        self._titulo_capa(None)
        self._despertar.set()
        if externo is not None and avisar and callable(externo.get("al_parar")):
            try:
                externo["al_parar"]()              # la canción de fuera también para
            except Exception:
                _log.exception("baile (patata): al_parar del pulso de fuera falló")
        return estaba

    def _reclamar_linea(self, t: float) -> None:
        """Baile a mano con ANSI: la línea viva va en el prompt de un reclamo."""
        if not self._ansi():
            return
        with self._lock:
            if self._cancelar is not None:
                return
        texto = self.linea(t)
        try:
            try:
                cancelar = self.consola.reclamar(self._enter, prompt=texto, prioridad=PRIORIDAD_RECLAMO)
            except TypeError:
                cancelar = self.consola.reclamar(self._enter, prompt=texto)
        except Exception:
            _log.debug("baile (patata): no pude reclamar la consola", exc_info=True)
            return
        with self._lock:
            if not self._bailando:
                pendiente = cancelar
            else:
                self._cancelar = cancelar
                self._ultima_linea = texto
                pendiente = None
        if pendiente is not None:
            pendiente()

    def _enter(self, linea: str):
        """La línea que llega con la línea del baile en el prompt."""
        if str(linea or "").strip():
            return False                       # lo escrito sigue al chat
        with self._lock:
            self._cancelar = None              # el reclamo se consume con esta línea
        self._parar_baile(silenciar=True)
        return True

    # ── Pulso, título y línea ────────────────────────────────────────────────────
    def _pulso_externo(self, t: float) -> Optional[Pulso]:
        """El pulso de `bailar_con` (None si no da uno válido: metrónomo)."""
        ext = self._externo if self._origen == "externo" else None
        if ext is None:
            return None
        try:
            r = ext["pulso"]() if callable(ext.get("pulso")) else None
        except Exception:
            return None
        if isinstance(r, Pulso):
            bpm, fase, energia = r.bpm, r.fase_en(t), r.energia
        elif isinstance(r, dict):
            bpm, fase, energia = r.get("bpm"), r.get("fase"), r.get("energia", 0.7)
        elif isinstance(r, (tuple, list)) and len(r) >= 2:
            bpm, fase, energia = r[0], r[1], (r[2] if len(r) > 2 else 0.7)
        else:
            return None
        try:
            bpm, fase, energia = float(bpm), float(fase), float(energia)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(x) for x in (bpm, fase, energia)) or bpm <= 0:
            return None
        return Pulso(max(40.0, min(240.0, bpm)), fase % 1.0, max(0.0, min(1.0, energia)), 1.0, t)

    def _reloj_externo(self) -> Optional[str]:
        """«0:42/3:15» (o «0:42») con la posición y la duración de la canción de fuera."""
        ext = self._externo if self._origen == "externo" else None
        if ext is None:
            return None

        def leer(clave):
            fn = ext.get(clave)
            try:
                v = fn() if callable(fn) else None
                v = float(v) if v is not None else None
            except Exception:
                return None
            return v if v is not None and math.isfinite(v) and v >= 0 else None
        pos, dur = leer("posicion"), leer("duracion")
        return _mmss(pos or 0) + (f"/{_mmss(dur)}" if dur else "")

    def _pulso_actual(self, t: float) -> Pulso:
        ext = self._pulso_externo(t)
        if ext is not None:
            return ext
        ref = self._pulso_ref
        if ref is not None and t - ref.t <= VIGENCIA_PULSO_S:
            det = self._pulso_det
            energia = det.energia if det is not None and t - det.t <= 2.0 else ref.energia
            return Pulso(ref.bpm, ref.fase_en(t), energia, ref.confianza, t)
        return self._metro(t)

    def _cuadro(self, p: Pulso, frames) -> str:
        """Dos cuadros por golpe."""
        f = p.fase % 1.0
        if self._fase_ant is not None and f < self._fase_ant - SALTO_GOLPE:
            self._golpes += 1
        self._fase_ant = f
        return frames[(self._golpes * 2 + int(f * 2)) % len(frames)]

    def titulo(self, t: Optional[float] = None) -> str:
        """El título mientras baila: «ヽ(^o^)ﾉ ♪ Spotify · 124 BPM»."""
        t = self._reloj() if t is None else t
        with self._lock:
            p = self._pulso_actual(t)
            cuadro = self._cuadro(p, nb.frames_ascii(True))
            app = self._app if self._musica else ""
            if self._externo is not None and self._origen == "externo":
                app = self._externo["titulo"]
        return f"{cuadro} ♪ " + (f"{app} · " if app else "") + f"{int(round(p.bpm))} BPM"

    def linea(self, t: Optional[float] = None) -> str:
        """«♪ \\o/  Spotify · 124 BPM ▮▮▯ 0:42  (Enter para)», ajustada al ancho."""
        t = self._reloj() if t is None else t
        with self._lock:
            p = self._pulso_actual(t)
            frames = nb.frames_ascii(self._kaomoji_linea)
            f = p.fase % 1.0
            golpes = self._golpes + (1 if (self._fase_ant is not None and f < self._fase_ant - SALTO_GOLPE) else 0)
            cuadro = frames[(golpes * 2 + int(f * 2)) % len(frames)]
            app = self._app if self._musica else ""
            reloj = _mmss(self._t_fin - t) if self._t_fin is not None else _mmss(t - self._t0)
            if self._externo is not None and self._origen == "externo":
                app = self._externo["titulo"]
                reloj = self._reloj_externo() or reloj
        n = int(round(min(1.0, max(0.0, p.energia)) * 3))
        barra = "▮" * n + "▯" * (3 - n)
        bpm = f"{int(round(p.bpm))} BPM"
        cy, dim, rst = self._col("cyan"), self._col("dim"), self._col("reset")
        cabeza = f"{cy}♪ {cuadro}{rst}  "
        cola = f"  {dim}(Enter para){rst}"
        ancho = self._ancho() - 1
        for medio in ((f"{app} · " if app else "") + f"{bpm} {barra} {reloj}",
                      f"{bpm} {barra} {reloj}", f"{bpm} {reloj}"):
            texto = cabeza + medio + cola
            if ancho_visible(texto) <= ancho:
                return texto
        corto = f"♪ {cuadro} {reloj}"
        return corto if ancho_visible(corto) <= ancho else corto[:max(1, ancho)]

    def _ancho(self) -> int:
        f = getattr(self.consola, "columnas", None)
        try:
            if callable(f):
                return max(10, int(f()))
        except Exception:
            pass
        return max(10, shutil.get_terminal_size((80, 24)).columns)

    def _titulo_capa(self, texto: Optional[str]) -> None:
        capa = getattr(self.consola, "titulo_capa", None)
        try:
            if callable(capa):
                capa(CAPA, texto, PRIORIDAD_TITULO)
            elif texto:
                self.consola.titulo(texto)
        except Exception:
            _log.debug("baile (patata): no pude poner el título", exc_info=True)
        if texto is None:
            with self._lock:
                self._ultimo_titulo = None

    # ── Animación ────────────────────────────────────────────────────────────────
    def paso(self, t: Optional[float] = None) -> None:
        """Un paso: fin del baile a mano, título y línea viva (solo si cambian)."""
        t = self._reloj() if t is None else t
        with self._lock:
            if not self._bailando:
                return
            juego = self._juego()
            fin = self._t_fin is not None and t >= self._t_fin
            seguir_auto = fin and self._musica and not self._pausado and leer_config(self.config)["auto"]
        if juego:
            self._parar_baile(silenciar=False)
            return
        if fin and not seguir_auto:
            self._parar_baile(silenciar=False)
            return
        if seguir_auto:
            with self._lock:                   # acabó el baile a mano con música: sigue sola
                self._origen = "auto"
                self._t_fin = None
                cancelar, self._cancelar = self._cancelar, None
            if cancelar is not None:
                try:
                    cancelar()
                except Exception:
                    pass
            d = self._detector
            if d is not None:
                try:
                    d.forzar_pulso(False)
                except Exception:
                    pass
        titulo = self.titulo(t)
        with self._lock:
            poner_titulo = titulo != self._ultimo_titulo
            self._ultimo_titulo = titulo
            cancelar = self._cancelar
        if poner_titulo:
            self._titulo_capa(titulo)
        cambiar = getattr(cancelar, "cambiar_prompt", None) if cancelar is not None else None
        if callable(cambiar):
            linea = self.linea(t)
            with self._lock:
                nueva = linea != self._ultima_linea
                self._ultima_linea = linea
            if nueva:
                try:
                    cambiar(linea)
                except Exception:
                    pass

    def _arrancar_hilo(self) -> None:
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._despertar.clear()
            self._hilo = threading.Thread(target=self._animar, name="lune-baile-terminal", daemon=True)
            self._hilo.start()

    def _animar(self) -> None:
        try:
            while self._bailando:
                try:
                    self.paso()
                except Exception:
                    _log.exception("baile (patata): fallo en la animación")
                self._despertar.wait(1.0 / HZ_ANIM)
                self._despertar.clear()
        finally:
            with self._lock:
                if self._hilo is threading.current_thread():
                    self._hilo = None

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        """/bailar … y /parar. None si la línea no es suya."""
        texto = str(linea or "").strip()
        bajo = texto.lower()
        if bajo in ("/parar", "/parar baile", "/parar_baile"):
            return "♪ Vale, dejo de bailar." if self.parar(silenciar_auto=True) else "No estaba bailando."
        if not (bajo == "/bailar" or bajo.startswith("/bailar ")):
            return None
        args = texto.split()[1:]
        if not args:
            return self.bailar()
        a0 = args[0].lower()
        if a0.isdigit():
            return self.bailar(int(a0))
        if a0 == "auto":
            return self._cmd_auto(args[1:])
        if a0 == "apps":
            return self._cmd_apps()
        if a0 in ("permitir", "añadir", "anadir", "+"):
            return self._cmd_permitir(" ".join(args[1:]))
        if a0 in ("quitar", "borrar", "-"):
            return self._cmd_quitar(" ".join(args[1:]))
        return f"Uso: {AYUDA}"

    def _guardar(self, clave: str, valor: Any) -> bool:
        if self.config is None:
            return False
        try:
            self.config.set("baile", clave, valor)
            return True
        except Exception:
            _log.exception("baile (patata): no pude guardar baile.%s", clave)
            return False

    def _cmd_auto(self, resto) -> str:
        actual = leer_config(self.config)["auto"]
        if not resto:
            return (f"Baile automático con la música: {'sí' if actual else 'no'}. "
                    "Cámbialo con /bailar auto on|off.")
        v = resto[0].lower()
        if v in _SI:
            nuevo = True
        elif v in _NO:
            nuevo = False
        else:
            return "Usa /bailar auto on o /bailar auto off."
        self._guardar("auto", nuevo)
        if not nuevo and self._bailando and self._origen == "auto":
            self._parar_baile(silenciar=False)
        d = self._detector
        if d is not None and nuevo:
            try:
                d.pedir_sondeo()
            except Exception:
                pass
        return ("♪ Vale: bailaré sola cuando suene música en una app permitida." if nuevo
                else "Vale: ya no bailo sola con la música (/bailar sigue funcionando).")

    def _apps(self) -> list:
        return list(leer_config(self.config)["apps"])

    def _cmd_apps(self) -> str:
        apps = self._apps()
        sonando = []
        d = self._detector
        if d is not None:
            try:
                sonando = list(d.apps_sonando())
                d.pedir_sondeo()
            except Exception:
                sonando = []
        txt = "Apps que cuentan como música: " + (", ".join(apps) if apps else "(ninguna)")
        txt += "\nSuenan ahora: " + (", ".join(sonando) if sonando else "nada")
        if d is None or getattr(d, "disponible", None) is False:
            txt += "\n(no puedo medir el audio de las apps en este equipo: sin baile automático)"
        return txt

    def _cmd_permitir(self, nombre: str) -> str:
        n = normalizar_nombre_app(nombre)
        if not n:
            return "Dime el nombre de la app, p. ej. /bailar permitir Spotify."
        apps = self._apps()
        if n.lower() in {a.lower() for a in apps}:
            return f"{n} ya cuenta como música."
        apps.append(n)
        self._guardar("apps", apps)
        return f"♪ Hecho: {n} cuenta como música."

    def _cmd_quitar(self, nombre: str) -> str:
        n = normalizar_nombre_app(nombre)
        if not n:
            return "Dime el nombre de la app, p. ej. /bailar quitar vlc."
        apps = self._apps()
        nuevas = [a for a in apps if a.lower() != n.lower()]
        if len(nuevas) == len(apps):
            return f"{n} no estaba en la lista."
        self._guardar("apps", nuevas)
        return f"Hecho: {n} ya no cuenta como música."


__all__ = ("BaileTerminal", "CAPA", "PRIORIDAD_TITULO", "PRIORIDAD_RECLAMO", "AYUDA")
