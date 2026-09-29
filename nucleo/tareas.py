"""
nucleo/tareas.py — La lista de tareas de Lune (estilo Microsoft To Do), sobre la memoria.

Qué es una tarea
----------------
No hay otro archivo: las tareas son los recuerdos de memoria.json con tipo "tarea" o
"recordatorio" (los que entran con «recuerda que tengo que…», «anota que…», el panel
«Tareas» de la ventana o /tareas de patata). `Tareas` trabaja SIEMPRE sobre el MISMO
`MemoriaManager` que ya tiene quien lo crea (la app, patata): dos instancias reescribirían
memoria.json entera cada una y se pisarían.

Campos nuevos del recuerdo, todos opcionales (el bot de Telegram y las versiones viejas
los ignoran):
    "hecha"     bool           marcada como hecha
    "hecha_en"  ISO-8601 | ""  cuándo se marcó
    "mi_dia"    "AAAA-MM-DD" | ""   el día en que se puso en «Mi día»; "" = se quitó a mano

Mi día
------
Una tarea está en Mi día de HOY si su "mi_dia" es la fecha de hoy. Sin el campo (la anotó
Lune desde el chat o Telegram, o es un recuerdo de antes de la 10.9) cuenta como en Mi día
solo el día en que se creó: lo que le dices a Lune hoy lo ves hoy, y un recuerdo viejo sin
campos es una tarea pendiente que NO está en Mi día. Al día siguiente sale en las
sugerencias («Ayer»), como en To Do.

API (la usan ui/puente_tareas.py, patata.py y el banco de respuestas):
    lista()                → [tarea]   tarea = {id, texto, lista ("Tareas"|"Recordatorios"),
                                        creada (ISO), hecha, hecha_en, en_mi_dia}
    mi_dia()               → {fecha, fecha_larga («martes, 29 de septiembre»), pendientes, hechas}
    sugerencias()          → {ayer, recientes, antes}
    estado()               → {mi_dia, sugerencias, contador}: todo de una sola lectura
    contador()             → {hoy: pendientes en Mi día, total: pendientes}
    pendientes()           → las pendientes, primero las de Mi día (para /tareas)
    agregar(texto, mi_dia=True, tipo="tarea") → tarea      (texto vacío → ValueError)
    completar(id, hecha=True) → tarea                       (id que no es tarea → KeyError)
    al_mi_dia(id, si=True) → tarea
    quitar(id)             → bool
    resumen_texto(max_items=8) → str   una frase en la voz de Lune (sin modelo)
Las fechas van en español sin depender del locale (como nucleo/respuestas.py).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

TIPOS_TAREA = ("tarea", "recordatorio")
LISTAS = {"tarea": "Tareas", "recordatorio": "Recordatorios"}
MAX_TEXTO = 200
DIAS_RECIENTES = 14          # «Agregado recientemente»: los últimos 14 días
MAX_RECIENTES = 8
MAX_ANTES = 20               # «Más antiguas»: lo que no cabe en las otras dos secciones

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fecha_larga(d: date) -> str:
    """date(2026, 9, 29) → «martes, 29 de septiembre» (sin locale)."""
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]}"


def limpiar_texto(texto: Any, maximo: int = MAX_TEXTO) -> str:
    """Una línea: sin caracteres de control ni marcas bidi, espacios juntos y ≤ `maximo`."""
    if texto is None:
        return ""
    s = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in str(texto))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:maximo].rstrip()


def _dia_de(valor: Any) -> Optional[date]:
    """«2026-09-29T08:00:00» o «2026-09-29» → date; lo demás, None."""
    if not isinstance(valor, str) or len(valor) < 10 or not _FECHA.match(valor[:10]):
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def es_tarea(r: Any) -> bool:
    return isinstance(r, dict) and r.get("tipo") in TIPOS_TAREA and isinstance(r.get("id"), str)


class Tareas:
    """Las tareas de `memoria` (un MemoriaManager). `ahora` es el reloj (inyectable en tests)."""

    def __init__(self, memoria, ahora: Callable[[], datetime] = datetime.now):
        self.memoria = memoria
        self._ahora = ahora

    # ── Lectura ────────────────────────────────────────────────────────────────
    def _hoy(self) -> date:
        return self._ahora().date()

    def sincronizar(self) -> bool:
        """memoria.json cambió en disco (patata, la otra ventana) → se recarga. True si recargó."""
        sync = getattr(self.memoria, "_sincronizar", None)
        if not callable(sync):
            return False
        try:
            return bool(sync())
        except Exception:
            return False

    def _crudas(self) -> List[dict]:
        """Las tareas de la memoria, la última añadida primero (así, con la misma fecha, la más
        nueva va delante: los sort de después son estables)."""
        self.sincronizar()
        return [r for r in reversed(self.memoria.get_todos_recuerdos() or []) if es_tarea(r)]

    @staticmethod
    def _en_mi_dia(r: dict, hoy: date) -> bool:
        md = r.get("mi_dia")
        if isinstance(md, str):
            return md == hoy.isoformat()          # "" = la quitaron de Mi día a mano
        return _dia_de(r.get("fecha")) == hoy     # sin el campo: solo el día en que se creó

    def _normalizar(self, r: dict, hoy: date) -> Dict[str, Any]:
        hecha = r.get("hecha") is True
        hecha_en = r.get("hecha_en") if isinstance(r.get("hecha_en"), str) else ""
        return {
            "id": r["id"],
            "texto": limpiar_texto(r.get("contenido")) or "(sin texto)",
            "lista": LISTAS.get(r.get("tipo"), "Tareas"),
            "creada": r.get("fecha") if isinstance(r.get("fecha"), str) else "",
            "hecha": hecha,
            "hecha_en": hecha_en if hecha else "",
            "en_mi_dia": self._en_mi_dia(r, hoy),
        }

    def lista(self) -> List[Dict[str, Any]]:
        """Todas las tareas normalizadas (las más nuevas primero)."""
        hoy = self._hoy()
        out = [self._normalizar(r, hoy) for r in self._crudas()]
        out.sort(key=lambda t: t["creada"], reverse=True)
        return out

    def _calcular(self, todas: List[Dict[str, Any]], crudas: Dict[str, dict], hoy: date) -> Dict[str, Any]:
        hoy_iso, ayer = hoy.isoformat(), hoy - timedelta(days=1)
        nuevas = lambda xs: sorted(xs, key=lambda t: t["creada"], reverse=True)  # noqa: E731
        pendientes_hoy = nuevas([t for t in todas if not t["hecha"] and t["en_mi_dia"]])
        hechas = sorted((t for t in todas if t["hecha"] and (t["en_mi_dia"] or t["hecha_en"][:10] == hoy_iso)),
                        key=lambda t: t["hecha_en"], reverse=True)
        fuera = nuevas([t for t in todas if not t["hecha"] and not t["en_mi_dia"]])
        de_ayer, recientes, antes = [], [], []
        desde = hoy - timedelta(days=DIAS_RECIENTES)
        for t in fuera:
            r = crudas.get(t["id"], {})
            creada = _dia_de(t["creada"])
            if r.get("mi_dia") == ayer.isoformat() or creada == ayer:
                de_ayer.append(t)
            elif creada is not None and creada >= desde and len(recientes) < MAX_RECIENTES:
                recientes.append(t)
            elif len(antes) < MAX_ANTES:
                antes.append(t)
        return {
            "mi_dia": {"fecha": hoy_iso, "fecha_larga": fecha_larga(hoy), "pendientes": pendientes_hoy, "hechas": hechas},
            "sugerencias": {"ayer": de_ayer, "recientes": recientes, "antes": antes},
            "contador": {"hoy": len(pendientes_hoy), "total": len(pendientes_hoy) + len(fuera)},
        }

    def estado(self) -> Dict[str, Any]:
        """{mi_dia, sugerencias, contador} de una sola lectura (lo que pide el panel)."""
        hoy = self._hoy()
        crudas = self._crudas()
        todas = [self._normalizar(r, hoy) for r in crudas]
        return self._calcular(todas, {r["id"]: r for r in crudas}, hoy)

    def mi_dia(self) -> Dict[str, Any]:
        """{fecha, fecha_larga, pendientes, hechas}: las pendientes de Mi día de hoy (las más nuevas
        primero) y las hechas de hoy (en Mi día o marcadas hoy; la última marcada primero)."""
        return self.estado()["mi_dia"]

    def sugerencias(self) -> Dict[str, Any]:
        """{ayer, recientes, antes}, solo pendientes que no están en Mi día de hoy:
        «Ayer» = estuvieron en Mi día ayer o se crearon ayer; «Agregado recientemente» = de los
        últimos 14 días (máx. 8, las más nuevas primero); «Más antiguas» = el resto (máx. 20)."""
        return self.estado()["sugerencias"]

    def contador(self) -> Dict[str, int]:
        return self.estado()["contador"]

    def pendientes(self) -> List[Dict[str, Any]]:
        """Todas las pendientes: primero las de Mi día y luego las demás (las más nuevas primero)."""
        todas = [t for t in self.lista() if not t["hecha"]]
        return [t for t in todas if t["en_mi_dia"]] + [t for t in todas if not t["en_mi_dia"]]

    def buscar(self, rid: str) -> Optional[Dict[str, Any]]:
        r = self._cruda(rid)
        return self._normalizar(r, self._hoy()) if r is not None else None

    def _cruda(self, rid: Any) -> Optional[dict]:
        if not isinstance(rid, str) or not rid:
            return None
        self.sincronizar()
        buscar = getattr(self.memoria, "buscar_recuerdo", None)
        r = buscar(rid) if callable(buscar) else next(
            (x for x in self.memoria.get_todos_recuerdos() if isinstance(x, dict) and x.get("id") == rid), None)
        return r if es_tarea(r) else None

    # ── Escritura ──────────────────────────────────────────────────────────────
    def agregar(self, texto: Any, mi_dia: bool = True, tipo: str = "tarea") -> Dict[str, Any]:
        """Anota una tarea (a Mi día de hoy si `mi_dia`). Texto limpio y ≤ 200 caracteres."""
        limpio = limpiar_texto(texto)
        if not limpio:
            raise ValueError("La tarea está vacía.")
        if tipo not in TIPOS_TAREA:
            raise ValueError(f"Tipo de tarea desconocido: {tipo}")
        ahora = self._ahora()
        self.sincronizar()
        rid = self.memoria.agregar_recuerdo(
            limpio, tipo, fecha=ahora.isoformat(), hecha=False, hecha_en="",
            mi_dia=ahora.date().isoformat() if mi_dia else "")
        t = self.buscar(rid)
        if t is None:                                  # no debería pasar
            raise KeyError(rid)
        return t

    def _actualizar(self, rid: Any, **campos) -> Dict[str, Any]:
        if self._cruda(rid) is None:
            raise KeyError(str(rid))
        r = self.memoria.actualizar_recuerdo(rid, **campos)
        if r is None:
            raise KeyError(str(rid))
        return self._normalizar(r, self._hoy())

    def completar(self, rid: Any, hecha: bool = True) -> Dict[str, Any]:
        """Marca (o desmarca) la tarea como hecha."""
        hecha = bool(hecha)
        return self._actualizar(rid, hecha=hecha, hecha_en=self._ahora().isoformat() if hecha else "")

    def al_mi_dia(self, rid: Any, si: bool = True) -> Dict[str, Any]:
        """La pone en Mi día de hoy (o la quita)."""
        return self._actualizar(rid, mi_dia=self._hoy().isoformat() if si else "")

    def quitar(self, rid: Any) -> bool:
        """Borra la tarea (solo tareas: un recuerdo de otro tipo no se toca). True si estaba."""
        if self._cruda(rid) is None:
            return False
        return self.memoria.quitar_recuerdo(rid) is not None

    # ── Voz de Lune ────────────────────────────────────────────────────────────
    def resumen_texto(self, max_items: int = 8) -> str:
        """«Tienes 3 tareas pendientes: · X · Y · Z. Las tienes a la vista en Menú → Tareas.»
        Primero las de Mi día. Sin pendientes: «No tienes tareas pendientes. ¡Día libre!»."""
        pend = self.pendientes()
        if not pend:
            return "No tienes tareas pendientes. ¡Día libre!"
        n = len(pend)
        max_items = max(1, int(max_items or 1))
        textos = [t["texto"].rstrip(" .") or t["texto"] for t in pend[:max_items]]
        lista = " ".join(f"· {x}" for x in textos)
        if n > max_items:
            lista += f" … y {n - max_items} más"
        cabeza = "Tienes 1 tarea pendiente" if n == 1 else f"Tienes {n} tareas pendientes"
        return f"{cabeza}: {lista}. Las tienes a la vista en Menú → Tareas."


def disponible(memoria: Any) -> bool:
    """¿`memoria` sirve para Tareas? (un MemoriaManager de la 10.9; no un doble ni MemoriaRemota)."""
    return all(callable(getattr(memoria, n, None)) for n in
               ("get_todos_recuerdos", "agregar_recuerdo", "actualizar_recuerdo", "quitar_recuerdo"))


def resumen_de(memoria: Any) -> Optional[str]:
    """Para el banco de respuestas («qué tareas tengo», sin modelo): el resumen de las
    tareas de ESA memoria (con MemoriaRemota, su respaldo local, como el panel) o None si
    no sirve: entonces la pregunta sigue hacia la IA."""
    mem = getattr(memoria, "respaldo", None) or memoria
    if not disponible(mem):
        return None
    try:
        return Tareas(mem).resumen_texto()
    except Exception:
        return None


__all__ = ("Tareas", "disponible", "resumen_de", "fecha_larga", "limpiar_texto", "es_tarea", "TIPOS_TAREA", "LISTAS",
           "MAX_TEXTO", "DIAS_RECIENTES", "MAX_RECIENTES", "MAX_ANTES")
