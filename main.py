import pygame
import sys
import os
import threading
import tkinter as tk
from tkinter import scrolledtext, Entry, messagebox
import requests
import json
import re
import math
from datetime import datetime
import time

# Importar los nuevos módulos
from system_integration import SystemIntegration
from command_processor import CommandProcessor
from screen_analyzer import ScreenAnalyzer
from notification_manager import NotificationManager
from local_model import LocalModel

# Clase del ChatBot local
class LuneChatBot:
    def __init__(self, system_integration):
        # Ya no necesitamos API Key, headers, etc.
        self.system_integration = system_integration
        self.local_model = LocalModel() # <-- Usar nuestro modelo local
        
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
    
    def process_message(self, user_message):
        """Procesa el mensaje del usuario usando la lógica local y de búsqueda."""
        message_lower = user_message.lower()
        
        # 1. Detectar si es una búsqueda web
        web_keywords = ['buscar', 'busca', 'search', 'google', 'web', 'internet', 'información sobre']
        if any(keyword in message_lower for keyword in web_keywords):
            # Extraer la consulta de búsqueda
            query = user_message
            for keyword in web_keywords:
                query = query.replace(keyword, '').strip()
            
            if query:
                return self.system_integration.search_web(query)
            else:
                return "¿Qué te gustaría buscar?"

        # 2. Detectar si es un problema matemático
        if any(keyword in message_lower for keyword in ['calcular', 'resolver', 'matemática', 'suma', 'resta', 'multiplicar', 'dividir']) or re.search(r'[\d+\-*/()]', user_message):
            return self.solve_math(user_message)
        
        # 3. Si no es nada de lo anterior, usar el modelo local para conversar
        return self.local_model.generate_response(user_message)

