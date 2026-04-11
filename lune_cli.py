#!/usr/bin/env python3
"""
lune_cli.py — CLI para Lune CD v7.0 con OpenRouter + Claude Code
==============================================================

Uso desde terminal:

  # Chat normal con modelo gratuito
  lune --model openrouter/free "¿Cuál es la capital de Francia?"

  # Chat interactivo
  lune chat --model openrouter/free

  # Ejecutar código (requiere Claude Code)
  lune code --model openrouter/free "escribe un script que calcule fibonacci"

  # Listar modelos disponibles
  lune models

  # Probar conexión
  lune test-connection

  # Con archivo de entrada
  lune file mi_archivo.txt --model openrouter/free

Requisitos:
  - API key de OpenRouter en datos.json
  - Python 3.10+
"""

import sys
import argparse
import asyncio
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

# Importar módulos del proyecto
try:
    from openrouter_provider import (
        OpenRouterChatProvider,
        OpenRouterClaudeCodeProvider,
        OpenRouterConfig,
        test_connection,
        list_free_models,
    )
    from memoria import MemoriaManager
    from utils import Logger, FileManager
    import datos
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("Asegúrate de que estés en la carpeta raíz del proyecto.")
    sys.exit(1)

logger = Logger("lune_cli")
memoria = MemoriaManager()


