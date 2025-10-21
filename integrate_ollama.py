"""
Script de integración para actualizar Lune con Ollama
Ejecuta este script para actualizar automáticamente tu instalación
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path


class OllamaIntegrator:
    def __init__(self):
        self.system = platform.system()
        self.errors = []
        self.warnings = []
        
    def print_header(self, text):
        print("\n" + "="*60)
        print(f"  {text}")
        print("="*60 + "\n")
    
    def print_step(self, step, description):
        print(f"[{step}] {description}...")
    
    def print_success(self, message):
        print(f"  ✅ {message}")
    
    def print_error(self, message):
        print(f"  ❌ {message}")
        self.errors.append(message)
    
    def print_warning(self, message):
        print(f"  ⚠️  {message}")
        self.warnings.append(message)
    
    def check_python_version(self):
        """Verifica la versión de Python"""
        self.print_step("1/7", "Verificando versión de Python")
        
        version = sys.version_info
        if version.major >= 3 and version.minor >= 8:
            self.print_success(f"Python {version.major}.{version.minor}.{version.micro}")
            return True
        else:
            self.print_error(f"Python {version.major}.{version.minor} detectado. Se requiere Python 3.8+")
            return False
    
    def check_ollama_installed(self):
        """Verifica si Ollama está instalado"""
        self.print_step("2/7", "Verificando instalación de Ollama")
        
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version = result.stdout.strip()
                self.print_success(f"Ollama instalado ({version})")
                return True
            else:
                self.print_error("Ollama no está instalado")
                self._show_ollama_install_instructions()
                return False
                
        except FileNotFoundError:
            self.print_error("Ollama no está instalado")
            self._show_ollama_install_instructions()
            return False
        except Exception as e:
            self.print_error(f"Error al verificar Ollama: {str(e)}")
            return False
    
    def _show_ollama_install_instructions(self):
        """Muestra instrucciones de instalación de Ollama"""
        print("\n  📦 Instala Ollama:")
        
        if self.system == "Windows":
            print("     Descarga desde: https://ollama.com/download/windows")
        elif self.system == "Darwin":
            print("     brew install ollama")
        else:
            print("     curl -fsSL https://ollama.com/install.sh | sh")
    
    def check_ollama_running(self):
        """Verifica si Ollama está corriendo"""
        self.print_step("3/7", "Verificando si Ollama está corriendo")
        
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                self.print_success(f"Ollama corriendo ({len(models)} modelos descargados)")
                
                if len(models) == 0:
                    self.print_warning("No tienes modelos descargados. Ejecuta: ollama pull llama3.2:3b")
                else:
                    print(f"\n  Modelos disponibles:")
                    for model in models:
                        print(f"    • {model['name']}")
                
                return True
            else:
                self.print_error("Ollama no responde correctamente")
                return False
                
        except ImportError:
            self.print_error("requests no instalado. Instala con: pip install requests")
            return False
        except Exception as e:
            self.print_error(f"Ollama no está corriendo. Ejecuta: ollama serve")
            return False
    
    def install_dependencies(self):
        """Instala las dependencias necesarias"""
        self.print_step("4/7", "Instalando dependencias de Python")
        
        dependencies = [
            "langchain>=0.1.0",
            "langchain-community>=0.0.20",
            "ollama-python>=0.1.0",
            "httpx>=0.25.0",
            "pydantic>=2.0.0"
        ]
        
        try:
            for dep in dependencies:
                print(f"  Instalando {dep}...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep, "--quiet"],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    self.print_success(f"{dep.split('>=')[0]} instalado")
                else:
                    self.print_error(f"Error instalando {dep}: {result.stderr}")
                    return False
            
            return True
            
        except Exception as e:
            self.print_error(f"Error instalando dependencias: {str(e)}")
            return False
    
    def backup_files(self):
        """Crea backup de archivos existentes"""
        self.print_step("5/7", "Creando backup de archivos")
        
        files_to_backup = ["main.py", "local_model.py"]
        backup_dir = Path("backup_before_ollama")
        
        try:
            if not backup_dir.exists():
                backup_dir.mkdir()
            
            for file in files_to_backup:
                if Path(file).exists():
                    shutil.copy2(file, backup_dir / file)
                    self.print_success(f"Backup de {file} creado")
            
            return True
            
        except Exception as e:
            self.print_error(f"Error creando backup: {str(e)}")
            return False
    
    def update_main_py(self):
        """Actualiza main.py para usar el nuevo modelo"""
        self.print_step("6/7", "Actualizando main.py")
        
        try:
            with open("main.py", "r", encoding="utf-8") as f:
                content = f.read()
            
            # Reemplazar import
            content = content.replace(
                "from local_model import LocalModel",
                "from enhanced_model import EnhancedLocalModel"
            )
            
            # Reemplazar inicialización
            content = content.replace(
                "self.local_model = LocalModel()",
                """self.local_model = EnhancedLocalModel(
            model_name="llama3.2:3b",
            use_ollama=True
        )"""
            )
            
            with open("main.py", "w", encoding="utf-8") as f:
                f.write(content)
            
            self.print_success("main.py actualizado")
            return True
            
        except Exception as e:
            self.print_error(f"Error actualizando main.py: {str(e)}")
            return False
    
    def run_tests(self):
        """Ejecuta tests básicos"""
        self.print_step("7/7", "Ejecutando tests")
        
        try:
            # Test 1: Importar el módulo
            print("  Test 1: Importando enhanced_model...")
            from enhanced_model import EnhancedLocalModel
            self.print_success("Importación exitosa")
            
            # Test 2: Inicializar modelo
            print("  Test 2: Inicializando modelo...")
            model = EnhancedLocalModel(model_name="llama3.2:3b")
            self.print_success("Modelo inicializado")
            
            # Test 3: Generar respuesta
            print("  Test 3: Generando respuesta...")
            response = model.generate_response("Hola")
            if response:
                self.print_success(f"Respuesta generada: '{response[:50]}...'")
            else:
                self.print_warning("Respuesta vacía (puede ser normal si Ollama no está configurado)")
            
            return True
            
        except Exception as e:
            self.print_error(f"Error en tests: {str(e)}")
            return False
    
    def show_summary(self):
        """Muestra resumen de la instalación"""
        self.print_header("RESUMEN DE INSTALACIÓN")
        
        if not self.errors:
            print("  🎉 ¡Instalación completada exitosamente!")
            print("\n  Próximos pasos:")
            print("  1. Si no tienes modelos, descarga uno: ollama pull llama3.2:3b")
            print("  2. Ejecuta Lune: python main.py")
            print("  3. ¡Disfruta de respuestas más inteligentes!")
        else:
            print("  ⚠️  Se encontraron errores durante la instalación:")
            for error in self.errors:
                print(f"     • {error}")
            print("\n  Revisa los errores y vuelve a ejecutar el script.")
        
        if self.warnings:
            print("\n  Advertencias:")
            for warning in self.warnings:
                print(f"     • {warning}")
    
    def run(self):
        """Ejecuta el proceso completo de integración"""
        self.print_header("INTEGRACIÓN DE OLLAMA + LANGCHAIN EN LUNE")
        
        print("Este script te ayudará a actualizar Lune con capacidades de IA mejoradas.")
        print("El proceso incluye:")
        print("  • Verificar requisitos")
        print("  • Instalar dependencias")
        print("  • Actualizar código")
        print("  • Ejecutar tests")
        print("\n¿Deseas continuar? (s/n): ", end="")
        
        response = input().lower()
        if response != 's':
            print("Operación cancelada.")
            return False
        
        # Ejecutar pasos
        steps = [
            self.check_python_version,
            self.check_ollama_installed,
            self.check_ollama_running,
            self.install_dependencies,
            self.backup_files,
            self.update_main_py,
            self.run_tests
        ]
        
        for step_func in steps:
            if not step_func():
                print("\n⚠️  Proceso interrumpido debido a errores.")
                print("Revisa los mensajes de error arriba.")
                return False
        
        self.show_summary()
        return len(self.errors) == 0


def main():
    """Función principal"""
    integrator = OllamaIntegrator()
    success = integrator.run()
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()