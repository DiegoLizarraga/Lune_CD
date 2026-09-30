"""
nucleo/estado_mascota.py — Qué está haciendo Lune ahora, en un solo sitio.

PARA QUÉ SIRVE
--------------
Varias piezas necesitan saber lo mismo: la presencia de Discord («Bailando»),
los botones del menú radial (¿se enseña «Parar baile»?), el salvapantallas
(no salta si la están arrastrando o si habla), la cadencia de Minecraft, el
modo juego... En vez de que cada una pregunte a la ventana de la mascota,
todas leen `BusEstado.actual()` o se suscriben a sus cambios.

Y hay máquinas que se pisan: la pantalla grande, las alarmas, sentarse, el
reproductor MMD y la comida quieren mover la misma ventana o el mismo cuerpo.
La TABLA DE PRIORIDADES decide quién gana:

    juego > alarma > grande = salvapantallas > mmd > sentada > comida > baile > idle

- `puede(actividad, estado)`: ¿puede empezar ahora? No, si hay otra activa por
  encima o del mismo nivel (grande y salvapantallas no se interrumpen entre sí).
- `que_ceder(nueva, estado)`: qué actividades activas hay que interrumpir para
  que empiece `nueva`, de la más a la menos prioritaria.
- `BusEstado.iniciar_actividad()` / `terminar_actividad()` hacen eso mismo de
  forma atómica y además RECUERDAN lo interrumpido que hay que reanudar: si
  entra la pantalla grande estando sentada en la barra, se devuelve la cesión
  («levántala») y, cuando termina la pantalla grande, `terminar_actividad`
  devuelve «vuelve a sentarla en la barra».

`baile` es el baile automático al detectar música; `mmd` es el reproductor de
bailes que se pone a mano. El automático no la levanta de su asiento; el MMD sí.

Sin Qt y seguro entre hilos (un lock). Los suscriptores se llaman FUERA del
lock y en orden: si uno llama a `actualizar()`, su cambio se notifica cuando
termina la ronda en curso, nunca anidado.
"""
from __future__ import annotations

import dataclasses
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

_log = logging.getLogger("lune.estado")

# Valores de `bailando`
BAILE_MUSICA = "musica"
BAILE_MMD = "mmd"

# Valores habituales de `sentada`
SENTADA_BARRA = "barra"
SENTADA_VENTANA = "ventana"

# Fuentes de `pensando` (BusEstado.pensar): lo escrito con actualizar(pensando=…) (la
# mascota comentando la pantalla) y el chat de la ventana web o nativa.
PENSANDO_DIRECTO = "directo"
PENSANDO_CHAT = "chat"


@dataclass(frozen=True)
class EstadoMascota:
    """Foto inmutable de lo que hace Lune. Se cambia con `BusEstado.actualizar()`."""
    render: str = ""                # vrm · animado · sprites · carita · patata · web ("" = sin mascota)
    visible: bool = False
    arrastrando: bool = False
    durmiendo: bool = False
    pensando: bool = False          # esperando la respuesta del modelo
    hablando: bool = False          # la voz está sonando
    llamada: bool = False           # modo llamada (micro abierto)
    bailando: str = ""              # "" · "musica" (automático) · "mmd" (reproductor)
    sentada: str = ""               # "" · "barra" · "ventana"
    grande: bool = False            # pantalla grande
    salvapantallas: bool = False
    alarma: bool = False            # hay una alarma sonando
    comiendo: bool = False
    menu_abierto: bool = False      # menú radial, bandeja o panel encima
    juego: bool = False             # modo juego (hay un juego en primer plano)
    emocion: str = "neutral"        # la última emoción canónica (happy, sad…)


_CAMPOS: Dict[str, Any] = {f.name: f.default for f in dataclasses.fields(EstadoMascota)}
_CAMPOS_TEXTO = frozenset(n for n, d in _CAMPOS.items() if isinstance(d, str))

# ── Tabla de prioridades ─────────────────────────────────────────────────────────
PRIORIDAD: Dict[str, int] = {
    "juego": 70,
    "alarma": 60,
    "grande": 50,
    "salvapantallas": 50,
    "mmd": 40,
    "sentada": 30,
    "comida": 20,
    "baile": 10,
    "idle": 0,
}
ACTIVIDADES: Tuple[str, ...] = tuple(sorted(PRIORIDAD, key=lambda a: -PRIORIDAD[a]))

