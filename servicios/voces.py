"""
voces.py — Catálogo y elección de la voz de Lune («elegir la voz», P08).

Todo lo que no es reproducir audio: qué voces hay, cuál toca ahora y cómo se
cambia. Sin Qt, y sin red en el hilo que llama (la lista online va en un hilo).

    VOCES_EDGE_ES      las 45 voces es-* de edge-tts 7.2.8, con país y género
    MULTILINGUES       las 12 *MultilingualNeural (hablan español con otro timbre)
    listar_edge()      lista viva de edge-tts con caché de 7 días en
                       cache/voces_edge.json (anclada a la raíz); la descarga va
                       en un hilo y, si falla, se usa la lista embebida
    validar_rate() · validar_volumen() · validar_pitch()
                       las mismas expresiones con las que edge-tts lanza ValueError
    resolver_voz()     ParamsVoz(motor, id, rate, pitch, volumen, tld)
    GTTS_TLD           acentos de gTTS (dominio de Google que sintetiza)
    KOKORO_VOCES       voces de Kokoro local (se cargan al pedirlas)
    herramienta_cambiar_voz(args, ctx)   handler de la herramienta `cambiar_voz`
    texto_voces() · comando_voz()        lo que imprime patata con /voces y /voz

PRIORIDAD (resolver_voz)
------------------------
Cada campo se resuelve por separado y un valor inválido cae al siguiente:

    personaje["voz"]  >  config voz.*  >  por defecto (es-MX-DaliaNeural, +0%, +0Hz, com.mx)

El motor sigue la misma idea con un matiz: un motor fijado en el personaje
manda; si no, manda el motor global de config (salvo «auto»); si config dice
«auto», se deduce de la voz del personaje (un id de Kokoro implica Kokoro).
Así el selector global de motor funciona aunque el personaje traiga su voz de
edge, y un personaje puede fijar su propio motor si lo necesita.

gTTS no tiene voces, solo acento: con motor gtts el id va vacío y cuenta `tld`.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional

from nucleo import rutas

# La lista de voces es una caché desechable: va a la carpeta local (desde el código,
# la raíz del repo, como siempre).
RAIZ = rutas.LOCAL
RUTA_CACHE = rutas.local("cache", "voces_edge.json")
TTL_CACHE_S = 7 * 24 * 3600          # la lista de Microsoft cambia muy de vez en cuando
REINTENTO_S = 600                    # tras un fallo de red, no volver a intentar en 10 min

VOZ_POR_DEFECTO = "es-MX-DaliaNeural"
RATE_POR_DEFECTO = "+0%"
PITCH_POR_DEFECTO = "+0Hz"
VOLUMEN_POR_DEFECTO = "+0%"
TLD_POR_DEFECTO = "com.mx"
MOTORES = ("auto", "edge", "gtts", "kokoro")

TEXTO_PRUEBA = "Hola, soy Lune. Así sonaré a partir de ahora."

# Las mismas expresiones que valida edge-tts (edge_tts/data_classes.py).
_RE_ID_EDGE = re.compile(r"^[a-z]{2,}-[A-Z]{2,}-.+Neural$")
_RE_PORCENTAJE = re.compile(r"^[+-]\d+%$")
_RE_HZ = re.compile(r"^[+-]\d+Hz$")

# Acentos de gTTS: el mismo español sintetizado desde otro dominio de Google.
GTTS_TLD: Dict[str, str] = {
    "com.mx": "México",
    "es": "España",
    "us": "Estados Unidos",
    "com": "Genérico (google.com)",
}

PAISES: Dict[str, str] = {
    "AR": "Argentina", "BO": "Bolivia", "CL": "Chile", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "DO": "República Dominicana",
    "EC": "Ecuador", "ES": "España", "GQ": "Guinea Ecuatorial",
    "GT": "Guatemala", "HN": "Honduras", "MX": "México", "NI": "Nicaragua",
    "PA": "Panamá", "PE": "Perú", "PR": "Puerto Rico", "PY": "Paraguay",
    "SV": "El Salvador", "US": "Estados Unidos", "UY": "Uruguay",
    "VE": "Venezuela", "AU": "Australia", "FR": "Francia", "DE": "Alemania",
    "IT": "Italia", "KR": "Corea del Sur", "BR": "Brasil", "GB": "Reino Unido",
    "CA": "Canadá", "IN": "India", "IE": "Irlanda",
}


class VozEdge(NamedTuple):
    """Una voz de edge-tts. `genero` es «F» o «M»; `pais` va en español."""
    id: str
    locale: str
    genero: str
    pais: str
    nombre: str
    multilingue: bool = False


def _nombre_corto(short_name: str) -> str:
    """«es-MX-DaliaNeural» → «Dalia»; «en-US-AvaMultilingualNeural» → «Ava»."""
    resto = short_name.split("-", 2)[-1]
    for sufijo in ("MultilingualNeural", "Neural"):
        if resto.endswith(sufijo):
            return resto[: -len(sufijo)] or resto
    return resto


def _pais(locale: str) -> str:
    region = (locale or "").split("-")[-1].upper()
    return PAISES.get(region, region or "?")


def _voz(short_name: str, locale: str, genero: str) -> VozEdge:
    return VozEdge(short_name, locale, genero, _pais(locale), _nombre_corto(short_name),
                   "Multilingual" in short_name)


# Lista real de edge-tts 7.2.8 (edge_tts.list_voices(), septiembre de 2026).
VOCES_EDGE_ES: tuple = tuple(_voz(*v) for v in (
    ("es-AR-ElenaNeural", "es-AR", "F"),
    ("es-AR-TomasNeural", "es-AR", "M"),
    ("es-BO-MarceloNeural", "es-BO", "M"),
    ("es-BO-SofiaNeural", "es-BO", "F"),
    ("es-CL-CatalinaNeural", "es-CL", "F"),
    ("es-CL-LorenzoNeural", "es-CL", "M"),
    ("es-CO-GonzaloNeural", "es-CO", "M"),
    ("es-CO-SalomeNeural", "es-CO", "F"),
    ("es-CR-JuanNeural", "es-CR", "M"),
    ("es-CR-MariaNeural", "es-CR", "F"),
    ("es-CU-BelkysNeural", "es-CU", "F"),
    ("es-CU-ManuelNeural", "es-CU", "M"),
    ("es-DO-EmilioNeural", "es-DO", "M"),
    ("es-DO-RamonaNeural", "es-DO", "F"),
    ("es-EC-AndreaNeural", "es-EC", "F"),
    ("es-EC-LuisNeural", "es-EC", "M"),
    ("es-ES-AlvaroNeural", "es-ES", "M"),
    ("es-ES-ElviraNeural", "es-ES", "F"),
    ("es-ES-XimenaNeural", "es-ES", "F"),
    ("es-GQ-JavierNeural", "es-GQ", "M"),
    ("es-GQ-TeresaNeural", "es-GQ", "F"),
    ("es-GT-AndresNeural", "es-GT", "M"),
    ("es-GT-MartaNeural", "es-GT", "F"),
    ("es-HN-CarlosNeural", "es-HN", "M"),
    ("es-HN-KarlaNeural", "es-HN", "F"),
    ("es-MX-DaliaNeural", "es-MX", "F"),
    ("es-MX-JorgeNeural", "es-MX", "M"),
    ("es-NI-FedericoNeural", "es-NI", "M"),
    ("es-NI-YolandaNeural", "es-NI", "F"),
    ("es-PA-MargaritaNeural", "es-PA", "F"),
    ("es-PA-RobertoNeural", "es-PA", "M"),
    ("es-PE-AlexNeural", "es-PE", "M"),
    ("es-PE-CamilaNeural", "es-PE", "F"),
    ("es-PR-KarinaNeural", "es-PR", "F"),
    ("es-PR-VictorNeural", "es-PR", "M"),
    ("es-PY-MarioNeural", "es-PY", "M"),
    ("es-PY-TaniaNeural", "es-PY", "F"),
    ("es-SV-LorenaNeural", "es-SV", "F"),
    ("es-SV-RodrigoNeural", "es-SV", "M"),
    ("es-US-AlonsoNeural", "es-US", "M"),
    ("es-US-PalomaNeural", "es-US", "F"),
    ("es-UY-MateoNeural", "es-UY", "M"),
    ("es-UY-ValentinaNeural", "es-UY", "F"),
    ("es-VE-PaolaNeural", "es-VE", "F"),
    ("es-VE-SebastianNeural", "es-VE", "M"),
))

MULTILINGUES: tuple = tuple(_voz(*v) for v in (
    ("en-AU-WilliamMultilingualNeural", "en-AU", "M"),
    ("en-US-AndrewMultilingualNeural", "en-US", "M"),
    ("en-US-AvaMultilingualNeural", "en-US", "F"),
    ("en-US-BrianMultilingualNeural", "en-US", "M"),
    ("en-US-EmmaMultilingualNeural", "en-US", "F"),
    ("fr-FR-VivienneMultilingualNeural", "fr-FR", "F"),
    ("fr-FR-RemyMultilingualNeural", "fr-FR", "M"),
    ("de-DE-SeraphinaMultilingualNeural", "de-DE", "F"),
    ("de-DE-FlorianMultilingualNeural", "de-DE", "M"),
    ("it-IT-GiuseppeMultilingualNeural", "it-IT", "M"),
    ("ko-KR-HyunsuMultilingualNeural", "ko-KR", "M"),
    ("pt-BR-ThalitaMultilingualNeural", "pt-BR", "F"),
))

VOCES_EDGE: tuple = VOCES_EDGE_ES + MULTILINGUES


def __getattr__(nombre: str):
    """KOKORO_VOCES se calcula al pedirlo: importar lune_core cuesta ~0.2 s."""
    if nombre == "KOKORO_VOCES":
        from lune_core.voz import kokoro_backend
        return dict(kokoro_backend.VOCES)
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")


# ── Validación ────────────────────────────────────────────────────────────────

def validar_rate(valor: Any) -> bool:
    """Velocidad de edge-tts: «+10%», «-25%»… (edge lanza ValueError si no)."""
    return isinstance(valor, str) and bool(_RE_PORCENTAJE.match(valor))


def validar_volumen(valor: Any) -> bool:
    """Volumen relativo de edge-tts: mismo formato que la velocidad."""
    return isinstance(valor, str) and bool(_RE_PORCENTAJE.match(valor))


def validar_pitch(valor: Any) -> bool:
    """Tono de edge-tts: «+5Hz», «-20Hz»."""
    return isinstance(valor, str) and bool(_RE_HZ.match(valor))


def es_id_edge(valor: Any) -> bool:
    """¿Tiene forma de ShortName de edge-tts? (no dice si la voz existe)."""
    return isinstance(valor, str) and bool(_RE_ID_EDGE.match(valor))


def _numero(valor: Any, sufijo: str) -> Optional[int]:
    """«+10%», «-5Hz», 10 → entero. None si no es un número finito («inf», «nan», basura)."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        try:
            n = float(valor)
        except OverflowError:                    # un entero enorme
            return None
    else:
        s = str(valor).strip().replace(" ", "")
        if s.lower().endswith(sufijo.lower()):
            s = s[: -len(sufijo)]
        try:
            n = float(s)
        except (ValueError, OverflowError):
            return None
    # inf/nan: round() lanzaría OverflowError/ValueError (p. ej. «/voz velocidad inf»).
    if not math.isfinite(n):
        return None
    return int(round(n))


