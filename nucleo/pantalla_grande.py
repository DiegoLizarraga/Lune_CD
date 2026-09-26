"""
nucleo/pantalla_grande.py — Pantalla grande y salvapantallas de Lune, sin Qt.

QUÉ ES
------
En Mate-Engine la «pantalla grande» (AvatarBigScreenHandler.cs) lleva la ventana
del avatar al monitor entero y encuadra la cabeza; el salvapantallas
(AvatarBigScreenScreenSaver.cs) la pone solo tras un rato sin tocar el PC. Aquí
está la lógica pura de las dos cosas; el adaptador de Qt es
ui/pantalla_grande_qt.ControlPantallaGrande y lo visual lo hace la página de la
mascota (luneGrande) o ui/ventana_reloj.VentanaReloj.

- `TIEMPOS`, `etiqueta(paso)`, `segundos(paso)`: los 11 pasos de espera del
  salvapantallas de Mate-Engine (TimeoutSteps, :26), de 30 s a 3 h.
- `MaquinaGrande`: la secuencia de entrada y salida con la mascota. Entrada:
  planeo de GLIDE_MS (la ventana aún en su sitio) → la ventana pasa al monitor y
  fundido de FADE_MS → activa. Salida al revés: fundido → la ventana vuelve a su
  sitio exacto → planeo de vuelta → fin. No sabe de ventanas: devuelve ACCIONES
  que ejecuta el controlador:
      ("guardar_geom", {motivo})          guardar la geometría de la mascota
      ("fase", {fase, ms, motivo})        grande_fase(fase) en la página:
                                          glide · entrar · salir · volver · fin
      ("geom_monitor", {motivo})          la ventana al monitor de mayor intersección
      ("restaurar_geom", {motivo})        la ventana a la geometría guardada
      ("activa", {motivo})                ya está en pantalla grande
      ("fin", {motivo})                   terminó (soltar la actividad del BusEstado)
  Reglas: pedir entrar mientras SALE se encola (entra al acabar); pedir entrar
  mientras entra o está activa no hace nada; pedir salir mientras ENTRA sale en
  cuanto llegue (sin cortar la animación); `pedir_salir(t, motivo)` solo sale si
  el motivo coincide (la alarma no quita la pantalla grande manual). El salto de
  cámara final de Mate-Engine (:252-270) no se copia.
- `ReglaSalvapantallas`: ¿toca poner el salvapantallas? Bloquean el juego, la
  pantalla grande, una alarma, arrastrarla, un menú abierto, que hable, la
  llamada, que piense, que baile (Mate-Engine solo arranca desde Idle) y, si se
  sabe, que alguien pida la pantalla encendida (un vídeo). Dormida cuenta como
  reposo.
- `herramienta(args, ctx)`: handler de `mascota_pantalla_grande`
  (lune_core/catalogo_herramientas.py).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

# ── Pasos del salvapantallas (Mate-Engine: TimeoutSteps / TimeoutLabels) ─────────
TIEMPOS: Tuple[int, ...] = (30, 60, 300, 900, 1800, 2700, 3600, 5400, 7200, 9000, 10800)
ETIQUETAS: Tuple[str, ...] = ("30 s", "1 min", "5 min", "15 min", "30 min", "45 min",
                              "1 h", "1 h 30 min", "2 h", "2 h 30 min", "3 h")
PASO_MAX = len(TIEMPOS) - 1

GLIDE_MS, FADE_MS = 400, 500
MOTIVOS: Tuple[str, ...] = ("manual", "herramienta", "alarma", "salvapantallas")
MINUTOS_MAX = 120

Accion = Tuple[str, Dict[str, Any]]


def paso_valido(paso: Any) -> int:
    """El paso como entero entre 0 y 10 (lo que no es un número → 0)."""
    try:
        p = float(paso)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(p):
        return 0
    return int(min(max(round(p), 0), PASO_MAX))


def segundos(paso: Any) -> int:
    """Segundos de espera del paso (0 → 30 s … 10 → 3 h)."""
    return TIEMPOS[paso_valido(paso)]


def etiqueta(paso: Any) -> str:
    """Texto del paso: «30 s», «5 min», «1 h 30 min»…"""
    return ETIQUETAS[paso_valido(paso)]


# ── Máquina de entrada y salida ──────────────────────────────────────────────────
class MaquinaGrande:
    """Estado de la pantalla grande con la mascota: None · entrando · activa · saliendo.

    `t` son segundos de un reloj monótono (el controlador pasa time.monotonic()).
    """

    def __init__(self, glide_ms: int = GLIDE_MS, fade_ms: int = FADE_MS):
        self.glide_s = max(0, int(glide_ms)) / 1000.0
        self.fade_s = max(0, int(fade_ms)) / 1000.0
        self.glide_ms = int(glide_ms)
        self.fade_ms = int(fade_ms)
        self.estado: Optional[str] = None
        self.motivo: str = ""
        self._paso = ""                 # entrando: glide | fundido · saliendo: fundido | volver
        self._hasta = 0.0
        self._cola: Optional[str] = None
        self._salir_pedido = False

    # ── Consultas ────────────────────────────────────────────────────────────────
    @property
    def en_transicion(self) -> bool:
        return self.estado in ("entrando", "saliendo")

    @property
    def encolado(self) -> Optional[str]:
        """Motivo de la entrada que espera a que acabe la salida (o None)."""
        return self._cola

    @property
    def paso(self) -> str:
        return self._paso

    def proximo(self) -> Optional[float]:
        """Instante del próximo cambio (None si no hay transición en marcha)."""
        return self._hasta if self.en_transicion else None

    # ── Peticiones ───────────────────────────────────────────────────────────────
    def pedir_entrar(self, motivo: str, t: float) -> List[Accion]:
        motivo = str(motivo or "manual")
        if self.estado is None:
            return self._empezar(motivo, t)
        if self.estado == "saliendo":
            self._cola = motivo
            return []
        if self.estado == "entrando":
            self._salir_pedido = False          # volver a pedirla anula una salida pedida
        return []

    def pedir_salir(self, t: float, motivo: Optional[str] = None) -> List[Accion]:
        """Empieza la salida animada. Con `motivo`, solo si coincide con el actual
        (o anula una entrada encolada con ese motivo)."""
        if motivo is not None and motivo != self.motivo:
            if self._cola == motivo:
                self._cola = None
            return []
        if self.estado == "activa":
            return self._salida(t)
        if self.estado == "entrando":
            self._salir_pedido = True
            return []
        if self.estado == "saliendo":
            self._cola = None                   # ya sale: que no vuelva a entrar
        return []

    def salir_ya(self, t: float = 0.0, *, conservar_cola: bool = False) -> List[Accion]:
        """Salida sin animación (entra un juego, se detiene el controlador):
        restaurar la geometría y fin en el acto."""
        if self.estado is None:
            if not conservar_cola:
                self._cola = None
            return []
        if not conservar_cola:
            self._cola = None
        m = self.motivo
        out: List[Accion] = [("restaurar_geom", {"motivo": m})]
        return out + self._fin(t)

    def cambiar_motivo(self, motivo: str) -> None:
        """Otro motivo para la pantalla grande en curso (salvapantallas → alarma o manual)."""
        if self.estado is not None:
            self.motivo = str(motivo or self.motivo)

    def abortar(self) -> None:
        """Olvida todo sin acciones (la actividad no se pudo empezar)."""
        self.estado, self.motivo, self._paso = None, "", ""
        self._cola = None
        self._salir_pedido = False

    def avanzar(self, t: float) -> List[Accion]:
        """Acciones de los pasos que han vencido hasta `t` (puede ser más de uno si
        el reloj dio un salto: cada paso cuenta desde el final del anterior)."""
        out: List[Accion] = []
        for _ in range(8):
            if not self.en_transicion or t < self._hasta:
                break
            m = self.motivo
            if self.estado == "entrando":
                if self._paso == "glide":
                    self._paso, self._hasta = "fundido", self._hasta + self.fade_s
                    out += [("geom_monitor", {"motivo": m}),
                            ("fase", {"fase": "entrar", "ms": self.fade_ms, "motivo": m})]
                else:
                    self.estado, self._paso = "activa", ""
                    out.append(("activa", {"motivo": m}))
                    if self._salir_pedido:
                        self._salir_pedido = False
                        out += self._salida(t)
            else:                                # saliendo
                if self._paso == "fundido":
                    self._paso, self._hasta = "volver", self._hasta + self.glide_s
                    out += [("restaurar_geom", {"motivo": m}),
                            ("fase", {"fase": "volver", "ms": self.glide_ms, "motivo": m})]
                else:
                    out += self._fin(t)
        return out

    # ── Internos ─────────────────────────────────────────────────────────────────
    def _empezar(self, motivo: str, t: float) -> List[Accion]:
        self.estado, self.motivo, self._paso = "entrando", motivo, "glide"
        self._hasta = t + self.glide_s
        self._salir_pedido = False
        return [("guardar_geom", {"motivo": motivo}),
                ("fase", {"fase": "glide", "ms": self.glide_ms, "motivo": motivo})]

    def _salida(self, t: float) -> List[Accion]:
        self.estado, self._paso = "saliendo", "fundido"
        self._hasta = t + self.fade_s
        return [("fase", {"fase": "salir", "ms": self.fade_ms, "motivo": self.motivo})]

    def _fin(self, t: float) -> List[Accion]:
        m = self.motivo
        self.estado, self.motivo, self._paso = None, "", ""
        self._salir_pedido = False
        out: List[Accion] = [("fase", {"fase": "fin", "ms": 0, "motivo": m}), ("fin", {"motivo": m})]
        cola, self._cola = self._cola, None
        if cola:
            out += self._empezar(cola, t)
        return out


# ── Regla del salvapantallas ─────────────────────────────────────────────────────
def _campo(obj: Any, nombre: str, defecto: Any = None) -> Any:
    if obj is None:
        return defecto
    if isinstance(obj, Mapping):
        return obj.get(nombre, defecto)
    return getattr(obj, nombre, defecto)


# (campo del EstadoMascota, motivo) en el orden en que se comprueban. Los de
# nucleo/estado_mascota.BLOQUEOS["salvapantallas"] están incluidos.
BLOQUEOS: Tuple[Tuple[str, str], ...] = (
    ("juego", "juego"),
    ("alarma", "alarma"),
    ("grande", "grande"),
    ("salvapantallas", "salvapantallas"),
    ("arrastrando", "arrastrando"),
    ("menu_abierto", "menu_abierto"),
    ("hablando", "hablando"),
    ("llamada", "llamada"),
    ("pensando", "pensando"),
    ("bailando", "bailando"),
)


class ReglaSalvapantallas:
    """¿Toca poner el salvapantallas? (config `salvapantallas.activo` y `.paso`)."""

    def __init__(self, activo: bool = False, paso: int = 0):
        self.activo = bool(activo)
        self.paso = paso_valido(paso)

    @classmethod
    def desde_config(cls, config: Any) -> "ReglaSalvapantallas":
        def leer(clave, defecto):
            try:
                if hasattr(config, "get") and not isinstance(config, Mapping):
                    return config.get("salvapantallas", clave, defecto)
                return (config or {}).get("salvapantallas", {}).get(clave, defecto)
            except Exception:
                return defecto
        return cls(bool(leer("activo", False)), leer("paso", 0))

    @property
    def umbral_s(self) -> int:
        return segundos(self.paso)

    @property
    def etiqueta(self) -> str:
        return etiqueta(self.paso)

    def motivo_no(self, estado: Any, *, pensando: bool = False, pantalla_requerida: bool = False,
                  mando: bool = False) -> str:
        """Motivo por el que NO puede ponerse ahora ("" si puede). La mascota
        dormida no bloquea: dormir es estar en reposo."""
        if not self.activo:
            return "apagado"
        for campo, motivo in BLOQUEOS:
            if _campo(estado, campo, False):
                return motivo
        if pensando:
            return "pensando"
        if mando:
            return "mando"
        if pantalla_requerida:
            return "pantalla_requerida"
        return ""

    def debe_activar(self, inactivo_s: float, estado: Any, **kw: bool) -> bool:
        """¿Lleva el PC `inactivo_s` segundos sin tocarse, más que el paso, y nada lo bloquea?"""
        try:
            inactivo = float(inactivo_s)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(inactivo) or inactivo < self.umbral_s:
            return False
        return not self.motivo_no(estado, **kw)


# ── Herramienta del modelo ───────────────────────────────────────────────────────
def _de_ctx(ctx: Any, clave: str) -> Any:
    """ctx[clave] (dict) o ctx.clave (objeto); también dentro de ctx['contexto']
    (así envuelve el Ejecutor un ctx que no es dict)."""
    v = _campo(ctx, clave)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        v = _campo(ctx.get("contexto"), clave)
    return v


def _bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return bool(v)
    t = str(v or "").strip().lower()
    if t in ("true", "1", "si", "sí", "yes", "on", "activar", "entrar"):
        return True
    if t in ("false", "0", "no", "off", "desactivar", "salir", "quitar"):
        return False
    return None


def _minutos(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        m = int(float(v))
    except (TypeError, ValueError):
        return None
    return min(max(m, 1), MINUTOS_MAX)


def herramienta(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `mascota_pantalla_grande` ({activar: bool, minutos?: 1–120}).

    `ctx["grande"]` es el ControlPantallaGrande y `ctx["en_ui"](fn)` (opcional)
    corre fn en el hilo de Qt y devuelve su resultado. Devuelve el texto para el
    modelo, o `(False, motivo)` si no se pudo.
    """
    args = args if isinstance(args, Mapping) else {}
    grande = _de_ctx(ctx, "grande")
    if grande is None:
        return False, "Aquí no tengo pantalla grande."
    activar = _bool(args.get("activar"))
    if activar is None:
        return False, "Falta decir si activar o quitar la pantalla grande."
    minutos = _minutos(args.get("minutos")) if activar else None
    en_ui: Optional[Callable[[Callable[[], Any]], Any]] = _de_ctx(ctx, "en_ui")

    def correr(fn: Callable[[], Any]) -> Any:
        return en_ui(fn) if callable(en_ui) else fn()

    try:
        if activar:
            ok = correr(lambda: grande.entrar("herramienta", minutos))
            if not ok:
                motivo = str(getattr(grande, "ultimo_error", "") or "")
                return False, ("Ahora no puedo ponerme en pantalla grande"
                               + (f" ({motivo})." if motivo else "."))
            return ("Vale, me pongo en pantalla grande"
                    + (f" durante {minutos} min." if minutos else ".")
                    + " Para quitarla: Ctrl+Alt+Shift+B, el menú o pídemelo.")
        estaba = correr(lambda: bool(getattr(grande, "activo", False)))
        if not estaba:
            return "No estaba en pantalla grande."
        correr(lambda: grande.salir())
        return "Listo, vuelvo a mi sitio."
    except Exception as e:                               # noqa: BLE001
        return False, f"No pude cambiar la pantalla grande: {e}"[:300]


__all__ = (
    "TIEMPOS", "ETIQUETAS", "PASO_MAX", "GLIDE_MS", "FADE_MS", "MOTIVOS", "MINUTOS_MAX",
    "paso_valido", "segundos", "etiqueta", "MaquinaGrande", "ReglaSalvapantallas",
    "BLOQUEOS", "herramienta",
)
