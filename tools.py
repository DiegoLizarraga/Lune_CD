"""
tools.py — Sistema de herramientas de escritorio para Lune CD
=============================================================
Permite a Lune ejecutar acciones reales en el PC del usuario.

Las herramientas se detectan de dos formas:
  1. Comando explícito del usuario ("abre YouTube", "toma una captura")
  2. Prefijo especial en la respuesta de la IA: TOOL:<nombre>:<args>

Herramientas disponibles:
  abrir_url       Abre una URL en el navegador predeterminado
  buscar_web      Busca en DuckDuckGo y abre el resultado
  abrir_archivo   Abre un archivo o carpeta con la app por defecto
  captura         Toma una captura de pantalla y la guarda
  volumen         Sube/baja/silencia el volumen del sistema
  escribir_texto  Escribe texto en el campo de texto activo (pyautogui)
  lanzar_app      Lanza una aplicación instalada
  portapapeles    Copia texto al portapapeles
  sistema_info    Devuelve CPU, RAM y disco como texto
  listar_archivos Lista archivos de una carpeta

Uso desde main.py:
    from tools import ToolManager
    tools = ToolManager()

    # Detectar si el usuario pide una herramienta
    resultado = tools.detectar_y_ejecutar(mensaje_usuario)
    if resultado:
        # mostrar resultado en el chat como burbuja especial
        ...

    # Parsear prefijos TOOL: en respuesta de la IA
    respuesta_limpia, acciones = tools.parsear_respuesta_ia(respuesta_cruda)
    for accion in acciones:
        tools.ejecutar(**accion)
"""

import os
import re
import subprocess
import platform
import webbrowser
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional


# ─── Dependencias opcionales ──────────────────────────────────────────────────
try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_OS = platform.system()   # "Windows", "Darwin", "Linux"

# Carpeta donde se guardan las capturas
CAPTURAS_DIR = Path(__file__).parent / "capturas"
CAPTURAS_DIR.mkdir(exist_ok=True)


# ─── Mapa de intenciones del usuario → herramienta ───────────────────────────
# Orden importa: más específico primero
INTENT_MAP = [
    # Capturas
    (r"(?:toma|haz|saca)\s+(?:una\s+)?captura", "captura", {}),
    (r"screenshot", "captura", {}),

    # Volumen
    (r"sube\s+(?:el\s+)?volumen", "volumen", {"accion": "subir"}),
    (r"baja\s+(?:el\s+)?volumen", "volumen", {"accion": "bajar"}),
    (r"silencia(?:r)?", "volumen", {"accion": "silenciar"}),
    (r"(?:quita|sin)\s+(?:el\s+)?sonido", "volumen", {"accion": "silenciar"}),

    # Portapapeles
    (r"copia\s+(?:al\s+portapapeles\s+)?[\"\'«»](.+)[\"\'«»]", "portapapeles", None),

    # Sistema
    (r"(?:info|estado)\s+(?:del\s+)?sistema", "sistema_info", {}),
    (r"(?:cuánta|cuanta)\s+(?:ram|memoria)", "sistema_info", {}),
    (r"(?:cuánto|cuanto)\s+(?:cpu|procesador)", "sistema_info", {}),

    # Abrir URL
    (r"abre?\s+(?:el\s+)?(?:navegador\s+en\s+|la\s+página\s+de\s+)?(https?://\S+)", "abrir_url", None),
    (r"ve\s+a\s+(https?://\S+)", "abrir_url", None),
    (r"abre?\s+youtube", "abrir_url", {"url": "https://youtube.com"}),
    (r"abre?\s+github", "abrir_url", {"url": "https://github.com"}),
    (r"abre?\s+spotify", "abrir_url", {"url": "https://open.spotify.com"}),
    (r"abre?\s+gmail", "abrir_url", {"url": "https://mail.google.com"}),
    (r"abre?\s+twitter|abre?\s+x\.com", "abrir_url", {"url": "https://x.com"}),

    # Búsqueda web
    (r"busca\s+(?:en\s+(?:google|internet|la\s+web)\s+)?(?:sobre\s+)?(.+)", "buscar_web", None),
    (r"investiga\s+(?:sobre\s+)?(.+)", "buscar_web", None),
    (r"qué\s+es\s+(.+)", "buscar_web", None),

    # Listar archivos
    (r"(?:lista|muestra|ver)\s+(?:los\s+)?(?:archivos|carpeta)(?:\s+de\s+(.+))?", "listar_archivos", None),

    # Abrir archivo o carpeta
    (r"abre?\s+(?:el\s+archivo|la\s+carpeta|el\s+folder)\s+(.+)", "abrir_archivo", None),
    (r"abre?\s+(.+\.(?:pdf|docx?|xlsx?|txt|mp3|mp4|png|jpg|zip))", "abrir_archivo", None),
]


