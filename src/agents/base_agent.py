"""
Sistema de Agentes para Lune CD v4.0
Clase base para todos los agentes especializados
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime

class BaseAgent(ABC):
    """Clase base para todos los agentes de Lune"""
    
    def __init__(self, name: str, description: str, ai_manager):
        self.name = name
        self.description = description
        self.ai_manager = ai_manager
        self.status = "idle"  # idle, working, completed, error
        self.task_history = []
        self.capabilities = []
        
    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar tarea específica del agente
        
        Args:
            task: Diccionario con la descripción de la tarea
            
        Returns:
            Resultado de la ejecución
        """
        pass
    
    @abstractmethod
    def can_handle(self, task_type: str) -> bool:
        """Verificar si el agente puede manejar un tipo de tarea"""
        pass
    
    def log_task(self, task: str, result: str, status: str):
        """Registrar tarea ejecutada"""
        self.task_history.append({
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "result": result,
            "status": status
        })
    
    def get_status(self) -> Dict[str, Any]:
        """Obtener estado actual del agente"""
        return {
            "name": self.name,
            "status": self.status,
            "capabilities": self.capabilities,
            "tasks_completed": len([t for t in self.task_history if t["status"] == "completed"])
        }
    
    def reset(self):
        """Resetear agente a estado inicial"""
        self.status = "idle"
        self.task_history = []