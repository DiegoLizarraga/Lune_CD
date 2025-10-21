import pygame
import sys
import os
import threading
import tkinter as tk
from tkinter import scrolledtext, Entry, messagebox
import json
import re
import math
from datetime import datetime
import time
import platform
import subprocess
import keyboard  # Para atajos de teclado globales

# Importar los módulos existentes
from system_integration import SystemIntegration
from command_processor import CommandProcessor
from screen_analyzer import ScreenAnalyzer
from notification_manager import NotificationManager
from enhanced_model import EnhancedLocalModel
 # ahora vamos a reverervar lo del modelo local

class TerminalWindow:
    def __init__(self):
        self.root = None
        self.text_area = None
        self.input_field = None
        self.chat = None
        self.visible = False
        self.minimized = False
        self.setup_window()
        
    def setup_window(self):
        """Configura la ventana de la terminal"""
        self.root = tk.Tk()
        self.root.title("Lune CD - Asistente Virtual")
        self.root.geometry("800x600+50+50")  # Posición en la parte izquierda
        self.root.configure(bg="#1e1e1e")  # Fondo oscuro tipo terminal
        
        # Configurar para que la ventana esté siempre encima
        self.root.attributes("-topmost", True)
        
        # Hacer la ventana redimensionable
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Frame principal
        main_frame = tk.Frame(self.root, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Área de texto para el chat
        self.text_area = scrolledtext.ScrolledText(
            main_frame, 
            wrap=tk.WORD, 
            bg="#2d2d30", 
            fg="#f1f1f1", 
            font=("Consolas", 12),
            state=tk.DISABLED
        )
        self.text_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Frame para el campo de entrada
        input_frame = tk.Frame(main_frame, bg="#1e1e1e")
        input_frame.pack(fill=tk.X)
        
        # Campo de entrada
        self.input_field = Entry(
            input_frame, 
            bg="#3c3c3c", 
            fg="#f1f1f1", 
            font=("Consolas", 12),
            insertbackground="#f1f1f1"
        )
        self.input_field.pack(fill=tk.X, side=tk.LEFT, padx=(0, 10))
        self.input_field.bind("<Return>", self.process_input)
        
        # Botón de enviar
        send_button = tk.Button(
            input_frame, 
            text="Enviar", 
            bg="#007acc", 
            fg="white", 
            font=("Consolas", 10),
            command=self.process_input
        )
        send_button.pack(side=tk.RIGHT)
        
        # Configurar eventos de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<Control-q>", lambda e: self.quit_app())
        self.root.bind("<Control-t>", lambda e: self.toggle_visibility())
        
        # Inicialmente ocultar la ventana
        self.hide_window()
        
    def set_chat(self, chat):
        """Establece la instancia de chat"""
        self.chat = chat
        
    def show_window(self):
        """Muestra la ventana de terminal"""
        if not self.visible:
            self.root.deiconify()
            self.visible = True
            self.input_field.focus_set()
            
    def hide_window(self):
        """Oculta la ventana de terminal"""
        if self.visible:
            self.root.withdraw()
            self.visible = False
            
    def toggle_visibility(self):
        """Alterna la visibilidad de la ventana"""
        if self.visible:
            self.hide_window()
        else:
            self.show_window()
            
    def quit_app(self):
        """Cierra la aplicación"""
        if self.chat:
            self.chat.stop_chat()
        self.root.quit()
        self.root.destroy()
        sys.exit(0)
        
    def process_input(self, event=None):
        """Procesa la entrada del usuario"""
        user_input = self.input_field.get().strip()
        if not user_input:
            return
            
        # Limpiar campo de entrada
        self.input_field.delete(0, tk.END)
        
        # Mostrar entrada del usuario
        self.add_message("Tú", user_input)
        
        # Procesar con el chat
        if self.chat:
            response = self.chat.process_message(user_input)
            self.add_message("Lune", response)
            
    def add_message(self, sender, message):
        """Añade un mensaje al área de chat"""
        self.text_area.config(state=tk.NORMAL)
        
        # Añadir timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_area.insert(tk.END, f"[{timestamp}] ", "timestamp")
        
        # Añadir remitente
        if sender == "Tú":
            self.text_area.insert(tk.END, f"{sender}: ", "user")
        else:
            self.text_area.insert(tk.END, f"{sender}: ", "bot")
            
        # Añadir mensaje
        self.text_area.insert(tk.END, f"{message}\n\n")
        
        # Configurar etiquetas de estilo
        self.text_area.tag_config("timestamp", foreground="#888888")
        self.text_area.tag_config("user", foreground="#569cd6")
        self.text_area.tag_config("bot", foreground="#4ec9b0")
        
        # Desplazar al final
        self.text_area.see(tk.END)
        self.text_area.config(state=tk.DISABLED)
        
    def run(self):
        """Inicia el bucle principal de la ventana"""
        self.root.mainloop()

class LuneChat:
    def __init__(self, terminal_window):
        self.terminal_window = terminal_window
        self.system_integration = SystemIntegration()
        self.local_model = EnhancedLocalModel(
        model_name="nous-hermes2",  # el modelo de llama descargado
        use_ollama=True
        )
        self.command_processor = None
        self.screen_analyzer = ScreenAnalyzer()
        self.notification_manager = NotificationManager()
        self.running = False
        
        # Inicializar el procesador de comandos
        self.command_processor = CommandProcessor(self.system_integration, self)
        
        # Iniciar servicios en segundo plano
        self.system_integration.start_reminder_service(self.handle_reminder_notification)
        self.system_integration.start_screen_monitoring(self.handle_screen_content)
        self.notification_manager.start_notification_service()
        
        # Mensaje de bienvenida
        self.terminal_window.add_message("Lune", "¡Hola! Soy Lune, tu asistente virtual. ¿En qué puedo ayudarte?")
        
    def handle_reminder_notification(self, notification):
        """Maneja las notificaciones de recordatorios"""
        self.terminal_window.add_message("Recordatorio", notification)
        self.notification_manager.show_notification("Lune - Recordatorio", notification)
        
        # Mostrar la terminal si está oculta
        if not self.terminal_window.visible:
            self.terminal_window.show_window()
    
    def handle_screen_content(self, text):
        """Maneja el contenido de la pantalla capturado"""
        # Analizar el contenido de la pantalla
        analysis = self.screen_analyzer.analyze_text(text)
        
        # Si hay palabras clave importantes, procesarlas
        if analysis["important_keywords"]:
            # Aquí podrías implementar lógica para recordar temas importantes
            pass
    
    def process_message(self, user_message):
        """Procesa el mensaje del usuario"""
        message_lower = user_message.lower()
        
        # Comandos especiales
        if user_message.lower() in ['salir', 'exit', 'quit']:
            return "¡Hasta luego! Usa Ctrl+Q para cerrar la aplicación."
        
        if user_message.lower() in ['limpiar', 'clear', 'reset']:
            self.terminal_window.text_area.config(state=tk.NORMAL)
            self.terminal_window.text_area.delete(1.0, tk.END)
            self.terminal_window.text_area.config(state=tk.DISABLED)
            return "Historial limpiado. Empecemos de nuevo."
        
        if user_message.lower() in ['help', 'ayuda']:
            return self._show_help()
        
        # Procesar comandos del sistema primero
        if self.command_processor:
            command_response = self.command_processor.process_command(user_message)
            if command_response:
                return command_response
        
        # 1. Detectar si es una búsqueda web
        web_keywords = ['buscar', 'busca', 'search', 'google', 'web', 'internet', 'información sobre', 'qué es', 'dime sobre', 'explícame', 'cuéntame sobre']
        if any(keyword in message_lower for keyword in web_keywords):
            # Extraer la consulta de búsqueda
            query = user_message
            for keyword in web_keywords:
                query = query.replace(keyword, '').strip()
            
            if query:
                # Mostrar mensaje de "buscando" antes de obtener resultados
                self.terminal_window.add_message("Lune", f"Buscando información sobre '{query}'...")
                return self.system_integration.search_web(query)
            else:
                return "¿Qué te gustaría que busque? Puedes decirme por ejemplo 'busca información sobre los cerdos' o 'qué es la fotosíntesis'."

        # 2. Detectar si es un problema matemático
        if any(keyword in message_lower for keyword in ['calcular', 'resolver', 'matemática', 'suma', 'resta', 'multiplicar', 'dividir']) or re.search(r'[\d+\-*/()]', user_message):
            return self.solve_math(user_message)
        
        # 3. Si no es nada de lo anterior, usar el modelo local para conversar
        return self.local_model.generate_response(user_message)
    
    def solve_math(self, expression):
        """Resuelve expresiones matemáticas básicas"""
        try:
            clean_expr = re.sub(r'[^0-9+\-*/().\s]', '', expression)
            allowed_names = {
                k: v for k, v in math.__dict__.items() 
                if not k.startswith("__")
            }
            allowed_names.update({"abs": abs, "round": round})
            
            result = eval(clean_expr, {"__builtins__": {}}, allowed_names)
            return f"El resultado es: {result}"
        except Exception as e:
            return f"No pude resolver esa expresión: {str(e)}"
    
    def _show_help(self):
        """Muestra comandos disponibles"""
        help_text = """
Comandos disponibles:
• 'salir' - Cerrar el chat
• 'limpiar' - Limpiar historial de conversación
• 'ayuda' - Mostrar esta ayuda
• 'abre [aplicación]' - Abrir una aplicación
• 'toma nota [texto]' - Guardar una nota
• 'lista mis notas' - Ver todas las notas
• 'recuérdame [tarea] [tiempo]' - Añadir un recordatorio
• 'busca en pantalla [término]' - Buscar en historial de pantalla
• 'información del sistema' - Ver información del sistema
• 'busca [consulta]' - Buscar en internet
• Cualquier otra cosa - Hablar con Lune

Atajos de teclado:
• Ctrl+T - Mostrar/ocultar terminal
• Ctrl+Q - Cerrar aplicación
        """
        return help_text
    
    def stop_chat(self):
        """Detiene el chat"""
        self.running = False
        self.system_integration.stop_services()
        self.notification_manager.stop_notification_service()

def setup_global_hotkeys(terminal_window):
    """Configura atajos de teclado globales"""
    try:
        # Atajo para mostrar/ocultar la terminal
        keyboard.add_hotkey('ctrl+t', lambda: terminal_window.toggle_visibility())
        
        # Atajo para cerrar la aplicación
        keyboard.add_hotkey('ctrl+q', lambda: terminal_window.quit_app())
        
        return True
    except Exception as e:
        print(f"No se pudieron configurar los atajos de teclado globales: {str(e)}")
        print("Es posible que necesites ejecutar el programa como administrador.")
        return False

def main():
    try:
        # Crear ventana de terminal
        terminal_window = TerminalWindow()
        
        # Crear instancia de chat
        chat = LuneChat(terminal_window)
        terminal_window.set_chat(chat)
        
        # Configurar atajos de teclado globales
        hotkeys_setup = setup_global_hotkeys(terminal_window)
        
        if hotkeys_setup:
            print("Atajos de teclado globales configurados:")
            print("- Ctrl+T: Mostrar/ocultar terminal")
            print("- Ctrl+Q: Cerrar aplicación")
        else:
            print("No se pudieron configurar los atajos de teclado globales.")
            print("Los atajos solo funcionarán cuando la terminal esté activa.")
        
        # Iniciar el bucle principal de la ventana
        terminal_window.run()
        
    except Exception as e:
        print(f"Error al iniciar la aplicación: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()