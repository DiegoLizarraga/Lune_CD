"""
lune_core/frases_mascota.py — Lo que dice la mascota cuando le pasa algo.

PARA QUÉ SIRVE
--------------
Frases cortas, sin pasar por el modelo, para los eventos de la mascota: la
arrastras, la sueltas, la acaricias, se duerme, se despierta, se marea al
agitarla, aparece en pantalla, se sienta en la barra o en una ventana, se baja
o come algo (cortes 7 y 8). Antes vivían fijas en `ui_web/companion_vrm.html`
(`FRASES`, 4 eventos) y cada página tiraba su dado. Ahora hay un solo sitio:

- `FRASES_BASE`: las de Lune, con su tono (directa y con filo, nada de «amo~»).
  Incluye las cuatro listas que había en companion_vrm.html.
- `PROBABILIDADES`: no habla SIEMPRE que pasa algo (se haría pesada).
- `FrasesMascota(personaje, reloj, rng)`:
    `elegir(evento)` → texto o None. Tira el dado con la probabilidad del
    evento, saca la frase de una `Bolsa` (no repite hasta agotar la lista) y
    respeta un COOLDOWN GLOBAL de 20 s entre frases de cualquier evento. El
    mareo es prioritario: se salta el cooldown (lo arranca igual), porque es la
    reacción que el usuario busca al zarandearla y tiene su propio enfriamiento
    de 10 s en la página.
    `como_json()` → lo que se le manda a la página con `luneFrases(json)` para
    que elija ella en los eventos que solo ve JS (caricia en el VRM…).

Cada personaje puede traer las suyas en `datos.json`:

    "frases_mascota": {
        "arrastre": ["¡Eh, que me mareo!"],         # sustituye a las de Lune
        "caricia": {"frases": ["Jeje"], "p": 0.9},  # con su propia probabilidad
        "soltar": []                                # lista vacía = callada en ese evento
    }

Lo que no traiga sale de FRASES_BASE. Eventos desconocidos (p. ej. «pudor», que
está fuera del alcance de esta versión) se ignoran. Los eventos «sentarse»,
«bajar» y «comer» los dicen las mascotas de escritorio (ui/companion.py y
ui/avatar_overlay.py) al sentarse, bajarse y comer.

Sin Qt ni red: reloj y azar inyectables, así los tests son deterministas.
"""
from __future__ import annotations

import json
import math
import random
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ── Eventos y probabilidades ─────────────────────────────────────────────────────
EVENTOS: Tuple[str, ...] = ("arrastre", "soltar", "caricia", "dormir", "despertar", "mareo", "aparecer",
                            "sentarse", "bajar", "comer")

PROBABILIDADES: Dict[str, float] = {
    "arrastre": 0.45,
    "soltar": 0.30,
    "caricia": 0.60,
    "dormir": 0.50,
    "despertar": 0.70,
    "mareo": 1.00,
    "aparecer": 0.50,
    "sentarse": 0.40,       # se sienta en la barra o en una ventana (corte 7)
    "bajar": 0.30,          # se baja (la bajan o se levanta sola)
    "comer": 0.50,          # le das de comer (corte 8)
}

COOLDOWN_S = 20.0

# Eventos que no esperan al cooldown global (pero lo reinician al hablar).
PRIORITARIOS = frozenset({"mareo"})

# Límites para las frases que vienen de datos.json (las escribe el usuario).
MAX_FRASES = 40
MAX_LARGO = 140

