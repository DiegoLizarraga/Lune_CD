"""
nucleo/packs_sonido.py — Packs de sonidos de reacción de la asistente (los «voice
packs» de Mate-Engine, versión Lune).

QUÉ ES UN PACK
--------------
Una carpeta dentro de `sonidos/` (anclada a la raíz del repo, nunca al cwd) con
un `pack.json`:

    {
      "nombre": "Gatita",                    # lo que ve el usuario (≤ 60)
      "autor": "Diego",                      # opcional (≤ 60)
      "mapeo": "ciclo",                      # ciclo | reemplazar (ver abajo)
      "volumen": 0.8,                        # 0–1, multiplica al de efectos
      "eventos": {"caricia": ["miau_1.ogg", "miau_2.ogg"], "beber": ["glup.wav"]},
      "capas":   {"caricia": ["ronroneo.wav"]}
    }

`eventos` son los clips principales de cada evento (suena uno al azar). En los
eventos de REACCIÓN (`REACCIONES`: caricia, pudor, mareo…) ese clip es la «voz»
de la asistente: suena solo si no está sonando otra voz de reacción ni la voz TTS.
`capas` se superponen SIEMPRE al evento (un ronroneo bajo el maullido…). La
lista completa de eventos está en `EVENTOS` y en `sonidos/default/pack.json`.

Solo se aceptan archivos .ogg y .wav DENTRO de la carpeta del pack (rutas
relativas; se permiten subcarpetas con «/»). Se descartan con aviso: otras
extensiones, rutas absolutas, con unidad o con «:», «..», barras invertidas,
nombres de dispositivo de Windows (NUL, CON…), archivos que no existen o que
pasan de `TAM_MAX_ARCHIVO`, y lo que tras resolver enlaces quede fuera de la
carpeta. Un pack.json roto, de más de `TAM_MAX_JSON` o sin ningún archivo
válido deja el pack como no válido (`listar_packs()` no lo devuelve salvo que
se pida con `incluir_invalidos=True`, para que la interfaz enseñe el error).

MAPEO (el de MEVoicePack de Mate-Engine)
----------------------------------------
Los eventos que el pack NO trae siguen con los sonidos del pack por defecto. Si
los trae:
- `reemplazar`: se usan solo los del pack.
- `ciclo`: la lista se alarga al tamaño de la del pack por defecto repitiendo
  los del pack en orden: out[i] = nuevos[i % len(nuevos)], con
  len(out) = max(len(defecto), len(nuevos)).

EL PACK POR DEFECTO
-------------------
`sonidos/default/pack.json` no trae archivos propios: `"base":
"ui_web/assets/sfx"` hace que sus rutas se lean en la carpeta de los WAV que
genera `scripts/generar_sfx.py`. `base` solo puede valer lo que hay en
`BASES_PERMITIDAS`: un pack descargado no puede hacer que Lune lea ni publique
otra carpeta del disco.

USO
---
- Web (asistente VRM y animada): `pack_para_web(pack)` da el pack ya resuelto
  (mapeo aplicado, URLs del servidor local) para `luneSonidos.cargar(objeto)` de
  ui_web/lune_packs.js. ui_web/ se sirve en «/» y `sonidos/` en el prefijo que se
  publique con `ServidorEstatico.publicar_carpeta(PREFIJO_WEB, CARPETA_SONIDOS)`.
- Patata y la asistente de sprites: `archivo_al_azar(pack, evento)` y el
  mezclador (`servicios/mezclador.py`).
- Configuración: `avatar.pack_sonidos` (id = nombre de la carpeta) y
  `avatar.volumen_sfx`.

Sin Qt ni red. No importa zips (fuera de alcance de esta serie).
"""
from __future__ import annotations

import json
import logging
import random
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

log = logging.getLogger("lune.packs_sonido")

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_SONIDOS = RAIZ / "sonidos"
DIR_WEB = RAIZ / "ui_web"
DIR_SFX = DIR_WEB / "assets" / "sfx"

PACK_DEFECTO = "default"
ARCHIVO_PACK = "pack.json"
PREFIJO_WEB = "/sonidos/"

EXTENSIONES = frozenset({".ogg", ".wav"})
MAPEOS = ("ciclo", "reemplazar")
# Únicos valores de "base" (relativos a la raíz, con «/»). Solo la carpeta de
# efectos que genera scripts/generar_sfx.py.
BASES_PERMITIDAS: Dict[str, Path] = {"ui_web/assets/sfx": DIR_SFX}

