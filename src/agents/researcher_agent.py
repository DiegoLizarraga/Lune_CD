"""
Agente de Investigación - Researcher Agent
Especializado en buscar información, analizar datos y crear informes de investigación
"""

import asyncio
from typing import Dict, Any, List
from src.agents.base_agent import BaseAgent
from src.agents.app_controller import ApplicationController
import requests
from bs4 import BeautifulSoup

class ResearcherAgent(BaseAgent):
    """Agente especializado en investigación y análisis"""
    
    def __init__(self, ai_manager):
        super().__init__(
            name="ResearcherAgent",
            description="Agente especializado en investigación, búsqueda y análisis de información",
            ai_manager=ai_manager
        )
        self.capabilities = [
            "investigar_tema",
            "buscar_información",
            "analizar_datos",
            "crear_bibliografia",
            "comparar_fuentes"
        ]
        self.app_controller = ApplicationController()
        self.sources = []
    
    def can_handle(self, task_type: str) -> bool:
        """Verificar si puede manejar la tarea"""
        keywords = ["investigar", "buscar", "analizar", "comparar", "referencias", "fuentes"]
        return any(keyword in task_type.lower() for keyword in keywords)
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar tarea de investigación"""
        self.status = "working"
        task_type = task.get("type", "")
        
        try:
            if "investigar" in task_type.lower():
                result = await self.research_topic(task)
            elif "comparar" in task_type.lower():
                result = await self.compare_sources(task)
            elif "bibliografía" in task_type.lower():
                result = await self.create_bibliography(task)
            else:
                result = await self.search_information(task)
            
            self.status = "completed"
            self.log_task(task_type, "Investigación completada", "completed")
            return result
            
        except Exception as e:
            self.status = "error"
            self.log_task(task_type, str(e), "error")
            return {"success": False, "error": str(e)}
    
    async def research_topic(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Investigar un tema completo"""
        topic = task.get("topic", "")
        depth = task.get("depth", "medio")  # básico, medio, profundo
        
        print(f"🔍 Investigando: {topic}")
        
        # 1. Generar preguntas de investigación
        questions_prompt = f"""
        Genera 5 preguntas clave de investigación sobre: {topic}
        
        Las preguntas deben ser:
        - Específicas y relevantes
        - Que cubran diferentes aspectos del tema
        - Que permitan una investigación profunda
        
        Formato: Solo lista las preguntas numeradas.
        """
        
        questions = self.ai_manager.get_response(questions_prompt)
        print(f"❓ Preguntas generadas:\n{questions}")
        
        # 2. Buscar información para cada pregunta
        research_data = []
        for question in questions.split('\n'):
            if question.strip():
                answer_prompt = f"""
                Responde esta pregunta de investigación con información detallada:
                {question}
                
                Incluye:
                - Datos concretos
                - Ejemplos
                - Diferentes perspectivas
                - Referencias si es posible
                """
                
                answer = self.ai_manager.get_response(answer_prompt)
                research_data.append({
                    "question": question,
                    "answer": answer
                })
                
                await asyncio.sleep(1)  # Evitar sobrecarga
        
        # 3. Sintetizar información
        synthesis_prompt = f"""
        Sintetiza esta investigación sobre {topic}:
        
        {chr(10).join([f"Q: {item['question']}\nA: {item['answer']}\n" for item in research_data])}
        
        Crea un informe estructurado con:
        1. Resumen ejecutivo
        2. Hallazgos principales
        3. Análisis detallado
        4. Conclusiones
        """
        
        final_report = self.ai_manager.get_response(synthesis_prompt)
        
        # 4. Abrir Word y escribir el informe
        print("📝 Creando documento con los resultados...")
        self.app_controller.open_word()
        await asyncio.sleep(3)
        
        # Aquí podrías usar pyautogui para escribir el informe
        
        return {
            "success": True,
            "message": f"Investigación sobre '{topic}' completada",
            "questions": len(research_data),
            "report": final_report,
            "sources": self.sources
        }
    
    async def search_information(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Buscar información específica"""
        query = task.get("query", "")
        
        print(f"🔎 Buscando: {query}")
        
        # Usar la IA para buscar y sintetizar información
        search_prompt = f"""
        Busca y proporciona información detallada sobre: {query}
        
        Incluye:
        - Definiciones claras
        - Datos relevantes
        - Ejemplos prácticos
        - Contexto e importancia
        
        Organiza la información de forma estructurada.
        """
        
        results = self.ai_manager.get_response(search_prompt)
        
        return {
            "success": True,
            "query": query,
            "results": results
        }
    
    async def compare_sources(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Comparar diferentes fuentes sobre un tema"""
        topic = task.get("topic", "")
        
        print(f"⚖️ Comparando fuentes sobre: {topic}")
        
        # Generar análisis comparativo
        compare_prompt = f"""
        Analiza diferentes perspectivas sobre: {topic}
        
        Compara:
        - Puntos de vista tradicionales vs modernos
        - Diferentes escuelas de pensamiento
        - Ventajas y desventajas de cada perspectiva
        
        Presenta un análisis objetivo y balanceado.
        """
        
        comparison = self.ai_manager.get_response(compare_prompt)
        
        return {
            "success": True,
            "topic": topic,
            "comparison": comparison
        }
    
    async def create_bibliography(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Crear bibliografía sobre un tema"""
        topic = task.get("topic", "")
        format_style = task.get("format", "APA")  # APA, MLA, Chicago
        
        print(f"📚 Creando bibliografía en formato {format_style}...")
        
        biblio_prompt = f"""
        Crea una bibliografía recomendada sobre: {topic}
        
        Incluye:
        - 10 fuentes relevantes (libros, artículos, sitios web)
        - Formato: {format_style}
        - Descripciones breves de cada fuente
        - Orden alfabético
        
        Asegúrate de que las referencias sean reales y verificables.
        """
        
        bibliography = self.ai_manager.get_response(biblio_prompt)
        
        # Abrir Word y escribir la bibliografía
        self.app_controller.open_word()
        await asyncio.sleep(3)
        
        return {
            "success": True,
            "topic": topic,
            "format": format_style,
            "bibliography": bibliography
        }