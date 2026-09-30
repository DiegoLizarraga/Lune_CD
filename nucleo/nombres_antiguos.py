"""
nucleo/nombres_antiguos.py — Los nombres de antes de la 11, para no romper lo que ya hay guardado.

POR QUÉ EXISTE
--------------
Hasta la 10.9, Lune fuera de la ventana se llamaba «mascota» (y «mascot» en rutas,
clases y CSS). En la 11 Diego pidió quitar esa palabra de todo el proyecto, código e
interfaz, porque suena ofensiva: ahora es el modo «asistente en escritorio» y en el
código todo dice «asistente». Pero lo que la gente ya tiene guardado sigue con los
nombres viejos (config.json, datos.json, el historial de chats/), y los modelos los
repiten por costumbre o porque los ven en ese historial.

Este módulo es el ÚNICO sitio del repo donde se escribe la palabra vieja (junto con sus
tests, tests/test_nombres_antiguos.py). tests/test_sin_nombre_antiguo.py falla si
aparece en cualquier otro archivo. Aquí solo va lo necesario para traducir lo viejo a
lo nuevo: nada de lógica de la app.

QUÉ SE TRADUCE Y QUIÉN LO USA
-----------------------------
- config.json → nucleo/config.Config._migrar (esquema 2, una sola vez): ids de acción
  en atajos.lista[].id, bandeja.acciones, menu_radial.principal/secundario y el valor
  de sistema.autoinicio_como.
- datos.json → nucleo/datos (al cargar y al guardar): la clave de las frases de cada
  personaje (personajes[].frases_…). Si están las dos, gana la nueva.
- Lo que escribe el modelo → lune_core/marcadores.nombre_herramienta: los nombres de
  herramienta de antes (<|mascota_bailar|>, <|CALL ["mascota_dormir", {}]|>…).
- Lo que teclea la persona por costumbre → como_autoinicio() («/autoinicio como
  mascota» en patata).
- Un id de acción viejo que vuelva a aparecer en config.json DESPUÉS de la migración
  (un Lune de la 10.x que seguía abierto y guarda su copia, o un config restaurado a
  mano con el esquema ya en 2) → accion(), al leer: nucleo/acciones_ui (validar_lista,
  en_modo y el Despachador), y migrar_atajos() en ui/atajos_qt.GestorAtajosQt (lista y
  cambiar). Así el botón de la bandeja o del radial y el atajo siguen funcionando en
  vez de desaparecer sin avisar.
- bailes/LEEME.txt (fuera de git) → nucleo/bailes.Biblioteca.asegurar_carpeta con
  leeme_viejo(): el LEEME que escribió Lune antes de la 11 se reescribe con el texto
  de ahora; uno que no sea de Lune (no empieza por su cabecera) no se toca.
- El hub entre equipos → tipo_evento(): el tipo «mascota:accion» de lune_core/protocolo
  (hoy nadie lo emite ni lo atiende; está por si un terminal viejo lo manda).

QUÉ NO SE TOCA
--------------
- chats/ y memoria.json: lo que escribiste tú es tuyo. Las marcas de herramienta con el
  nombre viejo que haya en el historial las entiende marcadores, y al guardar la
  respuesta nueva ya se escriben con el nombre de ahora (marcadores.normalizar).
- El registro de arranque con Windows (servicios/autoinicio.py) no lleva el nombre: solo
  «/autoinicio» y «/patata»; el modo sale de config.json, que sí se migra.
- localStorage de la web: solo guarda «lune-fx» (los efectos), sin el nombre viejo.
- Si alguien dejó clips propios en la carpeta vieja de la web (ui_web/assets/mascot/,
  sin versionar), hay que moverlos a mano a ui_web/assets/asistente/.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

# La palabra vieja y la de ahora (en identificadores; en la interfaz se dice
# «asistente en escritorio»).
VIEJA = "mascota"
NUEVA = "asistente"

# Ids de acción de la interfaz (nucleo/acciones_ui.ACCIONES) que config.json guarda en
# atajos.lista[].id, bandeja.acciones y menu_radial.principal/secundario.
ACCIONES: Dict[str, str] = {
    "mascota": "asistente",
    "cerrar_mascota": "cerrar_asistente",
}

# Valores de sistema.autoinicio_como (nucleo/arranque.COMOS).
COMOS_AUTOINICIO: Dict[str, str] = {
    "mascota": "asistente",
}

# Herramientas del modelo (lune_core/catalogo_herramientas.CATALOGO).
HERRAMIENTAS: Dict[str, str] = {
    "mascota_bailar": "asistente_bailar",
    "mascota_despertar": "asistente_despertar",
    "mascota_dormir": "asistente_dormir",
    "mascota_pantalla_grande": "asistente_pantalla_grande",
    "mascota_sentarse": "asistente_sentarse",
    "mascota_tamano": "asistente_tamano",
}

# Claves de un personaje en datos.json (nucleo/personajes.py).
CLAVES_PERSONAJE: Dict[str, str] = {
    "frases_mascota": "frases_asistente",
}

# Tipos de evento del hub (lune_core/protocolo.Tipo).
TIPOS_EVENTO: Dict[str, str] = {
    "mascota:accion": "asistente:accion",
}


# ── Valores sueltos ─────────────────────────────────────────────────────────────

def accion(id_: Any) -> Any:
    """Id de acción con el nombre de ahora. Lo que no es un nombre viejo sale tal cual."""
    return ACCIONES.get(id_, id_) if isinstance(id_, str) else id_


def como_autoinicio(valor: Any) -> Any:
    """sistema.autoinicio_como (o «/autoinicio como …») con el nombre de ahora. Sin
    distinguir mayúsculas ni espacios, como nucleo/arranque; lo demás, tal cual."""
    if isinstance(valor, str):
        return COMOS_AUTOINICIO.get(valor.strip().lower(), valor)
    return valor


def herramienta(nombre: Any) -> Any:
    """Nombre de herramienta con el nombre de ahora (ya en minúsculas y con «_»,
    como lo deja lune_core/marcadores). Lo demás, tal cual."""
    return HERRAMIENTAS.get(nombre, nombre) if isinstance(nombre, str) else nombre


def tipo_evento(tipo: Any) -> Any:
    """Tipo de evento del hub con el nombre de ahora. Lo demás, tal cual."""
    return TIPOS_EVENTO.get(tipo, tipo) if isinstance(tipo, str) else tipo


def texto_viejo(texto: Any) -> bool:
    """¿Lleva el texto la palabra vieja (en cualquier mayúscula)?"""
    return isinstance(texto, str) and VIEJA in texto.lower()


# Cabecera con la que empieza el bailes/LEEME.txt que escribe Lune (nucleo/bailes.TEXTO_LEEME).
CABECERA_LEEME_BAILES = "BAILES DE LUNE\n=============="


def leeme_viejo(texto: Any) -> bool:
    """¿Es `texto` un bailes/LEEME.txt que escribió Lune antes de la 11? Empieza por su
    cabecera (con saltos de línea de Windows o de Unix, con o sin BOM) y lleva la palabra
    vieja. Un LEEME que escribió la persona no empieza así y se deja en paz."""
    if not isinstance(texto, str):
        return False
    t = texto.lstrip("\ufeff").replace("\r\n", "\n")
    return t.startswith(CABECERA_LEEME_BAILES) and texto_viejo(t)


# ── config.json ─────────────────────────────────────────────────────────────────

def migrar_lista_acciones(lista: Any) -> Tuple[Any, bool]:
    """["mascota", "voz"] → (["asistente", "voz"], True). Cada id viejo se cambia en su
    sitio; si el nuevo ya estaba en la lista, gana ese y el viejo se quita (no quedan
    repetidos). Devuelve una lista NUEVA (la de entrada no se toca). Lo que no es una
    lista sale tal cual, con False."""
    if not isinstance(lista, list):
        return lista, False
    presentes = {x for x in lista if isinstance(x, str) and x not in ACCIONES}
    nueva: List[Any] = []
    cambio = False
    for x in lista:
        if isinstance(x, str) and x in ACCIONES:
            cambio = True
            n = ACCIONES[x]
            if n in presentes:
                continue
            presentes.add(n)
            nueva.append(n)
        else:
            nueva.append(x)
    return (nueva, True) if cambio else (lista, False)


def migrar_atajos(lista: Any) -> Tuple[Any, bool]:
    """atajos.lista ([{id, combo}]) con los ids de ahora. Se conserva el combo de cada
    uno; si ya había una entrada con el id nuevo, gana esa y la vieja se quita. Devuelve
    una lista NUEVA (las entradas cambiadas son dicts nuevos); lo que no es una lista
    sale tal cual, con False."""
    if not isinstance(lista, list):
        return lista, False
    presentes = {e.get("id") for e in lista
                 if isinstance(e, dict) and isinstance(e.get("id"), str) and e.get("id") not in ACCIONES}
    nueva: List[Any] = []
    cambio = False
    for e in lista:
        id_ = e.get("id") if isinstance(e, dict) else None
        if isinstance(id_, str) and id_ in ACCIONES:
            cambio = True
            n = ACCIONES[id_]
            if n in presentes:
                continue
            presentes.add(n)
            nueva.append({**e, "id": n})
        else:
            nueva.append(e)
    return (nueva, True) if cambio else (lista, False)


# ── datos.json ──────────────────────────────────────────────────────────────────

def _clave_evento(k: Any) -> str:
    # Como lune_core/frases_asistente.frases_de_personaje compara los eventos.
    return str(k).strip().lower()


def _fusionar_frases(nuevas: Any, viejas: Any) -> Any:
    """Las frases de la clave nueva y la vieja juntas: gana la nueva en cada evento y de
    la vieja se conserva lo que no choca. Si una de las dos no es un objeto (null, una
    lista…), se queda la que sí lo es; si ninguna lo es, la nueva."""
    if isinstance(nuevas, Mapping) and isinstance(viejas, Mapping):
        fusion = dict(nuevas)
        ya = {_clave_evento(k) for k in fusion}
        for k, v in viejas.items():
            if _clave_evento(k) not in ya:
                fusion[k] = v
                ya.add(_clave_evento(k))
        return fusion
    if not isinstance(nuevas, Mapping) and isinstance(viejas, Mapping):
        return viejas
    return nuevas


def migrar_personaje(p: Any) -> bool:
    """Un personaje de datos.json con las claves de ahora, EN EL SITIO. La clave vieja
    se renombra sin mover su posición; si ya estaba la nueva, se fusionan (gana la
    nueva). True si cambió algo. Idempotente."""
    if not isinstance(p, dict):
        return False
    cambio = False
    for vieja, nueva in CLAVES_PERSONAJE.items():
        if vieja not in p:
            continue
        cambio = True
        if nueva in p:
            p[nueva] = _fusionar_frases(p[nueva], p[vieja])
            del p[vieja]
        else:
            items = list(p.items())
            p.clear()
            p.update((nueva if k == vieja else k, v) for k, v in items)
    return cambio


def migrar_datos(data: Any) -> bool:
    """datos.json entero (personajes[]) con los nombres de ahora, EN EL SITIO.
    True si cambió algo. Idempotente."""
    if not isinstance(data, dict):
        return False
    personajes = data.get("personajes")
    if not isinstance(personajes, list):
        return False
    cambio = False
    for p in personajes:
        cambio = migrar_personaje(p) or cambio
    return cambio


__all__ = (
    "VIEJA", "NUEVA", "ACCIONES", "COMOS_AUTOINICIO", "HERRAMIENTAS", "CLAVES_PERSONAJE",
    "TIPOS_EVENTO", "CABECERA_LEEME_BAILES", "accion", "como_autoinicio", "herramienta",
    "tipo_evento", "texto_viejo", "leeme_viejo",
    "migrar_lista_acciones", "migrar_atajos", "migrar_personaje", "migrar_datos",
)