def _con_signo(n: int, sufijo: str) -> str:
    return f"{'+' if n >= 0 else '-'}{abs(n)}{sufijo}"


def normalizar_rate(valor: Any) -> Optional[str]:
    """10, «10», «10%», «+10%» → «+10%». Entre -90 % y +200 %. None si no se entiende."""
    n = _numero(valor, "%")
    return None if n is None else _con_signo(max(-90, min(200, n)), "%")


def normalizar_volumen(valor: Any) -> Optional[str]:
    """Como normalizar_rate, entre -100 % y +100 %."""
    n = _numero(valor, "%")
    return None if n is None else _con_signo(max(-100, min(100, n)), "%")


def normalizar_pitch(valor: Any) -> Optional[str]:
    """-5, «-5Hz» → «-5Hz». Entre -100 Hz y +100 Hz."""
    n = _numero(valor, "Hz")
    return None if n is None else _con_signo(max(-100, min(100, n)), "Hz")


def porcentaje(valor: str) -> int:
    """«+15%» → 15 (0 si no es válido). Para convertir la velocidad a Kokoro."""
    return int(valor[:-1]) if validar_rate(valor) else 0


# ── Lista de edge-tts (embebida + caché online) ───────────────────────────────

def voces_estaticas() -> List[dict]:
    """La lista embebida como dicts (id, locale, genero, pais, nombre, multilingue)."""
    return [v._asdict() for v in VOCES_EDGE]


