"""
nucleo/comida.py — La comida de Lune (el AvatarFoodController de Mate-Engine).

Con el clic central sobre la asistente (radial «secundario»), la bandeja o la
herramienta `dar_de_comer`, sale un batido o un pastel que sigue al cursor.
Pasarlo por la cabeza de Lune es darle de comer: trago o mordisco con un tono
al azar, cara feliz y, a veces, una frase.

Lo de aquí es la parte sin Qt (la usan ui/comida_qt.py y servicios/comida_terminal.py):

- `CATALOGO`: batido (fresa, mango, matcha) y pastel (chocolate, fresa, limón,
  vainilla). En ME eran 3 smoothies y 4 tartas; aquí cada variante es un color
  del dibujo procedural (sin PNG).
- `GestorComida`: qué hay en la mano y el acierto sobre la cabeza.
    · `alternar(id)` → aparece | guarda | cambia. ME guardaba la comida al pedir
      OTRA (ToggleById, :208-217); aquí pedir otra la cambia.
    · `al_mover(t, p0, p1, cabeza)`: el tramo del cursor de este paso contra el
      círculo de la cabeza (segmento-círculo: una pasada rápida también cuenta),
      por FLANCO (entrar, no quedarse dentro) y con 0.35 s de enfriamiento, como
      HeadInteractCheck (:174-188).
    · `reaccion()` → trago_N o mordisco_N, tono 0.65–1.25 (PlayRandom, :351-360),
      estado `happy` 2.5 s y el texto «*glup glup* (batido de mango)».
    · `caducada(t)`: D4, se guarda sola a los 2 min sin moverla (ME no la guarda
      nunca; sin foco no hay Esc para quitarla del cursor).
- `BalanceoComida`: el vaivén al moverla (UpdateSway + Spring, :143-172 y
  :362-368) con los valores de la escena: sensibilidad 4, 0.7/0.7 grados por px,
  topes 25°/10°, muelle de 1 Hz con ζ 0.35 y mezcla de 8/s.
- `SonidosComida`: los sonidos por el Mezclador (canal `sfx`) con el pack de
  `avatar.pack_sonidos` (eventos comida_aparece, comida_capa, beber, comer y el
  opcional comida_guarda), el volumen `avatar.volumen_sfx` y callados en modo
  juego si `juego.silenciar`.
- `herramienta(args, ctx)`: handler de `dar_de_comer` ({comida: batido|pastel}).

Sin Qt: reloj, azar, mezclador y el lanzador del sonido son inyectables.
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from nucleo.fisica import Muelle, clamp

_log = logging.getLogger("lune.comida")


# ── Catálogo ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Variante:
    id: str
    nombre: str                 # en minúscula: «batido de mango»
    color: str                  # #RRGGBB del dibujo (líquido o cobertura)


@dataclass(frozen=True)
class Comida:
    id: str
    nombre: str
    tipo: str                   # beber | comer (el evento del pack y de la asistente)
    variantes: Tuple[Variante, ...]


CATALOGO: Dict[str, Comida] = {
    "batido": Comida("batido", "Batido", "beber", (
        Variante("fresa", "fresa", "#FF6FA8"),
        Variante("mango", "mango", "#FFB547"),
        Variante("matcha", "matcha", "#8BC34A"),
    )),
    "pastel": Comida("pastel", "Pastel", "comer", (
        Variante("chocolate", "chocolate", "#6B3E26"),
        Variante("fresa", "fresa", "#FF8FB1"),
        Variante("limon", "limón", "#FFE45C"),
        Variante("vainilla", "vainilla", "#FFF1C9"),
    )),
}

# Otros nombres que se entienden al pedir comida (terminal, herramienta).
ALIAS: Dict[str, str] = {
    "batido": "batido", "batidos": "batido", "smoothie": "batido", "licuado": "batido",
    "malteada": "batido", "bebida": "batido",
    "pastel": "pastel", "pasteles": "pastel", "tarta": "pastel", "cake": "pastel",
    "torta": "pastel", "pastelito": "pastel", "bizcocho": "pastel",
}

APARECER_S, GUARDAR_S, COOLDOWN_S, TONO = 0.25, 0.20, 0.35, (0.65, 1.25)
GUARDAR_SOLA_S = 120
MS_REACCION = 2500
ESTADO_REACCION = "happy"

APARECE, GUARDA, CAMBIA = "aparece", "guarda", "cambia"

# Onomatopeyas y caras de la terminal.
ONOMATOPEYA = {"beber": "*glup glup*", "comer": "*ñam ñam*"}
CARA_ASCII = {"beber": "(^o^)~", "comer": "(^~^)"}
CARA_KAOMOJI = {"beber": "(っ˘ω˘ς)", "comer": "(っ˘ڡ˘ς)"}
SONIDO_BASE = {"beber": "trago", "comer": "mordisco"}
N_SONIDOS = 3                   # trago_1..3 y mordisco_1..3 en el pack por defecto

# Motivos de la tabla de prioridades (y los propios) en palabras.
MOTIVOS = {
    "juego": "hay un juego delante",
    "alarma": "hay una alarma sonando",
    "grande": "estoy en pantalla grande",
    "salvapantallas": "estoy de salvapantallas",
    "mmd": "estoy con un baile",
    "desactivada": "la comida está desactivada (Ajustes → Comida)",
    "desconocida": "no tengo esa comida",
}


def _plano(texto: Any) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def normalizar_id(id_: Any) -> Optional[str]:
    """«Batido», «tarta», «smoothie» → id del catálogo; None si no es comida."""
    return ALIAS.get(_plano(id_))


def comida(id_: Any) -> Optional[Comida]:
    n = normalizar_id(id_)
    return CATALOGO.get(n) if n else None


def variante_de(id_: Any, variante: Any = None) -> Optional[Variante]:
    """La variante `variante` de la comida (o la primera si no existe)."""
    c = comida(id_)
    if c is None:
        return None
    v = _plano(variante)
    for x in c.variantes:
        if x.id == v:
            return x
    return c.variantes[0]


def variante_exacta(id_: Any, variante: Any) -> Optional[Variante]:
    """La variante `variante` de la comida si existe (sin caer en la primera)."""
    c = comida(id_)
    v = _plano(variante)
    if c is None or not v:
        return None
    return next((x for x in c.variantes if x.id == v), None)


def catalogo_para_web() -> List[Dict[str, Any]]:
    """[{id, nombre, tipo, variantes: [{id, nombre, color}]}] para la página y el puente."""
    return [{"id": c.id, "nombre": c.nombre, "tipo": c.tipo,
             "variantes": [{"id": v.id, "nombre": v.nombre, "color": v.color} for v in c.variantes]}
            for c in CATALOGO.values()]


def motivo_legible(motivo: str) -> str:
    return MOTIVOS.get(str(motivo or ""), str(motivo or ""))


def texto_reaccion(id_: Any, variante: Any = None) -> str:
    """«*glup glup* (batido de mango)» / «*ñam ñam* (pastel de limón)»."""
    c = comida(id_)
    if c is None:
        return ""
    v = variante_de(c.id, variante)
    return f"{ONOMATOPEYA[c.tipo]} ({c.nombre.lower()} de {v.nombre})"


def texto_terminal(id_: Any, variante: Any = None, kaomoji: bool = False, *, nombre: str = "Lune") -> str:
    """«Lune (^o^)~ *glup glup* (batido de mango)» (con kaomoji, «(っ˘ω˘ς)»)."""
    c = comida(id_)
    if c is None:
        return ""
    cara = (CARA_KAOMOJI if kaomoji else CARA_ASCII)[c.tipo]
    quien = str(nombre or "").strip()
    return (f"{quien} " if quien else "") + f"{cara} {texto_reaccion(c.id, variante)}"


# ── Geometría del acierto ───────────────────────────────────────────────────────
Punto = Tuple[float, float]


def segmento_toca_circulo(p0: Sequence[float], p1: Sequence[float], c: Sequence[float], r: float) -> bool:
    """¿El segmento p0→p1 entra en el círculo (centro c, radio r)?

    Distancia del centro al punto más cercano del segmento ESTRICTAMENTE menor que
    r: rozarlo en tangente no cuenta. Un segmento de largo 0 es un punto."""
    try:
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        cx, cy = float(c[0]), float(c[1])
        r = float(r)
    except (TypeError, ValueError, IndexError):
        return False
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1, cx, cy, r)) or r <= 0.0:
        return False
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0.0 else clamp(((cx - x0) * dx + (cy - y0) * dy) / l2, 0.0, 1.0)
    px, py = x0 + t * dx, y0 + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 < r * r


def cabeza_valida(cabeza: Any) -> Optional[Tuple[float, float, float]]:
    """(cx, cy, r) con números finitos y r > 0, o None."""
    try:
        cx, cy, r = (float(v) for v in cabeza)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (cx, cy, r)) or r <= 0.0:
        return None
    return cx, cy, r


# ── Reacción ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Reaccion:
    tipo: str                   # beber | comer
    estado: str                 # happy
    ms: int
    sonido: str                 # trago_N | mordisco_N (N = 1..3)
    tono: float                 # velocidad del sonido (0.65–1.25)
    texto: str                  # «*glup glup* (batido de mango)»
    id: str = ""
    variante: str = ""

    @property
    def indice(self) -> int:
        """N − 1 de `sonido` (0 si no se entiende)."""
        try:
            return max(0, int(self.sonido.rsplit("_", 1)[1]) - 1)
        except (IndexError, ValueError):
            return 0


class GestorComida:
    """Qué comida hay en la mano y si ha tocado la cabeza (ver la cabecera)."""

    def __init__(self, *, azar: Optional[random.Random] = None, reloj: Callable[[], float] = time.monotonic):
        self._azar = azar if azar is not None else random.Random()
        self._reloj = reloj
        self._lock = threading.RLock()
        self.activa: Optional[Tuple[str, str]] = None      # (id, variante)
        self.ultima = ""                                    # la última que salió
        self._dentro = False
        self._siguiente = -math.inf
        self._t_mov: Optional[float] = None

    # ── Qué hay en la mano ──
    def variante_al_azar(self, id_: str, evitar: Optional[str] = None) -> Variante:
        c = CATALOGO[id_]
        opciones = [v for v in c.variantes if v.id != evitar] or list(c.variantes)
        return opciones[min(len(opciones) - 1, int(self._azar.random() * len(opciones)))]

    def mostrar(self, id_: Any, variante: Any = None) -> str:
        """Pone `id_` en la mano (sin alternar). aparece | cambia. ValueError si no existe."""
        n = normalizar_id(id_)
        if n is None:
            raise ValueError(f"comida desconocida: {id_!r}")
        with self._lock:
            antes = self.activa
            exacta = variante_exacta(n, variante)
            if exacta is not None:
                v = exacta.id
            else:
                evitar = antes[1] if antes and antes[0] == n else None
                v = self.variante_al_azar(n, evitar).id
            self.activa = (n, v)
            self.ultima = n
            self._dentro = False
            self._t_mov = self._reloj()
            return APARECE if antes is None else CAMBIA

    def alternar(self, id_: Any) -> str:
        """Sin comida → aparece; la misma → guarda; otra → cambia (ME la guardaba)."""
        n = normalizar_id(id_)
        if n is None:
            raise ValueError(f"comida desconocida: {id_!r}")
        with self._lock:
            if self.activa is not None and self.activa[0] == n:
                self.guardar()
                return GUARDA
            return self.mostrar(n)

    def guardar(self) -> bool:
        with self._lock:
            estaba = self.activa is not None
            self.activa = None
            self._dentro = False
            self._t_mov = None
            return estaba

    # ── Acierto ──
    def al_mover(self, t: float, p0: Sequence[float], p1: Sequence[float], cabeza: Any) -> bool:
        """El cursor fue de p0 a p1 en este paso. True si es un acierto nuevo.

        Cuenta al ENTRAR: el tramo toca la cabeza y el paso anterior acabó fuera
        (seguir dentro no cuenta; una pasada rápida que cruza entera, sí; la
        cabeza que se mueve hasta el cursor quieto, también). Como mucho uno cada
        COOLDOWN_S; como en ME, una entrada durante el enfriamiento se gasta."""
        with self._lock:
            if self.activa is None:
                self._dentro = False
                return False
            try:
                movido = (float(p0[0]), float(p0[1])) != (float(p1[0]), float(p1[1]))
            except (TypeError, ValueError, IndexError):
                movido = False
            if movido:
                self._t_mov = t
            cab = cabeza_valida(cabeza) if cabeza is not None else None
            toca = cab is not None and segmento_toca_circulo(p0, p1, cab[:2], cab[2])
            acierto = toca and not self._dentro and t >= self._siguiente
            if acierto:
                self._siguiente = t + COOLDOWN_S
            self._dentro = cab is not None and segmento_toca_circulo(p1, p1, cab[:2], cab[2])
            return acierto

    def acierto(self, t: Optional[float] = None) -> bool:
        """Un acierto que detectó otro (la página web): solo el enfriamiento."""
        t = self._reloj() if t is None else t
        with self._lock:
            if self.activa is None or t < self._siguiente:
                return False
            self._siguiente = t + COOLDOWN_S
            self._t_mov = t
            return True

    def caducada(self, t: Optional[float] = None) -> bool:
        """D4: ¿lleva GUARDAR_SOLA_S sin moverse?"""
        t = self._reloj() if t is None else t
        with self._lock:
            return self.activa is not None and self._t_mov is not None and t - self._t_mov >= GUARDAR_SOLA_S

    def reaccion(self, id_: Any = None, variante: Any = None) -> Reaccion:
        """La reacción al comer `id_` (por defecto la de la mano; si no hay, batido).
        Sin `variante` (o si no existe): la de la mano si es la misma comida, o una al azar."""
        with self._lock:
            act = self.activa
        n = normalizar_id(id_) if id_ is not None else (act[0] if act else None)
        n = n or "batido"
        if variante is None and act is not None and act[0] == n:
            variante = act[1]
        v = variante_exacta(n, variante) or self.variante_al_azar(n)
        c = CATALOGO[n]
        k = min(N_SONIDOS - 1, int(self._azar.random() * N_SONIDOS))
        tono = round(TONO[0] + (TONO[1] - TONO[0]) * self._azar.random(), 3)
        return Reaccion(c.tipo, ESTADO_REACCION, MS_REACCION, f"{SONIDO_BASE[c.tipo]}_{k + 1}",
                        tono, texto_reaccion(n, v.id), n, v.id)


# ── Balanceo ────────────────────────────────────────────────────────────────────
REF_HZ = 60.0                   # ME mide el ratón por frame; aquí se normaliza a 60 Hz


class BalanceoComida:
    """El vaivén de la comida al moverla. `paso(dt, dx, dy)` → (ladeo, cabeceo) en grados.

    - ladeo: giro en pantalla, positivo = horario (lo que hace QPainter.rotate):
      al mover a la derecha la parte de arriba se inclina a la derecha.
    - cabeceo: positivo = la parte de arriba se aleja (al subir el ratón).
    `dx, dy` en px de pantalla (y hacia abajo) movidos en este paso."""

    def __init__(self, *, sensibilidad: float = 4.0, ladeo_por_px: float = 0.7, cabeceo_por_px: float = 0.7,
                 max_ladeo: float = 25.0, max_cabeceo: float = 10.0, f_hz: float = 1.0, zeta: float = 0.35,
                 mezcla: float = 8.0, filtro: float = 12.0):
        self.sensibilidad = float(sensibilidad)
        self.ladeo_por_px = float(ladeo_por_px)
        self.cabeceo_por_px = float(cabeceo_por_px)
        self.max_ladeo = abs(float(max_ladeo))
        self.max_cabeceo = abs(float(max_cabeceo))
        self.mezcla = float(mezcla)
        self.filtro = float(filtro)
        # Tope de seguridad de 2× (el sobrepaso del muelle es ~31 %, ver fisica.sobrepaso_teorico).
        self._ml = Muelle(f_hz, zeta, tope=2 * self.max_ladeo)
        self._mc = Muelle(f_hz, zeta, tope=2 * self.max_cabeceo)
        self.reiniciar()

    def reiniciar(self) -> None:
        """Todo a cero (al aparecer: ResetSwayState de ME)."""
        self._ml.reiniciar()
        self._mc.reiniciar()
        self._fx = self._fy = 0.0
        self.peso = 0.0
        self.ladeo = self.cabeceo = 0.0

    def paso(self, dt: float, dx_px: float, dy_px: float) -> Tuple[float, float]:
        try:
            dt, dx, dy = float(dt), float(dx_px), float(dy_px)
        except (TypeError, ValueError):
            return self.ladeo, self.cabeceo
        if not (dt > 0.0) or not all(math.isfinite(v) for v in (dt, dx, dy)):
            return self.ladeo, self.cabeceo
        por_frame = 1.0 / (max(dt, 1e-3) * REF_HZ)        # px de este paso → px por frame de 60 Hz
        mx = dx * por_frame * self.sensibilidad
        my = dy * por_frame * self.sensibilidad
        k = 1.0 - math.exp(-self.filtro * dt)
        self._fx += (mx - self._fx) * k
        self._fy += (my - self._fy) * k
        obj_l = clamp(self._fx * self.ladeo_por_px, -self.max_ladeo, self.max_ladeo)
        obj_c = clamp(-self._fy * self.cabeceo_por_px, -self.max_cabeceo, self.max_cabeceo)
        l = self._ml.paso(obj_l, dt)
        c = self._mc.paso(obj_c, dt)
        self.peso = min(1.0, self.peso + self.mezcla * dt)
        self.ladeo, self.cabeceo = l * self.peso, c * self.peso
        return self.ladeo, self.cabeceo


# ── Sonidos ─────────────────────────────────────────────────────────────────────
def _lanzar_hilo(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="LuneSfxComida", daemon=True).start()


def _cfg(config: Any, seccion: str, clave: str, defecto: Any) -> Any:
    try:
        return config.get(seccion, clave, defecto) if config is not None else defecto
    except Exception:
        return defecto


def comida_habilitada(config: Any) -> bool:
    """`comida.activa` (el interruptor de la función)."""
    return bool(_cfg(config, "comida", "activa", True))


class SonidosComida:
    """Los sonidos de la comida por el Mezclador (canal `sfx`), en todos los modos.

    Cada sonido lleva su propio tono al azar (PlayRandom de ME). Se resuelven
    con el pack de `avatar.pack_sonidos` (si no existe, el de por defecto) en el
    hilo del lanzador: cargar el WAV y abrir el dispositivo tarda."""

    CANAL = "sfx"

    def __init__(self, config: Any, *, mezclador: Any = None,
                 lanzar: Optional[Callable[[Callable[[], None]], Any]] = None,
                 en_juego: Optional[Callable[[], bool]] = None, azar: Optional[random.Random] = None):
        self.config = config
        self._mez = mezclador
        self._lanzar = lanzar or _lanzar_hilo
        self._en_juego = en_juego or (lambda: False)
        self._azar = azar if azar is not None else random.Random()
        self.ultimos: List[str] = []            # eventos pedidos (para diagnóstico y tests)

    def volumen(self) -> float:
        try:
            v = float(_cfg(self.config, "avatar", "volumen_sfx", 0.7))
        except (TypeError, ValueError):
            v = 0.7
        return 0.0 if not math.isfinite(v) else max(0.0, min(1.0, v))

    def silenciado(self) -> bool:
        """En modo juego con `juego.silenciar`, o con el volumen de efectos a 0."""
        try:
            juego = bool(self._en_juego())
        except Exception:
            juego = False
        if juego and bool(_cfg(self.config, "juego", "silenciar", True)):
            return True
        return self.volumen() <= 0.0

    def tono(self) -> float:
        return TONO[0] + (TONO[1] - TONO[0]) * self._azar.random()

    def aparecer(self, id_: Any) -> bool:
        """comida_aparece y, en el batido, una capa (comida_capa_1|2)."""
        c = comida(id_)
        if c is None:
            return False
        ok = self._tocar("comida_aparece", tono=self.tono())
        if c.tipo == "beber":
            self._tocar("comida_capa", tono=self.tono())
        return ok

    def reaccion(self, r: Reaccion) -> bool:
        """trago_N / mordisco_N (eventos beber / comer del pack) con su tono."""
        return self._tocar(r.tipo, indice=r.indice, tono=r.tono)

    def guardar(self) -> bool:
        """Al guardar: solo si el pack trae `comida_guarda` (el de por defecto no: ME calla)."""
        return self._tocar("comida_guarda", tono=self.tono(), opcional=True)

    # ── Internos ──
    def _mezclador(self) -> Any:
        if self._mez is None:
            from servicios.mezclador import Mezclador
            self._mez = Mezclador.instancia()
        return self._mez

    def _pack(self):
        from nucleo import packs_sonido as ps
        pack_id = str(_cfg(self.config, "avatar", "pack_sonidos", ps.PACK_DEFECTO) or ps.PACK_DEFECTO)
        return ps.obtener_pack(pack_id) or ps.pack_por_defecto()

    def _tocar(self, evento: str, *, indice: Optional[int] = None, tono: float = 1.0,
               opcional: bool = False) -> bool:
        if self.silenciado():
            return False
        vol_cfg = self.volumen()
        azar = self._azar.random()

        def correr() -> None:
            try:
                from nucleo import packs_sonido as ps
                pack = self._pack()
                if pack is None:
                    return
                lista = ps.resolver(pack, evento)
                if not lista:
                    if not opcional:
                        _log.debug("comida: el pack no trae «%s»", evento)
                    return
                if indice is not None and 0 <= indice < len(lista) and len(lista) == N_SONIDOS:
                    ruta = lista[indice]
                else:
                    ruta = lista[min(len(lista) - 1, int(azar * len(lista)))]
                vol = max(0.0, min(1.0, vol_cfg * float(getattr(pack, "volumen", 1.0) or 0.0)))
                if vol <= 0.0:
                    return
                mez = self._mezclador()
                cargar = getattr(mez, "cargar_audio", None) or getattr(mez, "cargar_wav", None)
                buf = cargar(ruta) if callable(cargar) else ruta
                mez.reproducir(buf, vol=vol, velocidad=float(tono), canal=self.CANAL)
            except Exception:
                _log.debug("comida: el sonido %s falló", evento, exc_info=True)

        self.ultimos.append(evento)
        del self.ultimos[:-20]
        try:
            self._lanzar(correr)
        except Exception:
            _log.debug("comida: no pude lanzar el sonido %s", evento, exc_info=True)
            return False
        return True


# ── Herramienta del modelo ──────────────────────────────────────────────────────
def _de_ctx(ctx: Any, clave: str) -> Any:
    """ctx[clave] (dict) o ctx.clave, también dentro de ctx['contexto'] (el Ejecutor
    envuelve así los ctx que no son dict; como nucleo/baile y nucleo/sueno)."""
    if ctx is None:
        return None
    v = ctx.get(clave) if isinstance(ctx, Mapping) else getattr(ctx, clave, None)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        c = ctx.get("contexto")
        v = c.get(clave) if isinstance(c, Mapping) else getattr(c, clave, None)
    return v


def herramienta(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `dar_de_comer` ({comida: batido|pastel}).

    `ctx["comida"]` es el controlador (ui/comida_qt.ControlComida o
    servicios/comida_terminal.ComidaTerminal) con `comer_directo(id) -> str` ("" si
    no pudo, con `ultimo_motivo`); `ctx["en_ui"](fn)` lo corre en el hilo de Qt.
    Sin controlador solo devuelve el texto."""
    args = args if isinstance(args, Mapping) else {}
    n = normalizar_id(args.get("comida"))
    if n is None:
        return False, "No tengo esa comida: pide un batido o un pastel."
    ctl = _de_ctx(ctx, "comida")
    if ctl is None or not callable(getattr(ctl, "comer_directo", None)):
        v = GestorComida().variante_al_azar(n)
        return texto_reaccion(n, v.id)
    en_ui = _de_ctx(ctx, "en_ui")
    try:
        texto = en_ui(lambda: ctl.comer_directo(n)) if callable(en_ui) else ctl.comer_directo(n)
    except Exception as e:                                    # noqa: BLE001
        return False, f"No pude comer: {e}"[:300]
    if not texto:
        motivo = motivo_legible(getattr(ctl, "ultimo_motivo", "") or "")
        return False, "Ahora no puedo comer" + (f": {motivo}." if motivo else ".")
    return str(texto)


__all__ = (
    "Variante", "Comida", "CATALOGO", "ALIAS", "APARECER_S", "GUARDAR_S", "COOLDOWN_S", "TONO",
    "GUARDAR_SOLA_S", "MS_REACCION", "ESTADO_REACCION", "APARECE", "GUARDA", "CAMBIA", "Reaccion",
    "GestorComida", "BalanceoComida", "SonidosComida", "segmento_toca_circulo", "cabeza_valida",
    "normalizar_id", "comida", "variante_de", "variante_exacta", "catalogo_para_web", "texto_reaccion", "texto_terminal", "motivo_legible",
    "comida_habilitada", "herramienta",
)