class LuneCLI:
    """Interfaz de línea de comandos para Lune CD"""

    def __init__(self):
        self.api_key = datos.openrouter_key()
        self.default_model = datos.openrouter_model()
        
        if not self.api_key:
            print("❌ Error: OpenRouter API key no configurada.")
            print("   Agrega tu clave en datos.json bajo 'apis' → 'openrouter_key'")
            sys.exit(1)

    async def chat_once(self, message: str, model: Optional[str] = None) -> str:
        """Chat de una sola pregunta"""
        model = model or self.default_model
        
        config = OpenRouterConfig(api_key=self.api_key, model=model)
        provider = OpenRouterChatProvider(config)

        # Obtener contexto de memoria
        context = memoria.obtener_contexto_para_prompt()
        system_prompt = self._get_system_prompt() + "\n" + context

        print(f"\n🤖 Usando modelo: {model}")
        print(f"📝 Procesando...\n")

        response = await provider.chat(
            message=message,
            system_prompt=system_prompt,
            on_token=self._on_token
        )

        # Procesar respuesta en memoria
        memoria.procesar_respuesta_lune(response)
        
        return response

    async def chat_interactive(self, model: Optional[str] = None):
        """Chat interactivo multi-turno"""
        model = model or self.default_model
        
        config = OpenRouterConfig(api_key=self.api_key, model=model)
        provider = OpenRouterChatProvider(config)

        context = memoria.obtener_contexto_para_prompt()
        system_prompt = self._get_system_prompt() + "\n" + context

        print(f"\n🌙 Lune CD v7.0 — Chat Interactivo")
        print(f"📊 Modelo: {model}")
        print(f"💡 Escribe 'salir' para terminar, '/memoria' para ver recuerdos\n")

        conversation = []

        while True:
            try:
                user_input = input("👤 Tú: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == "salir":
                    print("🌙 ¡Hasta luego! Tus recuerdos han sido guardados.")
                    break
                
                # Procesar comando de memoria
                memory_response = memoria.procesar_mensaje_usuario(user_input)
                if memory_response:
                    print(f"💭 Lune: {memory_response}\n")
                    continue

                # Chat normal
                print("🤖 Lune: ", end="", flush=True)
                
                response = await provider.chat(
                    message=user_input,
                    system_prompt=system_prompt,
                    on_token=self._on_token
                )

                print()  # Nueva línea después de la respuesta
                
                if response.startswith("❌"):
                    print(f"⚠️  {response}\n")
                else:
                    memoria.procesar_respuesta_lune(response)
                    conversation.append({
                        "user": user_input,
                        "assistant": response,
                        "timestamp": datetime.now().isoformat()
                    })
                    print()

            except KeyboardInterrupt:
                print("\n\n🌙 Chat interrumpido. Guardando...")
                break
            except Exception as e:
                logger.error(f"Error en chat: {e}")
                print(f"❌ Error: {e}\n")

    async def code_mode(self, prompt: str, model: Optional[str] = None):
        """Modo Claude Code — permite ejecutar código sugerido"""
        model = model or self.default_model
        
        config = OpenRouterConfig(api_key=self.api_key, model=model, enable_claude_code=True)
        provider = OpenRouterClaudeCodeProvider(config)

        system_prompt = (
            "Eres un asistente experto en programación. "
            "Cuando el usuario pida que escribas o ejecutes código, "
            "proporciona código completo y funcional en bloques de código. "
            "Explica qué hace cada parte."
        )

        print(f"\n💻 Claude Code Mode — {model}")
        print("📝 Generando código...\n")

        response = await provider.chat(
            message=prompt,
            system_prompt=system_prompt,
            on_token=self._on_token
        )

        if not response.startswith("❌"):
            # Extraer bloques de código
            code_blocks = self._extract_code_blocks(response)
            
            if code_blocks:
                print("\n" + "="*60)
                print("📦 Bloques de código detectados:")
                print("="*60)
                
                for i, (lang, code) in enumerate(code_blocks, 1):
                    print(f"\n[{i}] Lenguaje: {lang or 'Python'}")
                    print("-" * 40)
                    print(code)
                    print("-" * 40)
                    
                    # Opción para ejecutar (solo Python)
                    if lang == "python" or not lang:
                        save_file = input(f"💾 ¿Guardar bloque {i}? (s/n): ").lower()
                        if save_file == "s":
                            filename = input("   Nombre del archivo: ").strip()
                            if filename:
                                path = Path(filename)
                                FileManager.write_file(str(path), code)
                                print(f"   ✅ Guardado en: {path}")

    async def process_file(self, filepath: str, model: Optional[str] = None):
        """Procesa un archivo con la IA"""
        model = model or self.default_model
        
        path = Path(filepath)
        if not path.exists():
            print(f"❌ Archivo no encontrado: {filepath}")
            return

        content = FileManager.read_file(str(path))
        
        if not content:
            print(f"❌ El archivo está vacío: {filepath}")
            return

        message = f"Analiza y procesa el siguiente contenido:\n\n{content[:2000]}..."
        response = await self.chat_once(message, model)
        
        print(response)

    async def list_models(self):
        """Lista modelos disponibles"""
        models = list_free_models()
        
        print("\n" + "="*70)
        print("📋 Modelos Gratuitos Disponibles en OpenRouter")
        print("="*70 + "\n")
        
        for model in models:
            print(f"🔹 {model['id']}")
            print(f"   Nombre: {model['name']}")
            print(f"   {model['description']}\n")

    async def test_openrouter(self, model: Optional[str] = None):
        """Prueba la conexión a OpenRouter"""
        model = model or self.default_model
        
        print(f"\n🔍 Probando conexión a OpenRouter...")
        print(f"   Modelo: {model}\n")
        
        result = await test_connection(self.api_key, model)
        
        if result['success']:
            print(f"✅ {result['message']}")
            logger.info(f"OpenRouter test passed with model {model}")
        else:
            print(f"❌ {result['message']}")
            logger.error(f"OpenRouter test failed: {result['message']}")

    def _get_system_prompt(self) -> str:
        """Obtener prompt del sistema personalizado"""
        personaje = datos.get_personaje("Lune")
        return personaje.get("systemPrompt", 
            "Eres Lune, un asistente personal dedicado y profesional."
        )

    @staticmethod
    def _on_token(token: str):
        """Callback para tokens (streaming)"""
        print(token, end="", flush=True)

    @staticmethod
    def _extract_code_blocks(text: str) -> list:
        """Extrae bloques de código del texto"""
        import re
        # Buscar bloques ```language ... ```
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        return matches if matches else []


def main():
    parser = argparse.ArgumentParser(
        description="🌙 Lune CD v7.0 — Asistente con OpenRouter + Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  lune "¿Hola, cómo estás?"
  lune chat                                    # Chat interactivo
  lune code "escribe un script fibonacci"
  lune models                                  # Listar modelos
  lune test-connection
  lune file documento.txt --model openrouter/free

Modelos gratuitos recomendados:
  openrouter/free                              # Router automático (recomendado)
  google/gemini-2.0-flash-lite-preview-02-05:free
  meta-llama/llama-3.1-70b-instruct:free
        """
    )

    # Comandos principales
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Chat (defecto)
    parser.add_argument(
        "message",
        nargs="?",
        help="Mensaje o pregunta para Lune"
    )

    # Chat interactivo
    chat_parser = subparsers.add_parser("chat", help="Chat interactivo multi-turno")
    chat_parser.add_argument("--model", help="Modelo a usar")

    # Code mode
    code_parser = subparsers.add_parser("code", help="Modo Claude Code")
    code_parser.add_argument("prompt", help="Descripción del código a generar")
    code_parser.add_argument("--model", help="Modelo a usar")

    # Procesamiento de archivos
    file_parser = subparsers.add_parser("file", help="Procesar archivo")
    file_parser.add_argument("filepath", help="Ruta del archivo")
    file_parser.add_argument("--model", help="Modelo a usar")

    # Listar modelos
    subparsers.add_parser("models", help="Listar modelos disponibles")

    # Prueba de conexión
    test_parser = subparsers.add_parser("test-connection", help="Probar OpenRouter")
    test_parser.add_argument("--model", help="Modelo a probar")

    # Opciones globales
    parser.add_argument(
        "--model",
        help="Modelo OpenRouter a usar (default: openrouter/free)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Modo verbose (más logs)"
    )

    args = parser.parse_args()

    cli = LuneCLI()
    
    # Configurar logging
    if args.verbose:
        print("🔍 Modo verbose activado")

    try:
        # Router de comandos
        if args.command == "chat":
            asyncio.run(cli.chat_interactive(args.model))
        
        elif args.command == "code":
            asyncio.run(cli.code_mode(args.prompt, args.model))
        
        elif args.command == "file":
            asyncio.run(cli.process_file(args.filepath, args.model))
        
        elif args.command == "models":
            asyncio.run(cli.list_models())
        
        elif args.command == "test-connection":
            asyncio.run(cli.test_openrouter(args.model))
        
        elif args.message:
            # Chat de una sola pregunta (default)
            response = asyncio.run(cli.chat_once(args.message, args.model))
            print(f"\n🤖 Lune:\n{response}\n")
        
        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\n\n🌙 Lune se despide.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        print(f"❌ Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
