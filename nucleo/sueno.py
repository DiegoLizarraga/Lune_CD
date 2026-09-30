"""
nucleo/sueno.py — Cuándo se duerme la asistente (y cómo se cuenta en la terminal).

PARA QUÉ SIRVE
--------------
Mate-Engine duerme al avatar tras un rato sin tocarlo, pero solo desde ciertos
estados: no se duerme a mitad de una respuesta, hablando, escuchando el micro
o mientras la arrastras. Lune hacía eso solo en el VRM y con un filtro a mano
(`companion._dormir`: «si está pensando, no»). Aquí está la regla en un solo
sitio, sin Qt, para la asistente VRM, la animada, los sprites y la barra lateral:

- `ReglaSueno(dormir_min, permitidos={'normal', 'bored'})`
    `debe_dormir(inactivo_s, estado_actual)` → ¿toca dormirse YA? Lista blanca:
    solo desde un estado de `permitidos`; nunca desde working/thinking/talking/
    listening, ni arrastrándola, ni con la voz sonando, ni en llamada (tampoco
    con alarma, pantalla grande, baile, comida o un menú abierto).
    `estado_actual` puede ser el nombre del estado visual ('normal', 'bored',
    'thinking'…) o un `nucleo.estado_asistente.EstadoAsistente` (o cualquier objeto
    o dict con sus campos).
    `segundos_restantes(inactivo_s)` → para rearmar el QTimer de sueño.
    `mensaje_diferido(pausa_s)` → en patata no hay asistente en escritorio que dormir: cuando el
    usuario vuelve tras una pausa larga se imprime «Lune se quedó dormida hace
    N min… (-_-) zzZ».
- `herramienta_dormir(args, ctx)` / `herramienta_despertar(args, ctx)`: los
  handlers de las herramientas del modelo `asistente_dormir` / `asistente_despertar`
  (lune_core/catalogo_herramientas.py). Llaman a `ctx['asistente'].dormir()` /
  `.despertar()` (en el hilo de Qt si `ctx['en_ui']` existe; contrato:
  `en_ui(fn)` devuelve el resultado de `fn`) y devuelven el texto para el
  modelo, o `(False, motivo)` si no se pudo (lo entiende el Ejecutor). Si `en_ui`
  devuelve None, se comprueba `durmiendo` (también vía `en_ui`) antes de dar el
  cambio por hecho.
  `ctx` puede ser un dict, un objeto o el dict con que el Ejecutor envuelve un
  objeto ({..., 'contexto': objeto}), igual que `nucleo.vrm.herramienta_tamano`.
  La herramienta NO pasa por la regla: si el usuario le pide que se duerma, se
  duerme aunque esté hablando (la asistente puede diferirlo al acabar la voz).
"""
from __future__ import annotations

import math
from typing import Any, Callable, FrozenSet, Iterable, Mapping, Optional, Tuple, Union

PERMITIDOS_POR_DEFECTO: FrozenSet[str] = frozenset({"normal", "bored"})

# Estados desde los que NUNCA se duerme, aunque alguien los meta en `permitidos`.
NUNCA: FrozenSet[str] = frozenset({"working", "thinking", "talking", "listening"})

# Campos booleanos de EstadoAsistente (o banderas sueltas) que impiden dormirse.
# campo → motivo legible.
BLOQUEOS: Tuple[Tuple[str, str], ...] = (
    ("arrastrando", "la están arrastrando"),
    ("hablando", "está hablando"),
    ("llamada", "está en una llamada"),
    ("pensando", "está pensando una respuesta"),
    ("alarma", "hay una alarma sonando"),
    ("grande", "está en pantalla grande"),
    ("comiendo", "está comiendo"),
    ("menu_abierto", "hay un menú abierto"),
)

# Emoción canónica (EstadoAsistente.emocion) → estado visual.
_EMOCION_A_ESTADO = {"neutral": "normal", "": "normal", "think": "thinking", "question": "thinking"}

EstadoT = Union[str, Mapping[str, Any], Any]


def _campo(obj: Any, nombre: str, defecto: Any = None) -> Any:
    if obj is None:
        return defecto
    if isinstance(obj, Mapping):
        return obj.get(nombre, defecto)
    return getattr(obj, nombre, defecto)


def _minutos(valor: Any, defecto: float) -> float:
    try:
        m = float(valor)
    except (TypeError, ValueError):
        return defecto
    return m if math.isfinite(m) and m > 0 else 0.0


