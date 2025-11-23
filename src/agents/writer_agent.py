"""
Agente de Escritura - Writer Agent
Especializado en crear documentos, ensayos, artículos, etc.
"""

import asyncio
from typing import Dict, Any
from src.agents.base_agent import BaseAgent
from src.agents.app_controller import ApplicationController
import pyautogui
import time

class WriterAgent(BaseAgent):
    """Agente especializado en escritura y creación de documentos"""
    
    def __init__(self, ai_manager):
        super().__init__(
            name="WriterAgent",
            description="Agente especializado en escribir documentos, ensayos y contenido",
            ai_manager=ai_manager
        )
        self.capabilities = [
            "escribir_ensayo",
            "crear_documento",
            "redactar_articulo",
            "generar_informe",
            "escribir_email"
        ]
        self.app_controller = ApplicationController()
    
    def can_handle(self, task_type: str) -> bool:
        """Verificar si puede manejar la tarea"""
        keywords = ["escribir", "redactar", "crear documento", "ensayo", "artículo", "informe"]
        return any(keyword in task_type.lower() for keyword in keywords)
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar tarea de escritura"""
        self.status = "working"
        task_type = task.get("type", "")
        
        try:
            if "ensayo" in task_type.lower():
                result = await self.write_essay(task)
            elif "artículo" in task_type.lower():
                result = await self.write_article(task)
            elif "informe" in task_type.lower():
                result = await self.write_report(task)
            else:
                result = await self.write_document(task)
            
            self.status = "completed"
            self.log_task(task_type, "Documento creado exitosamente", "completed")
            return result
            
        except Exception as e:
            self.status = "error"
            self.log_task(task_type, str(e), "error")
            return {"success": False, "error": str(e)}
    
    async def write_essay(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Escribir un ensayo completo"""
        topic = task.get("topic", "")
        length = task.get("length", "medio")
        style = task.get("style", "académico")
        
        # 1. Abrir Word
        print("📝 Abriendo Microsoft Word...")
        result = self.app_controller.open_word()
        if not result["success"]:
            return result
        
        # Esperar a que Word cargue
        await asyncio.sleep(3)
        
        # 2. Generar estructura del ensayo
        print("🧠 Generando estructura del ensayo...")
        prompt = f"""
        Crea la estructura de un ensayo {style} sobre: {topic}
        Longitud: {length}
        
        Incluye:
        1. Título atractivo
        2. Introducción
        3. 3 argumentos principales con desarrollo
        4. Conclusión
        
        Formato: Solo el contenido del ensayo, listo para copiar.
        """
        
        structure = self.ai_manager.get_response(prompt)
        
        # 3. Generar contenido completo
        print("✍️ Escribiendo el ensayo...")
        content_prompt = f"""
        Basándote en esta estructura, escribe el ensayo completo sobre {topic}:
        
        {structure}
        
        Requisitos:
        - Estilo {style}
        - Longitud {length} (aproximadamente {'500' if length == 'corto' else '1000' if length == 'medio' else '2000'} palabras)
        - Párrafos bien desarrollados
        - Argumentos sólidos con ejemplos
        - Conclusión contundente
        
        Escribe solo el ensayo completo, sin comentarios adicionales.
        """
        
        full_content = self.ai_manager.get_response(content_prompt)
        
        # 4. Escribir en Word usando pyautogui
        print("⌨️ Escribiendo en Word...")
        await self._type_in_word(full_content)
        
        return {
            "success": True,
            "message": f"Ensayo sobre '{topic}' creado exitosamente",
            "word_count": len(full_content.split()),
            "preview": full_content[:200] + "..."
        }
    
    async def write_article(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Escribir un artículo"""
        topic = task.get("topic", "")
        
        print("📰 Abriendo Word para artículo...")
        self.app_controller.open_word()
        await asyncio.sleep(3)
        
        prompt = f"""
        Escribe un artículo informativo sobre: {topic}
        
        Incluye:
        - Título llamativo
        - Lead/Entradilla
        - Desarrollo con subtítulos
        - Datos y ejemplos
        - Cierre impactante
        
        Formato periodístico, lenguaje claro y directo.
        """
        
        content = self.ai_manager.get_response(prompt)
        await self._type_in_word(content)
        
        return {
            "success": True,
            "message": f"Artículo sobre '{topic}' creado",
            "content": content
        }
    
    async def write_report(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Escribir un informe"""
        topic = task.get("topic", "")
        
        print("📊 Abriendo Word para informe...")
        self.app_controller.open_word()
        await asyncio.sleep(3)
        
        prompt = f"""
        Crea un informe profesional sobre: {topic}
        
        Estructura:
        1. Resumen ejecutivo
        2. Introducción
        3. Metodología
        4. Resultados/Hallazgos
        5. Análisis
        6. Conclusiones
        7. Recomendaciones
        
        Estilo formal y profesional.
        """
        
        content = self.ai_manager.get_response(prompt)
        await self._type_in_word(content)
        
        return {
            "success": True,
            "message": f"Informe sobre '{topic}' creado",
            "content": content
        }
    
    async def write_document(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Escribir documento genérico"""
        content_request = task.get("content", "")
        
        print("📄 Abriendo Word...")
        self.app_controller.open_word()
        await asyncio.sleep(3)
        
        prompt = f"Escribe: {content_request}"
        content = self.ai_manager.get_response(prompt)
        
        await self._type_in_word(content)
        
        return {
            "success": True,
            "message": "Documento creado",
            "content": content
        }
    
    async def _type_in_word(self, text: str, wpm: int = 300):
        """
        Escribir texto en Word simulando escritura humana
        
        Args:
            text: Texto a escribir
            wpm: Palabras por minuto (ajusta velocidad)
        """
        # Calcular delay entre palabras (más realista)
        words = text.split()
        delay = 60 / wpm  # segundos por palabra
        
        for i, word in enumerate(words):
            pyautogui.write(word, interval=0.01)  # Escribe cada letra rápido
            
            # Agregar espacio o salto de línea
            if i < len(words) - 1:
                if '\n' in text[text.index(word):text.index(word) + len(word) + 10]:
                    pyautogui.press('enter')
                else:
                    pyautogui.write(' ')
            
            # Pequeña pausa entre palabras
            await asyncio.sleep(delay)
            
            # Pausa más larga en puntos
            if word.endswith(('.', '!', '?')):
                await asyncio.sleep(delay * 2)