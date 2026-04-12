"""
memoria.py — Sistema de memoria personal persistente para Lune CD
================================================================
Guarda y recupera información sobre el usuario entre sesiones.

Estructura de memoria.json:
{
  "usuario": {
    "nombre": "...",
    "preferencias": [...],
    "contexto": "..."
  },
  "recuerdos": [
    {
      "id": "uuid",
      "fecha": "ISO-8601",
      "tipo": "hecho|preferencia|recordatorio|tarea",
      "contenido": "...",
      "tags": [...]
    }
  ],
  "resumen_sesion_anterior": "...",
  "estadisticas": {
    "total_mensajes": 0,
    "primera_sesion": "ISO-8601",
    "ultima_sesion": "ISO-8601"
  }
}

Uso desde main.py:
    from memoria import MemoriaManager
    memoria = MemoriaManager()

    # Al inicio de sesión — obtener contexto para el system prompt
    contexto = memoria.obtener_contexto_para_prompt()

    # Tras cada respuesta — detectar y guardar automáticamente
    memoria.procesar_respuesta(mensaje_usuario, respuesta_lune)

    # Al cerrar la app
    memoria.cerrar_sesion(resumen_conversacion)

Comandos del usuario detectados automáticamente:
    "recuerda que...", "anota que...", "no olvides que..."
    "/memoria", "/recuerdos"
    "/olvida [id]", "/olvida todo"
"""

import json
import uuid
import re
from pathlib import Path
from datetime import datetime, date
from typing import Optional


MEMORIA_PATH = Path(__file__).parent / "memoria.json"

TIPOS_RECUERDO = {
    "hecho":        "📌",
    "preferencia":  "❤️",
    "recordatorio": "⏰",
    "tarea":        "✅",
    "general":      "🧠",
}

# Palabras clave para detectar intención de guardar en la conversación
KEYWORDS_GUARDAR = [
    r"recuerda que (.+)",
    r"anota que (.+)",
    r"no olvides que (.+)",
    r"guarda que (.+)",
    r"tengo (.+) años",
    r"me llamo (.+)",
    r"mi nombre es (.+)",
    r"trabajo (?:en|como) (.+)",
    r"vivo en (.+)",
    r"prefiero (.+)",
    r"no me gusta(.+)",
    r"me gusta(.+)",
]

# Palabras clave que indican recordatorio/tarea
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