def _filtrar(crudas: Iterable[dict]) -> List[dict]:
    """De la respuesta de edge_tts.list_voices() se quedan las es-* y las multilingües."""
    salida, vistos = [], set()
    for v in crudas or ():
        if not isinstance(v, dict):
            continue
        sn = str(v.get("ShortName") or "")
        if not es_id_edge(sn) or sn in vistos:
            continue
        if not (sn.startswith("es-") or "MultilingualNeural" in sn):
            continue
        locale = str(v.get("Locale") or "-".join(sn.split("-")[:2]))
        genero = "F" if str(v.get("Gender", "")).lower().startswith("f") else "M"
        salida.append(_voz(sn, locale, genero)._asdict())
        vistos.add(sn)
    return salida


def _leer_cache(ruta: Path):
    """(ts, voces) de la caché, o (None, None) si no hay o está rota."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        voces = datos.get("voces")
        ts = float(datos.get("ts"))
        if isinstance(voces, list) and voces and all(isinstance(v, dict) and es_id_edge(v.get("id"))
                                                     for v in voces):
            return ts, voces
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None, None


def _escribir_cache(ruta: Path, voces: List[dict], ts: float) -> None:
    """Escritura atómica (tmp + os.replace): nunca queda un JSON a medias."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"version": 1, "ts": ts, "voces": voces}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, ruta)


