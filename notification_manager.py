
import platform
import subprocess
import threading
import time

class NotificationManager:
    def __init__(self):
        self.system = platform.system()
        self.notification_queue = []
        self.running = False
        self.notification_thread = None
        
    def show_notification(self, title, message, duration=5):
        """Muestra una notificación en el sistema"""
        if self.system == "Windows":
            self._show_windows_notification(title, message)
        elif self.system == "Darwin":  # macOS
            self._show_macos_notification(title, message)
        else:  # Linux
            self._show_linux_notification(title, message)
        
        # También agregar a la cola para procesamiento
        self.notification_queue.append({
            "title": title,
            "message": message,
            "duration": duration,
            "timestamp": time.time()
        })
    
    def _show_windows_notification(self, title, message):
        """Muestra una notificación en Windows"""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5)
        except ImportError:
            # Si win10toast no está instalado, usar método alternativo
            try:
                import win32api
                import win32con
                win32api.MessageBox(0, message, title, win32con.MB_OK | win32con.MB_ICONINFORMATION)
            except ImportError:
                # Último recurso: imprimir en consola
                print(f"NOTIFICACIÓN: {title} - {message}")
        except Exception as e:
            print(f"Error al mostrar notificación de Windows: {str(e)}")
    
    def _show_macos_notification(self, title, message):
        """Muestra una notificación en macOS"""
        try:
            subprocess.run([
                "osascript", "-e", f'display notification "{message}" with title "{title}"'
            ])
        except Exception as e:
            print(f"Error al mostrar notificación de macOS: {str(e)}")
    
    def _show_linux_notification(self, title, message):
        """Muestra una notificación en Linux"""
        try:
            subprocess.run([
                "notify-send", title, message
            ])
        except Exception as e:
            print(f"Error al mostrar notificación de Linux: {str(e)}")
    
    def start_notification_service(self, callback=None):
        """Inicia el servicio de notificaciones en segundo plano"""
        def notification_loop():
            while self.running:
                if self.notification_queue:
                    notification = self.notification_queue.pop(0)
                    
                    # Si hay un callback, llamarlo
                    if callback:
                        callback(notification)
                    
                    # Esperar el tiempo de duración antes de procesar la siguiente
                    time.sleep(notification["duration"])
                else:
                    time.sleep(1)
        
        if not self.notification_thread or not self.notification_thread.is_alive():
            self.running = True
            self.notification_thread = threading.Thread(target=notification_loop, daemon=True)
            self.notification_thread.start()
            return True
        return False
    
    def stop_notification_service(self):
        """Detiene el servicio de notificaciones"""
        self.running = False