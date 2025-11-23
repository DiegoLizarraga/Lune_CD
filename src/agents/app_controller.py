"""
Controlador de aplicaciones del sistema
Permite abrir y controlar aplicaciones como Word, Excel, navegadores, etc.
"""

import subprocess
import platform
import psutil
import time
from typing import Optional, List, Dict

class ApplicationController:
    """Controlador para abrir y gestionar aplicaciones"""
    
    def __init__(self):
        self.os_type = platform.system()
        self.running_apps = {}
        
    def open_word(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Abrir Microsoft Word"""
        try:
            if self.os_type == "Windows":
                cmd = ["start", "winword"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd, shell=True)
            elif self.os_type == "Darwin":  # macOS
                cmd = ["open", "-a", "Microsoft Word"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
            else:  # Linux
                cmd = ["libreoffice", "--writer"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
                
            time.sleep(2)  # Esperar a que abra
            return {"success": True, "message": "Word abierto correctamente"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_excel(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Abrir Microsoft Excel"""
        try:
            if self.os_type == "Windows":
                cmd = ["start", "excel"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd, shell=True)
            elif self.os_type == "Darwin":
                cmd = ["open", "-a", "Microsoft Excel"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
            else:
                cmd = ["libreoffice", "--calc"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
                
            time.sleep(2)
            return {"success": True, "message": "Excel abierto correctamente"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_browser(self, url: str = "https://google.com") -> Dict[str, Any]:
        """Abrir navegador web"""
        try:
            if self.os_type == "Windows":
                subprocess.Popen(["start", url], shell=True)
            elif self.os_type == "Darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
                
            return {"success": True, "message": f"Navegador abierto con {url}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_notepad(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Abrir editor de texto"""
        try:
            if self.os_type == "Windows":
                cmd = ["notepad"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
            elif self.os_type == "Darwin":
                cmd = ["open", "-a", "TextEdit"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
            else:
                cmd = ["gedit" if file_path else "gedit"]
                if file_path:
                    cmd.append(file_path)
                subprocess.Popen(cmd)
                
            return {"success": True, "message": "Editor de texto abierto"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_vscode(self, folder_path: Optional[str] = None) -> Dict[str, Any]:
        """Abrir Visual Studio Code"""
        try:
            cmd = ["code"]
            if folder_path:
                cmd.append(folder_path)
            subprocess.Popen(cmd)
            return {"success": True, "message": "VS Code abierto"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_running_processes(self, name: str) -> List[Dict]:
        """Obtener procesos en ejecución por nombre"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if name.lower() in proc.info['name'].lower():
                    processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return processes
    
    def is_app_running(self, app_name: str) -> bool:
        """Verificar si una aplicación está corriendo"""
        return len(self.get_running_processes(app_name)) > 0
    
    def close_app(self, app_name: str) -> Dict[str, Any]:
        """Cerrar una aplicación"""
        try:
            processes = self.get_running_processes(app_name)
            for proc_info in processes:
                proc = psutil.Process(proc_info['pid'])
                proc.terminate()
            return {"success": True, "message": f"{app_name} cerrado"}
        except Exception as e:
            return {"success": False, "error": str(e)}