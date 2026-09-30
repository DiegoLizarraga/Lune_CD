"""
scripts/generar_sfx.py — Genera los efectos de sonido de Lune (WAV) con numpy.

Todos los sonidos cortos de la interfaz y de la asistente (alarma, arrastre, comida,
menú, blip de texto) se SINTETIZAN aquí: no se copia ningún audio de otros
proyectos (los de Mate-Engine tienen copyright). Salen WAV PCM de 44.1 kHz,
16 bits y mono en `ui_web/assets/sfx/`. El servidor local ya sirve esa carpeta en
`/assets/sfx/…` para las páginas (WebAudio) y el mezclador de Python los lee
directamente del disco (sprites y patata).

Reglas que cumplen todos:
- envolvente con ataque y caída suaves y bordes a cero (primera y última muestra
  valen 0), así que no hacen «clic» ni al empezar ni al cortarse ni en bucle;
- pico moderado (entre −16 y −7 dBFS): no asustan con los auriculares puestos;
- deterministas: el ruido usa una semilla fija por sonido, de modo que regenerar
  da los mismos bytes y git no ve cambios si no se tocó la receta.

Las alarmas (`alarma_1..3`) están pensadas para sonar en bucle: son pitidos de
880/660 Hz de 0.2 s con 0.15 s de silencio (casillas de 0.35 s), cada una con su
patrón, y acaban en silencio para que el salto del bucle no se note.

Uso:
    python scripts/generar_sfx.py                # escribe en ui_web/assets/sfx/
    python scripts/generar_sfx.py --destino X    # en otra carpeta (tests)
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
DIR_SFX = RAIZ / "ui_web" / "assets" / "sfx"

SR = 44_100            # frecuencia de muestreo (Hz)
CASILLA_ALARMA = 0.35  # 0.2 s sonando + 0.15 s de silencio
PITIDO = 0.20

LEEME = """Efectos de sonido de Lune CD
============================

Estos WAV (44.1 kHz, 16 bits, mono) NO se editan a mano: los genera

    python scripts/generar_sfx.py

sintetizándolos con numpy (nada copiado de otros proyectos). Para cambiar un
sonido, toca su receta en ese script y vuelve a ejecutarlo; el resultado es
determinista, así que solo cambian los archivos cuya receta cambió.

Sonidos:
  alarma_1..3        pitidos 880/660 Hz para sonar en bucle (~1.4 s)
  drag_start/stop    levantar y soltar a la asistente
  comida_aparece     aparece un plato
  comida_capa_1..2   se añade una capa a la comida
  trago_1..3         beber
  mordisco_1..3      morder
  blip               letra a letra en los globos de texto
  menu_abrir/cerrar  abrir y cerrar menús
  menu_boton         pulsar un botón de menú