class ReglaSueno:
    """Regla de sueño por inactividad (lista blanca de estados).

    `dormir_min`: minutos sin tocarla ni hablarle; 0 (o negativo) = nunca.
    `permitidos`: estados visuales desde los que puede dormirse.
    """

    def __init__(self, dormir_min: float = 10, permitidos: Iterable[str] = PERMITIDOS_POR_DEFECTO):
        self.dormir_min = _minutos(dormir_min, 10.0)
        self.permitidos: FrozenSet[str] = frozenset(str(p).strip().lower() for p in permitidos) - NUNCA

    @classmethod
    def desde_config(cls, config: Any, permitidos: Iterable[str] = PERMITIDOS_POR_DEFECTO) -> "ReglaSueno":
        """Con `avatar.dormir_min` de un `nucleo.config.Config` (10 si no hay)."""
        valor = 10
        try:
            if config is not None:
                valor = config.get("avatar", "dormir_min", 10)
        except Exception:
            valor = 10
        return cls(_minutos(valor, 10.0), permitidos)

    # ── Tiempo ──
    @property
    def activa(self) -> bool:
        """False si está desactivada (dormir_min = 0)."""
        return self.dormir_min > 0

    @property
    def umbral_s(self) -> float:
        """Segundos de inactividad para dormirse (inf si está desactivada)."""
        return self.dormir_min * 60.0 if self.activa else math.inf

    def segundos_restantes(self, inactivo_s: float) -> Optional[float]:
        """Lo que falta para dormirse (0 si ya toca), o None si está desactivada."""
        if not self.activa:
            return None
        try:
            inactivo = float(inactivo_s)
        except (TypeError, ValueError):
            inactivo = 0.0
        if not math.isfinite(inactivo) or inactivo < 0:
            inactivo = 0.0
        return max(0.0, self.umbral_s - inactivo)

    # ── Estado ──
    @staticmethod
    def estado_visual(estado_actual: EstadoT) -> str:
        """El estado visual equivalente ('normal', 'thinking', 'sleeping'…).

        Con un EstadoAsistente (o dict/objeto con sus campos): durmiendo → sleeping,
        pensando → thinking, hablando → talking, llamada → listening,
        arrastrando → dragging; si no, su emoción ('neutral' → 'normal').
        """
        if isinstance(estado_actual, str):
            return estado_actual.strip().lower() or "normal"
        if estado_actual is None:
            return "normal"
        if _campo(estado_actual, "durmiendo"):
            return "sleeping"
        if _campo(estado_actual, "pensando"):
            return "thinking"
        if _campo(estado_actual, "hablando"):
            return "talking"
        if _campo(estado_actual, "llamada"):
            return "listening"
        if _campo(estado_actual, "arrastrando"):
            return "dragging"
        emocion = str(_campo(estado_actual, "emocion", "neutral") or "").strip().lower()
        return _EMOCION_A_ESTADO.get(emocion, emocion)

    def motivo_no(self, estado_actual: EstadoT, *, arrastrando: bool = False,
                  hablando: bool = False, llamada: bool = False, durmiendo: bool = False) -> str:
        """Por qué NO puede dormirse ahora ('' si puede), sin mirar el tiempo."""
        if durmiendo or (not isinstance(estado_actual, str) and _campo(estado_actual, "durmiendo")):
            return "ya está dormida"
        banderas = {"arrastrando": arrastrando, "hablando": hablando, "llamada": llamada}
        for campo, motivo in BLOQUEOS:
            if banderas.get(campo):
                return motivo
            if not isinstance(estado_actual, str) and _campo(estado_actual, campo):
                return motivo
        if not isinstance(estado_actual, str) and _campo(estado_actual, "bailando"):
            return "está bailando"
        visual = self.estado_visual(estado_actual)
        if visual == "sleeping":
            return "ya está dormida"
        if visual in NUNCA:
            return f"está en «{visual}»"
        if visual not in self.permitidos:
            return f"el estado «{visual}» no deja dormir"
        return ""

    def puede_dormir(self, estado_actual: EstadoT, **banderas: bool) -> bool:
        """¿Puede dormirse desde este estado? (sin mirar el tiempo)."""
        return not self.motivo_no(estado_actual, **banderas)

    def debe_dormir(self, inactivo_s: float, estado_actual: EstadoT, *, arrastrando: bool = False,
                    hablando: bool = False, llamada: bool = False, durmiendo: bool = False) -> bool:
        """¿Toca dormirse ya? Activa, `inactivo_s` ≥ umbral y un estado que lo permite."""
        restante = self.segundos_restantes(inactivo_s)
        if restante is None or restante > 0:
            return False
        return not self.motivo_no(estado_actual, arrastrando=arrastrando, hablando=hablando,
                                  llamada=llamada, durmiendo=durmiendo)

    # ── Patata ──
    def mensaje_diferido(self, pausa_s: float, nombre: str = "Lune",
                         frase_despertar: Optional[str] = None) -> Optional[str]:
        """Aviso para la terminal si la pausa del usuario dio para dormirse.

        Se durmió `dormir_min` después de la última entrada, así que lleva
        `pausa_s − umbral` dormida. None si no llegó a dormirse (o está desactivada).

            «Lune se quedó dormida hace 12 min… (-_-) zzZ»
        """
        restante = self.segundos_restantes(pausa_s)
        if restante is None or restante > 0:
            return None
        dormida_s = max(0.0, float(pausa_s) - self.umbral_s)
        texto = f"{nombre or 'Lune'} se quedó dormida {_hace(dormida_s)}… (-_-) zzZ"
        if frase_despertar:
            texto += f"\n{frase_despertar}"
        return texto


