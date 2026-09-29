"""
memoria.py — Sistema de memoria personal persistente para Lune CD
================================================================
Guarda y recupera información sobre el usuario entre sesiones.

CÓMO SE DECIDE QUÉ GUARDAR
--------------------------
Hay dos caminos y es importante no confundirlos:

  1. GUARDADO EXPLÍCITO (`PATRONES_EXPLICITOS`) — «recuerda que…», «anota que…».
     Están anclados con ^…$ y CONSUMEN el turno: Lune confirma «Anotado: …»
     y el mensaje no llega a la IA. Es lo que el usuario pidió, así que está bien.

  2. EXTRACCIÓN SILENCIOSA (`PATRONES_PERFIL`) — nombre, edad, ciudad, trabajo.
     Se anotan de fondo pero NO consumen el turno: el mensaje sigue su camino
     hacia la IA con normalidad.

Antes, patrones sueltos como `me gusta(.+)` se buscaban con `re.search` y
consumían el turno. Eso hacía que «me gustaría saber cómo funciona python»
se guardara como recuerdo («ría saber cómo funciona python») y el usuario
nunca recibiera respuesta. De ahí que ahora todo esté anclado y que la
inferencia sea silenciosa.

Estructura de memoria.json:
{
  "usuario": { "nombre": "...", "preferencias": [...], "contexto": "..." },
  "recuerdos": [
    { "id": "uuid", "fecha": "ISO-8601", "tipo": "hecho|preferencia|recordatorio|tarea",
      "contenido": "...", "tags": [...],
      "hecha": false, "hecha_en": "ISO", "mi_dia": "AAAA-MM-DD" }   # opcionales: tareas (10.9)
  ],
  "datos_clave": { "edad": "30", ... },       # compartido con el bot de Telegram
  "resumen_sesion_anterior": "...",
  "estadisticas": { "total_mensajes": 0, "primera_sesion": "...", "ultima_sesion": "..." }
}

Uso desde main.py:
    from nucleo.memoria import MemoriaManager
    memoria = MemoriaManager()
    contexto = memoria.obtener_contexto_para_prompt()
    respuesta = memoria.procesar_mensaje_usuario(texto)   # str o None
    memoria.cerrar_sesion(resumen)

Comandos del usuario (requieren la barra, para no comerse frases normales):
    /memoria · /recuerdos · /olvida [id] · /olvida todo

TAREAS (10.9, nucleo/tareas.py)
-------------------------------
Los recuerdos de tipo "tarea" y "recordatorio" son la lista de tareas del panel
«Tareas» (estilo Microsoft To Do) y de /tareas en patata. Para eso la memoria sabe:
  · buscar_recuerdo(id), actualizar_recuerdo(id, **campos), quitar_recuerdo(id): por id,
    sin pasar por /olvida (que busca también por texto);
  · al_cambiar(fn) → quitar: fn(motivo) tras cada cambio de recuerdos (agregar,
    actualizar, olvidar, olvidar todo, el «recuerda que…» del chat o una recarga del
    disco). Se llama en el hilo que hizo el cambio; un oyente que falla no rompe nada;
  · _sincronizar(): patata y la app son dos procesos con su propio MemoriaManager. Si
    memoria.json cambió en disco desde la última carga/guardado (mtime, tamaño e índice), se
    recarga ANTES de modificar (y al leer tareas o el contexto), para no pisar lo que
    anotó el otro. Un archivo a medio escribir no se recarga (se queda lo que había) y el
    guardado es atómico (temporal + os.replace), así el otro nunca lee medio JSON.
Las tareas hechas no van al system prompt como si estuvieran pendientes.
"""

import json
import logging
import os
import tempfile
import threading
import time
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

_log = logging.getLogger("lune.memoria")

_REINTENTOS_REEMPLAZO = 5           # os.replace con el archivo abierto por el otro proceso (Windows)
_PAUSA_REEMPLAZO_S = 0.02
_TIPOS_TAREA = ("tarea", "recordatorio")


MEMORIA_PATH = Path(__file__).parent.parent / "memoria.json"

TIPOS_RECUERDO = {
    "hecho":        "·",
    "preferencia":  "·",
    "recordatorio": "·",
    "tarea":        "·",
    "general":      "·",
}

