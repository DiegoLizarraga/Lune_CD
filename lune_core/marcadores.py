"""
lune_core/marcadores.py — Canal de control dentro del texto del modelo.

Portado de core-agent/runtime/llm-marker-parser.ts y pipelines-audio de AIRI.
El modelo intercala en su respuesta tokens de control que NO se leen en voz ni
se muestran como texto:

    Me alegro mucho <|ACT {"emotion":"happy","intensity":0.8}|> de verte.
    Un momento… <|DELAY 1.5|> ya está.

`ParserMarcadores.consumir(chunk)` recibe el stream en trozos y devuelve una
lista de piezas `(clase, valor)` donde clase es:
    "texto"    → texto hablable/mostrable, tal cual
    "act"      → dict {emotion, intensity, motion} normalizado
    "delay"    → float segundos
    "call"     → [nombre, args?]  (herramienta que pide el modelo; 9.5)

Es incremental y a prueba de cortes: si un chunk termina a mitad de un `<|…`,
retiene la cola hasta el siguiente chunk. Sin dependencias.
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

Pieza = Tuple[str, Any]

# Vocabulario canónico de emociones (AIRI stage-ui/constants/emotions.ts).
EMOCIONES = ("happy", "sad", "angry", "think", "surprised",
             "awkward", "question", "curious", "neutral",
             # v10 — expresividad: coinciden con los clips animados de la mascota.
             "nervous",   # nerviosa / con duda (gota de sudor)
             "wave",      # saludo / despedida
             "dismiss")   # rechaza o corrige sin ganas (gesto de "no")

# Estados que ya usaba lune_face → emoción canónica.
ALIAS_EMOCION = {
    "normal": "neutral", "typing": "think", "reading": "think",
    "confused": "question", "error": "sad", "thinking": "think",
    "surprise": "surprised", "fun": "happy", "joy": "happy",
    "sorrow": "sad", "excited": "happy",
    # v10
    "hello": "wave", "hi": "wave", "greet": "wave", "greeting": "wave",
    "bye": "wave", "goodbye": "wave", "adios": "wave", "hola": "wave",
    "worried": "nervous", "anxious": "nervous", "nervioso": "nervous",
    "nerviosa": "nervous", "unamused": "dismiss", "dismissive": "dismiss",
    "rechazo": "dismiss", "no": "dismiss", "annoyed": "dismiss",
}

_ABRE = "<|"
_CIERRA = "|>"
# Prefijos válidos tras "<|" (mayúsculas, como en AIRI).
_PREFIJOS = ("ACT ", "ACT:", "DELAY ", "DELAY:", "CALL ", "CALL:")


def normalizar_emocion(nombre: Optional[str]) -> str:
    n = (nombre or "").strip().lower()
    n = ALIAS_EMOCION.get(n, n)
    return n if n in EMOCIONES else "neutral"


def normalizar_act(payload: Any) -> dict:
    """
    Acepta las formas que emiten los modelos y devuelve siempre
    {emotion: str∈EMOCIONES, intensity: float∈[0,1], motion: str|None}.
      "happy"                                    → emoción simple
      {"emotion":"happy","intensity":0.8}
      {"emotion":{"name":"happy","intensity":1},"motion":"wave"}
    """
    emocion, intensidad, motion = "neutral", 1.0, None
    if isinstance(payload, str):
        emocion = payload
    elif isinstance(payload, dict):
        e = payload.get("emotion", payload.get("name"))
        if isinstance(e, dict):
            emocion = e.get("name", "neutral")
            intensidad = e.get("intensity", payload.get("intensity", 1.0))
        else:
            emocion = e if e is not None else "neutral"
            intensidad = payload.get("intensity", 1.0)
        motion = payload.get("motion")
    try:
        intensidad = float(intensidad)
    except (TypeError, ValueError):
        intensidad = 1.0
    intensidad = max(0.0, min(1.0, intensidad))
    return {"emotion": normalizar_emocion(emocion), "intensity": intensidad,
            "motion": (str(motion) if motion else None)}


def _parsear_marcador(cuerpo: str) -> Optional[Pieza]:
    """`cuerpo` es lo que va entre <| y |>. Devuelve la pieza o None si no cuela."""
    cuerpo = cuerpo.strip()
    for etiqueta, clase in (("ACT", "act"), ("DELAY", "delay"), ("CALL", "call")):
        if cuerpo.upper().startswith(etiqueta):
            resto = cuerpo[len(etiqueta):].lstrip(": ").strip()
            if clase == "delay":
                try:
                    return ("delay", max(0.0, float(resto)))
                except ValueError:
                    return None
            try:
                payload = json.loads(resto) if resto else None
            except json.JSONDecodeError:
                # ACT admite emoción suelta sin comillas: <|ACT happy|>
                if clase == "act" and re.fullmatch(r"[A-Za-z_]+", resto):
                    payload = resto
                else:
                    return None
            if clase == "act":
                return ("act", normalizar_act(payload))
            if clase == "call":
                if isinstance(payload, list) and payload:
                    return ("call", payload)
                return None
    return None


class ParserMarcadores:
    def __init__(self):
        self._buffer = ""

    def consumir(self, chunk: str) -> List[Pieza]:
        """Procesa un trozo del stream y devuelve las piezas completas de él."""
        self._buffer += chunk
        piezas: List[Pieza] = []
        while True:
            i = self._buffer.find(_ABRE)
            if i == -1:
                # No hay marcador abierto. Puede haber un "<" final suelto que
                # sea el principio de "<|": retén solo ese último carácter.
                corte = len(self._buffer)
                if self._buffer.endswith("<"):
                    corte -= 1
                if corte > 0:
                    piezas.append(("texto", self._buffer[:corte]))
                    self._buffer = self._buffer[corte:]
                break
            if i > 0:
                piezas.append(("texto", self._buffer[:i]))
                self._buffer = self._buffer[i:]
            # self._buffer empieza en "<|"
            j = self._buffer.find(_CIERRA)
            if j == -1:
                # marcador sin cerrar: espera más chunks
                break
            cuerpo = self._buffer[len(_ABRE):j]
            pieza = _parsear_marcador(cuerpo)
            if pieza is not None:
                piezas.append(pieza)
            else:
                # No era un marcador válido: se trata como texto literal.
                piezas.append(("texto", self._buffer[:j + len(_CIERRA)]))
            self._buffer = self._buffer[j + len(_CIERRA):]
        return piezas

    def vaciar(self) -> List[Pieza]:
        """Al terminar el stream: emite lo que quede como texto."""
        resto = self._buffer
        self._buffer = ""
        return [("texto", resto)] if resto else []


def limpiar_para_mostrar(texto: str) -> str:
    """
    Quita los marcadores de un texto que se está mostrando en vivo, incluida una
    cola `<|…` sin cerrar al final del buffer (para que no parpadee mientras el
    modelo aún está escribiendo el marcador).
    """
    texto = re.sub(r"<\|.*?\|>", "", texto, flags=re.DOTALL)
    corte = texto.rfind(_ABRE)
    if corte != -1 and _CIERRA not in texto[corte:]:
        texto = texto[:corte]
    return texto


def separar(texto: str) -> Tuple[str, List[Pieza]]:
    """
    Atajo para texto ya completo (no streaming): devuelve
    (texto_hablable, [piezas de control]).
    """
    parser = ParserMarcadores()
    piezas = parser.consumir(texto) + parser.vaciar()
    hablable = "".join(v for c, v in piezas if c == "texto")
    control = [(c, v) for c, v in piezas if c != "texto"]
    return hablable, control
