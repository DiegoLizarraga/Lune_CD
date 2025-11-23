"""Test del Orquestador"""

import asyncio
from src.agents.agent_orchestrator import AgentOrchestrator
from src.ai.ai_manager import AIManager
from src.utils.config import Config

async def test_orchestrator():
    config = Config()
    ai_manager = AIManager(config)
    orchestrator = AgentOrchestrator(ai_manager)
    
    print("🧪 Testing AgentOrchestrator...")
    
    # Test: Análisis de solicitud
    request = "Escribe un ensayo sobre IA"
    
    print(f"Analizando: '{request}'")
    result = await orchestrator._analyze_request(request)
    
    print(f"Resultado: {result}")
    
    # Verificar que se clasificó correctamente
    assert result['success']
    assert 'type' in result
    
    print("✅ Orquestador funciona correctamente")

if __name__ == "__main__":
    asyncio.run(test_orchestrator())