TAM_MAX_JSON = 64 * 1024
TAM_MAX_ARCHIVO = 10 * 1024 * 1024
MAX_EVENTOS = 64
MAX_ARCHIVOS_EVENTO = 32
MAX_TEXTO = 60
MAX_DESCRIPCION = 300
MAX_RUTA = 200

# Eventos que conoce Lune (un pack puede traer otros: se guardan igual).
EVENTOS: Dict[str, str] = {
    "arrastre_inicio": "levantarla con el ratón (tono 0.9–1.1 al azar)",
    "arrastre_fin": "soltarla (tono 0.9–1.1 al azar)",
    "caricia": "caricia en la cabeza (voz de reacción)",
    "pudor": "tocarla donde no debe (voz de reacción)",
    "mareo": "zarandearla (voz de reacción)",
    "despertar": "se despierta (voz de reacción)",
    "dormir": "se queda dormida (voz de reacción)",
    "saludo": "sale al escritorio (voz de reacción)",
    "burbuja_abrir": "sale un globo de texto",
    "burbuja_cerrar": "se va el globo de texto",
    "tecleo": "letra a letra en los globos (un blip cada 2 letras)",
    "alarma": "alarmas y temporizadores",
    "comida_aparece": "aparece un plato",
    "comida_capa": "se añade una capa a la comida",
    "beber": "beber",
    "comer": "morder",
    "menu_abrir": "abrir un menú",
    "menu_cerrar": "cerrar un menú",
    "menu_boton": "pulsar un botón de menú",
    "menu_interruptor": "cambiar un interruptor",
}
# Eventos cuyo clip principal es la «voz» de la asistente: nunca dos a la vez ni
# encima de la voz TTS (las capas suenan igual).
REACCIONES = frozenset({"caricia", "pudor", "mareo", "despertar", "dormir", "saludo"})

_RE_EVENTO = re.compile(r"^[a-z0-9_]{1,40}$")
_RE_ID = re.compile(r'^[^/\\:*?"<>|\x00-\x1f]{1,64}$')
_RESERVADOS_WIN = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})

RutaPack = Union["PackSonido", str, Path]


# ── Modelo ────────────────────────────────────────────────────────────────────

@dataclass
class PackSonido:
    """Un pack ya validado. Las rutas de `eventos`/`capas` son absolutas y existen."""
    id: str
    carpeta: Path
    nombre: str
    autor: str = ""
    descripcion: str = ""
    mapeo: str = "ciclo"
    volumen: float = 1.0
    base: Optional[Path] = None           # dónde se leen sus archivos (None = carpeta)
    eventos: Dict[str, List[Path]] = field(default_factory=dict)
    capas: Dict[str, List[Path]] = field(default_factory=dict)
    errores: List[str] = field(default_factory=list)   # dejan el pack no válido
    avisos: List[str] = field(default_factory=list)    # cosas descartadas

    @property
    def valido(self) -> bool:
        return not self.errores

    @property
    def carpeta_archivos(self) -> Path:
        return self.base if self.base is not None else self.carpeta

    def a_dict(self) -> dict:
        """Resumen para la interfaz (lista de packs, errores y avisos)."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "autor": self.autor,
            "descripcion": self.descripcion,
            "mapeo": self.mapeo,
            "volumen": self.volumen,
            "eventos": {ev: len(l) for ev, l in self.eventos.items()},
            "capas": {ev: len(l) for ev, l in self.capas.items()},
            "valido": self.valido,
            "errores": list(self.errores),
            "avisos": list(self.avisos),
        }


# ── Utilidades ────────────────────────────────────────────────────────────────

def _anclar(carpeta: Optional[Union[str, Path]]) -> Path:
    """Carpeta de packs anclada a la raíz del repo (nunca al cwd)."""
    if carpeta is None:
        return CARPETA_SONIDOS
    c = Path(carpeta)
    return c if c.is_absolute() else RAIZ / c


def _texto(valor, maximo: int) -> str:
    """Texto de una línea sin caracteres de control ni de formato (bidi)."""
    if not isinstance(valor, str):
        return ""
    limpio = "".join(
        " " if ch in "\r\n\t" else ch
        for ch in valor
        if ch in "\r\n\t" or unicodedata.category(ch) not in ("Cc", "Cf"))
    limpio = " ".join(limpio.split())
    return limpio[:maximo].rstrip()


def _dentro(ruta: Path, carpeta: Path) -> bool:
    try:
        ruta.relative_to(carpeta)
        return True
    except ValueError:
        return False


def _ruta_segura(ref, base: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Valida una ruta de archivo de pack.json. Devuelve (ruta, None) o (None, motivo)."""
    if not isinstance(ref, str) or not ref.strip():
        return None, "entrada vacía o que no es texto"
    r = ref.strip()
    muestra = r[:60]
    if len(r) > MAX_RUTA:
        return None, f"ruta demasiado larga: {muestra}…"
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in r):
        return None, f"caracteres de control en {muestra!r}"
    if "\\" in r or ":" in r:
        return None, f"«\\» o «:» no permitidos: {muestra}"
    if r.startswith("/"):
        return None, f"ruta absoluta: {muestra}"
    partes = r.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return None, f"ruta con «..», «.» o «//»: {muestra}"
    for p in partes:
        if p.split(".")[0].upper().rstrip() in _RESERVADOS_WIN or p.endswith((" ", ".")):
            return None, f"nombre no válido en Windows: {muestra}"
    if Path(partes[-1]).suffix.lower() not in EXTENSIONES:
        return None, f"solo .ogg o .wav: {muestra}"
    try:
        carpeta = base.resolve()
        ruta = (carpeta / Path(*partes)).resolve()
    except (OSError, RuntimeError, ValueError):
        return None, f"no se pudo resolver {muestra}"
    if not _dentro(ruta, carpeta):
        return None, f"se sale de la carpeta del pack: {muestra}"
    try:
        if not ruta.is_file():
            return None, f"no existe: {muestra}"
        if ruta.stat().st_size > TAM_MAX_ARCHIVO:
            return None, f"pasa de {TAM_MAX_ARCHIVO // (1024 * 1024)} MB: {muestra}"
    except OSError:
        return None, f"no se puede leer: {muestra}"
    return ruta, None