FRASES_BASE: Dict[str, Tuple[str, ...]] = {
    "arrastre": (
        # las cuatro de companion_vrm.html
        "Eh, eh, ¿a dónde me llevas?",
        "¿Me mudas de sitio otra vez?",
        "Vale, pero con cuidado.",
        "Ay… no me sueltes.",
        "Esto no venía en el contrato.",
        "¿Tienes carné para esto?",
        "Más despacio, que no soy un icono.",
    ),
    "soltar": (
        "Aquí está bien. Supongo.",
        "Aterrizaje aceptable.",
        "¿Ya? Qué viaje tan corto.",
        "Gracias por el paseo. Creo.",
        "Me quedo aquí. De momento.",
    ),
    "caricia": (
        "…Está bien, un poco más.",
        "Eso. Justo ahí.",
        "No te acostumbres.",
        "Mm. Te lo permito.",
        "Ni una palabra de esto a nadie.",
    ),
    "dormir": (
        "zzz…",
        "Cinco minutos. Solo cinco.",
        "Me apago un rato. No toques nada.",
        "Si pasa algo interesante, despiértame.",
    ),
    "despertar": (
        "¿Eh? Ya, ya estoy.",
        "No estaba dormida. Pensaba.",
        "¿Cuánto rato ha pasado? No contestes.",
        "Vale, vale. Ya me levanto.",
    ),
    "mareo": (
        "Para, para… el escritorio da vueltas.",
        "Voy a vomitar píxeles.",
        "¿Esto era necesario? Porque no lo parecía.",
        "Veo dos cursores. Y los dos son culpa tuya.",
    ),
    "aparecer": (
        "Aquí estoy. ¿Qué rompemos hoy?",
        "Volví. ¿Me echaste de menos? No contestes.",
        "Presente. Más o menos despierta.",
        "Hola. Haz como que no me ves.",
    ),
    "sentarse": (
        "Buen sitio. Me lo quedo.",
        "Desde aquí arriba se ve todo mejor.",
        "No te importa que me siente, ¿verdad? Da igual, ya estoy.",
        "Asiento con vistas. Aceptable.",
        "No muevas la ventana. O sí, ya veremos.",
    ),
    "bajar": (
        "Vale, ya bajo.",
        "Se acabó el descanso, por lo visto.",
        "¿Ya? Estaba cómoda.",
        "Bajando. Sin prisas.",
    ),
    "comer": (
        "Mm. Esto sí.",
        "¿Era para mí? Demasiado tarde.",
        "No está mal. Nada mal.",
        "Gracias. No se lo digas a nadie.",
        "Otro y te perdono lo de antes.",
    ),
}


# ── Bolsa: azar sin repetir ──────────────────────────────────────────────────────
_NADA = object()


class Bolsa:
    """Saca los elementos en orden barajado, sin repetir hasta agotarlos.

    Igual que `Bolsa` de `ui_web/vrm/lune_modulos.js`: al rellenar, el primero
    de la tanda nueva nunca es el último de la anterior (si hay más de uno), así
    que tampoco repite en el cambio de tanda.

        b = Bolsa(["a", "b", "c"], random.Random(7))
        b.siguiente()
    """

    def __init__(self, elementos: Iterable[Any] = (), rng: Optional[random.Random] = None):
        self._rng = rng if rng is not None else random.Random()
        self.ultimo: Any = _NADA
        self.elementos: List[Any] = []
        self._pila: List[Any] = []
        self.cambiar(elementos)

    def cambiar(self, elementos: Iterable[Any]) -> "Bolsa":
        """Sustituye los elementos y vacía la tanda en curso."""
        self.elementos = list(elementos)
        self._pila = []
        return self

    @property
    def quedan(self) -> int:
        return len(self._pila)

    def _indice(self, n: int) -> int:
        try:
            r = float(self._rng.random())
        except Exception:
            r = 0.0
        if not math.isfinite(r):
            r = 0.0
        return min(n - 1, max(0, int(r * n)))

    def _rellenar(self) -> None:
        p = list(self.elementos)
        for i in range(len(p) - 1, 0, -1):          # Fisher-Yates
            j = self._indice(i + 1)
            p[i], p[j] = p[j], p[i]
        # Se saca con pop(): el primero de la tanda es el último de la lista.
        if len(p) > 1 and self.ultimo is not _NADA and p[-1] == self.ultimo:
            p[0], p[-1] = p[-1], p[0]
        self._pila = p

    def siguiente(self) -> Any:
        """El siguiente elemento, o None si la bolsa está vacía."""
        if not self.elementos:
            return None
        if not self._pila:
            self._rellenar()
        self.ultimo = self._pila.pop()
        return self.ultimo


