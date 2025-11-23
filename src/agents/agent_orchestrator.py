"""
Orquestador de Agentes - Agent Orchestrator
Coordina todos los agentes y decide cuál usar para cada tarea
"""

import asyncio
from typing import Dict, Any, List, Optional
from src.agents.writer_agent import WriterAgent
from src.agents.researcher_agent import ResearcherAgent
from src.agents.automation_agent import AutomationAgent

class AgentOrchestrator:
    """Orquestador principal de todos los agentes"""
    
    def __init__(self, ai_manager):
        self.ai_manager = ai_manager
        
        # Inicializar todos los agentes
        self.agents = {
            "writer": WriterAgent(ai_manager),
            "researcher": ResearcherAgent(ai_manager),
            "automation": AutomationAgent(ai_manager)
        }
        
        self.task_queue = []
        self.active_tasks = {}
    
    async def process_request(self, request: str) -> Dict[str, Any]:
        """
        Procesar solicitud del usuario y decidir qué agente usar
        
        Args:
            request: Solicitud en lenguaje natural del usuario
            
        Returns:
            Resultado de la ejecución
        """
        print(f"\n🎯 Procesando solicitud: {request}")
        
        # 1. Analizar la solicitud usando IA
        task = await self._analyze_request(request)
        
        if not task["success"]:
            return task
        
        # 2. Seleccionar el agente apropiado
        agent = self._select_agent(task)
        
        if not agent:
            return {
                "success": False,
                "error": "No se encontró un agente capaz de realizar esta tarea"
            }
        
        print(f"✅ Agente seleccionado: {agent.name}")
        
        # 3. Ejecutar la tarea
        result = await agent.execute_task(task)
        
        # 4. Registrar en historial
        self.active_tasks[len(self.active_tasks)] = {
            "request": request,
            "agent": agent.name,
            "task": task,
            "result": result
        }
        
        return result
    
    async def _analyze_request(self, request: str) -> Dict[str, Any]:
        """Analizar solicitud y convertirla en tarea estructurada"""
        
        analysis_prompt = f"""
        Analiza esta solicitud del usuario y extrae la información clave:
        
        Solicitud: "{request}"
        
        Determina:
        1. ¿Qué tipo de tarea es? (escritura, investigación, automatización, otro)
        2. ¿Qué parámetros específicos hay? (tema, longitud, formato, etc.)
        3. ¿Qué aplicaciones se necesitan? (Word, Excel, navegador, etc.)
        
        Responde en formato JSON:
        {{
            "type": "tipo_de_tarea",
            "category": "categoria_principal",
            "params": {{
                "topic": "tema_principal",
                "additional": "otros_parametros"
            }},
            "apps_needed": ["app1", "app2"]
        }}
        
        Solo responde con el JSON, nada más.
        """
        
        try:
            analysis = self.ai_manager.get_response(analysis_prompt)
            
            # Extraer JSON de la respuesta
            import json
            # Limpiar la respuesta (remover backticks de markdown si existen)
            clean_analysis = analysis.strip()
            if clean_analysis.startswith("```"):
                clean_analysis = clean_analysis.split("```")[1]
                if clean_analysis.startswith("json"):
                    clean_analysis = clean_analysis[4:]
            
            task_data = json.loads(clean_analysis.strip())
            task_data["success"] = True
            task_data["raw_request"] = request
            
            return task_data
            
        except Exception as e:
            # Si falla el análisis, intentar clasificación simple
            return self._simple_classification(request)
    
    def _simple_classification(self, request: str) -> Dict[str, Any]:
        """Clasificación simple basada en palabras clave"""
        request_lower = request.lower()
        
        task = {
            "success": True,
            "raw_request": request,
            "params": {}
        }
        
        # Clasificar por palabras clave
        if any(word in request_lower for word in ["escribir", "redactar", "ensayo", "artículo", "documento"]):
            task["type"] = "escritura"
            task["category"] = "writer"
            if "ensayo" in request_lower:
                task["params"]["subtype"] = "essay"
            elif "artículo" in request_lower:
                task["params"]["subtype"] = "article"
        
        elif any(word in request_lower for word in ["investigar", "buscar", "analizar", "comparar"]):
            task["type"] = "investigación"
            task["category"] = "researcher"
        
        elif any(word in request_lower for word in ["organizar", "limpiar", "backup", "renombrar", "automatizar"]):
            task["type"] = "automatización"
            task["category"] = "automation"
        
        else:
            task["type"] = "general"
            task["category"] = "unknown"
        
        # Extraer tema/contenido
        task["params"]["topic"] = request
        
        return task
    
    def _select_agent(self, task: Dict[str, Any]) -> Optional[Any]:
        """Seleccionar el agente apropiado para la tarea"""
        
        category = task.get("category", "")
        task_type = task.get("type", "")
        
        # Selección directa por categoría
        if category in self.agents:
            return self.agents[category]
        
        # Buscar agente que pueda manejar la tarea
        for agent in self.agents.values():
            if agent.can_handle(task_type):
                return agent
        
        return None
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Obtener estado de todos los agentes"""
        return {
            name: agent.get_status()
            for name, agent in self.agents.items()
        }
    
    def get_task_history(self) -> List[Dict[str, Any]]:
        """Obtener historial de tareas"""
        return list(self.active_tasks.values())
    
    async def execute_multi_agent_task(self, request: str) -> Dict[str, Any]:
        """
        Ejecutar tarea que requiere múltiples agentes
        Ejemplo: "Investiga sobre IA y luego escribe un ensayo"
        """
        print(f"\n🔄 Tarea multi-agente: {request}")
        
        # Analizar si requiere múltiples pasos
        plan_prompt = f"""
        Analiza si esta tarea requiere múltiples pasos o agentes:
        
        "{request}"
        
        Si requiere múltiples pasos, lista cada paso en orden.
        Si es una tarea simple, indica "SIMPLE".
        
        Ejemplo de respuesta:
        PASO 1: Investigar sobre [tema]
        PASO 2: Escribir ensayo con la información
        """
        
        plan = self.ai_manager.get_response(plan_prompt)
        
        if "SIMPLE" in plan:
            # Tarea simple, usar proceso normal
            return await self.process_request(request)
        
        # Ejecutar cada paso
        results = []
        steps = [line for line in plan.split('\n') if line.strip().startswith("PASO")]
        
        for step in steps:
            step_request = step.split(':', 1)[1].strip() if ':' in step else step
            print(f"\n📋 Ejecutando: {step}")
            
            result = await self.process_request(step_request)
            results.append(result)
            
            # Pequeña pausa entre pasos
            await asyncio.sleep(1)
        
        return {
            "success": True,
            "message": "Tarea multi-agente completada",
            "steps": len(results),
            "results": results
        }
    
    def create_custom_agent(self, name: str, description: str, capabilities: List[str]):
        """Crear un agente personalizado en tiempo real"""
        # Esta función permitiría crear agentes dinámicamente
        # Por ahora es un placeholder para futuras expansiones
        pass