"""


# ── Piezas básicas ────────────────────────────────────────────────────────────

def _n(dur: float) -> int:
    return max(1, int(round(dur * SR)))


def _t(dur: float) -> np.ndarray:
    return np.arange(_n(dur)) / SR


def _rampa(n: int) -> np.ndarray:
    """Media onda de coseno de 0 a 1 (exactamente 0 en la primera muestra)."""
    if n <= 1:
        return np.zeros(max(n, 0))
    return 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n))


def _bordes(x: np.ndarray, entrada: float = 0.002, salida: float = 0.010) -> np.ndarray:
    """Fuerza la entrada y la salida a cero con rampas de coseno (sin clicks)."""
    x = x.copy()
    ne, ns = min(_n(entrada), len(x) // 2), min(_n(salida), len(x) // 2)
    x[:ne] *= _rampa(ne)
    x[len(x) - ns:] *= _rampa(ns)[::-1]
    return x


def _env_percusiva(n: int, ataque: float, tau: float) -> np.ndarray:
    """Ataque suave de `ataque` s y caída exponencial con constante `tau` s."""
    t = np.arange(n) / SR
    env = np.exp(-np.maximum(t - ataque, 0.0) / tau)
    na = min(_n(ataque), n)
    env[:na] *= _rampa(na)
    return env


def _env_sostenida(n: int, ataque: float, relajacion: float, caida: float = 0.0) -> np.ndarray:
    """Envolvente de nota sostenida: sube, se mantiene (con caída opcional) y baja."""
    t = np.arange(n) / SR
    env = np.exp(-t * caida) if caida > 0 else np.ones(n)
    na, nr = min(_n(ataque), n // 2), min(_n(relajacion), n // 2)
    env[:na] *= _rampa(na)
    env[n - nr:] *= _rampa(nr)[::-1]
    return env


def _barrido(f0: float, f1: float, dur: float, exponencial: bool = True) -> np.ndarray:
    """Seno cuya frecuencia va de f0 a f1 (fase continua, empieza en 0)."""
    n = _n(dur)
    x = np.arange(n) / max(n - 1, 1)
    f = f0 * (f1 / f0) ** x if exponencial else f0 + (f1 - f0) * x
    fase = 2.0 * np.pi * (np.cumsum(f) - f[0]) / SR
    return np.sin(fase)


def _tono(f: float, dur: float, armonicos: Sequence[float] = ()) -> np.ndarray:
    """Seno de frecuencia f con armónicos opcionales (amplitudes de 2f, 3f…)."""
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t)
    for k, a in enumerate(armonicos, start=2):
        x = x + a * np.sin(2 * np.pi * k * f * t)
    return x


def _campana(f: float, dur: float, tau: float) -> np.ndarray:
    """Nota de campanita: fundamental + un parcial inarmónico que se apaga antes."""
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / (tau * 0.35))
    return x * _env_percusiva(len(t), 0.003, tau)


def _pasabajos(fc: float, taps: int = 129) -> np.ndarray:
    """FIR de paso bajo por sinc enventanada (Blackman), ganancia 1 en continua."""
    m = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2.0 * fc / SR * m) * np.blackman(taps)
    return h / h.sum()


def _filtrar(x: np.ndarray, desde: Optional[float] = None, hasta: Optional[float] = None) -> np.ndarray:
    """Pasa-banda sencillo: quita lo que está por debajo de `desde` y por encima de `hasta`."""
    y = x
    if hasta:
        y = np.convolve(y, _pasabajos(hasta), mode="same")
    if desde:
        y = y - np.convolve(y, _pasabajos(desde), mode="same")
    return y


def _ruido(dur: float, semilla: int, desde: Optional[float] = None, hasta: Optional[float] = None) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return _filtrar(rng.standard_normal(_n(dur)), desde, hasta)


def _lienzo(dur: float) -> np.ndarray:
    return np.zeros(_n(dur))


def _poner(lienzo: np.ndarray, x: np.ndarray, t0: float, ganancia: float = 1.0) -> np.ndarray:
    """Suma `x` en el lienzo a partir del segundo t0 (recorta lo que no quepa).

    Cada pieza entra con sus propios bordes a cero: si su envolvente no había
    llegado a 0 cuando se acaba el array, el corte daría un clic a mitad del sonido.
    """
    i = _n(t0) if t0 > 0 else 0
    fin = min(len(lienzo), i + len(x))
    if fin > i:
        lienzo[i:fin] += ganancia * _bordes(x[:fin - i], entrada=0.001, salida=0.004)
    return lienzo


def _normalizar(x: np.ndarray, pico_db: float) -> np.ndarray:
    """Escala para que el pico quede en `pico_db` dBFS."""
    pico = float(np.max(np.abs(x)))
    if pico <= 0:
        return x
    return x * (10.0 ** (pico_db / 20.0) / pico)


def _acabar(x: np.ndarray, pico_db: float, salida: float = 0.010) -> np.ndarray:
    """Último paso de toda receta: bordes a cero y pico en `pico_db` dBFS."""
    return _normalizar(_bordes(x, salida=salida), pico_db)


# ── Recetas ───────────────────────────────────────────────────────────────────

def alarma(patron: Sequence[float]) -> np.ndarray:
    """Casillas de 0.35 s: pitido de 0.2 s a la frecuencia dada (0 = casilla muda)."""
    lienzo = _lienzo(CASILLA_ALARMA * len(patron))
    for i, f in enumerate(patron):
        if not f:
            continue
        p = _tono(f, PITIDO, armonicos=(0.22, 0.08))
        p *= _env_sostenida(len(p), ataque=0.006, relajacion=0.022, caida=1.5)
        _poner(lienzo, p, i * CASILLA_ALARMA)
    return _acabar(lienzo, -7.0)


def drag_start() -> np.ndarray:
    """La levantas: barrido corto hacia arriba con un soplo suave."""
    lienzo = _lienzo(0.17)
    tono = _barrido(280, 620, 0.12) + 0.2 * _barrido(560, 1240, 0.12)
    _poner(lienzo, tono * _env_percusiva(len(tono), 0.005, 0.045), 0.0)
    soplo = _ruido(0.08, 11, desde=900, hasta=4200)
    _poner(lienzo, soplo * _env_percusiva(len(soplo), 0.004, 0.02), 0.0, 0.25)
    return _acabar(lienzo, -12.0)


def drag_stop() -> np.ndarray:
    """La sueltas: barrido hacia abajo y un golpecito grave al «aterrizar»."""
    lienzo = _lienzo(0.22)
    tono = _barrido(520, 210, 0.12)
    _poner(lienzo, tono * _env_percusiva(len(tono), 0.004, 0.05), 0.0)
    golpe = _barrido(150, 90, 0.12)
    _poner(lienzo, golpe * _env_percusiva(len(golpe), 0.003, 0.035), 0.07, 0.9)
    return _acabar(lienzo, -12.0)


def comida_aparece() -> np.ndarray:
    """Aparece un plato: «pop» suave y arpegio de campanitas (mi mayor) hacia arriba."""
    lienzo = _lienzo(0.55)
    pop = _barrido(320, 130, 0.05)
    _poner(lienzo, pop * _env_percusiva(len(pop), 0.003, 0.018), 0.0, 0.8)
    for i, f in enumerate((1318.5, 1661.2, 1975.5)):
        _poner(lienzo, _campana(f, 0.40, 0.11), 0.03 + 0.065 * i, 0.55 - 0.08 * i)
    return _acabar(lienzo, -12.0, salida=0.02)


def _plop(f0: float, f1: float, dur: float, semilla: int) -> np.ndarray:
    lienzo = _lienzo(dur + 0.06)
    tono = _barrido(f0, f1, dur)
    _poner(lienzo, tono * _env_percusiva(len(tono), 0.003, dur * 0.45), 0.0)
    textura = _ruido(0.03, semilla, desde=300, hasta=2200)
    _poner(lienzo, textura * _env_percusiva(len(textura), 0.002, 0.008), 0.0, 0.3)
    return lienzo


def comida_capa_1() -> np.ndarray:
    """Se añade una capa: «plop» blandito."""
    return _acabar(_plop(430, 180, 0.08, 21), -12.0)


def comida_capa_2() -> np.ndarray:
    """Otra capa: doble «plop» algo más agudo, para no repetir siempre el mismo."""
    lienzo = _lienzo(0.2)
    _poner(lienzo, _plop(560, 240, 0.06, 22), 0.0)
    _poner(lienzo, _plop(470, 210, 0.05, 23), 0.065, 0.6)
    return _acabar(lienzo, -12.0)


def _trago(f0: float, f1: float, dur: float, semilla: int, burbuja: bool) -> np.ndarray:
    """«Glup»: tono grave que sube (el líquido) con un chasquido húmedo al principio."""
    lienzo = _lienzo(dur + 0.1)
    subida = _barrido(f0, f1, dur)
    subida = subida + 0.35 * _barrido(2 * f0, 2 * f1, dur)
    env = _env_sostenida(len(subida), ataque=0.012, relajacion=dur * 0.5, caida=6.0)
    _poner(lienzo, subida * env, 0.0)
    chasquido = _ruido(0.04, semilla, desde=250, hasta=1400)
    _poner(lienzo, chasquido * _env_percusiva(len(chasquido), 0.002, 0.012), 0.0, 0.35)
    if burbuja:
        b = _barrido(f1 * 1.2, f1 * 1.6, 0.04)
        _poner(lienzo, b * _env_percusiva(len(b), 0.003, 0.012), dur * 0.85, 0.45)
    return _acabar(lienzo, -11.0)


def trago_1() -> np.ndarray:
    return _trago(150, 280, 0.10, 31, burbuja=False)


def trago_2() -> np.ndarray:
    return _trago(130, 240, 0.12, 32, burbuja=True)


def trago_3() -> np.ndarray:
    return _trago(170, 320, 0.09, 33, burbuja=True)


def _mordisco(semilla: int, granos: int, separacion: float) -> np.ndarray:
    """Crujido: varios granos de ruido agudo muy cortos, cada vez más flojos."""
    rng = np.random.default_rng(semilla)
    lienzo = _lienzo(0.06 + granos * separacion + 0.05)
    golpe = _barrido(210, 140, 0.05)
    _poner(lienzo, golpe * _env_percusiva(len(golpe), 0.002, 0.018), 0.0, 0.5)
    t0 = 0.0
    for g in range(granos):
        dur = float(rng.uniform(0.018, 0.03))
        grano = _ruido(dur, semilla * 10 + g, desde=1400, hasta=7000)
        grano *= _env_percusiva(len(grano), 0.001, float(rng.uniform(0.006, 0.012)))
        _poner(lienzo, grano, t0, 0.95 ** g * float(rng.uniform(0.7, 1.0)))
        t0 += separacion * float(rng.uniform(0.8, 1.2))
    return _acabar(lienzo, -11.0)


def mordisco_1() -> np.ndarray:
    return _mordisco(41, granos=3, separacion=0.028)


def mordisco_2() -> np.ndarray:
    return _mordisco(42, granos=4, separacion=0.024)


def mordisco_3() -> np.ndarray:
    return _mordisco(43, granos=2, separacion=0.034)


def blip() -> np.ndarray:
    """Blip de texto (suena muchas veces seguidas): cortito y flojo."""
    lienzo = _lienzo(0.06)
    b = _tono(1320, 0.05, armonicos=(0.15,))
    _poner(lienzo, b * _env_percusiva(len(b), 0.002, 0.016), 0.0)
    return _acabar(lienzo, -16.0, salida=0.006)


def _dos_notas(f1: float, f2: float) -> np.ndarray:
    lienzo = _lienzo(0.24)
    _poner(lienzo, _campana(f1, 0.16, 0.05), 0.0, 0.85)
    _poner(lienzo, _campana(f2, 0.18, 0.06), 0.055, 1.0)
    return lienzo


def menu_abrir() -> np.ndarray:
    """Abrir un menú: dos notas hacia arriba (sol → re)."""
    return _acabar(_dos_notas(784.0, 1174.7), -14.0)


def menu_cerrar() -> np.ndarray:
    """Cerrar un menú: las mismas dos notas hacia abajo."""
    return _acabar(_dos_notas(1174.7, 784.0), -14.0)


def menu_boton() -> np.ndarray:
    """Pulsar un botón: «tic» breve con un clic suave de ruido."""
    lienzo = _lienzo(0.06)
    tic = _tono(1600, 0.045)
    _poner(lienzo, tic * _env_percusiva(len(tic), 0.0015, 0.011), 0.0)
    clic = _ruido(0.012, 51, desde=3000, hasta=9000)
    _poner(lienzo, clic * _env_percusiva(len(clic), 0.0008, 0.003), 0.0, 0.3)
    return _acabar(lienzo, -16.0, salida=0.006)


SONIDOS: Dict[str, Callable[[], np.ndarray]] = {
    "alarma_1": lambda: alarma((880, 660, 880, 660)),  # ding-dong alterno
    "alarma_2": lambda: alarma((880, 880, 880, 0)),    # tres agudos y pausa
    "alarma_3": lambda: alarma((660, 660, 880, 0)),    # dos graves, uno agudo y pausa
    "drag_start": drag_start,
    "drag_stop": drag_stop,
    "comida_aparece": comida_aparece,
    "comida_capa_1": comida_capa_1,
    "comida_capa_2": comida_capa_2,
    "trago_1": trago_1,
    "trago_2": trago_2,
    "trago_3": trago_3,
    "mordisco_1": mordisco_1,
    "mordisco_2": mordisco_2,
    "mordisco_3": mordisco_3,
    "blip": blip,
    "menu_abrir": menu_abrir,
    "menu_cerrar": menu_cerrar,
    "menu_boton": menu_boton,
}


# ── Salida ────────────────────────────────────────────────────────────────────

def sintetizar(nombre: str) -> np.ndarray:
    """Muestras float en [-1, 1] del sonido `nombre` (sin tocar el disco)."""
    return np.clip(SONIDOS[nombre](), -1.0, 1.0)


def escribir_wav(ruta: Path, muestras: np.ndarray) -> None:
    """WAV PCM 16 bits mono a 44.1 kHz (sin metadatos: mismos bytes cada vez)."""
    datos = np.round(np.clip(muestras, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(datos)


def generar(destino: Path = DIR_SFX, nombres: Optional[Sequence[str]] = None) -> List[Path]:
    """Genera los WAV (todos o los `nombres` dados) y el LEEME.txt en `destino`."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nombre in (nombres or list(SONIDOS)):
        ruta = destino / f"{nombre}.wav"
        escribir_wav(ruta, sintetizar(nombre))
        escritos.append(ruta)
    (destino / "LEEME.txt").write_text(LEEME, encoding="utf-8")
    return escritos


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Genera los efectos de sonido de Lune (WAV).")
    ap.add_argument("--destino", type=Path, default=DIR_SFX,
                    help="carpeta de salida (por defecto ui_web/assets/sfx/)")
    args = ap.parse_args(argv)
    for ruta in generar(args.destino):
        with wave.open(str(ruta), "rb") as w:
            seg = w.getnframes() / SR
        print(f"  {ruta.name:<20} {seg:5.2f} s")
    print(f"{len(SONIDOS)} sonidos en {args.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