# Pares que pueden estar activos a la vez sin que ninguno ceda:
# - la alarma se enseña en pantalla grande (la pide ella misma);
# - se puede comer sentada (la comida busca la cabeza esté donde esté).
COEXISTEN = frozenset({
    frozenset({"alarma", "grande"}),
    frozenset({"sentada", "comida"}),
})

# Al ceder, estas se recuerdan para volver a ellas cuando termine la que las
# interrumpió. La comida no: un batido a medias se cancela.
REANUDABLES = frozenset({"sentada", "mmd", "baile"})

# Condiciones del estado (no actividades) que impiden empezar algo.
BLOQUEOS: Dict[str, Tuple[str, ...]] = {
    "salvapantallas": ("arrastrando", "menu_abierto", "hablando", "llamada"),
}

# Actividad → (campo del estado, valor al empezar si no se da otro)
_CAMPO_ACTIVIDAD: Dict[str, Tuple[str, Any]] = {
    "juego": ("juego", True),
    "alarma": ("alarma", True),
    "grande": ("grande", True),
    "salvapantallas": ("salvapantallas", True),
    "mmd": ("bailando", BAILE_MMD),
    "sentada": ("sentada", SENTADA_BARRA),
    "comida": ("comiendo", True),
    "baile": ("bailando", BAILE_MUSICA),
}


def _comprobar_actividad(actividad: str) -> None:
    if actividad not in PRIORIDAD:
        raise ValueError(f"actividad desconocida: {actividad!r} (válidas: {', '.join(ACTIVIDADES)})")


def esta_activa(actividad: str, estado: EstadoMascota) -> bool:
    """¿Está `actividad` en marcha según `estado`? `idle` nunca cuenta como activa."""
    _comprobar_actividad(actividad)
    if actividad == "idle":
        return False
    campo, _ = _CAMPO_ACTIVIDAD[actividad]
    valor = getattr(estado, campo)
    if actividad == "mmd":
        return valor == BAILE_MMD
    if actividad == "baile":
        return bool(valor) and valor != BAILE_MMD
    return bool(valor)


def actividades_activas(estado: EstadoMascota) -> List[str]:
    """Las actividades en marcha, de la más a la menos prioritaria."""
    return [a for a in ACTIVIDADES if esta_activa(a, estado)]


def _coexisten(a: str, b: str) -> bool:
    return frozenset({a, b}) in COEXISTEN


def _bloqueo(actividad: str, estado: EstadoMascota) -> str:
    """Motivo por el que `actividad` no puede empezar, o "" si puede."""
    _comprobar_actividad(actividad)
    p = PRIORIDAD[actividad]
    for otra in actividades_activas(estado):
        if otra == actividad or _coexisten(otra, actividad):
            continue
        if PRIORIDAD[otra] >= p:
            return otra
    for campo in BLOQUEOS.get(actividad, ()):
        if getattr(estado, campo):
            return campo
    return ""


def puede(actividad: str, estado: EstadoMascota) -> bool:
    """¿Puede empezar `actividad` con este estado?

    No puede si hay otra activa de prioridad mayor o igual (salvo los pares de
    COEXISTEN) o si se da una condición de BLOQUEOS. Volver a pedir una que ya
    está activa se permite (p. ej. pasar de sentada en la barra a una ventana).
    """
    return not _bloqueo(actividad, estado)


def que_ceder(nueva: str, estado: EstadoMascota) -> List[str]:
    """Actividades activas que hay que interrumpir para que empiece `nueva`.

    De la más a la menos prioritaria. Lista vacía si no hay que interrumpir nada
    o si `nueva` no puede empezar (mírese antes `puede`).
    """
    if not puede(nueva, estado):
        return []
    p = PRIORIDAD[nueva]
    return [a for a in actividades_activas(estado)
            if a != nueva and not _coexisten(a, nueva) and PRIORIDAD[a] < p]


def _sin_actividad(estado: EstadoMascota, actividad: str) -> EstadoMascota:
    """`estado` con `actividad` apagada (solo si estaba activa)."""
    if actividad == "idle" or not esta_activa(actividad, estado):
        return estado
    campo, _ = _CAMPO_ACTIVIDAD[actividad]
    return dataclasses.replace(estado, **{campo: _CAMPOS[campo]})


