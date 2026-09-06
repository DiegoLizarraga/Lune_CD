"""
lune_core/herramientas.py — Política, aprobación y auditoría de acciones.

Portado del modelo de services/computer-use-mcp de AIRI (policy.ts, session.ts,
types.ts, tool-descriptors), NO de su ejecutor (que es solo macOS). La idea: que
un modelo local pequeño pueda actuar en el PC sin que un descuido —o una
inyección— haga algo peligroso.

Piezas:
  · Descriptor  — metadatos obligatorios de cada herramienta (fail-closed): si
    una herramienta no está registrada con descriptor, no se ejecuta.
  · Política    — decide permitir / pedir aprobación / denegar según el
    descriptor, una lista de denegación y un presupuesto por sesión.
  · Sesión      — cola de acciones pendientes de aprobación, presupuesto gastado
    y registro de auditoría (audit.jsonl). La aprobación la da un HUMANO, nunca
    el modelo (fallo de AIRI: en su modo 'actions' el LLM podía aprobarse solo).

Este módulo decide y registra; ejecutar la acción aprobada es cosa de tools.py.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional


class Riesgo(str, Enum):
    LECTURA = "lectura"        # observar, no cambia nada → sin aprobación
    ESCRITURA = "escritura"    # cambia algo reversible → aprobación
    DESTRUCTIVO = "destructivo"  # difícil de deshacer → aprobación + aviso fuerte


@dataclass
class Descriptor:
    """Metadatos de una herramienta. Sin esto, la herramienta no se ejecuta."""
    nombre: str
    descripcion: str
    riesgo: Riesgo = Riesgo.ESCRITURA
    requiere_aprobacion: bool = True
    # coste en "unidades de presupuesto" (frena bucles agénticos)
    coste: int = 1

    @property
    def solo_lectura(self) -> bool:
        return self.riesgo == Riesgo.LECTURA


class Decision(str, Enum):
    PERMITIR = "permitir"          # ejecutar ya
    REQUIERE_APROBACION = "aprobacion"
    DENEGAR = "denegar"


@dataclass
class Veredicto:
    decision: Decision
    motivo: str
    riesgo: Riesgo
    # texto listo para enseñar al humano: qué, por qué, riesgo
    resumen: str = ""


# ── Registro de herramientas (fail-closed) ──────────────────────────────────────

class Registro:
    def __init__(self):
        self._d: Dict[str, Descriptor] = {}

    def registrar(self, desc: Descriptor):
        self._d[desc.nombre] = desc

    def get(self, nombre: str) -> Optional[Descriptor]:
        return self._d.get(nombre)

    def nombres(self) -> List[str]:
        return sorted(self._d)

    def esquema_para_prompt(self) -> str:
        """Lista de herramientas para el system prompt (nombre + qué hacen)."""
        lineas = []
        for n in self.nombres():
            d = self._d[n]
            marca = "" if d.solo_lectura else " (pide confirmación)"
            lineas.append(f"- {n}: {d.descripcion}{marca}")
        return "\n".join(lineas)


# ── Política ────────────────────────────────────────────────────────────────────

# Nombres de app/proceso que NUNCA se tocan, aunque el modelo insista.
DENY_APPS = {
    "1password", "bitwarden", "keepass", "lastpass", "keychain",
    "credential", "administrador de credenciales", "cmd", "powershell",
    "regedit", "configuracion", "settings", "lune", "lune cd",
}

# Combinaciones de teclas prohibidas (normalizadas).
DENY_TECLAS = {"alt+f4", "ctrl+alt+supr", "ctrl+alt+del", "win+r", "win+l"}


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


class Politica:
    def __init__(self, deny_apps: Optional[set] = None):
        self.deny_apps = {_normalizar(a) for a in (deny_apps or DENY_APPS)}

    def evaluar(self, desc: Optional[Descriptor], args: dict) -> Veredicto:
        # 1) fail-closed: sin descriptor, no se ejecuta
        if desc is None:
            return Veredicto(Decision.DENEGAR, "herramienta no registrada",
                             Riesgo.DESTRUCTIVO, "Acción desconocida: denegada.")

        # 2) deny-list de apps (para lanzar/enfocar/cerrar apps)
        objetivo = _normalizar(str(args.get("app") or args.get("nombre") or ""))
        if objetivo and any(bloq in objetivo for bloq in self.deny_apps):
            return Veredicto(Decision.DENEGAR, f"«{objetivo}» está en la lista de denegación",
                             desc.riesgo, f"No toco «{objetivo}»: es sensible.")

        # 3) teclas prohibidas
        teclas = _normalizar(str(args.get("teclas") or args.get("keys") or "")).replace(" ", "")
        if teclas and teclas in DENY_TECLAS:
            return Veredicto(Decision.DENEGAR, f"combinación prohibida: {teclas}",
                             Riesgo.DESTRUCTIVO, f"No envío «{teclas}».")

        # 4) por el descriptor. La bandera `requiere_aprobacion` es la puerta,
        #    PERO lo destructivo siempre pide aprobación, aunque la bandera diga
        #    que no (defensa contra un descriptor mal puesto).
        if not desc.requiere_aprobacion and desc.riesgo != Riesgo.DESTRUCTIVO:
            nota = "solo observa" if desc.solo_lectura else "sin riesgo alto"
            return Veredicto(Decision.PERMITIR, "no requiere aprobación", desc.riesgo,
                             f"{desc.descripcion} ({nota}).")
        aviso = "Acción DESTRUCTIVA" if desc.riesgo == Riesgo.DESTRUCTIVO else "Acción"
        return Veredicto(Decision.REQUIERE_APROBACION,
                         "requiere aprobación por su nivel de riesgo", desc.riesgo,
                         f"{aviso}: {desc.descripcion}. ¿La autorizas?")


# ── Sesión: pendientes, presupuesto y auditoría ─────────────────────────────────

@dataclass
class Pendiente:
    id: str
    herramienta: str
    args: dict
    veredicto: dict
    creado: float


class Sesion:
    """
    Una sesión agéntica con presupuesto y auditoría. Encola lo que requiere
    aprobación; el humano la concede con `aprobar()`. Todo queda en audit.jsonl.
    """

    def __init__(self, registro: Registro, politica: Optional[Politica] = None,
                 *, presupuesto: int = 20, audit_path: Optional[Path] = None,
                 reloj: Callable[[], float] = time.time):
        self.registro = registro
        self.politica = politica or Politica()
        self.presupuesto = presupuesto
        self.gastado = 0
        self.audit_path = Path(audit_path) if audit_path else None
        self._reloj = reloj
        self.pendientes: Dict[str, Pendiente] = {}

    # ── Auditoría ──
    def _auditar(self, evento: str, **datos):
        entrada = {"at": self._reloj(), "evento": evento, **datos}
        if self.audit_path:
            try:
                self.audit_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.audit_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return entrada

    # ── Solicitud ──
    def solicitar(self, herramienta: str, args: Optional[dict] = None) -> dict:
        """
        Evalúa una acción. Devuelve un dict con el estado:
          {estado: 'permitida'|'aprobacion_requerida'|'denegada'|'sin_presupuesto',
           veredicto, pendiente_id?}
        """
        args = dict(args or {})
        desc = self.registro.get(herramienta)
        veredicto = self.politica.evaluar(desc, args)
        self._auditar("solicitud", herramienta=herramienta, args=args,
                      decision=veredicto.decision.value, motivo=veredicto.motivo)

        if veredicto.decision == Decision.DENEGAR:
            return {"estado": "denegada", "veredicto": asdict_veredicto(veredicto)}

        coste = desc.coste if desc else 1
        if self.gastado + coste > self.presupuesto:
            self._auditar("sin_presupuesto", herramienta=herramienta,
                          gastado=self.gastado, presupuesto=self.presupuesto)
            return {"estado": "sin_presupuesto",
                    "veredicto": asdict_veredicto(veredicto),
                    "detalle": f"presupuesto agotado ({self.gastado}/{self.presupuesto})"}

        if veredicto.decision == Decision.PERMITIR:
            self.gastado += coste
            self._auditar("permitida", herramienta=herramienta)
            return {"estado": "permitida", "veredicto": asdict_veredicto(veredicto)}

        # aprobación requerida → a la cola
        pid = uuid.uuid4().hex[:12]
        self.pendientes[pid] = Pendiente(pid, herramienta, args,
                                         asdict_veredicto(veredicto), self._reloj())
        self._auditar("encolada", herramienta=herramienta, pendiente_id=pid)
        return {"estado": "aprobacion_requerida", "pendiente_id": pid,
                "veredicto": asdict_veredicto(veredicto)}

    # ── Aprobación (humana) ──
    def aprobar(self, pendiente_id: str) -> dict:
        p = self.pendientes.pop(pendiente_id, None)
        if p is None:
            return {"ok": False, "motivo": "no hay una acción pendiente con ese id"}
        desc = self.registro.get(p.herramienta)
        coste = desc.coste if desc else 1
        if self.gastado + coste > self.presupuesto:
            self._auditar("aprobada_sin_presupuesto", pendiente_id=pendiente_id)
            return {"ok": False, "motivo": "presupuesto agotado"}
        self.gastado += coste
        self._auditar("aprobada", herramienta=p.herramienta, pendiente_id=pendiente_id)
        return {"ok": True, "herramienta": p.herramienta, "args": p.args}

    def rechazar(self, pendiente_id: str, motivo: str = "") -> dict:
        p = self.pendientes.pop(pendiente_id, None)
        if p is None:
            return {"ok": False, "motivo": "no hay una acción pendiente con ese id"}
        self._auditar("rechazada", herramienta=p.herramienta,
                      pendiente_id=pendiente_id, motivo=motivo)
        return {"ok": True}

    def listar_pendientes(self) -> List[dict]:
        return [asdict(p) for p in self.pendientes.values()]

    def registrar_resultado(self, herramienta: str, ok: bool, detalle: str = ""):
        self._auditar("resultado", herramienta=herramienta, ok=ok, detalle=detalle[:500])


def asdict_veredicto(v: Veredicto) -> dict:
    return {"decision": v.decision.value, "motivo": v.motivo,
            "riesgo": v.riesgo.value, "resumen": v.resumen}


# ── Registro por defecto con las herramientas actuales de Lune ─────────────────

def registro_por_defecto() -> Registro:
    r = Registro()
    r.registrar(Descriptor("sistema_info", "Ver estado de CPU y RAM",
                           Riesgo.LECTURA, requiere_aprobacion=False, coste=0))
    r.registrar(Descriptor("buscar_web", "Buscar en Google o YouTube",
                           Riesgo.ESCRITURA, requiere_aprobacion=False, coste=1))
    r.registrar(Descriptor("abrir_url", "Abrir una página web",
                           Riesgo.ESCRITURA, requiere_aprobacion=False, coste=1))
    r.registrar(Descriptor("lanzar_app", "Abrir una aplicación del equipo",
                           Riesgo.ESCRITURA, requiere_aprobacion=True, coste=1))
    return r
