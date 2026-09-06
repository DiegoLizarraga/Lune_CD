"""
tools.py — Sistema de herramientas FUSIONADO para Lune CD (Versión Ultra-Rápida)
=======================================================================
Integra las capacidades de escritorio y la lógica de web_extension.py.

Herramientas incluidas:
  - abrir_url      Abre un sitio web directamente
  - buscar_web     Realiza una búsqueda en Google o YouTube
  - lanzar_app     Lanza aplicaciones del PC (con alias automáticos)
  - sistema_info   Muestra CPU, RAM y Disco
"""

import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser
from typing import List, Dict, Tuple, Optional

# Intentar importar dependencias opcionales
try:
    import psutil
except ImportError:
    psutil = None


# ── Saneamiento ────────────────────────────────────────────────────────────────
# Estas herramientas se disparan con texto que puede venir del MODELO, no solo
# del usuario. Un personaje de roleplay descarrilado podría emitir
# `TOOL:lanzar_app:x" & del /q ...`, así que nada de shells ni concatenar
# cadenas en comandos: se valida primero y se ejecuta con lista de argumentos.

# Solo letras, números, espacios y unos pocos signos inofensivos.
_APP_VALIDA = re.compile(r"^[\w .\-()]{1,60}$", re.UNICODE)
_ESQUEMAS_PERMITIDOS = ("http", "https")

# Lanzar apps con `cmd /c start` abría una consola negra que parpadeaba.
_SIN_CONSOLA = {}
if os.name == "nt":
    _SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def _nombre_app_seguro(nombre: str) -> Optional[str]:
    """Devuelve el nombre saneado, o None si trae algo sospechoso."""
    nombre = (nombre or "").strip().strip('"').strip("'")
    if not nombre or not _APP_VALIDA.match(nombre):
        return None
    # Ni rutas ni escapes: solo el nombre del ejecutable.
    if any(c in nombre for c in ("/", "\\", "..")):
        return None
    return nombre


def _url_segura(url: str) -> Optional[str]:
    """
    Normaliza y valida una URL. Rechaza esquemas peligrosos como `file:`,
    `javascript:` o `data:`, que webbrowser abriría sin rechistar.
    """
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        return None

    # Si YA trae un esquema, tiene que ser http(s). Comprobarlo antes de añadir
    # el prefijo es lo que evita que «javascript:alert(1)» se convierta en
    # «https://javascript:alert(1)» y pase el filtro por la puerta de atrás.
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", url)
    if m:
        if m.group(1).lower() not in _ESQUEMAS_PERMITIDOS:
            return None
    else:
        url = "https://" + url

    try:
        partes = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if partes.scheme.lower() not in _ESQUEMAS_PERMITIDOS or not partes.netloc:
        return None
    return url


class ToolResult:
    """Contenedor para el resultado de ejecutar una herramienta."""
    def __init__(self, ok: bool, mensaje: str, datos: dict = None):
        self.ok = ok
        self.mensaje = mensaje
        self.datos = datos or {}


