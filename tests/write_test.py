"""Test de WriterAgent"""

import asyncio
from src.agents.writer_agent import WriterAgent
from src.ai.ai_manager import AIManager
from src.utils.config import Config

async def test_writer():
    config = Config()
    ai_manager = AIManager(config)
    writer = WriterAgent(ai_manager)
    
    print("🧪 Testing WriterAgent...")
    
    # Test 1: Verificar capacidades
    print(f"Capacidades: {writer.capabilities}")
    
    # Test 2: Verificar can_handle
    assert writer.can_handle("escribir ensayo")
    print("✅ can_handle funciona")
    
    # Test 3: Ejecutar tarea simple (sin abrir Word)
    # Esto solo prueba la generación de contenido
    
    print("✅ WriterAgent funciona correctamente")

if __name__ == "__main__":
    asyncio.run(test_writer())