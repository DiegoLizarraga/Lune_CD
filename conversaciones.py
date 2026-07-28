"""
conversaciones.py — Historial de chats en disco.

Hasta ahora la conversación se perdía al cerrar la app: memoria.json guarda
hechos sueltos sobre el usuario, pero no lo que se habló. Esto guarda cada
sesión completa en `chats/`, una por archivo, para poder reabrirlas.

Es deliberadamente aparte de memoria.py: la memoria es "lo que Lune sabe de ti"
y el historial es "lo que os dijisteis". Borrar uno no debería borrar el otro.

    from conversaciones import GestorConversaciones
    gestor = GestorConversaciones()
    gestor.nueva_sesion(proveedor="ollama", personaje="Lune")
    gestor.agregar("user", "hola")
    gestor.agregar("assistant", "¡Buenas!")
    for s in gestor.listar():          # metadatos, sin cargar los mensajes
        print(s["titulo"], s["mensajes"])
"""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

CHATS_DIR = Path(__file__).parent / "chats"


def _ahora() -> str:
    return datetime.now().isoformat()


def _titulo_desde(texto: str, largo: int = 48) -> str:
    """Título legible a partir del primer mensaje del usuario."""
    limpio = re.sub(r"\s+", " ", (texto or "").strip())
    if not limpio:
        return "Conversación sin título"
    return limpio[:largo] + ("…" if len(limpio) > largo else "")


class GestorConversaciones:
    def __init__(self, directorio: Path = CHATS_DIR, max_sesiones: int = 50):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_sesiones = max_sesiones
        self._sesion: Optional[dict] = None

    # ── Sesión actual ──────────────────────────────────────────────────────────

    @property
    def sesion_id(self) -> Optional[str]:
        return self._sesion["id"] if self._sesion else None

    def nueva_sesion(self, proveedor: str = "", personaje: str = "") -> dict:
        self._sesion = {
            "id": uuid.uuid4().hex[:12],
            "titulo": "",
            "creado": _ahora(),
            "actualizado": _ahora(),
            "proveedor": proveedor,
            "personaje": personaje,
            "mensajes": [],
        }
        return self._sesion

    def agregar(self, rol: str, contenido: str, adjuntos: Optional[list] = None,
                uso: Optional[dict] = None):
        """Añade un mensaje y persiste. `rol` es 'user' o 'assistant'."""
        if self._sesion is None:
            self.nueva_sesion()
        self._sesion["mensajes"].append({
            "rol": rol,
            "contenido": contenido,
            "hora": _ahora(),
            "adjuntos": [a.get("nombre", "") for a in (adjuntos or [])],
            "uso": uso or {},
        })
        if not self._sesion["titulo"] and rol == "user":
            self._sesion["titulo"] = _titulo_desde(contenido)
        self._sesion["actualizado"] = _ahora()
        self.guardar()

    def guardar(self):
        """
        Vuelca la sesión actual. Una sesión sin mensajes no se escribe: si no,
        abrir y cerrar la app dejaba un archivo vacío cada vez.
        """
        if not self._sesion or not self._sesion["mensajes"]:
            return
        try:
            self._ruta(self._sesion["id"]).write_text(
                json.dumps(self._sesion, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        self.podar()

    def mensajes_actuales(self) -> List[dict]:
        return self._sesion["mensajes"] if self._sesion else []

    # ── Listado y carga ────────────────────────────────────────────────────────

    def _ruta(self, sesion_id: str) -> Path:
        return self.dir / f"chat_{sesion_id}.json"

    def listar(self) -> List[dict]:
        """Metadatos de todas las sesiones, de la más reciente a la más vieja."""
        sesiones = []
        for archivo in self.dir.glob("chat_*.json"):
            try:
                d = json.loads(archivo.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sesiones.append({
                "id": d.get("id", archivo.stem.replace("chat_", "")),
                "titulo": d.get("titulo") or "Conversación sin título",
                "creado": d.get("creado", ""),
                "actualizado": d.get("actualizado", ""),
                "proveedor": d.get("proveedor", ""),
                "personaje": d.get("personaje", ""),
                "mensajes": len(d.get("mensajes", [])),
            })
        sesiones.sort(key=lambda s: s["actualizado"], reverse=True)
        return sesiones

    def cargar(self, sesion_id: str) -> Optional[dict]:
        ruta = self._ruta(sesion_id)
        if not ruta.exists():
            return None
        try:
            self._sesion = json.loads(ruta.read_text("utf-8"))
            return self._sesion
        except (json.JSONDecodeError, OSError):
            return None

    def ultima(self) -> Optional[dict]:
        sesiones = self.listar()
        return self.cargar(sesiones[0]["id"]) if sesiones else None

    def borrar(self, sesion_id: str) -> bool:
        try:
            self._ruta(sesion_id).unlink(missing_ok=True)
        except OSError:
            return False
        if self._sesion and self._sesion["id"] == sesion_id:
            self._sesion = None
        return True

    def borrar_todo(self) -> int:
        n = 0
        for archivo in list(self.dir.glob("chat_*.json")):
            try:
                archivo.unlink()
                n += 1
            except OSError:
                pass
        self._sesion = None
        return n

    def podar(self):
        """Se queda con las `max_sesiones` más recientes."""
        sesiones = self.listar()
        for vieja in sesiones[self.max_sesiones:]:
            self.borrar(vieja["id"])

    # ── Reconstrucción del contexto ────────────────────────────────────────────

    def como_historial(self, limite_turnos: int = 20) -> List[dict]:
        """
        Convierte la sesión al formato que esperan los proveedores, para poder
        retomar una conversación vieja con el modelo sabiendo de qué iba.
        """
        mensajes = self.mensajes_actuales()[-limite_turnos * 2:]
        return [{"role": m["rol"], "content": m["contenido"]} for m in mensajes]
