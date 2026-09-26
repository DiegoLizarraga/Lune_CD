"""
nucleo/asiento.py — Cuándo se sienta la mascota en una ventana o en la barra de
tareas, dónde la clava y cuándo se levanta. Sin Qt ni Win32: puro y con el reloj
inyectado, así se prueba en seco.

Es el port de `AvatarWindowHandler.cs` (TrySnap, PinToTarget,
IsStillNearSnappedWindow) y `AvatarTaskbarController.cs` (la «zona rosa») de
Mate-Engine, con los valores de su escena. El adaptador Qt que lee las ventanas
y mueve la de la mascota es `ui/asiento_qt.py` (ControlAsiento).

COORDENADAS
-----------
Todo en px FÍSICOS del escritorio (crítica c.16: con DPI mixto las coordenadas
lógicas de Qt no son continuas). Los parámetros de `ParamsAsiento` en px son
LÓGICOS y se multiplican por el `dpr` de la mascota (kw `dpr` de cada método);
el radio de la sonda sale del alto físico de la ventana de la mascota
(`radio_sonda`). Las páginas dan sus puntos en px lógicos relativos a su
ventana: `punto_fisico` los pasa a físicos del escritorio.

LA SONDA Y EL ASIENTO
---------------------
- sonda: el punto que busca un borde (en ME, las caderas −0.375; en la VRM de
  Lune, caderas − 0.23·altura; en la animada y los sprites, el centro de abajo
  de la figura).
- asiento: el punto que queda clavado en el borde (media de los muslos − 0.12·
  altura, el SeatWorldGuess de ME; en la animada y los sprites, igual que la
  sonda). `offset_px` (físico) lo sube o lo baja.

REGLAS (de ME, valores de la escena)
------------------------------------
- Ventanas: encaja arrastrando ≥ 0.5 s y ≥ 10 px cuando la sonda está dentro
  de [izq, der] del objetivo y a ≤ radio de su borde superior y ese punto no
  está tapado por otra ventana. Tras soltarse arrastrando: enfriamiento de
  0.275 s, zona de guardia (hasta que la sonda sale de 1.15·radio) y bloqueo
  vertical (hasta alejarse max(banda, radio) del borde en vertical).
- Barra: la zona rosa de 100×10 px (−5 px) alrededor de la sonda toca la franja
  superior de 5 px de la barra de abajo → encaja SIN agarre. Tras levantarse
  de la barra, la zona tiene que subir 20 px por encima de la barra para volver
  a encajar (histéresis).
- Sentada y arrastrando: la y queda fija y la x sigue al cursor (desliza,
  actualizando `frac`). Durante 0.43 s tras encajar no se suelta; después se
  suelta si el cursor se aleja en vertical más de max(banda, radio) de donde
  estaba (barra: max(20, radio)) o si el asiento sale por un lado del objetivo.
  (ME mira además la sonda en vertical; aquí la posición libre se mueve igual
  que el cursor y la sonda no queda en el borde al estar sentada, así que la
  comprobación del cursor basta y no suelta sola en reposo.)
- Clavar (`pin`): el asiento va a (izq + frac·ancho, arriba + offset) del
  objetivo. Justo tras encajar se desliza con SmoothDamp (0.075 s, 8000 px/s);
  al llegar a ≤ 1 px queda rígida, y si el objetivo se mueve el suavizado se
  cancela (rígida). Arrastrando, el asiento nunca se hunde bajo el borde
  (regla anti-hundimiento de ME).
- 4 poses de ventana al azar (variante 0..3); en la barra, la 0.

`herramienta(args, ctx)` es el handler de `mascota_sentarse`
({"sitio": "barra" | "ventana" | "bajar"}) con `ctx["asiento"]` (el
ControlAsiento) y `ctx["en_ui"]` (corre en el hilo de Qt).
"""
from __future__ import annotations

import dataclasses
import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Optional, Sequence, Tuple, Union

from nucleo.fisica import clamp, smooth_damp

Punto = Tuple[float, float]


class Rect(NamedTuple):
    """Rectángulo en px físicos (`der` y `abajo` fuera). Igual que win_pantalla.Rect."""
    izq: int
    arriba: int
    der: int
    abajo: int

    @property
    def ancho(self) -> int:
        return self.der - self.izq

    @property
    def alto(self) -> int:
        return self.abajo - self.arriba


def _rect(r) -> Rect:
    return r if isinstance(r, Rect) else Rect(*(int(round(v)) for v in r))