# ── Frases de un personaje ───────────────────────────────────────────────────────
def _limpiar_frase(f: Any) -> str:
    """Una frase de datos.json en una línea, sin espacios de más y recortada."""
    if not isinstance(f, str):
        return ""
    s = " ".join(f.split())
    if len(s) > MAX_LARGO:
        s = s[:MAX_LARGO - 1].rstrip() + "…"
    return s


def _probabilidad(valor: Any) -> Optional[float]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    p = float(valor)
    if not math.isfinite(p):
        return None
    return min(1.0, max(0.0, p))


def _override(valor: Any) -> Optional[Tuple[List[str], Optional[float]]]:
    """Lo que trae un personaje para un evento → (frases, prob|None), o None si no vale.

    Admite una lista, una sola frase (str) o {"frases": [...], "p": 0..1}. Una
    lista vacía silencia el evento; una lista sin ninguna frase válida se ignora.
    """
    prob = None
    if isinstance(valor, Mapping):
        prob = _probabilidad(valor.get("p", valor.get("prob")))
        if "frases" not in valor:
            return ([], prob) if prob is not None else None
        valor = valor.get("frases")
        if valor is None:
            return None
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, (list, tuple)):
        return None
    frases: List[str] = []
    for f in valor:
        s = _limpiar_frase(f)
        if s and s not in frases:
            frases.append(s)
        if len(frases) >= MAX_FRASES:
            break
    if valor and not frases:
        return None                              # todo basura: se queda la base
    return frases, prob


def frases_de_personaje(personaje: Optional[Mapping[str, Any]]) -> Dict[str, Tuple[List[str], float]]:
    """Frases y probabilidad efectivas por evento: FRASES_BASE + lo del personaje.

    Cuando el personaje solo trae una probabilidad ({"p": 0.9}) se conservan las
    frases de la base para ese evento.
    """
    efectivas: Dict[str, Tuple[List[str], float]] = {
        ev: (list(FRASES_BASE[ev]), PROBABILIDADES[ev]) for ev in EVENTOS
    }
    extra = personaje.get("frases_mascota") if isinstance(personaje, Mapping) else None
    if not isinstance(extra, Mapping):
        return efectivas
    for ev, valor in extra.items():
        ev = str(ev).strip().lower()
        if ev not in efectivas:
            continue
        ov = _override(valor)
        if ov is None:
            continue
        frases, prob = ov
        base_frases, base_p = efectivas[ev]
        solo_prob = isinstance(valor, Mapping) and "frases" not in valor
        efectivas[ev] = (base_frases if solo_prob else frases, base_p if prob is None else prob)
    return efectivas