def _tabla(crudo, base: Path, nombre_tabla: str, avisos: List[str]) -> Dict[str, List[Path]]:
    """Valida `eventos` o `capas`: {evento: [archivos]} (un texto suelto vale como lista)."""
    if crudo is None:
        return {}
    if not isinstance(crudo, dict):
        avisos.append(f"«{nombre_tabla}» no es un objeto: se ignora")
        return {}
    out: Dict[str, List[Path]] = {}
    for n, (evento, lista) in enumerate(crudo.items()):
        if n >= MAX_EVENTOS:
            avisos.append(f"«{nombre_tabla}»: más de {MAX_EVENTOS} eventos, se ignoran los demás")
            break
        if not isinstance(evento, str) or not _RE_EVENTO.match(evento):
            avisos.append(f"«{nombre_tabla}»: nombre de evento no válido {str(evento)[:40]!r}")
            continue
        if isinstance(lista, str):
            lista = [lista]
        if not isinstance(lista, list):
            avisos.append(f"«{nombre_tabla}.{evento}» no es una lista")
            continue
        if len(lista) > MAX_ARCHIVOS_EVENTO:
            avisos.append(f"«{nombre_tabla}.{evento}»: más de {MAX_ARCHIVOS_EVENTO} archivos, se ignoran los demás")
            lista = lista[:MAX_ARCHIVOS_EVENTO]
        rutas: List[Path] = []
        for ref in lista:
            ruta, motivo = _ruta_segura(ref, base)
            if ruta is None:
                avisos.append(f"«{nombre_tabla}.{evento}»: {motivo}")
            else:
                rutas.append(ruta)
        out[evento] = rutas
    return out


# ── Carga y listado ───────────────────────────────────────────────────────────