# Clase para el chat en terminal (modificada)
class TerminalChat:
    def __init__(self, pet_window=None):
        self.chatbot = None
        self.running = False
        self.chat_thread = None
        self.pet_window = pet_window  # Referencia a la ventana de la mascota
        
        # Inicializar nuevos módulos
        self.system_integration = SystemIntegration()
        self.command_processor = None  # Se inicializará después de que el chatbot esté listo
        self.screen_analyzer = ScreenAnalyzer()
        self.notification_manager = NotificationManager()
        
    def initialize_chatbot(self):
        """Inicializa el chatbot local."""
        try:
            # El chatbot ahora necesita la integración del sistema para buscar
            self.chatbot = LuneChatBot(self.system_integration)
            self.command_processor = CommandProcessor(self.system_integration, self.chatbot)
            
            # Iniciar servicios en segundo plano
            self.system_integration.start_reminder_service(self.handle_reminder_notification)
            self.system_integration.start_screen_monitoring(self.handle_screen_content)
            self.notification_manager.start_notification_service()
            
            print("✅ Chatbot local inicializado correctamente.")
            return True
        except Exception as e:
            print(f"❌ Error al inicializar chatbot: {str(e)}")
            return False
    
    def handle_reminder_notification(self, notification):
        """Maneja las notificaciones de recordatorios"""
        print(f"\n🔔 {notification}")
        self.notification_manager.show_notification("Lune - Recordatorio", notification)
        
        # Si la mascota está activa, mostrar animación
        if self.pet_window:
            self.pet_window.show_notification(notification)
    
    def handle_screen_content(self, text):
        """Maneja el contenido de la pantalla capturado"""
        # Analizar el contenido de la pantalla
        analysis = self.screen_analyzer.analyze_text(text)
        
        # Si hay palabras clave importantes, procesarlas
        if analysis["important_keywords"]:
            # Aquí podrías implementar lógica para recordar temas importantes
            # Por ejemplo, guardar en un archivo de contexto
            pass
    
    def start_chat(self):
        """Inicia el chat en terminal en un hilo separado"""
        if not self.chatbot:
            if not self.initialize_chatbot():
                return
        
        if self.running:
            print("🔄 Chat ya está activo.")
            return
        
        self.running = True
        self.chat_thread = threading.Thread(target=self._chat_loop, daemon=True)
        self.chat_thread.start()
        print("🌙 Chat con Lune iniciado en terminal!")
        print("💡 Escribe 'salir' para cerrar el chat.")
        print("💡 Escribe 'limpiar' para limpiar historial.")
        print("-" * 50)
    
    def _chat_loop(self):
        """Bucle principal del chat en terminal"""
        print("🌙 Lune: ¡Hola! Soy Lune, tu asistente virtual. ¿En qué puedo ayudarte?")
        
        while self.running:
            try:
                # Usar input() para obtener entrada del usuario
                user_input = input("\n👤 Tú: ").strip()
                
                if not user_input:
                    continue
                
                # Comandos especiales
                if user_input.lower() in ['salir', 'exit', 'quit']:
                    print("🌙 Lune: ¡Hasta luego! 👋")
                    self.stop_chat()
                    break
                
                if user_input.lower() in ['limpiar', 'clear', 'reset']:
                    print("🌙 Lune: Historial limpiado. Empecemos de nuevo.")
                    continue
                
                if user_input.lower() in ['help', 'ayuda']:
                    self._show_help()
                    continue
                
                # Iniciar animación de "hablando" en la mascota
                if self.pet_window:
                    self.pet_window.start_talking_animation()
                
                # Procesar comandos del sistema primero
                if self.command_processor:
                    command_response = self.command_processor.process_command(user_input)
                    if command_response:
                        print(f"🌙 Lune: {command_response}")
                        
                        # Detener animación de "hablando"
                        if self.pet_window:
                            self.pet_window.stop_talking_animation()
                        continue
                
                # Procesar mensaje con el chatbot
                print("🌙 Lune: Pensando...")
                response = self.chatbot.process_message(user_input)
                print(f"🌙 Lune: {response}")
                
                # Detener animación de "hablando"
                if self.pet_window:
                    self.pet_window.stop_talking_animation()
                
            except KeyboardInterrupt:
                print("\n🌙 Lune: ¡Hasta luego! 👋")
                self.stop_chat()
                break
            except EOFError:
                print("\n🌙 Lune: ¡Hasta luego! 👋")
                self.stop_chat()
                break
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                # Detener animación en caso de error
                if self.pet_window:
                    self.pet_window.stop_talking_animation()
    
    def _show_help(self):
        """Muestra comandos disponibles"""
        print("\n📋 Comandos disponibles:")
        print("  • 'salir' - Cerrar el chat")
        print("  • 'limpiar' - Limpiar historial de conversación")
        print("  • 'ayuda' - Mostrar esta ayuda")
        print("  • 'abre [aplicación]' - Abrir una aplicación")
        print("  • 'toma nota [texto]' - Guardar una nota")
        print("  • 'lista mis notas' - Ver todas las notas")
        print("  • 'recuérdame [tarea] [tiempo]' - Añadir un recordatorio")
        print("  • 'busca en pantalla [término]' - Buscar en historial de pantalla")
        print("  • 'información del sistema' - Ver información del sistema")
        print("  • Cualquier otra cosa - Hablar con Lune")
        print("  • Ctrl+C - Forzar salida")
    
    def stop_chat(self):
        """Detiene el chat"""
        self.running = False
        self.system_integration.stop_services()
        self.notification_manager.stop_notification_service()

