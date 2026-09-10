"""
lune_core/expresiones.py — Plan de expresiones de una respuesta.

El modelo intercala hasta MAX_ACTS marcadores <|ACT|> en su texto: uno al
empezar y los demás justo antes del tramo cuyo ánimo cambia. De ahí sale un
PLAN: una lista de tramos (emoción, intensidad, texto hablable) en orden.

    "<|ACT happy|>¡Qué bien! <|ACT laughing|>jaja, no me lo creo."
        → [Tramo(happy, "¡Qué bien! "), Tramo(laughing, "jaja, no me lo creo.")]

Quien lo usa decide el ritmo:
  · con voz, cada tramo se habla con su expresión (VoiceEngine.speak_segmentos);
  · sin voz y en streaming, la expresión cambia según llega el texto (SeguidorActs);
  · sin voz y de golpe, con un ritmo de lectura (horario()).
La última expresión SE QUEDA: si la haces reír, sigue riéndose hasta el siguiente
mensaje (o hasta que se aburra).

Sin Qt ni dependencias: se prueba en seco.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from lune_core import marcadores

MAX_ACTS = 3                     # los que se le piden al modelo (si manda más, se respetan)
CARACTERES_POR_SEGUNDO = 16.0    # ritmo de lectura para planificar sin voz
MINIMO_TRAMO_S = 0.9             # ningún tramo dura menos que esto en pantalla


@dataclass
class Tramo:
    emocion: str            # canónica (marcadores.EMOCIONES) o "" si el modelo no marcó nada
    intensidad: float
    texto: str

    @property
    def segundos(self) -> float:
        return duracion_lectura(self.texto)


def duracion_lectura(texto: str) -> float:
    """Cuánto tarda en leerse `texto`, en segundos."""
    return max(MINIMO_TRAMO_S, len((texto or "").strip()) / CARACTERES_POR_SEGUNDO)


def planificar(respuesta: str) -> List[Tramo]:
    """
    Trocea la respuesta por sus <|ACT|>. Cada tramo lleva la emoción del marcador
    que lo precede; el texto anterior al primer marcador hereda la primera emoción
    (el modelo suele marcar al empezar; si no, es el mismo ánimo). Dos marcadores
    seguidos sin texto entre medias se funden (gana el último). Sin marcadores →
    un único tramo con emoción "".
    """
    parser = marcadores.ParserMarcadores()
    piezas = parser.consumir(respuesta or "") + parser.vaciar()
    tramos: List[Tramo] = []
    actual: Optional[dict] = None
    buffer = ""
    inicial = ""                     # texto anterior al primer marcador
    for clase, valor in piezas:
        if clase == "texto":
            if actual is None:
                inicial += valor
            else:
                buffer += valor
        elif clase == "act":
            if actual is not None:
                if buffer.strip():
                    tramos.append(Tramo(actual["emotion"], actual["intensity"], buffer))
                    buffer = ""
                # sin texto entre medias: el marcador nuevo sustituye al anterior
            actual = valor
        # delay / call no cambian el plan
    if actual is None:
        return [Tramo("", 1.0, inicial)]
    # El último marcador siempre cuenta, aunque no le siga texto: es la cara con la
    # que se queda Lune ("…y eso es todo <|ACT laughing|>").
    tramos.append(Tramo(actual["emotion"], actual["intensity"], buffer))
    if inicial:
        tramos[0] = Tramo(tramos[0].emocion, tramos[0].intensidad, inicial + tramos[0].texto)
    return tramos


def hablable(plan: List[Tramo]) -> str:
    return "".join(t.texto for t in plan)


def emociones(plan: List[Tramo]) -> List[str]:
    """Emociones del plan en orden (sin la vacía)."""
    return [t.emocion for t in plan if t.emocion]


def final(plan: List[Tramo], por_defecto: str = "") -> str:
    """La expresión con la que se queda Lune al terminar."""
    for t in reversed(plan):
        if t.emocion:
            return t.emocion
    return por_defecto


def horario(plan: List[Tramo]) -> List[Tuple[float, str, float]]:
    """
    Cuándo (segundos desde que se muestra la respuesta) empieza cada expresión,
    leyendo a CARACTERES_POR_SEGUNDO. Solo los tramos con emoción.
        [(0.0, "happy", 0.8), (2.4, "laughing", 1.0)]
    """
    salida = []
    t = 0.0
    for tramo in plan:
        if tramo.emocion:
            salida.append((round(t, 2), tramo.emocion, tramo.intensidad))
        t += tramo.segundos
    return salida


def segmentos_voz(plan: List[Tramo], estado_de=lambda e: e) -> List[Tuple[str, str]]:
    """Pares (etiqueta, texto) para VoiceEngine.speak_segmentos; la etiqueta es la
    emoción ya traducida con `estado_de` ("" si el tramo no la tiene)."""
    return [(estado_de(t.emocion) if t.emocion else "", t.texto) for t in plan if t.texto.strip()]


class SeguidorActs:
    """
    Para el streaming: se le da el texto ACUMULADO cada vez que llega un trozo y
    devuelve los <|ACT|> nuevos (completos) desde la última llamada. Un marcador
    a medias no cuenta hasta que se cierra.
    """

    def __init__(self):
        self._vistos = 0

    def nuevos(self, acumulado: str) -> List[dict]:
        _, control = marcadores.separar(acumulado or "")
        acts = [v for c, v in control if c == "act"]
        nuevos = acts[self._vistos:]
        self._vistos = len(acts)
        return nuevos

    @property
    def vistos(self) -> int:
        return self._vistos