def _con_actividad(estado: EstadoMascota, actividad: str, valor: Any = None) -> EstadoMascota:
    """`estado` tras empezar `actividad` como lo haría `iniciar_actividad`:
    apaga las que ceden y marca la nueva (sin comprobar si puede)."""
    for a in que_ceder(actividad, estado):
        estado = _sin_actividad(estado, a)
    if actividad == "idle":
        return estado
    campo, por_defecto = _CAMPO_ACTIVIDAD[actividad]
    v = por_defecto if valor is None or valor is True else valor
    return dataclasses.replace(estado, **{campo: BusEstado._normalizar(campo, v)})


@dataclass(frozen=True)
class Cesion:
    """Una actividad interrumpida (o que hay que reanudar).

    `valor` es lo que tenía su campo en el estado (p. ej. "barra" para
    `sentada`), para poder restaurarla igual. `por` es quién la interrumpió.
    """
    actividad: str
    valor: Any
    por: str
    reanudar: bool


@dataclass(frozen=True)
class Resultado:
    """Respuesta de `BusEstado.iniciar_actividad`. Es verdadero si se permitió.

    `ceder`: lo que el llamador tiene que deshacer físicamente (levantarla,
    parar el baile, soltar la comida...). `motivo`: si no se permitió, la
    actividad o condición que lo impide.
    """
    ok: bool
    ceder: Tuple[Cesion, ...] = ()
    motivo: str = ""

    def __bool__(self) -> bool:
        return self.ok


Suscriptor = Callable[[EstadoMascota, Dict[str, Tuple[Any, Any]]], None]