@dataclass(frozen=True)
class ParamsAsiento:
    """Valores de la escena de ME. Los px son LÓGICOS (× dpr de la mascota)."""
    hold_s: float = 0.5                  # agarre mínimo antes de poder sentarse (ventanas)
    min_px: float = 10                   # arrastre mínimo (px)
    radio_frac: float = 0.09             # radio de la sonda = 9 % del alto físico de la ventana…
    radio_min: float = 18                # …recortado a [18, 64] px lógicos
    radio_max: float = 64
    banda_px: float = 16                 # banda vertical (ME: unsnapVerticalBand)
    latch_s: float = 0.43                # tras encajar no se suelta (8 + 18 frames a 60 fps)
    cooldown_s: float = 0.275            # tras soltarse arrastrando
    guardia_factor: float = 1.15         # zona de guardia = 1.15 · radio (150/130 en ME)
    smooth_t: float = 0.075              # SmoothDamp justo tras encajar
    vmax: float = 8000.0                 # px/s
    zona_barra: Tuple[float, float, float] = (100, 10, -5)   # ancho, alto, desplazamiento vertical
    franja_barra: float = 5              # franja superior de la barra que cuenta
    histeresis_barra: float = 20
    tol_pc: int = 2                      # ±px para «pantalla completa» (físicos)
    variantes: int = 4                   # poses de ventana (0..3)


@dataclass(frozen=True)
class Objetivo:
    hwnd: int
    es_barra: bool
    rect: Rect


@dataclass(frozen=True)
class Snap:
    """Sentada en `objetivo`, en la fracción `frac` de su ancho."""
    objetivo: Objetivo
    frac: float
    modo: str                  # "barra" | "ventana"
    variante: int              # pose (ventana 0..3; barra 0)
    cursor_y: int              # y del cursor al encajar o al empezar a arrastrarla sentada


@dataclass(frozen=True)
class Desnap:
    motivo: str


@dataclass(frozen=True)
class Mover:
    """Nueva posición (esquina superior izquierda, px físicos) de la ventana de la mascota."""
    x: int
    y: int


MOTIVOS = ("arrastre", "cerrada", "minimizada", "maximizada", "pantalla_completa", "cloaked", "oculta",
           "fuera", "cede", "usuario")
MODO_BARRA, MODO_VENTANA = "barra", "ventana"
SITIOS = ("barra", "ventana", "bajar")


# ── Geometría ──────────────────────────────────────────────────────────────────

def radio_sonda(alto_fisico: float, dpr: float = 1.0, p: ParamsAsiento = ParamsAsiento()) -> float:
    """Radio de la sonda en px físicos: 9 % del alto de la ventana, en [18, 64]·dpr."""
    d = dpr if dpr and dpr > 0 else 1.0
    return clamp(p.radio_frac * max(0.0, float(alto_fisico)), p.radio_min * d, p.radio_max * d)


def zona_barra(sonda: Punto, dpr: float, p: ParamsAsiento = ParamsAsiento()) -> Rect:
    """La zona rosa de ME (100×10 px, desplazada −5 px) centrada en la sonda, en px físicos."""
    d = dpr if dpr and dpr > 0 else 1.0
    ancho, alto, desp = p.zona_barra
    x, y = float(sonda[0]), float(sonda[1])
    return Rect(int(round(x - ancho * d / 2)), int(round(y + desp * d)),
                int(round(x + ancho * d / 2)), int(round(y + (desp + alto) * d)))


def toca_barra(zona, barra, franja_px: float) -> bool:
    """¿La zona toca la franja superior (`franja_px`) de la barra? (Rect.Overlaps de Unity)."""
    z, b = _rect(zona), _rect(barra)
    arriba, abajo = b.arriba, b.arriba + franja_px
    return z.der > b.izq and z.izq < b.der and z.abajo > arriba and z.arriba < abajo


def punto_fisico(rect_mascota_fisico, rel_logico, dpr) -> Tuple[int, int]:
    """Un punto de la página (px lógicos relativos a su ventana) en px físicos del escritorio."""
    r = _rect(rect_mascota_fisico)
    d = dpr if dpr and dpr > 0 else 1.0
    return int(round(r.izq + float(rel_logico[0]) * d)), int(round(r.arriba + float(rel_logico[1]) * d))


def _campo(c: Any, nombre: str, defecto: Any = None) -> Any:
    return c.get(nombre, defecto) if isinstance(c, Mapping) else getattr(c, nombre, defecto)