def cargar_pack(carpeta: Union[str, Path]) -> PackSonido:
    """Lee y valida el pack de `carpeta`. Nunca lanza: los problemas van a errores/avisos."""
    carpeta = _anclar(carpeta)
    pack = PackSonido(id=carpeta.name, carpeta=carpeta, nombre=carpeta.name)
    archivo = carpeta / ARCHIVO_PACK
    try:
        if not archivo.is_file():
            pack.errores.append(f"falta {ARCHIVO_PACK}")
            return pack
        if archivo.stat().st_size > TAM_MAX_JSON:
            pack.errores.append(f"{ARCHIVO_PACK} pasa de {TAM_MAX_JSON // 1024} KB")
            return pack
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        pack.errores.append(f"{ARCHIVO_PACK} no se puede leer: {str(e)[:120]}")
        return pack
    if not isinstance(datos, dict):
        pack.errores.append(f"{ARCHIVO_PACK} tiene que ser un objeto JSON")
        return pack

    pack.nombre = _texto(datos.get("nombre"), MAX_TEXTO) or carpeta.name
    pack.autor = _texto(datos.get("autor"), MAX_TEXTO)
    pack.descripcion = _texto(datos.get("descripcion"), MAX_DESCRIPCION)

    mapeo = datos.get("mapeo", "ciclo")
    if mapeo not in MAPEOS:
        pack.avisos.append(f"mapeo {str(mapeo)[:20]!r} desconocido: se usa «ciclo»")
        mapeo = "ciclo"
    pack.mapeo = mapeo

    vol = datos.get("volumen", 1.0)
    if isinstance(vol, bool) or not isinstance(vol, (int, float)) or vol != vol:
        pack.avisos.append("volumen no numérico: se usa 1")
        vol = 1.0
    pack.volumen = float(min(1.0, max(0.0, vol)))

    base = datos.get("base")
    if base not in (None, ""):
        destino = BASES_PERMITIDAS.get(base) if isinstance(base, str) else None
        if destino is None:
            pack.errores.append(f"«base» no permitida: {str(base)[:60]!r} "
                                f"(solo {', '.join(sorted(BASES_PERMITIDAS))})")
            return pack
        pack.base = destino

    pack.eventos = _tabla(datos.get("eventos"), pack.carpeta_archivos, "eventos", pack.avisos)
    pack.capas = _tabla(datos.get("capas"), pack.carpeta_archivos, "capas", pack.avisos)
    if not any(pack.eventos.values()) and not any(pack.capas.values()):
        pack.errores.append("no trae ningún archivo .ogg/.wav válido")
    for aviso in pack.avisos:
        log.info("pack de sonidos %s: %s", pack.id, aviso)
    return pack


def _id_valido(id_pack: str) -> bool:
    return (isinstance(id_pack, str) and bool(_RE_ID.match(id_pack))
            and not id_pack.startswith((".", "_")) and id_pack.strip() == id_pack)


def listar_packs(carpeta: Optional[Union[str, Path]] = None, *,
                 incluir_invalidos: bool = False) -> List[PackSonido]:
    """Packs de `carpeta` (por defecto sonidos/): el de por defecto primero y luego por nombre.

    Cada subcarpeta con pack.json es un pack; se saltan las que empiezan por «.» o «_».
    """
    raiz = _anclar(carpeta)
    packs: List[PackSonido] = []
    try:
        hijos = sorted(p for p in raiz.iterdir() if p.is_dir())
    except OSError:
        return packs
    for hijo in hijos:
        if not _id_valido(hijo.name) or not (hijo / ARCHIVO_PACK).exists():
            continue
        pack = cargar_pack(hijo)
        if pack.valido or incluir_invalidos:
            packs.append(pack)
    packs.sort(key=lambda p: (p.id != PACK_DEFECTO, p.nombre.casefold(), p.id))
    return packs


def obtener_pack(id_pack: str, carpeta: Optional[Union[str, Path]] = None) -> Optional[PackSonido]:
    """El pack `id_pack` (nombre de su carpeta) si existe y es válido; None si no."""
    if not _id_valido(id_pack):
        return None
    raiz = _anclar(carpeta)
    destino = raiz / id_pack
    try:
        if not _dentro(destino.resolve(), raiz.resolve()) or not (destino / ARCHIVO_PACK).is_file():
            return None
    except OSError:
        return None
    pack = cargar_pack(destino)
    return pack if pack.valido else None


_cache_defecto: Dict[Path, Tuple[int, PackSonido]] = {}


def pack_por_defecto(carpeta: Optional[Union[str, Path]] = None) -> Optional[PackSonido]:
    """El pack `default` de `carpeta` (sonidos/ si no se dice). En caché hasta que cambie su pack.json."""
    destino = _anclar(carpeta) / PACK_DEFECTO
    archivo = destino / ARCHIVO_PACK
    try:
        marca = archivo.stat().st_mtime_ns
    except OSError:
        return None
    guardado = _cache_defecto.get(archivo)
    if guardado and guardado[0] == marca:
        return guardado[1]
    pack = cargar_pack(destino)
    if not pack.valido:
        return None
    _cache_defecto[archivo] = (marca, pack)
    return pack


def _como_pack(pack: RutaPack) -> Optional[PackSonido]:
    if isinstance(pack, PackSonido):
        return pack
    if isinstance(pack, Path):
        p = cargar_pack(pack)
        return p if p.valido else None
    if isinstance(pack, str):
        return obtener_pack(pack)
    return None


def _defecto_para(pack: PackSonido) -> Optional[PackSonido]:
    """El pack por defecto que acompaña a `pack`: el `default` de su misma carpeta de
    packs si existe; si no, el de sonidos/."""
    if pack.id == PACK_DEFECTO:
        return pack
    return pack_por_defecto(pack.carpeta.parent) or pack_por_defecto()


