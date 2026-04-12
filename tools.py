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
import subprocess
import urllib.parse
import webbrowser
from typing import List, Dict, Tuple, Optional
import sys

# Intentar importar dependencias opcionales
try:
    import psutil
except ImportError:
    psutil = None


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
                    return ToolResult(True, f"🎥 Buscando en YouTube: '{query}'")
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
        return ToolResult(True, f"🔍 Buscando en Google: '{query}'")

    def _cmd_abrir_url(self, url: str) -> ToolResult:
        """Abre una URL directamente respetando las mayúsculas/minúsculas."""
        # Se asegura de que la URL empiece con http para evitar errores de navegador
        if not url.startswith(("http://", "https://")):
            url_final = "https://" + url
        else:
            url_final = url
            
        webbrowser.open(url_final)
        
        # Extraemos el nombre de la página solo para motivos de visualización en el chat
        try:
            dominio = url_final.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0].split(".")[0].capitalize()
        except:
            dominio = "enlace"
            
        return ToolResult(True, f"🌐 Abriendo {dominio}...")

    def _cmd_lanzar_app(self, nombre: str) -> ToolResult:
        """Lanza aplicaciones locales."""
        if not nombre: return ToolResult(False, "Nombre de app vacío.")
        
        # Diccionario de alias técnicos para programas de Windows
        aliases = {
            "paint": "mspaint",
            "calculadora": "calc",
            "bloc de notas": "notepad",
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt",
            "archivos": "explorer",
            "explorador": "explorer",
            "cmd": "cmd",
            "consola": "cmd",
            "terminal": "cmd"
        }
        
        app_exe = aliases.get(nombre.lower(), nombre)
        
        try:
            if os.name == 'nt': 
                os.system(f'start "" "{app_exe}"')
            elif sys.platform == 'darwin': 
                subprocess.Popen(["open", "-a", nombre])
            else: 
                subprocess.Popen([nombre])
                
            return ToolResult(True, f"🚀 Lanzando aplicación: {nombre}")
        except Exception as e:
            return ToolResult(False, f"❌ No se pudo abrir {nombre}: {e}")

    def _cmd_sistema_info(self, *args) -> ToolResult:
        """Información de hardware."""
        if not psutil: return ToolResult(False, "psutil no instalado.")
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        return ToolResult(True, f"💻 **Estado del PC**: CPU {cpu}% | RAM {ram}%")

    def listar_disponibles(self) -> str:
        todas = {
            "buscar_web": "🔍 Buscar en Google o YouTube",
            "abrir_url":  "🌐 Abrir sitios populares al instante",
            "lanzar_app": "🚀 Lanzar programas del PC",
            "sistema_info": "💻 Ver estado del sistema"
        }
        lineas = ["🛠 **Herramientas Fusionadas Activas:**"]
        for cmd, desc in todas.items():
            lineas.append(f"  ✓ {desc}")
        return "\n".join(lineas)