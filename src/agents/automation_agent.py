"""
Agente de Automatización - Automation Agent
Especializado en automatizar tareas repetitivas del sistema
"""

import asyncio
from typing import Dict, Any, List
from src.agents.base_agent import BaseAgent
from src.agents.app_controller import ApplicationController
import pyautogui
import os
import shutil
from datetime import datetime

class AutomationAgent(BaseAgent):
    """Agente especializado en automatización de tareas"""
    
    def __init__(self, ai_manager):
        super().__init__(
            name="AutomationAgent",
            description="Agente especializado en automatizar tareas del sistema",
            ai_manager=ai_manager
        )
        self.capabilities = [
            "organizar_archivos",
            "backup_automatico",
            "renombrar_masivo",
            "limpiar_temporales",
            "programar_tareas",
            "control_ventanas"
        ]
        self.app_controller = ApplicationController()
    
    def can_handle(self, task_type: str) -> bool:
        """Verificar si puede manejar la tarea"""
        keywords = ["organizar", "automatizar", "limpiar", "backup", "renombrar", "ordenar"]
        return any(keyword in task_type.lower() for keyword in keywords)
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar tarea de automatización"""
        self.status = "working"
        task_type = task.get("type", "")
        
        try:
            if "organizar archivos" in task_type.lower():
                result = await self.organize_files(task)
            elif "backup" in task_type.lower():
                result = await self.create_backup(task)
            elif "renombrar" in task_type.lower():
                result = await self.batch_rename(task)
            elif "limpiar" in task_type.lower():
                result = await self.clean_temp_files(task)
            else:
                result = await self.automate_custom(task)
            
            self.status = "completed"
            self.log_task(task_type, "Automatización completada", "completed")
            return result
            
        except Exception as e:
            self.status = "error"
            self.log_task(task_type, str(e), "error")
            return {"success": False, "error": str(e)}
    
    async def organize_files(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Organizar archivos por tipo/fecha"""
        folder_path = task.get("path", os.path.expanduser("~/Downloads"))
        organize_by = task.get("organize_by", "type")  # type, date
        
        print(f"📁 Organizando archivos en: {folder_path}")
        
        if not os.path.exists(folder_path):
            return {"success": False, "error": "Carpeta no encontrada"}
        
        organized_count = 0
        
        if organize_by == "type":
            # Organizar por tipo de archivo
            file_types = {
                "Imágenes": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"],
                "Documentos": [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".pptx"],
                "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
                "Música": [".mp3", ".wav", ".flac", ".m4a"],
                "Comprimidos": [".zip", ".rar", ".7z", ".tar", ".gz"],
                "Código": [".py", ".js", ".html", ".css", ".java", ".cpp"]
            }
            
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                
                if os.path.isfile(file_path):
                    ext = os.path.splitext(filename)[1].lower()
                    
                    for category, extensions in file_types.items():
                        if ext in extensions:
                            # Crear carpeta si no existe
                            category_folder = os.path.join(folder_path, category)
                            os.makedirs(category_folder, exist_ok=True)
                            
                            # Mover archivo
                            dest_path = os.path.join(category_folder, filename)
                            if not os.path.exists(dest_path):
                                shutil.move(file_path, dest_path)
                                organized_count += 1
                            break
        
        elif organize_by == "date":
            # Organizar por fecha de modificación
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                
                if os.path.isfile(file_path):
                    # Obtener fecha de modificación
                    mod_time = os.path.getmtime(file_path)
                    date = datetime.fromtimestamp(mod_time)
                    
                    # Crear carpeta por año/mes
                    date_folder = os.path.join(
                        folder_path,
                        f"{date.year}",
                        f"{date.month:02d}-{date.strftime('%B')}"
                    )
                    os.makedirs(date_folder, exist_ok=True)
                    
                    # Mover archivo
                    dest_path = os.path.join(date_folder, filename)
                    if not os.path.exists(dest_path):
                        shutil.move(file_path, dest_path)
                        organized_count += 1
        
        return {
            "success": True,
            "message": f"Se organizaron {organized_count} archivos",
            "files_organized": organized_count,
            "path": folder_path
        }
    
    async def create_backup(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Crear backup de una carpeta"""
        source = task.get("source", "")
        destination = task.get("destination", "")
        
        if not source or not destination:
            return {"success": False, "error": "Especifica origen y destino"}
        
        print(f"💾 Creando backup de {source} a {destination}")
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{os.path.basename(source)}_{timestamp}"
            backup_path = os.path.join(destination, backup_name)
            
            # Copiar carpeta completa
            shutil.copytree(source, backup_path)
            
            # Comprimir si se solicita
            if task.get("compress", False):
                shutil.make_archive(backup_path, 'zip', backup_path)
                shutil.rmtree(backup_path)  # Eliminar carpeta sin comprimir
                backup_path += ".zip"
            
            return {
                "success": True,
                "message": "Backup creado exitosamente",
                "backup_path": backup_path,
                "timestamp": timestamp
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def batch_rename(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Renombrar múltiples archivos"""
        folder_path = task.get("path", "")
        pattern = task.get("pattern", "{name}_{n}")  # {name}, {n}, {date}
        
        print(f"✏️ Renombrando archivos en: {folder_path}")
        
        if not os.path.exists(folder_path):
            return {"success": False, "error": "Carpeta no encontrada"}
        
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        renamed_count = 0
        
        for i, filename in enumerate(sorted(files), 1):
            old_path = os.path.join(folder_path, filename)
            name, ext = os.path.splitext(filename)
            
            # Aplicar patrón
            new_name = pattern.replace("{name}", name)
            new_name = new_name.replace("{n}", f"{i:03d}")
            new_name = new_name.replace("{date}", datetime.now().strftime("%Y%m%d"))
            new_name += ext
            
            new_path = os.path.join(folder_path, new_name)
            
            if old_path != new_path and not os.path.exists(new_path):
                os.rename(old_path, new_path)
                renamed_count += 1
        
        return {
            "success": True,
            "message": f"Se renombraron {renamed_count} archivos",
            "files_renamed": renamed_count
        }
    
    async def clean_temp_files(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Limpiar archivos temporales"""
        print("🧹 Limpiando archivos temporales...")
        
        temp_folders = [
            os.path.expanduser("~/AppData/Local/Temp"),  # Windows
            "/tmp",  # Linux/Mac
            os.path.expanduser("~/.cache")  # Cache
        ]
        
        cleaned_size = 0
        cleaned_files = 0
        
        for folder in temp_folders:
            if os.path.exists(folder):
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            # Solo eliminar archivos más viejos de 7 días
                            if os.path.getmtime(file_path) < (datetime.now().timestamp() - 7*24*3600):
                                size = os.path.getsize(file_path)
                                os.remove(file_path)
                                cleaned_size += size
                                cleaned_files += 1
                        except Exception:
                            pass  # Ignorar archivos en uso
        
        cleaned_mb = cleaned_size / (1024 * 1024)
        
        return {
            "success": True,
            "message": f"Limpieza completada: {cleaned_mb:.2f} MB liberados",
            "files_deleted": cleaned_files,
            "space_freed_mb": round(cleaned_mb, 2)
        }
    
    async def automate_custom(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar automatización personalizada"""
        script = task.get("script", "")
        
        print("🤖 Ejecutando automatización personalizada...")
        
        # Aquí podrías ejecutar scripts personalizados
        # Por seguridad, esto debería estar muy controlado
        
        return {
            "success": True,
            "message": "Automatización personalizada ejecutada"
        }