class MemoriaManager:
    """Gestor de memoria personal persistente entre sesiones."""

    def __init__(self, path: Path = MEMORIA_PATH):
        self.path = path
        self._data = self._cargar()
        self._mensajes_sesion: int = 0
        self._recuerdos_nuevos_sesion: list[str] = []
        self._registrar_inicio_sesion()

    # ── Carga / guardado ─────────────────────────────────────────────────────

    def _cargar(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text("utf-8"))
            except Exception:
                pass
        return self._estructura_vacia()

    def _guardar(self):
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _estructura_vacia(self) -> dict:
        ahora = datetime.now().isoformat()
        return {
            "usuario": {
                "nombre": None,
                "preferencias": [],
                "contexto": "",
            },
            "recuerdos": [],
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
        Resume lo que Lune sabe del usuario sin saturar el contexto.
        """
        partes = []
        usuario = self._data.get("usuario", {})

        if nombre := usuario.get("nombre"):
            partes.append(f"El usuario se llama {nombre}.")

        recuerdos = self._data.get("recuerdos", [])
        if recuerdos:
            # Últimos 15 recuerdos ordenados por fecha desc
            recientes = sorted(recuerdos, key=lambda r: r["fecha"], reverse=True)[:15]
            lineas = []
            for r in recientes:
                emoji = TIPOS_RECUERDO.get(r.get("tipo", "general"), "🧠")
                fecha_corta = r["fecha"][:10]
                lineas.append(f"  {emoji} [{fecha_corta}] {r['contenido']}")
            partes.append("Lo que sé sobre el usuario:\n" + "\n".join(lineas))

        resumen = self._data.get("resumen_sesion_anterior", "")
        if resumen:
            partes.append(f"Resumen de la última sesión: {resumen}")

        stats = self._data.get("estadisticas", {})
        total = stats.get("total_mensajes", 0)
        if total > 0:
            partes.append(f"Llevamos {total} mensajes intercambiados en total.")

        if not partes:
            return ""

        return (
            "\n\n--- MEMORIA PERSONAL ---\n"
            + "\n".join(partes)
            + "\n--- FIN MEMORIA ---\n"
        )

    def procesar_mensaje_usuario(self, mensaje: str) -> Optional[str]:
        """
        Analiza el mensaje del usuario en busca de:
        - Comandos explícitos (/memoria, /recuerda, /olvida)
        - Intención implícita de guardar algo

        Devuelve una respuesta de confirmación si procesó algo,
        o None si el mensaje es una conversación normal.
        """
        self._mensajes_sesion += 1
        self._data["estadisticas"]["total_mensajes"] = (
            self._data["estadisticas"].get("total_mensajes", 0) + 1
        )

        msg_lower = mensaje.lower().strip()

        # ── Comandos explícitos ───────────────────────────────────────────────

        # /memoria o /recuerdos — mostrar todo
        if re.match(r"^/?(memoria|recuerdos)$", msg_lower):
            return self._cmd_listar()

        # /olvida todo
        if re.match(r"^/?olvida\s+todo$", msg_lower):
            return self._cmd_olvida_todo()

        # /olvida <id_o_fragmento>
        m = re.match(r"^/?olvida\s+(.+)$", msg_lower)
        if m:
            return self._cmd_olvida(m.group(1).strip())

        # "recuerda que...", "anota que...", etc.
        for patron in KEYWORDS_GUARDAR:
            m = re.search(patron, msg_lower)
            if m:
                contenido = m.group(1).strip().rstrip(".")
                # Detectar nombre propio
                if "llamo" in patron or "nombre" in patron:
                    nombre = contenido.strip().split()[0].capitalize()
                    self._data["usuario"]["nombre"] = nombre
                tipo = self._detectar_tipo(contenido)
                rid = self.agregar_recuerdo(contenido, tipo)
                self._guardar()
                emoji = TIPOS_RECUERDO.get(tipo, "🧠")
                return f"{emoji} Anotado: *{contenido}*"

        return None  # conversación normal

    def procesar_respuesta_lune(self, respuesta: str):
        """
        Extrae hechos implícitos de la respuesta de Lune
        (p.ej. si Lune confirma algo, lo guarda como hecho).
        Llamar después de recibir cada respuesta completa.
        """
        self._guardar()

    def agregar_recuerdo(
        self,
        contenido: str,
        tipo: str = "general",
        tags: Optional[list] = None,
    ) -> str:
        """Agrega un recuerdo manualmente. Devuelve su ID."""
        rid = str(uuid.uuid4())[:8]
        recuerdo = {
            "id": rid,
            "fecha": datetime.now().isoformat(),
            "tipo": tipo,
            "contenido": contenido,
            "tags": tags or [],
        }
        self._data["recuerdos"].append(recuerdo)
        self._recuerdos_nuevos_sesion.append(rid)
        self._guardar()
        return rid

    def cerrar_sesion(self, resumen: str = ""):
        """
        Llama esto al cerrar la app.
        Guarda el resumen de la sesión actual como contexto para la próxima.
        """
        if resumen:
            self._data["resumen_sesion_anterior"] = resumen[:500]
        self._data["estadisticas"]["ultima_sesion"] = datetime.now().isoformat()
        self._guardar()

    def get_nombre_usuario(self) -> Optional[str]:
        return self._data.get("usuario", {}).get("nombre")

    def get_todos_recuerdos(self) -> list:
        return self._data.get("recuerdos", [])

    def get_stats(self) -> dict:
        return self._data.get("estadisticas", {})

    # ── Comandos internos ─────────────────────────────────────────────────────

    def _cmd_listar(self) -> str:
        recuerdos = self._data.get("recuerdos", [])
        if not recuerdos:
            return "📭 No tengo nada guardado todavía. Dime *'recuerda que...'* para empezar."

        usuario = self._data.get("usuario", {})
        lineas = ["🧠 **Lo que sé sobre ti:**\n"]

        if nombre := usuario.get("nombre"):
            lineas.append(f"👤 Nombre: {nombre}")

        por_tipo: dict[str, list] = {}
        for r in sorted(recuerdos, key=lambda x: x["fecha"], reverse=True):
            t = r.get("tipo", "general")
            por_tipo.setdefault(t, []).append(r)

        for tipo, items in por_tipo.items():
            emoji = TIPOS_RECUERDO.get(tipo, "🧠")
            lineas.append(f"\n{emoji} **{tipo.capitalize()}:**")
            for r in items[:10]:
                fecha = r["fecha"][:10]
                lineas.append(f"  `{r['id']}` [{fecha}] {r['contenido']}")

        stats = self._data.get("estadisticas", {})
        lineas.append(f"\n📊 Total de mensajes: {stats.get('total_mensajes', 0)}")
        lineas.append("*Usa /olvida [id] para borrar un recuerdo.*")
        return "\n".join(lineas)

    def _cmd_olvida(self, fragmento: str) -> str:
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
            return f"❌ No encontré ningún recuerdo con *'{fragmento}'*. Usa /memoria para ver los IDs."

        borrado = recuerdos.pop(idx)
        self._guardar()
        return f"🗑 Olvidado: *{borrado['contenido']}*"

    def _cmd_olvida_todo(self) -> str:
        n = len(self._data.get("recuerdos", []))
        self._data["recuerdos"] = []
        self._data["usuario"]["nombre"] = None
        self._data["resumen_sesion_anterior"] = ""
        self._guardar()
        return f"🗑 Memoria borrada. Eliminé {n} recuerdos. Empezamos de cero."

    def _detectar_tipo(self, texto: str) -> str:
        texto_l = texto.lower()
        if any(k in texto_l for k in KEYWORDS_RECORDATORIO):
            return "recordatorio"
        if any(k in texto_l for k in KEYWORDS_TAREA):
            return "tarea"
        if any(k in texto_l for k in KEYWORDS_PREFERENCIA):
            return "preferencia"
        return "hecho"