# ─────────────────────────────────────────────────────────────────────────────

class ToolResult:
    """Resultado de ejecutar una herramienta."""
    def __init__(self, ok: bool, mensaje: str, datos: dict = None):
        self.ok = ok
        self.mensaje = mensaje
        self.datos = datos or {}

    def __str__(self):
        return self.mensaje


class ToolManager:
    """Gestor central de herramientas de escritorio."""

    def __init__(self):
        self._disponibles = self._detectar_disponibles()

    def _detectar_disponibles(self) -> set[str]:
        disponibles = {
            "abrir_url", "buscar_web", "sistema_info", "listar_archivos",
        }
        if _PYAUTOGUI:
            disponibles |= {"captura", "escribir_texto", "volumen"}
        if _PYPERCLIP or _OS == "Windows":
            disponibles.add("portapapeles")
        disponibles.add("abrir_archivo")
        disponibles.add("lanzar_app")
        return disponibles

    # ── Detección de intención ────────────────────────────────────────────────

    def detectar_y_ejecutar(self, mensaje: str) -> Optional[ToolResult]:
        """
        Analiza el mensaje del usuario y ejecuta la herramienta si detecta
        una intención clara. Devuelve None si es conversación normal.
        """
        msg_lower = mensaje.lower().strip()

        for patron, herramienta, args_fijos in INTENT_MAP:
            m = re.search(patron, msg_lower)
            if not m:
                continue

            if herramienta not in self._disponibles:
                return ToolResult(
                    False,
                    f"⚠️ La herramienta *{herramienta}* no está disponible en este sistema."
                )

            # Construir argumentos
            if args_fijos is None:
                # El argumento viene del grupo capturado
                arg = m.group(1).strip() if m.lastindex else ""
                kwargs = self._arg_para_herramienta(herramienta, arg)
            else:
                kwargs = dict(args_fijos)

            return self.ejecutar(herramienta, **kwargs)

        return None

    def _arg_para_herramienta(self, herramienta: str, arg: str) -> dict:
        mapping = {
            "abrir_url":     {"url": arg},
            "buscar_web":    {"query": arg},
            "abrir_archivo": {"ruta": arg},
            "lanzar_app":    {"nombre": arg},
            "portapapeles":  {"texto": arg},
            "listar_archivos": {"carpeta": arg or "."},
            "escribir_texto":  {"texto": arg},
        }
        return mapping.get(herramienta, {})

    # ── Parseo de prefijos TOOL: en respuestas de la IA ──────────────────────

    def parsear_respuesta_ia(self, respuesta: str) -> tuple[str, list[dict]]:
        """
        Extrae comandos TOOL:<herramienta>:<arg> de la respuesta de la IA.
        Devuelve (respuesta_limpia, lista_de_acciones).

        Ejemplo en respuesta IA:
            "Claro, abro YouTube ahora mismo.
            TOOL:abrir_url:https://youtube.com"
        """
        acciones = []
        lineas_limpias = []

        for linea in respuesta.splitlines():
            m = re.match(r"TOOL:(\w+):?(.*)", linea.strip())
            if m:
                herramienta = m.group(1)
                arg = m.group(2).strip()
                kwargs = self._arg_para_herramienta(herramienta, arg)
                acciones.append({"herramienta": herramienta, **kwargs})
            else:
                lineas_limpias.append(linea)

        return "\n".join(lineas_limpias).strip(), acciones

    def ejecutar(self, herramienta: str, **kwargs) -> ToolResult:
        """Ejecuta una herramienta por nombre."""
        metodo = getattr(self, f"_tool_{herramienta}", None)
        if metodo is None:
            return ToolResult(False, f"❌ Herramienta desconocida: {herramienta}")
        try:
            return metodo(**kwargs)
        except Exception as e:
            return ToolResult(False, f"❌ Error en {herramienta}: {e}")

    # ── Herramientas ──────────────────────────────────────────────────────────

    def _tool_abrir_url(self, url: str = "") -> ToolResult:
        if not url:
            return ToolResult(False, "❌ No especificaste una URL.")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return ToolResult(True, f"🌐 Abriendo: {url}", {"url": url})

    def _tool_buscar_web(self, query: str = "") -> ToolResult:
        if not query:
            return ToolResult(False, "❌ No indicaste qué buscar.")
        encoded = urllib.parse.quote(query)
        url = f"https://duckduckgo.com/?q={encoded}"
        webbrowser.open(url)
        return ToolResult(True, f"🔍 Buscando en la web: *{query}*", {"query": query, "url": url})

    def _tool_captura(self, nombre: str = "") -> ToolResult:
        if not _PYAUTOGUI:
            return ToolResult(False, "❌ Instala pyautogui: pip install pyautogui")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo = CAPTURAS_DIR / f"captura_{ts}.png"
        import time; time.sleep(0.4)   # pequeño delay para que Lune no aparezca
        img = pyautogui.screenshot()
        img.save(str(archivo))
        return ToolResult(
            True,
            f"📸 Captura guardada en: `capturas/captura_{ts}.png`",
            {"ruta": str(archivo)},
        )

    def _tool_volumen(self, accion: str = "bajar") -> ToolResult:
        if _OS == "Windows":
            return self._volumen_windows(accion)
        elif _OS == "Darwin":
            return self._volumen_mac(accion)
        else:
            return self._volumen_linux(accion)

    def _volumen_windows(self, accion: str) -> ToolResult:
        if not _PYAUTOGUI:
            return ToolResult(False, "❌ Necesita pyautogui en Windows.")
        from pyautogui import hotkey, press
        if accion == "silenciar":
            press("volumemute")
            return ToolResult(True, "🔇 Volumen silenciado.")
        elif accion == "subir":
            for _ in range(5): press("volumeup")
            return ToolResult(True, "🔊 Volumen subido.")
        else:
            for _ in range(5): press("volumedown")
            return ToolResult(True, "🔉 Volumen bajado.")

    def _volumen_mac(self, accion: str) -> ToolResult:
        if accion == "silenciar":
            subprocess.run(["osascript", "-e", "set volume output muted true"])
            return ToolResult(True, "🔇 Volumen silenciado.")
        elif accion == "subir":
            subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 20)"])
            return ToolResult(True, "🔊 Volumen subido.")
        else:
            subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 20)"])
            return ToolResult(True, "🔉 Volumen bajado.")

    def _volumen_linux(self, accion: str) -> ToolResult:
        if accion == "silenciar":
            subprocess.run(["amixer", "-q", "set", "Master", "mute"])
            return ToolResult(True, "🔇 Volumen silenciado.")
        elif accion == "subir":
            subprocess.run(["amixer", "-q", "set", "Master", "20%+"])
            return ToolResult(True, "🔊 Volumen subido.")
        else:
            subprocess.run(["amixer", "-q", "set", "Master", "20%-"])
            return ToolResult(True, "🔉 Volumen bajado.")

    def _tool_abrir_archivo(self, ruta: str = "") -> ToolResult:
        if not ruta:
            return ToolResult(False, "❌ No indicaste qué abrir.")
        path = Path(ruta).expanduser()
        if not path.exists():
            # Buscar en carpetas comunes
            for base in [Path.home(), Path.home() / "Desktop", Path.home() / "Documents"]:
                candidate = base / ruta
                if candidate.exists():
                    path = candidate
                    break
        if not path.exists():
            return ToolResult(False, f"❌ No encontré el archivo: `{ruta}`")

        if _OS == "Windows":
            os.startfile(str(path))
        elif _OS == "Darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])

        return ToolResult(True, f"📂 Abriendo: `{path.name}`", {"ruta": str(path)})

    def _tool_lanzar_app(self, nombre: str = "") -> ToolResult:
        if not nombre:
            return ToolResult(False, "❌ No indicaste la aplicación.")
        nombre_l = nombre.lower().strip()

        # Mapa de apps comunes por nombre amigable → comando real
        apps_windows = {
            "bloc de notas": "notepad", "notepad": "notepad",
            "calculadora": "calc", "calc": "calc",
            "explorador": "explorer", "paint": "mspaint",
            "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
            "chrome": "chrome", "firefox": "firefox",
            "código": "code", "vscode": "code", "vs code": "code",
        }
        apps_mac = {
            "safari": "Safari", "chrome": "Google Chrome",
            "firefox": "Firefox", "código": "Visual Studio Code",
            "terminal": "Terminal", "finder": "Finder",
            "calculadora": "Calculator", "notas": "Notes",
        }
        apps_linux = {
            "firefox": "firefox", "chrome": "google-chrome",
            "código": "code", "terminal": "gnome-terminal",
            "gedit": "gedit", "calculadora": "gnome-calculator",
        }

        try:
            if _OS == "Windows":
                cmd = apps_windows.get(nombre_l, nombre_l)
                subprocess.Popen(cmd, shell=True)
            elif _OS == "Darwin":
                cmd = apps_mac.get(nombre_l, nombre)
                subprocess.Popen(["open", "-a", cmd])
            else:
                cmd = apps_linux.get(nombre_l, nombre_l)
                subprocess.Popen(cmd, shell=True)
            return ToolResult(True, f"🚀 Lanzando: *{nombre}*")
        except Exception as e:
            return ToolResult(False, f"❌ No pude abrir *{nombre}*: {e}")

    def _tool_portapapeles(self, texto: str = "") -> ToolResult:
        if not texto:
            return ToolResult(False, "❌ No indicaste qué copiar.")
        try:
            if _PYPERCLIP:
                import pyperclip
                pyperclip.copy(texto)
            elif _OS == "Windows":
                subprocess.run(["clip"], input=texto.encode("utf-16"), check=True)
            elif _OS == "Darwin":
                subprocess.run(["pbcopy"], input=texto.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=texto.encode(), check=True)
            preview = texto[:40] + ("..." if len(texto) > 40 else "")
            return ToolResult(True, f"📋 Copiado al portapapeles: *{preview}*")
        except Exception as e:
            return ToolResult(False, f"❌ Error copiando: {e}")

    def _tool_escribir_texto(self, texto: str = "") -> ToolResult:
        if not _PYAUTOGUI:
            return ToolResult(False, "❌ Necesita pyautogui.")
        if not texto:
            return ToolResult(False, "❌ No indicaste qué escribir.")
        import time; time.sleep(0.5)
        pyautogui.write(texto, interval=0.03)
        preview = texto[:40] + ("..." if len(texto) > 40 else "")
        return ToolResult(True, f"⌨️ Escrito: *{preview}*")

    def _tool_sistema_info(self) -> ToolResult:
        lineas = ["💻 **Estado del sistema:**"]
        if _PSUTIL:
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disco = psutil.disk_usage("/")
            lineas.append(f"  CPU: {cpu:.1f}%")
            lineas.append(f"  RAM: {ram.used / 1e9:.1f} GB usados / {ram.total / 1e9:.1f} GB total ({ram.percent}%)")
            lineas.append(f"  Disco: {disco.used / 1e9:.1f} GB usados / {disco.total / 1e9:.1f} GB total ({disco.percent}%)")
        else:
            lineas.append("  (Instala psutil para ver detalles: pip install psutil)")
        lineas.append(f"  OS: {platform.system()} {platform.release()}")
        lineas.append(f"  Python: {platform.python_version()}")
        return ToolResult(True, "\n".join(lineas))

    def _tool_listar_archivos(self, carpeta: str = ".") -> ToolResult:
        path = Path(carpeta).expanduser()
        if not path.exists():
            # Intentar rutas relativas al home
            path = Path.home() / carpeta
        if not path.exists():
            return ToolResult(False, f"❌ No encontré la carpeta: `{carpeta}`")

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if not items:
                return ToolResult(True, f"📁 La carpeta `{path.name}` está vacía.")

            lineas = [f"📁 **{path}:**"]
            for item in items[:30]:   # máximo 30 items
                icon = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    size = f" ({s/1024:.1f} KB)" if s < 1_000_000 else f" ({s/1e6:.1f} MB)"
                lineas.append(f"  {icon} {item.name}{size}")

            if len(items) > 30:
                lineas.append(f"  ... y {len(items) - 30} más")

            return ToolResult(True, "\n".join(lineas), {"carpeta": str(path)})
        except PermissionError:
            return ToolResult(False, f"❌ Sin permiso para leer `{carpeta}`.")

    # ── Utilidades públicas ───────────────────────────────────────────────────

    def listar_disponibles(self) -> str:
        """Devuelve una lista legible de herramientas activas."""
        todas = {
            "abrir_url":      "🌐 Abrir URL en el navegador",
            "buscar_web":     "🔍 Buscar en DuckDuckGo",
            "captura":        "📸 Tomar captura de pantalla",
            "volumen":        "🔊 Control de volumen",
            "abrir_archivo":  "📂 Abrir archivo o carpeta",
            "lanzar_app":     "🚀 Lanzar aplicación",
            "portapapeles":   "📋 Copiar al portapapeles",
            "escribir_texto": "⌨️ Escribir texto (pyautogui)",
            "sistema_info":   "💻 Info de CPU/RAM/disco",
            "listar_archivos":"📁 Listar archivos",
        }
        lineas = ["🛠 **Herramientas disponibles:**"]
        for nombre, desc in todas.items():
            estado = "✓" if nombre in self._disponibles else "✗"
            lineas.append(f"  {estado} {desc}")
        return "\n".join(lineas)