def _descargar(cargar: Optional[Callable] = None) -> list:
    """Pide la lista a Microsoft (o a `cargar`, que puede ser síncrona o async)."""
    import asyncio
    if cargar is None:
        import edge_tts                     # ~1 s de import: solo aquí, en el hilo
        return asyncio.run(edge_tts.list_voices())
    r = cargar()
    if asyncio.iscoroutine(r):
        r = asyncio.run(r)
    return r


def actualizar_edge(cache: Optional[Path] = None, cargar: Optional[Callable] = None,
                    reloj: Callable[[], float] = time.time) -> List[dict]:
    """Descarga, filtra y guarda la lista. Síncrona; lanza si falla (sin red…)."""
    cache = Path(cache) if cache else RUTA_CACHE
    voces = _filtrar(_descargar(cargar))
    if not voces:
        raise RuntimeError("edge-tts devolvió una lista sin voces en español")
    _escribir_cache(cache, voces, reloj())
    return voces


_hilo: Optional[threading.Thread] = None
_hilo_lock = threading.Lock()
_ultimo_fallo: Optional[float] = None


def listar_edge(cache: Optional[Path] = None, ttl: float = TTL_CACHE_S,
                cargar: Optional[Callable] = None, reloj: Callable[[], float] = time.time,
                esperar: bool = False,
                al_actualizar: Optional[Callable[[List[dict]], None]] = None) -> List[dict]:
    """
    Voces de edge-tts (español + multilingües) como lista de dicts.

    Nunca bloquea en la red salvo con `esperar=True`: si la caché tiene menos de
    `ttl` segundos se devuelve tal cual; si no, se devuelve la caché vieja (o la
    lista embebida) y se lanza la descarga en un hilo, que al terminar guarda la
    caché y llama a `al_actualizar(voces)` desde ESE hilo (marshalear a Qt).
    """
    global _hilo
    cache = Path(cache) if cache else RUTA_CACHE
    ts, voces = _leer_cache(cache)
    ahora = reloj()
    if voces and ts is not None and 0 <= ahora - ts < ttl:
        return voces
    base = voces or voces_estaticas()
    if _ultimo_fallo is not None and 0 <= ahora - _ultimo_fallo < REINTENTO_S:
        return base

    def _trabajo():
        global _ultimo_fallo
        try:
            nuevas = actualizar_edge(cache, cargar, reloj)
        except Exception:
            _ultimo_fallo = reloj()
            return None
        _ultimo_fallo = None
        if al_actualizar is not None:
            try:
                al_actualizar(nuevas)
            except Exception:
                pass
        return nuevas

    if esperar:
        return _trabajo() or base
    with _hilo_lock:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_trabajo, name="voces-edge", daemon=True)
            _hilo.start()
    return base


def esperar_actualizacion(timeout: float = 30.0) -> bool:
    """Espera a que termine la descarga en curso (patata, tests). True si no queda ninguna."""
    h = _hilo
    if h is not None:
        h.join(timeout)
        return not h.is_alive()
    return True


