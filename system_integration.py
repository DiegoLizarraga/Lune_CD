import os
import platform
import subprocess
import time
from datetime import datetime
import json
import threading
import pyautogui
import pytesseract
from PIL import Image
import cv2
import numpy as np
from duckduckgo_search import DDGS

class SystemIntegration:
    def __init__(self):
        self.system = platform.system()
        self.notes_file = "lune_notes.json"
        self.reminders_file = "lune_reminders.json"
        self.screen_history = []
        self.reminders = self.load_reminders()
        self.notes = self.load_notes()
        self.reminder_thread = None
        self.screen_monitor_thread = None
        self.running = False
        
    def load_notes(self):
        try:
            with open(self.notes_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def save_notes(self):
        with open(self.notes_file, 'w') as f:
            json.dump(self.notes, f)
    
    def load_reminders(self):
        try:
            with open(self.reminders_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_reminders(self):
        with open(self.reminders_file, 'w') as f:
            json.dump(self.reminders, f)
    
    def open_application(self, app_name):
        """Abre una aplicación específica según el sistema operativo"""
        app_commands = {
            "visual studio code": ["code"],
            "vscode": ["code"],
            "compilador": ["code"],
            "navegador": self._get_browser_command(),
            "chrome": ["chrome"],
            "firefox": ["firefox"],
            "calculadora": self._get_calculator_command(),
            "notas": self._get_notes_command(),
            "explorador": self._get_explorer_command()
        }
        
        app_name_lower = app_name.lower()
        
        for key, command in app_commands.items():
            if key in app_name_lower:
                try:
                    subprocess.Popen(command)
                    return f"Abriendo {key}..."
                except Exception as e:
                    return f"No pude abrir {key}: {str(e)}"
        
        return f"No reconocí la aplicación '{app_name}'. ¿Podrías ser más específico?"
    
    def _get_browser_command(self):
        if self.system == "Windows":
            return ["start", "chrome"]
        elif self.system == "Darwin":  # macOS
            return ["open", "-a", "Google Chrome"]
        else:  # Linux
            return ["google-chrome"]
    
    def _get_calculator_command(self):
        if self.system == "Windows":
            return ["calc"]
        elif self.system == "Darwin":  # macOS
            return ["open", "-a", "Calculator"]
        else:  # Linux
            return ["gnome-calculator"]
    
    def _get_notes_command(self):
        if self.system == "Windows":
            return ["notepad"]
        elif self.system == "Darwin":  # macOS
            return ["open", "-a", "Notes"]
        else:  # Linux
            return ["gedit"]
    
    def _get_explorer_command(self):
        if self.system == "Windows":
            return ["explorer"]
        elif self.system == "Darwin":  # macOS
            return ["open", "."]
        else:  # Linux
            return ["nautilus"]
    
    def add_note(self, title, content):
        """Añade una nueva nota"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.notes[title] = {
            "content": content,
            "created_at": timestamp,
            "updated_at": timestamp
        }
        self.save_notes()
        return f"Nota '{title}' guardada."
    
    def get_note(self, title):
        """Recupera una nota específica"""
        if title in self.notes:
            return f"Nota: {title}\nContenido: {self.notes[title]['content']}\nCreada: {self.notes[title]['created_at']}"
        return f"No encontré ninguna nota con el título '{title}'."
    
    def list_notes(self):
        """Lista todas las notas"""
        if not self.notes:
            return "No tienes notas guardadas."
        
        result = "Tus notas:\n"
        for title, data in self.notes.items():
            result += f"- {title} (Creada: {data['created_at']})\n"
        return result
    
    def add_reminder(self, task, reminder_time):
        """Añade un nuevo recordatorio"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.reminders.append({
                "task": task,
                "reminder_time": reminder_time,
                "created_at": timestamp,
                "notified": False
            })
            self.save_reminders()
            return f"Recordatorio añadido: '{task}' para {reminder_time}"
        except Exception as e:
            return f"No pude añadir el recordatorio: {str(e)}"
    
    def check_reminders(self):
        """Verifica si hay recordatorios que notificar"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        for reminder in self.reminders:
            if not reminder["notified"] and reminder["reminder_time"] <= current_time:
                reminder["notified"] = True
                self.save_reminders()
                return f"⏰ Recordatorio: {reminder['task']}"
        
        return None
    
    def start_reminder_service(self, callback):
        """Inicia el servicio de recordatorios en segundo plano"""
        def reminder_loop():
            while self.running:
                notification = self.check_reminders()
                if notification:
                    callback(notification)
                time.sleep(30)  # Verificar cada 30 segundos
        
        if not self.reminder_thread or not self.reminder_thread.is_alive():
            self.running = True
            self.reminder_thread = threading.Thread(target=reminder_loop, daemon=True)
            self.reminder_thread.start()
            return True
        return False
    
    def capture_screen(self):
        """Captura la pantalla actual"""
        try:
            screenshot = pyautogui.screenshot()
            return screenshot
        except Exception as e:
            print(f"Error al capturar pantalla: {str(e)}")
            return None
    
    def analyze_screen(self, screenshot):
        """Analiza el contenido de la pantalla usando OCR"""
        try:
            # Convertir a numpy array y luego a escala de grises para mejor OCR
            img_array = np.array(screenshot)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Aplicar umbralización para mejorar el texto
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Extraer texto usando Tesseract OCR
            text = pytesseract.image_to_string(thresh, lang='spa')
            return text
        except Exception as e:
            print(f"Error al analizar pantalla: {str(e)}")
            return ""
    
    def start_screen_monitoring(self, callback, interval=60):
        """Inicia el monitoreo de pantalla en segundo plano"""
        def monitor_loop():
            while self.running:
                screenshot = self.capture_screen()
                if screenshot:
                    text = self.analyze_screen(screenshot)
                    if text.strip():
                        # Guardar en historial
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.screen_history.append({
                            "timestamp": timestamp,
                            "content": text[:500]  # Limitar a 500 caracteres
                        })
                        
                        # Mantener solo las últimas 10 capturas
                        if len(self.screen_history) > 10:
                            self.screen_history.pop(0)
                        
                        # Enviar a callback para procesamiento
                        callback(text)
                
                time.sleep(interval)
        
        if not self.screen_monitor_thread or not self.screen_monitor_thread.is_alive():
            self.running = True
            self.screen_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            self.screen_monitor_thread.start()
            return True
        return False
    
    def search_web(self, query):
        """Realiza una búsqueda en DuckDuckGo y devuelve los resultados formateados."""
        try:
            with DDGS() as ddgs:
                # ddgs.text devuelve un generador, lo convertimos a lista
                resultados = list(ddgs.text(query, region='wt-wt', safesearch='off', timelimit='y', max_results=5))
            
            if not resultados:
                return f"No encontré resultados para '{query}'."
            
            response = f"Resultados de búsqueda para '{query}':\n\n"
            for i, r in enumerate(resultados, 1):
                response += f"{i}. {r['title']}\n"
                response += f"   {r['body'][:150]}...\n"  # Mostrar un fragmento del contenido
                response += f"   🔗 {r['href']}\n\n"
            
            return response.strip()

        except Exception as e:
            return f"Error al realizar la búsqueda: {str(e)}"
    
    def search_screen_history(self, query):
        """Busca en el historial de pantalla"""
        results = []
        query_lower = query.lower()
        
        for entry in self.screen_history:
            if query_lower in entry["content"].lower():
                results.append({
                    "timestamp": entry["timestamp"],
                    "snippet": entry["content"][:100] + "..." if len(entry["content"]) > 100 else entry["content"]
                })
        
        if results:
            response = f"Encontré {len(results)} coincidencias con '{query}':\n"
            for result in results:
                response += f"- {result['timestamp']}: {result['snippet']}\n"
            return response
        else:
            return f"No encontré información sobre '{query}' en el historial de pantalla."
    
    def stop_services(self):
        """Detiene todos los servicios en segundo plano"""
        self.running = False