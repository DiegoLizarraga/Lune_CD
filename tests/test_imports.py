"""Test de importaciones"""

def test_agents_import():
    """Verificar que todos los agentes se importan correctamente"""
    try:
        from src.agents import (
            BaseAgent,
            WriterAgent,
            ResearcherAgent,
            AutomationAgent,
            AgentOrchestrator,
            ApplicationController
        )
        print("✅ Todos los agentes importados correctamente")
        return True
    except Exception as e:
        print(f"❌ Error en importaciones: {e}")
        return False

def test_ai_manager():
    """Verificar AI Manager"""
    try:
        from src.ai.ai_manager import AIManager
        from src.utils.config import Config
        
        config = Config()
        ai_manager = AIManager(config)
        
        print("✅ AI Manager inicializado")
        return True
    except Exception as e:
        print(f"❌ Error en AI Manager: {e}")
        return False

if __name__ == "__main__":
    print("\n🧪 Ejecutando Tests...\n")
    
    test_agents_import()
    test_ai_manager()
    
    print("\n✅ Tests completados!")