# ── Resolución ────────────────────────────────────────────────────────────────

def mapear(existentes: List, nuevos: List, mapeo: str = "ciclo") -> List:
    """Mapeo de MEVoicePack. Sin nuevos → existentes; reemplazar → nuevos;
    ciclo → out[i] = nuevos[i % len(nuevos)] con len = max(len(existentes), len(nuevos))."""
    if not nuevos:
        return list(existentes)
    if mapeo == "reemplazar":
        return list(nuevos)
    total = max(len(existentes), len(nuevos))
    return [nuevos[i % len(nuevos)] for i in range(total)]


def resolver(pack: RutaPack, evento: str, *, capas: bool = False,
             defecto: Optional[PackSonido] = None) -> List[Path]:
    """Archivos del `evento` en `pack` (o de sus capas) con el mapeo aplicado.

    `pack` puede ser un PackSonido, el id de una carpeta de sonidos/ o una carpeta.
    Si el pack no trae el evento, o no existe (p. ej. se borró su carpeta y la
    configuración aún lo nombra), salen los del pack por defecto. Lista vacía si
    nadie lo trae.
    """
    p = _como_pack(pack)
    if p is None:
        d = defecto or pack_por_defecto()
        return list((d.capas if capas else d.eventos).get(evento, [])) if d else []
    d = defecto if defecto is not None else _defecto_para(p)
    tabla = p.capas if capas else p.eventos
    existentes = ((d.capas if capas else d.eventos).get(evento, []) if d else [])
    return mapear(existentes, tabla.get(evento, []), p.mapeo)


def archivo_al_azar(pack: RutaPack, evento: str, *, capas: bool = False,
                    defecto: Optional[PackSonido] = None,
                    azar: Callable[[], float] = random.random) -> Optional[Path]:
    """Un archivo al azar del evento (para el mezclador en patata y sprites)."""
    lista = resolver(pack, evento, capas=capas, defecto=defecto)
    if not lista:
        return None
    i = int(azar() * len(lista))
    return lista[min(max(i, 0), len(lista) - 1)]


def url_web(ruta: Path, *, prefijo: str = PREFIJO_WEB,
            carpeta_sonidos: Optional[Union[str, Path]] = None) -> Optional[str]:
    """URL del servidor local para un archivo de pack; None si no se sirve.

    ui_web/ se sirve en «/»; la carpeta de packs, en `prefijo` (publicar_carpeta).
    """
    ruta = Path(ruta)
    try:
        ruta = ruta.resolve()
        web = DIR_WEB.resolve()
        sonidos = _anclar(carpeta_sonidos).resolve()
    except OSError:
        return None
    if _dentro(ruta, web):
        return "/" + quote(ruta.relative_to(web).as_posix(), safe="/")
    if _dentro(ruta, sonidos):
        pre = "/" + prefijo.strip("/") + "/"
        return pre + quote(ruta.relative_to(sonidos).as_posix(), safe="/")
    return None


def pack_para_web(pack: RutaPack, *, defecto: Optional[PackSonido] = None,
                  prefijo: str = PREFIJO_WEB,
                  carpeta_sonidos: Optional[Union[str, Path]] = None) -> Optional[dict]:
    """El pack resuelto para `luneSonidos.cargar(objeto)`: mapeo aplicado sobre el
    de por defecto y cada archivo como URL del servidor local. None si no existe."""
    p = _como_pack(pack)
    if p is None:
        return None
    d = defecto if defecto is not None else _defecto_para(p)
    if carpeta_sonidos is None:
        carpeta_sonidos = p.carpeta.parent

    def _urls(lista: Iterable[Path]) -> List[str]:
        out = []
        for ruta in lista:
            u = url_web(ruta, prefijo=prefijo, carpeta_sonidos=carpeta_sonidos)
            if u:
                out.append(u)
            else:
                log.warning("pack %s: %s no se puede servir a la web", p.id, ruta)
        return out

    def _resuelta(capas: bool) -> Dict[str, List[str]]:
        propias = p.capas if capas else p.eventos
        claves = set(propias) | set((d.capas if capas else d.eventos) if d else {})
        return {ev: _urls(resolver(p, ev, capas=capas, defecto=d)) for ev in sorted(claves)}

    return {
        "id": p.id,
        "nombre": p.nombre,
        "autor": p.autor,
        "mapeo": p.mapeo,
        "volumen": p.volumen,
        "resuelto": True,
        "eventos": _resuelta(False),
        "capas": _resuelta(True),
    }