def ids_edge(cache: Optional[Path] = None) -> frozenset:
    """Ids conocidos: la lista embebida más lo que haya en la caché (aunque caducada)."""
    _ts, voces = _leer_cache(Path(cache) if cache else RUTA_CACHE)
    ids = {v.id for v in VOCES_EDGE}
    ids.update(v.get("id") for v in (voces or ()) if isinstance(v, dict))
    return frozenset(i for i in ids if i)


def es_voz_edge_conocida(voz: str, cache: Optional[Path] = None) -> bool:
    return voz in ids_edge(cache)


def info_voz(voz: str, cache: Optional[Path] = None) -> Optional[dict]:
    """Dict de la voz (id, pais, genero, nombre…) o None si no está en la lista."""
    _ts, voces = _leer_cache(Path(cache) if cache else RUTA_CACHE)
    for v in list(voces or ()) + voces_estaticas():
        if isinstance(v, dict) and v.get("id") == voz:
            return v
    return None


def _plano(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower()


def buscar_edge(filtro: str = "", voces: Optional[List[dict]] = None) -> List[dict]:
    """Filtra por id, país, nombre o género («mujer»/«hombre», «F»/«M»), sin acentos."""
    voces = voces_estaticas() if voces is None else voces
    f = _plano(filtro).strip()
    if not f:
        return list(voces)
    genero = {"mujer": "F", "femenina": "F", "f": "F", "hombre": "M", "masculina": "M", "m": "M"}.get(f)
    if genero:
        return [v for v in voces if v.get("genero") == genero]
    if f in ("multi", "multilingue", "multilingues"):
        return [v for v in voces if v.get("multilingue")]
    return [v for v in voces
            if f in _plano(" ".join(str(v.get(k, "")) for k in ("id", "pais", "nombre", "locale")))]


# ── Parámetros de voz ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParamsVoz:
    """Todo lo que necesita el motor para decir algo con la voz elegida."""
    motor: str = "auto"                 # auto · edge · gtts · kokoro
    id: str = VOZ_POR_DEFECTO           # ShortName de edge o voz de Kokoro; "" con gtts
    rate: str = RATE_POR_DEFECTO
    pitch: str = PITCH_POR_DEFECTO
    volumen: str = VOLUMEN_POR_DEFECTO
    tld: str = TLD_POR_DEFECTO

    def a_dict(self) -> dict:
        return asdict(self)


def _cfg(config: Any, clave: str, defecto: Any = None) -> Any:
    """Lee voz.<clave> de un Config de Lune, de un dict {'voz': {...}} o de nada."""
    if config is None:
        return defecto
    try:
        if isinstance(config, dict):
            sec = config.get("voz", {})
            return sec.get(clave, defecto) if isinstance(sec, dict) else defecto
        return config.get("voz", clave, defecto)
    except Exception:
        return defecto


def _voz_personaje(personaje: Any) -> dict:
    try:
        from nucleo.personajes import voz_de
    except Exception:                       # sin datos.json importable: sin voz propia
        return {}
    return voz_de(personaje)


def _es_id_kokoro(valor: Any) -> bool:
    if not isinstance(valor, str) or not valor:
        return False
    try:
        from lune_core.voz import kokoro_backend
    except Exception:
        return False
    return valor in kokoro_backend.VOCES


def _motor_de_id(voz: Any) -> Optional[str]:
    if es_id_edge(voz):
        return "edge"
    if _es_id_kokoro(voz):
        return "kokoro"
    return None


def _primero(candidatos: Iterable[Any], normalizar: Callable[[Any], Optional[str]]) -> Optional[str]:
    for c in candidatos:
        v = normalizar(c)
        if v:
            return v
    return None


def resolver_voz(config: Any = None, personaje: Any = None, *, motor: Optional[str] = None) -> ParamsVoz:
    """
    Parámetros efectivos de la voz: personaje["voz"] > config voz.* > por defecto.
    `motor` fuerza el motor (p. ej. «edge» para saber qué voz de edge usar como
    respaldo cuando Kokoro falla). Nunca lanza: lo inválido se ignora.
    """
    pv = _voz_personaje(personaje)
    m_cfg = str(_cfg(config, "motor_salida", "auto") or "auto").strip().lower()
    m_pers = str(pv.get("motor") or "").strip().lower()
    if motor:
        m = str(motor).strip().lower()
    elif m_pers in MOTORES and m_pers != "auto":
        m = m_pers
    elif m_cfg in MOTORES and m_cfg != "auto":
        m = m_cfg
    else:
        m = _motor_de_id(pv.get("id")) or "auto"
    if m not in MOTORES:
        m = "auto"

    if m == "kokoro":
        try:
            from lune_core.voz import kokoro_backend
            defecto_k = kokoro_backend.VOZ_POR_DEFECTO
        except Exception:
            defecto_k = "ef_dora"
        voz = _primero((pv.get("id"), _cfg(config, "kokoro_voz"), defecto_k),
                       lambda v: v if _es_id_kokoro(v) else None) or defecto_k
    elif m == "gtts":
        voz = ""
    else:
        voz = _primero((pv.get("id"), _cfg(config, "edge_voz"), VOZ_POR_DEFECTO),
                       lambda v: v.strip() if isinstance(v, str) and es_id_edge(v.strip()) else None)

    rate = _primero((pv.get("rate"), _cfg(config, "edge_rate")), normalizar_rate) or RATE_POR_DEFECTO
    pitch = _primero((pv.get("pitch"), _cfg(config, "edge_pitch")), normalizar_pitch) or PITCH_POR_DEFECTO
    volumen = _primero((pv.get("volumen"), _cfg(config, "edge_volumen")),
                       normalizar_volumen) or VOLUMEN_POR_DEFECTO
    tld = _primero((pv.get("tld"), _cfg(config, "gtts_tld")),
                   lambda v: v.strip().lower() if isinstance(v, str) and v.strip().lower() in GTTS_TLD
                   else None) or TLD_POR_DEFECTO
    if m != "gtts" and not voz:
        voz = VOZ_POR_DEFECTO
    return ParamsVoz(m, voz, rate, pitch, volumen, tld)


def voz_activa(config: Any = None) -> ParamsVoz:
    """resolver_voz con el personaje activo de datos.json."""
    try:
        from nucleo import personajes
        p = personajes.get_activo()
    except Exception:
        p = None
    return resolver_voz(config, p)


def params_desde(valor: Any, base: Optional[ParamsVoz] = None) -> ParamsVoz:
    """
    ParamsVoz a partir de lo que mande la interfaz: otro ParamsVoz, un dict o un
    JSON ({motor, id, rate, pitch, volumen, tld}; rate/pitch también como número).
    Lo que falte o no valga se toma de `base`. Para el botón «Probar».
    """
    base = base or ParamsVoz()
    if isinstance(valor, ParamsVoz):
        return valor
    if isinstance(valor, str):
        try:
            valor = json.loads(valor) if valor.strip() else {}
        except ValueError:
            valor = {}
    if not isinstance(valor, dict):
        return base
    # También con las claves planas de config (motor_salida, edge_voz, edge_rate…).
    for plana, corta in (("motor_salida", "motor"), ("edge_rate", "rate"), ("edge_pitch", "pitch"),
                         ("edge_volumen", "volumen"), ("gtts_tld", "tld")):
        if corta not in valor and plana in valor:
            valor = {**valor, corta: valor[plana]}
    m = str(valor.get("motor") or base.motor).strip().lower()
    m = m if m in MOTORES else base.motor
    voz = valor.get("id", valor.get("voz"))
    if voz is None:
        voz = valor.get("kokoro_voz") if m == "kokoro" else valor.get("edge_voz")
    if m == "gtts":
        voz = ""
    elif m == "kokoro":
        voz = voz if _es_id_kokoro(voz) else (base.id if _es_id_kokoro(base.id) else "ef_dora")
    else:
        voz = voz.strip() if isinstance(voz, str) and es_id_edge(voz.strip()) else (
            base.id if es_id_edge(base.id) else VOZ_POR_DEFECTO)
    tld = str(valor.get("tld") or "").strip().lower()
    return replace(
        base, motor=m, id=voz,
        rate=normalizar_rate(valor.get("rate")) or base.rate,
        pitch=normalizar_pitch(valor.get("pitch")) or base.pitch,
        volumen=normalizar_volumen(valor.get("volumen")) or base.volumen,
        tld=tld if tld in GTTS_TLD else base.tld,
    )


# ── Kokoro y catálogo para la interfaz ────────────────────────────────────────

def kokoro_estado(config: Any = None) -> dict:
    """{disponible, voces, mensaje}: para pintar Kokoro en gris si no está instalado."""
    carpeta = _cfg(config, "kokoro_carpeta", None)
    try:
        from lune_core.voz import kokoro_backend as kb
        disp = kb.disponible(carpeta)
        instaladas = kb.voces_instaladas(carpeta) if disp else []
        voces = {k: v for k, v in kb.VOCES.items() if not instaladas or k in instaladas}
        return {"disponible": disp, "voces": voces,
                "mensaje": "" if disp else kb.mensaje_instalacion(carpeta)}
    except Exception as e:
        return {"disponible": False, "voces": {}, "mensaje": f"Kokoro no disponible: {e}"}


def catalogo(config: Any = None, personaje: Any = None, voice: Any = None) -> dict:
    """Todo lo que necesita el selector de voz (VozCard, /voces) en un dict JSON-able.
    Con `voice` (VoiceEngine) añade `motor_activo`, el motor que suena de verdad."""
    if personaje is None:
        try:
            from nucleo import personajes
            personaje = personajes.get_activo()
        except Exception:
            personaje = None
    voces = listar_edge()
    return {
        "edge": [v for v in voces if not v.get("multilingue")],
        "multilingues": [v for v in voces if v.get("multilingue")],
        "gtts_tld": dict(GTTS_TLD),
        "kokoro": kokoro_estado(config),
        "motores": list(MOTORES),
        "actual": resolver_voz(config, personaje).a_dict(),
        "personaje": (personaje or {}).get("nombre", "") if isinstance(personaje, dict) else "",
        "personaje_voz": _voz_personaje(personaje),
        "defecto": ParamsVoz().a_dict(),
        "motor_activo": str(getattr(voice, "engine_name", "")) if voice is not None else "",
    }


# ── Cambiar la voz del personaje activo ───────────────────────────────────────

def _de_ctx(ctx: Any, clave: str) -> Any:
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx.get(clave)
    return getattr(ctx, clave, None)


def _id_canonico(texto: Any, config: Any = None) -> Optional[str]:
    """El id exacto de la lista (sin distinguir mayúsculas), o None."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    t = texto.strip()
    por_minusculas = {i.lower(): i for i in ids_edge()}
    if t.lower() in por_minusculas:
        return por_minusculas[t.lower()]
    k = kokoro_estado(config)
    if k["disponible"] and t in k["voces"]:
        return t
    return None


def guardar_voz_personaje(cambios: dict, nombre: Optional[str] = None) -> dict:
    """Mezcla `cambios` en personaje["voz"] (del activo si no se dice) y guarda. Devuelve la voz final."""
    from nucleo import personajes
    nombre = nombre or personajes.activo_nombre()
    actual = personajes.voz_de(personajes.get(nombre))
    nueva = {**actual, **{k: v for k, v in (cambios or {}).items() if v is not None}}
    for k, v in (cambios or {}).items():
        if v is None:
            nueva.pop(k, None)
    if not personajes.set_voz(nombre, nueva):
        raise ValueError(f"No encuentro el personaje «{nombre}» para guardarle la voz.")
    return nueva


def _refrescar(voice: Any) -> None:
    """Que el VoiceEngine olvide su caché de 2 s y use ya la voz nueva."""
    fn = getattr(voice, "invalidar_params", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def cambiar_voz(voz: str, config: Any = None, voice: Any = None) -> str:
    """Valida `voz` contra la lista y la guarda en el personaje activo. Lanza ValueError si no vale."""
    canon = _id_canonico(voz, config)
    if canon is None:
        raise ValueError(f"No conozco la voz «{str(voz)[:60]}». Usa un id como {VOZ_POR_DEFECTO} "
                         f"(lista con /voces).")
    motor = "edge" if es_id_edge(canon) else "kokoro"
    guardar_voz_personaje({"motor": motor, "id": canon})
    _refrescar(voice)
    info = info_voz(canon)
    detalle = f" ({info['nombre']}, {info['pais']})" if info else ""
    return f"Listo: ahora hablo con la voz {canon}{detalle}."


def herramienta_cambiar_voz(args: dict, ctx: Any = None) -> str:
    """
    Handler de la herramienta del modelo `cambiar_voz` ({voz: ShortName}).
    Solo acepta ids de la lista (edge-tts embebida + caché; Kokoro si está
    instalado) y guarda la voz en el personaje activo. Un id que no está lanza
    ValueError: el Ejecutor lo cuenta como fallo y no se toca nada.
    """
    voz = (args or {}).get("voz") if isinstance(args, dict) else None
    return cambiar_voz(voz, _de_ctx(ctx, "config"), _de_ctx(ctx, "voice"))


# ── Patata: /voces y /voz ─────────────────────────────────────────────────────

def texto_voces(filtro: str = "", actual: str = "", voces: Optional[List[dict]] = None) -> str:
    """Lista para la terminal, agrupada por país. `actual` se marca con «*»."""
    lista = buscar_edge(filtro, voces if voces is not None else listar_edge())
    if not lista:
        return f"No hay voces que coincidan con «{filtro}». Prueba /voces mexico, /voces mujer o /voces multi."
    grupos: Dict[str, List[str]] = {}
    for v in lista:
        clave = "Multilingües" if v.get("multilingue") else v.get("pais", "?")
        marca = "*" if v.get("id") == actual else ""
        grupos.setdefault(clave, []).append(f"{marca}{v.get('id')} ({v.get('genero')})")
    ancho = max(len(g) for g in grupos)
    lineas = [f"Voces de edge-tts ({len(lista)}). Elige con /voz <id>; prueba con /voz prueba."]
    for g in sorted(grupos, key=lambda x: (x == "Multilingües", _plano(x))):
        lineas.append(f"  {g.ljust(ancho)}  " + "  ".join(grupos[g]))
    return "\n".join(lineas)


def _estado_voz(config: Any, voice: Any) -> str:
    p = voz_activa(config)
    encendida = bool(getattr(voice, "_enabled", False)) if voice is not None else False
    motor = getattr(voice, "engine_name", "?") if voice is not None else p.motor
    quien = p.id or f"acento {GTTS_TLD.get(p.tld, p.tld)}"
    return (f"Voz {'activada' if encendida else 'desactivada'} · motor {motor} · {quien} · "
            f"velocidad {p.rate} · tono {p.pitch}")


def comando_voz(argumento: str, config: Any = None, voice: Any = None) -> str:
    """
    /voz                      estado
    /voz on | off             activar o callar la voz
    /voz prueba [texto]       probar la voz actual (suena aunque esté apagada)
    /voz motor <m>            auto · edge · gtts · kokoro (para el personaje activo)
    /voz velocidad <n>        -90…+200 (%) · /voz tono <n>  -100…+100 (Hz) (lo de fuera se recorta)
    /voz <id>                 elegir una voz de /voces para el personaje activo
    Devuelve el texto a imprimir; no imprime nada.
    """
    arg = (argumento or "").strip()
    partes = arg.split(None, 1)
    orden = partes[0].lower() if partes else ""
    resto = partes[1].strip() if len(partes) > 1 else ""
    try:
        if not orden:
            return _estado_voz(config, voice)
        if orden in ("on", "off"):
            if voice is None:
                return "No hay motor de voz en esta sesión."
            voice._enabled = orden == "on"
            if orden == "off":
                getattr(voice, "cancelar", lambda: None)()
            return "Voz activada." if orden == "on" else "Voz desactivada."
        if orden in ("prueba", "probar"):
            if voice is None:
                return "No hay motor de voz en esta sesión."
            ok = voice.probar_voz(None, resto or None)
            return "Probando la voz…" if ok else "No pude probar la voz (sin motor o sin salida de audio)."
        if orden == "motor":
            m = resto.lower()
            if m not in MOTORES:
                return f"Motor desconocido. Usa uno de: {', '.join(MOTORES)}."
            if m == "kokoro":
                k = kokoro_estado(config)
                if not k["disponible"]:
                    return k["mensaje"]
            guardar_voz_personaje({"motor": None if m == "auto" else m})
            nombre = voice.reiniciar_motor() if voice is not None else m
            return f"Motor de voz: {nombre}."
        if orden in ("velocidad", "rate", "tono", "pitch"):
            es_tono = orden in ("tono", "pitch")
            valor = normalizar_pitch(resto) if es_tono else normalizar_rate(resto)
            if valor is None:
                return "Pon un número, p. ej. /voz velocidad -10 o /voz tono +5."
            guardar_voz_personaje({"pitch" if es_tono else "rate": valor})
            _refrescar(voice)
            return f"{'Tono' if es_tono else 'Velocidad'}: {valor}."
        return cambiar_voz(arg, config, voice)
    except ValueError as e:
        return str(e)
    except Exception as e:                  # datos.json bloqueado, etc.: que patata no muera
        return f"No pude cambiar la voz: {e}"