def _hace(segundos: float) -> str:
    """«hace un momento», «hace 1 min», «hace 12 min», «hace 2 h», «hace 1 h 5 min»."""
    minutos = int(segundos // 60)
    if minutos < 1:
        return "hace un momento"
    if minutos < 60:
        return f"hace {minutos} min"
    horas, resto = divmod(minutos, 60)
    return f"hace {horas} h" + (f" {resto} min" if resto else "")


# ── Herramientas del modelo ──────────────────────────────────────────────────────
def _de_ctx(ctx: Any, clave: str) -> Any:
    """ctx[clave] (dict) o ctx.clave (objeto). El Ejecutor (lune_core/acciones.py)
    envuelve un ctx que no es dict como {..., 'contexto': objeto}: también se busca
    ahí (igual que `nucleo.vrm._de_ctx`)."""
    v = _campo(ctx, clave)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        v = _campo(ctx.get("contexto"), clave)
    return v


def _llamar_en_ui(ctx: Any, fn: Callable[[], Any]) -> Tuple[Any, bool]:
    """Ejecuta `fn` en el hilo de Qt si ctx trae `en_ui` (el Ejecutor puede ir en
    otro hilo). Contrato: `en_ui(fn)` devuelve lo que devuelve `fn` (web_bridge y
    main.py lo cumplen). Devuelve (resultado, por_en_ui)."""
    en_ui = _de_ctx(ctx, "en_ui")
    if callable(en_ui):
        return en_ui(fn), True
    return fn(), False


def _durmiendo(asistente: Any) -> Optional[bool]:
    """¿Duerme ya? Mira `durmiendo` (atributo, propiedad o método) o `_durmiendo`."""
    for nombre in ("durmiendo", "_durmiendo"):
        v = getattr(asistente, nombre, None)
        if callable(v):
            try:
                v = v()
            except Exception:
                v = None
        if isinstance(v, bool):
            return v
    return None


_YA_ESTABA = object()     # centinela: ya estaba dormida / despierta


def _herramienta(ctx: Any, metodo: str, quiere_dormida: bool) -> Union[str, Tuple[bool, str]]:
    asistente = _de_ctx(ctx, "asistente")
    if asistente is None:
        return False, ("No estoy en el escritorio: sácame primero y me echo la siesta ahí."
                       if quiere_dormida
                       else "No estoy en el escritorio: no hay nada que despertar.")
    fn = getattr(asistente, metodo, None)
    if not callable(fn):
        return False, ("Con esta figura todavía no sé dormirme." if quiere_dormida
                       else "Con esta figura todavía no sé despertarme.")

    def paso():
        # Todo en el hilo de Qt (con en_ui): mirar si ya lo está y, si no, pedirlo.
        if _durmiendo(asistente) is quiere_dormida:
            return _YA_ESTABA
        return fn()

    try:
        r, por_en_ui = _llamar_en_ui(ctx, paso)
        if r is _YA_ESTABA:
            return "Ya estoy dormida. Shh." if quiere_dormida else "Ya estaba despierta."
        if r is None and por_en_ui:
            # Un en_ui que no devuelve el resultado (o un dormir() sin valor): no se
            # da por hecho. Se vuelve a preguntar, también en el hilo de Qt.
            ahora = _llamar_en_ui(ctx, lambda: _durmiendo(asistente))[0]
            if ahora is None:
                return False, ("Lo intenté, pero no pude comprobar si "
                               + ("me quedé dormida." if quiere_dormida else "me desperté."))
            r = ahora is quiere_dormida
    except Exception as e:
        return False, f"No pude {'dormirme' if quiere_dormida else 'despertarme'}: {e}"[:300]
    if r is False:
        return False, ("Ahora no puedo dormirme: estoy liada." if quiere_dormida
                       else "No pude despertarme.")
    return ("Vale, me echo una siesta. Una caricia y vuelvo." if quiere_dormida
            else "Ya estoy despierta. ¿Qué pasa?")


def herramienta_dormir(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `asistente_dormir` ({}). Llama a `ctx['asistente'].dormir()`.

    `ctx` es un dict (u objeto) con `asistente` y, opcional, `en_ui(fn)` para
    ejecutar en el hilo de Qt. Devuelve el texto para el modelo; `(False, motivo)`
    si no hay asistente a la vista, su figura no sabe dormirse o `dormir()` devolvió False.
    """
    return _herramienta(ctx, "dormir", True)


def herramienta_despertar(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `asistente_despertar` ({}). Llama a `ctx['asistente'].despertar()`."""
    return _herramienta(ctx, "despertar", False)


__all__ = (
    "PERMITIDOS_POR_DEFECTO", "NUNCA", "BLOQUEOS", "ReglaSueno",
    "herramienta_dormir", "herramienta_despertar",
)