# ── La máquina ─────────────────────────────────────────────────────────────────

class MaquinaAsiento:
    """El estado de «sentada» (ver la cabecera del módulo).

    Uso en un arrastre manual (VRM y animada): `al_pulsar` al empezar,
    `al_arrastrar` en cada movimiento (Snap = acaba de sentarse; Desnap = se
    soltó; None = nada nuevo) y `pin` para saber dónde poner la ventana mientras
    está sentada; `al_soltar` al acabar. En un arrastre nativo (sprites) solo
    `al_pulsar` y `al_soltar(sonda=…, candidatas=…)`, que es quien encaja.
    Sentada y quieta: `pin` y `comprobar` en cada tic.

    `offset_px` (físico) es el ajuste vertical del asiento (avatar.sentarse_offset_px × dpr).
    """

    def __init__(self, params: ParamsAsiento = ParamsAsiento(), *, azar: Optional[random.Random] = None):
        self.p = params
        self._azar = azar if azar is not None else random.Random()
        self.sentada: Optional[Snap] = None
        self.offset_px = 0
        self._arrastrando = False
        self._t0 = 0.0
        self._c0: Optional[Punto] = None
        self._cooldown_hasta = -math.inf
        self._guardia: Optional[Tuple[float, float, float]] = None      # (x, y, r²)
        self._reciente = False
        self._ultimo_borde: Optional[int] = None
        self._barra_bloqueada = False
        self._latch_hasta = -math.inf
        self._suave = False
        self._vel = (0.0, 0.0)
        self._rect_prev: Optional[Rect] = None

    # ── Consultas ──────────────────────────────────────────────────────────────
    @property
    def arrastrando(self) -> bool:
        return self._arrastrando

    @property
    def suavizando(self) -> bool:
        """¿Está deslizándose con SmoothDamp hacia su sitio? (tras encajar)."""
        return self.sentada is not None and self._suave

    # ── Arrastre ───────────────────────────────────────────────────────────────
    def al_pulsar(self, t: float, cursor: Optional[Punto]) -> None:
        """Empieza un arrastre (el umbral de la mascota ya se pasó)."""
        self._arrastrando = True
        self._t0 = float(t)
        self._c0 = (float(cursor[0]), float(cursor[1])) if cursor else None
        self._latch_hasta = -math.inf                  # al volver a cogerla sentada no hay bloqueo
        if self.sentada is not None and cursor:
            self.sentada = dataclasses.replace(self.sentada, cursor_y=int(round(cursor[1])))

    def al_soltar(self, t: float, *, sonda: Optional[Punto] = None, radio: float = 0,
                  candidatas: Iterable[Any] = (), ocluida: Optional[Callable[[int, int, int], bool]] = None,
                  cursor: Optional[Punto] = None, dpr: float = 1.0, asiento: Optional[Punto] = None
                  ) -> Optional[Snap]:
        """Acaba el arrastre. Con `sonda` (sprites, arrastre nativo) intenta sentarse
        ahí mismo con las mismas reglas (agarre ≥ 0.5 s y ≥ 10 px si llega `cursor`)."""
        snap = None
        try:
            if self.sentada is None and sonda is not None:
                snap = self._intentar(float(t), cursor, sonda, float(radio), list(candidatas or ()), ocluida,
                                      dpr, asiento)
        finally:
            self._arrastrando = False
            self._reciente = False
            self._c0 = None
        return snap

    def al_arrastrar(self, t: float, cursor: Optional[Punto], sonda: Punto, radio: float,
                     candidatas: Iterable[Any], ocluida: Optional[Callable[[int, int, int], bool]],
                     *, dpr: float = 1.0, asiento: Optional[Punto] = None) -> Union[Snap, Desnap, None]:
        """Un paso del arrastre manual con la posición LIBRE (donde estaría la
        ventana si no estuviera sentada): `sonda` y `asiento` en px físicos del
        escritorio, `radio` en px físicos. Snap / Desnap / None."""
        t = float(t)
        if not self._arrastrando:
            self.al_pulsar(t, cursor)
        cands = list(candidatas or ())
        sx, sy = float(sonda[0]), float(sonda[1])
        vband = max(self.p.banda_px * self._d(dpr), float(radio))
        if self._reciente and self._ultimo_borde is not None and abs(sy - self._ultimo_borde) >= vband:
            self._reciente = False                     # ya se alejó del borde en vertical
        if self.sentada is None:
            return self._intentar(t, cursor, sonda, float(radio), cands, ocluida, dpr, asiento)
        s = self.sentada
        c = self._buscar(s.objetivo, cands)
        if c is not None:
            obj = dataclasses.replace(s.objetivo, rect=_rect(_campo(c, "rect")))
            s = self.sentada = dataclasses.replace(s, objetivo=obj)
        if self._sigue_cerca(t, cursor, sonda, asiento, float(radio), c, dpr):
            r = s.objetivo.rect
            px = float((asiento or sonda)[0])
            frac = clamp((px - r.izq) / max(1, r.ancho), 0.0, 1.0)
            self.sentada = dataclasses.replace(s, frac=frac)
            return None
        r = float(radio) * self.p.guardia_factor
        self._guardia = (sx, sy, r * r)
        return self._soltar(t, "arrastre")

    # ── Sentarse y levantarse sin arrastre ─────────────────────────────────────
    def sentar_directo(self, objetivo: Objetivo, *, frac: float = 0.5, variante: Optional[int] = None) -> Snap:
        """Sentarse ya (herramienta, acción del menú o reanudar tras una cesión):
        se desliza hasta su sitio con SmoothDamp."""
        obj = objetivo if isinstance(objetivo, Objetivo) else Objetivo(
            int(_campo(objetivo, "hwnd", 0)), bool(_campo(objetivo, "es_barra", False)), _rect(_campo(objetivo, "rect")))
        obj = dataclasses.replace(obj, rect=_rect(obj.rect))
        modo = MODO_BARRA if obj.es_barra else MODO_VENTANA
        if variante is None:
            variante = 0 if obj.es_barra else self._azar.randrange(max(1, self.p.variantes))
        self.sentada = Snap(obj, clamp(float(frac), 0.0, 1.0), modo, int(variante), 0)
        self._guardia = None
        self._reciente = False
        self._ultimo_borde = obj.rect.arriba
        self._latch_hasta = -math.inf
        self.suavizar()
        return self.sentada

    def levantar(self, motivo: str) -> Desnap:
        """Se levanta por `motivo` (cerrada, usuario, cede…). Se queda donde está."""
        obj = self.sentada.objetivo if self.sentada is not None else None
        self.sentada = None
        self._parar_suavizado()
        self._rect_prev = None
        if obj is not None:
            if obj.es_barra:
                self._barra_bloqueada = True
            if self._arrastrando:
                self._reciente = True
                self._ultimo_borde = obj.rect.arriba
        return Desnap(str(motivo) if motivo in MOTIVOS else "usuario")

    def anular(self, t: float) -> None:
        """Deshace un encaje que la tabla de prioridades no permitió (con enfriamiento)."""
        if self.sentada is not None:
            self.levantar("cede")
        self._cooldown_hasta = float(t) + self.p.cooldown_s

    def comprobar(self, estado: str) -> Optional[Desnap]:
        """Con el estado de la ventana objetivo ("ok", "minimizada"…): Desnap si hay que levantarse."""
        if self.sentada is None or estado == "ok":
            return None
        return self.levantar(estado if estado in MOTIVOS else "cerrada")

    def suavizar(self) -> None:
        """Vuelve a deslizar con SmoothDamp hasta el sitio (p. ej. al llegar el
        asiento medido con la pose completa: el recalibrado de ME en un paso)."""
        self._suave = self.sentada is not None
        self._vel = (0.0, 0.0)
        self._rect_prev = None

    # ── Clavar ─────────────────────────────────────────────────────────────────
    def pin(self, t: float, dt: float, rect_objetivo, asiento_rel: Punto, rect_mascota, *, arrastrando: bool,
            cursor: Optional[Punto] = None, dpr: float = 1.0) -> Union[Mover, Desnap, None]:
        """Dónde poner la ventana de la mascota para que el asiento (`asiento_rel`,
        px LÓGICOS relativos a su ventana) quede en el borde del objetivo.

        `rect_objetivo` None → la ventana ya no está (Desnap "cerrada"). Mover si
        hay que moverla; None si ya está en su sitio. `cursor` no se usa (el
        deslizamiento lo lleva `al_arrastrar`)."""
        s = self.sentada
        if s is None:
            return None
        if rect_objetivo is None:
            return self.levantar("cerrada")
        ro, rm = _rect(rect_objetivo), _rect(rect_mascota)
        if ro != s.objetivo.rect:
            s = self.sentada = dataclasses.replace(s, objetivo=dataclasses.replace(s.objetivo, rect=ro))
        if self._rect_prev is not None and ro != self._rect_prev:
            self._parar_suavizado()                    # el objetivo se movió: rígida, sin retraso
        self._rect_prev = ro
        ax, ay = punto_fisico(rm, asiento_rel, dpr)
        dx = ro.izq + s.frac * max(1, ro.ancho) - ax
        dy = ro.arriba + int(self.offset_px) - ay
        tx, ty = rm.izq + int(round(dx)), rm.arriba + int(round(dy))
        if not self._suave:
            return Mover(tx, ty) if (tx, ty) != (rm.izq, rm.arriba) else None
        paso = float(dt) if dt and dt > 0 else 1.0 / 60.0
        paso = min(paso, 0.1)
        nx, vx = smooth_damp(float(rm.izq), float(tx), self._vel[0], self.p.smooth_t, self.p.vmax, paso)
        ny, vy = smooth_damp(float(rm.arriba), float(ty), self._vel[1], self.p.smooth_t, self.p.vmax, paso)
        self._vel = (vx, vy)
        if arrastrando:
            hundido = ny - ty                          # > 0: el asiento quedaría bajo el borde
            if hundido > 0:
                ny -= min(self.p.vmax * paso, max(0.0, hundido - 1.0))
        ix, iy = int(round(nx)), int(round(ny))
        if abs(tx - ix) <= 1 and abs(ty - iy) <= 1:
            ix, iy = tx, ty
            self._parar_suavizado()
        return Mover(ix, iy) if (ix, iy) != (rm.izq, rm.arriba) else None

    # ── Internos ───────────────────────────────────────────────────────────────
    @staticmethod
    def _d(dpr: float) -> float:
        return dpr if dpr and dpr > 0 else 1.0

    def _parar_suavizado(self) -> None:
        self._suave = False
        self._vel = (0.0, 0.0)

    @staticmethod
    def _buscar(obj: Objetivo, candidatas: Sequence[Any]) -> Any:
        for c in candidatas:
            if bool(_campo(c, "es_barra", False)) != obj.es_barra:
                continue
            if obj.es_barra or int(_campo(c, "hwnd", 0)) == obj.hwnd:
                return c
        return None

    def _sigue_cerca(self, t: float, cursor: Optional[Punto], sonda: Punto, asiento: Optional[Punto],
                     radio: float, c: Any, dpr: float) -> bool:
        """IsStillNearSnappedWindow: bloqueo tras encajar, asiento dentro por los
        lados y cursor dentro de la banda vertical."""
        if t < self._latch_hasta:
            return True
        if c is None:
            return False
        s = self.sentada
        r = s.objetivo.rect
        d = self._d(dpr)
        banda = (self.p.histeresis_barra if s.objetivo.es_barra else self.p.banda_px) * d
        vband = max(banda, radio)
        px, py = (asiento or sonda)
        if not (r.izq <= float(px) <= r.der):
            return False
        if cursor:
            return abs(float(cursor[1]) - s.cursor_y) <= vband
        return abs(float(py) - (r.arriba + int(self.offset_px))) <= vband

    def _soltar(self, t: float, motivo: str) -> Desnap:
        self._cooldown_hasta = t + self.p.cooldown_s
        d = self.levantar(motivo)
        return d

    def _intentar(self, t: float, cursor: Optional[Punto], sonda: Punto, radio: float, cands: Sequence[Any],
                  ocluida: Optional[Callable[[int, int, int], bool]], dpr: float,
                  asiento: Optional[Punto]) -> Optional[Snap]:
        """TrySnap de ME (ventanas) + la zona rosa (barra)."""
        if t < self._cooldown_hasta:
            return None
        d = self._d(dpr)
        sx, sy = float(sonda[0]), float(sonda[1])
        px = float((asiento or sonda)[0])
        # Barra: la zona rosa, sin agarre y con histéresis.
        zona = zona_barra((sx, sy), d, self.p)
        for c in cands:
            if not _campo(c, "es_barra", False):
                continue
            rb = _rect(_campo(c, "rect"))
            if self._barra_bloqueada:
                if zona.abajo < rb.arriba - self.p.histeresis_barra * d:
                    self._barra_bloqueada = False
                else:
                    continue
            if toca_barra(zona, rb, self.p.franja_barra * d):
                return self._encajar(t, c, cursor, px)
        # Ventanas: agarre, arrastre mínimo, guardia y bloqueo vertical.
        if t - self._t0 < self.p.hold_s:
            return None
        if cursor and self._c0 is not None:
            minimo = self.p.min_px * d
            if abs(cursor[0] - self._c0[0]) < minimo and abs(cursor[1] - self._c0[1]) < minimo:
                return None
        if self._guardia is not None:
            gx, gy, r2 = self._guardia
            if (sx - gx) ** 2 + (sy - gy) ** 2 < r2:
                return None
            self._guardia = None
        if self._reciente and self._ultimo_borde is not None:
            if abs(sy - self._ultimo_borde) < max(self.p.banda_px * d, radio):
                return None
        for c in cands:
            if _campo(c, "es_barra", False):
                continue
            r = _rect(_campo(c, "rect"))
            if not (r.izq <= sx <= r.der):
                continue
            if abs(sy - r.arriba) > radio:
                continue
            if ocluida is not None:
                try:
                    if ocluida(int(_campo(c, "hwnd", 0)), int(round(sx)), int(round(sy))):
                        continue
                except Exception:
                    continue
            return self._encajar(t, c, cursor, px)
        return None

    def _encajar(self, t: float, c: Any, cursor: Optional[Punto], px: float) -> Snap:
        obj = Objetivo(int(_campo(c, "hwnd", 0)), bool(_campo(c, "es_barra", False)), _rect(_campo(c, "rect")))
        frac = clamp((px - obj.rect.izq) / max(1, obj.rect.ancho), 0.0, 1.0)
        modo = MODO_BARRA if obj.es_barra else MODO_VENTANA
        variante = 0 if obj.es_barra else self._azar.randrange(max(1, self.p.variantes))
        cy = int(round(cursor[1])) if cursor else 0
        self.sentada = Snap(obj, frac, modo, variante, cy)
        self._guardia = None
        self._reciente = False
        self._ultimo_borde = obj.rect.arriba
        self._latch_hasta = t + self.p.latch_s
        self.suavizar()
        return self.sentada