class ToolManager:
    def __init__(self):
        # Mapa de funciones activas
        self._tools = {
            "buscar_web": self._cmd_buscar_web,
            "abrir_url": self._cmd_abrir_url,
            "lanzar_app": self._cmd_lanzar_app,
            "sistema_info": self._cmd_sistema_info,
        }

    def detectar_y_ejecutar(self, texto: str) -> Optional[ToolResult]:
        """
        Intercepta el mensaje del usuario ANTES de la IA.
        Soporta lenguaje natural para ejecutar acciones en 0.1 segundos.
        """
        texto_lower = texto.lower().strip()

        # 1. Búsqueda Web (Optimizada para YouTube y Google)
        if texto_lower.startswith(("busca ", "buscar ", "investiga ")):
            if "youtube" in texto_lower:
                # Usamos re.search para extraer la consulta respetando mayúsculas/minúsculas originales
                match = re.search(r"^(busca en youtube|buscar en youtube|busca videos de|busca|buscar)\s+(.+)", texto, flags=re.IGNORECASE)
                if match:
                    query = match.group(2).strip()
                    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
                    webbrowser.open(url)
                    return ToolResult(True, f"Buscando en YouTube: '{query}'")
            else:
                # Búsqueda normal en Google
                match = re.search(r"^(busca en google|buscar en google|investiga sobre|investiga|buscar|busca)\s+(.+)", texto, flags=re.IGNORECASE)
                if match:
                    query = match.group(2).strip()
                    return self._cmd_buscar_web(query)

        # 2. Lanzar App Local (Prioridad)
        if texto_lower.startswith(("abre la app ", "lanza el programa ", "lanza ", "abre el programa ")):
            match = re.search(r"^(abre la app|lanza el programa|lanza|abre el programa)\s+(.+)", texto, flags=re.IGNORECASE)
            if match:
                app = match.group(2).strip()
                return self._cmd_lanzar_app(app)

        # 3. Abrir URL Directa o Atajos Populares (¡INSTANTÁNEO!)
        if texto_lower.startswith(("ve a ", "abre la web ", "abre el sitio ", "abre ")):
            match = re.search(r"^(ve a la web de|ve a|abre la web|abre el sitio|abre)\s+(.+)", texto, flags=re.IGNORECASE)
            if match:
                objetivo_original = match.group(2).strip()
                objetivo_lower = objetivo_original.lower()
                
                # Diccionario de atajos rápidos para saltarse a la IA
                atajos_web = {
                    "youtube": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "facebook": "https://www.facebook.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "whatsapp": "https://web.whatsapp.com",
                    "instagram": "https://www.instagram.com",
                    "github": "https://github.com",
                    "chatgpt": "https://chatgpt.com",
                    "tiktok": "https://www.tiktok.com",
                    "twitch": "https://www.twitch.tv",
                    "netflix": "https://www.netflix.com",
                    "reddit": "https://www.reddit.com",
                    "amazon": "https://www.amazon.com",
                    "spotify": "https://open.spotify.com",
                }
                
                # Si el usuario dice "abre youtube", lo detecta aquí y abre al instante
                if objetivo_lower in atajos_web:
                    return self._cmd_abrir_url(atajos_web[objetivo_lower])
                    
                # Si el usuario dice "abre wikipedia.org" o pega un enlace de youtube completo
                # PASAMOS EL OBJETIVO ORIGINAL PARA PRESERVAR LAS MAYÚSCULAS DE LA URL
                if "." in objetivo_lower and not " " in objetivo_lower:
                    return self._cmd_abrir_url(objetivo_original)

        # 4. Info del sistema
        if any(k in texto_lower for k in ["info del sistema", "estado del pc", "cuanta ram"]):
            return self._cmd_sistema_info()

        return None

    def parsear_respuesta_ia(self, respuesta: str) -> Tuple[str, List[Dict]]:
        """
        Analiza la respuesta de la IA buscando comandos TOOL: o ABRIR_:
        """
        acciones = []
        respuesta_limpia = respuesta

        # Detectar ABRIR_BUSQUEDA:
        match_search = re.search(r'ABRIR_BUSQUEDA:(.+?)(?:\n|$)', respuesta_limpia)
        if match_search:
            query = match_search.group(1).strip()
            respuesta_limpia = respuesta_limpia.replace(match_search.group(0), '').strip()
            acciones.append({"herramienta": "buscar_web", "args": query})

        # Detectar ABRIR_URL:
        match_url = re.search(r'ABRIR_URL:(https?://\S+)', respuesta_limpia)
        if match_url:
            url = match_url.group(1).strip()
            respuesta_limpia = respuesta_limpia.replace(match_url.group(0), '').strip()
            acciones.append({"herramienta": "abrir_url", "args": url})

        # Detectar formato TOOL clásico
        for linea in respuesta_limpia.split('\n'):
            if linea.strip().startswith("TOOL:"):
                try:
                    comando = linea.replace("TOOL:", "").strip()
                    partes = comando.split(":", 1)
                    nombre_tool = partes[0].strip()
                    args = partes[1].strip() if len(partes) > 1 else ""

                    if nombre_tool in self._tools:
                        acciones.append({"herramienta": nombre_tool, "args": args})
                        respuesta_limpia = respuesta_limpia.replace(linea, "").strip()
                except Exception:
                    pass

        return respuesta_limpia, acciones

    def ejecutar(self, herramienta: str, **kwargs) -> ToolResult:
        """Ejecuta una herramienta solicitada."""
        if herramienta not in self._tools:
            return ToolResult(False, f"Herramienta '{herramienta}' no disponible.")
        
        try:
            func = self._tools[herramienta]
            args = kwargs.get("args", "")
            return func(args) if args else func()
        except Exception as e:
            return ToolResult(False, f"Error en {herramienta}: {str(e)}")

    # ── Implementación de Herramientas ────────────────────────────────────────

    def _cmd_buscar_web(self, query: str) -> ToolResult:
        """Busca en Google."""
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return ToolResult(True, f"Buscando en Google: '{query}'")

    def _cmd_abrir_url(self, url: str) -> ToolResult:
        """Abre una URL, siempre que sea http(s)."""
        url_final = _url_segura(url)
        if not url_final:
            return ToolResult(False, f"No abro esa dirección: «{url}» no es una URL http(s) válida.")

        webbrowser.open(url_final)

        # Nombre de la página solo para mostrarlo bonito en el chat
        try:
            host = urllib.parse.urlparse(url_final).netloc
            dominio = host.replace("www.", "").split(".")[0].capitalize() or "enlace"
        except Exception:
            dominio = "enlace"

        return ToolResult(True, f"Abriendo {dominio}...")

    # Alias técnicos para programas de Windows
    ALIAS_APPS = {
        "paint": "mspaint",
        "calculadora": "calc",
        "bloc de notas": "notepad",
        "notas": "notepad",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "archivos": "explorer",
        "explorador": "explorer",
        "cmd": "cmd",
        "consola": "cmd",
        "terminal": "cmd",
        "navegador": "msedge",
    }

    def _cmd_lanzar_app(self, nombre: str) -> ToolResult:
        """
        Lanza una aplicación local.

        Nunca se pasa por un shell ni se concatena el nombre en una cadena de
        comando: primero se sanea y luego se ejecuta con lista de argumentos.
        """
        limpio = _nombre_app_seguro(nombre)
        if not limpio:
            return ToolResult(False, f"No puedo lanzar «{nombre}»: el nombre no es válido.")

        app_exe = self.ALIAS_APPS.get(limpio.lower(), limpio)

        try:
            ruta = shutil.which(app_exe)
            if ruta:
                subprocess.Popen([ruta], **_SIN_CONSOLA)
            elif os.name == "nt":
                # Sin shell=True. `start` resuelve las App Paths del registro
                # (Office y demás), y el nombre ya viene saneado.
                subprocess.Popen(["cmd", "/c", "start", "", app_exe], shell=False, **_SIN_CONSOLA)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", app_exe])
            else:
                return ToolResult(False, f"No encontré «{app_exe}» en el PATH.")
            return ToolResult(True, f"Lanzando aplicación: {limpio}")
        except FileNotFoundError:
            return ToolResult(False, f"No encontré «{app_exe}» en este equipo.")
        except Exception as e:
            return ToolResult(False, f"No se pudo abrir {limpio}: {e}")

    def _cmd_sistema_info(self, *args) -> ToolResult:
        """Información de hardware."""
        if not psutil: return ToolResult(False, "psutil no instalado.")
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        return ToolResult(True, f"**Estado del PC**: CPU {cpu}% | RAM {ram}%")

    def listar_disponibles(self) -> str:
        todas = {
            "buscar_web": "Buscar en Google o YouTube",
            "abrir_url":  "Abrir sitios populares al instante",
            "lanzar_app": "Lanzar programas del PC",
            "sistema_info": "Ver estado del sistema"
        }
        lineas = ["**Herramientas Fusionadas Activas:**"]
        for cmd, desc in todas.items():
            lineas.append(f"  {desc}")
        return "\n".join(lineas)