# ── 1. Guardado explícito: el usuario pide guardar → consume el turno ──────────
# Anclados a la frase completa. Nada de `search` suelto.
PATRONES_EXPLICITOS = [
    re.compile(r"^(?:recuerda|recuérda(?:me)?|recuerdame)\s+que\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:anota|apunta|guarda)\s+que\s+(.+)$", re.IGNORECASE),
    re.compile(r"^no\s+(?:te\s+)?olvides\s+(?:de\s+)?que\s+(.+)$", re.IGNORECASE),
]

# ── 2. Extracción silenciosa: se infiere de fondo, NO consume el turno ────────
# El valor va acotado (sin `.+` glotón) para no tragarse la frase entera.
_NOMBRE = r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,19}|[a-záéíóúñ]{2,20})"
PATRONES_PERFIL = [
    ("nombre",  re.compile(rf"\bme\s+llamo\s+{_NOMBRE}\b", re.IGNORECASE)),
    ("nombre",  re.compile(rf"\bmi\s+nombre\s+es\s+{_NOMBRE}\b", re.IGNORECASE)),
    ("edad",    re.compile(r"\btengo\s+(\d{1,3})\s+años\b", re.IGNORECASE)),
    # Ciudad y trabajo solo si la frase ENTERA es esa afirmación. «trabajo en un
    # script y no me compila» no es una profesión, y prefiero anotar de menos
    # que ensuciar la memoria con basura que luego va al system prompt.
    ("ciudad",  re.compile(r"^vivo\s+en\s+([^.,;:!?]{2,40})[.!]?$", re.IGNORECASE)),
    ("trabajo", re.compile(r"^trabajo\s+(?:en|como)\s+([^.,;:!?]{2,40})[.!]?$", re.IGNORECASE)),
]

# Conectores que delatan que lo capturado es una oración, no un dato.
# «trabajo en un script y no me compila» encaja en el patrón de trabajo, pero
# «un script y no me compila» no es una profesión.
_CONECTORES_DE_ORACION = (
    " y ", " o ", " no ", " que ", " pero ", " porque ", " aunque ",
    " cuando ", " si ", " me ", " te ", " se ", " lo ",
)
_MAX_PALABRAS_PERFIL = 5


def _valor_de_perfil_plausible(valor: str) -> bool:
    """
    ¿El texto capturado parece un dato (una ciudad, un oficio) y no media frase?
    Se prefiere anotar de menos: lo que entra aquí acaba en el system prompt.
    """
    v = f" {valor.lower().strip()} "
    if any(c in v for c in _CONECTORES_DE_ORACION):
        return False
    return 1 <= len(valor.split()) <= _MAX_PALABRAS_PERFIL


# Palabras clave para clasificar un recuerdo ya capturado
KEYWORDS_RECORDATORIO = [
    "mañana", "el lunes", "el martes", "el miércoles", "el jueves",
    "el viernes", "la próxima semana", "en una hora", "a las", "el día",
]
KEYWORDS_TAREA = ["tengo que", "debo", "necesito", "pendiente", "hacer"]
KEYWORDS_PREFERENCIA = [
    "prefiero", "me gusta", "favorito", "favorita", "no me gusta",
    "odio", "amo", "encanta",
]


# ─────────────────────────────────────────────────────────────────────────────