# ── Herramienta del modelo (mascota_sentarse) ──────────────────────────────────

TEXTO_SIN_CONTROL = "Ahora mismo no puedo sentarme aquí: necesito la mascota a la vista."


def _de_ctx(ctx: Any, clave: str) -> Any:
    """ctx[clave] (dict) o ctx.clave (objeto), también dentro de ctx['contexto']."""
    if ctx is None:
        return None
    v = ctx.get(clave) if isinstance(ctx, Mapping) else getattr(ctx, clave, None)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        c = ctx.get("contexto")
        v = c.get(clave) if isinstance(c, Mapping) else getattr(c, clave, None)
    return v


def _en_ui(ctx: Any, fn: Callable[[], Any]) -> Any:
    en_ui = _de_ctx(ctx, "en_ui")
    return en_ui(fn) if callable(en_ui) else fn()


def herramienta(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `mascota_sentarse` ({"sitio": "barra" | "ventana" | "bajar"})."""
    asiento = _de_ctx(ctx, "asiento")
    if asiento is None or not callable(getattr(asiento, "sentar", None)):
        return False, TEXTO_SIN_CONTROL
    args = args if isinstance(args, Mapping) else {}
    sitio = str(args.get("sitio") or "").strip().lower()
    if sitio not in SITIOS:
        return False, "¿Dónde me siento? Dime «barra», «ventana» o «bajar»."
    try:
        if sitio == "bajar":
            ok = _en_ui(ctx, lambda: asiento.bajar("usuario"))
            return "Vale, ya me bajé." if ok else "No estaba sentada."
        res = _en_ui(ctx, lambda: asiento.sentar(sitio))
    except Exception as e:
        return False, f"No pude sentarme: {e}"[:300]
    if isinstance(res, tuple) and len(res) == 2:
        ok, texto = bool(res[0]), str(res[1] or "")
    else:
        ok, texto = bool(res), ""
    if ok:
        return texto or ("Me senté en la barra de tareas." if sitio == "barra" else "Me senté en una ventana.")
    return False, texto or "Ahora no puedo sentarme."


__all__ = (
    "ParamsAsiento", "Rect", "Objetivo", "Snap", "Desnap", "Mover", "MaquinaAsiento", "MOTIVOS", "SITIOS",
    "MODO_BARRA", "MODO_VENTANA", "radio_sonda", "zona_barra", "toca_barra", "punto_fisico", "herramienta",
    "TEXTO_SIN_CONTROL",
)