class FrasesMascota:
    """Elige qué dice la mascota en cada evento.

    `personaje`: el dict del personaje activo (o None → solo FRASES_BASE).
    `reloj`: función → segundos monótonos (por defecto time.monotonic).
    `rng`: un `random.Random` (sembrado en los tests).
    `cooldown_s`: silencio mínimo entre dos frases, de cualquier evento.
    """

    def __init__(self, personaje: Optional[Mapping[str, Any]] = None,
                 reloj: Optional[Callable[[], float]] = None,
                 rng: Optional[random.Random] = None,
                 cooldown_s: float = COOLDOWN_S,
                 prioritarios: Iterable[str] = PRIORITARIOS):
        self._reloj = reloj or time.monotonic
        self._rng = rng if rng is not None else random.Random()
        self.cooldown_s = max(0.0, float(cooldown_s))
        self.prioritarios = frozenset(prioritarios)
        self._ultima_t: Optional[float] = None
        self.ultima: Optional[Tuple[str, str]] = None      # (evento, frase) de la última que dijo
        self._frases: Dict[str, List[str]] = {}
        self._prob: Dict[str, float] = {}
        self._bolsas: Dict[str, Bolsa] = {}
        self.nombre = ""
        self.set_personaje(personaje)

    # ── Personaje ──
    def set_personaje(self, personaje: Optional[Mapping[str, Any]]) -> None:
        """Cambia de personaje: rehace las listas (el cooldown se conserva)."""
        self.nombre = str(personaje.get("nombre", "")) if isinstance(personaje, Mapping) else ""
        efectivas = frases_de_personaje(personaje)
        self._frases = {ev: frases for ev, (frases, _) in efectivas.items()}
        self._prob = {ev: p for ev, (_, p) in efectivas.items()}
        self._bolsas = {ev: Bolsa(frases, self._rng) for ev, frases in self._frases.items()}

    def frases(self, evento: str) -> List[str]:
        """Las frases efectivas de un evento (copia). [] si no existe o está callado."""
        return list(self._frases.get(evento, ()))

    def probabilidad(self, evento: str) -> float:
        return self._prob.get(evento, 0.0)

    # ── Cooldown ──
    def restante_cooldown(self) -> float:
        """Segundos que faltan para poder volver a hablar (0 si ya puede)."""
        if self._ultima_t is None:
            return 0.0
        return max(0.0, self.cooldown_s - (self._reloj() - self._ultima_t))

    def en_cooldown(self) -> bool:
        return self.restante_cooldown() > 0.0

    def reiniciar_cooldown(self) -> None:
        """Olvida la última frase: la siguiente puede salir ya."""
        self._ultima_t = None

    def marcar_hablado(self) -> None:
        """Arranca el cooldown sin elegir frase (p. ej. si la mascota dijo otra cosa)."""
        self._ultima_t = self._reloj()

    # ── Elegir ──
    def elegir(self, evento: str, forzar: bool = False) -> Optional[str]:
        """La frase para `evento`, o None si esta vez calla.

        Calla si: el evento no existe o no tiene frases, estamos en cooldown (salvo
        eventos prioritarios o `forzar`), o el dado no sale (salvo `forzar`). En
        cooldown no se tira el dado. Si habla, arranca el cooldown.
        """
        evento = str(evento or "").strip().lower()
        frases = self._frases.get(evento)
        if not frases:
            return None
        if not forzar and evento not in self.prioritarios and self.en_cooldown():
            return None
        if not forzar:
            p = self._prob.get(evento, 0.0)
            if p <= 0.0:
                return None
            if p < 1.0 and self._rng.random() >= p:
                return None
        frase = self._bolsas[evento].siguiente()
        if frase is None:
            return None
        self._ultima_t = self._reloj()
        self.ultima = (evento, frase)
        return frase

    # ── Para la página ──
    def como_dict(self) -> Dict[str, Any]:
        """Todo lo que la página necesita para elegir ella (ver `como_json`)."""
        return {
            "v": 1,
            "personaje": self.nombre,
            "cooldown_s": self.cooldown_s,
            "prioritarios": sorted(self.prioritarios),
            "eventos": {ev: {"p": self._prob[ev], "frases": list(self._frases[ev])} for ev in EVENTOS},
        }

    def como_json(self) -> str:
        """JSON para `window.luneFrases(json)`:

            {"v": 1, "personaje": "Lune", "cooldown_s": 20.0, "prioritarios": ["mareo"],
             "eventos": {"arrastre": {"p": 0.45, "frases": ["…", …]}, …}}

        Siempre trae todos los eventos de EVENTOS; `frases: []` = callada en ese evento.
        """
        return json.dumps(self.como_dict(), ensure_ascii=False, separators=(",", ":"))


def frases_para(personaje: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> FrasesMascota:
    """Atajo: `FrasesMascota` del personaje dado o, si es None, del activo en datos.json."""
    if personaje is None:
        try:
            from nucleo import personajes
            personaje = personajes.get_activo()
        except Exception:
            personaje = None
    return FrasesMascota(personaje, **kwargs)


__all__: Sequence[str] = (
    "EVENTOS", "PROBABILIDADES", "COOLDOWN_S", "PRIORITARIOS", "FRASES_BASE",
    "Bolsa", "FrasesMascota", "frases_de_personaje", "frases_para",
)