# Clase principal de la mascota (modificada para añadir notificaciones)
class DesktopPet:
    def __init__(self):
        # Inicializar Pygame
        pygame.init()
        
        # Obtener información de la pantalla
        info = pygame.display.Info()
        self.ANCHO_PANTALLA, self.ALTO_PANTALLA = info.current_w, info.current_h
        
        # Tamaño de la ventana de la mascota
        self.ANCHO_VENTANA = 170
        self.ALTO_VENTANA = 170
        
        # Posición en esquina inferior izquierda
        self.pos_ventana_x = 20
        self.pos_ventana_y = self.ALTO_PANTALLA - self.ALTO_VENTANA - 60
        
        # Configurar la posición de la ventana antes de crearla
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.pos_ventana_x},{self.pos_ventana_y}'
        
        # Crear ventana sin bordes y con transparencia
        self.ventana = pygame.display.set_mode((self.ANCHO_VENTANA, self.ALTO_VENTANA), pygame.NOFRAME)
        pygame.display.set_caption("Lune - Mascota Virtual")
        
        self.setup_transparency()
        self.load_images()
        
        # Variables de estado
        self.estado_actual = self.lune_normal
        self.tiempo_reaccion = 0
        self.arrastrar = False
        self.offset_x = 0
        self.offset_y = 0
        
        # Variables para animación de habla
        self.talking = False
        self.talk_animation_frame = 0
        self.talk_animation_speed = 200  # milisegundos entre frames
        self.last_talk_frame_time = 0
        self.talk_offset_x = 0
        self.talk_offset_y = 0
        
        # Variables para notificaciones
        self.notification_text = ""
        self.notification_time = 0
        self.showing_notification = False
        
        # Color de transparencia
        self.COLOR_TRANSPARENTE = (255, 0, 255)
        
        # Chat en terminal con referencia a esta ventana
        self.terminal_chat = TerminalChat(self)
        
        print("🌙 Mascota Lune iniciada!")
        print("- Haz clic en Lune para hacerla feliz")
        print("- Arrastra para mover la mascota")
        print("- Presiona Ctrl+N para hacerla feliz")
        print("- Presiona Ctrl+T para abrir chat en terminal")
        print("- Presiona Ctrl+Q para cerrar")
        print("- La ventana NO se puede cerrar con la X")
        
        print("✅ Iniciando chat en terminal...")
        # Iniciar chat en terminal automáticamente
        self.terminal_chat.start_chat()
    
    def show_notification(self, text):
        """Muestra una notificación en la mascota"""
        self.notification_text = text
        self.notification_time = pygame.time.get_ticks() + 5000  # 5 segundos
        self.showing_notification = True
        self.estado_actual = self.lune_feliz
    
    def start_talking_animation(self):
        """Inicia la animación de habla"""
        self.talking = True
        self.talk_animation_frame = 0
        self.last_talk_frame_time = pygame.time.get_ticks()
    
    def stop_talking_animation(self):
        """Detiene la animación de habla"""
        self.talking = False
        self.talk_offset_x = 0
        self.talk_offset_y = 0
    
    def update_talking_animation(self):
        """Actualiza la animación de habla"""
        if not self.talking:
            return
        
        current_time = pygame.time.get_ticks()
        if current_time - self.last_talk_frame_time > self.talk_animation_speed:
            self.talk_animation_frame = (self.talk_animation_frame + 1) % 4
            self.last_talk_frame_time = current_time
            
            # Crear movimiento sutil de "habla"
            if self.talk_animation_frame == 0:
                self.talk_offset_x = 0
                self.talk_offset_y = 0
            elif self.talk_animation_frame == 1:
                self.talk_offset_x = 2
                self.talk_offset_y = -1
            elif self.talk_animation_frame == 2:
                self.talk_offset_x = -1
                self.talk_offset_y = 1
            elif self.talk_animation_frame == 3:
                self.talk_offset_x = 1
                self.talk_offset_y = -2
    
    def setup_transparency(self):
        """Configurar transparencia de ventana"""
        try:
            import ctypes
            from ctypes import wintypes
            
            hwnd = pygame.display.get_wm_info()["window"]
            ctypes.windll.user32.SetWindowPos(hwnd, -1, self.pos_ventana_x, self.pos_ventana_y, 0, 0, 0x0001)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, 0x00080000 | 0x00000020)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x000000, 255, 0x00000002)
        except:
            print("No se pudo configurar transparencia (probablemente no estás en Windows)")
    
    def load_images(self):
        """Cargar y ajustar imágenes"""
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_normal = os.path.join(carpeta_actual, "Lune_normal.png")
        ruta_feliz = os.path.join(carpeta_actual, "Lune_feliz.png")
        
        # Crear imágenes por defecto si no existen
        self.create_default_images(ruta_normal, ruta_feliz)
        
        try:
            lune_normal_original = pygame.image.load(ruta_normal).convert_alpha()
            lune_feliz_original = pygame.image.load(ruta_feliz).convert_alpha()
            
            self.lune_normal, self.ancho_img, self.alto_img = self.ajustar_imagen(lune_normal_original)
            self.lune_feliz, _, _ = self.ajustar_imagen(lune_feliz_original)
            
            print(f"Imágenes cargadas y ajustadas a {self.ancho_img}x{self.alto_img}")
            
        except:
            print("Error al cargar las imágenes")
            pygame.quit()
            sys.exit()
    
    def create_default_images(self, ruta_normal, ruta_feliz):
        """Crear imágenes por defecto"""
        if not os.path.exists(ruta_normal):
            superficie = pygame.Surface((150, 150), pygame.SRCALPHA)
            pygame.draw.circle(superficie, (255, 200, 150), (75, 75), 70)
            pygame.draw.circle(superficie, (50, 50, 50), (55, 60), 8)
            pygame.draw.circle(superficie, (50, 50, 50), (95, 60), 8)
            pygame.draw.arc(superficie, (50, 50, 50), (60, 85, 30, 20), 0, 3.14, 3)
            pygame.draw.circle(superficie, (255, 180, 120), (40, 80), 12)
            pygame.draw.circle(superficie, (255, 180, 120), (110, 80), 12)
            pygame.image.save(superficie, ruta_normal)
        
        if not os.path.exists(ruta_feliz):
            superficie = pygame.Surface((150, 150), pygame.SRCALPHA)
            pygame.draw.circle(superficie, (255, 220, 180), (75, 75), 70)
            pygame.draw.arc(superficie, (30, 30, 30), (45, 55, 20, 15), 0, 3.14, 4)
            pygame.draw.arc(superficie, (30, 30, 30), (85, 55, 20, 15), 0, 3.14, 4)
            pygame.draw.arc(superficie, (30, 30, 30), (45, 80, 60, 35), 0, 3.14, 4)
            pygame.draw.circle(superficie, (255, 150, 150), (40, 80), 15)
            pygame.draw.circle(superficie, (255, 150, 150), (110, 80), 15)
            pygame.draw.circle(superficie, (255, 255, 255, 100), (65, 50), 8)
            pygame.image.save(superficie, ruta_feliz)
    
    def ajustar_imagen(self, imagen):
        """Ajustar imagen al tamaño de ventana"""
        ancho_original = imagen.get_width()
        alto_original = imagen.get_height()
        
        ratio_ancho = (self.ANCHO_VENTANA - 20) / ancho_original
        ratio_alto = (self.ALTO_VENTANA - 20) / alto_original
        ratio = min(ratio_ancho, ratio_alto)
        
        nuevo_ancho = int(ancho_original * ratio)
        nuevo_alto = int(alto_original * ratio)
        
        imagen_ajustada = pygame.transform.scale(imagen, (nuevo_ancho, nuevo_alto))
        return imagen_ajustada, nuevo_ancho, nuevo_alto
    
    def run(self):
        """Bucle principal"""
        reloj = pygame.time.Clock()
        ejecutando = True
        
        # Fuente para notificaciones
        try:
            pygame.font.init()
            self.font = pygame.font.SysFont('Arial', 12)
        except:
            self.font = None
        
        while ejecutando:
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    continue
                
                # Manejo de teclas
                if evento.type == pygame.KEYDOWN:
                    teclas = pygame.key.get_pressed()
                    mods = pygame.key.get_mods()
                    
                    # Cerrar SOLO con Ctrl + Q
                    if teclas[pygame.K_q] and (mods & pygame.KMOD_CTRL):
                        ejecutando = False
                        break
                    
                    # Cambiar a imagen feliz con Ctrl + N
                    if teclas[pygame.K_n] and (mods & pygame.KMOD_CTRL):
                        self.estado_actual = self.lune_feliz
                        self.tiempo_reaccion = pygame.time.get_ticks() + 2000
                    
                    # Activar/reactivar chat en terminal con Ctrl + T
                    if teclas[pygame.K_t] and (mods & pygame.KMOD_CTRL):
                        if not self.terminal_chat.running:
                            self.terminal_chat.start_chat()
                        else:
                            print("🔄 Chat en terminal ya está activo. Escribe en la consola.")
                
                # Manejo del mouse
                if evento.type == pygame.MOUSEBUTTONDOWN:
                    if evento.button == 1:
                        mouse_x, mouse_y = pygame.mouse.get_pos()
                        
                        pos_img_x = (self.ANCHO_VENTANA - self.ancho_img) // 2
                        pos_img_y = (self.ALTO_VENTANA - self.alto_img) // 2
                        
                        margen = 15
                        if (pos_img_x - margen <= mouse_x <= pos_img_x + self.ancho_img + margen) and \
                           (pos_img_y - margen <= mouse_y <= pos_img_y + self.alto_img + margen):
                            self.estado_actual = self.lune_feliz
                            self.tiempo_reaccion = pygame.time.get_ticks() + 2000
                        
                        self.arrastrar = True
                        self.offset_x = mouse_x
                        self.offset_y = mouse_y
                
                if evento.type == pygame.MOUSEBUTTONUP:
                    if evento.button == 1:
                        self.arrastrar = False
                
                if evento.type == pygame.MOUSEMOTION and self.arrastrar:
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    nueva_pos_x = self.pos_ventana_x + (mouse_x - self.offset_x)
                    nueva_pos_y = self.pos_ventana_y + (mouse_y - self.offset_y)
                    
                    nueva_pos_x = max(0, min(nueva_pos_x, self.ANCHO_PANTALLA - self.ANCHO_VENTANA))
                    nueva_pos_y = max(0, min(nueva_pos_y, self.ALTO_PANTALLA - self.ALTO_VENTANA))
                    
                    try:
                        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{nueva_pos_x},{nueva_pos_y}'
                        self.pos_ventana_x = nueva_pos_x
                        self.pos_ventana_y = nueva_pos_y
                    except:
                        pass
            
            # Actualizar animación de habla
            self.update_talking_animation()
            
            # Volver al estado normal
            if self.tiempo_reaccion and pygame.time.get_ticks() > self.tiempo_reaccion:
                self.estado_actual = self.lune_normal
                self.tiempo_reaccion = 0
            
            # Ocultar notificación después del tiempo
            if self.showing_notification and pygame.time.get_ticks() > self.notification_time:
                self.showing_notification = False
                self.estado_actual = self.lune_normal
            
            # Dibujar
            self.ventana.fill(self.COLOR_TRANSPARENTE)
            pos_x_centrada = (self.ANCHO_VENTANA - self.ancho_img) // 2 + self.talk_offset_x
            pos_y_centrada = (self.ALTO_VENTANA - self.alto_img) // 2 + self.talk_offset_y
            self.ventana.blit(self.estado_actual, (pos_x_centrada, pos_y_centrada))
            
            # Dibujar notificación si está activa
            if self.showing_notification and self.font:
                # Crear un fondo para la notificación
                notif_surface = pygame.Surface((self.ANCHO_VENTANA - 20, 40), pygame.SRCALPHA)
                notif_surface.fill((0, 0, 0, 180))  # Negro semitransparente
                
                # Dividir el texto en líneas si es necesario
                words = self.notification_text.split()
                lines = []
                current_line = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    text_width = self.font.size(test_line)[0]
                    
                    if text_width <= self.ANCHO_VENTANA - 30:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                # Dibujar cada línea
                y_offset = 5
                for line in lines[:2]:  # Máximo 2 líneas
                    text_surface = self.font.render(line, True, (255, 255, 255))
                    text_rect = text_surface.get_rect(center=(self.ANCHO_VENTANA // 2, y_offset + 10))
                    notif_surface.blit(text_surface, text_rect)
                    y_offset += 15
                
                # Posicionar la notificación debajo de la mascota
                notif_y = pos_y_centrada + self.alto_img + 5
                self.ventana.blit(notif_surface, (10, notif_y))
            
            pygame.display.flip()
            reloj.tick(60)
        
        self.cleanup()
    
    def cleanup(self):
        """Limpiar recursos"""
        try:
            if self.terminal_chat.running:
                self.terminal_chat.stop_chat()
        except:
            pass
        
        print("¡Hasta luego! 🌙")
        pygame.quit()
        sys.exit()

# Función principal
def main():
    try:
        pet = DesktopPet()
        pet.run()
    except Exception as e:
        print(f"Error al iniciar la mascota: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()