def mensajes_aproximados(total) -> int:
    """El total de mensajes redondeado hacia abajo a una cifra significativa (812 →
    800, 45 → 40, 1234 → 1000); 0 si son menos de 10. Estable entre mensajes."""
    try:
        n = int(total or 0)
    except (TypeError, ValueError):
        return 0
    if n < 10:
        return 0
    base = 10 ** (len(str(n)) - 1)
    return (n // base) * base


class MemoriaManager:
    """Gestor de memoria personal persistente entre sesiones."""

    # Valores por defecto de clase: una instancia hecha con __new__ (algún test arma una
    # memoria así, solo con _data) sigue funcionando para leer.
    path: Optional[Path] = None
    _firma: Optional[tuple] = None
    _mensajes_sin_guardar = 0
    _oyentes: tuple = ()

    @property
    def _lock(self) -> "threading.RLock":
        """El candado de esta instancia (se crea al primer uso; setdefault es atómico)."""
        candado = self.__dict__.get("_candado")
        if candado is None:
            candado = self.__dict__.setdefault("_candado", threading.RLock())
        return candado

    def __init__(self, path: Path = MEMORIA_PATH):
        self.path = Path(path)
        self._oyentes: list = []                  # al_cambiar(fn): fn(motivo)
        self._firma: Optional[tuple] = None       # (mtime_ns, tamaño, índice) tras la última carga/guardado
        self._mensajes_sin_guardar = 0            # total_mensajes contados y aún no escritos
        self._data = self._cargar()
        self._mensajes_sesion: int = 0
        self._recuerdos_nuevos_sesion: list[str] = []
        self._registrar_inicio_sesion()

    # ── Carga / guardado ─────────────────────────────────────────────────────

    def _firma_disco(self) -> Optional[tuple]:
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        # st_ino: cada guardado atómico deja un archivo nuevo (otro índice en NTFS), así dos
        # escrituras en el mismo tic del reloj y con el mismo tamaño también se distinguen.
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def _leer_disco(self) -> Optional[dict]:
        """memoria.json con las secciones que falten rellenas; None si no está o no es JSON."""
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        # Rellena secciones que falten en memorias de versiones viejas
        for clave, valor in self._estructura_vacia().items():
            data.setdefault(clave, valor)
        if not isinstance(data.get("recuerdos"), list):
            data["recuerdos"] = []
        return data

    def _cargar(self) -> dict:
        if self.path.exists():
            firma = self._firma_disco()
            data = self._leer_disco()
            if data is not None:
                self._firma = firma
                return data
        return self._estructura_vacia()

    def _guardar(self):
        with self._lock:
            texto = json.dumps(self._data, ensure_ascii=False, indent=2)
            self._escribir(texto)
            self._firma = self._firma_disco()
            self._mensajes_sin_guardar = 0

    def _escribir(self, texto: str) -> None:
        """Atómico (temporal en la misma carpeta + os.replace): el otro proceso (patata o la
        app) nunca lee medio JSON. Si el reemplazo no se deja (archivo abierto por otro en
        Windows, reintentos agotados), se escribe directamente como siempre."""
        tmp = None
        try:
            carpeta = self.path.parent
            fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(carpeta))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
            for intento in range(_REINTENTOS_REEMPLAZO):
                try:
                    os.replace(tmp, self.path)
                    tmp = None
                    return
                except PermissionError:
                    if intento < _REINTENTOS_REEMPLAZO - 1:
                        time.sleep(_PAUSA_REEMPLAZO_S)
        except OSError as e:
            _log.warning("memoria: no pude guardar de forma atómica (%s); escribo directamente", e)
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self.path.write_text(texto, encoding="utf-8")

    def _sincronizar(self) -> bool:
        """Si memoria.json cambió en disco desde la última carga/guardado (patata y la app
        son dos procesos que lo escriben), lo recarga. Devuelve True si recargó. Un archivo
        a medio escribir o roto no se recarga: se queda lo que había. Los mensajes contados
        y aún sin guardar se suman al total recargado. Avisa a los oyentes («recargar») si
        cambiaron los recuerdos."""
        if self.path is None:
            return False
        with self._lock:
            firma = self._firma_disco()
            if firma is None or firma == self._firma:
                return False
            data = self._leer_disco()
            if data is None:
                return False
            antes = self._data.get("recuerdos")
            if self._mensajes_sin_guardar:
                stats = data.setdefault("estadisticas", {})
                try:
                    stats["total_mensajes"] = int(stats.get("total_mensajes", 0) or 0) + self._mensajes_sin_guardar
                except (TypeError, ValueError):
                    pass
            self._data = data
            self._firma = firma
            cambio = data.get("recuerdos") != antes
        if cambio:
            self._avisar("recargar")
        return True

    # ── Oyentes (el panel de tareas se refresca solo) ───────────────────────

    def al_cambiar(self, fn: Callable[[str], None]) -> Callable[[], None]:
        """fn(motivo) tras cada cambio de recuerdos: «agregar», «actualizar», «olvidar»,
        «olvidar_todo» o «recargar» (memoria.json cambió en disco). Se llama en el hilo
        que hizo el cambio. Devuelve la función para darse de baja."""
        with self._lock:
            if fn not in self._oyentes:
                self._oyentes = [*self._oyentes, fn]
        return lambda: self.quitar_oyente(fn)

    def quitar_oyente(self, fn) -> None:
        with self._lock:
            self._oyentes = [f for f in self._oyentes if f is not fn and f != fn]

    def _avisar(self, motivo: str) -> None:
        """Fuera del candado: un oyente puede volver a leer la memoria."""
        with self._lock:
            oyentes = list(self._oyentes)
        for fn in oyentes:
            try:
                fn(motivo)
            except Exception:
                _log.exception("memoria: un oyente de al_cambiar falló (%s)", motivo)

    def _estructura_vacia(self) -> dict:
        ahora = datetime.now().isoformat()
        return {
            "usuario": {
                "nombre": None,
                "preferencias": [],
                "contexto": "",
            },
            "recuerdos": [],
            "datos_clave": {},
            "resumen_sesion_anterior": "",
            "estadisticas": {
                "total_mensajes": 0,
                "primera_sesion": ahora,
                "ultima_sesion": ahora,
            },
        }

    def _registrar_inicio_sesion(self):
        self._data["estadisticas"]["ultima_sesion"] = datetime.now().isoformat()
        self._guardar()

    # ── API pública ───────────────────────────────────────────────────────────

    def obtener_contexto_para_prompt(self) -> str:
        """
        Devuelve un bloque de texto listo para insertar en el system prompt.
        Resume lo que Lune sabe del usuario sin saturar el contexto. Las tareas ya
        hechas no entran (no son pendientes). Sin horas ni contadores nuevos: el texto
        es estable entre mensajes (caché de prefijo del modelo).
        """
        self._sincronizar()
        partes = []
        usuario = self._data.get("usuario", {})

        if nombre := usuario.get("nombre"):
            partes.append(f"El usuario se llama {nombre}.")

        recuerdos = [r for r in self._data.get("recuerdos", [])
                     if not (r.get("tipo") in _TIPOS_TAREA and r.get("hecha") is True)]
        if recuerdos:
            # Últimos 15 recuerdos ordenados por fecha desc
            recientes = sorted(recuerdos, key=lambda r: r["fecha"], reverse=True)[:15]
            lineas = []
            for r in recientes:
                emoji = TIPOS_RECUERDO.get(r.get("tipo", "general"), "")
                fecha_corta = r["fecha"][:10]
                lineas.append(f"  {emoji} [{fecha_corta}] {r['contenido']}")
            partes.append("Lo que sé sobre el usuario:\n" + "\n".join(lineas))

        # Hechos clave:valor (compartidos con el bot de Telegram)
        datos_clave = self._data.get("datos_clave", {})
        if datos_clave:
            lineas = [f"  · {k}: {v}" for k, v in datos_clave.items()]
            partes.append("Datos del usuario:\n" + "\n".join(lineas))

        resumen = self._data.get("resumen_sesion_anterior", "")
        if resumen:
            partes.append(f"Resumen de la última sesión: {resumen}")

        # Redondeado a propósito: un contador exacto cambiaba en CADA mensaje y, como
        # la memoria va en el system prompt, rompía la caché de prefijo del modelo
        # (prueba real: 37 s hasta el primer token). Así cambia muy de vez en cuando.
        stats = self._data.get("estadisticas", {})
        aprox = mensajes_aproximados(stats.get("total_mensajes", 0))
        if aprox:
            partes.append(f"Llevamos más de {aprox} mensajes intercambiados en total.")

        if not partes:
            return ""

        return (
            "\n\n--- MEMORIA PERSONAL ---\n"
            + "\n".join(partes)
            + "\n--- FIN MEMORIA ---\n"
        )

    def procesar_mensaje_usuario(self, mensaje: str) -> Optional[str]:
        """
        Analiza el mensaje del usuario.

        Devuelve una respuesta SOLO si el usuario pidió explícitamente algo de
        memoria (un comando /… o un «recuerda que…»). En ese caso el turno se
        consume y no se llama a la IA.

        Devuelve None para conversación normal — incluso si de paso se extrajo
        algún dato de perfil, que se guarda en silencio.
        """
        self._sincronizar()                     # patata o la otra ventana pudieron anotar algo
        self._mensajes_sesion += 1
        with self._lock:
            self._data["estadisticas"]["total_mensajes"] = (
                self._data["estadisticas"].get("total_mensajes", 0) + 1
            )
            self._mensajes_sin_guardar += 1

        texto = (mensaje or "").strip()
        msg_lower = texto.lower()

        # ── Comandos explícitos (requieren la barra) ──────────────────────────
        if re.fullmatch(r"/(?:memoria|recuerdos)", msg_lower):
            return self._cmd_listar()

        if re.fullmatch(r"/olvida\s+todo", msg_lower):
            return self._cmd_olvida_todo()

        if m := re.fullmatch(r"/olvida\s+(.+)", msg_lower):
            return self._cmd_olvida(m.group(1).strip())

        # ── «recuerda que…» → guarda y consume el turno ───────────────────────
        for patron in PATRONES_EXPLICITOS:
            if m := patron.match(texto):
                contenido = m.group(1).strip().rstrip(".")
                if not contenido:
                    continue
                tipo = self._detectar_tipo(contenido)
                self.agregar_recuerdo(contenido, tipo)
                # Un «recuerda que me llamo X» también actualiza el perfil
                self._extraer_perfil(contenido)
                self._guardar()
                emoji = TIPOS_RECUERDO.get(tipo, "")
                return f"{emoji} Anotado: *{contenido}*"

        # ── Extracción silenciosa: anota de fondo y deja pasar el mensaje ─────
        if self._extraer_perfil(texto):
            self._guardar()

        return None  # conversación normal → va a la IA

    def _extraer_perfil(self, texto: str) -> bool:
        """
        Busca datos de perfil (nombre, edad, ciudad, trabajo) y los guarda.
        Devuelve True si algo cambió. NUNCA interrumpe la conversación.
        """
        cambio = False
        for campo, patron in PATRONES_PERFIL:
            m = patron.search(texto)
            if not m:
                continue
            valor = m.group(1).strip().rstrip(".,;:")
            if not valor:
                continue

            if campo == "nombre":
                nombre = valor.capitalize()
                if self._data["usuario"].get("nombre") != nombre:
                    self._data["usuario"]["nombre"] = nombre
                    cambio = True
            else:
                # La edad ya viene acotada por el patrón (\d{1,3}); ciudad y
                # trabajo son texto libre y necesitan el filtro de plausibilidad.
                if campo != "edad" and not _valor_de_perfil_plausible(valor):
                    continue
                datos = self._data.setdefault("datos_clave", {})
                if datos.get(campo) != valor:
                    datos[campo] = valor
                    cambio = True
        return cambio

    def procesar_respuesta_lune(self, respuesta: str):
        """
        Persiste el estado tras recibir una respuesta completa.
        Llamar después de cada respuesta de Lune.
        """
        self._sincronizar()                     # no pisar lo que anotó el otro proceso
        self._guardar()

    def agregar_recuerdo(
        self,
        contenido: str,
        tipo: str = "general",
        tags: Optional[list] = None,
        **campos,
    ) -> str:
        """Agrega un recuerdo manualmente. Devuelve su ID. `campos` (opcionales, p. ej.
        los de las tareas: fecha, hecha, hecha_en, mi_dia) van también al recuerdo."""
        self._sincronizar()
        rid = str(uuid.uuid4())[:8]
        recuerdo = {
            "id": rid,
            "fecha": datetime.now().isoformat(),
            "tipo": tipo,
            "contenido": contenido,
            "tags": tags or [],
        }
        recuerdo.update({k: v for k, v in campos.items() if k != "id"})
        with self._lock:
            self._data["recuerdos"].append(recuerdo)
            self._recuerdos_nuevos_sesion.append(rid)
            self._guardar()
        self._avisar("agregar")
        return rid

    def buscar_recuerdo(self, rid: str) -> Optional[dict]:
        """El recuerdo con ese id exacto (el dict vivo de la memoria) o None."""
        self._sincronizar()
        with self._lock:
            return next((r for r in self._data.get("recuerdos", [])
                         if isinstance(r, dict) and r.get("id") == rid), None)

    def actualizar_recuerdo(self, rid: str, **campos) -> Optional[dict]:
        """Cambia campos de un recuerdo (no su id) y guarda. Devuelve el recuerdo o None
        si no existe. Recarga antes del disco si el otro proceso lo tocó."""
        self._sincronizar()
        with self._lock:
            r = next((x for x in self._data.get("recuerdos", [])
                      if isinstance(x, dict) and x.get("id") == rid), None)
            if r is None:
                return None
            r.update({k: v for k, v in campos.items() if k != "id"})
            self._guardar()
            copia = dict(r)
        self._avisar("actualizar")
        return copia

    def quitar_recuerdo(self, rid: str) -> Optional[dict]:
        """Borra el recuerdo con ese id exacto (sin buscar por texto como /olvida).
        Devuelve el borrado o None."""
        self._sincronizar()
        with self._lock:
            recuerdos = self._data.get("recuerdos", [])
            idx = next((i for i, x in enumerate(recuerdos) if isinstance(x, dict) and x.get("id") == rid), None)
            if idx is None:
                return None
            borrado = recuerdos.pop(idx)
            self._guardar()
        self._avisar("olvidar")
        return borrado

    def cerrar_sesion(self, resumen: str = ""):
        """
        Llama esto al cerrar la app.
        Guarda el resumen de la sesión actual como contexto para la próxima.
        """
        self._sincronizar()
        if resumen:
            self._data["resumen_sesion_anterior"] = resumen[:500]
        self._data["estadisticas"]["ultima_sesion"] = datetime.now().isoformat()
        self._guardar()

    def get_nombre_usuario(self) -> Optional[str]:
        return self._data.get("usuario", {}).get("nombre")

    def get_todos_recuerdos(self) -> list:
        self._sincronizar()
        return self._data.get("recuerdos", [])

    def get_stats(self) -> dict:
        return self._data.get("estadisticas", {})

    # ── Comandos internos ─────────────────────────────────────────────────────

    def _cmd_listar(self) -> str:
        self._sincronizar()
        recuerdos = self._data.get("recuerdos", [])
        usuario = self._data.get("usuario", {})
        datos_clave = self._data.get("datos_clave", {})

        if not recuerdos and not datos_clave and not usuario.get("nombre"):
            return "No tengo nada guardado todavía. Dime *'recuerda que...'* para empezar."

        lineas = ["**Lo que sé sobre ti:**\n"]

        if nombre := usuario.get("nombre"):
            lineas.append(f"Nombre: {nombre}")

        # Hechos clave:valor (compartidos con el bot de Telegram)
        if datos_clave:
            lineas.append("\n**Datos** (compartidos con Telegram):")
            for k, v in datos_clave.items():
                lineas.append(f"  · {k}: {v}")

        por_tipo: dict[str, list] = {}
        for r in sorted(recuerdos, key=lambda x: x["fecha"], reverse=True):
            t = r.get("tipo", "general")
            por_tipo.setdefault(t, []).append(r)

        for tipo, items in por_tipo.items():
            emoji = TIPOS_RECUERDO.get(tipo, "")
            lineas.append(f"\n{emoji} **{tipo.capitalize()}:**")
            for r in items[:10]:
                fecha = r["fecha"][:10]
                hecha = " (hecha)" if tipo in _TIPOS_TAREA and r.get("hecha") is True else ""
                lineas.append(f"  `{r['id']}` [{fecha}] {r['contenido']}{hecha}")

        stats = self._data.get("estadisticas", {})
        lineas.append(f"\nTotal de mensajes: {stats.get('total_mensajes', 0)}")
        lineas.append("*Usa /olvida [id] para borrar un recuerdo.*")
        return "\n".join(lineas)

    def _cmd_olvida(self, fragmento: str) -> str:
        self._sincronizar()
        with self._lock:
            recuerdos = self._data.get("recuerdos", [])
            # Buscar por ID exacto primero
            idx = next((i for i, r in enumerate(recuerdos) if r["id"] == fragmento), None)
            # Si no, buscar por fragmento de contenido
            if idx is None:
                idx = next(
                    (i for i, r in enumerate(recuerdos) if fragmento in r["contenido"].lower()),
                    None
                )
            if idx is None:
                return f"No encontré ningún recuerdo con *'{fragmento}'*. Usa /memoria para ver los IDs."

            borrado = recuerdos.pop(idx)
            self._guardar()
        self._avisar("olvidar")
        return f"Olvidado: *{borrado['contenido']}*"

    def _cmd_olvida_todo(self) -> str:
        self._sincronizar()
        with self._lock:
            n = len(self._data.get("recuerdos", [])) + len(self._data.get("datos_clave", {}))
            self._data["recuerdos"] = []
            self._data["datos_clave"] = {}
            self._data["usuario"]["nombre"] = None
            self._data["resumen_sesion_anterior"] = ""
            self._guardar()
        self._avisar("olvidar_todo")
        return f"Memoria borrada. Eliminé {n} datos. Empezamos de cero."

    def _detectar_tipo(self, texto: str) -> str:
        texto_l = texto.lower()
        if any(k in texto_l for k in KEYWORDS_RECORDATORIO):
            return "recordatorio"
        if any(k in texto_l for k in KEYWORDS_TAREA):
            return "tarea"
        if any(k in texto_l for k in KEYWORDS_PREFERENCIA):
            return "preferencia"
        return "hecho"
