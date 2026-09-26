"""
nucleo/alarmas.py — Alarmas y temporizadores de Lune (sin Qt).

QUÉ HAY
-------
- `Alarma`, `Temporizador`, `Disparo` y `Perdida`: los datos.
- `Almacen`: `alarmas.json` en RAIZ, compartido por la app, patata y las
  herramientas del modelo. Escritura atómica (temporal + os.replace) bajo un
  lock por archivo (dentro del proceso) y un mutex con nombre (entre procesos),
  como nucleo/config.py. Recarga por firma (inode, mtime, tamaño). Un JSON roto
  se aparta como `alarmas.json.corrupto-AAAAMMDD-HHMMSS` y se sigue vacío.
- `Programador`: decide qué suena. El dueño del mutex `Local\\Lune_CD_Alarmas`
  lo llama cada segundo (ui/alarmas_qt.py, servicios/alarmas_patata.py).
- `resumen()`, los handlers de las cuatro herramientas del catálogo
  (`temporizador`, `alarma`, `cancelar_alarma`, `listar_alarmas`) y
  `registrar_herramientas(tools)`.
- `parsear_hora`, `parsear_dias`, `texto_dias`, `parsear_duracion`.

EL ARCHIVO
----------
    {"version": 1,
     "alarmas": [{id, activa, hora, minuto, dias, una_vez, texto, ultimo_minuto, fecha}],
     "temporizadores": [{id, activo, duracion_s, objetivo, restante_s, texto, una_vez, pospuesta}],
     "sonando": [{origen, texto, tipo, t, programado}],   # reclamadas y aún sin apagar
     "visto_hasta": epoch}                                # último minuto visto por el dueño

- `dias` es una máscara (bit0 = lunes … bit6 = domingo); 0 = todos los días,
  como Mate-Engine. `una_vez` desactiva la alarma al sonar. `fecha`
  (AAAA-MM-DD, opcional) la limita a ese día («mañana a las 9»).
- `ultimo_minuto` («AAAA-MM-DDTHH:MM», hora local) es la marca del reclamo:
  una ocurrencia con esa clave ya sonó (o se dio por perdida).
- Temporizadores con objetivo absoluto (epoch): sobreviven a reinicios y a la
  suspensión. `activo` = cuenta atrás en marcha (entonces `objetivo` > 0); en
  pausa, `restante_s` guarda lo que falta. `una_vez` (los del chat, el
  «temporizador rápido» y los de posponer) se borra al sonar; `pospuesta`
  suena como tipo «pospuesta».
- Ids cortos (`a1`, `t3`) para que el modelo y `/borrar_alarma` los citen.

RECLAMO ATÓMICO (una sola vez aunque haya dos procesos)
-------------------------------------------------------
Dentro del lock + mutex: releer el archivo, marcar `ultimo_minuto` (o vaciar el
objetivo del temporizador), apuntar en `sonando`, os.replace y SOLO ENTONCES
devolver el Disparo. Si otro proceso lo reclamó antes, al releer ya está
marcado y no se devuelve nada. El mutex del dueño es la primera red; esto, la
segunda.

RECUPERACIÓN (al arrancar el dueño o tras un hueco de más de 90 s)
------------------------------------------------------------------
- Alarmas: la última ocurrencia de cada una entre `visto_hasta` (o el tic
  anterior) y ahora. Con un retraso ≤ `recuperar_min` suena como «texto (hace N
  min)»; si es mayor, es una `Perdida` (solo se avisa).
- Temporizadores vencidos: igual (el retraso sale del objetivo).
- `recuperar_sonando()`: lo que quedó en `sonando` (la app se cerró sonando, o
  hubo un cambio de interfaz) se vuelve a disparar si tiene ≤ `recuperar_min`.
- Al reactivar `alarmas.activo`, `marcar_visto(ahora)`: no se recupera nada.
- Reloj de pared (hora local) para las alarmas y epoch para los temporizadores:
  suspender, cambiar la hora o el horario de verano no duplican ni pierden nada
  (la clave del minuto manda).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple, Union

from nucleo.config import RAIZ, _MutexProcesos, _lock_de

_log = logging.getLogger("lune.alarmas")

DIAS = "lmxjvsd"
NOMBRES_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
ABREV_DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
TODOS_LOS_DIAS = 0b1111111
LABORABLES = 0b0011111
FIN_DE_SEMANA = 0b1100000

RUTA = RAIZ / "alarmas.json"
VERSION = 1
MUTEX_ARCHIVO = "Local\\Lune_CD_alarmas_json"   # escritura de alarmas.json
MUTEX_DUENO = "Local\\Lune_CD_Alarmas"          # quién programa (servicios/mutex_win.MutexNombrado)
MUTEX_APP = "Local\\Lune_CD_Alarmas_app"        # la app está abierta: patata le cede las alarmas

TIPOS = ("alarma", "temporizador", "pospuesta", "prueba")
HUECO_S = 90.0                 # un tic tras más de esto = hubo suspensión o cambio de hora
RECUPERAR_MIN = 10
MAX_ALARMAS = 50
MAX_TEMPORIZADORES = 30
MAX_TEXTO = 60
MAX_DURACION_S = 99 * 3600 + 59 * 60 + 59
MAX_SONANDO = 20
SONANDO_CADUCA_S = 24 * 3600   # lo que lleve un día en `sonando` se tira al escribir

_REINTENTOS_LECTURA = 3
_PAUSA_LECTURA_S = 0.02
_REINTENTOS_REEMPLAZO = 20
_PAUSA_REEMPLAZO_S = 0.025
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁦-⁩]")
_ID = re.compile(r"[\w-]{1,40}")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
EPOCH_MAX = 4102444800.0       # 2100-01-01: más allá, un epoch de alarmas.json es basura (fromtimestamp revienta)


# ── Datos ────────────────────────────────────────────────────────────────────────

@dataclass
class Alarma:
    id: str
    hora: int
    minuto: int
    dias: int = 0                 # máscara bit0 = lunes; 0 = todos los días
    una_vez: bool = False
    texto: str = ""
    activa: bool = True
    ultimo_minuto: str = ""       # «AAAA-MM-DDTHH:MM» de la última ocurrencia reclamada
    fecha: str = ""               # «AAAA-MM-DD»: solo ese día (opcional)

    @property
    def hhmm(self) -> str:
        return f"{self.hora:02d}:{self.minuto:02d}"


@dataclass
class Temporizador:
    id: str
    duracion_s: int
    texto: str = ""
    objetivo: float = 0.0         # epoch en que suena (0 = parado)
    restante_s: int = 0           # lo que falta si está en pausa
    activo: bool = True           # cuenta atrás en marcha
    una_vez: bool = False         # se borra al sonar
    pospuesta: bool = False       # lo creó «posponer»

    @property
    def corriendo(self) -> bool:
        return bool(self.activo and self.objetivo > 0)

    def falta(self, epoch: float) -> int:
        """Segundos que faltan (redondeando hacia arriba)."""
        if self.corriendo:
            return max(0, int(math.ceil(self.objetivo - epoch)))
        return max(0, int(self.restante_s or self.duracion_s))


@dataclass(frozen=True)
class Disparo:
    """Algo que tiene que sonar. `texto` es el de la alarma (sin el «(hace N min)»:
    eso lo añade `texto_visible`). `t` es el epoch del momento programado."""
    origen: str                   # id de la alarma o temporizador · «prueba»
    texto: str
    tipo: str                     # alarma | temporizador | pospuesta | prueba
    atraso_s: float = 0.0
    programado: str = ""          # «HH:MM»
    t: float = 0.0


@dataclass(frozen=True)
class Perdida:
    """Una ocurrencia que pasó con Lune cerrada (o el PC dormido) hace más de
    `recuperar_min`: no suena, solo se avisa."""
    origen: str
    texto: str
    cuando: datetime
    tipo: str = "alarma"

    @property
    def mensaje(self) -> str:
        return texto_perdida(self)


def texto_por_defecto(tipo: str) -> str:
    return {"temporizador": "Temporizador", "pospuesta": "Alarma pospuesta",
            "prueba": "Prueba de alarma"}.get(tipo, "Alarma")


def texto_visible(d: Disparo) -> str:
    """El texto que se enseña: el de la alarma (o uno por defecto) y, si sonó
    tarde, «(hace N min)»."""
    base = d.texto or texto_por_defecto(d.tipo)
    n = int((d.atraso_s or 0) // 60)
    return f"{base} (hace {n} min)" if n >= 1 else base


def _cuando_texto(cuando: datetime, ahora: Optional[datetime] = None) -> str:
    ahora = ahora or datetime.now()
    hhmm = cuando.strftime("%H:%M")
    dias = (ahora.date() - cuando.date()).days
    if dias <= 0:
        return f"de las {hhmm}"
    if dias == 1:
        return f"de ayer a las {hhmm}"
    return f"del {NOMBRES_DIAS[cuando.weekday()]} {cuando.day} a las {hhmm}"


def texto_perdida(p: Perdida, ahora: Optional[datetime] = None) -> str:
    """«Se pasó la alarma de las 07:30 «gimnasio» mientras Lune no estaba»."""
    etiqueta = f" «{p.texto}»" if p.texto else ""
    if p.tipo in ("temporizador", "pospuesta"):
        return (f"Se acabó el temporizador{etiqueta} {_cuando_texto(p.cuando, ahora)} "
                "mientras Lune no estaba")
    return f"Se pasó la alarma {_cuando_texto(p.cuando, ahora)}{etiqueta} mientras Lune no estaba"


# ── Texto: horas, días y duraciones ─────────────────────────────────────────────

def limpiar_texto(texto: Any, maximo: int = MAX_TEXTO) -> str:
    """Sin caracteres de control, espacios colapsados y como mucho `maximo`."""
    t = _CONTROL.sub(" ", str(texto or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:maximo].rstrip()


_RE_HORA = re.compile(
    r"^\s*(\d{1,2})(?:\s*[:.h]\s*(\d{2}))?\s*(?:h|hs|hrs)?\s*"
    r"(a\.?\s*m\.?|p\.?\s*m\.?|am|pm)?\s*$", re.IGNORECASE)


def parsear_hora(txt: Any) -> Tuple[int, int]:
    """«7», «7:30», «07.30», «19h», «7pm», «7:30 a.m.» → (h, m). ValueError si no vale."""
    s = str(txt or "").strip().lower()
    m = _RE_HORA.match(s)
    if not m and re.fullmatch(r"\d{3,4}", s):          # «730», «1945»
        m = _RE_HORA.match(f"{s[:-2]}:{s[-2:]}")
    if not m:
        raise ValueError(f"hora no válida: {txt!r} (usa HH:MM)")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    sufijo = (m.group(3) or "").replace(".", "").replace(" ", "")
    if sufijo:
        if not 1 <= h <= 12:
            raise ValueError(f"hora no válida: {txt!r}")
        if sufijo == "pm" and h != 12:
            h += 12
        elif sufijo == "am" and h == 12:
            h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValueError(f"hora no válida: {txt!r}")
    return h, mi


_DIA_PALABRA = {
    "lunes": 0, "lun": 0, "martes": 1, "mar": 1, "miercoles": 2, "miércoles": 2, "mie": 2, "mié": 2,
    "jueves": 3, "jue": 3, "viernes": 4, "vie": 4, "sabado": 5, "sábado": 5, "sab": 5, "sáb": 5,
    "domingo": 6, "dom": 6,
}
_DIAS_GRUPO = {
    "todos": TODOS_LOS_DIAS, "todo": TODOS_LOS_DIAS, "diario": TODOS_LOS_DIAS, "diaria": TODOS_LOS_DIAS,
    "todos los dias": TODOS_LOS_DIAS, "todos los días": TODOS_LOS_DIAS, "cada dia": TODOS_LOS_DIAS,
    "cada día": TODOS_LOS_DIAS,
    "laborables": LABORABLES, "entre semana": LABORABLES, "l-v": LABORABLES, "lun-vie": LABORABLES,
    "finde": FIN_DE_SEMANA, "fin de semana": FIN_DE_SEMANA, "fines de semana": FIN_DE_SEMANA,
}


def parsear_dias(txt: Any) -> int:
    """«lmxjv» → máscara. También «todos», «laborables», «finde», «lunes,viernes»
    o un entero 0–127. «» → 0 (todos los días; `una_vez` va aparte).
    ValueError si no se entiende."""
    if isinstance(txt, bool):
        raise ValueError("días no válidos")
    if isinstance(txt, int):
        if 0 <= txt <= TODOS_LOS_DIAS:
            return txt
        raise ValueError(f"días no válidos: {txt!r}")
    s = re.sub(r"\s+", " ", str(txt or "").strip().lower())
    if not s:
        return 0
    if s.isdigit():
        return parsear_dias(int(s))
    if s in _DIAS_GRUPO:
        return _DIAS_GRUPO[s]
    compacto = s.replace(" ", "").replace(",", "")
    if re.fullmatch(f"[{DIAS}]+", compacto):
        mask = 0
        for c in compacto:
            mask |= 1 << DIAS.index(c)
        return mask
    mask = 0
    for parte in re.split(r"[,\s/]+|\sy\s", s):
        parte = parte.strip()
        if not parte or parte == "y":
            continue
        if parte not in _DIA_PALABRA:
            raise ValueError(f"días no válidos: {txt!r} (usa letras lmxjvsd)")
        mask |= 1 << _DIA_PALABRA[parte]
    return mask


def letras_dias(mask: int) -> str:
    """Máscara → «lmxjv» (0 → «»)."""
    return "".join(c for i, c in enumerate(DIAS) if int(mask or 0) & (1 << i))


def _unir(partes: List[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def texto_dias(mask: int) -> str:
    """Máscara → «todos los días», «de lunes a viernes», «sábados y domingos», «lunes y jueves»."""
    mask = int(mask or 0) & TODOS_LOS_DIAS
    if mask in (0, TODOS_LOS_DIAS):
        return "todos los días"
    if mask == LABORABLES:
        return "de lunes a viernes"
    if mask == FIN_DE_SEMANA:
        return "sábados y domingos"
    return _unir([NOMBRES_DIAS[i] for i in range(7) if mask & (1 << i)])


_RE_DUR_PARTES = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(h|hs|hrs|hora|horas|m|min|mins|minuto|minutos|s|seg|segs|segundo|segundos)\b")


def parsear_duracion(txt: Any) -> int:
    """«10m», «1h30», «90s», «1:30» (m:s), «1:00:00» (h:m:s), «10» (minutos),
    «1.5h», «2 horas y 10 minutos» → segundos. ValueError si no vale."""
    s = str(txt or "").strip().lower().replace(" y ", " ")
    if not s:
        raise ValueError("duración vacía")
    if re.fullmatch(r"\d+(?:[.,]\d+)?", s):
        seg = float(s.replace(",", ".")) * 60
    elif re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", s):
        partes = [int(p) for p in s.split(":")]
        if any(p >= 60 for p in partes[1:]):
            raise ValueError(f"duración no válida: {txt!r}")
        seg = partes[0] * 60 + partes[1] if len(partes) == 2 else partes[0] * 3600 + partes[1] * 60 + partes[2]
    else:
        m = re.fullmatch(r"(\d+)\s*h\s*(\d{1,2})", s)          # «1h30» = 1 h 30 min
        if m:
            seg = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        else:
            resto = _RE_DUR_PARTES.sub("", s)
            if resto.strip(" ,") or not _RE_DUR_PARTES.search(s):
                raise ValueError(f"duración no válida: {txt!r} (ej.: 10m, 1h30, 90s)")
            seg = 0.0
            for num, unidad in _RE_DUR_PARTES.findall(s):
                v = float(num.replace(",", "."))
                seg += v * (3600 if unidad.startswith("h") else 60 if unidad.startswith("m") else 1)
    seg = int(round(seg))
    if not 1 <= seg <= MAX_DURACION_S:
        raise ValueError(f"duración fuera de rango: {txt!r}")
    return seg


def formato_duracion(seg: Union[int, float]) -> str:
    """90 → «1 min 30 s»; 3600 → «1 h»; 5400 → «1 h 30 min»."""
    seg = max(0, int(round(seg)))
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    partes = []
    if h:
        partes.append(f"{h} h")
    if m:
        partes.append(f"{m} min")
    if s or not partes:
        partes.append(f"{s} s")
    return " ".join(partes)


def reloj_restante(seg: Union[int, float]) -> str:
    """272 → «4:32»; 3872 → «1:04:32»."""
    seg = max(0, int(math.ceil(seg)))
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── Ocurrencias ──────────────────────────────────────────────────────────────────

def clave_minuto(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def _minuto(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def _dia_vale(a: Alarma, d: date) -> bool:
    if a.fecha:
        return d.isoformat() == a.fecha
    return a.dias == 0 or bool(a.dias & (1 << d.weekday()))


def ocurrencia_anterior(a: Alarma, hasta: datetime) -> Optional[datetime]:
    """La última ocurrencia de `a` que cae en `hasta` o antes (hasta 8 días atrás)."""
    for atras in range(0, 8):
        d = (hasta - timedelta(days=atras)).date()
        if not _dia_vale(a, d):
            continue
        o = datetime(d.year, d.month, d.day, a.hora, a.minuto)
        if o <= hasta:
            return o
    return None


def ocurrencia_siguiente(a: Alarma, ahora: datetime) -> Optional[datetime]:
    """La próxima vez que sonará `a` (el minuto en curso cuenta si aún no sonó)."""
    if not a.activa:
        return None
    base = _minuto(ahora)
    for adelante in range(0, 8):
        d = (base + timedelta(days=adelante)).date()
        if not _dia_vale(a, d):
            continue
        o = datetime(d.year, d.month, d.day, a.hora, a.minuto)
        if o > base or (o == base and a.ultimo_minuto != clave_minuto(o)):
            return o
    if a.fecha:
        try:
            f = date.fromisoformat(a.fecha)
        except ValueError:
            return None
        o = datetime(f.year, f.month, f.day, a.hora, a.minuto)
        return o if o > base else None
    return None


# ── Conversión dict ↔ datos ──────────────────────────────────────────────────────

def _entero(v: Any, lo: int, hi: int, defecto: int) -> int:
    try:
        if isinstance(v, bool):
            return defecto
        n = int(v)
    except (TypeError, ValueError, OverflowError):      # OverflowError: int(float("inf"))
        return defecto
    return n if lo <= n <= hi else defecto


def _epoch(v: Any) -> float:
    """Un epoch de alarmas.json: finito, > 0 y antes de 2100; si no, 0."""
    try:
        e = float(v or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return e if math.isfinite(e) and 0 < e <= EPOCH_MAX else 0.0


def _alarma_de(d: Any) -> Optional[Alarma]:
    if not isinstance(d, Mapping):
        return None
    id_ = str(d.get("id") or "")
    if not _ID.fullmatch(id_):
        return None
    h = _entero(d.get("hora"), 0, 23, -1)
    m = _entero(d.get("minuto"), 0, 59, -1)
    if h < 0 or m < 0:
        return None
    fecha = str(d.get("fecha") or "")
    return Alarma(id=id_, hora=h, minuto=m, dias=_entero(d.get("dias"), 0, TODOS_LOS_DIAS, 0),
                  una_vez=bool(d.get("una_vez", False)), texto=limpiar_texto(d.get("texto")),
                  activa=bool(d.get("activa", True)), ultimo_minuto=str(d.get("ultimo_minuto") or "")[:16],
                  fecha=fecha if _FECHA.fullmatch(fecha) else "")


def _temporizador_de(d: Any) -> Optional[Temporizador]:
    if not isinstance(d, Mapping):
        return None
    id_ = str(d.get("id") or "")
    if not _ID.fullmatch(id_):
        return None
    dur = _entero(d.get("duracion_s"), 1, MAX_DURACION_S, 0)
    if not dur:
        return None
    objetivo = _epoch(d.get("objetivo"))
    activo = bool(d.get("activo", True)) and objetivo > 0
    return Temporizador(id=id_, duracion_s=dur, texto=limpiar_texto(d.get("texto")),
                        objetivo=objetivo if activo else 0.0,
                        restante_s=_entero(d.get("restante_s"), 0, MAX_DURACION_S, dur),
                        activo=activo, una_vez=bool(d.get("una_vez", False)),
                        pospuesta=bool(d.get("pospuesta", False)))


def _sonando_de(d: Any) -> Optional[dict]:
    if not isinstance(d, Mapping):
        return None
    tipo = str(d.get("tipo") or "alarma")
    if tipo not in TIPOS:
        return None
    t = _epoch(d.get("t"))
    if t <= 0:
        return None
    return {"origen": str(d.get("origen") or "")[:40], "texto": limpiar_texto(d.get("texto")),
            "tipo": tipo, "t": t, "programado": str(d.get("programado") or "")[:5]}


def _vacio() -> dict:
    return {"version": VERSION, "alarmas": [], "temporizadores": [], "sonando": [], "visto_hasta": 0.0}


def _lista(v: Any) -> list:
    """Solo una lista de verdad (un número, un texto o un objeto en su sitio no se recorren)."""
    return v if isinstance(v, list) else []


def _normalizar(crudo: Any) -> dict:
    datos = _vacio()
    if not isinstance(crudo, Mapping):
        return datos
    ids = set()
    for lista, conv in (("alarmas", _alarma_de), ("temporizadores", _temporizador_de)):
        for x in _lista(crudo.get(lista)):
            obj = conv(x)
            if obj is None or obj.id in ids:
                continue
            ids.add(obj.id)
            datos[lista].append(asdict(obj))
    for x in _lista(crudo.get("sonando")):
        s = _sonando_de(x)
        if s is not None:
            datos["sonando"].append(s)
    datos["visto_hasta"] = _epoch(crudo.get("visto_hasta"))
    return datos


def _sin_constantes(nombre: str):
    """json.loads: Infinity, -Infinity y NaN no son JSON (alarmas.json con ellos = corrupto)."""
    raise ValueError(f"constante no válida en JSON: {nombre}")


def _disparo_de_sonando(s: Mapping, epoch: float) -> Disparo:
    return Disparo(origen=s["origen"], texto=s["texto"], tipo=s["tipo"],
                   atraso_s=max(0.0, epoch - float(s["t"])), programado=s.get("programado", ""),
                   t=float(s["t"]))


def _sonando_dict(d: Disparo) -> dict:
    return {"origen": d.origen, "texto": d.texto, "tipo": d.tipo, "t": float(d.t),
            "programado": d.programado}


def _misma(s: Mapping, d: Disparo) -> bool:
    return s.get("origen") == d.origen and abs(float(s.get("t") or 0) - float(d.t)) < 0.5


def _nombre_mutex(base: str, ruta: Path) -> str:
    """El nombre fijo para alarmas.json de verdad; con un resumen de la ruta para
    otros archivos (tests): así no compiten con una Lune abierta."""
    try:
        if os.path.normcase(str(Path(ruta).resolve())) == os.path.normcase(str(RUTA.resolve())):
            return base
    except OSError:
        pass
    return base + "_" + hashlib.sha1(os.path.normcase(str(ruta)).encode("utf-8")).hexdigest()[:12]


def nombre_mutex_dueno(ruta: Union[str, Path] = RUTA) -> str:
    """`Local\\Lune_CD_Alarmas` para alarmas.json de verdad (otro nombre para otro archivo)."""
    return _nombre_mutex(MUTEX_DUENO, Path(ruta))


def nombre_mutex_app(ruta: Union[str, Path] = RUTA) -> str:
    """`Local\\Lune_CD_Alarmas_app`: lo tiene la app mientras sus alarmas están en marcha.
    La app es la dueña preferente: patata, si lo ve ocupado, le cede las alarmas."""
    return _nombre_mutex(MUTEX_APP, Path(ruta))


class _MutexArchivo(_MutexProcesos):
    """El mutex entre procesos de nucleo/config.py con el nombre de alarmas.json."""

    def __init__(self, ruta: Path):
        super().__init__(ruta)
        self.nombre = _nombre_mutex(MUTEX_ARCHIVO, ruta)


# ── Almacén ──────────────────────────────────────────────────────────────────────

class Almacen:
    """alarmas.json con lectura en caché, escritura atómica y reclamo bajo mutex.

    Seguro entre hilos y entre procesos. `leer()` y las listas usan la caché (se
    recarga sola si otro escribió el archivo); lo que modifica relee del disco
    dentro del lock (`_editar`).
    """

    def __init__(self, ruta: Union[str, Path] = RUTA, *, reloj: Callable[[], float] = time.time):
        self.ruta = Path(ruta)
        self._reloj = reloj
        self._lock = _lock_de(self.ruta)
        self._firma: Optional[tuple] = None
        self._datos = _vacio()
        self._cargado = False
        self._rev = 0                 # sube cuando cambia el contenido (salvo visto_hasta)
        self._rev_visto = 0
        self._huella = self._huella_de(self._datos)

    # ── Disco ──
    def _mutex(self):
        return _MutexArchivo(self.ruta)

    def _firma_disco(self) -> Optional[tuple]:
        try:
            st = os.stat(self.ruta)
        except OSError:
            return None
        return (st.st_ino, st.st_mtime_ns, st.st_size)

    def _leer_disco(self):
        try:
            with open(self.ruta, "rb") as f:
                st = os.fstat(f.fileno())
                crudo = f.read()
        except FileNotFoundError:
            return "falta", None, None
        except OSError as e:
            return "error", str(e), None
        firma = (st.st_ino, st.st_mtime_ns, st.st_size)
        try:
            data = json.loads(crudo.decode("utf-8-sig"), parse_constant=_sin_constantes)
        except (ValueError, RecursionError) as e:
            return "corrupto", str(e), firma
        if not isinstance(data, dict):
            return "corrupto", "no es un objeto JSON", firma
        return "ok", data, firma

    def _leer_con_reintento(self):
        r = self._leer_disco()
        for _ in range(_REINTENTOS_LECTURA - 1):
            if r[0] not in ("corrupto", "error"):
                break
            time.sleep(_PAUSA_LECTURA_S)
            r = self._leer_disco()
        return r

    def _apartar_corrupto(self, motivo: str) -> None:
        fecha = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = self.ruta.with_name(f"{self.ruta.name}.corrupto-{fecha}")
        n = 1
        while destino.exists():
            destino = self.ruta.with_name(f"{self.ruta.name}.corrupto-{fecha}-{n}")
            n += 1
        try:
            os.replace(self.ruta, destino)
        except OSError:
            try:
                shutil.copyfile(self.ruta, destino)
            except OSError as e:
                _log.error("alarmas.json está corrupto (%s) y no pude apartarlo (%s)", motivo, e)
                return
        _log.warning("alarmas.json estaba corrupto (%s): lo aparto como %s y sigo sin alarmas",
                     motivo, destino.name)

    def _leer_fresco(self) -> dict:
        """Lee del disco (dentro del lock). Corrupto → se aparta y se sigue vacío."""
        estado, valor, firma = self._leer_con_reintento()
        datos = None
        if estado == "ok":
            try:
                datos = _normalizar(valor)
            except Exception as e:                  # JSON válido con tipos imposibles: también corrupto
                estado, valor = "corrupto", f"{type(e).__name__}: {e}"
        if estado == "corrupto":
            self._apartar_corrupto(valor)
            datos, firma = _vacio(), None
        elif estado == "falta":
            datos, firma = _vacio(), None
        elif estado != "ok":
            _log.warning("alarmas: no pude leer %s (%s); sigo con lo que tenía", self.ruta.name, valor)
            return copy.deepcopy(self._datos)
        self._poner_cache(datos, firma)
        return copy.deepcopy(datos)

    def _escribir(self, datos: dict) -> bool:
        carpeta = self.ruta.parent
        tmp = None
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            texto = json.dumps(datos, indent=2, ensure_ascii=False)
            fd, tmp = tempfile.mkstemp(prefix=f".{self.ruta.name}.", suffix=".tmp", dir=str(carpeta))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
                f.flush()
                os.fsync(f.fileno())
            for intento in range(_REINTENTOS_REEMPLAZO):
                try:
                    os.replace(tmp, self.ruta)
                    break
                except PermissionError:
                    if intento == _REINTENTOS_REEMPLAZO - 1:
                        raise
                    time.sleep(_PAUSA_REEMPLAZO_S)
            tmp = None
        except Exception as e:
            _log.error("alarmas: error guardando %s: %s", self.ruta.name, e)
            return False
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self._poner_cache(datos, self._firma_disco())
        return True

    @staticmethod
    def _huella_de(datos: dict) -> str:
        sin_visto = {k: v for k, v in datos.items() if k != "visto_hasta"}
        return json.dumps(sin_visto, sort_keys=True, ensure_ascii=False)

    def _poner_cache(self, datos: dict, firma: Optional[tuple]) -> None:
        huella = self._huella_de(datos)
        if huella != self._huella:
            self._rev += 1
            self._huella = huella
        self._datos = copy.deepcopy(datos)
        self._firma = firma
        self._cargado = True

    def _refrescar(self) -> None:
        """Recarga la caché si el archivo cambió (o si aún no se leyó)."""
        with self._lock:
            firma = self._firma_disco()
            if self._cargado and firma == self._firma:
                return
            if firma is None:
                self._poner_cache(_vacio(), None)
                return
            self._leer_fresco()

    @contextmanager
    def _editar(self) -> Iterator[dict]:
        """Lee-modifica-escribe atómico entre hilos y procesos. Si el bloque lanza
        una excepción, no se escribe nada."""
        with self._lock, self._mutex():
            datos = self._leer_fresco()
            antes = json.dumps(datos, sort_keys=True)
            yield datos
            if json.dumps(datos, sort_keys=True) != antes:
                ahora = self._reloj()
                datos["sonando"] = [s for s in datos["sonando"]
                                    if ahora - float(s.get("t") or 0) < SONANDO_CADUCA_S][-MAX_SONANDO:]
                self._escribir(datos)

    # ── Lectura ──
    def leer(self) -> dict:
        """Copia del contenido (recargado si otro proceso lo cambió)."""
        with self._lock:
            self._refrescar()
            return copy.deepcopy(self._datos)

    def cambio(self) -> bool:
        """¿Cambió el contenido desde la última vez que se preguntó? Cuenta lo que
        escribió este proceso y lo que escribieron otros (no `visto_hasta`)."""
        with self._lock:
            self._refrescar()
            hay = self._rev != self._rev_visto
            self._rev_visto = self._rev
            return hay

    def alarmas(self) -> List[Alarma]:
        return [a for a in (_alarma_de(x) for x in self.leer()["alarmas"]) if a is not None]

    def temporizadores(self) -> List[Temporizador]:
        return [t for t in (_temporizador_de(x) for x in self.leer()["temporizadores"]) if t is not None]

    def obtener(self, id_: str) -> Union[Alarma, Temporizador, None]:
        for x in self.alarmas() + self.temporizadores():
            if x.id == id_:
                return x
        return None

    def visto_hasta(self) -> float:
        return float(self.leer().get("visto_hasta") or 0.0)

    def proxima(self, ahora: Optional[datetime] = None) -> Optional[Tuple[datetime, Union[Alarma, Temporizador]]]:
        """(cuándo, qué) de lo próximo que va a sonar, o None."""
        ahora = ahora or datetime.now()
        mejor: Optional[Tuple[datetime, Any]] = None
        for a in self.alarmas():
            o = ocurrencia_siguiente(a, ahora)
            if o is not None and (mejor is None or o < mejor[0]):
                mejor = (o, a)
        for t in self.temporizadores():
            if t.corriendo:
                try:
                    o = datetime.fromtimestamp(t.objetivo)
                except (OverflowError, OSError, ValueError):
                    continue
                if mejor is None or o < mejor[0]:
                    mejor = (o, t)
        return mejor

    # ── Escritura ──
    @staticmethod
    def _nuevo_id(datos: dict, prefijo: str) -> str:
        n = 0
        for lista in ("alarmas", "temporizadores"):
            for x in datos[lista]:
                m = re.fullmatch(prefijo + r"(\d+)", str(x.get("id") or ""))
                if m:
                    n = max(n, int(m.group(1)))
        return f"{prefijo}{n + 1}"

    def crear_alarma(self, hora: int, minuto: int, dias: int = 0, una_vez: bool = False,
                     texto: str = "", *, fecha: str = "", activa: bool = True) -> Alarma:
        """Crea y guarda una alarma. ValueError si los datos no valen o hay demasiadas."""
        hora, minuto = int(hora), int(minuto)
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            raise ValueError("hora no válida")
        dias = parsear_dias(dias)
        fecha = str(fecha or "")
        if fecha and not _FECHA.fullmatch(fecha):
            raise ValueError("fecha no válida (AAAA-MM-DD)")
        if fecha:
            date.fromisoformat(fecha)
        with self._editar() as datos:
            if len(datos["alarmas"]) >= MAX_ALARMAS:
                raise ValueError(f"ya hay {MAX_ALARMAS} alarmas: borra alguna antes")
            a = Alarma(id=self._nuevo_id(datos, "a"), hora=hora, minuto=minuto, dias=dias,
                       una_vez=bool(una_vez or fecha), texto=limpiar_texto(texto),
                       activa=bool(activa), fecha=fecha)
            datos["alarmas"].append(asdict(a))
        return a

    def crear_temporizador(self, segundos: int, texto: str = "", iniciar: bool = True, *,
                           una_vez: bool = False, pospuesta: bool = False) -> Temporizador:
        """Crea (y arranca si `iniciar`) un temporizador de `segundos`."""
        seg = int(segundos)
        if not 1 <= seg <= MAX_DURACION_S:
            raise ValueError("duración fuera de rango")
        with self._editar() as datos:
            if len(datos["temporizadores"]) >= MAX_TEMPORIZADORES:
                raise ValueError(f"ya hay {MAX_TEMPORIZADORES} temporizadores: borra alguno antes")
            t = Temporizador(id=self._nuevo_id(datos, "t"), duracion_s=seg, texto=limpiar_texto(texto),
                             objetivo=(self._reloj() + seg) if iniciar else 0.0, restante_s=seg,
                             activo=bool(iniciar), una_vez=bool(una_vez), pospuesta=bool(pospuesta))
            datos["temporizadores"].append(asdict(t))
        return t

    _CAMPOS_ALARMA = ("hora", "minuto", "dias", "una_vez", "texto", "activa", "fecha")
    _CAMPOS_TEMP = ("texto", "duracion_s")

    def actualizar(self, id_: str, **campos) -> bool:
        """Cambia campos de una alarma (hora, minuto, dias, una_vez, texto, activa,
        fecha) o de un temporizador (texto, duracion_s). False si no existe.
        ValueError si un valor no vale."""
        with self._editar() as datos:
            for x in datos["alarmas"]:
                if x["id"] != id_:
                    continue
                nuevo = dict(x)
                for k, v in campos.items():
                    if k not in self._CAMPOS_ALARMA:
                        raise ValueError(f"campo desconocido: {k}")
                    nuevo[k] = parsear_dias(v) if k == "dias" else v
                if "texto" in campos:
                    nuevo["texto"] = limpiar_texto(campos["texto"])
                if "fecha" not in campos and nuevo.get("fecha") and (
                        ("dias" in campos and nuevo["dias"]) or ("una_vez" in campos and not nuevo["una_vez"])):
                    # «Mañana a las 7» pasada a días o a repetida: la fecha ya no vale (con ella
                    # oculta no volvería a sonar nunca).
                    nuevo["fecha"] = ""
                if nuevo.get("fecha") and not _FECHA.fullmatch(str(nuevo["fecha"])):
                    raise ValueError("fecha no válida (AAAA-MM-DD)")
                a = _alarma_de(nuevo)
                if a is None:
                    raise ValueError("alarma no válida")
                x.clear()
                x.update(asdict(a))
                return True
            for x in datos["temporizadores"]:
                if x["id"] != id_:
                    continue
                for k in campos:
                    if k not in self._CAMPOS_TEMP:
                        raise ValueError(f"campo desconocido: {k}")
                if "texto" in campos:
                    x["texto"] = limpiar_texto(campos["texto"])
                if "duracion_s" in campos:
                    dur = int(campos["duracion_s"])
                    if not 1 <= dur <= MAX_DURACION_S:
                        raise ValueError("duración fuera de rango")
                    x["duracion_s"] = dur
                    if not x.get("activo"):
                        x["restante_s"] = dur
                return True
        return False

    def borrar(self, id_: str) -> bool:
        with self._editar() as datos:
            for lista in ("alarmas", "temporizadores"):
                antes = len(datos[lista])
                datos[lista] = [x for x in datos[lista] if x.get("id") != id_]
                if len(datos[lista]) != antes:
                    return True
        return False

    def temporizador(self, id_: str, accion: str) -> bool:
        """iniciar · parar (guarda lo que falta) · reiniciar (lo para y vuelve a la
        duración completa). False si no existe o la acción no vale."""
        if accion not in ("iniciar", "parar", "reiniciar"):
            return False
        with self._editar() as datos:
            for x in datos["temporizadores"]:
                if x["id"] != id_:
                    continue
                ahora = self._reloj()
                corriendo = bool(x.get("activo")) and float(x.get("objetivo") or 0) > 0
                if accion == "iniciar":
                    if not corriendo:
                        falta = int(x.get("restante_s") or 0) or int(x["duracion_s"])
                        x["objetivo"] = ahora + falta
                        x["activo"] = True
                elif accion == "parar":
                    if corriendo:
                        x["restante_s"] = max(1, int(math.ceil(float(x["objetivo"]) - ahora)))
                    x["objetivo"] = 0.0
                    x["activo"] = False
                else:
                    x["objetivo"] = 0.0
                    x["activo"] = False
                    x["restante_s"] = int(x["duracion_s"])
                return True
        return False

    def anotar_sonando(self, d: Disparo) -> None:
        if d.tipo == "prueba":
            return
        with self._editar() as datos:
            if not any(_misma(s, d) for s in datos["sonando"]):
                datos["sonando"].append(_sonando_dict(d))

    def quitar_sonando(self, d: Disparo) -> None:
        if d.tipo == "prueba":
            return
        with self._editar() as datos:
            datos["sonando"] = [s for s in datos["sonando"] if not _misma(s, d)]

    def sonando(self) -> List[Disparo]:
        ahora = self._reloj()
        return [_disparo_de_sonando(s, ahora) for s in self.leer()["sonando"]]

    def marcar_visto(self, epoch: Optional[float] = None) -> None:
        """`visto_hasta` = ahora: lo anterior ya no se recupera (al reactivar las alarmas)."""
        with self._editar() as datos:
            datos["visto_hasta"] = float(self._reloj() if epoch is None else epoch)


# ── Programador ─────────────────────────────────────────────────────────────────

class Programador:
    """Qué suena en cada tic. Solo lo llama el dueño del mutex de alarmas.

        disparos, perdidas = prog.tick(datetime.now(), time.time())

    Cada tic mira la caché (barato); solo si algo toca, o una vez por minuto
    para `visto_hasta`, entra en el reclamo atómico del almacén.
    """

    def __init__(self, almacen: Almacen, *, recuperar_min: Union[int, float] = RECUPERAR_MIN):
        self.almacen = almacen
        self.recuperar_min = recuperar_min
        self._ultimo_ahora: Optional[datetime] = None
        self._ultimo_epoch: Optional[float] = None
        self._minuto_visto = ""

    @property
    def recuperar_s(self) -> float:
        try:
            return max(0.0, float(self.recuperar_min) * 60.0)
        except (TypeError, ValueError):
            return RECUPERAR_MIN * 60.0

    def reiniciar(self) -> None:
        """Olvida el último tic: el siguiente vuelve a mirar `visto_hasta` (al
        recuperar el mutex o al reactivar las alarmas)."""
        self._ultimo_ahora = self._ultimo_epoch = None
        self._minuto_visto = ""

    def _ventana(self, ahora: datetime, epoch: float, datos: dict) -> Optional[datetime]:
        """Desde cuándo hay que recuperar, o None si no hubo hueco."""
        if self._ultimo_ahora is None:
            vh = float(datos.get("visto_hasta") or 0.0)
            if vh <= 0:
                return None
            try:
                desde = datetime.fromtimestamp(vh)
            except (OverflowError, OSError, ValueError):
                return None
            return desde if desde < ahora else None
        hueco = (epoch - (self._ultimo_epoch or epoch) > HUECO_S
                 or (ahora - self._ultimo_ahora).total_seconds() > HUECO_S)
        return self._ultimo_ahora if hueco else None

    def _decidir(self, datos: dict, ahora: datetime, epoch: float, desde: Optional[datetime],
                 aplicar: bool, tope: Optional[Tuple[datetime, float]] = None
                 ) -> Tuple[List[Disparo], List[Perdida], bool]:
        """Recorre `datos`. Con `aplicar`, marca lo que reclama. → (disparos, perdidas, hay_algo).

        `tope` = (hora de pared del tic anterior, segundos de verdad —epoch— desde él). Una
        ocurrencia posterior a ese tic no puede llevar más retraso que esos segundos aunque
        el reloj de pared haya saltado (cambio al horario de verano: la alarma de las 02:30
        suena al saltar a las 03:00; antes se daba por perdida con Lune abierta)."""
        disparos: List[Disparo] = []
        perdidas: List[Perdida] = []
        hay = False
        minuto = _minuto(ahora)
        desde_min = _minuto(desde) if desde is not None else None
        for x in datos["alarmas"]:
            a = _alarma_de(x)
            if a is None or not a.activa:
                continue
            o = ocurrencia_anterior(a, ahora)
            if o is None:
                continue
            clave = clave_minuto(o)
            if clave == a.ultimo_minuto:
                continue
            en_ventana = o == minuto or (desde_min is not None and o >= desde_min)
            if not en_ventana:
                if a.fecha and a.una_vez and o < minuto:     # «mañana a las 9» que ya pasó
                    hay = True
                    if aplicar:
                        x["activa"] = False
                        x["ultimo_minuto"] = clave
                continue
            hay = True
            if not aplicar:
                continue
            x["ultimo_minuto"] = clave
            if a.una_vez:
                x["activa"] = False
            atraso = max(0.0, (ahora - o).total_seconds())
            if tope is not None and o > tope[0]:
                atraso = min(atraso, max(0.0, tope[1]))
            if o == minuto or atraso <= self.recuperar_s:
                disparos.append(Disparo(a.id, a.texto, "alarma", atraso if o != minuto else 0.0,
                                        a.hhmm, float(epoch) - atraso))
            else:
                perdidas.append(Perdida(a.id, a.texto, o, "alarma"))
        quedan = []
        for x in datos["temporizadores"]:
            t = _temporizador_de(x)
            if t is None or not t.corriendo or epoch < t.objetivo:
                quedan.append(x)
                continue
            hay = True
            if not aplicar:
                quedan.append(x)
                continue
            tipo = "pospuesta" if t.pospuesta else "temporizador"
            atraso = max(0.0, epoch - t.objetivo)
            try:
                prog = datetime.fromtimestamp(t.objetivo)
            except (OverflowError, OSError, ValueError):
                prog = ahora
            if atraso <= max(self.recuperar_s, 60.0):
                disparos.append(Disparo(t.id, t.texto, tipo, atraso if atraso >= 60 else 0.0,
                                        prog.strftime("%H:%M"), float(t.objetivo)))
            else:
                perdidas.append(Perdida(t.id, t.texto, prog, tipo))
            if t.una_vez:
                continue                                    # se borra al sonar
            x["activo"] = False
            x["objetivo"] = 0.0
            x["restante_s"] = int(t.duracion_s)
            quedan.append(x)
        if aplicar:
            datos["temporizadores"] = quedan
            for d in disparos:
                if not any(_misma(s, d) for s in datos["sonando"]):
                    datos["sonando"].append(_sonando_dict(d))
        return disparos, perdidas, hay

    def tick(self, ahora: datetime, epoch: float) -> Tuple[List[Disparo], List[Perdida]]:
        """Lo que tiene que sonar ahora (ya reclamado en el archivo) y lo que se perdió."""
        datos = self.almacen.leer()
        desde = self._ventana(ahora, epoch, datos)
        tope = None
        if self._ultimo_ahora is not None and self._ultimo_epoch is not None:
            tope = (self._ultimo_ahora, float(epoch) - float(self._ultimo_epoch))
        self._ultimo_ahora, self._ultimo_epoch = ahora, epoch
        _, _, hay = self._decidir(datos, ahora, epoch, desde, aplicar=False)
        clave = clave_minuto(ahora)
        if not hay and clave == self._minuto_visto:
            return [], []
        with self.almacen._editar() as fresco:
            disparos, perdidas, _ = self._decidir(fresco, ahora, epoch, desde, aplicar=True, tope=tope)
            if clave != self._minuto_visto:
                fresco["visto_hasta"] = float(epoch)
        self._minuto_visto = clave
        return disparos, perdidas

    def recuperar_sonando(self, epoch: float) -> List[Disparo]:
        """Lo que quedó sonando (app cerrada o cambio de interfaz) con ≤ recuperar_min
        vuelve a sonar; lo más viejo se quita del archivo."""
        if not self.almacen.leer()["sonando"]:
            return []
        res: List[Disparo] = []
        with self.almacen._editar() as datos:
            quedan = []
            for s in datos["sonando"]:
                if epoch - float(s["t"]) <= max(self.recuperar_s, 60.0):
                    quedan.append(s)
                    res.append(_disparo_de_sonando(s, epoch))
                else:
                    _log.info("alarmas: descarto «%s» (lleva demasiado en sonando)", s.get("texto"))
            datos["sonando"] = quedan
        return res


# ── Resumen ──────────────────────────────────────────────────────────────────────

def texto_alarma(a: Alarma, ahora: Optional[datetime] = None) -> str:
    """«07:30 · de lunes a viernes · gimnasio»."""
    if a.fecha:
        try:
            f = date.fromisoformat(a.fecha)
            hoy = (ahora or datetime.now()).date()
            dia = "hoy" if f == hoy else "mañana" if f == hoy + timedelta(days=1) else f.strftime("%d/%m")
        except ValueError:
            dia = a.fecha
        cuando = f"una vez ({dia})"
    elif a.una_vez:
        cuando = "una vez" if a.dias in (0, TODOS_LOS_DIAS) else f"una vez ({texto_dias(a.dias)})"
    else:
        cuando = texto_dias(a.dias)
    partes = [a.hhmm, cuando]
    if a.texto:
        partes.append(a.texto)
    return " · ".join(partes)


def _cuando_proxima(o: datetime, ahora: datetime) -> str:
    dias = (o.date() - ahora.date()).days
    if dias == 0:
        return f"hoy a las {o:%H:%M}"
    if dias == 1:
        return f"mañana a las {o:%H:%M}"
    return f"el {NOMBRES_DIAS[o.weekday()]} a las {o:%H:%M}"


def resumen(almacen: Almacen, ahora: Optional[datetime] = None, epoch: Optional[float] = None) -> str:
    """Lista legible con ids (para /alarmas y la herramienta listar_alarmas)."""
    ahora = ahora or datetime.now()
    epoch = time.time() if epoch is None else epoch
    alarmas = almacen.alarmas()
    temps = almacen.temporizadores()
    if not alarmas and not temps:
        return "No hay alarmas ni temporizadores."
    lineas: List[str] = []
    if alarmas:
        lineas.append("Alarmas:")
        for a in alarmas:
            extra = "" if a.activa else " (apagada)"
            lineas.append(f"  {a.id} · {texto_alarma(a, ahora)}{extra}")
    if temps:
        lineas.append("Temporizadores:")
        for t in temps:
            estado = (f"quedan {reloj_restante(t.falta(epoch))}" if t.corriendo
                      else f"en pausa, faltan {reloj_restante(t.falta(epoch))}"
                      if t.restante_s and t.restante_s != t.duracion_s else "parado")
            nombre = f" · {t.texto}" if t.texto else ""
            pos = " (pospuesta)" if t.pospuesta else ""
            lineas.append(f"  {t.id} · {formato_duracion(t.duracion_s)}{nombre}{pos} · {estado}")
    prox = almacen.proxima(ahora)
    if prox is not None:
        o, obj = prox
        nombre = f" ({obj.texto})" if getattr(obj, "texto", "") else ""
        lineas.append(f"Próxima: {_cuando_proxima(o, ahora)}{nombre}")
    return "\n".join(lineas)


# ── Herramientas del modelo ──────────────────────────────────────────────────────

_ALMACEN_DEFECTO: Optional[Almacen] = None
_LOCK_DEFECTO = threading.Lock()


def almacen_por_defecto() -> Almacen:
    global _ALMACEN_DEFECTO
    with _LOCK_DEFECTO:
        if _ALMACEN_DEFECTO is None:
            _ALMACEN_DEFECTO = Almacen(RUTA)
        return _ALMACEN_DEFECTO


def _de_ctx(ctx: Any, clave: str) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(clave)
    return getattr(ctx, clave, None) if ctx is not None else None


def _almacen(ctx: Any) -> Almacen:
    a = _de_ctx(ctx, "almacen")
    return a if a is not None else almacen_por_defecto()


def _aviso_apagadas(ctx: Any) -> str:
    cfg = _de_ctx(ctx, "config")
    try:
        if cfg is not None and not cfg.get("alarmas", "activo", True):
            return " Ojo: las alarmas están apagadas en los ajustes; no sonará hasta que las enciendas."
    except Exception:
        pass
    return ""


def _avisar_cambio(ctx: Any) -> None:
    f = _de_ctx(ctx, "al_cambiar")
    if callable(f):
        try:
            f()
        except Exception:
            _log.debug("alarmas: al_cambiar falló", exc_info=True)


def herramienta_temporizador(args: Any, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """`temporizador` {segundos: 1–90000, texto}. Se borra solo al sonar."""
    args = args or {}
    try:
        seg = int(args.get("segundos"))
    except (TypeError, ValueError):
        return False, "Dime cuántos segundos."
    texto = limpiar_texto(args.get("texto"))
    try:
        t = _almacen(ctx).crear_temporizador(seg, texto, iniciar=True, una_vez=True)
    except ValueError as e:
        return False, f"No pude poner el temporizador: {e}"
    _avisar_cambio(ctx)
    fin = datetime.fromtimestamp(t.objetivo)
    etiqueta = f" «{texto}»" if texto else ""
    return (f"Temporizador de {formato_duracion(seg)}{etiqueta} en marcha ({t.id}): "
            f"sonará a las {fin:%H:%M}.{_aviso_apagadas(ctx)}")


def herramienta_alarma(args: Any, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """`alarma` {hora: "HH:MM", dias: "lmxjvsd" | "" (= una vez), texto}. Admite
    además `fecha` («AAAA-MM-DD»: solo ese día) si el catálogo la deja pasar."""
    args = args or {}
    try:
        h, m = parsear_hora(args.get("hora"))
        dias_txt = str(args.get("dias") or "").strip().lower()
        dias = parsear_dias(dias_txt)
    except ValueError as e:
        return False, f"No pude poner la alarma: {e}"
    fecha = str(args.get("fecha") or "").strip()
    if fecha and not _FECHA.fullmatch(fecha):
        fecha = ""
    texto = limpiar_texto(args.get("texto"))
    try:
        a = _almacen(ctx).crear_alarma(h, m, dias, una_vez=not dias_txt, texto=texto, fecha=fecha)
    except ValueError as e:
        return False, f"No pude poner la alarma: {e}"
    _avisar_cambio(ctx)
    ahora = datetime.now()
    o = ocurrencia_siguiente(a, ahora)
    etiqueta = f" «{texto}»" if texto else ""
    if a.una_vez:
        cuando = _cuando_proxima(o, ahora) if o is not None else f"a las {a.hhmm}"
        return f"Alarma{etiqueta} para {cuando}, una sola vez ({a.id}).{_aviso_apagadas(ctx)}"
    return (f"Alarma{etiqueta} a las {a.hhmm} {texto_dias(a.dias)} ({a.id})."
            f"{_aviso_apagadas(ctx)}")


def herramienta_cancelar(args: Any, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """`cancelar_alarma` {id}: quita una alarma o un temporizador."""
    id_ = str((args or {}).get("id") or "").strip()
    if not _ID.fullmatch(id_):
        return False, "Dime el id de la alarma (por ejemplo a1 o t2)."
    alm = _almacen(ctx)
    obj = alm.obtener(id_)
    if obj is None or not alm.borrar(id_):
        return False, f"No encuentro la alarma o temporizador «{id_}». Mira la lista con listar_alarmas."
    _avisar_cambio(ctx)
    que = "el temporizador" if isinstance(obj, Temporizador) else "la alarma"
    nombre = f" «{obj.texto}»" if obj.texto else ""
    return f"Quitado {que}{nombre} ({id_})."


def herramienta_listar(args: Any = None, ctx: Any = None) -> str:
    """`listar_alarmas` {}: la lista con ids."""
    texto = resumen(_almacen(ctx))
    return texto + _aviso_apagadas(ctx)


HERRAMIENTAS = {
    "temporizador": herramienta_temporizador,
    "alarma": herramienta_alarma,
    "cancelar_alarma": herramienta_cancelar,
    "listar_alarmas": herramienta_listar,
}


def handlers(almacen: Optional[Almacen] = None, config: Any = None,
             al_cambiar: Optional[Callable[[], None]] = None) -> Dict[str, Callable[[dict, Any], Any]]:
    """Las cuatro herramientas atadas a un almacén (y a la config para avisar si
    las alarmas están apagadas). `al_cambiar()` se llama tras crear o borrar."""
    def atar(fn):
        def handler(args: dict, ctx: Any = None):
            c: Dict[str, Any] = dict(ctx) if isinstance(ctx, Mapping) else {}
            c["almacen"] = almacen if almacen is not None else almacen_por_defecto()
            if config is not None:
                c["config"] = config
            if al_cambiar is not None:
                c["al_cambiar"] = al_cambiar
            return fn(args, c)
        handler.__name__ = fn.__name__
        handler.__doc__ = fn.__doc__
        return handler
    return {nombre: atar(fn) for nombre, fn in HERRAMIENTAS.items()}


def registrar_herramientas(tools: Any, almacen: Optional[Almacen] = None, config: Any = None) -> None:
    """Enchufa las cuatro en un ToolManager (patata y tests)."""
    if tools is None:
        return
    for nombre, fn in handlers(almacen, config).items():
        tools.registrar_handler(nombre, fn)


__all__ = (
    "DIAS", "RUTA", "Alarma", "Temporizador", "Disparo", "Perdida", "Almacen", "Programador",
    "parsear_dias", "texto_dias", "letras_dias", "parsear_hora", "parsear_duracion",
    "formato_duracion", "reloj_restante", "texto_visible", "texto_perdida", "texto_alarma",
    "resumen", "herramienta_temporizador", "herramienta_alarma", "herramienta_cancelar",
    "herramienta_listar", "handlers", "registrar_herramientas", "nombre_mutex_dueno", "nombre_mutex_app",
    "ocurrencia_siguiente", "ocurrencia_anterior", "clave_minuto",
)