class BusEstado:
    """Fuente única y compartida entre hilos del estado de la mascota.

    - `actual()` → la foto actual (inmutable).
    - `actualizar(**campos)` → cambia campos; solo notifica si algo cambió.
    - `suscribir(fn)` → `fn(estado, cambios)` en cada cambio, con
      `cambios = {campo: (antes, después)}`. Devuelve la función para cancelar.
    - `iniciar_actividad` / `terminar_actividad` → la tabla de prioridades
      (`terminar_actividad` devuelve reanudaciones compatibles entre sí, de
      mayor a menor prioridad; `reanudar_despues` deja pendiente una que al
      final no pudo empezar).
    - `pensar(fuente, on)` → `pensando` con VARIAS fuentes a la vez (cortes 9/10):
      el chat de la ventana web o nativa («chat») y la mascota comentando la
      pantalla (que escribe `actualizar(pensando=…)`, la fuente PENSANDO_DIRECTO).
      `pensando` es True mientras alguna siga pensando: que una acabe no apaga la
      otra (Discord, el sueño, el salvapantallas y el bot de Minecraft lo leen).
    """

    def __init__(self, inicial: Optional[EstadoMascota] = None):
        self._lock = threading.RLock()
        self._estado = inicial if inicial is not None else EstadoMascota()
        self._subs: List[Suscriptor] = []
        self._cola: Deque[Tuple[EstadoMascota, Dict[str, Tuple[Any, Any]]]] = deque()
        self._notificando = False
        # actividad que interrumpió → cesiones pendientes de reanudar cuando acabe
        self._pendientes: Dict[str, List[Cesion]] = {}
        # Quién está pensando ahora (ver pensar()).
        self._pensando_fuentes: set = {PENSANDO_DIRECTO} if self._estado.pensando else set()

    # ── Lectura y suscripción ────────────────────────────────────────────────────
    def actual(self) -> EstadoMascota:
        with self._lock:
            return self._estado

    def suscribir(self, fn: Suscriptor) -> Callable[[], None]:
        """Llama a `fn(estado, cambios)` en cada cambio. Devuelve `cancelar()`."""
        with self._lock:
            self._subs.append(fn)

        def cancelar() -> None:
            with self._lock:
                try:
                    self._subs.remove(fn)
                except ValueError:
                    pass
        return cancelar

    # ── Escritura ────────────────────────────────────────────────────────────────
    def actualizar(self, **campos: Any) -> bool:
        """Cambia los campos dados. Devuelve True si algo cambió (y se notificó).

        Un campo desconocido es un error (TypeError): así una errata no pasa
        inadvertida. En los campos de texto, None o False equivalen a "".
        `pensando` escrito aquí es la fuente PENSANDO_DIRECTO de `pensar()`.
        """
        with self._lock:
            if "pensando" in campos:
                campos = dict(campos)
                campos["pensando"] = self._fuente_pensando_locked(PENSANDO_DIRECTO, campos["pensando"])
            hay = self._aplicar_locked(campos)
        if hay:
            self._vaciar()
        return hay

    def pensar(self, fuente: str, on: Any) -> bool:
        """`fuente` («chat»: la ventana esperando al modelo) empieza o deja de pensar.
        `pensando` queda True mientras alguna fuente siga. True si cambió."""
        with self._lock:
            hay = self._aplicar_locked({"pensando": self._fuente_pensando_locked(str(fuente or ""), on)})
        if hay:
            self._vaciar()
        return hay

    def _fuente_pensando_locked(self, fuente: str, on: Any) -> bool:
        if self._normalizar("pensando", on):
            self._pensando_fuentes.add(fuente)
        else:
            self._pensando_fuentes.discard(fuente)
        return bool(self._pensando_fuentes)

    def iniciar_actividad(self, nueva: str, valor: Any = None) -> Resultado:
        """Intenta empezar `nueva` según la tabla de prioridades, de forma atómica.

        Si se permite: marca `nueva` en el estado (con `valor`, p. ej. "ventana"
        para `sentada`), apaga las que ceden y devuelve sus Cesion para que el
        llamador las deshaga en la mascota. Las REANUDABLES se recuerdan y las
        devolverá `terminar_actividad(nueva)`. Si no se permite, no toca nada.
        """
        _comprobar_actividad(nueva)
        with self._lock:
            est = self._estado
            motivo = _bloqueo(nueva, est)
            if motivo:
                return Resultado(False, (), motivo)
            ceden = que_ceder(nueva, est)
            cesiones = []
            cambios: Dict[str, Any] = {}
            heredadas: List[Cesion] = []
            for a in ceden:
                campo, _ = _CAMPO_ACTIVIDAD[a]
                c = Cesion(a, getattr(est, campo), nueva, a in REANUDABLES)
                cesiones.append(c)
                # El campo de `bailando` lo comparten mmd y baile: se apaga una vez.
                cambios.setdefault(campo, _CAMPOS[campo])
                # Lo que tenía pendiente la que cede pasa a la nueva.
                heredadas.extend(self._pendientes.pop(a, []))
            if nueva != "idle":
                campo, por_defecto = _CAMPO_ACTIVIDAD[nueva]
                cambios[campo] = por_defecto if valor is None or valor is True else valor
            lista = self._pendientes.setdefault(nueva, [])
            for c in heredadas + [c for c in cesiones if c.reanudar]:
                if c.actividad != nueva:          # la que empieza ya no hay que reanudarla
                    self._anadir_pendiente(lista, Cesion(c.actividad, c.valor, nueva, True))
            if not lista:
                self._pendientes.pop(nueva, None)
            hay = self._aplicar_locked(cambios)
        if hay:
            self._vaciar()
        return Resultado(True, tuple(cesiones), "")

    def terminar_actividad(self, actividad: str) -> List[Cesion]:
        """Apaga `actividad` y devuelve lo que hay que reanudar ahora.

        Solo se devuelve lo que puede reanudarse con el estado de este momento.
        Lo que siga bloqueado por otra actividad pasa a esperar a esa otra (p. ej.
        si mientras estaba en pantalla grande empezó un juego, se volverá a
        sentar cuando acabe el juego). Lo que ya está activo otra vez se omite.

        Las pendientes se miran de la más a la menos prioritaria y cada una que
        se reanuda cuenta para las siguientes: lo devuelto es compatible entre
        sí. P. ej. sentada → mmd → pantalla grande: al acabar la grande vuelve
        el MMD y «sentada» pasa a esperar a que acabe el MMD (antes se devolvían
        las dos y se sentaba para levantarse en el acto).

        El llamador debe reanudarlo, en este orden, con
        `iniciar_actividad(c.actividad, c.valor)`.
        """
        _comprobar_actividad(actividad)
        with self._lock:
            est = _sin_actividad(self._estado, actividad)
            aplicar = self._diferencias(est)
            pendientes = sorted(self._pendientes.pop(actividad, []),
                                key=lambda c: -PRIORIDAD[c.actividad])      # estable: empates en su orden
            reanudar: List[Cesion] = []
            for c in pendientes:
                if esta_activa(c.actividad, est):
                    continue
                motivo = _bloqueo(c.actividad, est)
                if not motivo:
                    reanudar.append(c)
                    est = _con_actividad(est, c.actividad, c.valor)       # las siguientes lo ven
                elif motivo in PRIORIDAD:
                    self.reanudar_despues(c, motivo)
                # bloqueada por una condición (arrastrando…): se descarta
            hay = self._aplicar_locked(aplicar)
        if hay:
            self._vaciar()
        return reanudar

    def reanudar_despues(self, c: Cesion, por: str) -> bool:
        """Deja `c` pendiente de reanudarse cuando termine la actividad `por`.

        Para cuando un reanudar no pudo hacerse (p. ej. entre `terminar_actividad`
        e `iniciar_actividad` otro hilo empezó un juego). False si `por` no es
        una actividad (una condición como «arrastrando» no termina: se descarta)
        o si la cesión no es reanudable.
        """
        if por not in PRIORIDAD or por == "idle" or c.actividad not in REANUDABLES:
            return False
        with self._lock:
            lista = self._pendientes.setdefault(por, [])
            self._anadir_pendiente(lista, Cesion(c.actividad, c.valor, por, True))
        return True

    def olvidar_reanudar(self, actividad: Optional[str] = None) -> None:
        """Descarta reanudaciones pendientes: de `actividad` o todas si es None.

        P. ej. si durante la pantalla grande alguien pide «bájate», ya no hay que
        volver a sentarla: `olvidar_reanudar("sentada")`.
        """
        with self._lock:
            if actividad is None:
                self._pendientes.clear()
                return
            for clave in list(self._pendientes):
                lista = [c for c in self._pendientes[clave] if c.actividad != actividad]
                if lista:
                    self._pendientes[clave] = lista
                else:
                    del self._pendientes[clave]

    def pendientes(self) -> Dict[str, List[Cesion]]:
        """Copia de las reanudaciones pendientes, por actividad que las bloquea."""
        with self._lock:
            return {k: list(v) for k, v in self._pendientes.items()}

    # ── Internos ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _anadir_pendiente(lista: List[Cesion], c: Cesion) -> None:
        """Añade sin duplicar actividad (se queda la más antigua: su valor es el original)."""
        if all(x.actividad != c.actividad for x in lista):
            lista.append(c)

    def _diferencias(self, nuevo: EstadoMascota) -> Dict[str, Any]:
        return {n: getattr(nuevo, n) for n in _CAMPOS if getattr(nuevo, n) != getattr(self._estado, n)}

    @staticmethod
    def _normalizar(campo: str, valor: Any) -> Any:
        if campo not in _CAMPOS:
            raise TypeError(f"EstadoMascota no tiene el campo {campo!r}")
        if campo in _CAMPOS_TEXTO:
            if valor is None or valor is False:
                return ""
            if valor is True or not isinstance(valor, str):
                raise TypeError(f"{campo} espera texto, no {valor!r}")
            return valor
        return bool(valor)

    def _aplicar_locked(self, campos: Dict[str, Any]) -> bool:
        """Aplica `campos` (con el lock tomado) y encola la notificación. True si cambió."""
        normal = {c: self._normalizar(c, v) for c, v in campos.items()}
        antes = self._estado
        cambios = {c: (getattr(antes, c), v) for c, v in normal.items() if getattr(antes, c) != v}
        if not cambios:
            return False
        self._estado = dataclasses.replace(antes, **{c: d for c, (_, d) in cambios.items()})
        self._cola.append((self._estado, cambios))
        return True

    def _vaciar(self) -> None:
        """Entrega las notificaciones encoladas, en orden y fuera del lock.

        Solo un hilo reparte a la vez: si otro está repartiendo (o si un
        suscriptor cambió el estado desde dentro), su cambio lo entrega ese.
        """
        with self._lock:
            if self._notificando:
                return
            self._notificando = True
        try:
            while True:
                with self._lock:
                    if not self._cola:
                        self._notificando = False
                        return
                    estado, cambios = self._cola.popleft()
                    subs = list(self._subs)
                for fn in subs:
                    try:
                        fn(estado, cambios)
                    except Exception:
                        _log.exception("Error en un suscriptor del estado de la mascota")
        except BaseException:
            with self._lock:
                self._notificando = False
            raise
